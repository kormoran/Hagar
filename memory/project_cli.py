"""Comandi `/project` e selezione iniziale del progetto."""

from __future__ import annotations

from typing import Any
from typing import Callable

from memory.projects import Project, ProjectStore


class ProjectCLI:
    def __init__(
        self,
        store: ProjectStore,
        project_id_getter: Callable[[], str | None],
        project_id_setter: Callable[[str | None], None],
        output: Callable[[str], Any] = print,
        input_func: Callable[[str], str] = input,
        max_active: int = 0,
        interactive: bool = True,
        audit: Any = None,
    ) -> None:

        self.store = store
        self.get_project_id = project_id_getter
        self.set_project_id = project_id_setter
        self.output = output
        self.input_func = input_func
        self.max_active = int(max_active)
        self.interactive = interactive
        self.audit = audit

    def handle(
        self,
        line: str,
    ) -> bool:

        parts = line.strip().split()

        if not parts or parts[0].lower() != "/project":
            return False

        arguments = parts[1:]

        command = (
            arguments[0].lower()
            if arguments
            else "list"
        )

        if command in {"list", "ls"}:
            self._list()

        elif command == "new":
            self._new(arguments[1:])

        elif command in {"select", "use"}:
            self._select(arguments[1:])

        elif command in {"free", "none"}:
            self.set_project_id(None)
            self.output("Attività libera: nessuna memoria di progetto.")
            self._hint()

        elif command == "archive":
            self._archive(arguments[1:], True)

        elif command == "unarchive":
            self._archive(arguments[1:], False)

        elif command in {"status", "current"}:
            self._status()

        else:
            self._help()

        return True

    def choose_initial(
        self,
        forced: str | None = None,
        free: bool = False,
    ) -> str | None:
        """
        Seleziona il progetto iniziale.

        ``forced`` e ``free`` vengono dagli argomenti CLI e non chiedono
        nulla. Senza TTY si resta in attività libera.
        """

        if free:
            self.output("Attività libera: nessuna memoria di progetto.")
            self._hint()
            return None

        if forced:

            project = self.store.get_project(forced)

            if project is None or project.status != "active":

                raise ValueError(
                    f"progetto non trovato o non attivo: {forced}"
                )

            self.set_project_id(project.id)
            self._selected(project)
            return project.id

        projects = self.store.list_projects()

        if not projects:

            self.output("Nessun progetto attivo.")
            self.output(
                "Crea un progetto con: /project new <nome>"
            )
            return None

        self.output("")
        self.output("Progetti attivi:")

        for index, project in enumerate(projects, start=1):

            self.output(
                f"  {index}. {project.title} [{project.id}] "
                f"({project.active_decisions} decisioni attive)"
            )

        self.output("  a. attività libera")
        self.output("  n. nuovo progetto")
        self.output("")

        try:
            choice = self.input_func(
                "Scelta [a]: "
            ).strip().lower()

        except (EOFError, KeyboardInterrupt):

            choice = ""

        if choice in {"a", "free", ""}:

            self.set_project_id(None)
            self.output(
                "Attività libera: nessuna memoria di progetto."
            )
            self._hint()
            return None

        if choice in {"n", "new", "nuovo"}:

            try:
                name = self.input_func(
                    "Nome nuovo progetto: "
                ).strip()

            except (EOFError, KeyboardInterrupt):

                name = ""

            if not name:

                self.set_project_id(None)
                return None

            project = self.store.create_project(name)
            self.set_project_id(project.id)
            self._selected(project)
            return project.id

        if choice.isdigit():

            position = int(choice) - 1

            if 0 <= position < len(projects):

                project = projects[position]
                self.set_project_id(project.id)
                self._selected(project)
                return project.id

        self.output("Scelta non valida; attività libera.")
        self.set_project_id(None)
        return None

    # ==================================================
    # Comandi
    # ==================================================

    def _list(self) -> None:

        projects = self.store.list_projects()
        current = self.get_project_id()

        self.output("Progetti attivi:")

        if not projects:

            self.output("  (nessuno)")

        for project in projects:

            marker = (
                "*"
                if project.id == current
                else " "
            )

            self.output(
                f" {marker} {project.title} [{project.id}] "
                f"({project.active_decisions} decisioni attive)"
            )

        self.output("  attività libera")

    def _new(self, arguments: list[str]) -> None:

        name = " ".join(arguments).strip()

        if not name:

            self.output("Uso: /project new <nome>")
            return

        try:

            project = self.store.create_project(name)

        except Exception as ex:

            self.output(f"Errore: {ex}")
            return

        self.set_project_id(project.id)
        self._selected(project)

    def _select(self, arguments: list[str]) -> None:

        if not arguments:

            self.output("Uso: /project select <nome>")
            return

        project_id = arguments[0]

        project = self.store.get_project(project_id)

        if project is None or project.status != "active":

            self.output(
                f"Progetto non trovato o non attivo: {project_id}"
            )
            return

        self.set_project_id(project.id)
        self._selected(project)

    def _status(self) -> None:

        project_id = self.get_project_id()

        if project_id is None:

            self.output("Progetto attivo: attività libera")
            return

        project = self.store.get_project(project_id)

        if project is None:

            self.output("Progetto attivo: non trovato")
            return

        self.output(
            f"Progetto attivo: {project.title} [{project.id}]"
        )
        self.output(
            f"Decisioni attive: {project.active_decisions}"
        )
        self.output(f"Ultima attività: {project.last_activity}")

    def _archive(
        self,
        arguments: list[str],
        archived: bool,
    ) -> None:

        if not arguments:

            self.output(
                "Uso: /project "
                + ("archive" if archived else "unarchive")
                + " <nome>"
            )
            return

        project_id = arguments[0]
        project = self.store.get_project(project_id)

        if project is None:

            self.output(f"Progetto non trovato: {project_id}")
            return

        try:
            self.store.set_project_status(
                project.id,
                "archived" if archived else "active",
            )

        except Exception as ex:

            self.output(f"Errore: {ex}")
            return

        if archived and self.get_project_id() == project.id:
            self.set_project_id(None)
            self.output(
                "Progetto archiviato; attività libera."
            )

        else:

            self.output(
                "Progetto archiviato."
                if archived
                else "Progetto riattivato."
            )

    def _selected(self, project: Project) -> None:

        self.output("")
        self.output(
            f"Buon lavoro sul progetto {project.title}."
        )
        self._hint()
        self._maintenance(project)

    def _maintenance(self, project: Project) -> None:

        if not self.max_active:
            return

        if project.active_decisions <= self.max_active:
            return

        self.output(
            f"Attenzione: il progetto {project.title} ha "
            f"{project.active_decisions} decisioni attive, "
            f"oltre il limite di {self.max_active}."
        )

        if not self.interactive:

            self.output(
                "Manutenzione rimandata: sessione non interattiva."
            )
            return

        try:

            answer = self.input_func(
                "Vuoi archiviare il progetto? (y/N): "
            ).strip().lower()

        except (EOFError, KeyboardInterrupt):

            answer = ""

        if answer not in {"y", "yes", "s", "si", "sì"}:

            self.output("Progetto mantenuto attivo.")
            return

        try:
            self.store.set_project_status(
                project.id,
                "archived",
            )

        except Exception as ex:

            self.output(f"Archiviazione non riuscita: {ex}")
            return

        self.set_project_id(None)
        self.output(
            f"Progetto {project.title} archiviato. "
            "Attività libera."
        )

        if self.audit is not None:

            try:
                self.audit.record(
                    "project.archive",
                    project=project.id,
                    decisions=project.active_decisions,
                )

            except Exception:
                pass

    def _hint(self) -> None:

        self.output(
            "Comandi: /project new <nome> per creare, "
            "/project list per tornare alla lista."
        )

    def _help(self) -> None:

        self.output(
            "Comandi progetto:\n"
            "  /project list\n"
            "  /project new <nome>\n"
            "  /project select <nome>\n"
            "  /project free\n"
            "  /project archive <nome>\n"
            "  /project unarchive <nome>\n"
            "  /project status"
        )
