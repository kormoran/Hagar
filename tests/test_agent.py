"""Test del ciclo agentico con un LLM finto (nessuna rete)."""

from __future__ import annotations

import pytest

from core.agent import Agent
from core.tool_call import ToolCall
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry


class FakeLLM:
    """LLM scriptato: restituisce le ToolCall in coda."""

    def __init__(
        self,
        calls=None,
        answer: str = "risposta finale",
    ) -> None:

        self.calls = list(calls or [])
        self.answer = answer
        self.requests: list[list[dict]] = []
        self.chat_requests: list[list[dict]] = []
        self.request_error: Exception | None = None
        self.chat_error: Exception | None = None

    def request_tool_call(self, messages, registry):

        self.requests.append(
            [dict(message) for message in messages]
        )

        if self.request_error is not None:
            raise self.request_error

        if self.calls:
            return self.calls.pop(0)

        return ToolCall(tool=None, arguments={})

    def chat(self, messages):

        self.chat_requests.append(
            [dict(message) for message in messages]
        )

        if self.chat_error is not None:
            raise self.chat_error

        return self.answer


class Recorder:
    def __init__(self, result="output del tool") -> None:
        self.result = result
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def make_registry(handler=None) -> tuple[ToolRegistry, Recorder]:

    registry = ToolRegistry()
    recorder = Recorder() if handler is None else None

    registry.register(
        ToolDefinition(
            name="demo.echo",
            description="Echo",
            category="demo",
            handler=handler or recorder,
        )
    )

    return registry, recorder


def test_answer_without_tools():
    llm = FakeLLM()
    registry, _ = make_registry()

    answer = Agent(llm, registry, vault=None).ask("ciao")

    assert answer == "risposta finale"
    assert len(llm.requests) == 1
    assert llm.requests[0][0]["content"] == "ciao"
    assert llm.chat_requests[0] == llm.requests[0]


def test_tool_is_executed_and_result_is_sent_back():
    llm = FakeLLM(
        calls=[ToolCall(tool="demo.echo", arguments={"text": "x"})]
    )
    registry, recorder = make_registry()

    answer = Agent(llm, registry, vault=None).ask("usa il tool")

    assert answer == "risposta finale"
    assert recorder.calls == [{"text": "x"}]

    # Seconda richiesta: contiene la chiamata e il risultato.
    assert len(llm.requests) == 2

    second = llm.requests[1]
    assert second[-2]["role"] == "assistant"
    assert "tool=demo.echo" in second[-2]["content"]
    assert second[-1]["role"] == "user"
    assert "Tool result (demo.echo, success):" in second[-1]["content"]
    assert "output del tool" in second[-1]["content"]


def test_multiple_tools():
    llm = FakeLLM(
        calls=[
            ToolCall(tool="demo.echo", arguments={"n": 1}),
            ToolCall(tool="demo.echo", arguments={"n": 2}),
        ]
    )
    registry, recorder = make_registry()

    Agent(llm, registry, vault=None).ask("due tool")

    assert recorder.calls == [{"n": 1}, {"n": 2}]
    assert len(llm.requests) == 3


def test_tool_exception_is_reported():
    def handler(**kwargs):
        raise ValueError("boom")

    llm = FakeLLM(
        calls=[ToolCall(tool="demo.echo", arguments={})]
    )
    registry, _ = make_registry(handler=handler)

    answer = Agent(llm, registry, vault=None).ask("fallisci")

    assert answer == "risposta finale"

    failure = llm.requests[1][-1]["content"]
    assert "Tool execution failed (demo.echo)" in failure
    assert "boom" in failure


def test_unknown_tool_is_reported():
    llm = FakeLLM(
        calls=[ToolCall(tool="missing.tool", arguments={})]
    )
    registry, _ = make_registry()

    Agent(llm, registry, vault=None).ask("tool sconosciuto")

    failure = llm.requests[1][-1]["content"]
    assert "unknown tool" in failure


def test_loop_guard_stops_after_max_calls():
    llm = FakeLLM(
        calls=[
            ToolCall(tool="demo.echo", arguments={"i": index})
            for index in range(5)
        ]
    )
    registry, recorder = make_registry()

    answer = Agent(
        llm,
        registry,
        vault=None,
        max_tool_calls=2,
    ).ask("loop")

    assert answer == "Agent stopped after 2 tool calls."
    assert len(recorder.calls) == 2

    # 2 esecuzioni + 1 richiesta finale che chiede ancora un tool.
    assert len(llm.requests) == 3


def test_zero_tool_calls_never_executes():
    llm = FakeLLM(
        calls=[ToolCall(tool="demo.echo", arguments={})]
    )
    registry, recorder = make_registry()

    answer = Agent(
        llm,
        registry,
        vault=None,
        max_tool_calls=0,
    ).ask("subito")

    assert answer == "Agent stopped after 0 tool calls."
    assert recorder.calls == []
    assert len(llm.requests) == 1


def test_request_exception_returns_message():
    llm = FakeLLM()
    llm.request_error = RuntimeError("ollama offline")
    registry, _ = make_registry()

    answer = Agent(llm, registry, vault=None).ask("ciao")

    assert "Errore durante la richiesta al modello" in answer
    assert "ollama offline" in answer


def test_chat_exception_returns_message():
    llm = FakeLLM()
    llm.chat_error = RuntimeError("risposta rotta")
    registry, _ = make_registry()

    answer = Agent(llm, registry, vault=None).ask("ciao")

    assert "Errore durante la generazione" in answer
    assert "risposta rotta" in answer


def test_components_are_stored():
    llm = FakeLLM()
    registry, _ = make_registry()
    vault = object()

    agent = Agent(llm, registry, vault=vault)

    assert agent.llm is llm
    assert agent.tools is registry
    assert agent.vault is vault
    assert agent.max_tool_calls == 10


def test_tool_result_is_structured():
    llm = FakeLLM(
        calls=[ToolCall(tool="demo.echo", arguments={})]
    )
    registry, _ = make_registry()

    agent = Agent(llm, registry, vault=None)
    result = agent._execute_tool(
        ToolCall(tool="demo.echo", arguments={})
    )

    assert result.tool_name == "demo.echo"
    assert result.success is True
    assert result.output == "output del tool"
    assert result.error is None


def test_failed_tool_result_carries_error():
    def handler(**kwargs):
        raise RuntimeError("guasto")

    registry, _ = make_registry(handler=handler)
    agent = Agent(FakeLLM(), registry, vault=None)

    result = agent._execute_tool(
        ToolCall(tool="demo.echo", arguments={})
    )

    assert result.success is False
    assert result.output == ""
    assert result.error == "guasto"


# =====================================================
# Audit log
# =====================================================


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, event, **fields):
        entry = {"event": event, **fields}
        self.entries.append(entry)
        return entry


def test_audit_records_successful_turn():
    llm = FakeLLM(
        calls=[ToolCall(tool="demo.echo", arguments={"text": "x"})]
    )
    registry, _ = make_registry()
    audit = FakeAudit()

    Agent(llm, registry, vault=None, audit=audit).ask("ciao")

    events = [
        entry["event"]
        for entry in audit.entries
    ]

    assert events == [
        "turn.start",
        "tool.call",
        "tool.result",
        "turn.answer",
    ]

    turn = audit.entries[0]["turn"]

    assert all(
        entry["turn"] == turn
        for entry in audit.entries
    )

    assert audit.entries[0]["question"] == "ciao"
    assert audit.entries[1]["tool"] == "demo.echo"
    assert audit.entries[1]["arguments"] == {"text": "x"}
    assert audit.entries[2]["success"] is True
    assert audit.entries[2]["output"] == "output del tool"
    assert isinstance(
        audit.entries[2]["duration_ms"],
        float,
    )
    assert audit.entries[3]["answer"] == "risposta finale"
    assert audit.entries[3]["tool_calls"] == 1


def test_audit_records_answer_without_tools():
    audit = FakeAudit()

    Agent(
        FakeLLM(),
        make_registry()[0],
        vault=None,
        audit=audit,
    ).ask("ciao")

    assert [
        entry["event"]
        for entry in audit.entries
    ] == ["turn.start", "turn.answer"]

    assert audit.entries[1]["tool_calls"] == 0


def test_audit_records_failed_tool():
    def handler(**kwargs):
        raise RuntimeError("guasto")

    audit = FakeAudit()

    Agent(
        FakeLLM(
            calls=[
                ToolCall(tool="demo.echo", arguments={})
            ]
        ),
        make_registry(handler=handler)[0],
        vault=None,
        audit=audit,
    ).ask("fallisci")

    result = [
        entry
        for entry in audit.entries
        if entry["event"] == "tool.result"
    ][0]

    assert result["success"] is False
    assert result["error"] == "guasto"


def test_audit_records_request_error():
    audit = FakeAudit()
    llm = FakeLLM()
    llm.request_error = RuntimeError("offline")

    Agent(
        llm,
        make_registry()[0],
        vault=None,
        audit=audit,
    ).ask("ciao")

    entry = audit.entries[-1]

    assert entry["event"] == "turn.error"
    assert entry["stage"] == "request_tool_call"
    assert "offline" in entry["error"]


def test_audit_records_loop_stop():
    audit = FakeAudit()

    Agent(
        FakeLLM(
            calls=[
                ToolCall(
                    tool="demo.echo",
                    arguments={"i": index},
                )
                for index in range(3)
            ]
        ),
        make_registry()[0],
        vault=None,
        max_tool_calls=1,
        audit=audit,
    ).ask("loop")

    entry = audit.entries[-1]

    assert entry["event"] == "turn.stop"
    assert entry["tool_calls"] == 1
    assert entry["max_tool_calls"] == 1


def test_broken_audit_does_not_stop_the_agent(capsys):
    class BrokenAudit:
        def record(self, event, **fields):
            raise RuntimeError("audit rotto")

    answer = Agent(
        FakeLLM(),
        make_registry()[0],
        vault=None,
        audit=BrokenAudit(),
    ).ask("ciao")

    assert answer == "risposta finale"
    assert "Audit log error" in capsys.readouterr().err
