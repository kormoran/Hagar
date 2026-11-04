"""Comandi `/memory` per la console.

La revisione è volutamente umana: l'LLM può proporre skill candidate, ma
non può promuoverle. I comandi lavorano direttamente sul vault.
"""

from __future__ import annotations

from typing import Any
from typing import Callable

from memory.store import MemoryError
from memory.store import MemoryStore
from memory.store import Skill


def _clip(
    text: str,
    limit: int,
) -> str:

    text = text.strip()

    if len(text) <= limit:
        return text

    return text[:limit] + "…"


class MemoryCLI:
    def __init__(
        self,
        store: MemoryStore,
        audit: Any = None,
        input_func: Callable[[str], str] | None = None,
        output_func: Callable[[str], Any] | None = None,
    ) -> None:

        self.store = store
        self.audit = audit
        self.input_func = input_func or input
        self.output = output_func or print

    # ==================================================
    # Entry point
    # ==================================================

    def handle(
        self,
        line: str,
    ) -> bool:

        parts = line.strip().split()

        if not parts or parts[0].lower() != "/memory":
            return False

        arguments = parts[1:]

        command = (
            arguments[0].lower()
            if arguments
            else "help"
        )

        try:

            if command in {"help", "?"}:

                self._help()

            elif command == "list":

                self._list(arguments[1:])

            elif command == "show":

                self._show(arguments[1:])

            elif command == "confirm":

                self._set_status(
                    arguments[1:],
                    "confirmed",
                    "confirm",
                )

            elif command == "archive":

                self._archive(arguments[1:])

            elif command == "review":

                self._review()

            else:

                self.output(
                    f"Comando memoria sconosciuto: {command}"
                )

                self._help()

        except MemoryError as exc:

            self.output(f"Memoria: {exc}")

        return True

    # ==================================================
    # Archivio
    # ==================================================

    def _archive(
        self,
        arguments: list[str],
    ) -> None:

        if not arguments:

            self.output(
                "Uso: /memory archive <slug> "
                "oppure /memory archive search|read ..."
            )
            return

        subcommand = arguments[0].lower()

        if subcommand == "search":

            self._archive_search(arguments[1:])

        elif subcommand == "read":

            self._archive_read(arguments[1:])

        else:

            self._set_status(
                arguments,
                "archived",
                "archive",
            )

    def _archive_search(
        self,
        arguments: list[str],
    ) -> None:

        query = " ".join(arguments).strip()

        if not query:

            self.output(
                "Uso: /memory archive search <testo>"
            )
            return

        results, total = self.store.search_archive(
            query,
            limit=10,
        )

        if not results:

            self.output(
                f"Nessun risultato nell'archivio per: {query}"
            )
            return

        self.output(
            f"Archivio: {len(results)} di {total} risultati"
        )

        for item in results:

            project = (
                f" · progetto {item['project']}"
                if item.get("project")
                else ""
            )

            self.output("")
            self.output(
                f"[{item['session']} · {item['turn']}] "
                f"{item['timestamp']}{project}"
            )
            self.output(
                f"Utente: {_clip(item['question'], 300)}"
            )
            self.output(
                f"Hagar: {_clip(item['answer'], 500)}"
            )

        if total > len(results):

            self.output("")
            self.output(
                "Altri risultati disponibili: "
                "restringi la ricerca."
            )

    def _archive_read(
        self,
        arguments: list[str],
    ) -> None:

        if not arguments:

            self.output(
                "Uso: /memory archive read <session> "
                "[offset] [limit]"
            )
            return

        session = arguments[0]

        try:

            offset = (
                int(arguments[1])
                if len(arguments) > 1
                else 0
            )
            limit = (
                int(arguments[2])
                if len(arguments) > 2
                else 20
            )

        except ValueError as exc:

            raise MemoryError(
                "offset e limit devono essere numeri"
            ) from exc

        payload = self.store.read_archive(
            session,
            offset=offset,
            limit=limit,
        )

        if payload is None:

            self.output(
                f"Sessione archiviata non trovata: {session}"
            )
            return

        project = (
            f" · progetto {payload['project']}"
            if payload.get("project")
            else ""
        )

        self.output(
            f"Archivio sessione {payload['session']}"
            f"{project} — "
            f"{payload['total_turns']} turni"
        )

        for turn in payload["turns"]:

            self.output("")
            self.output(
                f"[{turn['timestamp']} · {turn['turn']}]"
            )
            self.output(f"Utente: {turn['question']}")
            self.output(f"Hagar: {turn['answer']}")

        if payload["has_more"]:

            self.output("")
            self.output(
                "Per continuare: /memory archive read "
                f"{payload['session']} "
                f"{payload['next_offset']} {payload['limit']}"
            )

    # ==================================================
    # Comandi
    # ==================================================

    def _help(self) -> None:

        self.output(
            "Comandi memoria:\n"
            "  /memory list [candidate|confirmed|archived]\n"
            "  /memory show <slug>\n"
            "  /memory review\n"
            "  /memory confirm <slug>\n"
            "  /memory archive <slug>\n"
            "  /memory archive search <testo>\n"
            "  /memory archive read <session> [offset] [limit]"
        )

    def _counts(self) -> dict[str, int]:

        return {
            status: len(
                self.store.list_skills(
                    status=status,
                    limit=1000,
                )
            )
            for status in sorted(
                MemoryStore.STATUSES
            )
        }

    def _list(
        self,
        arguments: list[str],
    ) -> None:

        counts = self._counts()

        self.output(
            "Memoria: "
            + ", ".join(
                f"{status}={count}"
                for status, count in counts.items()
            )
        )

        status = (
            arguments[0].lower()
            if arguments
            else "candidate"
        )

        if status not in MemoryStore.STATUSES:

            raise MemoryError(
                "stato non valido: "
                f"{status}"
            )

        skills = self.store.list_skills(
            status=status,
            limit=1000,
        )

        if not skills:

            self.output(
                f"Nessuna skill in stato {status}."
            )

            return

        for skill in skills:

            self.output(
                f"[{skill.id}] {skill.title} "
                f"({skill.kind}) — {skill.created_at}"
            )

    def _show(
        self,
        arguments: list[str],
    ) -> None:

        if not arguments:

            self.output(
                "Uso: /memory show <slug>"
            )

            return

        skill = self.store.get_skill(arguments[0])

        if skill is None:

            self.output(
                f"Skill non trovata: {arguments[0]}"
            )

            return

        self.output(self._details(skill))

    def _set_status(
        self,
        arguments: list[str],
        status: str,
        action: str,
    ) -> None:

        if not arguments:

            self.output(
                f"Uso: /memory {action} <slug>"
            )

            return

        slug = arguments[0]

        before = self.store.get_skill(slug)

        if before is None:

            raise MemoryError(
                f"skill non trovata: {slug}"
            )

        skill = self.store.set_skill_status(
            slug,
            status,
        )

        self._record(
            "memory.status",
            skill=slug,
            **{
                "from": before.status,
                "to": skill.status,
            },
        )

        self.output(
            f"Skill {skill.id}: {skill.status}"
        )

    def _review(self) -> None:

        queue = self.store.review_queue()

        if not queue:

            self.output("Nessuna skill candidata.")
            return

        self.output(
            f"{len(queue)} skill candidate da rivedere."
        )

        for index, skill in enumerate(queue, 1):

            self.output("")
            self.output(
                f"[{index}/{len(queue)}] "
                f"{skill.id} — {skill.title}"
            )

            self.output(
                f"kind: {skill.kind} | "
                f"tags: {', '.join(skill.tags) or '-'} | "
                f"origine: {skill.source_session or '-'}"
                f"/{skill.source_turn or '-'} | "
                f"modello: {skill.model or '-'}"
            )

            self.output(
                f"creata: {skill.created_at}"
            )

            self.output("---")
            self.output(_clip(skill.content, 1200))
            self.output("---")

            try:

                answer = self.input_func(
                    "Confermi? "
                    "(y/N/a=archivia/s=salta/q=esci) "
                )

            except (EOFError, KeyboardInterrupt):

                self.output("")
                break

            answer = answer.strip().lower()

            if answer in {"q", "quit", "esci"}:

                break

            if answer in {"y", "yes", "si", "sì"}:

                updated = self.store.set_skill_status(
                    skill.id,
                    "confirmed",
                )

                self._record(
                    "memory.review",
                    skill=skill.id,
                    action="confirm",
                    status=updated.status,
                )

                self.output(
                    f"Confermata: {skill.id}"
                )

            elif answer in {"a", "archivia", "archivio"}:

                updated = self.store.set_skill_status(
                    skill.id,
                    "archived",
                )

                self._record(
                    "memory.review",
                    skill=skill.id,
                    action="archive",
                    status=updated.status,
                )

                self.output(
                    f"Archiviata: {skill.id}"
                )

            elif answer in {"s", "salta", "skip"}:

                self.output(
                    f"Saltata: {skill.id}"
                )

            elif answer in {"", "n", "no"}:

                self.output(
                    f"Lasciata candidata: {skill.id}"
                )

            else:

                self.output(
                    "Risposta non valida: "
                    f"resta candidata ({skill.id})"
                )

        counts = self._counts()

        self.output(
            "\nRiepilogo: "
            + ", ".join(
                f"{status}={count}"
                for status, count in counts.items()
            )
        )

    # ==================================================
    # Utility
    # ==================================================

    @staticmethod
    def _details(skill: Skill) -> str:

        return (
            f"id: {skill.id}\n"
            f"title: {skill.title}\n"
            f"status: {skill.status}\n"
            f"kind: {skill.kind}\n"
            f"tags: {', '.join(skill.tags) or '-'}\n"
            f"created_at: {skill.created_at}\n"
            f"source: {skill.source_session or '-'}"
            f"/{skill.source_turn or '-'}\n"
            f"model: {skill.model or '-'}\n"
            f"path: {skill.path}\n"
            "---\n"
            f"{skill.content}"
        )

    def _record(
        self,
        event: str,
        **fields: Any,
    ) -> None:

        if self.audit is None:
            return

        try:

            self.audit.record(event, **fields)

        except Exception:

            pass
