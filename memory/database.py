"""Connessione e schema del database delle memorie Hagar."""

from __future__ import annotations

import os
import sqlite3

from contextlib import contextmanager
from pathlib import Path

from memory.store import MemoryError


SCHEMA_VERSION = 1


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
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) "
                "VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

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
