"""Indice SQLite derivato dal Vault Markdown.

Il Markdown resta la fonte di verità: questo indice può essere cancellato
e ricostruito in qualsiasi momento.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3

from contextlib import contextmanager
from pathlib import Path
from typing import Any

from memory.vault import Vault


SCHEMA_VERSION = 1


class MemoryIndexError(RuntimeError):
    pass


def default_index_path(vault: Vault) -> Path:
    """Percorso locale, fuori dal Vault sincronizzato."""

    override = os.environ.get("HAGAR_INDEX_DIR")

    if override:
        base = Path(override)
    elif os.name == "nt":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or Path.home() / "AppData" / "Local"
        )
    else:
        base = Path(
            os.environ.get("XDG_STATE_HOME")
            or Path.home() / ".local" / "state"
        )

    digest = hashlib.sha256(
        str(vault.root.resolve()).encode("utf-8")
    ).hexdigest()[:16]

    return base / "Hagar" / "index" / f"{digest}.db"


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):

        return {}, text

    lines = text.splitlines()
    end = None

    for index, line in enumerate(lines[1:], start=1):

        if line.strip() == "---":
            end = index
            break

    if end is None:
        return {}, text

    data: dict[str, str] = {}

    for line in lines[1:end]:

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            data[key] = value

    return data, "\n".join(lines[end + 1:]).strip()


def _title(meta: dict[str, str], body: str, fallback: str) -> str:
    title = meta.get("title", "").strip()

    if title:
        return title

    for line in body.splitlines():

        if line.startswith("# "):
            return line[2:].strip()

    return fallback


def _classify(relative: Path) -> tuple[str, str | None]:
    parts = relative.parts
    project = None

    if "projects" in parts:

        position = parts.index("projects")

        if position + 1 < len(parts):
            project = parts[position + 1]

        kind = (
            "decision"
            if "decisions" in parts
            else "project"
        )

        return kind, project

    if "skills" in parts:
        return "skill", None

    if "archive" in parts:
        return "archive", None

    if "summaries" in parts:
        return "summary", None

    if "chat" in parts:
        return "chat", None

    return "note", None


class MemoryIndex:
    """Indice FTS5 ricostruibile delle memorie Markdown."""

    def __init__(
        self,
        vault: Vault,
        subdir: str = "Hagar",
        path: Path | None = None,
    ) -> None:

        self.vault = vault
        self.subdir = Path(subdir)
        self.path = Path(
            path or default_index_path(vault)
        )
        self.fts = False

    # ==================================================
    # Connessione
    # ==================================================

    def _connect(self) -> sqlite3.Connection:

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
            raise MemoryIndexError(
                f"cannot open memory index: {exc}"
            ) from exc

        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self):
        """Connessione con commit/rollback e chiusura garantita."""

        connection = self._connect()

        try:
            yield connection
            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def ensure(self) -> None:

        with self._connection() as connection:

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    path TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    project TEXT,
                    status TEXT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS documents_kind "
                "ON documents(kind)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS documents_project "
                "ON documents(project)"
            )

            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                    USING fts5(
                        path UNINDEXED,
                        title,
                        content,
                        tokenize = 'unicode61'
                    )
                    """
                )
                self.fts = True

            except sqlite3.OperationalError:
                self.fts = False

            connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) "
                "VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    # ==================================================
    # Sync
    # ==================================================

    def _documents(self) -> list[Path]:

        if not self.vault.root.is_dir():
            return []

        root = self.vault.root.resolve()

        try:
            base = (root / self.subdir).resolve()
        except OSError:
            return []

        documents: list[Path] = []

        for candidate in root.rglob("*.md"):

            if not candidate.is_file():
                continue

            try:
                relative = candidate.resolve().relative_to(root)
            except (OSError, ValueError):
                continue

            if not relative.parts:
                continue

            if base != root:

                base_parts = base.relative_to(root).parts

                if relative.parts[:len(base_parts)] != base_parts:
                    continue

            documents.append(relative)

        return sorted(documents)

    def _parse(
        self,
        relative: Path,
        text: str,
    ) -> dict[str, Any]:

        meta, body = _frontmatter(text)
        kind, project = _classify(relative)

        return {
            "path": relative.as_posix(),
            "kind": kind,
            "project": meta.get("project") or project,
            "status": meta.get("status") or None,
            "title": _title(
                meta,
                body,
                relative.stem,
            ),
            "content": body,
        }

    def sync(self) -> int:
        """Indicizza file nuovi o modificati; rimuove i mancanti."""

        self.ensure()
        root = self.vault.root.resolve()
        documents = self._documents()
        changed = 0

        with self._connection() as connection:

            existing = {
                row["path"]: row
                for row in connection.execute(
                    "SELECT path, hash, mtime, size FROM documents"
                )
            }

            seen: set[str] = set()

            for relative in documents:

                path = relative.as_posix()
                seen.add(path)

                try:
                    text = (root / relative).read_text(
                        encoding="utf-8",
                        errors="ignore",
                    )
                    stat = (root / relative).stat()

                except OSError:
                    continue

                digest = hashlib.sha256(
                    text.encode("utf-8")
                ).hexdigest()
                previous = existing.get(path)

                if (
                    previous is not None
                    and previous["hash"] == digest
                    and previous["mtime"] == stat.st_mtime
                    and previous["size"] == stat.st_size
                ):
                    continue

                document = self._parse(relative, text)

                connection.execute(
                    """
                    INSERT INTO documents(
                        path, kind, project, status, title,
                        content, hash, mtime, size
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        kind=excluded.kind,
                        project=excluded.project,
                        status=excluded.status,
                        title=excluded.title,
                        content=excluded.content,
                        hash=excluded.hash,
                        mtime=excluded.mtime,
                        size=excluded.size
                    """,
                    (
                        document["path"],
                        document["kind"],
                        document["project"],
                        document["status"],
                        document["title"],
                        document["content"],
                        digest,
                        stat.st_mtime,
                        stat.st_size,
                    ),
                )

                if self.fts:
                    connection.execute(
                        "DELETE FROM documents_fts WHERE path = ?",
                        (path,),
                    )
                    connection.execute(
                        "INSERT INTO documents_fts(path, title, content) "
                        "VALUES (?, ?, ?)",
                        (
                            path,
                            document["title"],
                            document["content"],
                        ),
                    )

                changed += 1

            for path in set(existing) - seen:

                connection.execute(
                    "DELETE FROM documents WHERE path = ?",
                    (path,),
                )

                if self.fts:
                    connection.execute(
                        "DELETE FROM documents_fts WHERE path = ?",
                        (path,),
                    )

                changed += 1

        return changed

    def rebuild(self) -> int:
        """Svuota l'indice e lo ricostruisce dal Vault."""

        self.ensure()

        with self._connection() as connection:

            connection.execute("DELETE FROM documents")

            if self.fts:
                connection.execute(
                    "DELETE FROM documents_fts"
                )

        return self.sync()

    # ==================================================
    # Ricerca
    # ==================================================

    def _filters(
        self,
        project: str | None,
        kind: str | None,
        status: str | None,
    ) -> tuple[str, list[Any]]:

        clauses = []
        values: list[Any] = []

        if project:

            clauses.append("d.project = ?")
            values.append(project)

        if kind:

            clauses.append("d.kind = ?")
            values.append(kind)

        if status:

            clauses.append("d.status = ?")
            values.append(status)

        return (
            (" AND " + " AND ".join(clauses))
            if clauses
            else "",
            values,
        )

    def search(
        self,
        query: str,
        project: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:

        query = query.strip()

        if not query:
            return []

        self.sync()

        limit = max(1, min(int(limit), 100))
        filters, values = self._filters(
            project,
            kind,
            status,
        )

        words = re.findall(
            r"\w+",
            query,
            flags=re.UNICODE,
        )

        with self._connection() as connection:

            if self.fts and words:

                fts_query = " OR ".join(
                    '"' + word.replace('"', '""') + '"'
                    for word in words
                )

                try:
                    rows = connection.execute(
                        """
                        SELECT d.path, d.kind, d.project, d.status,
                               d.title,
                               snippet(documents_fts, 2, '[', ']', '…', 20)
                                   AS snippet
                        FROM documents_fts
                        JOIN documents d ON d.path = documents_fts.path
                        WHERE documents_fts MATCH ?
                        """
                        + filters
                        + """
                        ORDER BY bm25(documents_fts)
                        LIMIT ?
                        """,
                        [fts_query, *values, limit],
                    ).fetchall()

                except sqlite3.OperationalError:
                    rows = []

            else:
                rows = []

            if not rows:

                like = f"%{query}%"
                rows = connection.execute(
                    """
                    SELECT d.path, d.kind, d.project, d.status,
                           d.title,
                           substr(d.content, 1, 240) AS snippet
                    FROM documents d
                    WHERE (d.title LIKE ? OR d.content LIKE ?)
                    """
                    + filters
                    + """
                    ORDER BY d.title
                    LIMIT ?
                    """,
                    [like, like, *values, limit],
                ).fetchall()

        return [
            {
                "path": row["path"],
                "kind": row["kind"],
                "project": row["project"],
                "status": row["status"],
                "title": row["title"],
                "snippet": row["snippet"],
            }
            for row in rows
        ]

    def stats(self) -> dict[str, Any]:

        self.sync()

        with self._connection() as connection:

            total = connection.execute(
                "SELECT COUNT(*) FROM documents"
            ).fetchone()[0]
            kinds = {
                row["kind"]: row["count"]
                for row in connection.execute(
                    "SELECT kind, COUNT(*) AS count "
                    "FROM documents GROUP BY kind"
                )
            }

        return {
            "path": str(self.path),
            "documents": total,
            "kinds": kinds,
            "fts": self.fts,
        }
