"""Test dell'MVP subagenti: un figlio sincrono e read-only."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.filesystem import DirectoryPermissions
from core.filesystem import FileSystemSandbox
from core.subagents import AgentSpec
from core.subagents import SubagentBusy
from core.subagents import SubagentLimit
from core.subagents import SubagentManager
from core.tool_call import ToolCall
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event, **fields):
        self.events.append((event, fields))


class FakeLLM:
    def __init__(self, release=None, read_path=None):
        self.registry = None
        self.prompts = []
        self.usage_sink = None
        self.release = release
        self.read_path = read_path
        self.read_output = None

    def request_tool_call(self, messages, registry):
        self.registry = registry
        self.prompts.extend(messages)

        if self.read_path is not None:
            self.read_output = registry.execute(
                "filesystem.read_file",
                path=self.read_path,
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
    registry = ToolRegistry()

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
            context="contesto",
        )
    )

    assert result.status == "completed"
    assert result.answer == "risposta del subagente"
    assert llm.registry is not None
    assert "demo.read" in llm.registry.tool_names()
    assert "demo.write" not in llm.registry.tool_names()
    assert "agent.run" not in llm.registry.tool_names()
    assert "Contesto fornito dal padre" in str(llm.prompts[0]["content"])
    assert audit.events[0][0] == "agent.spawned"
    assert audit.events[-1][0] == "agent.finished"


def test_second_subagent_is_rejected_while_busy():
    release = __import__("threading").Event()
    manager = SubagentManager(
        make_config(),
        make_parent_registry(),
        Audit(),
        llm_factory=lambda model, audit: FakeLLM(release),
        max_concurrent=1,
    )

    first = manager.spawn(AgentSpec(task="primo"))

    with pytest.raises(SubagentLimit):
        manager.spawn(AgentSpec(task="secondo"))

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

    result = manager.run(AgentSpec(task="fallisci"))

    assert result.status == "failed"
    assert "provider unavailable" in result.error
    assert audit.events[-1][0] == "agent.failed"


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

    first = manager.spawn(AgentSpec(task="primo"))
    second = manager.spawn(AgentSpec(task="secondo"))

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
