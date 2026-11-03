"""Test dell'integrazione tra memoria e Agent."""

from __future__ import annotations

from core.agent import Agent
from core.tool_call import ToolCall
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry
from memory.store import MemoryStore
from memory.vault import Vault


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, event, **fields):
        entry = {"event": event, **fields}
        self.entries.append(entry)
        return entry


class ScriptedLLM:
    def __init__(
        self,
        calls=None,
        answer: str = "risposta",
    ) -> None:

        self.calls = list(calls or [])
        self.answer = answer
        self.seen: list[list[dict]] = []

    def request_tool_call(self, messages, registry):
        self.seen.append(
            [dict(message) for message in messages]
        )

        if self.calls:
            return self.calls.pop(0)

        return ToolCall(tool=None, arguments={})

    def chat(self, messages):
        return self.answer


class FailingStore:
    def __init__(
        self,
        *,
        fail_context: bool = False,
        fail_append: bool = False,
    ) -> None:

        self.fail_context = fail_context
        self.fail_append = fail_append
        self.turn = None
        self.ended = False
        self.appended = []

    def begin_turn(self, turn):
        self.turn = turn

    def context_text(self):
        if self.fail_context:
            raise RuntimeError("contesto rotto")
        return None, 0

    def append_turn(self, turn, question, answer):
        if self.fail_append:
            raise RuntimeError("append rotto")
        self.appended.append((turn, question, answer))

    def end_turn(self):
        self.ended = True
        self.turn = None


def make_store(tmp_path, context_turns: int = 5) -> MemoryStore:

    root = tmp_path / "vault"
    root.mkdir(exist_ok=True)

    return MemoryStore(
        Vault(root),
        session_id="s1",
        context_turns=context_turns,
        max_skill_chars=500,
        model="test-model",
    )


def make_agent(llm, memory, audit=None) -> Agent:

    return Agent(
        llm,
        ToolRegistry(),
        vault=None,
        audit=audit,
        memory=memory,
    )


def events(audit) -> list[str]:

    return [
        entry["event"]
        for entry in audit.entries
    ]


def test_turn_is_appended(tmp_path):
    store = make_store(tmp_path)
    audit = FakeAudit()

    answer = make_agent(
        ScriptedLLM(answer="la risposta"),
        store,
        audit,
    ).ask("la domanda")

    assert answer == "la risposta"

    turns = store.recent_turns()

    assert len(turns) == 1
    assert turns[0].question == "la domanda"
    assert turns[0].answer == "la risposta"

    assert "memory.turn" in events(audit)
    assert "memory.context" not in events(audit)


def test_context_is_injected_on_next_turn(tmp_path):
    store = make_store(tmp_path)
    audit = FakeAudit()

    make_agent(ScriptedLLM(answer="prima risposta"), store, audit).ask(
        "prima domanda"
    )

    llm = ScriptedLLM(answer="seconda risposta")

    make_agent(llm, store, audit).ask("seconda domanda")

    messages = llm.seen[0]

    assert messages[0]["role"] == "system"
    assert "prima domanda" in messages[0]["content"]
    assert "prima risposta" in messages[0]["content"]

    context_events = [
        entry
        for entry in audit.entries
        if entry["event"] == "memory.context"
    ]

    assert context_events[-1]["turns"] == 1


def test_context_respects_limit(tmp_path):
    store = make_store(tmp_path, context_turns=1)

    make_agent(ScriptedLLM(answer="A1"), store).ask("Q1")
    make_agent(ScriptedLLM(answer="A2"), store).ask("Q2")

    llm = ScriptedLLM(answer="A3")

    make_agent(llm, store).ask("Q3")

    context = llm.seen[0][0]["content"]

    assert "Q2" in context
    assert "Q1" not in context


def test_errors_are_not_stored(tmp_path):
    store = make_store(tmp_path)
    audit = FakeAudit()

    class BrokenLLM(ScriptedLLM):
        def request_tool_call(self, messages, registry):
            raise RuntimeError("offline")

    answer = make_agent(
        BrokenLLM(),
        store,
        audit,
    ).ask("domanda")

    assert "Errore" in answer
    assert store.recent_turns() == []
    assert "memory.turn" not in events(audit)


def test_append_failure_does_not_break_the_turn(tmp_path):
    audit = FakeAudit()
    store = FailingStore(fail_append=True)

    answer = make_agent(
        ScriptedLLM(answer="ok"),
        store,
        audit,
    ).ask("domanda")

    assert answer == "ok"

    failure = [
        entry
        for entry in audit.entries
        if entry["event"] == "memory.failed"
    ]

    assert failure[0]["stage"] == "append"
    assert store.ended is True


def test_context_failure_does_not_break_the_turn(tmp_path):
    audit = FakeAudit()
    store = FailingStore(fail_context=True)
    llm = ScriptedLLM(answer="ok")

    answer = make_agent(llm, store, audit).ask("domanda")

    assert answer == "ok"
    assert llm.seen[0][0]["role"] == "user"

    assert any(
        entry["event"] == "memory.failed"
        and entry["stage"] == "context"
        for entry in audit.entries
    )


def test_current_turn_is_visible_to_tools(tmp_path):
    store = make_store(tmp_path)
    audit = FakeAudit()

    registry = ToolRegistry()
    captured = {}

    def handler():
        captured["turn"] = store.current_turn
        return "ok"

    registry.register(
        ToolDefinition(
            name="demo.tool",
            description="Demo",
            category="demo",
            handler=handler,
        )
    )

    llm = ScriptedLLM(
        calls=[ToolCall(tool="demo.tool", arguments={})],
        answer="fatto",
    )

    agent = Agent(
        llm,
        registry,
        vault=None,
        audit=audit,
        memory=store,
    )

    assert agent.ask("usa il tool") == "fatto"

    turn = [
        entry["turn"]
        for entry in audit.entries
        if entry["event"] == "turn.start"
    ][0]

    assert captured["turn"] == turn
    assert store.current_turn is None
