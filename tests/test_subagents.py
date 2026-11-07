"""Test dell'MVP subagenti: un figlio sincrono e read-only."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.filesystem import DirectoryPermissions
from core.filesystem import FileSystemSandbox
from core.permissions import ALL_CAPABILITIES
from core.permissions import Capability
from core.permissions import Effect
from core.permissions import PermissionEvaluator
from core.permissions import Subject
from core.confirmations import ParentBridgeConfirmation
from core.subagents import AgentSpec
from core.subagents import READ_ONLY_CAPABILITIES
from core.subagents import SubagentBusy
from core.subagents import SubagentLimit
from core.subagents import SubagentManager
from core.subagents import SubagentPolicyError
from core.tool_call import ToolCall
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event, **fields):
        self.events.append((event, fields))


class FakeLLM:
    def __init__(self, release=None, read_path=None, outbox=None):
        self.registry = None
        self.prompts = []
        self.usage_sink = None
        self.release = release
        self.read_path = read_path
        self.read_output = None
        self.outbox = outbox

    def request_tool_call(self, messages, registry):
        self.registry = registry
        self.prompts.extend(messages)

        if self.read_path is not None:
            self.read_output = registry.execute(
                "filesystem.read_file",
                path=self.read_path,
            )

        if self.outbox is not None:
            artifact = registry.execute(
                "artifact.put",
                text=self.outbox,
            )
            import json
            ref = json.loads(artifact)
            registry.execute(
                "mailbox.send",
                text="risultato",
                artifacts=[ref["artifact_id"]],
            )

        return ToolCall(tool=None, arguments={})

    def chat(self, messages):
        if self.release is not None:
            self.release.wait(2)
        return "risposta del subagente"


def make_config():
    return SimpleNamespace(
        model=SimpleNamespace(
            provider="lmstudio",
            name="same-model",
        ),
        memory=SimpleNamespace(
            max_context_chars=6000,
            context_project_memories=10,
        ),
    )


def make_parent_registry():
    registry = ToolRegistry(
        evaluator=PermissionEvaluator(ALL_CAPABILITIES),
        subject=Subject(
            name="assistant",
            default=Effect.ALLOW,
        ),
    )

    registry.register(
        ToolDefinition(
            name="demo.read",
            description="Read",
            category="demo",
            capabilities=1,
            handler=lambda: "read",
        )
    )
    registry.register(
        ToolDefinition(
            name="demo.write",
            description="Write",
            category="demo",
            capabilities=2,
            handler=lambda: "write",
        )
    )
    registry.register(
        ToolDefinition(
            name="agent.run",
            description="Nested subagent",
            category="agent",
            capabilities=1,
            handler=lambda task: "nested",
        )
    )

    return registry


def test_subagent_runs_with_read_only_tools():
    llm = FakeLLM()
    audit = Audit()
    parent = make_parent_registry()

    manager = SubagentManager(
        make_config(),
        parent,
        audit,
        llm_factory=lambda model, audit: llm,
    )

    result = manager.run(
        AgentSpec(
            task="analizza",
            reason="test",
            context="contesto",
        )
    )

    assert result.status == "completed"
    assert result.answer == "risposta del subagente"
    assert llm.registry is not None
    assert "demo.read" in llm.registry.tool_names()
    assert "demo.write" not in llm.registry.tool_names()
    assert "agent.run" not in llm.registry.tool_names()
    assert "artifact.put" in llm.registry.tool_names()
    assert "mailbox.send" in llm.registry.tool_names()
    assert "artifact.read" not in llm.registry.tool_names()
    assert "mailbox.inbox" not in llm.registry.tool_names()
    assert "Contesto fornito dal padre" in str(llm.prompts[0]["content"])
    assert audit.events[0][0] == "agent.spawned"
    assert audit.events[0][1]["reason"] == "test"
    assert audit.events[0][1]["agent_id"] == result.agent_id
    assert audit.events[-1][0] == "agent.finished"
    assert audit.events[-1][1]["agent_id"] == result.agent_id


def test_second_subagent_is_rejected_while_busy():
    release = __import__("threading").Event()
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        Audit(),
        llm_factory=lambda model, audit: FakeLLM(release),
        max_concurrent=1,
    )

    first = manager.spawn(AgentSpec(task="primo", reason="test"))

    with pytest.raises(SubagentLimit):
        manager.spawn(AgentSpec(task="secondo", reason="test"))

    release.set()
    assert manager.wait(first, timeout=3) is not None
    manager.finish_turn()


def test_subagent_failure_is_returned_as_result():
    def broken_factory(model, audit):
        raise RuntimeError("provider unavailable")

    audit = Audit()
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        audit,
        llm_factory=broken_factory,
    )

    result = manager.run(
        AgentSpec(task="fallisci", reason="test")
    )

    assert result.status == "failed"
    assert "provider unavailable" in result.error
    assert audit.events[-1][0] == "agent.failed"


def test_reason_is_required():
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        Audit(),
        llm_factory=lambda model, audit: FakeLLM(),
    )

    with pytest.raises(ValueError, match="reason"):
        manager.spawn(AgentSpec(task="senza motivo", reason=""))


def test_policy_must_be_strictly_more_restrictive():
    parent = ToolRegistry(
        evaluator=PermissionEvaluator(
            READ_ONLY_CAPABILITIES,
        ),
        subject=Subject(
            name="assistant",
            default=Effect.ALLOW,
        ),
    )
    manager = SubagentManager(
        make_config(),
        parent,
        Audit(),
        llm_factory=lambda model, audit: FakeLLM(),
    )

    with pytest.raises(SubagentPolicyError):
        manager.spawn(
            AgentSpec(task="test", reason="test")
        )


def test_child_confirmation_is_bridged_to_human():
    class Human:
        def confirm(self, request):
            return False

    llm = FakeLLM()
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        Audit(),
        confirmation=Human(),
        llm_factory=lambda model, audit: llm,
    )

    manager.run(
        AgentSpec(task="test", reason="test")
    )

    assert isinstance(
        llm.registry.confirmation,
        ParentBridgeConfirmation,
    )


def test_wall_clock_timeout():
    class SlowLLM(FakeLLM):
        def chat(self, messages):
            import time
            time.sleep(0.05)
            return "troppo tardi"

    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        Audit(),
        llm_factory=lambda model, audit: SlowLLM(),
        max_seconds=0.01,
    )

    result = manager.run(
        AgentSpec(task="slow", reason="test")
    )

    assert result.status == "timed_out"
    assert "deadline" in result.error


def test_input_is_copied_into_private_workspace(tmp_path):
    parent_root = tmp_path / "parent"
    parent_root.mkdir()
    (parent_root / "input.txt").write_text(
        "contenuto privato",
        encoding="utf-8",
    )
    parent_fs = FileSystemSandbox(
        roots={
            parent_root: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
            )
        },
        current_directory=parent_root,
        aliases={"workspace": parent_root},
    )

    llm = FakeLLM(
        read_path="/home/ai/workspace/input.txt",
    )
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        Audit(),
        parent_filesystem=parent_fs,
        llm_factory=lambda model, audit: llm,
    )

    result = manager.run(
        AgentSpec(
            task="leggi",
            reason="test",
            inputs=("/home/ai/workspace/input.txt",),
        )
    )

    assert result.status == "completed"
    assert "contenuto privato" in llm.read_output


def test_two_subagents_can_run_concurrently():
    release = __import__("threading").Event()

    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        Audit(),
        llm_factory=lambda model, audit: FakeLLM(release),
        max_concurrent=2,
    )

    first = manager.spawn(AgentSpec(task="primo", reason="test"))
    second = manager.spawn(AgentSpec(task="secondo", reason="test"))

    assert manager.status(first)["status"] in {
        "queued",
        "running",
    }
    assert manager.status(second)["status"] in {
        "queued",
        "running",
    }

    release.set()

    assert manager.wait(first, timeout=3) is not None
    assert manager.wait(second, timeout=3) is not None
    manager.finish_turn()


def test_subagent_outbox_and_mailbox():
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        Audit(),
        parent_id="parent",
        llm_factory=lambda model, audit: FakeLLM(
            outbox="contenuto outbox"
        ),
    )

    result = manager.run(
        AgentSpec(task="produci", reason="test")
    )

    assert result.status == "completed"
    assert len(result.artifacts) == 1

    messages = manager.mailbox.inbox("parent")
    assert len(messages) == 1
    assert messages[0].artifacts == result.artifacts

    artifact = manager.artifacts.read(result.artifacts[0])
    assert artifact["text"] == "contenuto outbox"

    manager.finish_turn()


def test_unread_artifact_is_audited_when_discarded():
    audit = Audit()
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        audit,
        llm_factory=lambda model, audit: FakeLLM(),
    )
    manager.artifacts.put_text(
        "mai letto",
        owner="a-1",
    )

    manager.finish_turn()

    events = [
        fields
        for event, fields in audit.events
        if event == "artifact.discarded"
    ]
    assert len(events) == 1
    assert events[0]["reason"] == "unread"


def test_read_but_unsaved_artifact_is_audited():
    audit = Audit()
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        audit,
        llm_factory=lambda model, audit: FakeLLM(),
    )
    ref = manager.artifacts.put_text(
        "letto ma non salvato",
        owner="a-1",
    )
    manager.artifacts.read(ref.artifact_id)

    manager.finish_turn()

    events = [
        fields
        for event, fields in audit.events
        if event == "artifact.discarded"
    ]
    assert len(events) == 1
    assert events[0]["reason"] == "read_but_not_saved"
    assert events[0]["read_count"] == 1


def test_saved_artifact_is_not_reported_as_discarded(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    parent_fs = FileSystemSandbox(
        roots={
            root: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
            )
        },
        current_directory=root,
        aliases={"workspace": root},
    )
    audit = Audit()
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        audit,
        parent_filesystem=parent_fs,
        llm_factory=lambda model, audit: FakeLLM(),
    )
    ref = manager.artifacts.put_text(
        "salvato",
        owner="a-1",
    )
    manager.artifacts.save_to(
        ref.artifact_id,
        parent_fs,
        "/home/ai/workspace/report.txt",
    )

    manager.finish_turn()

    assert not [
        event
        for event, _ in audit.events
        if event == "artifact.discarded"
    ]
