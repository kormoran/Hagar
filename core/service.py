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
        self.summary_runner: Any = None

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
    # Summary in background
    # ==================================================

    def start_summary_worker(self) -> None:

        if self.summary_runner is not None:
            return

        memory = getattr(self.harness, "memory", None)
        database = getattr(memory, "database", None)

        if memory is None or database is None:
            return

        config = getattr(self.harness, "config", None)
        memory_config = getattr(config, "memory", None)

        if not getattr(
            memory_config,
            "summary_background",
            True,
        ):
            return

        llm = getattr(self.harness, "llm", None)
        context_window = getattr(
            llm,
            "context_window",
            None,
        )

        if not context_window:
            context_window = getattr(
                memory_config,
                "summary_context_window",
                8192,
            )

        summary_llm = llm

        try:

            from llm.factory import create_llm

            model_config = getattr(config, "model", None)

            if model_config is not None:
                summary_llm = create_llm(model_config)

        except Exception:
            summary_llm = llm

        try:

            from memory.summary_jobs import SummaryJobRunner

            self.summary_runner = SummaryJobRunner(
                memory,
                llm=summary_llm,
                projects=getattr(
                    self.harness,
                    "project_store",
                    None,
                ),
                context_window=context_window,
                summary_max_chars=getattr(
                    memory_config,
                    "summary_max_chars",
                    4000,
                ),
                audit=getattr(self.harness, "audit", None),
                embedding_index=getattr(
                    self.harness,
                    "embedding_index",
                    None,
                ),
            )
            self.summary_runner.start()

        except Exception as exc:

            self.summary_runner = None
            audit = getattr(self.harness, "audit", None)

            if audit is not None:

                try:
                    audit.record(
                        "memory.summary_worker_failed",
                        error=str(exc),
                    )
                except Exception:
                    pass

    def stop_summary_worker(self) -> None:

        if self.summary_runner is None:
            return

        self.summary_runner.stop()
        self.summary_runner = None

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

        filesystem = getattr(
            self.harness,
            "filesystem",
            None,
        )
        checkpoint_started = False

        if filesystem is not None:

            try:
                filesystem.begin_checkpoint()
                checkpoint_started = True
            except Exception:
                checkpoint_started = False

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

        finally:

            manager = getattr(
                self.harness,
                "subagents",
                None,
            )

            if manager is not None:

                try:
                    manager.finish_turn()
                except Exception:
                    pass

            if checkpoint_started and filesystem is not None:

                try:
                    filesystem.commit_checkpoint()
                except Exception:
                    pass

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
        """Archivia la chat corrente, poi apre una nuova sessione."""

        memory = getattr(self.harness, "memory", None)

        if memory is None:
            raise RuntimeError("memory is disabled")

        old_session = getattr(memory, "session_id", None)
        old_turns = []

        if old_session:

            try:
                old_turns = memory.session_turns(limit=1)
            except Exception:
                old_turns = []

        if old_turns:

            audit = getattr(self.harness, "audit", None)
            old_project = getattr(
                self.harness,
                "project_id",
                None,
            )

            try:
                archived = memory.archive_session(
                    project=old_project
                )

            except Exception as exc:

                if audit is not None:

                    audit.record(
                        "chat.archive_failed",
                        session=old_session,
                        error=str(exc),
                    )

            else:

                if audit is not None:

                    audit.record(
                        "chat.archive",
                        session=old_session,
                        archived=archived,
                    )

                self._emit(
                    "chat.archive",
                    session_id=old_session,
                )

                if self.summary_runner is None:
                    self.start_summary_worker()

                if self.summary_runner is not None:

                    try:
                        self.summary_runner.enqueue(
                            old_session,
                            project=old_project,
                        )
                    except Exception as exc:

                        if audit is not None:

                            audit.record(
                                "memory.summary_enqueue_failed",
                                session=old_session,
                                error=str(exc),
                            )

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

            stats = (
                memory.stats()
                if hasattr(memory, "stats")
                else {
                    "backend": "markdown",
                    "path": str(config.vault.path),
                }
            )

            memory_status = {
                "enabled": True,
                "backend": stats.get("backend", "sqlite"),
                "path": stats.get("path"),
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

        embedding = getattr(self.harness, "embeddings", None)

        embedding_status = (
            embedding.status()
            if embedding is not None
            else {
                "enabled": False,
                "error": getattr(
                    self.harness,
                    "embedding_error",
                    None,
                ),
            }
        )

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
            "embedding": embedding_status,
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

            llm = getattr(self.harness, "llm", None)
            memory_config = getattr(
                getattr(self.harness, "config", None),
                "memory",
                None,
            )
            context_window = getattr(
                llm,
                "context_window",
                None,
            ) or getattr(
                memory_config,
                "summary_context_window",
                8192,
            )

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
                llm=llm,
                audit=self.harness.audit,
                input_func=prompt,
                summary_max_chars=(
                    self.harness.config.memory.summary_max_chars
                ),
                context_window=context_window,
                embedding_index=getattr(
                    self.harness,
                    "embedding_index",
                    None,
                ),
            ).finish()

        except Exception as exc:

            self.harness.audit.record(
                "memory.failed",
                stage="session_end",
                error=str(exc),
            )

        self._emit("session.finished")
