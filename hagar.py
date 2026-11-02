from __future__ import annotations

import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Callable

from core.agent import Agent
from core.audit import AuditLog
from core.config import ConfigError, ConfigLoader
from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.filesystem_tools import FileSystemToolProvider
from core.models import AppConfig
from core.tool_registry import ToolRegistry
from llm.base import LLMClient
from llm.factory import create_llm
from llm.mcp_client import MCPClient
from memory.vault import Vault

CONFIG_PATH = Path(__file__).with_name("hagar.yaml")


@dataclass(slots=True)
class Harness:
    """
    Componenti del harness, tutti esistenti fuori dalla "mente" del modello.
    """

    config: AppConfig
    filesystem: FileSystemSandbox
    registry: ToolRegistry
    llm: LLMClient
    vault: Vault
    agent: Agent
    audit: AuditLog


def build_harness(
    config: AppConfig,
    mcp_client_factory: Callable[..., Any] = MCPClient,
) -> Harness:
    """
    Costruisce il harness a partire dalla configurazione.

    La funzione non esegue I/O di rete: l'unica eccezione sono i server MCP
    configurati, e il fallimento di un server viene isolato e registrato
    senza impedire l'avvio del resto del harness.

    Ogni scelta di configurazione finisce nell'audit log: provider,
    modello, radici della sandbox, permessi, tool registrati.
    """

    # ==========================================
    # Audit
    # ==========================================

    audit = AuditLog(
        path=config.audit.path,
        max_field_chars=config.audit.max_field_chars,
        enabled=config.audit.enabled,
    )

    # ==========================================
    # Filesystem sandbox
    # ==========================================

    permissions = DirectoryPermissions(
        read=config.permissions.read,
        write=config.permissions.write,
        create=config.permissions.write,
        delete=config.permissions.write,
    )

    sandbox_roots = {
        Path(path): permissions
        for path in config.filesystem.allowed
    }

    filesystem = FileSystemSandbox(
        roots=sandbox_roots,
        current_directory=Path(
            config.filesystem.allowed[0]
        ),
    )

    # ==========================================
    # Registry
    # ==========================================

    registry = ToolRegistry()

    # ==========================================
    # Local filesystem tools
    # ==========================================

    fs_provider = FileSystemToolProvider(
        filesystem
    )

    fs_provider.register_tools(registry)

    # ==========================================
    # MCP servers
    # ==========================================

    mcp_status: list[dict[str, Any]] = []

    for server_cfg in config.mcp_servers:

        before = set(
            registry.tool_names()
        )

        try:

            mcp = mcp_client_factory(
                endpoint=server_cfg.endpoint,
                namespace=server_cfg.namespace,
            )

            mcp.register_tools(registry)

            added = sorted(
                set(registry.tool_names()) - before
            )

            mcp_status.append(
                {
                    "namespace": server_cfg.namespace,
                    "tools": added,
                }
            )

            print(
                "Loaded MCP namespace:",
                server_cfg.namespace,
            )

            audit.record(
                "mcp.loaded",
                namespace=server_cfg.namespace,
                endpoint=server_cfg.endpoint,
                tools=added,
            )

        except Exception as exc:

            print(
                "Failed to load MCP server",
                server_cfg.namespace,
                exc,
            )

            audit.record(
                "mcp.failed",
                namespace=server_cfg.namespace,
                endpoint=server_cfg.endpoint,
                error=str(exc),
            )

    # ==========================================
    # LLM
    # ==========================================

    try:

        llm = create_llm(
            config.model,
            audit=audit,
        )

    except Exception as exc:

        audit.record(
            "llm.failed",
            provider=config.model.provider,
            model=config.model.name,
            error=str(exc),
        )

        raise

    # ==========================================
    # Vault
    # ==========================================

    vault = Vault(
        config.vault.path
    )

    # ==========================================
    # Agent
    # ==========================================

    agent = Agent(
        llm=llm,
        tool_registry=registry,
        vault=vault,
        audit=audit,
    )

    # ==========================================
    # Session header
    # ==========================================

    audit.record(
        "harness.start",
        provider=config.model.provider,
        model=config.model.name,
        workspace=str(
            filesystem.current_directory
        ),
        roots=[
            str(root)
            for root in config.filesystem.allowed
        ],
        permissions={
            "read": config.permissions.read,
            "write": config.permissions.write,
            "shell": config.permissions.shell,
        },
        tools=registry.tool_names(),
        mcp_servers=mcp_status,
        vault=str(config.vault.path),
        audit_path=str(config.audit.path),
    )

    return Harness(
        config=config,
        filesystem=filesystem,
        registry=registry,
        llm=llm,
        vault=vault,
        agent=agent,
        audit=audit,
    )


def main() -> None:

    try:

        config = ConfigLoader.load(CONFIG_PATH)

        harness = build_harness(config)

    except ConfigError as exc:

        print(
            f"Errore di configurazione: {exc}",
            file=sys.stderr,
        )

        raise SystemExit(1) from exc

    # ==========================================
    # Console
    # ==========================================

    print()
    print("Harness ready.")
    print(
        "Model:",
        f"{config.model.provider} / "
        f"{config.model.name}",
    )

    if harness.audit.enabled:

        print(
            "Audit log:",
            harness.audit.path,
        )

    else:

        print("Audit log: disabled")

    print()
    print("Available tools:")

    for tool in harness.registry.tool_names():

        print(f"  - {tool}")

    print()

    try:

        _interactive_loop(harness)

    finally:

        harness.audit.record(
            "harness.stop",
            reason="exit",
        )


def _interactive_loop(harness: Harness) -> None:

    while True:

        try:

            question = input("> ")

        except (EOFError, KeyboardInterrupt):

            print()
            break

        if question.strip().lower() in {
            "exit",
            "quit",
        }:
            break

        if not question.strip():
            continue

        answer = harness.agent.ask(question)

        print()
        print(answer)
        print()


if __name__ == "__main__":
    main()
