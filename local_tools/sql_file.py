"""Accesso in sola lettura a database SQL su file.

SQLite usa la stdlib; gli altri formati passano da ODBC con il driver
installato dall'host. Il percorso del database deve stare dentro la
sandbox e non può coincidere con il database delle memorie di Hagar.
"""

from __future__ import annotations

import base64
import os
import re
import sqlite3
import time

from datetime import date
from datetime import datetime
from datetime import time as time_of_day
from decimal import Decimal
from pathlib import Path
from typing import Any

from memory.database import default_memory_path


MAX_SQL_CHARS = 20_000

MAX_CELL_CHARS = 4_000

MAX_BLOB_BYTES = 4_096

MAX_ROWS = 1_000

MAX_TABLES = 500

MAX_CATALOG_ROWS = 2_000

MAX_NAME_CHARS = 128

MAX_TIMEOUT_SECONDS = 120

DEFAULT_ROWS = 100

DEFAULT_TIMEOUT = 30

DEFAULT_MAX_TABLES = 200

ODBC_ALIASES = {
    "access": (
        "Microsoft Access Driver (*.mdb, *.accdb)",
        "Microsoft Access Driver (*.mdb)",
    ),
    "sqlite-odbc": (
        "SQLite3 ODBC Driver",
        "SQLite ODBC Driver",
    ),
    "firebird": (
        "Firebird/InterBase(r) driver",
        "Firebird ODBC Driver",
    ),
    "duckdb": (
        "DuckDB Driver",
    ),
    "dbase": (
        "Microsoft dBase Driver (*.dbf)",
    ),
}

EXTENSION_ALIASES = {
    ".db": "sqlite",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".accdb": "access",
    ".mdb": "access",
    ".fdb": "firebird",
    ".duckdb": "duckdb",
    ".dbf": "dbase",
}

DANGEROUS_TOKENS = (
    "OPENROWSET",
    "OPENDATASOURCE",
    "OPENQUERY",
    "BULK",
    "XP_CMDSHELL",
    "SP_EXECUTESQL",
    "PG_READ_FILE",
    "PG_LS_DIR",
    "LO_IMPORT",
    "LO_EXPORT",
    "DBLINK",
    "UTL_FILE",
    "DBMS_",
    "LOAD_EXTENSION",
    "READFILE",
    "WRITEFILE",
)

WRITE_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "REPLACE",
    "CREATE",
    "ALTER",
    "DROP",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "CALL",
    "EXEC",
    "EXECUTE",
    "COPY",
    "LOAD",
    "VACUUM",
    "ANALYZE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
)

BLOCKED_SQLITE_FUNCTIONS = {
    "load_extension",
    "readfile",
    "writefile",
    "edit",
    "fts3_tokenizer",
}

VERBS = {"SELECT", "WITH", "EXPLAIN"}

WRITE_VERBS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "REPLACE",
}


class SqlFileError(RuntimeError):
    """Errore SQL leggibile dal modello, senza percorsi host."""


class SqlDriverError(SqlFileError):
    """Driver ODBC mancante o non utilizzabile."""


def _bounded_int(
    value: Any,
    default: int,
    minimum: int,
    maximum: int,
    name: str,
) -> int:

    if value is None:
        return default

    if isinstance(value, bool):
        raise SqlFileError(
            f"{name} must be an integer"
        )

    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SqlFileError(
            f"{name} must be an integer"
        ) from exc

    return max(minimum, min(number, maximum))


def _clean_name(
    value: Any,
    name: str,
) -> str:

    if not isinstance(value, str):
        raise SqlFileError(
            f"{name} must be a string"
        )

    value = value.strip()

    if not value:
        raise SqlFileError(
            f"{name} must not be empty"
        )

    if len(value) > MAX_NAME_CHARS:
        raise SqlFileError(
            f"{name} is too long"
        )

    if "\x00" in value:
        raise SqlFileError(
            f"{name} contains invalid characters"
        )

    return value


def _strip_sql_literals_and_comments(
    sql: str,
) -> str:
    """Sostituisce stringhe e commenti con spazi.

    Serve solo a contare le istruzioni e a cercare parole chiave:
    l'esecuzione resta al database. Il parser è volutamente
    conservativo; un falso positivo è un rifiuto, non un rischio.
    """

    result: list[str] = []
    index = 0
    length = len(sql)

    while index < length:

        char = sql[index]
        following = (
            sql[index + 1]
            if index + 1 < length
            else ""
        )

        if char == "-" and following == "-":

            index += 2

            while (
                index < length
                and sql[index] not in "\r\n"
            ):
                index += 1

            result.append(" ")
            continue

        if char == "/" and following == "*":

            index += 2

            while (
                index + 1 < length
                and not (
                    sql[index] == "*"
                    and sql[index + 1] == "/"
                )
            ):
                index += 1

            index = min(length, index + 2)
            result.append(" ")
            continue

        if char in {"'", '"', "`"}:

            quote = char
            result.append(" ")
            index += 1

            while index < length:

                if (
                    sql[index] == "\\"
                    and quote in {"'", '"'}
                ):
                    index += 2
                    continue

                if sql[index] == quote:

                    if (
                        index + 1 < length
                        and sql[index + 1] == quote
                    ):
                        index += 2
                        continue

                    index += 1
                    break

                index += 1

            continue

        if char == "[":

            result.append(" ")
            index += 1

            while index < length:

                if sql[index] == "]":

                    if (
                        index + 1 < length
                        and sql[index + 1] == "]"
                    ):
                        index += 2
                        continue

                    index += 1
                    break

                index += 1

            continue

        if char == "$":

            match = re.match(
                r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$",
                sql[index:],
            )

            if match is not None:

                tag = match.group(0)
                end = sql.find(
                    tag,
                    index + len(tag),
                )

                if end < 0:
                    index = length
                else:
                    index = end + len(tag)

                result.append(" ")
                continue

        result.append(char)
        index += 1

    return "".join(result)


def validate_read_only_sql(
    sql: Any,
) -> str:
    """Accetta una sola istruzione di lettura."""

    if not isinstance(sql, str):
        raise SqlFileError(
            "sql must be a string"
        )

    text = sql.strip()

    if not text:
        raise SqlFileError(
            "sql must not be empty"
        )

    if len(text) > MAX_SQL_CHARS:
        raise SqlFileError(
            "sql is too long "
            f"(max {MAX_SQL_CHARS} characters)"
        )

    cleaned = _strip_sql_literals_and_comments(
        text
    )

    body = cleaned.strip()

    if body.endswith(";"):
        body = body[:-1].rstrip()

    if ";" in body:
        raise SqlFileError(
            "only one SQL statement is allowed"
        )

    match = re.match(
        r"(?is)^([A-Za-z]+)\b",
        body,
    )

    if match is None:
        raise SqlFileError(
            "SQL statement is not recognizable"
        )

    verb = match.group(1).upper()

    if verb not in VERBS:
        raise SqlFileError(
            "only SELECT, WITH or EXPLAIN "
            "statements are allowed"
        )

    upper = body.upper()

    if verb in {"SELECT", "WITH"}:

        if re.search(r"\bINTO\b", upper):

            raise SqlFileError(
                "SELECT ... INTO is not allowed "
                "in read-only mode"
            )

    if verb == "WITH":

        for keyword in WRITE_KEYWORDS:

            if re.search(
                rf"\b{keyword}\b",
                upper,
            ):

                raise SqlFileError(
                    "write statements are not allowed "
                    "in read-only mode"
                )

    if verb == "EXPLAIN":

        if re.match(
            r"(?is)^EXPLAIN\s+ANALYZE\b",
            body,
        ):

            raise SqlFileError(
                "EXPLAIN ANALYZE is not allowed "
                "in read-only mode"
            )

    for token in DANGEROUS_TOKENS:

        if token == "DBMS_":

            forbidden = re.search(
                r"\bDBMS_",
                upper,
            )

        else:

            forbidden = re.search(
                rf"\b{token}\b",
                upper,
            )

        if forbidden:

            raise SqlFileError(
                f"SQL token not allowed: {token}"
            )

    return text


def validate_write_sql(
    sql: Any,
) -> str:
    """Accetta una sola istruzione DML esplicita.

    Le DDL restano fuori dal primo taglio: ``CREATE``, ``ALTER``,
    ``DROP`` e ``TRUNCATE`` richiedono una decisione separata.
    """

    if not isinstance(sql, str):
        raise SqlFileError(
            "sql must be a string"
        )

    text = sql.strip()

    if not text:
        raise SqlFileError(
            "sql must not be empty"
        )

    if len(text) > MAX_SQL_CHARS:
        raise SqlFileError(
            "sql is too long "
            f"(max {MAX_SQL_CHARS} characters)"
        )

    cleaned = _strip_sql_literals_and_comments(
        text
    )

    body = cleaned.strip()

    if body.endswith(";"):
        body = body[:-1].rstrip()

    if ";" in body:
        raise SqlFileError(
            "only one SQL statement is allowed"
        )

    match = re.match(
        r"(?is)^([A-Za-z]+)\b",
        body,
    )

    if match is None:
        raise SqlFileError(
            "SQL statement is not recognizable"
        )

    verb = match.group(1).upper()

    if verb not in WRITE_VERBS:
        raise SqlFileError(
            "only INSERT, UPDATE, DELETE, MERGE "
            "or REPLACE statements are allowed"
        )

    upper = body.upper()

    for token in DANGEROUS_TOKENS:

        if token == "DBMS_":

            forbidden = re.search(
                r"\bDBMS_",
                upper,
            )

        else:

            forbidden = re.search(
                rf"\b{token}\b",
                upper,
            )

        if forbidden:

            raise SqlFileError(
                f"SQL token not allowed: {token}"
            )

    return text


def memory_database_paths(
    config: Any = None,
    memory: Any = None,
) -> list[Path]:
    """Percorsi del DB memorie da escludere dai tool SQL."""

    paths: list[Path] = []

    database = getattr(memory, "database", None)
    memory_path = getattr(database, "path", None)

    if memory_path:
        paths.append(Path(memory_path))

    if config is not None:

        memory_config = getattr(
            config,
            "memory",
            None,
        )

        configured = getattr(
            memory_config,
            "database",
            None,
        )

        if configured:
            paths.append(Path(configured))

        paths.append(default_memory_path())

    return paths


def _json_value(
    value: Any,
) -> Any:

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    if isinstance(value, str):

        if len(value) > MAX_CELL_CHARS:
            return (
                value[:MAX_CELL_CHARS]
                + "...[truncated]"
            )

        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(
        value,
        (datetime, date, time_of_day),
    ):
        return value.isoformat()

    if isinstance(
        value,
        (bytes, bytearray, memoryview),
    ):

        raw = bytes(value)
        truncated = len(raw) > MAX_BLOB_BYTES

        return {
            "base64": base64.b64encode(
                raw[:MAX_BLOB_BYTES]
            ).decode("ascii"),
            "truncated": truncated,
        }

    text = str(value)

    if len(text) > MAX_CELL_CHARS:
        text = (
            text[:MAX_CELL_CHARS]
            + "...[truncated]"
        )

    return text


def _json_row(
    row: Any,
) -> list[Any]:

    return [
        _json_value(value)
        for value in row
    ]


def _description_columns(
    description: Any,
) -> list[dict[str, Any]]:

    columns = []

    for item in description or []:

        if not item:
            continue

        name = item[0]
        type_code = (
            item[1]
            if len(item) > 1
            else None
        )

        if not isinstance(
            type_code,
            (int, str, type(None)),
        ):
            type_code = str(type_code)

        columns.append(
            {
                "name": str(name),
                "type_code": type_code,
            }
        )

    return columns


def _quote_sqlite_identifier(
    value: str,
) -> str:

    return '"' + value.replace(
        '"',
        '""',
    ) + '"'


def _normalize_path(
    path: Path,
) -> str:

    return os.path.normcase(
        os.path.abspath(str(path))
    )


def _match_driver(
    drivers: list[str],
    wanted: str,
) -> str | None:

    for driver in drivers:

        if driver.casefold() == wanted.casefold():
            return driver

    return None


def _drivers_text(
    drivers: list[str],
) -> str:

    if not drivers:
        return "none"

    ordered = sorted(
        drivers,
        key=str.casefold,
    )

    if len(ordered) > 20:
        ordered = ordered[:20] + ["..."]

    return ", ".join(ordered)


def _load_odbc():

    try:
        import pyodbc

    except Exception as exc:  # noqa: BLE001

        raise SqlDriverError(
            "ODBC support requires pyodbc; "
            "install Hagar with the 'database' extra"
        ) from exc

    return pyodbc


def _odbc_drivers(
    pyodbc: Any,
) -> list[str]:

    try:
        return [
            str(driver)
            for driver in pyodbc.drivers()
        ]

    except Exception as exc:  # noqa: BLE001

        raise SqlDriverError(
            "cannot enumerate ODBC drivers: "
            f"{exc}"
        ) from exc


def _resolve_odbc_driver(
    alias: str,
    drivers: list[str],
) -> str:

    if alias in ODBC_ALIASES:

        for candidate in ODBC_ALIASES[alias]:

            match = _match_driver(
                drivers,
                candidate,
            )

            if match is not None:
                return match

        raise SqlDriverError(
            f"ODBC driver for '{alias}' is not "
            "installed; available: "
            f"{_drivers_text(drivers)}"
        )

    match = _match_driver(drivers, alias)

    if match is not None:
        return match

    raise SqlDriverError(
        f"ODBC driver '{alias}' is not installed; "
        "available: "
        f"{_drivers_text(drivers)}"
    )


def _odbc_value(
    value: Any,
) -> str:

    text = str(value).replace("}", "}}")

    return "{" + text + "}"


def _odbc_connection_string(
    driver: str,
    path: Path,
    alias: str,
) -> str:

    key = (
        "Database"
        if alias in {
            "sqlite-odbc",
            "firebird",
            "duckdb",
        }
        else "DBQ"
    )

    return (
        f"DRIVER={_odbc_value(driver)};"
        f"{key}={_odbc_value(str(path))};"
    )


def odbc_driver_report() -> dict[str, Any]:
    """Stato dei driver ODBC, senza toccare alcun database."""

    base = {
        "success": True,
        "native": ["sqlite"],
        "odbc_available": False,
        "odbc_drivers": [],
        "aliases": {},
        "extensions": dict(EXTENSION_ALIASES),
    }

    try:
        pyodbc = _load_odbc()
        drivers = _odbc_drivers(pyodbc)

    except SqlDriverError as exc:

        base["error"] = str(exc)
        return base

    drivers = sorted(
        set(drivers),
        key=str.casefold,
    )

    aliases = {}

    for alias, candidates in ODBC_ALIASES.items():

        match = None

        for candidate in candidates:

            match = _match_driver(
                drivers,
                candidate,
            )

            if match is not None:
                break

        aliases[alias] = {
            "available": match is not None,
            "driver": match,
            "candidates": list(candidates),
        }

    base["odbc_available"] = True
    base["odbc_drivers"] = drivers
    base["aliases"] = aliases

    return base


class SqliteDatabase:
    """SQLite in modalità ``mode=ro`` con authorizer."""

    def __init__(
        self,
        path: Path,
        display: str,
    ) -> None:

        self.path = path
        self.display = display

    def _error(
        self,
        exc: Exception,
    ) -> str:

        message = str(exc) or exc.__class__.__name__

        for value in {
            str(self.path),
            self.path.as_posix(),
        }:
            message = message.replace(
                value,
                self.display,
            )

        return message

    def _connect(self) -> sqlite3.Connection:

        try:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=ro",
                uri=True,
                timeout=10,
            )

        except sqlite3.Error as exc:

            raise SqlFileError(
                self._error(exc)
            ) from exc

        return connection

    @staticmethod
    def _authorizer(
        action: int,
        arg1: Any,
        arg2: Any,
        dbname: Any,
        source: Any,
    ) -> int:

        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
        }

        for name in (
            "SQLITE_RECURSIVE",
            "SQLITE_TRANSACTION",
        ):

            value = getattr(
                sqlite3,
                name,
                None,
            )

            if value is not None:
                allowed.add(value)

        if action in allowed:
            return sqlite3.SQLITE_OK

        if action == sqlite3.SQLITE_FUNCTION:

            function = str(arg2 or "").casefold()

            if function in BLOCKED_SQLITE_FUNCTIONS:
                return sqlite3.SQLITE_DENY

            return sqlite3.SQLITE_OK

        return sqlite3.SQLITE_DENY

    @staticmethod
    def _deadline_handler(
        deadline: float,
    ):

        def handler() -> int:

            return (
                1
                if time.monotonic() > deadline
                else 0
            )

        return handler

    def query(
        self,
        sql: str,
        max_rows: int,
        timeout_seconds: int,
    ) -> dict[str, Any]:

        sql = validate_read_only_sql(sql)

        max_rows = _bounded_int(
            max_rows,
            DEFAULT_ROWS,
            1,
            MAX_ROWS,
            "max_rows",
        )

        timeout_seconds = _bounded_int(
            timeout_seconds,
            DEFAULT_TIMEOUT,
            1,
            MAX_TIMEOUT_SECONDS,
            "timeout_seconds",
        )

        started = time.monotonic()

        connection = self._connect()

        try:

            connection.execute(
                "PRAGMA query_only = ON"
            )
            connection.set_authorizer(
                self._authorizer
            )
            connection.set_progress_handler(
                self._deadline_handler(
                    started + timeout_seconds
                ),
                1000,
            )

            cursor = connection.cursor()
            cursor.execute(sql)

            description = cursor.description or []

            raw_rows = cursor.fetchmany(
                max_rows + 1
            )

            truncated = len(raw_rows) > max_rows

            rows = [
                _json_row(row)
                for row in raw_rows[:max_rows]
            ]

        except sqlite3.OperationalError as exc:

            if "interrupted" in str(exc).lower():

                raise SqlFileError(
                    "query timed out after "
                    f"{timeout_seconds}s"
                ) from exc

            raise SqlFileError(
                self._error(exc)
            ) from exc

        except sqlite3.Error as exc:

            raise SqlFileError(
                self._error(exc)
            ) from exc

        finally:

            try:
                connection.set_progress_handler(
                    lambda: 0,
                    0,
                )

            except Exception:  # noqa: BLE001
                pass

            connection.close()

        duration_ms = int(
            (time.monotonic() - started) * 1000
        )

        return {
            "columns": _description_columns(
                description
            ),
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "duration_ms": duration_ms,
            "read_only": True,
        }

    def schema(
        self,
        table: str | None = None,
        max_tables: int = DEFAULT_MAX_TABLES,
    ) -> dict[str, Any]:

        max_tables = _bounded_int(
            max_tables,
            DEFAULT_MAX_TABLES,
            1,
            MAX_TABLES,
            "max_tables",
        )

        connection = self._connect()

        try:

            if table is None:

                rows = connection.execute(
                    "SELECT name, type "
                    "FROM sqlite_master "
                    "WHERE type IN ('table', 'view') "
                    "AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY type, name"
                ).fetchall()

                tables = [
                    {
                        "name": row[0],
                        "type": row[1],
                    }
                    for row in rows
                ]

                return {
                    "tables": tables[:max_tables],
                    "count": min(
                        len(tables),
                        max_tables,
                    ),
                    "truncated": (
                        len(tables) > max_tables
                    ),
                }

            quoted = _quote_sqlite_identifier(
                table
            )

            rows = connection.execute(
                f"PRAGMA table_info({quoted})"
            ).fetchall()

            if not rows:
                raise SqlFileError(
                    f"table or view not found: "
                    f"{table}"
                )

            columns = [
                {
                    "name": row[1],
                    "type": row[2] or "",
                    "not_null": bool(row[3]),
                    "default": row[4],
                    "primary_key": bool(row[5]),
                    "primary_key_order": row[5],
                }
                for row in rows
            ]

            primary_key = [
                column["name"]
                for column in sorted(
                    (
                        item
                        for item in columns
                        if item["primary_key"]
                    ),
                    key=lambda item: (
                        item["primary_key_order"]
                    ),
                )
            ]

            foreign_keys = [
                {
                    "from": row[3],
                    "to_table": row[2],
                    "to_column": row[4],
                    "on_update": row[5],
                    "on_delete": row[6],
                    "match": row[7],
                }
                for row in connection.execute(
                    "PRAGMA foreign_key_list"
                    f"({quoted})"
                ).fetchall()
            ]

            indexes = []

            for row in connection.execute(
                f"PRAGMA index_list({quoted})"
            ).fetchall():

                index_name = row[1]

                index_columns = [
                    item[2]
                    for item in connection.execute(
                        "PRAGMA index_info"
                        f"({_quote_sqlite_identifier(index_name)})"
                    ).fetchall()
                ]

                indexes.append(
                    {
                        "name": index_name,
                        "unique": bool(row[2]),
                        "origin": row[3],
                        "partial": bool(row[4]),
                        "columns": index_columns,
                    }
                )

            return {
                "table": table,
                "columns": columns,
                "primary_key": primary_key,
                "foreign_keys": foreign_keys,
                "indexes": indexes,
                "found": True,
            }

        except sqlite3.Error as exc:

            raise SqlFileError(
                self._error(exc)
            ) from exc

        finally:
            connection.close()


class OdbcDatabase:
    """Database su file raggiunto attraverso un driver ODBC."""

    def __init__(
        self,
        path: Path,
        display: str,
        driver: str,
        read_only: bool = True,
    ) -> None:

        self.path = path
        self.display = display
        self.driver = driver
        self.read_only = bool(read_only)

    def _error(
        self,
        exc: Exception,
    ) -> str:

        message = str(exc) or exc.__class__.__name__

        for value in {
            str(self.path),
            self.path.as_posix(),
        }:
            message = message.replace(
                value,
                self.display,
            )

        return message

    def _connect(
        self,
        timeout_seconds: int,
        read_only: bool | None = None,
    ) -> tuple[Any, str]:

        pyodbc = _load_odbc()
        drivers = _odbc_drivers(pyodbc)
        driver = _resolve_odbc_driver(
            self.driver,
            drivers,
        )

        connection_string = _odbc_connection_string(
            driver,
            self.path,
            self.driver,
        )

        read_only = (
            self.read_only
            if read_only is None
            else bool(read_only)
        )

        try:
            connection = pyodbc.connect(
                connection_string,
                readonly=read_only,
                autocommit=False,
                timeout=int(timeout_seconds),
            )

        except TypeError as exc:

            raise SqlDriverError(
                "installed pyodbc does not support "
                "read-only connections"
            ) from exc

        except Exception as exc:  # noqa: BLE001

            raise SqlFileError(
                self._error(exc)
            ) from exc

        try:
            connection.timeout = int(
                timeout_seconds
            )

        except Exception:  # noqa: BLE001
            pass

        return connection, driver

    def query(
        self,
        sql: str,
        max_rows: int,
        timeout_seconds: int,
    ) -> dict[str, Any]:

        sql = validate_read_only_sql(sql)

        max_rows = _bounded_int(
            max_rows,
            DEFAULT_ROWS,
            1,
            MAX_ROWS,
            "max_rows",
        )

        timeout_seconds = _bounded_int(
            timeout_seconds,
            DEFAULT_TIMEOUT,
            1,
            MAX_TIMEOUT_SECONDS,
            "timeout_seconds",
        )

        started = time.monotonic()

        connection, driver = self._connect(
            timeout_seconds
        )

        cursor = None

        try:

            cursor = connection.cursor()
            cursor.execute(sql)

            description = cursor.description or []

            raw_rows = cursor.fetchmany(
                max_rows + 1
            )

            truncated = len(raw_rows) > max_rows

            rows = [
                _json_row(row)
                for row in raw_rows[:max_rows]
            ]

            return {
                "driver": driver,
                "columns": _description_columns(
                    description
                ),
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
                "duration_ms": int(
                    (
                        time.monotonic()
                        - started
                    )
                    * 1000
                ),
                "read_only": True,
            }

        except SqlFileError:
            raise

        except Exception as exc:  # noqa: BLE001

            raise SqlFileError(
                self._error(exc)
            ) from exc

        finally:

            try:

                if cursor is not None:
                    cursor.close()

            except Exception:  # noqa: BLE001
                pass

            try:
                connection.rollback()
            except Exception:  # noqa: BLE001
                pass

            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass

    def execute(
        self,
        sql: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:

        sql = validate_write_sql(sql)

        timeout_seconds = _bounded_int(
            timeout_seconds,
            DEFAULT_TIMEOUT,
            1,
            MAX_TIMEOUT_SECONDS,
            "timeout_seconds",
        )

        started = time.monotonic()

        connection, driver = self._connect(
            timeout_seconds,
            read_only=False,
        )

        cursor = None
        committed = False

        try:

            cursor = connection.cursor()
            cursor.execute(sql)

            row_count = getattr(
                cursor,
                "rowcount",
                -1,
            )

            if not isinstance(row_count, int):
                row_count = -1

            connection.commit()
            committed = True

            return {
                "driver": driver,
                "row_count": row_count,
                "committed": True,
                "duration_ms": int(
                    (
                        time.monotonic()
                        - started
                    )
                    * 1000
                ),
            }

        except SqlFileError:
            raise

        except Exception as exc:  # noqa: BLE001

            try:
                connection.rollback()

            except Exception:  # noqa: BLE001
                pass

            raise SqlFileError(
                self._error(exc)
            ) from exc

        finally:

            try:

                if cursor is not None:
                    cursor.close()

            except Exception:  # noqa: BLE001
                pass

            if not committed:

                try:
                    connection.rollback()

                except Exception:  # noqa: BLE001
                    pass

            try:
                connection.close()

            except Exception:  # noqa: BLE001
                pass

    def _catalog(
        self,
        cursor: Any,
        method: str,
        warnings: list[str],
        **kwargs,
    ) -> list[dict[str, Any]]:

        function = getattr(
            cursor,
            method,
            None,
        )

        if function is None:

            warnings.append(
                f"ODBC driver does not expose "
                f"{method}()"
            )

            return []

        try:

            result = function(
                **{
                    key: value
                    for key, value in kwargs.items()
                    if value is not None
                }
            )

        except Exception as exc:  # noqa: BLE001

            warnings.append(
                f"{method}() failed: "
                f"{self._error(exc)}"
            )

            return []

        description = (
            getattr(result, "description", None)
            or []
        )

        names = [
            str(item[0]).lower()
            for item in description
        ]

        if not names:

            warnings.append(
                f"{method}() returned no description"
            )

            return []

        try:

            rows = result.fetchmany(
                MAX_CATALOG_ROWS + 1
            )

        except Exception as exc:  # noqa: BLE001

            warnings.append(
                f"{method}() fetch failed: "
                f"{self._error(exc)}"
            )

            return []

        mapped = []

        for row in rows[:MAX_CATALOG_ROWS]:

            mapped.append(
                {
                    name: _json_value(value)
                    for name, value in zip(
                        names,
                        row,
                    )
                }
            )

        return mapped

    def schema(
        self,
        table: str | None = None,
        schema_name: str | None = None,
        max_tables: int = DEFAULT_MAX_TABLES,
        timeout_seconds: int = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:

        max_tables = _bounded_int(
            max_tables,
            DEFAULT_MAX_TABLES,
            1,
            MAX_TABLES,
            "max_tables",
        )

        timeout_seconds = _bounded_int(
            timeout_seconds,
            DEFAULT_TIMEOUT,
            1,
            MAX_TIMEOUT_SECONDS,
            "timeout_seconds",
        )

        connection, driver = self._connect(
            timeout_seconds
        )

        cursor = None
        warnings: list[str] = []

        try:

            cursor = connection.cursor()

            if table is not None:

                columns = self._catalog(
                    cursor,
                    "columns",
                    warnings,
                    table=table,
                    schema=schema_name,
                )

                primary_key = self._catalog(
                    cursor,
                    "primaryKeys",
                    warnings,
                    table=table,
                    schema=schema_name,
                )

                foreign_keys = self._catalog(
                    cursor,
                    "foreignKeys",
                    warnings,
                    table=table,
                    schema=schema_name,
                )

                return {
                    "driver": driver,
                    "table": table,
                    "columns": columns,
                    "primary_key": primary_key,
                    "foreign_keys": foreign_keys,
                    "found": bool(columns),
                    "warnings": warnings,
                }

            rows = self._catalog(
                cursor,
                "tables",
                warnings,
                schema=schema_name,
            )

            tables = []
            seen = set()

            for row in rows:

                table_type = str(
                    row.get("table_type") or ""
                ).upper()

                if "SYSTEM" in table_type:
                    continue

                name = row.get("table_name")

                if not name:
                    continue

                key = (
                    row.get("table_cat"),
                    row.get("table_schem"),
                    name,
                )

                if key in seen:
                    continue

                seen.add(key)

                tables.append(
                    {
                        "catalog":
                            row.get("table_cat"),
                        "schema":
                            row.get("table_schem"),
                        "name": name,
                        "type": table_type or None,
                    }
                )

            return {
                "driver": driver,
                "tables": tables[:max_tables],
                "count": min(
                    len(tables),
                    max_tables,
                ),
                "truncated": (
                    len(tables) > max_tables
                ),
                "warnings": warnings,
            }

        except SqlFileError:
            raise

        except Exception as exc:  # noqa: BLE001

            raise SqlFileError(
                self._error(exc)
            ) from exc

        finally:

            try:

                if cursor is not None:
                    cursor.close()

            except Exception:  # noqa: BLE001
                pass

            try:
                connection.rollback()
            except Exception:  # noqa: BLE001
                pass

            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass


class SqlFileReader:
    """Orchestratore sandbox, adapter e controlli di sicurezza."""

    def __init__(
        self,
        filesystem: Any,
        forbidden_paths: Any = (),
    ) -> None:

        self.filesystem = filesystem

        self._forbidden = tuple(
            dict.fromkeys(
                Path(path).expanduser().resolve()
                for path in forbidden_paths
                if path is not None
            )
        )

    def _display(
        self,
        target: Path,
    ) -> str:

        try:
            return self.filesystem.virtual_path(
                target
            )

        except Exception:  # noqa: BLE001
            return "outside sandbox"

    def _assert_allowed(
        self,
        target: Path,
    ) -> None:

        target_name = _normalize_path(target)

        target_stat = None

        try:
            target_stat = target.stat()

        except OSError:
            pass

        for forbidden in self._forbidden:

            base = _normalize_path(forbidden)

            for suffix in (
                "",
                "-wal",
                "-shm",
                "-journal",
            ):

                if target_name == base + suffix:

                    raise SqlFileError(
                        "access to the Hagar memory "
                        "database is not allowed"
                    )

            if target_stat is None:
                continue

            try:
                forbidden_stat = forbidden.stat()

            except OSError:
                continue

            if (
                target_stat.st_ino
                and forbidden_stat.st_ino
                and (
                    target_stat.st_dev,
                    target_stat.st_ino,
                ) == (
                    forbidden_stat.st_dev,
                    forbidden_stat.st_ino,
                )
            ):

                raise SqlFileError(
                    "access to the Hagar memory "
                    "database is not allowed"
                )

    def resolve(
        self,
        path: Any,
        operation: str = "read",
    ) -> tuple[Path, str]:

        if not isinstance(path, str):
            raise SqlFileError(
                "path must be a string"
            )

        path = path.strip()

        if not path:
            raise SqlFileError(
                "path must not be empty"
            )

        try:
            target = self.filesystem.resolve_path(
                path
            )

        except PermissionError as exc:

            raise SqlFileError(
                str(exc)
            ) from exc

        except FileNotFoundError as exc:

            raise SqlFileError(
                "path not found"
            ) from exc

        error = self.filesystem.FS_Guardian(
            operation,
            target,
        )

        if error:
            raise SqlFileError(error)

        if operation == "write":

            read_error = self.filesystem.FS_Guardian(
                "read",
                target,
            )

            if read_error:
                raise SqlFileError(read_error)

        try:
            is_file = target.is_file()

        except OSError as exc:

            raise SqlFileError(
                f"{self._display(target)} is not "
                "accessible"
            ) from exc

        if not is_file:

            raise SqlFileError(
                f"{self._display(target)} is not a file"
            )

        self._assert_allowed(target)

        return target, self._display(target)

    def select_adapter(
        self,
        target: Path,
        driver: str | None,
    ) -> tuple[str, str | None]:

        driver = (
            driver.strip()
            if isinstance(driver, str)
            else ""
        )

        if not driver:
            driver = "auto"

        lower = driver.casefold()

        if lower == "auto":

            extension = target.suffix.casefold()

            if extension in {
                ".db",
                ".sqlite",
                ".sqlite3",
            }:
                return "sqlite", None

            alias = EXTENSION_ALIASES.get(
                extension
            )

            if alias is not None:
                return "odbc", alias

            raise SqlDriverError(
                "cannot infer a database adapter "
                f"for extension "
                f"'{extension or '<none>'}'; "
                "use driver='sqlite', 'access', "
                "'sqlite-odbc', 'firebird', "
                "'duckdb', 'dbase' or an installed "
                "ODBC driver name"
            )

        if lower == "sqlite":
            return "sqlite", None

        if lower in ODBC_ALIASES:
            return "odbc", lower

        return "odbc", driver

    def drivers(self) -> dict[str, Any]:

        return odbc_driver_report()

    def schema(
        self,
        path: str,
        driver: str | None = None,
        table: str | None = None,
        schema_name: str | None = None,
        max_tables: int = DEFAULT_MAX_TABLES,
        timeout_seconds: int = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:

        target, display = self.resolve(path)

        adapter, driver_alias = self.select_adapter(
            target,
            driver,
        )

        if table is not None:
            table = _clean_name(table, "table")

        if schema_name is not None:
            schema_name = _clean_name(
                schema_name,
                "schema",
            )

        if adapter == "sqlite":

            database = SqliteDatabase(
                target,
                display,
            )

            payload = database.schema(
                table=table,
                max_tables=max_tables,
            )
            payload["adapter"] = "sqlite"

        else:

            database = OdbcDatabase(
                target,
                display,
                driver_alias or "",
            )

            payload = database.schema(
                table=table,
                schema_name=schema_name,
                max_tables=max_tables,
                timeout_seconds=timeout_seconds,
            )
            payload["adapter"] = "odbc"

        payload["success"] = True
        payload["path"] = display

        return payload

    def query(
        self,
        path: str,
        sql: str,
        driver: str | None = None,
        max_rows: int = DEFAULT_ROWS,
        timeout_seconds: int = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:

        target, display = self.resolve(path)

        adapter, driver_alias = self.select_adapter(
            target,
            driver,
        )

        if adapter == "sqlite":

            database = SqliteDatabase(
                target,
                display,
            )

            payload = database.query(
                sql,
                max_rows=max_rows,
                timeout_seconds=timeout_seconds,
            )
            payload["adapter"] = "sqlite"

        else:

            database = OdbcDatabase(
                target,
                display,
                driver_alias or "",
            )

            payload = database.query(
                sql,
                max_rows=max_rows,
                timeout_seconds=timeout_seconds,
            )
            payload["adapter"] = "odbc"

        payload["success"] = True
        payload["path"] = display

        return payload
