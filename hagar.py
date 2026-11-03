from __future__ import annotations

import argparse
import os
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
from core.permissions import (
    ConfirmationProvider,
    ConsoleConfirmation,
    DenyAllConfirmation,
    PermissionEvaluator,
    PolicyError,
    PolicySet,
    capabilities_from_permissions,
    load_policies,
)
from core.tool_registry import ToolRegistry
from llm.base import LLMClient
from llm.factory import create_llm
from llm.mcp_client import (
    MCPClient,
    resolve_auth_headers,
)
from llm.mcp_oauth import OAuthProvider
from memory.store import MemoryError, MemoryStore
from memory.tools import MemoryToolProvider
from memory.vault import Vault

__version__ = "0.2.0"

DEFAULT_CONFIG_NAME = "hagar.yaml"


def resolve_config(
    explicit: str | None = None,
) -> Path:
    """
    Ordine di ricerca della configurazione:

        1. --config
        2. variabile HAGAR_CONFIG
        3. ./hagar.yaml nella directory corrente
    """

    if explicit:
        return Path(explicit).expanduser()

    from_env = os.environ.get(
        "HAGAR_CONFIG",
        "",
    ).strip()

    if from_env:
        return Path(from_env).expanduser()

    return Path.cwd() / DEFAULT_CONFIG_NAME


def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        prog="hagar",
        description=(
            "Harness agentico generale "
            "per AI resilienti."
        ),
    )

    parser.add_argument(
        "--config",
        metavar="PATH",
        help=(
            "file di configurazione "
            "(default: ./hagar.yaml)"
        ),
    )

    parser.add_argument(
        "--model",
        metavar="NAME",
        help="sovrascrive model.name",
    )

    parser.add_argument(
        "--no-memory",
        action="store_true",
        help=(
            "disattiva la memoria "
            "per questa sessione"
        ),
    )

    parser.add_argument(
        "--no-native-tools",
        action="store_true",
        help=(
            "usa il protocollo JSON testuale "
            "invece del calling nativo"
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"hagar {__version__}",
    )

    return parser


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
    policy: PolicySet
    policy_error: str | None = None
    memory: MemoryStore | None = None
    memory_error: str | None = None


def build_harness(
    config: AppConfig,
    mcp_client_factory: Callable[..., Any] = MCPClient,
    confirmation: ConfirmationProvider | None = None,
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
        max_bytes=config.audit.max_bytes,
        include_outputs=config.audit.include_outputs,
        max_files=config.audit.max_files,
    )

    # ==========================================
    # Policy
    #
    # Le policy si leggono prima di costruire qualunque LLM. Un errore
    # non ferma il harness: si degrada a DENY totale (fail closed) e si
    # registra il motivo.
    # ==========================================

    policy_error: str | None = None

    try:

        policies = load_policies(
            config.policy.path
        )

        audit.record(
            "policy.loaded",
            path=str(config.policy.path),
            subjects=sorted(policies.subjects),
        )

    except PolicyError as exc:

        policies = PolicySet.deny_all()
        policy_error = str(exc)

        audit.record(
            "policy.failed",
            path=str(config.policy.path),
            error=policy_error,
            fallback="deny-all",
        )

    if (
        policy_error is None
        and config.policy.subject not in policies.subjects
    ):

        policy_error = (
            f"subject '{config.policy.subject}' "
            f"not found in {config.policy.path}"
        )

        audit.record(
            "policy.subject_missing",
            path=str(config.policy.path),
            subject=config.policy.subject,
        )

    subject = policies.get(
        config.policy.subject
    )

    evaluator = PermissionEvaluator(
        ceiling=capabilities_from_permissions(
            read=config.permissions.read,
            write=config.permissions.write,
            shell=config.permissions.shell,
        )
    )

    # ==========================================
    # Vault e memoria
    #
    # Prima del registry: i tool di memoria vengono registrati insieme a
    # quelli del filesystem. Un vault assente o non scrivibile non ferma
    # il harness, disattiva solo la memoria.
    # ==========================================

    vault = Vault(config.vault.path)

    memory: MemoryStore | None = None
    memory_error: str | None = None

    if config.memory.enabled:

        try:

            if not vault.exists():

                raise MemoryError(
                    f"Vault not found: {config.vault.path}"
                )

            memory = MemoryStore(
                vault,
                session_id=audit.session_id,
                subdir=config.memory.vault_subdir,
                context_turns=config.memory.context_turns,
                max_skill_chars=config.memory.max_skill_chars,
                model=config.model.name,
            )

            memory.ensure()

            audit.record(
                "memory.enabled",
                root=str(config.vault.path),
                subdir=config.memory.vault_subdir,
                context_turns=config.memory.context_turns,
            )

        except Exception as exc:

            memory = None
            memory_error = str(exc)

            audit.record(
                "memory.disabled",
                root=str(config.vault.path),
                error=memory_error,
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

    registry = ToolRegistry(
        evaluator=evaluator,
        subject=subject,
        confirmation=(
            confirmation
            or DenyAllConfirmation()
        ),
        audit=audit,
    )

    # ==========================================
    # Local filesystem tools
    # ==========================================

    fs_provider = FileSystemToolProvider(
        filesystem
    )

    fs_provider.register_tools(registry)

    # ==========================================
    # Memory tools
    # ==========================================

    if memory is not None:

        memory_provider = MemoryToolProvider(
            memory
        )

        memory_provider.register_tools(registry)

    # ==========================================
    # MCP servers
    # ==========================================

    mcp_status: list[dict[str, Any]] = []

    for server_cfg in config.mcp_servers:

        before = set(
            registry.tool_names()
        )

        try:

            kwargs: dict[str, Any] = {
                "endpoint": server_cfg.endpoint,
                "namespace": server_cfg.namespace,
            }

            if server_cfg.auth is not None:

                if server_cfg.auth.type == "oauth":

                    if server_cfg.auth.oauth is None:

                        raise ValueError(
                            "OAuth configuration missing "
                            f"for MCP namespace "
                            f"'{server_cfg.namespace}'"
                        )

                    kwargs["token_provider"] = OAuthProvider(
                        server_cfg.auth.oauth,
                        resource_url=server_cfg.endpoint,
                        server_name=server_cfg.namespace,
                    )

                else:

                    kwargs["headers"] = resolve_auth_headers(
                        server_cfg.auth
                    )

            mcp = mcp_client_factory(**kwargs)

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
    # Agent
    # ==========================================

    agent = Agent(
        llm=llm,
        tool_registry=registry,
        vault=vault,
        audit=audit,
        memory=memory,
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
        policy={
            "path": str(config.policy.path),
            "subject": config.policy.subject,
            "error": policy_error,
        },
        memory={
            "enabled": memory is not None,
            "root": str(config.vault.path),
            "subdir": config.memory.vault_subdir,
            "error": memory_error,
        },
    )

    return Harness(
        config=config,
        filesystem=filesystem,
        registry=registry,
        llm=llm,
        vault=vault,
        agent=agent,
        audit=audit,
        policy=policies,
        policy_error=policy_error,
        memory=memory,
        memory_error=memory_error,
    )


def main(
    argv: list[str] | None = None,
) -> None:

    args = build_parser().parse_args(argv)

    config_path = resolve_config(args.config)

    try:

        config = ConfigLoader.load(config_path)

        if args.model:
            config.model.name = args.model

        if args.no_memory:
            config.memory.enabled = False

        if args.no_native_tools:
            config.model.native_tools = False

        harness = build_harness(
            config,
            confirmation=ConsoleConfirmation(),
        )

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

    if harness.policy_error:

        print("Policy: DENY ALL")
        print(
            "ATTENZIONE: policy non valida:",
            harness.policy_error,
        )
        print(
            "Nessun tool verra' eseguito "
            "finche' le policy non sono valide."
        )

    else:

        print(
            "Policy:",
            config.policy.path,
            f"(subject: {config.policy.subject})",
        )

    if harness.memory is not None:

        print(
            "Memory:",
            config.vault.path,
            f"(contesto {config.memory.context_turns} turni)",
        )

    elif config.memory.enabled and harness.memory_error:

        print("Memory: disabled —", harness.memory_error)

    else:

        print("Memory: disabled")

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
