"""Subagenti asincroni con workspace privato.

Il padre può avviare fino a `max_concurrent` figli. Ogni figlio:

- ha un client LLM separato;
- riceve una copia degli input in un workspace temporaneo;
- vede solo quel workspace, in sola lettura;
- non può usare `agent.*` né `filesystem.chdir`;
- non scrive memoria;
- non chiede conferme.

I figli non sono persistenti: alla fine del turno del padre vengono
attesi, annullati e i workspace vengono rimossi.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Callable

from core.agent import Agent
from core.agent import AgentCancelled
from core.agent import AgentTimedOut
from core.agent_data import ArtifactStore
from core.agent_data import Mailbox
from core.agent_data import register_child_data_tools
from core.confirmations import ParentBridgeConfirmation
from core.filesystem import DirectoryPermissions
from core.filesystem import FileSystemSandbox
from core.filesystem_tools import FileSystemToolProvider
from core.permissions import Capability
from core.permissions import DenyAllConfirmation
from core.permissions import PermissionEvaluator
from core.tool_registry import ToolRegistry
from core.usage import UsageLedger
from local_tools.vision_tool import VisionToolProvider


READ_ONLY_CAPABILITIES = (
    Capability.FILESYSTEM_READ
    | Capability.MEMORY_READ
    | Capability.COMPUTE
    | Capability.AGENT_DATA
)

EXCLUDED_TOOLS = frozenset({
    "filesystem.chdir",
})


class SubagentBusy(RuntimeError):
    """Un subagente è già in esecuzione."""


class SubagentLimit(SubagentBusy):
    """Troppi subagenti attivi."""


class SubagentPolicyError(RuntimeError):
    """La policy del figlio non è più restrittiva di quella del padre."""


@dataclass(frozen=True)
class AgentSpec:
    task: str
    reason: str
    context: str = ""
    inputs: tuple[str, ...] = ()
    max_tool_calls: int = 8
    max_seconds: float = 300.0


@dataclass(frozen=True)
class AgentResult:
    agent_id: str
    status: str
    answer: str = ""
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0.0
    artifacts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:

        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "answer": self.answer,
            "error": self.error,
            "usage": self.usage,
            "duration_ms": self.duration_ms,
            "artifacts": list(self.artifacts),
        }


@dataclass
class _Job:
    agent_id: str
    spec: AgentSpec
    status: str = "queued"
    result: AgentResult | None = None
    error: str | None = None
    workspace: Path | None = None
    agent: Agent | None = None
    child_ceiling: Capability = Capability.NONE
    started: float = field(default_factory=time.perf_counter)
    done: threading.Event = field(
        default_factory=threading.Event
    )


class SubagentManager:
    """Esegue subagenti concorrenti con risorse separate."""

    def __init__(
        self,
        config: Any,
        parent_registry: ToolRegistry,
        audit: Any,
        *,
        parent_filesystem: FileSystemSandbox | None = None,
        project_store: Any = None,
        project_state: dict[str, Any] | None = None,
        parent_id: str | None = None,
        llm_factory: Callable[[Any, Any], Any] | None = None,
        broker: Any = None,
        broker_profile: str | None = None,
        broker_local_only: bool = True,
        max_tool_calls: int = 8,
        max_concurrent: int = 2,
        max_seconds: float = 300.0,
        confirmation: Any = None,
    ) -> None:

        self.config = config
        self.parent_registry = parent_registry
        self.audit = audit
        self.parent_filesystem = parent_filesystem
        self.project_store = project_store
        self.project_state = project_state or {}
        self.parent_id = parent_id
        self.llm_factory = llm_factory
        self.broker = broker
        self.broker_profile = broker_profile
        self.broker_local_only = broker_local_only
        self.max_tool_calls = int(max_tool_calls)
        self.max_concurrent = max(1, int(max_concurrent))
        self.max_seconds = float(max_seconds)
        self.confirmation = confirmation
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self.artifacts = ArtifactStore()
        self.mailbox = Mailbox()

    # ==================================================
    # Stato
    # ==================================================

    def _active_count_locked(self) -> int:

        return sum(
            1
            for job in self._jobs.values()
            if job.status in {"queued", "running"}
        )

    @property
    def busy(self) -> bool:

        with self._lock:
            return self._active_count_locked() > 0

    def status(self, agent_id: str) -> dict[str, Any]:

        with self._lock:
            job = self._jobs.get(agent_id)

        if job is None:
            raise KeyError("unknown subagent")

        result = job.result

        return {
            "agent_id": agent_id,
            "status": job.status,
            "error": job.error,
            "usage": (
                dict(result.usage) if result is not None else {}
            ),
            "duration_ms": (
                result.duration_ms if result is not None else 0.0
            ),
        }

    def result(self, agent_id: str) -> AgentResult | None:

        with self._lock:
            job = self._jobs.get(agent_id)

        return None if job is None else job.result

    # ==================================================
    # Workspace
    # ==================================================

    def _new_workspace(self) -> Path:

        return Path(
            tempfile.mkdtemp(prefix="hagar-subagent-")
        )

    def _copy_inputs(
        self,
        spec: AgentSpec,
        workspace: Path,
    ) -> None:

        if not spec.inputs:
            return

        if self.parent_filesystem is None:

            raise RuntimeError(
                "subagent inputs require a parent filesystem"
            )

        for raw in spec.inputs:

            source = self.parent_filesystem.resolve_path(raw)

            if not source.is_file():

                raise ValueError(
                    f"subagent input is not a file: {raw}"
                )

            target = workspace / source.name

            if target.exists():

                raise ValueError(
                    f"duplicate subagent input: {source.name}"
                )

            shutil.copy2(source, target)

    def _child_filesystem(
        self,
        workspace: Path,
    ) -> FileSystemSandbox:

        return FileSystemSandbox(
            roots={
                workspace: DirectoryPermissions(
                    read=True,
                    write=False,
                    create=False,
                    rename=False,
                    delete=False,
                    execute=True,
                )
            },
            current_directory=workspace,
            aliases={"workspace": workspace},
            limits=(
                self.parent_filesystem.limits
                if self.parent_filesystem is not None
                else None
            ),
        )

    def _child_ceiling(self) -> Capability:
        """Il figlio deve avere un tetto strettamente più basso."""

        evaluator = self.parent_registry.evaluator

        if evaluator is None:

            raise SubagentPolicyError(
                "parent policy is unavailable"
            )

        parent_ceiling = evaluator.ceiling
        child_ceiling = (
            parent_ceiling
            & READ_ONLY_CAPABILITIES
        )

        if child_ceiling == parent_ceiling:

            raise SubagentPolicyError(
                "subagent policy is not more restrictive "
                "than the parent policy"
            )

        return child_ceiling

    def _child_registry(
        self,
        filesystem: FileSystemSandbox,
        agent_id: str,
        child_ceiling: Capability,
    ) -> ToolRegistry:

        registry = ToolRegistry(
            evaluator=PermissionEvaluator(child_ceiling),
            subject=self.parent_registry.subject,
            confirmation=(
                ParentBridgeConfirmation(
                    self.confirmation,
                    timeout=180,
                    audit=self.audit,
                    agent_id=agent_id,
                    parent_id=self.parent_id,
                )
                if self.confirmation is not None
                else DenyAllConfirmation()
            ),
            audit=self.audit,
            agent_id=agent_id,
            parent_id=self.parent_id,
            compact_descriptions=(
                self.parent_registry.compact_descriptions
            ),
        )

        FileSystemToolProvider(filesystem).register_tools(registry)
        VisionToolProvider(filesystem).register_tools(registry)

        for tool in list(registry.list_definitions()):

            if (
                tool.name in EXCLUDED_TOOLS
                or tool.capabilities & ~READ_ONLY_CAPABILITIES
            ):
                registry.unregister(tool.name)

        for tool in self.parent_registry.list_definitions():

            if tool.name.startswith("filesystem."):
                continue

            if tool.name.startswith("agent."):
                continue

            if tool.name.startswith("artifact."):
                continue

            if tool.name.startswith("mailbox."):
                continue

            if tool.name in EXCLUDED_TOOLS:
                continue

            if tool.capabilities & ~READ_ONLY_CAPABILITIES:
                continue

            if registry.exists(tool.name):
                continue

            registry.register(tool)

        register_child_data_tools(
            registry,
            self.artifacts,
            self.mailbox,
            agent_id=agent_id,
            parent_id=self.parent_id or "parent",
            filesystem=filesystem,
        )

        return registry

    def _default_llm_factory(
        self,
        model_config: Any,
        audit: Any,
    ) -> Any:

        from llm.factory import create_llm

        return create_llm(model_config, audit=audit)

    # ==================================================
    # Esecuzione
    # ==================================================

    def spawn(self, spec: AgentSpec) -> str:

        if not spec.task.strip():

            raise ValueError("subagent task is required")

        if not spec.reason.strip():

            raise ValueError("subagent reason is required")

        try:
            child_ceiling = self._child_ceiling()

        except SubagentPolicyError as exc:

            if self.audit is not None:

                self.audit.record(
                    "agent.policy_rejected",
                    agent_id="a-policy",
                    parent=self.parent_id,
                    reason=str(exc),
                )

            raise

        agent_id = "a-" + uuid.uuid4().hex[:8]

        with self._lock:

            if self._active_count_locked() >= self.max_concurrent:

                raise SubagentLimit(
                    "too many active subagents"
                )

            job = _Job(
                agent_id=agent_id,
                spec=spec,
                child_ceiling=child_ceiling,
            )
            self._jobs[agent_id] = job

        if self.audit is not None:

            self.audit.record(
                "agent.spawned",
                agent_id=agent_id,
                agent=agent_id,
                parent=self.parent_id,
                task=spec.task,
                reason=spec.reason,
                inputs=list(spec.inputs),
                max_tool_calls=min(
                    int(spec.max_tool_calls),
                    self.max_tool_calls,
                ),
                max_seconds=min(
                    float(spec.max_seconds),
                    self.max_seconds,
                ),
                child_capabilities=sorted(
                    name
                    for name in (
                        "FILESYSTEM_READ",
                        "MEMORY_READ",
                        "COMPUTE",
                        "AGENT_DATA",
                    )
                    if child_ceiling & Capability[name]
                ),
            )

        thread = threading.Thread(
            target=self._run_job,
            args=(job,),
            name=f"hagar-subagent-{agent_id}",
            daemon=True,
        )
        thread.start()

        return agent_id

    def _run_job(self, job: _Job) -> None:

        with self._lock:
            job.status = "running"

        if self.audit is not None:

            self.audit.record(
                "agent.started",
                agent_id=job.agent_id,
                agent=job.agent_id,
                parent=self.parent_id,
            )

        started = time.perf_counter()
        deadline = started + min(
            float(job.spec.max_seconds),
            self.max_seconds,
        )
        workspace: Path | None = None

        try:

            workspace = self._new_workspace()
            job.workspace = workspace
            self._copy_inputs(job.spec, workspace)

            if self.llm_factory is not None:

                llm = self.llm_factory(
                    self.config.model,
                    self.audit,
                )

            elif self.broker is not None:

                from llm.broker_client import BrokerLLMClient

                llm = BrokerLLMClient(
                    self.broker,
                    self.config.model,
                    profile=(
                        self.broker_profile
                        or getattr(
                            self.config.broker,
                            "default_profile",
                            "coding",
                        )
                    ),
                    audit=self.audit,
                    local_only=self.broker_local_only,
                    auto_route=bool(
                        getattr(
                            self.config.broker,
                            "auto_route",
                            False,
                        )
                    ),
                )

            else:

                llm = self._default_llm_factory(
                    self.config.model,
                    self.audit,
                )

            usage = UsageLedger()

            if hasattr(llm, "usage_sink"):
                llm.usage_sink = usage.record

            child_agent = Agent(
                llm=llm,
                tool_registry=self._child_registry(
                    self._child_filesystem(workspace),
                    job.agent_id,
                    job.child_ceiling,
                ),
                vault=None,
                audit=self.audit,
                memory=None,
                project_store=self.project_store,
                project_id=self.project_state.get("id"),
                max_tool_calls=min(
                    int(job.spec.max_tool_calls),
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
                agent_id=job.agent_id,
                deadline=deadline,
            )
            job.agent = child_agent

            prompt = job.spec.task

            if job.spec.inputs:

                prompt = (
                    "File copiati nel workspace: "
                    + ", ".join(
                        Path(value).name
                        for value in job.spec.inputs
                    )
                    + "\n\n"
                    + prompt
                )

            if job.spec.context.strip():

                prompt = (
                    "Contesto fornito dal padre:\n"
                    f"{job.spec.context.strip()}\n\n"
                    "Compito:\n"
                    f"{prompt}"
                )

            answer = child_agent.ask(prompt)
            duration_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )
            result = AgentResult(
                agent_id=job.agent_id,
                status="completed",
                answer=answer,
                usage=usage.snapshot(),
                duration_ms=duration_ms,
                artifacts=tuple(
                    ref.artifact_id
                    for ref in self.artifacts.list()
                    if ref.owner == job.agent_id
                ),
            )

        except AgentTimedOut:

            duration_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )
            result = AgentResult(
                agent_id=job.agent_id,
                status="timed_out",
                error="wall-clock deadline exceeded",
                duration_ms=duration_ms,
            )

        except AgentCancelled:

            duration_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )
            result = AgentResult(
                agent_id=job.agent_id,
                status="cancelled",
                error="cancelled",
                duration_ms=duration_ms,
            )

        except Exception as exc:

            duration_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )
            result = AgentResult(
                agent_id=job.agent_id,
                status="failed",
                error=str(exc),
                duration_ms=duration_ms,
            )

        finally:

            if workspace is not None:

                shutil.rmtree(
                    workspace,
                    ignore_errors=True,
                )

        with self._lock:
            job.result = result
            job.status = result.status
            job.error = result.error
            job.done.set()

        if self.audit is not None:

            self.audit.record(
                (
                    "agent.finished"
                    if result.status == "completed"
                    else (
                        "agent.timed_out"
                        if result.status == "timed_out"
                        else (
                            "agent.cancelled"
                            if result.status == "cancelled"
                            else "agent.failed"
                        )
                    )
                ),
                agent_id=job.agent_id,
                agent=job.agent_id,
                parent=self.parent_id,
                status=result.status,
                usage=result.usage,
                duration_ms=result.duration_ms,
                error=result.error,
            )

    def wait(
        self,
        agent_id: str,
        timeout: float | None = None,
    ) -> AgentResult | None:

        with self._lock:
            job = self._jobs.get(agent_id)

        if job is None:
            raise KeyError("unknown subagent")

        job.done.wait(timeout)

        return job.result

    def cancel(self, agent_id: str) -> bool:

        with self._lock:
            job = self._jobs.get(agent_id)

        if job is None:
            return False

        if job.status in {"completed", "failed", "cancelled"}:
            return False

        if job.agent is not None:
            job.agent.cancel()

        return True

    def run(
        self,
        spec: AgentSpec,
    ) -> AgentResult:

        """Scorciatoia sincrona: spawn + wait."""

        agent_id = self.spawn(spec)
        result = self.wait(agent_id, timeout=300)

        if result is None:

            self.cancel(agent_id)
            return AgentResult(
                agent_id=agent_id,
                status="failed",
                error="subagent timeout",
            )

        return result

    def _audit_discarded_artifacts(self) -> None:

        if self.audit is None:
            return

        for item in self.artifacts.snapshot():

            if item["saved"]:
                continue

            reason = (
                "unread"
                if item["read_count"] == 0
                else "read_but_not_saved"
            )

            self.audit.record(
                "artifact.discarded",
                agent_id=item["owner"],
                artifact=item["artifact_id"],
                owner=item["owner"],
                kind=item["kind"],
                mime_type=item["mime_type"],
                size=item["size"],
                sha256=item["sha256"],
                read_count=item["read_count"],
                reason=reason,
            )

    def finish_turn(self, timeout: float = 30.0) -> None:
        """Attende i figli, annulla i rimasti e dimentica i risultati."""

        deadline = time.monotonic() + timeout

        with self._lock:
            jobs = list(self._jobs.values())

        for job in jobs:

            remaining = max(0.0, deadline - time.monotonic())

            if remaining:
                job.done.wait(remaining)

            if not job.done.is_set():
                self.cancel(job.agent_id)

        for job in jobs:

            remaining = max(0.0, deadline - time.monotonic())

            if remaining:
                job.done.wait(remaining)

        self._audit_discarded_artifacts()

        with self._lock:
            self._jobs.clear()

        self.artifacts.reset()
        self.mailbox.clear()
