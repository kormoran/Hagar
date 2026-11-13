"""Tool SQL ODBC, inclusa la scrittura DML."""

from __future__ import annotations

import json

from typing import Any

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry

from local_tools.sql_file import (
    OdbcDatabase,
    SqlFileError,
    SqlFileReader,
)


def _json(
    payload: Any,
) -> str:

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def _error(
    exc: Exception,
) -> str:

    message = str(exc) or exc.__class__.__name__

    return _json(
        {
            "success": False,
            "error": message,
        }
    )


class SqlOdbcToolProvider:
    """Tool ODBC con lettura e DML esplicito."""

    def __init__(
        self,
        reader: SqlFileReader,
    ) -> None:

        self.reader = reader

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="sql.odbc.drivers",
                description=(
                    "List installed ODBC drivers and aliases "
                    "for local database files. Use it when a "
                    "driver is missing. This plugin uses ODBC "
                    "only; native SQLite is available through "
                    "the built-in sql.file tools."
                ),
                category="sql",
                capabilities=Capability.DATABASE_READ,
                origin="plugin.sql_odbc",
                timeout=15,
                parameters=[],
                handler=self.drivers,
            )
        )

        registry.register(
            ToolDefinition(
                name="sql.odbc.schema",
                description=(
                    "Inspect a local database file inside the "
                    "sandbox through ODBC. Without table, lists "
                    "tables and views; with table, returns "
                    "columns, primary key, foreign keys and "
                    "indexes. Read-only."
                ),
                category="sql",
                capabilities=(
                    Capability.FILESYSTEM_READ
                    | Capability.DATABASE_READ
                ),
                origin="plugin.sql_odbc",
                timeout=60,
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Database file path inside the "
                            "sandbox."
                        ),
                    ),
                    ToolParameter(
                        name="driver",
                        param_type="string",
                        description=(
                            "ODBC alias or exact driver name: "
                            "access, sqlite-odbc, firebird, "
                            "duckdb, dbase, or an installed "
                            "driver. Default: auto."
                        ),
                        required=False,
                        default="auto",
                    ),
                    ToolParameter(
                        name="table",
                        param_type="string",
                        description=(
                            "Table or view to inspect. "
                            "Omit to list tables."
                        ),
                        required=False,
                        default=None,
                    ),
                    ToolParameter(
                        name="schema",
                        param_type="string",
                        description=(
                            "Optional ODBC schema or catalog "
                            "name."
                        ),
                        required=False,
                        default=None,
                    ),
                    ToolParameter(
                        name="max_tables",
                        param_type="integer",
                        description=(
                            "Maximum tables to list "
                            "(1-500). Default: 200."
                        ),
                        required=False,
                        default=200,
                    ),
                    ToolParameter(
                        name="timeout_seconds",
                        param_type="integer",
                        description=(
                            "ODBC connection timeout in "
                            "seconds (1-120). Default: 30."
                        ),
                        required=False,
                        default=30,
                    ),
                ],
                handler=self.schema,
            )
        )

        registry.register(
            ToolDefinition(
                name="sql.odbc.query",
                description=(
                    "Run one read-only SELECT, WITH or EXPLAIN "
                    "statement through ODBC against a local "
                    "database file inside the sandbox. Multiple "
                    "statements and write statements are "
                    "rejected. Results are bounded by max_rows "
                    "and timeout_seconds."
                ),
                category="sql",
                capabilities=(
                    Capability.FILESYSTEM_READ
                    | Capability.DATABASE_READ
                ),
                origin="plugin.sql_odbc",
                timeout=120,
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Database file path inside the "
                            "sandbox."
                        ),
                    ),
                    ToolParameter(
                        name="sql",
                        param_type="string",
                        description=(
                            "One SELECT, WITH or EXPLAIN "
                            "statement."
                        ),
                    ),
                    ToolParameter(
                        name="driver",
                        param_type="string",
                        description=(
                            "ODBC alias or exact driver name: "
                            "access, sqlite-odbc, firebird, "
                            "duckdb, dbase, or an installed "
                            "driver. Default: auto."
                        ),
                        required=False,
                        default="auto",
                    ),
                    ToolParameter(
                        name="max_rows",
                        param_type="integer",
                        description=(
                            "Maximum rows to return "
                            "(1-1000). Default: 100."
                        ),
                        required=False,
                        default=100,
                    ),
                    ToolParameter(
                        name="timeout_seconds",
                        param_type="integer",
                        description=(
                            "Maximum query time in seconds "
                            "(1-120). Default: 30."
                        ),
                        required=False,
                        default=30,
                    ),
                ],
                handler=self.query,
            )
        )

        registry.register(
            ToolDefinition(
                name="sql.odbc.execute",
                description=(
                    "Execute one INSERT, UPDATE, DELETE, MERGE "
                    "or REPLACE statement through ODBC against "
                    "a local database file inside the sandbox. "
                    "Requires sandbox write permission, "
                    "DATABASE_WRITE and human confirmation. "
                    "DDL, SELECT, multiple statements, "
                    "ATTACH/PRAGMA and dangerous tokens are "
                    "rejected. The Hagar memory database is "
                    "always excluded."
                ),
                category="sql",
                capabilities=(
                    Capability.FILESYSTEM_READ
                    | Capability.FILESYSTEM_WRITE
                    | Capability.DATABASE_READ
                    | Capability.DATABASE_WRITE
                ),
                origin="plugin.sql_odbc",
                requires_confirmation=True,
                timeout=120,
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Database file path inside the "
                            "sandbox."
                        ),
                    ),
                    ToolParameter(
                        name="sql",
                        param_type="string",
                        description=(
                            "One INSERT, UPDATE, DELETE, MERGE "
                            "or REPLACE statement."
                        ),
                    ),
                    ToolParameter(
                        name="driver",
                        param_type="string",
                        description=(
                            "ODBC alias or exact driver name: "
                            "access, sqlite-odbc, firebird, "
                            "duckdb, dbase, or an installed "
                            "driver. Default: auto."
                        ),
                        required=False,
                        default="auto",
                    ),
                    ToolParameter(
                        name="timeout_seconds",
                        param_type="integer",
                        description=(
                            "Maximum statement time in seconds "
                            "(1-120). Default: 30."
                        ),
                        required=False,
                        default=30,
                    ),
                ],
                handler=self.execute,
            )
        )

    # ==========================================================
    # Handler
    # ==========================================================

    def _prepare(
        self,
        path: str,
        driver: str,
        operation: str = "read",
    ) -> tuple[Any, str, str]:

        target, display = self.reader.resolve(
            path,
            operation=operation,
        )

        adapter, alias = self.reader.select_adapter(
            target,
            driver,
        )

        if adapter != "odbc":

            raise SqlFileError(
                "sql.odbc uses only ODBC drivers; "
                "for native SQLite read-only use "
                "sql.file.query, or set "
                "driver='sqlite-odbc' with an installed "
                "SQLite ODBC driver"
            )

        return target, display, alias or ""

    def drivers(self) -> str:

        try:

            report = self.reader.drivers()
            report["native"] = []
            report["plugin"] = "sql-odbc"
            report["extensions"] = {
                extension: adapter
                for extension, adapter in report[
                    "extensions"
                ].items()
                if adapter != "sqlite"
            }
            report["note"] = (
                "This plugin uses ODBC only; native "
                "SQLite is available via sql.file.query."
            )

            return _json(report)

        except Exception as exc:  # noqa: BLE001

            return _error(exc)

    def schema(
        self,
        path: str,
        driver: str = "auto",
        table: str | None = None,
        schema: str | None = None,
        max_tables: int = 200,
        timeout_seconds: int = 30,
    ) -> str:

        try:

            target, display, alias = self._prepare(
                path,
                driver,
            )

            database = OdbcDatabase(
                target,
                display,
                alias,
                read_only=True,
            )

            payload = database.schema(
                table=table,
                schema_name=schema,
                max_tables=max_tables,
                timeout_seconds=timeout_seconds,
            )

            payload["success"] = True
            payload["path"] = display
            payload["adapter"] = "odbc"

            return _json(payload)

        except Exception as exc:  # noqa: BLE001

            return _error(exc)

    def query(
        self,
        path: str,
        sql: str,
        driver: str = "auto",
        max_rows: int = 100,
        timeout_seconds: int = 30,
    ) -> str:

        try:

            target, display, alias = self._prepare(
                path,
                driver,
            )

            database = OdbcDatabase(
                target,
                display,
                alias,
                read_only=True,
            )

            payload = database.query(
                sql,
                max_rows=max_rows,
                timeout_seconds=timeout_seconds,
            )

            payload["success"] = True
            payload["path"] = display
            payload["adapter"] = "odbc"

            return _json(payload)

        except Exception as exc:  # noqa: BLE001

            return _error(exc)

    def execute(
        self,
        path: str,
        sql: str,
        driver: str = "auto",
        timeout_seconds: int = 30,
    ) -> str:

        try:

            target, display, alias = self._prepare(
                path,
                driver,
                operation="write",
            )

            database = OdbcDatabase(
                target,
                display,
                alias,
                read_only=False,
            )

            payload = database.execute(
                sql,
                timeout_seconds=timeout_seconds,
            )

            payload["success"] = True
            payload["path"] = display
            payload["adapter"] = "odbc"

            return _json(payload)

        except Exception as exc:  # noqa: BLE001

            return _error(exc)
