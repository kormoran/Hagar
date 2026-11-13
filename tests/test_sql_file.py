"""Test del tool SQL locale in sola lettura."""

from __future__ import annotations

import json
import sqlite3

from pathlib import Path

import pytest

from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.permissions import (
    Capability,
    Effect,
    PermissionDenied,
    PermissionEvaluator,
    Subject,
)
from core.tool_registry import ToolRegistry

import local_tools.sql_file as sql_file

from local_tools.sql_file import SqlDriverError
from local_tools.sql_file_tool import SqlFileToolProvider


def create_database(path: Path) -> None:

    connection = sqlite3.connect(path)

    connection.executescript(
        """
        CREATE TABLE authors (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE books (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            author_id INTEGER NOT NULL
                REFERENCES authors(id)
        );

        CREATE INDEX books_author
            ON books(author_id);

        INSERT INTO authors(name)
            VALUES ('Ada Lovelace');

        INSERT INTO authors(name)
            VALUES ('Alan Turing');

        INSERT INTO books(title, author_id)
            VALUES ('Notes', 1);

        INSERT INTO books(title, author_id)
            VALUES ('Computing Machinery', 2);

        CREATE VIEW book_titles AS
            SELECT title FROM books;
        """
    )

    connection.close()


def make_registry(
    sandbox: FileSystemSandbox,
    forbidden: list[Path] | None = None,
) -> ToolRegistry:

    registry = ToolRegistry()

    SqlFileToolProvider(
        sandbox,
        forbidden_paths=forbidden or [],
    ).register_tools(registry)

    return registry


def run(
    registry: ToolRegistry,
    name: str,
    **arguments,
) -> dict:

    return json.loads(
        registry.execute(name, **arguments)
    )


def test_sql_tools_are_registered(
    sandbox: FileSystemSandbox,
):

    registry = make_registry(sandbox)

    assert registry.tool_names() == [
        "sql.file.drivers",
        "sql.file.query",
        "sql.file.schema",
    ]

    drivers = registry.get("sql.file.drivers")
    assert drivers.capabilities == Capability.DATABASE_READ
    assert drivers.origin == "local"
    assert drivers.category == "sql"

    for name in (
        "sql.file.query",
        "sql.file.schema",
    ):

        tool = registry.get(name)
        assert tool.capabilities == (
            Capability.FILESYSTEM_READ
            | Capability.DATABASE_READ
        )
        assert tool.origin == "local"
        assert tool.category == "sql"


def test_sqlite_schema_lists_tables(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    payload = run(
        make_registry(sandbox),
        "sql.file.schema",
        path="app.db",
    )

    assert payload["success"] is True
    assert payload["adapter"] == "sqlite"
    assert payload["path"] == (
        "/home/ai/root/app.db"
    )

    tables = {
        item["name"]: item["type"]
        for item in payload["tables"]
    }

    assert tables == {
        "authors": "table",
        "books": "table",
        "book_titles": "view",
    }
    assert payload["truncated"] is False


def test_sqlite_schema_inspects_table(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    payload = run(
        make_registry(sandbox),
        "sql.file.schema",
        path="app.db",
        table="books",
    )

    assert payload["success"] is True
    assert payload["found"] is True

    columns = {
        item["name"]: item
        for item in payload["columns"]
    }

    assert columns["id"]["primary_key"] is True
    assert columns["title"]["not_null"] is True
    assert payload["primary_key"] == ["id"]

    assert payload["foreign_keys"] == [
        {
            "from": "author_id",
            "to_table": "authors",
            "to_column": "id",
            "on_update": "NO ACTION",
            "on_delete": "NO ACTION",
            "match": "NONE",
        }
    ]

    assert payload["indexes"] == [
        {
            "name": "books_author",
            "unique": False,
            "origin": "c",
            "partial": False,
            "columns": ["author_id"],
        }
    ]


def test_sqlite_schema_missing_table(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    payload = run(
        make_registry(sandbox),
        "sql.file.schema",
        path="app.db",
        table="missing",
    )

    assert payload["success"] is False
    assert "not found" in payload["error"]


def test_sqlite_query_returns_rows(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    raw = make_registry(sandbox).execute(
        "sql.file.query",
        path="app.db",
        sql=(
            "SELECT id, title FROM books "
            "ORDER BY id"
        ),
    )

    payload = json.loads(raw)

    assert payload["success"] is True
    assert payload["adapter"] == "sqlite"
    assert payload["read_only"] is True
    assert payload["row_count"] == 2
    assert payload["rows"] == [
        [1, "Notes"],
        [2, "Computing Machinery"],
    ]
    assert payload["columns"][0]["name"] == "id"
    assert payload["truncated"] is False
    assert str(workspace) not in raw


def test_sqlite_query_limits_rows(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="app.db",
        sql="SELECT * FROM books",
        max_rows=1,
    )

    assert payload["success"] is True
    assert payload["row_count"] == 1
    assert payload["truncated"] is True


def test_sqlite_query_rejects_writes_and_pragmas(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    registry = make_registry(sandbox)

    statements = [
        "DELETE FROM books",
        "UPDATE books SET title = 'x'",
        "INSERT INTO books(title, author_id) "
        "VALUES ('x', 1)",
        "CREATE TABLE x (id INTEGER)",
        "DROP TABLE books",
        "PRAGMA table_info(books)",
        "ATTACH DATABASE 'other.db' AS other",
        "WITH x AS (DELETE FROM books "
        "RETURNING *) SELECT * FROM x",
        "EXPLAIN ANALYZE SELECT * FROM books",
    ]

    for statement in statements:

        payload = run(
            registry,
            "sql.file.query",
            path="app.db",
            sql=statement,
        )

        assert payload["success"] is False, statement
        assert "error" in payload


def test_sqlite_query_rejects_multiple_statements(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="app.db",
        sql="SELECT 1; SELECT 2",
    )

    assert payload["success"] is False
    assert "one SQL statement" in payload["error"]


def test_sqlite_query_allows_semicolon_in_string(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="app.db",
        sql="SELECT ';' AS value",
    )

    assert payload["success"] is True
    assert payload["rows"] == [[";"]]


def test_sqlite_query_allows_cte_and_explain(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    registry = make_registry(sandbox)

    cte = run(
        registry,
        "sql.file.query",
        path="app.db",
        sql=(
            "WITH x AS (SELECT * FROM books) "
            "SELECT count(*) FROM x"
        ),
    )

    assert cte["success"] is True
    assert cte["rows"] == [[2]]

    plan = run(
        registry,
        "sql.file.query",
        path="app.db",
        sql="EXPLAIN QUERY PLAN SELECT * FROM books",
    )

    assert plan["success"] is True


def test_sqlite_query_blocks_extension_functions(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="app.db",
        sql="SELECT load_extension('evil')",
    )

    assert payload["success"] is False


def test_sqlite_memory_database_is_forbidden(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "memory.db")

    memory = workspace / "memory.db"

    registry = make_registry(
        sandbox,
        forbidden=[memory],
    )

    for path in (
        "memory.db",
        "memory.db-wal",
        "memory.db-shm",
    ):

        (workspace / path).touch(exist_ok=True)

        payload = run(
            registry,
            "sql.file.query",
            path=path,
            sql="SELECT * FROM authors",
        )

        assert payload["success"] is False
        assert "memory database" in payload["error"]


def test_sqlite_path_outside_sandbox_is_rejected(
    sandbox: FileSystemSandbox,
):

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="../outside.db",
        sql="SELECT 1",
    )

    assert payload["success"] is False
    assert "outside" in payload["error"].lower()


def test_sqlite_directory_is_rejected(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "folder").mkdir()

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="folder",
        sql="SELECT 1",
    )

    assert payload["success"] is False
    assert "not a file" in payload["error"]


def test_sqlite_missing_file_is_reported(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    raw = make_registry(sandbox).execute(
        "sql.file.query",
        path="missing.db",
        sql="SELECT 1",
    )

    payload = json.loads(raw)

    assert payload["success"] is False
    assert "not a file" in payload["error"]
    assert str(workspace) not in raw


def test_sqlite_query_timeout(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="app.db",
        sql=(
            "WITH RECURSIVE c(x) AS ("
            "VALUES(1) UNION ALL "
            "SELECT x + 1 FROM c "
            "WHERE x < 50000000"
            ") SELECT count(*) FROM c"
        ),
        timeout_seconds=1,
    )

    assert payload["success"] is False
    assert "timed out" in payload["error"]


class FakeCursor:
    def __init__(self):

        self.description = []
        self._rows = []
        self.sql = None

    def execute(self, sql):

        self.sql = sql
        self.description = [
            ("id", int),
            ("name", str),
        ]
        self._rows = [
            (1, "Ada"),
            (2, "Alan"),
        ]

    def fetchmany(self, amount):

        return self._rows[:amount]

    def tables(self, **kwargs):

        self.description = [
            ("table_cat", str),
            ("table_schem", str),
            ("table_name", str),
            ("table_type", str),
        ]
        self._rows = [
            (None, None, "people", "TABLE"),
            (None, None, "adults", "VIEW"),
            (None, None, "sys", "SYSTEM TABLE"),
        ]
        return self

    def columns(self, **kwargs):

        self.description = [
            ("table_name", str),
            ("column_name", str),
            ("type_name", str),
            ("nullable", int),
        ]
        self._rows = [
            ("people", "id", "INTEGER", 0),
            ("people", "name", "TEXT", 1),
        ]
        return self

    def primaryKeys(self, **kwargs):

        self.description = [
            ("table_name", str),
            ("column_name", str),
            ("key_seq", int),
        ]
        self._rows = [
            ("people", "id", 1),
        ]
        return self

    def foreignKeys(self, **kwargs):

        self.description = [
            ("fk_table_name", str),
            ("fk_column_name", str),
        ]
        self._rows = []
        return self

    def close(self):

        return None


class FakeConnection:
    def __init__(self, connection_string, kwargs):

        self.connection_string = connection_string
        self.kwargs = kwargs
        self.timeout = None
        self.rolled_back = False
        self.closed = False
        self.cursor_object = FakeCursor()

    def cursor(self):

        return self.cursor_object

    def rollback(self):

        self.rolled_back = True

    def close(self):

        self.closed = True


class FakePyodbc:
    def __init__(self, drivers):

        self._drivers = drivers
        self.connections = []

    def drivers(self):

        return list(self._drivers)

    def connect(self, connection_string, **kwargs):

        connection = FakeConnection(
            connection_string,
            kwargs,
        )
        self.connections.append(connection)
        return connection


def test_drivers_reports_missing_pyodbc(
    monkeypatch,
    sandbox: FileSystemSandbox,
):

    def missing():

        raise SqlDriverError(
            "ODBC support requires pyodbc"
        )

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        missing,
    )

    payload = run(
        make_registry(sandbox),
        "sql.file.drivers",
    )

    assert payload["success"] is True
    assert payload["odbc_available"] is False
    assert "pyodbc" in payload["error"]


def test_odbc_reports_installed_drivers(
    monkeypatch,
    sandbox: FileSystemSandbox,
):

    fake = FakePyodbc(
        ["Fake ODBC Driver"]
    )

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    payload = run(
        make_registry(sandbox),
        "sql.file.drivers",
    )

    assert payload["odbc_available"] is True
    assert payload["odbc_drivers"] == [
        "Fake ODBC Driver"
    ]
    assert (
        payload["aliases"]["access"]["available"]
        is False
    )


def test_odbc_missing_driver_returns_error(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(
        b"not a real database"
    )

    fake = FakePyodbc(
        ["Fake ODBC Driver"]
    )

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="notes.accdb",
        driver="access",
        sql="SELECT 1",
    )

    assert payload["success"] is False
    assert "not installed" in payload["error"]
    assert "Fake ODBC Driver" in payload["error"]
    assert fake.connections == []


def test_odbc_query_uses_read_only_connection(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(
        b"not a real database"
    )

    fake = FakePyodbc(
        ["Fake ODBC Driver"]
    )

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="notes.accdb",
        driver="Fake ODBC Driver",
        sql="SELECT * FROM people",
    )

    assert payload["success"] is True
    assert payload["adapter"] == "odbc"
    assert payload["driver"] == "Fake ODBC Driver"
    assert payload["rows"] == [
        [1, "Ada"],
        [2, "Alan"],
    ]

    connection = fake.connections[0]

    assert connection.kwargs["readonly"] is True
    assert connection.kwargs["autocommit"] is False
    assert "DBQ=" in connection.connection_string
    assert "notes.accdb" in (
        connection.connection_string
    )
    assert connection.rolled_back is True
    assert connection.closed is True


def test_odbc_query_validation_happens_before_connect(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(
        b"not a real database"
    )

    fake = FakePyodbc(
        ["Fake ODBC Driver"]
    )

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    payload = run(
        make_registry(sandbox),
        "sql.file.query",
        path="notes.accdb",
        driver="Fake ODBC Driver",
        sql="DELETE FROM people",
    )

    assert payload["success"] is False
    assert fake.connections == []


def test_odbc_schema_uses_catalog_functions(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(
        b"not a real database"
    )

    fake = FakePyodbc(
        ["Fake ODBC Driver"]
    )

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    registry = make_registry(sandbox)

    tables = run(
        registry,
        "sql.file.schema",
        path="notes.accdb",
        driver="Fake ODBC Driver",
    )

    assert tables["success"] is True
    assert tables["count"] == 2
    assert [
        item["name"]
        for item in tables["tables"]
    ] == ["people", "adults"]

    columns = run(
        registry,
        "sql.file.schema",
        path="notes.accdb",
        driver="Fake ODBC Driver",
        table="people",
    )

    assert columns["success"] is True
    assert columns["found"] is True
    assert columns["columns"][0]["column_name"] == "id"
    assert columns["primary_key"][0]["column_name"] == "id"


def test_sql_query_requires_database_read(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_database(workspace / "app.db")

    evaluator = PermissionEvaluator(
        ceiling=Capability.FILESYSTEM_READ,
    )
    subject = Subject(
        name="assistant",
        default=Effect.ALLOW,
    )
    registry = ToolRegistry(
        evaluator=evaluator,
        subject=subject,
    )

    SqlFileToolProvider(sandbox).register_tools(
        registry
    )

    with pytest.raises(
        PermissionDenied,
        match="DATABASE_READ",
    ):
        registry.execute(
            "sql.file.query",
            path="app.db",
            sql="SELECT 1",
        )
