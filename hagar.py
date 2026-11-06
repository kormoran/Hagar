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
from core.console_commands import ConsoleCommands
from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.filesystem_tools import FileSystemToolProvider
from core.models import AppConfig
from core.service import HarnessService
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
from memory.cli import MemoryCLI
from memory.projects import ProjectStore
from memory.project_cli import ProjectCLI
from memory.project_tools import ProjectToolProvider
from memory.store import MemoryError, MemoryStore
from memory.tools import MemoryToolProvider
from memory.vault import Vault
from local_tools.calculator import Calculator
from local_tools.clock import Clock
from local_tools.clock_tool import ClockToolProvider
from local_tools.calendar import Calendar
from local_tools.calendar_tool import CalendarToolProvider
from local_tools.feeder import Feeder
from local_tools.statistics import Stats_calc
from local_tools.think import Think
from local_tools.think_tool import ThinkToolProvider
from local_tools.text_diff import TextDiff
from local_tools.text_diff_tool import TextDiffToolProvider
from local_tools.url_parse import UrlParser
from local_tools.url_parse_tool import UrlParseToolProvider
from local_tools.unit_converter import UnitConverter
from local_tools.math_tools import MathToolsProvider
from local_tools.unit_converter_tool import UnitConverterToolProvider
from local_tools.feeder_tool import FeederToolProvider


__version__ = "0.3.0"

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

    project_group = parser.add_mutually_exclusive_group()

    project_group.add_argument(
        "--project",
        metavar="NAME",
        help="seleziona un progetto attivo all'avvio",
    )

    project_group.add_argument(
        "--free",
        action="store_true",
        help="avvia in attività libera, senza progetto",
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
    project_store: ProjectStore | None = None
    project_id: str | None = None
    project_state: dict[str, str | None] | None = None


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
            network=config.permissions.network,
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
    project_store: ProjectStore | None = None
    project_state: dict[str, str | None] = {"id": None}

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
                context_skills=config.memory.context_skills,
                max_skill_chars=config.memory.max_skill_chars,
                model=config.model.name,
            )

            memory.ensure()

            audit.record(
                "memory.enabled",
                root=str(config.vault.path),
                subdir=config.memory.vault_subdir,
                context_turns=config.memory.context_turns,
                context_skills=config.memory.context_skills,
            )

        except Exception as exc:

            memory = None
            project_store = None
            memory_error = str(exc)

            audit.record(
                "memory.disabled",
                root=str(config.vault.path),
                error=memory_error,
            )

        if memory is not None:

            try:

                project_store = ProjectStore(
                    vault,
                    subdir=config.memory.vault_subdir,
                )
                project_store.ensure()

                audit.record(
                    "project.enabled",
                    root=str(config.vault.path),
                )

            except Exception as exc:

                project_store = None

                audit.record(
                    "project.disabled",
                    root=str(config.vault.path),
                    error=str(exc),
                )

    # ==========================================
    # Filesystem sandbox
    # ==========================================

    sandbox_roots: dict[Path, DirectoryPermissions] = {}
    sandbox_aliases: dict[str, Path] = {}

    for mount in config.filesystem.sandbox:

        mount_path = mount.path.expanduser().resolve()

        if not mount_path.is_dir():

            raise ConfigError(
                f"filesystem.sandbox path is not a "
                f"directory: {mount.path}"
            )

        if mount_path in sandbox_roots:

            raise ConfigError(
                "filesystem.sandbox has duplicate path: "
                f"{mount.path}"
            )

        sandbox_roots[mount_path] = DirectoryPermissions(
            read=("R" in mount.permissions)
            and config.permissions.read,
            write=("W" in mount.permissions)
            and config.permissions.write,
            create=("W" in mount.permissions)
            and config.permissions.write,
            rename=("W" in mount.permissions)
            and config.permissions.write,
            delete=("W" in mount.permissions)
            and config.permissions.write,
            execute=("X" in mount.permissions),
        )

        sandbox_aliases[mount.alias] = mount_path

    filesystem = FileSystemSandbox(
        roots=sandbox_roots,
        current_directory=next(iter(sandbox_roots)),
        aliases=sandbox_aliases,
        limits=config.filesystem.limits,
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

        if project_store is not None:

            ProjectToolProvider(
                project_store,
                lambda: project_state["id"],
            ).register_tools(registry)

    # ==========================================
    # Local tools (non-MCP)
    # ==========================================

    unit_conversions = UnitConverterToolProvider(
        UnitConverter()
    )

    unit_conversions.register_tools(registry)

    ClockToolProvider(
        Clock()
    ).register_tools(registry)

    CalendarToolProvider(
        Calendar()
    ).register_tools(registry)

    ThinkToolProvider(
        Think()
    ).register_tools(registry)

    TextDiffToolProvider(
        TextDiff()
    ).register_tools(registry)

    UrlParseToolProvider(
        UrlParser()
    ).register_tools(registry)

    math_tools = MathToolsProvider(
        Calculator(),
        Stats_calc(),
    )

    math_tools.register_tools(registry)

    feed_reader = FeederToolProvider(
        Feeder()
    )

    feed_reader.register_tools(registry)

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
        project_store=project_store,
        project_id=None,
        max_context_chars=config.memory.max_context_chars,
        context_project_memories=(
            config.memory.context_project_memories
        ),
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
            str(mount.path)
            for mount in config.filesystem.sandbox
        ],
        sandbox=[
            {
                "alias": mount.alias,
                "permissions": mount.permissions,
            }
            for mount in config.filesystem.sandbox
        ],
        permissions={
            "read": config.permissions.read,
            "write": config.permissions.write,
            "shell": config.permissions.shell,
            "network": config.permissions.network,
        },
        filesystem_limits={
            "max_write_bytes": (
                config.filesystem.limits.max_write_bytes
            ),
            "min_free_bytes": (
                config.filesystem.limits.min_free_bytes
            ),
            "session_write_bytes": (
                config.filesystem.limits.session_write_bytes
            ),
            "ask_over_bytes": (
                config.filesystem.limits.ask_over_bytes
            ),
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
        project_store=project_store,
        project_id=None,
        project_state=project_state,
    )


def _main(
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

    service = HarnessService(harness)

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
            f"(contesto {config.memory.context_turns} turni, "
            f"{config.memory.context_skills} skill)",
        )

    elif config.memory.enabled and harness.memory_error:

        print("Memory: disabled —", harness.memory_error)

    else:

        print("Memory: disabled")

    if harness.memory is not None:

        if getattr(harness, "project_store", None) is not None:

            print("Projects: enabled")

        else:

            print(
                "Projects: disabled "
                "(directory projects non scrivibile)"
            )

    print()

    project_cli: ProjectCLI | None = None

    if getattr(harness, "project_store", None) is not None:

        project_cli = ProjectCLI(
            harness.project_store,
            lambda: harness.project_id,
            service.set_project,
            max_active=(
                config.memory.project_max_active
            ),
            interactive=sys.stdin.isatty(),
            audit=harness.audit,
        )

        try:

            project_cli.choose_initial(
                forced=args.project,
                free=(
                    args.free
                    or (
                        not sys.stdin.isatty()
                        and not args.project
                    )
                ),
            )

        except ValueError as exc:

            print(
                f"Errore progetto: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc

    print()
    print("Available tools:")

    for tool in harness.registry.tool_names():

        print(f"  - {tool}")

    print()

    try:

        _interactive_loop(
            harness,
            project_cli,
            service,
        )

    finally:

        _finish_session(harness, service)

        harness.audit.record(
            "harness.stop",
            reason="exit",
        )


def _set_project(
    harness: Harness,
    project_id: str | None,
) -> None:

    HarnessService(harness).set_project(project_id)


def _finish_session(
    harness: Harness,
    service: HarnessService | None = None,
) -> None:

    if service is None:
        service = HarnessService(harness)

    service.finish_session(
        interactive=sys.stdin.isatty(),
    )


def _interactive_loop(
    harness: Harness,
    project_cli: ProjectCLI | None = None,
    service: HarnessService | None = None,
) -> None:

    if service is None:
        service = HarnessService(harness)

    memory_cli = (
        MemoryCLI(
            harness.memory,
            harness.audit,
        )
        if harness.memory is not None
        else None
    )

    console_commands = ConsoleCommands(harness)

    while True:

        try:

            question = input("> ")

        except (EOFError, KeyboardInterrupt):

            print()
            break

        stripped = question.strip()

        if stripped.lower() in {
            "exit",
            "quit",
        }:
            break

        if not stripped:
            continue

        if (
            stripped == "/project"
            or stripped.startswith("/project ")
        ):

            if project_cli is None:

                print()
                print("Progetti disattivati: memoria assente.")
                print()

            else:

                project_cli.handle(stripped)
                print()

            continue

        if (
            stripped == "/memory"
            or stripped.startswith("/memory ")
        ):

            if memory_cli is None:

                print()
                print("Memoria disattivata.")
                print()

            else:

                memory_cli.handle(stripped)
                print()

            continue

        if console_commands.handle(stripped):

            print()
            continue

        answer = service.ask(question)

        print()
        print(answer)
        print()


def main(
    argv: list[str] | None = None,
) -> None:
    """Entry point con uscita pulita su Ctrl-C."""

    try:

        _main(argv)

    except KeyboardInterrupt:

        print(
            "\nOperazione interrotta.",
            file=sys.stderr,
        )

        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
