"""Connessione e schema del database delle memorie Hagar."""

from __future__ import annotations

import os
import sqlite3

from contextlib import contextmanager
from pathlib import Path

from memory.store import MemoryError


SCHEMA_VERSION = 2


def default_memory_path() -> Path:
    """Database locale, fuori da qualsiasi Vault sincronizzato."""

    override = os.environ.get("HAGAR_MEMORY_DB")

    if override:
        return Path(override)

    if os.name == "nt":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or Path.home() / "AppData" / "Local"
        )
    else:
        base = Path(
            os.environ.get("XDG_STATE_HOME")
            or Path.home() / ".local" / "state"
        )

    return base / "Hagar" / "memory.db"


class MemoryDatabase:
    """Connessione SQLite con WAL, transazioni e migrazioni."""

    def __init__(
        self,
        path: str | Path | None = None,
    ) -> None:

        self.path = Path(path or default_memory_path())
        self.fts = False

    def connect(self) -> sqlite3.Connection:

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            connection = sqlite3.connect(
                str(self.path),
                timeout=10,
            )

        except sqlite3.Error as exc:
            raise MemoryError(
                f"cannot open memory database: {exc}"
            ) from exc

        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def connection(self):

        connection = self.connect()

        try:
            yield connection
            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def ensure(self) -> None:

        with self.connection() as connection:

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            row = connection.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()

            current = 0

            if row is not None:

                current = int(row["value"])

                if current > SCHEMA_VERSION:

                    raise MemoryError(
                        "memory database schema is newer "
                        f"({current} > {SCHEMA_VERSION})"
                    )

            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS turns (
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    PRIMARY KEY (session_id, turn_id),
                    FOREIGN KEY (session_id)
                        REFERENCES sessions(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS turns_session_time
                    ON turns(session_id, timestamp);

                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_session TEXT,
                    source_turn TEXT,
                    model TEXT
                );

                CREATE INDEX IF NOT EXISTS skills_status
                    ON skills(status, created_at);

                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    project TEXT,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    transcript_sha256 TEXT,
                    archived_transcripts TEXT NOT NULL DEFAULT '[]'
                );

                CREATE INDEX IF NOT EXISTS summaries_time
                    ON summaries(created_at);

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_activity TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    alternatives TEXT NOT NULL DEFAULT '[]',
                    rationale TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    auto_saved INTEGER NOT NULL DEFAULT 0,
                    source_session TEXT,
                    source_turn TEXT,
                    FOREIGN KEY (project_id)
                        REFERENCES projects(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS decisions_project_status
                    ON decisions(project_id, status, created_at);
                """
            )
            self._ensure_fts(connection)

            if current < SCHEMA_VERSION:
                self.rebuild_fts(connection)

            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) "
                "VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def _ensure_fts(self, connection) -> bool:

        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(
                    entity UNINDEXED,
                    entity_id UNINDEXED,
                    kind UNINDEXED,
                    project UNINDEXED,
                    status UNINDEXED,
                    title,
                    body,
                    tokenize = 'unicode61'
                )
                """
            )
            self.fts = True

        except sqlite3.OperationalError:
            self.fts = False

        return self.fts

    def fts_delete(
        self,
        connection,
        entity: str,
        entity_id: str,
    ) -> None:

        if not self.fts:
            return

        connection.execute(
            "DELETE FROM memory_fts "
            "WHERE entity = ? AND entity_id = ?",
            (entity, entity_id),
        )

    def fts_upsert(
        self,
        connection,
        *,
        entity: str,
        entity_id: str,
        kind: str,
        project: str | None,
        status: str | None,
        title: str,
        body: str,
    ) -> None:

        if not self.fts:
            return

        self.fts_delete(connection, entity, entity_id)
        connection.execute(
            """
            INSERT INTO memory_fts(
                entity, entity_id, kind, project, status, title, body
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity,
                entity_id,
                kind,
                project,
                status,
                title or "",
                body or "",
            ),
        )

    def rebuild_fts(self, connection=None) -> int:

        if connection is None:

            with self.connection() as own:
                return self.rebuild_fts(own)

        if not self.fts:
            return 0

        connection.execute("DELETE FROM memory_fts")

        script = (
            """
            INSERT INTO memory_fts(
                entity, entity_id, kind, project, status, title, body
            )
            SELECT 'turn', turn_id, 'chat', NULL, NULL,
                   question, answer
            FROM turns;

            INSERT INTO memory_fts(
                entity, entity_id, kind, project, status, title, body
            )
            SELECT 'skill', id, kind, NULL, status, title, content
            FROM skills;

            INSERT INTO memory_fts(
                entity, entity_id, kind, project, status, title, body
            )
            SELECT 'summary', CAST(id AS TEXT), 'summary', project,
                   NULL, 'Summary ' || session_id, body
            FROM summaries;

            INSERT INTO memory_fts(
                entity, entity_id, kind, project, status, title, body
            )
            SELECT 'project', id, 'project', id, status, title, summary
            FROM projects;

            INSERT INTO memory_fts(
                entity, entity_id, kind, project, status, title, body
            )
            SELECT 'decision', id, 'decision', project_id, status,
                   title, decision || '\n' || rationale
            FROM decisions;
            """
        )
        connection.executescript(script)

        return connection.execute(
            "SELECT COUNT(*) FROM memory_fts"
        ).fetchone()[0]

    def backup(self, target: str | Path) -> Path:
        """Backup consistente con VACUUM INTO."""

        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self.connection() as connection:
            connection.execute(
                "VACUUM INTO ?",
                (str(destination),),
            )

        return destination
