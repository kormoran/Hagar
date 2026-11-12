"""Comandi di console come servizio strutturato, senza input/stdout."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.audit import read_entries
from core.broker import BrokerError
from core.hardware import detect_hardware
from core.model_bench import benchmark_model
from core.model_cards import ModelCardError
from core.model_cards import ModelCardStore
from core.permissions import capability_names
from core.service import HarnessService
from memory.export import MarkdownExporter
from memory.import_markdown import MarkdownImporter
from memory.projects import ProjectError


@dataclass(frozen=True)
class CommandResult:
    """Risultato di un comando: dati + eventuale testo per la CLI."""

    command: str
    ok: bool = True
    lines: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    requires_input: bool = False


class CommandService:
    """Esegue i comandi slash senza conoscere la console."""

    def __init__(
        self,
        harness: Any,
        service: HarnessService,
        model_cards: ModelCardStore | None = None,
        broker: Any = None,
        default_profile: str | None = None,
    ) -> None:

        self.harness = harness
        self.service = service
        self.model_cards = model_cards or ModelCardStore()
        self.broker = (
            broker
            if broker is not None
            else getattr(harness, "broker", None)
        )
        configured_broker = getattr(
            getattr(harness, "config", None),
            "broker",
            None,
        )

        if default_profile is None and configured_broker is not None:
            default_profile = configured_broker.default_profile

        self.default_profile = default_profile or "coding"

    def handle(
        self,
        line: str,
    ) -> CommandResult:

        stripped = line.strip()

        if not stripped.startswith("/"):
            return CommandResult(
                command=stripped,
                ok=False,
                error="not a slash command",
            )

        parts = stripped.split()
        command = parts[0].lower()
        arguments = parts[1:]

        if command in {"/help", "/?"}:

            return self._help()

        if command == "/tools":

            return self._tools(arguments)

        if command == "/status":

            return self._status()

        if command == "/usage":

            return self._usage()

        if command == "/mcp":

            return self._mcp()

        if command == "/audit":

            return self._audit(arguments)

        if command == "/project":

            return self._project(arguments)

        if command == "/memory":

            return self._memory(arguments)

        if command == "/models":

            return self._models(arguments)

        if command == "/undo":

            return self._undo()

        return CommandResult(
            command=command,
            ok=False,
            error=f"unknown command: {command}",
            lines=[
                f"Comando sconosciuto: {command}. Usa /help."
            ],
        )

    # ==================================================
    # Help
    # ==================================================

    def _help(self) -> CommandResult:

        lines = [
            "Comandi chat:",
            "  /help                 questo elenco",
            "  /tools [categoria]    tool disponibili e capability",
            "  /status               modello, progetto, memoria, audit",
            "  /usage                token consumati nella sessione",
            "  /mcp                  server MCP e tool importati",
            "  /audit [n]            ultimi n eventi",
            "  /project ...          gestione progetti",
            "  /memory ...           memoria, skill e archivio",
            "  /models ...           schede, benchmark e scelta modello",
            "  /undo                 annulla le modifiche dell'ultimo turno",
            "  exit | quit            esci",
            "",
            "I tool sono chiamati dal modello, non digitati come comandi.",
        ]

        return CommandResult(
            command="/help",
            lines=lines,
            data={"commands": lines},
        )

    # ==================================================
    # Undo
    # ==================================================

    def _undo(self) -> CommandResult:

        filesystem = getattr(self.harness, "filesystem", None)

        if filesystem is None:
            return CommandResult(
                command="/undo",
                ok=False,
                error="filesystem unavailable",
                lines=["Filesystem non disponibile."],
            )

        status = filesystem.checkpoint_status()

        if status is None:
            return CommandResult(
                command="/undo",
                ok=False,
                error="no checkpoint",
                lines=["Nessun turno da annullare."],
            )

        try:
            restored = filesystem.rollback_last_checkpoint()

        except Exception as exc:

            return CommandResult(
                command="/undo",
                ok=False,
                error=str(exc),
                lines=[f"Undo non riuscito: {exc}"],
            )

        audit = getattr(self.harness, "audit", None)

        if audit is not None:
            audit.record(
                "workspace.undo",
                checkpoint=status["checkpoint_id"],
                files=status["files"],
                restored=restored,
            )

        return CommandResult(
            command="/undo",
            lines=[
                f"Undo completato: {restored} file ripristinati.",
                f"Checkpoint: {status['checkpoint_id']}",
            ],
            data={
                "checkpoint": status,
                "restored": restored,
            },
        )

    # ==================================================
    # Model cards / benchmarks
    # ==================================================

    def _models(self, arguments: list[str]) -> CommandResult:

        action = arguments[0].lower() if arguments else "list"

        if action in {"list", "ls"}:

            cards = self.model_cards.list()
            lines = [f"Modelli provati: {len(cards)}"]

            for card in cards:
                lines.append(
                    f"  {card.get('provider')}/{card.get('model')} "
                    f"— ultima prova: "
                    f"{card.get('last_tested_at', 'mai')}"
                )

            return CommandResult(
                command="/models list",
                lines=lines,
                data={"cards": cards},
            )

        if action == "hardware":

            info = detect_hardware()
            cpu = info["cpu"]
            memory = info["memory"]
            lines = [
                f"Sistema: {info['platform']} {info['release']} "
                f"({info['machine']})",
                f"CPU: {cpu.get('model') or 'sconosciuta'}",
                f"Core: {cpu.get('physical_cores') or '?'} fisici / "
                f"{cpu.get('logical_cores') or '?'} logici",
                f"Clock: {cpu.get('ghz_current') or '?'} GHz "
                f"(max {cpu.get('ghz_max') or '?'} GHz)",
                f"RAM: {memory.get('total_gib') or '?'} GiB "
                f"(disponibile {memory.get('available_gib') or '?'} GiB)",
            ]

            if not info["gpus"]:
                lines.append("GPU: non rilevata")
            else:
                for gpu in info["gpus"]:
                    vram = gpu.get("vram_bytes")
                    lines.append(
                        f"GPU: {gpu.get('name') or '?'} "
                        f"({gpu.get('vendor') or '?'}, "
                        f"{round(vram / (1024 ** 3), 2) if vram else '?'} GiB, "
                        f"{gpu.get('api') or '?'})"
                    )

            return CommandResult(
                command="/models hardware",
                lines=lines,
                data=info,
            )

        if action == "show":

            target = arguments[1:]

            if len(target) == 1 and "/" in target[0]:
                provider, model = target[0].split("/", 1)
            elif len(target) >= 2:
                provider, model = target[0], " ".join(target[1:])
            else:
                return CommandResult(
                    command="/models show",
                    ok=False,
                    error="missing model",
                    lines=["Uso: /models show <provider> <model>"],
                )

            card = self.model_cards.load(provider, model)

            if card is None:
                return CommandResult(
                    command="/models show",
                    ok=False,
                    error="model card not found",
                    lines=[f"Scheda non trovata: {provider}/{model}"],
                )

            return CommandResult(
                command="/models show",
                lines=[
                    f"{card.get('provider')}/{card.get('model')}",
                    f"Ultima prova: {card.get('last_tested_at')}",
                    f"Capabilities: {card.get('capabilities')}",
                    f"Benchmarks: {card.get('benchmarks')}",
                ],
                data=card,
            )

        if action in {"test", "benchmark"}:

            llm = getattr(self.harness, "llm", None)

            if llm is None:
                return CommandResult(
                    command="/models test",
                    ok=False,
                    error="LLM unavailable",
                    lines=["Nessun modello LLM disponibile."],
                )

            try:
                report = benchmark_model(llm)
                report["last_tested_at"] = report["tested_at"]
                path = self.model_cards.save(report)

            except Exception as exc:

                return CommandResult(
                    command="/models test",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore benchmark: {exc}"],
                )

            chat = report["benchmarks"]["chat"]
            structured = report["benchmarks"]["structured"]
            tools = report["benchmarks"]["tool_call"]
            lines = [
                f"Modello: {report['provider']}/{report['model']}",
                f"Scheda: {path}",
                f"Chat: {chat['successes']}/{chat['attempts']} "
                f"(p50 {chat['duration_ms']['p50']} ms)",
                f"JSON: {structured['valid_json']}/"
                f"{structured['attempts']} "
                f"(choice {structured['valid_choice']})",
                f"Tool: {tools['successes']}/{tools['attempts']}",
                f"Ultima prova: {report['last_tested_at']}",
            ]

            audit = getattr(self.harness, "audit", None)
            if audit is not None:
                audit.record(
                    "model.tested",
                    provider=report["provider"],
                    model=report["model"],
                    card=str(path),
                    chat_p50_ms=chat["duration_ms"]["p50"],
                    structured_valid=structured["valid_json"],
                    tool_successes=tools["successes"],
                )

            return CommandResult(
                command="/models test",
                lines=lines,
                data=report,
            )

        if action in {"route", "explain"}:

            if self.broker is None:

                detail = getattr(
                    self.harness,
                    "broker_error",
                    None,
                )
                lines = [
                    "Broker non configurato: "
                    "abilita broker.enabled e crea "
                    "models.yaml e profiles.yaml."
                ]

                if detail:
                    lines.append(f"Dettaglio: {detail}")

                return CommandResult(
                    command=f"/models {action}",
                    ok=False,
                    error="broker not configured",
                    lines=lines,
                )

            profile = (
                arguments[1]
                if len(arguments) > 1
                else self.default_profile
            )

            try:

                if action == "explain":

                    report = self.broker.explain(profile)
                    selected = report.get("selected")
                    lines = [
                        f"Profilo: {profile}",
                    ]

                    if selected is None:
                        lines.append("Nessun modello eleggibile.")
                    else:
                        lines.append(
                            f"Scelto: {selected['model_id']} "
                            f"(score {selected['score']:.4f})"
                        )

                    lines.append(
                        f"Esclusi: {len(report['excluded'])}"
                    )

                    for item in report["excluded"]:
                        lines.append(
                            f"  {item['model_id']}: "
                            + "; ".join(item["reasons"])
                        )

                    return CommandResult(
                        command="/models explain",
                        lines=lines,
                        data=report,
                    )

                selection = self.broker.select(profile)
                lines = [
                    f"Profilo: {profile}",
                    f"Modello: {selection.entry.id}",
                    f"Provider: {selection.entry.provider}",
                    f"Modello provider: {selection.entry.model}",
                    f"Score: {selection.score:.4f}",
                    "Motivi:",
                ]

                for reason in selection.reasons:
                    lines.append(f"  - {reason}")

                return CommandResult(
                    command="/models route",
                    lines=lines,
                    data=selection.as_dict(),
                )

            except BrokerError as exc:

                return CommandResult(
                    command=f"/models {action}",
                    ok=False,
                    error=str(exc),
                    lines=[
                        str(exc),
                        *[
                            f"  {item['model_id']}: "
                            + "; ".join(item["reasons"])
                            for item in exc.excluded
                        ],
                    ],
                    data={"excluded": exc.excluded},
                )

        return CommandResult(
            command="/models",
            ok=False,
            error="unknown models action",
            lines=[
                "Uso: /models "
                "[list|show|test|hardware|route|explain]",
            ],
        )

    # ==================================================
    # Tools
    # ==================================================

    def _tools(
        self,
        arguments: list[str],
    ) -> CommandResult:

        definitions = (
            self.harness.registry.list_definitions()
        )

        category = (
            arguments[0].casefold()
            if arguments
            else None
        )

        if category:

            definitions = [
                tool
                for tool in definitions
                if tool.category.casefold() == category
            ]

        categories: dict[str, list[dict[str, Any]]] = {}

        for tool in sorted(
            definitions,
            key=lambda item: (item.category, item.name),
        ):

            categories.setdefault(
                tool.category,
                [],
            ).append(
                {
                    "name": tool.name,
                    "capabilities": capability_names(
                        tool.capabilities
                    ),
                    "requires_confirmation": (
                        tool.requires_confirmation
                    ),
                }
            )

        lines = [f"Tool disponibili: {len(definitions)}"]

        for name in sorted(categories):

            lines.append("")
            lines.append(f"[{name}]")

            for tool in categories[name]:

                capabilities = ", ".join(
                    tool["capabilities"]
                ) or "-"

                lines.append(
                    f"  {tool['name']}  ({capabilities})"
                )

        return CommandResult(
            command="/tools",
            lines=lines,
            data={
                "count": len(definitions),
                "categories": categories,
            },
        )

    # ==================================================
    # Status
    # ==================================================

    def _status(self) -> CommandResult:

        status = self.service.status()
        project = status.get("project")
        memory = status.get("memory") or {}

        lines = [
            f"Sessione: {status.get('session_id') or '-'}",
            (
                f"Modello: {status['model']['provider']} / "
                f"{status['model']['name']}"
            ),
        ]

        if project:

            lines.append(
                f"Progetto: {project['title']} "
                f"[{project['id']}] "
                f"({project['active_decisions']} decisioni attive)"
            )

        else:

            lines.append("Progetto: attività libera")

        if memory.get("enabled"):

            lines.append(
                f"Memoria: {memory.get('vault')} "
                f"(subdir {memory.get('subdir')})"
            )

        else:

            lines.append("Memoria: disattivata")

        audit = status.get("audit") or {}

        lines.append(
            f"Audit: {audit.get('path')} "
            + (
                "attivo"
                if audit.get("enabled")
                else "disattivato"
            )
        )

        return CommandResult(
            command="/status",
            lines=lines,
            data=status,
        )

    # ==================================================
    # Usage
    # ==================================================

    def _usage(self) -> CommandResult:

        usage = self.service.usage.snapshot()

        lines = [
            f"Token sessione: {usage['total_tokens']}",
            (
                f"  input: {usage['input_tokens']} · "
                f"output: {usage['output_tokens']}"
            ),
        ]

        if usage["cached_input_tokens"]:
            lines.append(
                f"  cached input: {usage['cached_input_tokens']}"
            )

        if usage["reasoning_tokens"]:
            lines.append(
                f"  reasoning: {usage['reasoning_tokens']}"
            )

        lines.append(f"  chiamate LLM: {usage['calls']}")

        return CommandResult(
            command="/usage",
            lines=lines,
            data=usage,
        )

    # ==================================================
    # MCP
    # ==================================================

    def _mcp(self) -> CommandResult:

        definitions = [
            tool
            for tool in self.harness.registry.list_definitions()
            if tool.origin.startswith("mcp.")
        ]

        servers = getattr(
            self.harness.config,
            "mcp_servers",
            [],
        )

        grouped: dict[str, list[str]] = {}

        for tool in definitions:

            namespace = tool.origin.removeprefix("mcp.")
            grouped.setdefault(namespace, []).append(
                tool.name
            )

        lines = [
            f"Server MCP configurati: {len(servers)}; "
            f"tool importati: {len(definitions)}"
        ]

        data_servers = []

        for server in servers:

            tools = sorted(
                grouped.get(server.namespace, [])
            )

            lines.append(
                f"\n[{server.namespace}] {server.endpoint}"
            )
            lines.append(f"  tool: {len(tools)}")

            for name in tools:
                lines.append(f"  - {name}")

            data_servers.append(
                {
                    "namespace": server.namespace,
                    "endpoint": server.endpoint,
                    "tools": tools,
                }
            )

        return CommandResult(
            command="/mcp",
            lines=lines,
            data={"servers": data_servers},
        )

    # ==================================================
    # Audit
    # ==================================================

    def _audit(
        self,
        arguments: list[str],
    ) -> CommandResult:

        try:

            limit = (
                int(arguments[0])
                if arguments
                else 10
            )

        except ValueError:

            return CommandResult(
                command="/audit",
                ok=False,
                error="invalid limit",
                lines=["Uso: /audit [numero]"],
            )

        limit = max(1, min(limit, 50))
        audit = self.harness.audit

        if not audit.enabled:

            return CommandResult(
                command="/audit",
                ok=False,
                error="audit disabled",
                lines=["Audit disattivato."],
            )

        try:

            entries = read_entries(audit.path)

        except (OSError, ValueError) as exc:

            return CommandResult(
                command="/audit",
                ok=False,
                error=str(exc),
                lines=[f"Audit non leggibile: {exc}"],
            )

        selected = entries[-limit:]
        lines = [
            f"Ultimi {len(selected)} eventi ({audit.path}):"
        ]

        for entry in selected:

            parts = [
                str(entry.get("ts", "")),
                str(entry.get("event", "?")),
            ]

            for key in (
                "turn",
                "tool",
                "namespace",
                "effect",
                "status",
                "error",
            ):

                if key in entry and entry[key] not in {
                    None,
                    "",
                }:

                    parts.append(
                        f"{key}={entry[key]}"
                    )

            lines.append("  " + " ".join(parts))

        return CommandResult(
            command="/audit",
            lines=lines,
            data={"entries": selected},
        )

    # ==================================================
    # Project
    # ==================================================

    def _project(
        self,
        arguments: list[str],
    ) -> CommandResult:

        command = (
            arguments[0].lower()
            if arguments
            else "list"
        )

        if command in {"list", "ls"}:

            projects = self.service.list_projects()
            current = self.service.project_id

            lines = ["Progetti attivi:"]

            if not projects:
                lines.append("  (nessuno)")

            for project in projects:

                marker = (
                    "*"
                    if project["id"] == current
                    else " "
                )

                lines.append(
                    f" {marker} {project['title']} "
                    f"[{project['id']}] "
                    f"({project['active_decisions']} "
                    "decisioni attive)"
                )

            lines.append("  attività libera")

            return CommandResult(
                command="/project list",
                lines=lines,
                data={
                    "projects": projects,
                    "current": current,
                },
            )

        if command == "new":

            name = " ".join(arguments[1:]).strip()

            if not name:

                return CommandResult(
                    command="/project new",
                    ok=False,
                    error="missing project name",
                    lines=["Uso: /project new <nome>"],
                )

            try:

                project = self.service.create_project(name)

            except (ProjectError, ValueError) as exc:

                return CommandResult(
                    command="/project new",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore: {exc}"],
                )

            return CommandResult(
                command="/project new",
                lines=[
                    f"Progetto creato: {project['title']} "
                    f"[{project['id']}]"
                ],
                data={"project": project},
            )

        if command in {"select", "use"}:

            if len(arguments) < 2:

                return CommandResult(
                    command="/project select",
                    ok=False,
                    error="missing project id",
                    lines=["Uso: /project select <id>"],
                )

            try:

                self.service.set_project(arguments[1])

            except ProjectError as exc:

                return CommandResult(
                    command="/project select",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore: {exc}"],
                )

            return CommandResult(
                command="/project select",
                lines=[
                    f"Progetto selezionato: {arguments[1]}"
                ],
                data={"project": self.service.current_project()},
            )

        if command in {"free", "none"}:

            self.service.clear_project()

            return CommandResult(
                command="/project free",
                lines=[
                    "Attività libera: nessuna memoria di progetto."
                ],
                data={"project": None},
            )

        if command in {"status", "current"}:

            project = self.service.current_project()

            if project is None:

                lines = ["Progetto attivo: attività libera"]

            else:

                lines = [
                    f"Progetto attivo: {project['title']} "
                    f"[{project['id']}]"
                ]

            return CommandResult(
                command="/project status",
                lines=lines,
                data={"project": project},
            )

        if command in {"archive", "unarchive"}:

            if len(arguments) < 2:

                return CommandResult(
                    command=f"/project {command}",
                    ok=False,
                    error="missing project id",
                    lines=[
                        f"Uso: /project {command} <id>"
                    ],
                )

            project_id = arguments[1]
            store = getattr(
                self.harness,
                "project_store",
                None,
            )

            if store is None:

                return CommandResult(
                    command=f"/project {command}",
                    ok=False,
                    error="projects disabled",
                    lines=["Progetti disattivati."],
                )

            project = store.get_project(project_id)

            if project is None:

                return CommandResult(
                    command=f"/project {command}",
                    ok=False,
                    error="project not found",
                    lines=[
                        f"Progetto non trovato: {project_id}"
                    ],
                )

            try:

                updated = store.set_project_status(
                    project.id,
                    (
                        "archived"
                        if command == "archive"
                        else "active"
                    ),
                )

            except ProjectError as exc:

                return CommandResult(
                    command=f"/project {command}",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore: {exc}"],
                )

            if (
                command == "archive"
                and self.service.project_id == project.id
            ):

                self.service.clear_project()

            return CommandResult(
                command=f"/project {command}",
                lines=[
                    (
                        "Progetto archiviato."
                        if command == "archive"
                        else "Progetto riattivato."
                    )
                ],
                data={"project": {
                    "id": updated.id,
                    "title": updated.title,
                    "status": updated.status,
                    "active_decisions": (
                        updated.active_decisions
                    ),
                }},
            )

        return CommandResult(
            command="/project",
            ok=False,
            error=f"comando progetto sconosciuto: {command}",
            lines=[
                f"Comando progetto sconosciuto: {command}"
            ],
        )

    # ==================================================
    # Memory
    # ==================================================

    def _memory(
        self,
        arguments: list[str],
    ) -> CommandResult:

        memory = getattr(self.harness, "memory", None)

        if memory is None:

            return CommandResult(
                command="/memory",
                ok=False,
                error="memory disabled",
                lines=["Memoria disattivata."],
            )

        command = (
            arguments[0].lower()
            if arguments
            else "help"
        )

        if command in {"help", "?"}:

            return CommandResult(
                command="/memory help",
                lines=[
                    "Comandi memoria:",
                    "  /memory list [status]",
                    "  /memory show <slug>",
                    "  /memory search <testo>",
                    "  /memory sessions",
                    "  /memory chat <session>",
                    "  /memory reindex",
                    "  /memory stats",
                    "  /memory backup <path>",
                    "  /memory export <path> [--force]",
                    "  /memory import <path> [--force]",
                    "  /memory confirm <slug>",
                    "  /memory archive <slug>",
                    "  /memory archive search <testo>",
                    "  /memory archive read <session> [offset] [limit]",
                    "  /memory review",
                ],
                data={"statuses": sorted(memory.STATUSES)},
            )

        if command == "list":

            status = (
                arguments[1]
                if len(arguments) > 1
                else None
            )

            try:

                skills = memory.list_skills(
                    status=status,
                    limit=1000,
                )

            except Exception as exc:

                return CommandResult(
                    command="/memory list",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore: {exc}"],
                )

            counts = {
                name: len(memory.list_skills(
                    status=name,
                    limit=1000,
                ))
                for name in sorted(memory.STATUSES)
            }

            lines = [
                "Memoria: "
                + ", ".join(
                    f"{key}={value}"
                    for key, value in counts.items()
                )
            ]

            for skill in skills:

                lines.append(
                    f"  {skill.id}  {skill.title} "
                    f"[{skill.status}]"
                )

            return CommandResult(
                command="/memory list",
                lines=lines,
                data={
                    "counts": counts,
                    "skills": [
                        skill.summary()
                        for skill in skills
                    ],
                },
            )

        if command == "search":

            query = " ".join(arguments[1:]).strip()

            if not query:

                return CommandResult(
                    command="/memory search",
                    ok=False,
                    error="missing query",
                    lines=["Uso: /memory search <testo>"],
                )

            try:

                results = memory.index.search(
                    query,
                    limit=20,
                )

            except Exception as exc:

                return CommandResult(
                    command="/memory search",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore indice: {exc}"],
                )

            lines = [
                f"Risultati indice: {len(results)}"
            ]

            for result in results:

                lines.append(
                    f"  [{result['kind']}] "
                    f"{result['title']} "
                    f"({result['path']})"
                )

            return CommandResult(
                command="/memory search",
                lines=lines,
                data={"query": query, "results": results},
            )

        if command == "reindex":

            try:

                changed = memory.index.rebuild()

            except Exception as exc:

                return CommandResult(
                    command="/memory reindex",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore indice: {exc}"],
                )

            return CommandResult(
                command="/memory reindex",
                lines=[
                    (
                        "Indici SQLite ottimizzati."
                        if hasattr(memory, "database")
                        else f"Indice ricostruito: {changed} documenti."
                    )
                ],
                data={"changed": changed},
            )

        if command == "sessions":

            sessions = memory.list_sessions(limit=50)
            lines = [f"Chat: {len(sessions)}"]

            for session in sessions:
                lines.append(
                    f"  {session['id']}  {session['title']} "
                    f"({session['turns']} turni"
                    + (", archiviata" if session["archived"] else "")
                    + ")"
                )

            return CommandResult(
                command="/memory sessions",
                lines=lines,
                data={"sessions": sessions},
            )

        if command == "chat":

            if len(arguments) < 2:
                return CommandResult(
                    command="/memory chat",
                    ok=False,
                    error="missing session id",
                    lines=["Uso: /memory chat <session>"],
                )

            session = arguments[1]
            turns = memory.read_session(session)

            if not turns:
                return CommandResult(
                    command="/memory chat",
                    ok=False,
                    error="chat not found",
                    lines=[f"Chat non trovata: {session}"],
                )

            lines = [f"Chat {session}: {len(turns)} turni"]

            for turn in turns:
                lines.append(
                    f"  [{turn['timestamp']}] {turn['turn']}"
                )
                lines.append(
                    f"    U: {turn['question'][:300]}"
                )
                lines.append(
                    f"    H: {turn['answer'][:300]}"
                )

            return CommandResult(
                command="/memory chat",
                lines=lines,
                data={"session": session, "turns": turns},
            )

        if command == "backup":

            if len(arguments) < 2:
                return CommandResult(
                    command="/memory backup",
                    ok=False,
                    error="missing path",
                    lines=["Uso: /memory backup <path>"],
                )

            database = getattr(memory, "database", None)

            if database is None:
                return CommandResult(
                    command="/memory backup",
                    ok=False,
                    error="backup only for sqlite backend",
                    lines=["Il backup è disponibile solo con backend SQLite."],
                )

            target = database.backup(arguments[1])

            return CommandResult(
                command="/memory backup",
                lines=[f"Backup: {target}"],
                data={"path": str(target)},
            )

        if command == "export":

            arguments = arguments[1:]
            force = "--force" in arguments
            path_parts = [
                item for item in arguments
                if item != "--force"
            ]
            path = " ".join(path_parts).strip()

            if not path:
                return CommandResult(
                    command="/memory export",
                    ok=False,
                    error="missing path",
                    lines=[
                        "Uso: /memory export <path> [--force]"
                    ],
                )

            try:

                result = MarkdownExporter(
                    memory,
                    getattr(self.harness, "project_store", None),
                    path,
                ).export(force=force)

            except Exception as exc:

                return CommandResult(
                    command="/memory export",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore export: {exc}"],
                )

            return CommandResult(
                command="/memory export",
                lines=[
                    f"Export Markdown: {result['files']} file",
                    f"Destinazione: {result['root']}",
                ],
                data=result,
            )

        if command == "import":

            arguments = arguments[1:]
            replace = "--force" in arguments
            path_parts = [
                item for item in arguments
                if item != "--force"
            ]
            path = " ".join(path_parts).strip()

            if not path:
                return CommandResult(
                    command="/memory import",
                    ok=False,
                    error="missing path",
                    lines=[
                        "Uso: /memory import <path> [--force]"
                    ],
                )

            database = getattr(memory, "database", None)

            if database is None:
                return CommandResult(
                    command="/memory import",
                    ok=False,
                    error="import only for sqlite backend",
                    lines=[
                        "L'import è disponibile solo con backend SQLite."
                    ],
                )

            try:

                result = MarkdownImporter(
                    database,
                    path,
                    replace=replace,
                ).run()

            except Exception as exc:

                return CommandResult(
                    command="/memory import",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore import: {exc}"],
                )

            return CommandResult(
                command="/memory import",
                lines=[
                    f"Import Markdown: {result['source']}",
                    (
                        f"chat={result['sessions']} "
                        f"turni={result['turns']} "
                        f"skill={result['skills']} "
                        f"summary={result['summaries']} "
                        f"progetti={result['projects']} "
                        f"decisioni={result['decisions']} "
                        f"skipped={result['skipped']}"
                    ),
                ],
                data=result,
            )

        if command == "stats":

            try:

                stats = memory.index.stats()

            except Exception as exc:

                return CommandResult(
                    command="/memory stats",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore indice: {exc}"],
                )

            if "documents" in stats:

                lines = [
                    f"Indice: {stats['documents']} documenti",
                    f"File: {stats['path']}",
                    f"FTS5: {'sì' if stats.get('fts') else 'no'}",
                ]

            else:

                lines = [
                    f"Backend: {stats.get('backend', 'sqlite')}",
                    f"File: {stats.get('path')}",
                    f"Sessioni: {stats.get('sessions', 0)}",
                    f"Turni: {stats.get('turns', 0)}",
                    f"Skill: {stats.get('skills', 0)}",
                    f"Summary: {stats.get('summaries', 0)}",
                ]

            return CommandResult(
                command="/memory stats",
                lines=lines,
                data=stats,
            )

        if command == "show":

            if len(arguments) < 2:

                return CommandResult(
                    command="/memory show",
                    ok=False,
                    error="missing skill slug",
                    lines=["Uso: /memory show <slug>"],
                )

            skill = memory.get_skill(arguments[1])

            if skill is None:

                return CommandResult(
                    command="/memory show",
                    ok=False,
                    error="skill not found",
                    lines=[
                        f"Skill non trovata: {arguments[1]}"
                    ],
                )

            return CommandResult(
                command="/memory show",
                lines=[
                    f"{skill.title} [{skill.id}]",
                    f"stato: {skill.status}",
                    "",
                    skill.content,
                ],
                data={
                    "skill": skill.summary(),
                    "content": skill.content,
                },
            )

        if command == "archive" and arguments[1:2] == ["search"]:

            return self._archive_search(
                memory,
                arguments[2:],
            )

        if command == "archive" and arguments[1:2] == ["read"]:

            return self._archive_read(
                memory,
                arguments[2:],
            )

        if command in {"confirm", "archive"}:

            if len(arguments) < 2:

                return CommandResult(
                    command=f"/memory {command}",
                    ok=False,
                    error="missing skill slug",
                    lines=[
                        f"Uso: /memory {command} <slug>"
                    ],
                )

            status = (
                "confirmed"
                if command == "confirm"
                else "archived"
            )

            try:

                skill = memory.set_skill_status(
                    arguments[1],
                    status,
                )

            except Exception as exc:

                return CommandResult(
                    command=f"/memory {command}",
                    ok=False,
                    error=str(exc),
                    lines=[f"Errore: {exc}"],
                )

            return CommandResult(
                command=f"/memory {command}",
                lines=[
                    f"{skill.title}: {skill.status}"
                ],
                data={"skill": skill.summary()},
            )

        if command == "review":

            return CommandResult(
                command="/memory review",
                ok=False,
                error="interactive review requires a console",
                requires_input=True,
                lines=[
                    "La review interattiva richiede la console."
                ],
            )

        return CommandResult(
            command="/memory",
            ok=False,
            error=f"unknown memory command: {command}",
            lines=[
                f"Comando memoria sconosciuto: {command}"
            ],
        )

    def _archive_search(
        self,
        memory: Any,
        arguments: list[str],
    ) -> CommandResult:

        query = " ".join(arguments).strip()

        if not query:

            return CommandResult(
                command="/memory archive search",
                ok=False,
                error="missing query",
                lines=[
                    "Uso: /memory archive search <testo>"
                ],
            )

        hits, total = memory.search_archive(query)

        lines = [
            f"Risultati archivio: {len(hits)} di {total}"
        ]

        for hit in hits:

            lines.append(
                f"  {hit.get('date', '')} "
                f"{hit.get('session', '')} "
                f"{hit.get('turn', '')}: "
                f"{hit.get('question', '')}"
            )

        return CommandResult(
            command="/memory archive search",
            lines=lines,
            data={
                "query": query,
                "hits": hits,
                "total": total,
            },
        )

    def _archive_read(
        self,
        memory: Any,
        arguments: list[str],
    ) -> CommandResult:

        if not arguments:

            return CommandResult(
                command="/memory archive read",
                ok=False,
                error="missing session",
                lines=[
                    "Uso: /memory archive read "
                    "<session> [offset] [limit]"
                ],
            )

        session = arguments[0]

        try:

            offset = int(arguments[1]) if len(arguments) > 1 else 0
            limit = int(arguments[2]) if len(arguments) > 2 else 20

        except ValueError:

            return CommandResult(
                command="/memory archive read",
                ok=False,
                error="offset/limit must be integers",
                lines=[
                    "Uso: /memory archive read "
                    "<session> [offset] [limit]"
                ],
            )

        turns_result = memory.read_archive(
            session,
            offset=offset,
            limit=limit,
        )

        if turns_result is None:

            return CommandResult(
                command="/memory archive read",
                ok=False,
                error="archive session not found",
                lines=[
                    f"Archivio non trovato: {session}"
                ],
            )

        turns = turns_result.get("turns", [])
        total = turns_result.get("total_turns", 0)

        lines = [
            f"Archivio {session}: {len(turns)} di {total}"
        ]

        for turn in turns:

            lines.append(
                f"  {turn.get('timestamp', '')} "
                f"{turn.get('turn', '')}: "
                f"{turn.get('question', '')}"
            )

        return CommandResult(
            command="/memory archive read",
            lines=lines,
            data=turns_result,
        )
