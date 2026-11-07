"""Subagenti sincroni e isolati dell'MVP.

Un solo subagente per volta, stesso modello del padre, tool in sola
lettura, nessuna scrittura di memoria, conferme negate e nessun
annidamento. Il manager tiene il ciclo di vita e l'audit; il subagente
non riceve mai `agent.run`.
"""

from __future__ import annotations

import threading
import time
import uuid

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Callable

from core.agent import Agent
from core.permissions import Capability
from core.permissions import DenyAllConfirmation
from core.tool_registry import ToolRegistry
from core.usage import UsageLedger


READ_ONLY_CAPABILITIES = (
    Capability.FILESYSTEM_READ
    | Capability.MEMORY_READ
    | Capability.COMPUTE
)

EXCLUDED_TOOLS = frozenset({
    "agent.run",
    "filesystem.chdir",
})


class SubagentBusy(RuntimeError):
    """Un subagente è già in esecuzione."""


@dataclass(frozen=True)
class AgentSpec:
    task: str
    context: str = ""
    max_tool_calls: int = 8


@dataclass(frozen=True)
class AgentResult:
    agent_id: str
    status: str
    answer: str = ""
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:

        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "answer": self.answer,
            "error": self.error,
            "usage": self.usage,
            "duration_ms": self.duration_ms,
        }


class SubagentManager:
    """Esegue un subagente sincrono con componenti separati."""

    def __init__(
        self,
        config: Any,
        parent_registry: ToolRegistry,
        audit: Any,
        *,
        project_store: Any = None,
        project_state: dict[str, Any] | None = None,
        parent_id: str | None = None,
        llm_factory: Callable[[Any, Any], Any] | None = None,
        max_tool_calls: int = 8,
    ) -> None:

        self.config = config
        self.parent_registry = parent_registry
        self.audit = audit
        self.project_store = project_store
        self.project_state = project_state or {}
        self.parent_id = parent_id
        self.llm_factory = llm_factory
        self.max_tool_calls = int(max_tool_calls)
        self._lock = threading.Lock()
        self._busy = False

    @property
    def busy(self) -> bool:

        with self._lock:
            return self._busy

    def _default_llm_factory(
        self,
        model_config: Any,
        audit: Any,
    ) -> Any:

        from llm.factory import create_llm

        return create_llm(model_config, audit=audit)

    def _child_registry(self) -> ToolRegistry:
        """Registry filtrato: sole capability di lettura/calcolo."""

        registry = ToolRegistry(
            evaluator=self.parent_registry.evaluator,
            subject=self.parent_registry.subject,
            confirmation=DenyAllConfirmation(),
            audit=self.audit,
        )

        for tool in self.parent_registry.list_definitions():

            if tool.name in EXCLUDED_TOOLS:
                continue

            if (
                tool.capabilities
                & ~READ_ONLY_CAPABILITIES
            ):
                continue

            registry.register(tool)

        return registry

    def run(
        self,
        spec: AgentSpec,
    ) -> AgentResult:

        if not spec.task.strip():

            raise ValueError("subagent task is required")

        with self._lock:

            if self._busy:
                raise SubagentBusy(
                    "a subagent is already running"
                )

            self._busy = True

        agent_id = "a-" + uuid.uuid4().hex[:8]
        started = time.perf_counter()

        if self.audit is not None:

            self.audit.record(
                "agent.spawned",
                agent=agent_id,
                parent=self.parent_id,
                task=spec.task,
                max_tool_calls=min(
                    int(spec.max_tool_calls),
                    self.max_tool_calls,
                ),
            )
            self.audit.record(
                "agent.started",
                agent=agent_id,
                parent=self.parent_id,
            )

        try:

            llm = (
                self.llm_factory
                or self._default_llm_factory
            )(
                self.config.model,
                self.audit,
            )

            usage = UsageLedger()

            if hasattr(llm, "usage_sink"):
                llm.usage_sink = usage.record

            child_agent = Agent(
                llm=llm,
                tool_registry=self._child_registry(),
                vault=None,
                audit=self.audit,
                memory=None,
                project_store=self.project_store,
                project_id=self.project_state.get("id"),
                max_tool_calls=min(
                    int(spec.max_tool_calls),
                    self.max_tool_calls,
                ),
                max_context_chars=getattr(
                    self.config.memory,
                    "max_context_chars",
                    6000,
                ),
                context_project_memories=getattr(
                    self.config.memory,
                    "context_project_memories",
                    10,
                ),
            )

            prompt = spec.task

            if spec.context.strip():

                prompt = (
                    "Contesto fornito dal padre:\n"
                    f"{spec.context.strip()}\n\n"
                    "Compito:\n"
                    f"{spec.task}"
                )

            answer = child_agent.ask(prompt)
            snapshot = usage.snapshot()
            duration_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )

            if self.audit is not None:

                self.audit.record(
                    "agent.finished",
                    agent=agent_id,
                    parent=self.parent_id,
                    status="completed",
                    usage=snapshot,
                    duration_ms=duration_ms,
                )

            return AgentResult(
                agent_id=agent_id,
                status="completed",
                answer=answer,
                usage=snapshot,
                duration_ms=duration_ms,
            )

        except Exception as exc:

            duration_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )

            if self.audit is not None:

                self.audit.record(
                    "agent.failed",
                    agent=agent_id,
                    parent=self.parent_id,
                    error=str(exc),
                    duration_ms=duration_ms,
                )

            return AgentResult(
                agent_id=agent_id,
                status="failed",
                error=str(exc),
                duration_ms=duration_ms,
            )

        finally:

            with self._lock:
                self._busy = False
