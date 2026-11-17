"""Manutenzione temporale della memoria.

La retention archivia, non cancella. Le entità restano recuperabili e
possono essere ripristinate.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from memory.database import MemoryDatabase


class MemoryRetention:
    def __init__(
        self,
        database: MemoryDatabase,
        *,
        candidate_ttl_days: int = 30,
        summary_retention_days: int = 0,
        chat_retention_days: int = 0,
    ) -> None:

        self.database = database
        self.candidate_ttl_days = max(0, int(candidate_ttl_days))
        self.summary_retention_days = max(
            0,
            int(summary_retention_days),
        )
        self.chat_retention_days = max(
            0,
            int(chat_retention_days),
        )

    def sweep(self, now: datetime | None = None) -> dict[str, int]:

        moment = now or datetime.now().astimezone()
        counts = {
            "skills": 0,
            "decisions": 0,
            "summaries": 0,
            "sessions": 0,
        }

        with self.database.connection() as connection:

            if self.candidate_ttl_days:
                cutoff = self._cutoff(
                    moment,
                    self.candidate_ttl_days,
                )
                counts["skills"] = self._archive(
                    connection,
                    "skills",
                    "created_at",
                    cutoff,
                    "status = 'candidate'",
                )
                counts["decisions"] = self._archive(
                    connection,
                    "decisions",
                    "created_at",
                    cutoff,
                    "status = 'candidate'",
                )
                counts["summaries"] += self._archive(
                    connection,
                    "summaries",
                    "created_at",
                    cutoff,
                    "status = 'candidate'",
                )

            if self.summary_retention_days:
                cutoff = self._cutoff(
                    moment,
                    self.summary_retention_days,
                )
                counts["summaries"] += self._archive(
                    connection,
                    "summaries",
                    "created_at",
                    cutoff,
                    "status = 'confirmed'",
                )

            if self.chat_retention_days:
                cutoff = self._cutoff(
                    moment,
                    self.chat_retention_days,
                )
                cursor = connection.execute(
                    "UPDATE sessions SET archived = 1 "
                    "WHERE archived = 0 AND updated_at < ?",
                    (cutoff,),
                )
                counts["sessions"] = int(cursor.rowcount or 0)

            self._sync_fts(connection)
            self._sync_embeddings(connection, moment)

        return counts

    @staticmethod
    def _cutoff(
        moment: datetime,
        days: int,
    ) -> str:

        return (
            moment - timedelta(days=days)
        ).isoformat(timespec="seconds")

    @staticmethod
    def _archive(
        connection: Any,
        table: str,
        column: str,
        cutoff: str,
        condition: str,
    ) -> int:

        cursor = connection.execute(
            f"UPDATE {table} SET status = 'archived' "
            f"WHERE {condition} AND {column} < ?",
            (cutoff,),
        )
        return int(cursor.rowcount or 0)

    def _sync_fts(self, connection: Any) -> None:

        for entity, table in (
            ("skill", "skills"),
            ("summary", "summaries"),
            ("decision", "decisions"),
        ):
            connection.execute(
                f"""
                UPDATE memory_fts
                SET status = (
                    SELECT status FROM {table}
                    WHERE CAST({table}.id AS TEXT) =
                          memory_fts.entity_id
                )
                WHERE entity = ?
                """,
                (entity,),
            )

    def _sync_embeddings(
        self,
        connection: Any,
        moment: datetime,
    ) -> None:

        timestamp = moment.isoformat(timespec="seconds")

        for entity, table in (
            ("skill", "skills"),
            ("summary", "summaries"),
            ("decision", "decisions"),
        ):
            connection.execute(
                f"""
                UPDATE memory_embeddings
                SET status = (
                    SELECT status FROM {table}
                    WHERE CAST({table}.id AS TEXT) =
                          memory_embeddings.entity_id
                ),
                updated_at = ?
                WHERE entity = ?
                """,
                (timestamp, entity),
            )
