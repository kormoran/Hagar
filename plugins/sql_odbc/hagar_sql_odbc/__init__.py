"""Plugin SQL ODBC con scrittura per Hagar.

Il plugin è volutamente ODBC-only: SQLite nativo resta nel tool
built-in ``sql.file.*``. Ogni percorso deve stare nella sandbox e non
può essere il database delle memorie di Hagar.
"""

from __future__ import annotations

from core.plugins import (
    PluginContext,
    ToolPlugin,
)

from local_tools.sql_file import (
    SqlFileReader,
    memory_database_paths,
)

from .tools import SqlOdbcToolProvider


VERSION = "1.0.0"


def register(
    registry,
    context: PluginContext,
) -> None:
    """Registra i tool SQL ODBC nel registry dell'host."""

    if context.filesystem is None:
        return

    reader = SqlFileReader(
        context.filesystem,
        forbidden_paths=memory_database_paths(
            context.config,
            context.memory,
        ),
    )

    SqlOdbcToolProvider(reader).register_tools(
        registry
    )


PLUGIN = ToolPlugin(
    name="sql-odbc",
    version=VERSION,
    register=register,
)


__all__ = [
    "PLUGIN",
    "VERSION",
    "SqlOdbcToolProvider",
    "register",
]
