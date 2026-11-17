"""Rilevamento e migrazione dei vettori dopo un cambio modello."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.permissions import Capability
from core.permissions import ConfirmationRequest
from memory.database import MemoryDatabase


META_KEY = "embedding_model"


@dataclass(frozen=True, slots=True)
class MigrationStatus:

    changed: bool
    current: str
    recorded: str | None
    models: dict[str, int]

    @property
    def old_vectors(self) -> int:

        return sum(
            count
            for model, count in self.models.items()
            if model != self.current
        )


class EmbeddingMigration:
    """Chiede consenso e ricostruisce i vettori del nuovo modello."""

    def __init__(
        self,
        database: MemoryDatabase,
        index: Any,
        confirmation: Any,
        audit: Any = None,
    ) -> None:

        self.database = database
        self.index = index
        self.confirmation = confirmation
        self.audit = audit

    def inspect(self) -> MigrationStatus:

        with self.database.connection() as connection:

            rows = connection.execute(
                "SELECT model, COUNT(*) AS total "
                "FROM memory_embeddings GROUP BY model"
            ).fetchall()

            models = {
                str(row["model"]): int(row["total"])
                for row in rows
            }

            row = connection.execute(
                "SELECT value FROM meta WHERE key = ?",
                (META_KEY,),
            ).fetchone()

        current = str(self.index.model)
        recorded = str(row["value"]) if row else None

        if not models:
            return MigrationStatus(
                changed=False,
                current=current,
                recorded=recorded,
                models={},
            )

        if recorded is not None:
            changed = (
                recorded != current
                or current not in models
            )
        else:
            changed = current not in models

        return MigrationStatus(
            changed=changed,
            current=current,
            recorded=recorded,
            models=models,
        )

    def migrate(self) -> str:

        status = self.inspect()

        if not status.changed:
            self._record_current(status.current)
            return "unchanged"

        request = ConfirmationRequest(
            subject="embedding",
            tool="embedding.migrate",
            capabilities=Capability.MEMORY_WRITE,
            arguments={
                "current": status.current,
                "old_models": [
                    model
                    for model in status.models
                    if model != status.current
                ],
                "old_vectors": status.old_vectors,
            },
            reason=(
                "Il modello di embedding è cambiato. "
                "I vettori del modello precedente non sono "
                "compatibili. Posso scartarli e ricrearli "
                "con il modello corrente?"
            ),
        )

        approved = bool(
            self.confirmation.confirm(request)
        )

        if not approved:

            self._audit(
                "memory.embedding_migration",
                decision="declined",
                status=status,
            )
            return "declined"

        counts = self.index.reindex(
            prune_other_models=True,
        )
        self._record_current(status.current)
        self._audit(
            "memory.embedding_migration",
            decision="accepted",
            status=status,
            counts=counts,
        )

        return "migrated"

    def _record_current(self, current: str) -> None:

        with self.database.connection() as connection:

            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) "
                "VALUES (?, ?)",
                (META_KEY, current),
            )

    def _audit(
        self,
        event: str,
        **fields: Any,
    ) -> None:

        if self.audit is None:
            return

        status = fields.pop("status", None)

        if status is not None:
            fields.update({
                "current": status.current,
                "recorded": status.recorded,
                "old_models": [
                    model
                    for model in status.models
                    if model != status.current
                ],
                "old_vectors": status.old_vectors,
            })

        try:
            self.audit.record(event, **fields)
        except Exception:
            pass
