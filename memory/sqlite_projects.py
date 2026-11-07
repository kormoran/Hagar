"""Progetti e decisioni sul database SQLite delle memorie."""

from __future__ import annotations

import json

from datetime import datetime
from pathlib import Path
from typing import Any

from memory.database import MemoryDatabase
from memory.projects import (
    DECISION_STATUSES,
    PROJECT_STATUSES,
    Decision,
    Project,
    ProjectError,
)
from memory.store import _iso_timestamp, slugify


class SqliteProjectStore:
    """Registry progetti e decision log, senza Vault."""

    def __init__(
        self,
        database: MemoryDatabase | str | Path,
    ) -> None:

        if isinstance(database, MemoryDatabase):
            self.database = database
        else:
            self.database = MemoryDatabase(database)

    def ensure(self) -> None:
        self.database.ensure()

    # ==================================================
    # Progetti
    # ==================================================

    def list_projects(
        self,
        include_archived: bool = False,
    ) -> list[Project]:

        where = "" if include_archived else " WHERE p.status = 'active'"

        with self.database.connection() as connection:

            rows = connection.execute(
                """
                SELECT p.*,
                       (SELECT COUNT(*) FROM decisions d
                        WHERE d.project_id = p.id
                          AND d.status = 'active') AS active_decisions
                FROM projects p
                """
                + where
                + " ORDER BY p.last_activity DESC"
            ).fetchall()

        return [self._row_to_project(row) for row in rows]

    def get_project(self, project_id: str) -> Project | None:

        with self.database.connection() as connection:

            row = connection.execute(
                """
                SELECT p.*,
                       (SELECT COUNT(*) FROM decisions d
                        WHERE d.project_id = p.id
                          AND d.status = 'active') AS active_decisions
                FROM projects p WHERE p.id = ?
                """,
                (project_id,),
            ).fetchone()

        return self._row_to_project(row) if row is not None else None

    def create_project(
        self,
        name: str,
        when: datetime | None = None,
    ) -> Project:

        if not isinstance(name, str) or not name.strip():
            raise ProjectError(
                "project name must be a non-empty string"
            )

        project_id = slugify(name.strip())

        if not project_id:
            raise ProjectError("invalid project name")

        moment = _iso_timestamp(when)

        with self.database.connection() as connection:

            existing = connection.execute(
                "SELECT id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()

            if existing is not None:
                raise ProjectError(
                    f"project already exists: {project_id}"
                )

            connection.execute(
                """
                INSERT INTO projects(
                    id, title, status, created_at,
                    last_activity, summary
                ) VALUES (?, ?, 'active', ?, ?, '')
                """,
                (project_id, name.strip(), moment, moment),
            )
            self.database.fts_upsert(
                connection,
                entity="project",
                entity_id=project_id,
                kind="project",
                project=project_id,
                status="active",
                title=name.strip(),
                body="",
            )

        project = self.get_project(project_id)

        if project is None:
            raise ProjectError(
                f"project not readable after creation: {project_id}"
            )

        return project

    def set_project_status(
        self,
        project_id: str,
        status: str,
        when: datetime | None = None,
    ) -> Project:

        if status not in PROJECT_STATUSES:
            raise ProjectError(
                "project status must be active or archived"
            )

        with self.database.connection() as connection:

            cursor = connection.execute(
                "UPDATE projects SET status = ?, last_activity = ? "
                "WHERE id = ?",
                (status, _iso_timestamp(when), project_id),
            )

            if cursor.rowcount == 0:
                raise ProjectError(
                    f"project not found: {project_id}"
                )

            row = connection.execute(
                "SELECT title, summary FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            self.database.fts_upsert(
                connection,
                entity="project",
                entity_id=project_id,
                kind="project",
                project=project_id,
                status=status,
                title=row["title"],
                body=row["summary"],
            )

        project = self.get_project(project_id)

        if project is None:
            raise ProjectError(
                f"project not readable after update: {project_id}"
            )

        return project

    def set_project_summary(
        self,
        project_id: str,
        summary: str,
        when: datetime | None = None,
    ) -> Project:

        with self.database.connection() as connection:

            cursor = connection.execute(
                "UPDATE projects SET summary = ?, last_activity = ? "
                "WHERE id = ?",
                (summary.strip(), _iso_timestamp(when), project_id),
            )

            if cursor.rowcount == 0:
                raise ProjectError(
                    f"project not found: {project_id}"
                )

            row = connection.execute(
                "SELECT title, status FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            self.database.fts_upsert(
                connection,
                entity="project",
                entity_id=project_id,
                kind="project",
                project=project_id,
                status=row["status"],
                title=row["title"],
                body=summary.strip(),
            )

        project = self.get_project(project_id)

        if project is None:
            raise ProjectError(
                f"project not readable after summary: {project_id}"
            )

        return project

    # ==================================================
    # Decisioni
    # ==================================================

    def create_decision(
        self,
        project_id: str,
        title: str,
        decision: str,
        alternatives: Any = None,
        rationale: str = "",
        status: str = "candidate",
        auto_saved: bool = False,
        session: str | None = None,
        turn: str | None = None,
        when: datetime | None = None,
    ) -> Decision:

        if status not in DECISION_STATUSES:
            raise ProjectError("invalid decision status")

        if not isinstance(title, str) or not title.strip():
            raise ProjectError(
                "decision title must be non-empty"
            )

        if not isinstance(decision, str) or not decision.strip():
            raise ProjectError(
                "decision text must be non-empty"
            )

        if self.get_project(project_id) is None:
            raise ProjectError(
                f"project not found: {project_id}"
            )

        moment = _iso_timestamp(when)
        decision_id = f"{moment[:10]}-{slugify(title)}"
        base_id = decision_id
        suffix = 2

        values = (
            [alternatives]
            if isinstance(alternatives, str)
            else (alternatives or [])
        )
        alternatives_tuple = tuple(
            str(item).strip()
            for item in values
            if str(item).strip()
        )

        with self.database.connection() as connection:

            while connection.execute(
                "SELECT id FROM decisions WHERE id = ?",
                (decision_id,),
            ).fetchone() is not None:

                decision_id = f"{base_id}-{suffix}"
                suffix += 1

            connection.execute(
                """
                INSERT INTO decisions(
                    id, project_id, title, decision, alternatives,
                    rationale, status, created_at, reviewed_at,
                    auto_saved, source_session, source_turn
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    project_id,
                    title.strip(),
                    decision.strip(),
                    json.dumps(
                        list(alternatives_tuple),
                        ensure_ascii=False,
                    ),
                    rationale.strip(),
                    status,
                    moment,
                    (
                        moment
                        if status in {"active", "archived"}
                        else None
                    ),
                    int(bool(auto_saved)),
                    session,
                    turn,
                ),
            )
            connection.execute(
                "UPDATE projects SET last_activity = ? WHERE id = ?",
                (moment, project_id),
            )
            self.database.fts_upsert(
                connection,
                entity="decision",
                entity_id=decision_id,
                kind="decision",
                project=project_id,
                status=status,
                title=title.strip(),
                body=decision.strip() + "\n" + rationale.strip(),
            )

        loaded = self.get_decision(project_id, decision_id)

        if loaded is None:
            raise ProjectError(
                f"decision not readable: {decision_id}"
            )

        return loaded

    def get_decision(
        self,
        project_id: str,
        decision_id: str,
    ) -> Decision | None:

        with self.database.connection() as connection:

            row = connection.execute(
                "SELECT * FROM decisions "
                "WHERE project_id = ? AND id = ?",
                (project_id, decision_id),
            ).fetchone()

        return self._row_to_decision(row) if row is not None else None

    def list_decisions(
        self,
        project_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Decision]:

        clauses = ["project_id = ?"]
        values: list[Any] = [project_id]

        if status is not None:
            clauses.append("status = ?")
            values.append(status)

        with self.database.connection() as connection:

            rows = connection.execute(
                "SELECT * FROM decisions WHERE "
                + " AND ".join(clauses)
                + " ORDER BY created_at DESC LIMIT ?",
                [*values, max(1, int(limit))],
            ).fetchall()

        return [self._row_to_decision(row) for row in rows]

    def review_queue(
        self,
        project_id: str,
        limit: int = 1000,
    ) -> list[Decision]:

        decisions = self.list_decisions(
            project_id,
            status="candidate",
            limit=limit,
        )
        decisions.sort(key=lambda item: item.created_at)
        return decisions

    def set_decision_status(
        self,
        project_id: str,
        decision_id: str,
        status: str,
        when: datetime | None = None,
    ) -> Decision:

        if status not in DECISION_STATUSES:
            raise ProjectError("invalid decision status")

        moment = _iso_timestamp(when)

        with self.database.connection() as connection:

            cursor = connection.execute(
                """
                UPDATE decisions
                SET status = ?,
                    reviewed_at = CASE
                        WHEN ? IN ('active', 'archived') THEN ?
                        ELSE reviewed_at
                    END
                WHERE project_id = ? AND id = ?
                """,
                (
                    status,
                    status,
                    moment,
                    project_id,
                    decision_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ProjectError(
                    f"decision not found: {decision_id}"
                )

            row = connection.execute(
                "SELECT title, decision, rationale "
                "FROM decisions WHERE project_id = ? AND id = ?",
                (project_id, decision_id),
            ).fetchone()
            self.database.fts_upsert(
                connection,
                entity="decision",
                entity_id=decision_id,
                kind="decision",
                project=project_id,
                status=status,
                title=row["title"],
                body=row["decision"] + "\n" + row["rationale"],
            )

        updated = self.get_decision(project_id, decision_id)

        if updated is None:
            raise ProjectError(
                f"decision not readable: {decision_id}"
            )

        return updated

    def mark_auto_saved(
        self,
        project_id: str,
        decision_ids: list[str],
    ) -> None:

        with self.database.connection() as connection:

            for decision_id in decision_ids:

                connection.execute(
                    "UPDATE decisions SET auto_saved = 1 "
                    "WHERE project_id = ? AND id = ?",
                    (project_id, decision_id),
                )

    # ==================================================
    # Ricerca e contesto
    # ==================================================

    def search_decisions(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[Decision]:

        needle = query.strip().lower()

        if not needle:
            return []

        matches = [
            item
            for item in self.list_decisions(
                project_id,
                limit=100000,
            )
            if (
                needle in item.title.lower()
                or needle in item.decision.lower()
                or needle in item.rationale.lower()
                or any(
                    needle in alt.lower()
                    for alt in item.alternatives
                )
            )
        ]

        return matches[: max(1, int(limit))]

    def context_index(
        self,
        project_id: str,
        max_decisions: int = 10,
        max_chars: int = 6000,
    ) -> tuple[str, int]:

        project = self.get_project(project_id)

        if project is None:
            return "", 0

        active = (
            self.list_decisions(
                project_id,
                status="active",
                limit=max_decisions,
            )
            if max_decisions > 0
            else []
        )

        lines = [
            f"Progetto: {project.title} [{project.id}]",
            f"Ultima attività: {project.last_activity}",
        ]

        if project.summary:
            lines.append(f"Sintesi: {project.summary.strip()}")

        if active:
            lines.append("Decisioni attive recenti:")
            for item in active:
                lines.append(
                    f"- {item.title} ({item.created_at[:10]}, "
                    f"{item.id})"
                )

        lines.append(
            f"Decisioni attive totali: {project.active_decisions}"
        )
        lines.append(
            "Dettagli: memory.project_context(query=...)"
        )

        text = "\n".join(lines)

        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"

        return text, len(active)

    @staticmethod
    def _row_to_project(row) -> Project:

        return Project(
            id=row["id"],
            title=row["title"],
            status=row["status"],
            created_at=row["created_at"],
            last_activity=row["last_activity"],
            summary=row["summary"],
            path=Path(f"sqlite:projects/{row['id']}"),
            active_decisions=int(row["active_decisions"]),
        )

    @staticmethod
    def _row_to_decision(row) -> Decision:

        return Decision(
            id=row["id"],
            project=row["project_id"],
            title=row["title"],
            decision=row["decision"],
            alternatives=tuple(
                json.loads(row["alternatives"] or "[]")
            ),
            rationale=row["rationale"],
            status=row["status"],
            created_at=row["created_at"],
            reviewed_at=row["reviewed_at"],
            auto_saved=bool(row["auto_saved"]),
            source_session=row["source_session"],
            source_turn=row["source_turn"],
            path=Path(f"sqlite:projects/{row['project_id']}/{row['id']}"),
        )
