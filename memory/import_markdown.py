"""Import di una struttura Markdown nel database SQLite."""

from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from memory.database import MemoryDatabase
from memory.store import (
    MemoryError,
    _parse_turns,
    _split_frontmatter,
)


class MarkdownImportError(MemoryError):
    pass


class MarkdownImporter:
    """Importa chat, skill, summary, progetti e decisioni."""

    def __init__(
        self,
        database: MemoryDatabase,
        source: str | Path,
        replace: bool = False,
    ) -> None:

        self.database = database
        self.source = Path(source)
        self.replace = bool(replace)
        self.base = self._base_dir()

    def _base_dir(self) -> Path:

        if not self.source.is_dir():
            raise MarkdownImportError(
                f"source directory not found: {self.source}"
            )

        nested = self.source / "Hagar"

        if nested.is_dir():
            return nested

        return self.source

    def run(self) -> dict[str, Any]:

        self.database.ensure()
        counts = {
            "sessions": 0,
            "turns": 0,
            "skills": 0,
            "summaries": 0,
            "projects": 0,
            "decisions": 0,
            "skipped": 0,
        }

        self._import_chats(counts)
        self._import_skills(counts)
        self._import_summaries(counts)
        self._import_projects(counts)

        with self.database.connection() as connection:
            self.database.rebuild_fts(connection)

        counts["source"] = str(self.base)
        return counts

    # ==================================================
    # Chat
    # ==================================================

    def _chat_files(self) -> list[tuple[Path, bool]]:

        files: list[tuple[Path, bool]] = []

        for folder, archived in (
            (self.base / "chat", False),
            (self.base / "archive" / "chat", True),
        ):

            if folder.is_dir():
                files.extend(
                    (path, archived)
                    for path in sorted(folder.glob("*.md"))
                )

        return files

    def _import_chats(self, counts: dict[str, int]) -> None:

        seen_sessions: set[str] = set()

        for path, archived in self._chat_files():

            text = path.read_text(encoding="utf-8", errors="ignore")
            turns = _parse_turns(text, path.stem)

            for turn in turns:

                with self.database.connection() as connection:

                    exists = connection.execute(
                        "SELECT 1 FROM turns "
                        "WHERE session_id = ? AND turn_id = ?",
                        (turn.session, turn.turn_id),
                    ).fetchone() is not None

                    if exists and not self.replace:
                        counts["skipped"] += 1
                        continue

                    title = (
                        turn.question.strip().splitlines()[0][:100]
                        or turn.session
                    )

                    connection.execute(
                        """
                        INSERT INTO sessions(
                            id, title, created_at, updated_at, archived
                        ) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            updated_at = excluded.updated_at,
                            archived = MAX(archived, excluded.archived)
                        """,
                        (
                            turn.session,
                            title,
                            turn.timestamp,
                            turn.timestamp,
                            int(archived),
                        ),
                    )
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO turns(
                            session_id, turn_id, timestamp,
                            question, answer
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            turn.session,
                            turn.turn_id,
                            turn.timestamp,
                            turn.question,
                            turn.answer,
                        ),
                    )

                    if not exists:
                        counts["turns"] += 1

                if not archived and turn.session not in seen_sessions:
                    seen_sessions.add(turn.session)
                    counts["sessions"] += 1

    # ==================================================
    # Skill
    # ==================================================

    def _import_skills(self, counts: dict[str, int]) -> None:

        folder = self.base / "skills"

        if not folder.is_dir():
            return

        for path in sorted(folder.glob("*.md")):

            text = path.read_text(encoding="utf-8", errors="ignore")
            meta, body = _split_frontmatter(text)

            if not meta:
                counts["skipped"] += 1
                continue

            skill_id = str(meta.get("id") or path.stem)

            with self.database.connection() as connection:

                exists = connection.execute(
                    "SELECT 1 FROM skills WHERE id = ?",
                    (skill_id,),
                ).fetchone() is not None

                if exists and not self.replace:
                    counts["skipped"] += 1
                    continue

                tags = meta.get("tags") or []
                if not isinstance(tags, list):
                    tags = []

                timestamp = str(meta.get("created_at") or "")
                connection.execute(
                    """
                    INSERT OR REPLACE INTO skills(
                        id, title, kind, status, content, tags,
                        created_at, updated_at, source_session,
                        source_turn, model
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        skill_id,
                        str(meta.get("title") or skill_id),
                        str(meta.get("kind") or "procedure"),
                        str(meta.get("status") or "candidate"),
                        body.strip(),
                        json.dumps(tags, ensure_ascii=False),
                        timestamp,
                        timestamp,
                        meta.get("source_session"),
                        meta.get("source_turn"),
                        meta.get("model"),
                    ),
                )

            counts["skills"] += 1

    # ==================================================
    # Summary
    # ==================================================

    def _import_summaries(self, counts: dict[str, int]) -> None:

        folder = self.base / "summaries"

        if not folder.is_dir():
            return

        for path in sorted(folder.glob("*.md")):

            text = path.read_text(encoding="utf-8", errors="ignore")
            meta, body = _split_frontmatter(text)
            session = str(meta.get("session") or "")

            if not session:
                counts["skipped"] += 1
                continue

            with self.database.connection() as connection:

                exists = connection.execute(
                    "SELECT 1 FROM summaries "
                    "WHERE session_id = ? AND created_at = ? "
                    "AND body = ?",
                    (
                        session,
                        str(meta.get("created_at") or ""),
                        body.strip(),
                    ),
                ).fetchone() is not None

                if exists and not self.replace:
                    counts["skipped"] += 1
                    continue

                connection.execute(
                    """
                    INSERT INTO summaries(
                        session_id, project, body, created_at,
                        transcript_sha256, archived_transcripts
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session,
                        meta.get("project"),
                        body.strip(),
                        str(meta.get("created_at") or ""),
                        meta.get("transcript_sha256"),
                        json.dumps(
                            meta.get("archived_transcripts") or [],
                            ensure_ascii=False,
                        ),
                    ),
                )

            counts["summaries"] += 1

    # ==================================================
    # Progetti
    # ==================================================

    def _import_projects(self, counts: dict[str, int]) -> None:

        folder = self.base / "projects"

        if not folder.is_dir():
            return

        for index in sorted(folder.glob("*/index.md")):

            text = index.read_text(encoding="utf-8", errors="ignore")
            meta, _ = _split_frontmatter(text)
            project_id = str(meta.get("id") or index.parent.name)

            with self.database.connection() as connection:

                exists = connection.execute(
                    "SELECT 1 FROM projects WHERE id = ?",
                    (project_id,),
                ).fetchone() is not None

                if exists and not self.replace:
                    counts["skipped"] += 1
                else:
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO projects(
                            id, title, status, created_at,
                            last_activity, summary
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            project_id,
                            str(meta.get("title") or project_id),
                            str(meta.get("status") or "active"),
                            str(meta.get("created_at") or ""),
                            str(meta.get("last_activity") or ""),
                            str(meta.get("summary") or ""),
                        ),
                    )
                    counts["projects"] += 1

            decisions = index.parent / "decisions"

            if not decisions.is_dir():
                continue

            for path in sorted(decisions.glob("*.md")):

                text = path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
                meta, body = _split_frontmatter(text)
                decision_id = str(meta.get("id") or path.stem)

                with self.database.connection() as connection:

                    exists = connection.execute(
                        "SELECT 1 FROM decisions WHERE id = ?",
                        (decision_id,),
                    ).fetchone() is not None

                    if exists and not self.replace:
                        counts["skipped"] += 1
                        continue

                    alternatives = meta.get("alternatives") or []
                    if not isinstance(alternatives, list):
                        alternatives = []

                    connection.execute(
                        """
                        INSERT OR REPLACE INTO decisions(
                            id, project_id, title, decision,
                            alternatives, rationale, status,
                            created_at, reviewed_at, auto_saved,
                            source_session, source_turn
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            decision_id,
                            project_id,
                            str(meta.get("title") or decision_id),
                            body.strip(),
                            json.dumps(
                                alternatives,
                                ensure_ascii=False,
                            ),
                            str(meta.get("rationale") or ""),
                            str(meta.get("status") or "candidate"),
                            str(meta.get("created_at") or ""),
                            meta.get("reviewed_at"),
                            int(bool(meta.get("auto_saved"))),
                            meta.get("source_session"),
                            meta.get("source_turn"),
                        ),
                    )

                counts["decisions"] += 1
