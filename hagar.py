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
from core.broker import Broker
from core.config import ConfigError, ConfigLoader
from core.command_service import CommandService
from core.confirmations import QueueConfirmationProvider
from core.dev_recipes import DevRecipeError, DevRecipeLoader
from core.dev_runner import DevExecutionError, DevRunner
from core.boxes import BoxRunner
from core.flow import FlowRunner
from core.decisions import DecisionError
from core.decisions import build_decision_registry
from core.hifi import HiFiResolver
from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.filesystem_tools import FileSystemToolProvider
from local_tools.aish_tool import AishToolProvider
from local_tools.box_tool import BoxToolProvider
from local_tools.dev_tool import DevToolProvider
from local_tools.flow_primitives import FlowPrimitiveProvider
from local_tools.flow_tool import FlowToolProvider
from local_tools.text_transform_tool import TextTransformToolProvider
from core.input_broker import ConsoleInputBroker
from core.models import AppConfig
from core.model_registry import ModelRegistry, ModelRegistryError
from core.task_profile import TaskProfileStore, TaskProfileError
from core.plugins import PluginContext
from core.plugins import load_tool_plugins
from core.service import HarnessService
from core.subagents import SubagentManager
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
from llm.broker_client import BrokerLLMClient
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
from local_tools.decision_tool import DecisionToolProvider
from local_tools.plugins import BUILTIN_TOOL_PLUGINS
from local_tools.vision_tool import VisionToolProvider


__version__ = "0.7.0"

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
        "--hifi",
        action="store_true",
        help=(
            "attiva la modalità Hi-Fi: chiarisce le "
            "interpretazioni prima di rispondere"
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
        "command",
        nargs="?",
        choices=["web"],
        help="avvia la GUI web locale",
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host della GUI web (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="porta della GUI web (default: 8765)",
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
    memory: Any = None
    memory_error: str | None = None
    project_store: ProjectStore | None = None
    project_id: str | None = None
    project_state: dict[str, str | None] | None = None
    subagents: Any = None
    broker: Any = None
    broker_error: str | None = None


def _load_broker(
    config: AppConfig,
    audit: AuditLog,
) -> tuple[Broker | None, str | None]:
    """Carica catalogo e profili, senza rendere il broker obbligatorio."""

    if not config.broker.enabled:
        return None, None

    try:
        broker_registry = ModelRegistry.load(
            config.broker.catalog
        )
        broker_profiles = TaskProfileStore.load(
            config.broker.profiles
        )
        broker_service = Broker(
            broker_registry,
            broker_profiles,
        )
    except (ModelRegistryError, TaskProfileError) as exc:

        error = str(exc)
        audit.record(
            "broker.disabled",
            error=error,
        )
        return None, error

    audit.record(
        "broker.enabled",
        catalog=config.broker.catalog,
        profiles=config.broker.profiles,
        models=len(broker_registry.entries),
        profiles_count=len(broker_profiles.profiles),
    )
    return broker_service, None


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
            agents=getattr(
                config.permissions,
                "agents",
                False,
            ),
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

    memory: Any = None
    memory_error: str | None = None
    project_store: ProjectStore | None = None
    project_state: dict[str, str | None] = {"id": None}

    if config.memory.enabled:

        try:

            if config.memory.backend == "sqlite":

                from memory.sqlite_store import SqliteMemoryStore

                memory = SqliteMemoryStore(
                    session_id=audit.session_id,
                    path=config.memory.database,
                    context_turns=config.memory.context_turns,
                    context_skills=config.memory.context_skills,
                    max_skill_chars=config.memory.max_skill_chars,
                    model=config.model.name,
                )
                memory.ensure()

                audit.record(
                    "memory.enabled",
                    backend="sqlite",
                    path=str(memory.database.path),
                    context_turns=config.memory.context_turns,
                    context_skills=config.memory.context_skills,
                )

            else:

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
                    backend="markdown",
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
                backend=config.memory.backend,
                root=str(config.vault.path),
                error=memory_error,
            )

        if memory is not None:

            try:

                if config.memory.backend == "sqlite":

                    from memory.sqlite_projects import SqliteProjectStore

                    project_store = SqliteProjectStore(
                        memory.database
                    )
                    project_store.ensure()
                    audit.record(
                        "project.enabled",
                        backend="sqlite",
                        path=str(memory.database.path),
                    )

                else:

                    project_store = ProjectStore(
                        vault,
                        subdir=config.memory.vault_subdir,
                    )
                    project_store.ensure()
                    audit.record(
                        "project.enabled",
                        backend="markdown",
                        root=str(config.vault.path),
                    )

            except Exception as exc:

                project_store = None

                audit.record(
                    "project.disabled",
                    backend=config.memory.backend,
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
        agent_id=audit.session_id,
        default_timeout=config.tools.timeout,
        repeat_limit=config.tools.repeat_limit,
    )

    # ==========================================
    # Local filesystem tools
    # ==========================================

    fs_provider = FileSystemToolProvider(
        filesystem
    )

    fs_provider.register_tools(registry)

    AishToolProvider(
        registry,
        filesystem,
        audit=audit,
    ).register_tools(registry)

    TextTransformToolProvider(filesystem).register_tools(registry)

    if config.dev.enabled:

        recipe_path = Path(
            config.dev.recipes
        ).expanduser().resolve()

        for root in filesystem.roots:

            try:
                recipe_path.relative_to(root)
            except ValueError:
                continue

            raise ConfigError(
                "dev.recipes must be outside the sandbox"
            )

        try:
            recipe_book = DevRecipeLoader().load(recipe_path)
        except DevRecipeError as exc:
            raise ConfigError(
                f"cannot load dev recipes: {exc}"
            ) from exc

        dev_runner = DevRunner(
            filesystem,
            recipe_book,
            audit=audit,
            max_output_chars=config.dev.max_output_chars,
            copy_workspace=config.dev.copy_workspace,
        )

        DevToolProvider(
            dev_runner,
            recipe_book,
            audit=audit,
        ).register_tools(registry)

        audit.record(
            "dev.recipes.loaded",
            path=str(recipe_path),
            recipes=len(recipe_book.recipes),
            sha256=recipe_book.sha256,
        )

    vision_provider = VisionToolProvider(filesystem)
    vision_provider.register_tools(registry)

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
    # Local tools (plugin)
    # ==========================================

    subagents = SubagentManager(
        config=config,
        parent_registry=registry,
        audit=audit,
        parent_filesystem=filesystem,
        project_store=project_store,
        project_state=project_state,
        parent_id=audit.session_id,
        max_concurrent=2,
        confirmation=confirmation,
    )

    plugin_failures = load_tool_plugins(
        BUILTIN_TOOL_PLUGINS,
        registry,
        PluginContext(
            config=config,
            audit=audit,
            filesystem=filesystem,
            memory=memory,
            project_store=project_store,
            project_state=project_state,
            subagents=subagents,
        ),
        audit=audit,
    )

    for failure in plugin_failures:
        audit.record(
            "plugin.skipped",
            plugin_group=failure.group,
            plugin=failure.name,
            error=failure.error,
        )

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

    broker_service, broker_error = _load_broker(
        config,
        audit,
    )

    if subagents is not None:
        subagents.broker = broker_service
        subagents.broker_profile = config.broker.default_profile

    try:

        llm = create_llm(
            config.model,
            audit=audit,
        )

        if broker_service is not None:
            llm = BrokerLLMClient(
                broker_service,
                config.model,
                profile=config.broker.default_profile,
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
    # Boxed transforms
    # ==========================================

    box_runner = None

    if config.boxes.enabled:

        box_runner = BoxRunner(
            llm,
            filesystem,
            config.boxes,
            audit=audit,
        )

        BoxToolProvider(
            box_runner
        ).register_tools(registry)

        audit.record(
            "boxes.enabled",
            max_input_chars=config.boxes.max_input_chars,
            max_output_chars=config.boxes.max_output_chars,
            max_calls=config.boxes.max_calls,
        )

    # ==========================================
    # Hagar Flow
    # ==========================================

    if config.flow.enabled:

        primitive_registry = ToolRegistry(
            evaluator=evaluator,
            subject=subject,
            confirmation=(
                confirmation
                or DenyAllConfirmation()
            ),
            audit=audit,
            agent_id=audit.session_id,
            default_timeout=config.flow.timeout,
            repeat_limit=0,
        )

        primitive_provider = FlowPrimitiveProvider(
            filesystem,
            box_runner,
            memory=memory,
            project_store=project_store,
            project_id_getter=lambda: project_state["id"],
        )
        primitive_provider.register_tools(primitive_registry)

        FlowToolProvider(
            FlowRunner(
                primitive_registry,
                config.flow,
                primitive_provider.primitives,
                audit=audit,
            ),
            llm=llm,
        ).register_tools(registry)

        audit.record(
            "flow.enabled",
            primitives=len(primitive_provider.primitives),
            max_steps=config.flow.max_steps,
            max_tool_calls=config.flow.max_tool_calls,
        )

    # ==========================================
    # Decision tools
    # ==========================================

    try:

        decisions = build_decision_registry(config, llm)

        if decisions is not None:

            DecisionToolProvider(
                decisions,
                audit=audit,
            ).register_tools(registry)

            audit.record(
                "decision.enabled",
                providers=decisions.names(),
                default=decisions.default,
            )

    except DecisionError as exc:

        audit.record(
            "decision.disabled",
            error=str(exc),
        )

    # ==========================================
    # Hi-Fi mode
    # ==========================================

    hifi = None

    if config.hifi.enabled:

        hifi = HiFiResolver(
            llm,
            margin=config.hifi.margin,
            interpretations=config.hifi.interpretations,
        )

        audit.record(
            "hifi.enabled",
            margin=config.hifi.margin,
            interpretations=config.hifi.interpretations,
        )

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
        agent_id=audit.session_id,
        hifi=hifi,
        artifact_store=getattr(subagents, "artifacts", None),
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
        subagents=subagents,
        broker=broker_service,
        broker_error=broker_error,
    )


def _load_config(
    args: argparse.Namespace,
) -> AppConfig:

    config = ConfigLoader.load(
        resolve_config(args.config)
    )

    if args.model:
        config.model.name = args.model

    if args.no_memory:
        config.memory.enabled = False

    if args.no_native_tools:
        config.model.native_tools = False

    if getattr(args, "hifi", False):
        config.hifi.enabled = True

    return config


def _run_web(
    args: argparse.Namespace,
) -> None:

    from core.web import serve

    try:

        config = _load_config(args)

        provider = QueueConfirmationProvider(
            timeout=180,
        )

        harness = build_harness(
            config,
            confirmation=provider,
        )

        if args.project:

            project = (
                harness.project_store.get_project(
                    args.project
                )
                if harness.project_store is not None
                else None
            )

            if (
                project is None
                or project.status != "active"
            ):

                raise ValueError(
                    "progetto non trovato o non attivo: "
                    f"{args.project}"
                )

            harness.project_id = project.id

            if harness.project_state is not None:
                harness.project_state["id"] = project.id

            harness.agent.project_id = project.id

        if args.free:
            harness.project_id = None

    except (ConfigError, ValueError) as exc:

        print(f"Errore: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    serve(
        harness,
        provider,
        host=args.host,
        port=args.port,
    )


def _main(
    argv: list[str] | None = None,
) -> None:

    args = build_parser().parse_args(argv)

    if args.command == "web":
        _run_web(args)
        return

    try:

        config = _load_config(args)

        console_confirmation = ConsoleConfirmation()

        harness = build_harness(
            config,
            confirmation=console_confirmation,
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

        stats = (
            harness.memory.stats()
            if hasattr(harness.memory, "stats")
            else {
                "path": str(config.vault.path),
                "backend": "markdown",
            }
        )
        print(
            "Memory:",
            stats.get("path"),
            f"(backend {stats.get('backend', 'sqlite')}, "
            f"contesto {config.memory.context_turns} turni, "
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

    broker = ConsoleInputBroker()
    console_confirmation.broker = broker

    interrupted = False

    try:

        _interactive_loop(
            harness,
            project_cli,
            service,
            broker=broker,
        )

    except KeyboardInterrupt:

        interrupted = True
        raise

    finally:

        try:

            if not interrupted:
                _finish_session(harness, service, broker)

        finally:

            harness.audit.record(
                "harness.stop",
                reason=(
                    "interrupt"
                    if interrupted
                    else "exit"
                ),
            )

            broker.close()


def _set_project(
    harness: Harness,
    project_id: str | None,
) -> None:

    HarnessService(harness).set_project(project_id)


def _finish_session(
    harness: Harness,
    service: HarnessService | None = None,
    broker: ConsoleInputBroker | None = None,
) -> None:

    if service is None:
        service = HarnessService(harness)

    service.finish_session(
        interactive=sys.stdin.isatty(),
        input_func=(
            broker.read_line
            if broker is not None
            else None
        ),
    )


def _interactive_loop(
    harness: Harness,
    project_cli: ProjectCLI | None = None,
    service: HarnessService | None = None,
    broker: ConsoleInputBroker | None = None,
) -> None:

    if service is None:
        service = HarnessService(harness)

    if broker is None:
        broker = ConsoleInputBroker()

    if project_cli is not None:
        project_cli.input_func = broker.read_line

    memory_cli = (
        MemoryCLI(
            harness.memory,
            harness.audit,
            input_func=broker.read_line,
        )
        if harness.memory is not None
        else None
    )

    command_service = CommandService(
        harness,
        service,
    )

    while True:

        try:

            question = broker.read_line("> ")

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

        if stripped.startswith("/"):

            print()

            if (
                stripped == "/memory review"
                or stripped.startswith("/memory review ")
            ):

                if memory_cli is None:
                    print("Memoria disattivata.")
                else:
                    memory_cli.handle(stripped)

            else:

                result = command_service.handle(stripped)

                if result.lines:
                    for line in result.lines:
                        print(line)
                elif result.error:
                    print(result.error)

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
