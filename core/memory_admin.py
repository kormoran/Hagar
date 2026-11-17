"""Azioni di review delle memorie dalla Web UI."""

from __future__ import annotations

from typing import Any


class MemoryAdminError(RuntimeError):
    pass


KINDS = {"project", "skill", "summary"}
ACTIONS = {"confirm", "archive", "delete"}


class MemoryAdmin:
    """Legge e modifica le memorie candidate nel database SQLite."""

    def __init__(
        self,
        memory: Any,
        projects: Any = None,
        audit: Any = None,
    ) -> None:

        self.memory = memory
        self.projects = projects
        self.audit = audit
        self.database = getattr(memory, "database", None)

        if self.database is None:
            raise MemoryAdminError(
                "memory review requires the SQLite backend"
            )

    def list(self, kind: str) -> list[dict[str, Any]]:

        if kind not in KINDS:
            raise MemoryAdminError(f"unknown memory kind: {kind}")

        with self.database.connection() as connection:

            if kind == "skill":

                rows = connection.execute(
                    """
                    SELECT id, title, content, tags, created_at
                    FROM skills
                    WHERE status = 'candidate'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 500
                    """
                ).fetchall()

                return [
                    {
                        "kind": "skill",
                        "id": str(row["id"]),
                        "title": str(row["title"]),
                        "text": str(row["content"]),
                        "project": None,
                        "status": "candidate",
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]

            if kind == "project":

                rows = connection.execute(
                    """
                    SELECT d.id, d.project_id, d.title, d.decision,
                           d.rationale, d.created_at,
                           p.title AS project_title
                    FROM decisions d
                    LEFT JOIN projects p ON p.id = d.project_id
                    WHERE d.status = 'candidate'
                    ORDER BY d.created_at DESC, d.id DESC
                    LIMIT 500
                    """
                ).fetchall()

                return [
                    {
                        "kind": "project",
                        "id": str(row["id"]),
                        "title": str(row["title"]),
                        "text": "\n".join([
                            str(row["decision"]),
                            str(row["rationale"] or ""),
                        ]).strip(),
                        "project": str(row["project_id"]),
                        "project_title": (
                            str(row["project_title"])
                            if row["project_title"]
                            else str(row["project_id"])
                        ),
                        "status": "candidate",
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]

            rows = connection.execute(
                """
                SELECT id, session_id, project, body, created_at
                FROM summaries
                WHERE status = 'candidate'
                ORDER BY created_at DESC, id DESC
                LIMIT 500
                """
            ).fetchall()

            return [
                {
                    "kind": "summary",
                    "id": str(row["id"]),
                    "title": "Sessione " + str(row["session_id"]),
                    "text": str(row["body"]),
                    "project": row["project"],
                    "status": "candidate",
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def act(
        self,
        kind: str,
        item_id: str,
        action: str,
    ) -> str:

        if kind not in KINDS:
            raise MemoryAdminError(f"unknown memory kind: {kind}")

        if action not in ACTIONS:
            raise MemoryAdminError(f"unknown action: {action}")

        if action == "delete":
            self._delete(kind, item_id)
        else:
            status = (
                "confirmed"
                if kind in {"skill", "summary"}
                else "active"
            ) if action == "confirm" else "archived"
            self._set_status(kind, item_id, status)

        if self.audit is not None:

            try:
                self.audit.record(
                    "memory.review_web",
                    kind=kind,
                    id=item_id,
                    action=action,
                )
            except Exception:
                pass

        return action

    def _set_status(
        self,
        kind: str,
        item_id: str,
        status: str,
    ) -> None:

        with self.database.connection() as connection:

            if kind == "skill":

                cursor = connection.execute(
                    "UPDATE skills SET status = ?, updated_at = ? "
                    "WHERE id = ?",
                    (status, self._now(), item_id),
                )
                if cursor.rowcount == 0:
                    raise MemoryAdminError("skill not found")

                row = connection.execute(
                    "SELECT title, content FROM skills WHERE id = ?",
                    (item_id,),
                ).fetchone()
                self._fts(
                    connection,
                    "skill",
                    item_id,
                    "skill",
                    None,
                    status,
                    row["title"],
                    row["content"],
                )

            elif kind == "project":

                row = connection.execute(
                    "SELECT project_id, title, decision, rationale "
                    "FROM decisions WHERE id = ?",
                    (item_id,),
                ).fetchone()
                if row is None:
                    raise MemoryAdminError("decision not found")

                connection.execute(
                    "UPDATE decisions SET status = ?, reviewed_at = ? "
                    "WHERE id = ?",
                    (status, self._now(), item_id),
                )
                self._fts(
                    connection,
                    "decision",
                    item_id,
                    "decision",
                    row["project_id"],
                    status,
                    row["title"],
                    f"{row['decision']}\n{row['rationale'] or ''}",
                )

            else:

                cursor = connection.execute(
                    "UPDATE summaries SET status = ? WHERE id = ?",
                    (status, item_id),
                )
                if cursor.rowcount == 0:
                    raise MemoryAdminError("summary not found")

                row = connection.execute(
                    "SELECT session_id, project, body "
                    "FROM summaries WHERE id = ?",
                    (item_id,),
                ).fetchone()
                self._fts(
                    connection,
                    "summary",
                    item_id,
                    "summary",
                    row["project"],
                    status,
                    f"Summary {row['session_id']}",
                    row["body"],
                )

            self._embedding_status(
                connection,
                kind,
                item_id,
                status,
            )

    def _delete(
        self,
        kind: str,
        item_id: str,
    ) -> None:

        with self.database.connection() as connection:

            if kind == "skill":
                cursor = connection.execute(
                    "DELETE FROM skills WHERE id = ?",
                    (item_id,),
                )
            elif kind == "project":
                cursor = connection.execute(
                    "DELETE FROM decisions WHERE id = ?",
                    (item_id,),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM summaries WHERE id = ?",
                    (item_id,),
                )

            if cursor.rowcount == 0:
                raise MemoryAdminError(
                    f"{kind} memory not found"
                )

            self.database.fts_delete(
                connection,
                self._entity(kind),
                item_id,
            )
            connection.execute(
                "DELETE FROM memory_embeddings "
                "WHERE entity = ? AND entity_id = ?",
                (self._entity(kind), item_id),
            )

    def _embedding_status(
        self,
        connection: Any,
        kind: str,
        item_id: str,
        status: str,
    ) -> None:

        connection.execute(
            "UPDATE memory_embeddings SET status = ?, updated_at = ? "
            "WHERE entity = ? AND entity_id = ?",
            (
                status,
                self._now(),
                self._entity(kind),
                item_id,
            ),
        )

    @staticmethod
    def _entity(kind: str) -> str:

        return "decision" if kind == "project" else kind

    def _fts(
        self,
        connection: Any,
        entity: str,
        entity_id: str,
        kind: str,
        project: str | None,
        status: str | None,
        title: str,
        body: str,
    ) -> None:

        self.database.fts_upsert(
            connection,
            entity=entity,
            entity_id=entity_id,
            kind=kind,
            project=project,
            status=status,
            title=title,
            body=body or "",
        )

    @staticmethod
    def _now() -> str:

        from memory.store import _iso_timestamp

        return _iso_timestamp()
