"""Tool SQL in sola lettura per database su file nella sandbox."""

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


class SqlFileToolProvider:
    """Espone ispezione e query read-only sui file della sandbox."""

    def __init__(
        self,
        filesystem: Any,
        forbidden_paths: Any = (),
    ) -> None:

        self.reader = SqlFileReader(
            filesystem,
            forbidden_paths=forbidden_paths,
        )

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="sql.file.drivers",
                description=(
                    "List native SQL adapters and installed "
                    "ODBC drivers for local database files. "
                    "Use it when a file format is not "
                    "recognized or a driver is missing."
                ),
                category="sql",
                capabilities=Capability.DATABASE_READ,
                origin="local",
                timeout=15,
                parameters=[],
                handler=self.drivers,
            )
        )

        registry.register(
            ToolDefinition(
                name="sql.file.schema",
                description=(
                    "Inspect a local database file inside the "
                    "sandbox. Without table, lists tables and "
                    "views; with table, returns columns, "
                    "primary key, foreign keys and indexes. "
                    "Read-only. SQLite is native; other file "
                    "databases need an installed ODBC driver."
                ),
                category="sql",
                capabilities=(
                    Capability.FILESYSTEM_READ
                    | Capability.DATABASE_READ
                ),
                origin="local",
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
                            "Adapter or ODBC driver. Use auto "
                            "to infer from the extension, "
                            "sqlite for the native adapter, "
                            "sqlite-odbc, access, firebird, "
                            "duckdb, dbase, or an installed "
                            "ODBC driver name. Default: auto."
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
                name="sql.file.query",
                description=(
                    "Run one read-only SELECT, WITH or EXPLAIN "
                    "statement against a local database file "
                    "inside the sandbox. SQLite is native; "
                    "other formats need an installed ODBC "
                    "driver. Multiple statements and write "
                    "statements are rejected. Results are "
                    "bounded by max_rows and timeout_seconds."
                ),
                category="sql",
                capabilities=(
                    Capability.FILESYSTEM_READ
                    | Capability.DATABASE_READ
                ),
                origin="local",
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
                            "Adapter or ODBC driver. Use auto "
                            "to infer from the extension, "
                            "sqlite for the native adapter, "
                            "sqlite-odbc, access, firebird, "
                            "duckdb, dbase, or an installed "
                            "ODBC driver name. Default: auto."
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

    # ==========================================================
    # Handler
    # ==========================================================

    def drivers(self) -> str:

        try:
            return _json(self.reader.drivers())

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

            return _json(
                self.reader.schema(
                    path,
                    driver=driver,
                    table=table,
                    schema_name=schema,
                    max_tables=max_tables,
                    timeout_seconds=timeout_seconds,
                )
            )

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

            return _json(
                self.reader.query(
                    path,
                    sql,
                    driver=driver,
                    max_rows=max_rows,
                    timeout_seconds=timeout_seconds,
                )
            )

        except Exception as exc:  # noqa: BLE001

            return _error(exc)
