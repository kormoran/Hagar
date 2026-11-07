"""Comandi di console come servizio strutturato, senza input/stdout."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.audit import read_entries
from core.permissions import capability_names
from core.service import HarnessService
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
    ) -> None:

        self.harness = harness
        self.service = service

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

        if command == "/mcp":

            return self._mcp()

        if command == "/audit":

            return self._audit(arguments)

        if command == "/project":

            return self._project(arguments)

        if command == "/memory":

            return self._memory(arguments)

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
            "  /mcp                  server MCP e tool importati",
            "  /audit [n]            ultimi n eventi",
            "  /project ...          gestione progetti",
            "  /memory ...           memoria, skill e archivio",
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
