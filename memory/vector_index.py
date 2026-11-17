"""Indice vettoriale delle memorie su SQLite.

I vettori sono float32 in BLOB; la ricerca è cosine in Python. Non serve
un database vettoriale separato per i volumi di Hagar.
"""

from __future__ import annotations

import hashlib
import sqlite3
import struct

from dataclasses import dataclass
from typing import Any
from typing import Iterable

from memory.database import MemoryDatabase
from memory.embeddings import EmbeddingEngine
from memory.embeddings import EmbeddingError
from memory.store import _iso_timestamp


@dataclass(frozen=True, slots=True)
class EmbeddingHit:

    entity: str
    entity_id: str
    project: str | None
    status: str | None
    score: float

    def as_dict(self) -> dict[str, Any]:

        return {
            "entity": self.entity,
            "entity_id": self.entity_id,
            "project": self.project,
            "status": self.status,
            "score": round(self.score, 6),
        }


class MemoryEmbeddingIndex:
    """Salva e cerca vettori associati alle entità della memoria."""

    def __init__(
        self,
        database: MemoryDatabase,
        engine: EmbeddingEngine,
    ) -> None:

        self.database = database
        self.engine = engine

    @property
    def model(self) -> str:

        return self.engine.config.model

    @property
    def dimensions(self) -> int:

        return self.engine.dimensions

    def _pack(self, vector: list[float]) -> bytes:

        return struct.pack(
            f"<{len(vector)}f",
            *vector,
        )

    def _unpack(
        self,
        blob: bytes,
        dimensions: int,
    ) -> list[float]:

        if len(blob) != dimensions * 4:

            raise EmbeddingError(
                "invalid vector blob length: "
                f"{len(blob)} != {dimensions * 4}"
            )

        return list(
            struct.unpack(f"<{dimensions}f", blob)
        )

    @staticmethod
    def _content_hash(text: str) -> str:

        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

    def upsert(
        self,
        entity: str,
        entity_id: str,
        text: str,
        *,
        project: str | None = None,
        status: str | None = None,
        vector: list[float] | None = None,
    ) -> bool:
        """Salva il vettore; restituisce True se è cambiato."""

        if not entity.strip() or not entity_id.strip():
            raise EmbeddingError(
                "entity and entity_id are required"
            )

        if not text.strip():
            raise EmbeddingError("cannot index an empty text")

        digest = self._content_hash(text)
        dimensions = self.dimensions

        with self.database.connection() as connection:

            existing = connection.execute(
                """
                SELECT content_hash, dimensions
                FROM memory_embeddings
                WHERE entity = ? AND entity_id = ? AND model = ?
                """,
                (entity, entity_id, self.model),
            ).fetchone()

            if (
                existing is not None
                and existing["content_hash"] == digest
                and int(existing["dimensions"]) == dimensions
            ):
                return False

            if vector is None:

                vector = self.engine.embed_documents([text])[0]

            if len(vector) != dimensions:

                raise EmbeddingError(
                    "embedding dimension mismatch: "
                    f"{len(vector)} != {dimensions}"
                )

            connection.execute(
                """
                INSERT OR REPLACE INTO memory_embeddings(
                    entity, entity_id, project, status,
                    model, dimensions, vector,
                    content_hash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity,
                    entity_id,
                    project,
                    status,
                    self.model,
                    dimensions,
                    sqlite3.Binary(self._pack(vector)),
                    digest,
                    _iso_timestamp(),
                ),
            )

        return True

    def delete(
        self,
        entity: str,
        entity_id: str,
    ) -> None:

        with self.database.connection() as connection:

            connection.execute(
                """
                DELETE FROM memory_embeddings
                WHERE entity = ? AND entity_id = ? AND model = ?
                """,
                (entity, entity_id, self.model),
            )

    def prune_other_models(self) -> int:

        with self.database.connection() as connection:

            cursor = connection.execute(
                "DELETE FROM memory_embeddings WHERE model != ?",
                (self.model,),
            )

        return int(cursor.rowcount or 0)

    def search(
        self,
        query: str,
        *,
        project: str | None = None,
        entity_types: Iterable[str] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        include_archived: bool = False,
    ) -> list[EmbeddingHit]:

        if not query.strip():
            return []

        query_vector = self.engine.embed_query(query)
        clauses = [
            "model = ?",
            "dimensions = ?",
        ]
        values: list[Any] = [
            self.model,
            self.dimensions,
        ]

        if project is not None:

            clauses.append("project = ?")
            values.append(project)

        if entity_types is not None:

            kinds = [
                str(item)
                for item in entity_types
                if str(item).strip()
            ]

            if not kinds:
                return []

            placeholders = ", ".join(
                "?" for _ in kinds
            )
            clauses.append(
                f"entity IN ({placeholders})"
            )
            values.extend(kinds)

        with self.database.connection() as connection:

            rows = connection.execute(
                "SELECT entity, entity_id, project, status, vector "
                "FROM memory_embeddings WHERE "
                + " AND ".join(clauses),
                values,
            ).fetchall()

        hits = []

        for row in rows:

            if (
                not include_archived
                and row["status"] == "archived"
            ):
                continue

            try:

                vector = self._unpack(
                    bytes(row["vector"]),
                    self.dimensions,
                )

            except EmbeddingError:
                continue

            score = sum(
                left * right
                for left, right in zip(
                    query_vector,
                    vector,
                )
            )

            if score <= 0.0 or score < min_score:
                continue

            hits.append(
                EmbeddingHit(
                    entity=str(row["entity"]),
                    entity_id=str(row["entity_id"]),
                    project=row["project"],
                    status=row["status"],
                    score=float(score),
                )
            )

        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:max(1, int(limit))]

    def stats(self) -> dict[str, Any]:

        with self.database.connection() as connection:

            rows = connection.execute(
                """
                SELECT entity, model, dimensions, COUNT(*) AS total
                FROM memory_embeddings
                GROUP BY entity, model, dimensions
                ORDER BY entity
                """
            ).fetchall()

        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "entities": {
                row["entity"]: int(row["total"])
                for row in rows
            },
            "total": sum(
                int(row["total"])
                for row in rows
            ),
        }

    def _items(self) -> list[tuple[str, str, str, str | None, str | None]]:

        with self.database.connection() as connection:

            items: list[tuple[str, str, str, str | None, str | None]] = []

            for row in connection.execute(
                "SELECT id, title, content, status FROM skills"
            ):
                items.append((
                    "skill",
                    str(row["id"]),
                    f"{row['title']}\n{row['content']}",
                    None,
                    row["status"],
                ))

            for row in connection.execute(
                "SELECT id, session_id, project, body, status "
                "FROM summaries"
            ):
                items.append((
                    "summary",
                    str(row["id"]),
                    str(row["body"]),
                    row["project"],
                    row["status"],
                ))

            for row in connection.execute(
                "SELECT id, project_id, title, decision, rationale, status "
                "FROM decisions"
            ):
                items.append((
                    "decision",
                    str(row["id"]),
                    "\n".join([
                        str(row["title"]),
                        str(row["decision"]),
                        str(row["rationale"] or ""),
                    ]),
                    row["project_id"],
                    row["status"],
                ))

            for row in connection.execute(
                "SELECT id, title, summary, status FROM projects"
            ):
                items.append((
                    "project",
                    str(row["id"]),
                    f"{row['title']}\n{row['summary'] or ''}",
                    str(row["id"]),
                    row["status"],
                ))

        return items

    def reindex(
        self,
        *,
        batch_size: int = 16,
        prune_other_models: bool = False,
    ) -> dict[str, int]:

        items = self._items()
        counts = {
            "skill": 0,
            "summary": 0,
            "decision": 0,
            "project": 0,
            "updated": 0,
            "unchanged": 0,
            "pruned": 0,
        }
        batch_size = max(1, int(batch_size))

        for start in range(0, len(items), batch_size):

            batch = items[start:start + batch_size]
            texts = [item[2] for item in batch]
            vectors = self.engine.embed_documents(texts)

            for item, vector in zip(batch, vectors):

                entity, entity_id, text, project, status = item
                changed = self.upsert(
                    entity,
                    entity_id,
                    text,
                    project=project,
                    status=status,
                    vector=vector,
                )

                if changed:
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1

                if entity in counts:
                    counts[entity] += 1

        if prune_other_models:
            counts["pruned"] = self.prune_other_models()

        return counts
