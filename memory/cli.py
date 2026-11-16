"""Comandi `/memory` per la console.

La revisione è volutamente umana: l'LLM può proporre skill candidate, ma
non può promuoverle. I comandi lavorano direttamente sul vault.
"""

from __future__ import annotations

from typing import Any
from typing import Callable

from memory.consolidate import apply_skill_retention
from memory.consolidate import find_duplicate_skills
from memory.consolidate import merge_skills
from memory.consolidate import retention_candidates
from memory.embeddings import EmbeddingError
from memory.store import MemoryError
from memory.store import MemoryStore
from memory.store import Skill
from memory.vector_index import MemoryEmbeddingIndex


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
        max_active_skills: int = 0,
        embedding_index: MemoryEmbeddingIndex | None = None,
    ) -> None:

        self.store = store
        self.audit = audit
        self.input_func = input_func or input
        self.output = output_func or print
        self.max_active_skills = max(0, int(max_active_skills))
        self.embedding_index = embedding_index

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

            elif command == "duplicates":

                self._duplicates(arguments[1:])

            elif command == "merge":

                self._merge(arguments[1:])

            elif command == "retention":

                self._retention(arguments[1:])

            elif command == "embeddings":

                self._embeddings(arguments[1:])

            else:

                self.output(
                    f"Comando memoria sconosciuto: {command}"
                )

                self._help()

        except (MemoryError, EmbeddingError) as exc:

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
            "  /memory archive read <session> [offset] [limit]\n"
            "  /memory duplicates [soglia]\n"
            "  /memory merge <target> <fonte> [...]\n"
            "  /memory retention [apply]\n"
            "  /memory embeddings [status|reindex|search <testo>]"
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

    def _duplicates(
        self,
        arguments: list[str],
    ) -> None:

        threshold = 0.70

        if arguments:

            try:
                threshold = float(arguments[0])

            except ValueError as exc:

                raise MemoryError(
                    "la soglia deve essere un numero tra 0 e 1"
                ) from exc

        groups = find_duplicate_skills(
            self.store,
            threshold=threshold,
        )

        if not groups:

            self.output(
                "Nessuna coppia di skill simile "
                f"(soglia {threshold:.2f})."
            )
            return

        self.output(
            f"Gruppi di skill simili: {len(groups)} "
            f"(soglia {threshold:.2f})"
        )

        for index, group in enumerate(groups, start=1):

            self.output("")
            self.output(
                f"[{index}] target: {group.target.id} "
                f"— {group.target.title} "
                f"({group.target.status}, {group.score:.2f})"
            )

            for duplicate in group.duplicates:

                self.output(
                    f"    - {duplicate.id} — {duplicate.title} "
                    f"({duplicate.status})"
                )

        self.output("")
        self.output(
            "Unisci con: /memory merge <target> <fonte> [...]"
        )

    def _merge(
        self,
        arguments: list[str],
    ) -> None:

        if len(arguments) < 2:

            self.output(
                "Uso: /memory merge <target> <fonte> [...]"
            )
            return

        target = arguments[0]
        sources = arguments[1:]
        merged = merge_skills(
            self.store,
            target,
            sources,
        )

        self._record(
            "memory.merge",
            target=merged.id,
            sources=sources,
            content_chars=len(merged.content),
        )

        self.output(
            f"Skill {merged.id} consolidata; "
            f"fonti archiviate: {', '.join(sources)}"
        )

    def _retention(
        self,
        arguments: list[str],
    ) -> None:

        apply = bool(arguments) and arguments[0].lower() in {
            "apply",
            "applica",
            "archivia",
        }

        if self.max_active_skills <= 0:

            self.output(
                "Retention skill disattivata "
                "(memory.max_active_skills: 0)."
            )
            return

        confirmed = self.store.list_skills(
            status="confirmed",
            limit=10000,
        )
        candidates = retention_candidates(
            self.store,
            self.max_active_skills,
        )

        self.output(
            f"Skill confermate: {len(confirmed)}; "
            f"limite: {self.max_active_skills}; "
            f"da archiviare: {len(candidates)}."
        )

        for skill in candidates:

            self.output(
                f"  - {skill.id} — {skill.title} "
                f"({skill.created_at})"
            )

        if not candidates:
            return

        if not apply:

            self.output(
                "Nessuna modifica. Usa "
                "/memory retention apply per archiviare."
            )
            return

        archived = apply_skill_retention(
            self.store,
            self.max_active_skills,
        )

        self._record(
            "memory.retention",
            limit=self.max_active_skills,
            archived=[skill.id for skill in archived],
        )

        self.output(
            f"Archiviate {len(archived)} skill; "
            "nessun contenuto è stato cancellato."
        )

    def _embeddings(
        self,
        arguments: list[str],
    ) -> None:

        if self.embedding_index is None:

            self.output(
                "Embedding disattivato: configura embedding.enabled "
                "e installa hagar[embedding]."
            )
            return

        command = (
            arguments[0].lower()
            if arguments
            else "stats"
        )

        if command in {"stats", "status"}:

            stats = self.embedding_index.stats()
            self.output(
                f"Embedding: {stats['model']} "
                f"({stats['dimensions']}d), "
                f"{stats.get('total', 0)} vettori"
            )

            for entity, total in sorted(
                stats.get("entities", {}).items()
            ):
                self.output(f"  {entity}: {total}")

            return

        if command == "reindex":

            counts = self.embedding_index.reindex()
            self.output(
                "Reindex: "
                f"{counts.get('updated', 0)} aggiornati, "
                f"{counts.get('unchanged', 0)} invariati"
            )
            return

        if command == "search":

            query = " ".join(arguments[1:]).strip()

            if not query:

                self.output(
                    "Uso: /memory embeddings search <testo>"
                )
                return

            hits = self.embedding_index.search(
                query,
                limit=10,
            )

            if not hits:

                self.output("Nessun risultato vettoriale.")
                return

            for hit in hits:

                self.output(
                    f"{hit.score:.4f}  {hit.entity}:{hit.entity_id}"
                    + (
                        f"  progetto={hit.project}"
                        if hit.project
                        else ""
                    )
                )
            return

        self.output(
            "Uso: /memory embeddings "
            "status|reindex|search <testo>"
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
