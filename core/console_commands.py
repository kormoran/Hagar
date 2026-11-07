"""Comandi di console di Hagar: /help, /tools, /status, /mcp, /audit."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from typing import Callable

from core.audit import read_entries
from core.permissions import capability_names


def _clip(
    value: Any,
    limit: int = 160,
) -> str:

    text = str(value).replace("\n", " ").strip()

    if len(text) <= limit:
        return text

    return text[:limit] + "…"


class ConsoleCommands:
    """Comandi informativi che non passano dal modello."""

    def __init__(
        self,
        harness: Any,
        output: Callable[[str], Any] = print,
    ) -> None:

        self.harness = harness
        self.output = output

    def handle(
        self,
        line: str,
    ) -> bool:

        if not line.startswith("/"):
            return False

        parts = line.split()
        command = parts[0].lower()

        if command in {"/help", "/?"}:

            self._help()

        elif command == "/tools":

            self._tools(parts[1:])

        elif command == "/status":

            self._status()

        elif command == "/mcp":

            self._mcp()

        elif command == "/audit":

            self._audit(parts[1:])

        else:

            self.output(
                f"Comando sconosciuto: {command}. "
                "Usa /help."
            )

        return True

    # ==================================================
    # Help
    # ==================================================

    def _help(self) -> None:

        self.output(
            "Comandi chat:\n"
            "  /help                 questo elenco\n"
            "  /tools [categoria]    tool disponibili e capability\n"
            "  /status               modello, progetto, memoria, audit\n"
            "  /mcp                  server MCP e tool importati\n"
            "  /audit [n]            ultimi n eventi (default 10)\n"
            "  /project ...          gestione progetti\n"
            "  /memory ...           memoria, skill e archivio\n"
            "  exit | quit            esci\n"
            "\n"
            "I tool (filesystem.*, memory.*, mcp.*, ...) sono "
            "chiamati dal modello, non digitati come comandi."
        )

    # ==================================================
    # Tools
    # ==================================================

    def _tools(
        self,
        arguments: list[str],
    ) -> None:

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

        if not definitions:

            self.output("Nessun tool disponibile.")
            return

        grouped: dict[str, list[Any]] = defaultdict(list)

        for tool in definitions:

            grouped[tool.category].append(tool)

        self.output(f"Tool disponibili: {len(definitions)}")

        for name in sorted(grouped):

            self.output(f"\n[{name}]")

            for tool in sorted(
                grouped[name],
                key=lambda item: item.name,
            ):

                capabilities = ", ".join(
                    capability_names(tool.capabilities)
                ) or "-"

                self.output(
                    f"  {tool.name}  ({capabilities})"
                )

    # ==================================================
    # Status
    # ==================================================

    def _status(self) -> None:

        config = self.harness.config
        audit = self.harness.audit

        self.output(
            f"Sessione: {getattr(audit, 'session_id', '-')}"
        )
        self.output(
            f"Modello: {config.model.provider} / "
            f"{config.model.name}"
        )

        native = bool(
            getattr(
                self.harness.llm,
                "supports_native_tools",
                False,
            )
            and getattr(
                self.harness.llm,
                "native_tools",
                False,
            )
        )

        self.output(
            "Calling: "
            + ("nativo" if native else "JSON testuale")
        )

        project_id = getattr(
            self.harness,
            "project_id",
            None,
        )
        projects = getattr(
            self.harness,
            "project_store",
            None,
        )

        if project_id and projects is not None:

            project = projects.get_project(project_id)

            if project is not None:

                self.output(
                    f"Progetto: {project.title} "
                    f"[{project.id}] "
                    f"({project.active_decisions} decisioni attive)"
                )

            else:

                self.output(
                    f"Progetto: {project_id} (non trovato)"
                )

        else:

            self.output("Progetto: attività libera")

        policy_error = getattr(
            self.harness,
            "policy_error",
            None,
        )

        self.output(
            f"Policy: {config.policy.path} "
            f"(subject: {config.policy.subject})"
        )

        if policy_error:

            self.output(
                f"Policy error: {_clip(policy_error)}"
            )

        memory = getattr(self.harness, "memory", None)

        if memory is None:

            self.output("Memoria: disattivata")

        elif hasattr(memory, "stats"):

            stats = memory.stats()
            self.output(
                f"Memoria: SQLite {stats.get('path')}"
            )
            self.output(
                f"  sessioni={stats.get('sessions', 0)}; "
                f"turni={stats.get('turns', 0)}; "
                f"skill={stats.get('skills', 0)}; "
                f"summary={stats.get('summaries', 0)}"
            )

        else:

            counts = {}

            for status in sorted(memory.STATUSES):

                counts[status] = len(
                    memory.list_skills(
                        status=status,
                        limit=1000,
                    )
                )

            chat_files = len(
                memory.vault.list_files(
                    memory.chat_dir,
                    "*.md",
                )
            )
            summaries = len(
                memory.vault.list_files(
                    memory.summaries_dir,
                    "*.md",
                )
            )
            archived = len(
                memory.vault.list_files(
                    memory.archive_chat_dir,
                    "*.md",
                )
            )

            self.output(
                f"Memoria: {config.vault.path} "
                f"(subdir {config.memory.vault_subdir})"
            )
            self.output(
                "  skill: "
                + ", ".join(
                    f"{status}={count}"
                    for status, count in counts.items()
                )
                + f"; chat={chat_files}; "
                f"summary={summaries}; archivio={archived}"
            )

        self.output(
            f"Audit: {audit.path} "
            + ("attivo" if audit.enabled else "disattivato")
        )

        filesystem = getattr(
            self.harness,
            "filesystem",
            None,
        )

        if filesystem is not None:

            self.output(
                f"Filesystem: {filesystem.current_directory} "
                f"({len(filesystem.aliases)} alias)"
            )

    # ==================================================
    # MCP
    # ==================================================

    def _mcp(self) -> None:

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

        if not servers and not definitions:

            self.output("Nessun server MCP configurato.")
            return

        grouped: dict[str, list[Any]] = defaultdict(list)

        for tool in definitions:

            namespace = tool.origin.removeprefix("mcp.")

            grouped[namespace].append(tool)

        self.output(
            f"Server MCP configurati: {len(servers)}; "
            f"tool importati: {len(definitions)}"
        )

        for server in servers:

            count = len(grouped.get(server.namespace, []))

            self.output(
                f"\n[{server.namespace}] {server.endpoint}"
            )
            self.output(f"  tool: {count}")

            if count == 0:

                self.output(
                    "  nessun tool: caricamento fallito o "
                    "server senza tool"
                )

            else:

                for tool in sorted(
                    grouped[server.namespace],
                    key=lambda item: item.name,
                ):

                    self.output(f"  - {tool.name}")

        orphan = sorted(
            set(grouped) - {
                server.namespace
                for server in servers
            }
        )

        for namespace in orphan:

            self.output(
                f"\n[{namespace}] tool senza configurazione corrente"
            )

    # ==================================================
    # Audit
    # ==================================================

    def _audit(
        self,
        arguments: list[str],
    ) -> None:

        try:

            limit = (
                int(arguments[0])
                if arguments
                else 10
            )

        except ValueError:

            self.output("Uso: /audit [numero]")
            return

        limit = max(1, min(limit, 50))
        audit = self.harness.audit

        if not audit.enabled:

            self.output("Audit disattivato.")
            return

        try:

            entries = read_entries(audit.path)

        except (OSError, ValueError) as exc:

            self.output(
                f"Audit non leggibile: {_clip(exc)}"
            )
            return

        if not entries:

            self.output("Audit vuoto.")
            return

        self.output(
            f"Ultimi {min(limit, len(entries))} eventi "
            f"({audit.path}):"
        )

        for entry in entries[-limit:]:

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
                        f"{key}={_clip(entry[key], 80)}"
                    )

            self.output("  " + " ".join(parts))
