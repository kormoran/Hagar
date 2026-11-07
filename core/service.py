"""Service layer di Hagar: stato, turni ed eventi senza console."""

from __future__ import annotations

import time

from typing import Any
from typing import Callable

from core.agent import AgentCancelled
from core.events import EventSink
from core.events import ServiceEvent
from core.events import emit
from core.images import ImageInput
from core.usage import UsageLedger
from memory.projects import ProjectError
from memory.session import SessionSummarizer


class HarnessService:
    """
    API stabile sopra il ``Harness``.

    Non legge da ``input`` e non scrive su stdout: espone operazioni e
    eventi. La CLI attuale è un adapter; la GUI userà la stessa API.
    """

    def __init__(
        self,
        harness: Any,
        event_sink: EventSink | None = None,
    ) -> None:

        self.harness = harness
        self._event_sink = event_sink or (lambda event: None)

        # Instrada anche gli eventi generati da Agent e ToolRegistry.
        if getattr(self.harness, "agent", None) is not None:
            self.harness.agent.event_sink = self._emit_event

        registry = getattr(self.harness, "registry", None)

        if registry is not None and hasattr(
            registry,
            "event_sink",
        ):
            registry.event_sink = self._emit_event

        self.usage = UsageLedger(self._emit_event)

        llm = getattr(self.harness, "llm", None)

        if llm is not None and hasattr(llm, "usage_sink"):
            llm.usage_sink = self.usage.record

    # ==================================================
    # Eventi
    # ==================================================

    def _emit_event(
        self,
        event: ServiceEvent,
    ) -> None:

        try:
            self._event_sink(event)
        except Exception:
            # Un sink guasto non deve interrompere il turno.
            pass

    def _emit(
        self,
        event_type: str,
        **data: Any,
    ) -> None:

        emit(
            self._emit_event,
            event_type,
            **data,
        )

    # ==================================================
    # Turni
    # ==================================================

    def ask(
        self,
        question: str,
        images: list[ImageInput] | None = None,
    ) -> str:

        started = time.perf_counter()

        self._emit(
            "turn.start",
            question=question,
            image_count=len(images or []),
            project_id=getattr(
                self.harness,
                "project_id",
                None,
            ),
        )

        try:
            if images:
                answer = self.harness.agent.ask(
                    question,
                    images=images,
                )
            else:
                answer = self.harness.agent.ask(question)

        except AgentCancelled:

            self._emit(
                "turn.cancelled",
                duration_ms=round(
                    (time.perf_counter() - started) * 1000,
                    1,
                ),
            )

            raise

        except Exception as exc:

            self._emit(
                "turn.error",
                error=str(exc),
                duration_ms=round(
                    (time.perf_counter() - started) * 1000,
                    1,
                ),
            )

            raise

        self._emit(
            "turn.answer",
            answer=answer,
            duration_ms=round(
                (time.perf_counter() - started) * 1000,
                1,
            ),
        )

        return answer

    # ==================================================
    # Progetto
    # ==================================================

    @property
    def project_id(self) -> str | None:

        return self.harness.project_id

    def current_project(self) -> dict[str, Any] | None:

        project_id = self.harness.project_id
        store = getattr(self.harness, "project_store", None)

        if project_id is None or store is None:
            return None

        project = store.get_project(project_id)

        if project is None:
            return None

        return {
            "id": project.id,
            "title": project.title,
            "status": project.status,
            "active_decisions": project.active_decisions,
        }

    def list_projects(
        self,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:

        store = getattr(self.harness, "project_store", None)

        if store is None:
            return []

        projects = store.list_projects(
            include_archived=include_archived,
        )

        return [
            {
                "id": project.id,
                "title": project.title,
                "status": project.status,
                "active_decisions": project.active_decisions,
            }
            for project in projects
        ]

    def set_project(
        self,
        project_id: str | None,
    ) -> None:

        if project_id is None:
            self.clear_project()
            return

        store = getattr(self.harness, "project_store", None)

        if store is None:
            raise ProjectError(
                "projects are disabled: memory is not available"
            )

        project = store.get_project(project_id)

        if project is None or project.status != "active":
            raise ProjectError(
                f"project not found or not active: {project_id}"
            )

        self.harness.project_id = project.id

        if self.harness.project_state is not None:
            self.harness.project_state["id"] = project.id

        self.harness.agent.project_id = project.id

        self._emit(
            "project.changed",
            project_id=project.id,
            title=project.title,
        )

    def clear_project(self) -> None:

        self.harness.project_id = None

        if self.harness.project_state is not None:
            self.harness.project_state["id"] = None

        self.harness.agent.project_id = None

        self._emit(
            "project.changed",
            project_id=None,
        )

    def create_project(
        self,
        name: str,
    ) -> dict[str, Any]:

        store = getattr(self.harness, "project_store", None)

        if store is None:
            raise ProjectError(
                "projects are disabled: memory is not available"
            )

        project = store.create_project(name)
        self.set_project(project.id)

        return {
            "id": project.id,
            "title": project.title,
            "status": project.status,
            "active_decisions": project.active_decisions,
        }

    # ==================================================
    # Chat
    # ==================================================

    def new_chat(self) -> str:
        """Apre una nuova sessione e azzera il contesto della chat."""

        memory = getattr(self.harness, "memory", None)

        if memory is None:
            raise RuntimeError("memory is disabled")

        session_id = memory.new_session()

        audit = getattr(self.harness, "audit", None)

        if audit is not None:
            audit.session_id = session_id
            audit.record(
                "chat.new",
                session=session_id,
            )

        self.usage.reset()

        self._emit(
            "chat.new",
            session_id=session_id,
        )

        return session_id

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Elenco delle chat salvate nel Vault."""

        memory = getattr(self.harness, "memory", None)

        if memory is None:
            return []

        return memory.list_sessions(limit=limit)

    def load_chat(self, session_id: str) -> list[dict[str, Any]]:
        """Turni di una chat passata, in ordine cronologico."""

        memory = getattr(self.harness, "memory", None)

        if memory is None:
            raise RuntimeError("memory is disabled")

        return memory.read_session(session_id)

    def resume_chat(self, session_id: str) -> list[dict[str, Any]]:
        """Riprende una chat: nuova sessione di lavoro sullo stesso id."""

        memory = getattr(self.harness, "memory", None)

        if memory is None:
            raise RuntimeError("memory is disabled")

        memory.select_session(session_id)

        audit = getattr(self.harness, "audit", None)

        if audit is not None:
            audit.session_id = session_id
            audit.record(
                "chat.resume",
                session=session_id,
            )

        self.usage.reset()
        self._emit(
            "chat.resumed",
            session_id=session_id,
        )

        return memory.read_session(session_id)

    def memories(
        self,
        query: str = "",
        limit: int = 200,
    ) -> dict[str, Any]:
        """Elenco o ricerca delle note di memoria, sola lettura."""

        memory = getattr(self.harness, "memory", None)

        if memory is None:
            return {
                "enabled": False,
                "query": query,
                "documents": [],
            }

        if query.strip():

            results = memory.index.search(
                query,
                limit=min(int(limit), 100),
            )

            documents = [
                result
                for result in results
                if result.get("kind")
                not in {"chat", "archive", "summary"}
            ]

            return {
                "enabled": True,
                "query": query,
                "documents": documents,
            }

        return {
            "enabled": True,
            "query": "",
            "documents": memory.index.documents(limit=limit),
        }

    def read_memory(self, path: str) -> dict[str, Any] | None:
        """Contenuto di una nota di memoria indicizzata."""

        memory = getattr(self.harness, "memory", None)

        if memory is None:
            raise RuntimeError("memory is disabled")

        return memory.index.document(path)

    # ==================================================
    # Stato
    # ==================================================

    def status(self) -> dict[str, Any]:

        config = self.harness.config
        audit = self.harness.audit
        memory = getattr(self.harness, "memory", None)

        memory_status: dict[str, Any]

        if memory is None:

            memory_status = {
                "enabled": False,
                "error": getattr(
                    self.harness,
                    "memory_error",
                    None,
                ),
            }

        else:

            memory_status = {
                "enabled": True,
                "vault": str(config.vault.path),
                "subdir": config.memory.vault_subdir,
            }

        audit_status = {
            "enabled": bool(
                getattr(audit, "enabled", False)
            ),
            "path": str(
                getattr(audit, "path", "")
            ),
        }

        return {
            "session_id": getattr(
                audit,
                "session_id",
                None,
            ),
            "model": {
                "provider": config.model.provider,
                "name": config.model.name,
            },
            "project": self.current_project(),
            "memory": memory_status,
            "audit": audit_status,
            "policy": {
                "path": str(config.policy.path),
                "subject": config.policy.subject,
                "error": getattr(
                    self.harness,
                    "policy_error",
                    None,
                ),
            },
            "tools": list(
                self.harness.registry.tool_names()
            ),
        }

    # ==================================================
    # Fine sessione
    # ==================================================

    def finish_session(
        self,
        interactive: bool = False,
        input_func: Callable[[str], str] | None = None,
    ) -> None:

        memory = getattr(self.harness, "memory", None)

        if memory is None:
            return

        prompt = (
            input_func
            if input_func is not None
            else (
                input
                if interactive
                else (lambda _prompt: "")
            )
        )

        try:

            SessionSummarizer(
                memory,
                projects=getattr(
                    self.harness,
                    "project_store",
                    None,
                ),
                project_id=getattr(
                    self.harness,
                    "project_id",
                    None,
                ),
                llm=self.harness.llm,
                audit=self.harness.audit,
                input_func=prompt,
                summary_max_chars=(
                    self.harness.config.memory.summary_max_chars
                ),
            ).finish()

        except Exception as exc:

            self.harness.audit.record(
                "memory.failed",
                stage="session_end",
                error=str(exc),
            )

        self._emit("session.finished")
