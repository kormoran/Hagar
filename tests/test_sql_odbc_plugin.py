"""Test del plugin SQL ODBC, incluso il percorso di scrittura."""

from __future__ import annotations

import json
import sqlite3
import tomllib

from pathlib import Path

import pytest

import core.plugins as plugins

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
from core.plugins import (
    PluginContext,
    load_tool_plugins,
)
from core.tool_registry import ToolRegistry

import local_tools.sql_file as sql_file

from hagar_sql_odbc import PLUGIN, VERSION
from hagar_sql_odbc.tools import SqlOdbcToolProvider

from local_tools.sql_file import (
    SqlFileReader,
)


class Audit:
    def __init__(self):

        self.events = []

    def record(self, event, **fields):

        self.events.append((event, fields))


def run(
    registry: ToolRegistry,
    name: str,
    **arguments,
) -> dict:

    return json.loads(
        registry.execute(name, **arguments)
    )


def create_sqlite(path: Path) -> None:

    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        INSERT INTO people(name) VALUES ('Ada');
        """
    )
    connection.close()


def read_only_sandbox(
    workspace: Path,
) -> FileSystemSandbox:

    return FileSystemSandbox(
        roots={
            workspace: DirectoryPermissions(
                read=True,
                write=False,
                create=False,
                rename=False,
                delete=False,
                execute=True,
            )
        },
        current_directory=workspace,
        aliases={"root": workspace},
    )


class FakeCursor:
    def __init__(self):

        self.description = []
        self._rows = []
        self.rowcount = -1
        self.sql = None

    def execute(self, sql):

        self.sql = sql
        self.rowcount = 1
        self.description = []
        self._rows = []

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
            (None, None, "people_view", "VIEW"),
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
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.cursor_object = FakeCursor()

    def cursor(self):

        return self.cursor_object

    def commit(self):

        self.committed = True

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


def test_plugin_metadata():

    assert PLUGIN.name == "sql-odbc"
    assert PLUGIN.version == VERSION
    assert PLUGIN.builtin is False


def test_pyproject_declares_entry_point():

    root = Path(__file__).resolve().parents[1]
    path = root / "plugins" / "sql_odbc" / "pyproject.toml"
    data = tomllib.loads(
        path.read_text(encoding="utf-8")
    )

    assert (
        data["project"]["entry-points"]["hagar.tools"][
            "sql-odbc"
        ]
        == "hagar_sql_odbc:PLUGIN"
    )


def test_plugin_registers_tools(
    sandbox: FileSystemSandbox,
):

    registry = ToolRegistry()

    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    assert registry.tool_names() == [
        "sql.odbc.drivers",
        "sql.odbc.execute",
        "sql.odbc.query",
        "sql.odbc.schema",
    ]

    assert registry.get(
        "sql.odbc.drivers"
    ).capabilities == Capability.DATABASE_READ

    for name in (
        "sql.odbc.schema",
        "sql.odbc.query",
    ):

        assert registry.get(name).capabilities == (
            Capability.FILESYSTEM_READ
            | Capability.DATABASE_READ
        )

    execute = registry.get("sql.odbc.execute")

    assert execute.capabilities == (
        Capability.FILESYSTEM_READ
        | Capability.FILESYSTEM_WRITE
        | Capability.DATABASE_READ
        | Capability.DATABASE_WRITE
    )
    assert execute.requires_confirmation is True
    assert execute.origin == "plugin.sql_odbc"


def test_entry_point_discovery(
    monkeypatch,
    sandbox: FileSystemSandbox,
):

    class Entry:
        name = "sql-odbc"

        def load(self):

            return PLUGIN

    monkeypatch.setattr(
        plugins,
        "_entry_points",
        lambda group: [Entry()]
        if group == plugins.TOOL_GROUP
        else [],
    )

    registry = ToolRegistry()
    audit = Audit()

    failures = load_tool_plugins(
        [],
        registry,
        PluginContext(filesystem=sandbox),
        audit=audit,
    )

    assert failures == []
    assert "sql.odbc.execute" in registry.tool_names()
    assert audit.events[0][0] == "plugin.loaded"
    assert audit.events[0][1]["plugin"] == "sql-odbc"


def test_odbc_only_rejects_native_sqlite(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_sqlite(workspace / "app.db")

    registry = ToolRegistry()
    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    payload = run(
        registry,
        "sql.odbc.query",
        path="app.db",
        sql="SELECT 1",
    )

    assert payload["success"] is False
    assert "ODBC" in payload["error"]


def test_missing_driver_returns_error(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(b"x")

    fake = FakePyodbc(["Fake ODBC Driver"])

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    registry = ToolRegistry()
    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    payload = run(
        registry,
        "sql.odbc.execute",
        path="notes.accdb",
        driver="access",
        sql="UPDATE people SET name = 'x'",
    )

    assert payload["success"] is False
    assert "not installed" in payload["error"]
    assert fake.connections == []


def test_execute_runs_dml_and_commits(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(b"x")

    fake = FakePyodbc(["Fake ODBC Driver"])

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    registry = ToolRegistry()
    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    payload = run(
        registry,
        "sql.odbc.execute",
        path="notes.accdb",
        driver="Fake ODBC Driver",
        sql="UPDATE people SET name = 'Grace'",
    )

    assert payload["success"] is True
    assert payload["committed"] is True
    assert payload["row_count"] == 1
    assert payload["adapter"] == "odbc"

    connection = fake.connections[0]

    assert connection.kwargs["readonly"] is False
    assert connection.kwargs["autocommit"] is False
    assert connection.committed is True
    assert connection.closed is True


def test_execute_rejects_non_dml(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(b"x")

    fake = FakePyodbc(["Fake ODBC Driver"])

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    registry = ToolRegistry()
    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    for sql in (
        "SELECT * FROM people",
        "CREATE TABLE x (id INTEGER)",
        "DROP TABLE people",
        "TRUNCATE TABLE people",
        "UPDATE people SET name = 'x'; DELETE FROM people",
        "ATTACH DATABASE 'x' AS x",
        "PRAGMA table_info(people)",
    ):

        payload = run(
            registry,
            "sql.odbc.execute",
            path="notes.accdb",
            driver="Fake ODBC Driver",
            sql=sql,
        )

        assert payload["success"] is False, sql

    assert fake.connections == []


def test_query_is_read_only(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(b"x")

    fake = FakePyodbc(["Fake ODBC Driver"])

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    registry = ToolRegistry()
    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    payload = run(
        registry,
        "sql.odbc.query",
        path="notes.accdb",
        driver="Fake ODBC Driver",
        sql="SELECT * FROM people",
    )

    assert payload["success"] is True
    assert payload["read_only"] is True

    connection = fake.connections[0]

    assert connection.kwargs["readonly"] is True
    assert connection.rolled_back is True
    assert connection.committed is False


def test_schema_uses_catalog(
    monkeypatch,
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(b"x")

    fake = FakePyodbc(["Fake ODBC Driver"])

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    registry = ToolRegistry()
    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    tables = run(
        registry,
        "sql.odbc.schema",
        path="notes.accdb",
        driver="Fake ODBC Driver",
    )

    assert tables["success"] is True
    assert tables["count"] == 2

    columns = run(
        registry,
        "sql.odbc.schema",
        path="notes.accdb",
        driver="Fake ODBC Driver",
        table="people",
    )

    assert columns["success"] is True
    assert columns["found"] is True
    assert columns["columns"][0]["column_name"] == "id"


def test_drivers_report_is_odbc_only(
    monkeypatch,
    sandbox: FileSystemSandbox,
):

    fake = FakePyodbc(["Fake ODBC Driver"])

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    registry = ToolRegistry()
    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    payload = run(
        registry,
        "sql.odbc.drivers",
    )

    assert payload["success"] is True
    assert payload["plugin"] == "sql-odbc"
    assert payload["native"] == []
    assert ".db" not in payload["extensions"]
    assert ".accdb" in payload["extensions"]


def test_execute_requires_sandbox_write(
    monkeypatch,
    workspace: Path,
):

    (workspace / "notes.accdb").write_bytes(b"x")

    fake = FakePyodbc(["Fake ODBC Driver"])

    monkeypatch.setattr(
        sql_file,
        "_load_odbc",
        lambda: fake,
    )

    registry = ToolRegistry()
    PLUGIN.register(
        registry,
        PluginContext(
            filesystem=read_only_sandbox(workspace)
        ),
    )

    payload = run(
        registry,
        "sql.odbc.execute",
        path="notes.accdb",
        driver="Fake ODBC Driver",
        sql="UPDATE people SET name = 'x'",
    )

    assert payload["success"] is False
    assert "Write access denied" in payload["error"]
    assert fake.connections == []


def test_execute_requires_database_write(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    evaluator = PermissionEvaluator(
        ceiling=(
            Capability.FILESYSTEM_READ
            | Capability.FILESYSTEM_WRITE
            | Capability.DATABASE_READ
        ),
    )
    subject = Subject(
        name="assistant",
        default=Effect.ALLOW,
    )
    registry = ToolRegistry(
        evaluator=evaluator,
        subject=subject,
    )

    PLUGIN.register(
        registry,
        PluginContext(filesystem=sandbox),
    )

    with pytest.raises(
        PermissionDenied,
        match="DATABASE_WRITE",
    ):
        registry.execute(
            "sql.odbc.execute",
            path="notes.accdb",
            sql="UPDATE people SET name = 'x'",
        )


def test_memory_database_is_forbidden(
    sandbox: FileSystemSandbox,
    workspace: Path,
):

    create_sqlite(workspace / "memory.db")

    reader = SqlFileReader(
        sandbox,
        forbidden_paths=[
            workspace / "memory.db"
        ],
    )

    registry = ToolRegistry()
    SqlOdbcToolProvider(reader).register_tools(
        registry
    )

    payload = run(
        registry,
        "sql.odbc.execute",
        path="memory.db",
        driver="Fake ODBC Driver",
        sql="DELETE FROM people",
    )

    assert payload["success"] is False
    assert "memory database" in payload["error"]
