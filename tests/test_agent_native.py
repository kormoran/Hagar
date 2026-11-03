"""Test del ciclo agentico con calling nativo."""

from __future__ import annotations

from core.agent import Agent
from core.tool_call import ToolCall
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry
from llm.base import (
    LLMReply,
    NativeToolsUnavailable,
)


class FakeAudit:
    include_outputs = True

    def __init__(self):
        self.entries = []

    def record(self, event, **fields):
        self.entries.append({"event": event, **fields})


class FakeNativeLLM:
    supports_native_tools = True

    def __init__(
        self,
        replies,
        native=True,
        text_answer="risposta testuale",
    ):
        self.replies = list(replies)
        self.native_tools = native
        self.text_answer = text_answer
        self.messages = []
        self.calls = 0
        self.text_calls = 0

    def native_step(self, messages, registry):
        self.calls += 1
        self.messages.append(
            [dict(message) for message in messages]
        )

        reply = self.replies.pop(0)

        if isinstance(reply, Exception):
            raise reply

        return reply

    def request_tool_call(self, messages, registry):
        self.text_calls += 1
        return ToolCall(tool=None, arguments={})

    def chat(self, messages):
        return self.text_answer


def make_registry(result="echo: x") -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="demo.echo",
            description="Echo.",
            category="demo",
            handler=lambda text: result,
        )
    )

    return registry


def native_call(
    text: str = "x",
    call_id: str = "c1",
) -> tuple[ToolCall, dict]:
    call = ToolCall(
        tool="demo.echo",
        arguments={"text": text},
        id=call_id,
    )

    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "name": call.tool,
                "arguments": call.arguments,
            }
        ],
    }

    return call, message


def test_native_tool_call_then_final_answer():
    call, message = native_call()

    llm = FakeNativeLLM(
        [
            LLMReply(
                text="",
                tool_calls=[call],
                assistant_message=message,
            ),
            LLMReply(text="fatto"),
        ]
    )

    audit = FakeAudit()

    answer = Agent(
        llm,
        make_registry(),
        vault=None,
        audit=audit,
    ).ask("ciao")

    assert answer == "fatto"
    assert llm.calls == 2

    second = llm.messages[1]

    assert second[0] == {
        "role": "user",
        "content": "ciao",
    }
    assert second[1]["role"] == "assistant"
    assert second[1]["tool_calls"][0]["id"] == "c1"
    assert second[2] == {
        "role": "tool",
        "tool_call_id": "c1",
        "name": "demo.echo",
        "content": "echo: x",
    }

    events = [entry["event"] for entry in audit.entries]

    assert "tool.call" in events
    assert "tool.result" in events
    assert "turn.answer" in events

    assert audit.entries[0]["native"] is True


def test_native_multiple_calls_in_one_reply():
    first = ToolCall(
        tool="demo.echo",
        arguments={"text": "a"},
        id="c1",
    )
    second = ToolCall(
        tool="demo.echo",
        arguments={"text": "b"},
        id="c2",
    )

    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "c1",
                "name": "demo.echo",
                "arguments": {"text": "a"},
            },
            {
                "id": "c2",
                "name": "demo.echo",
                "arguments": {"text": "b"},
            },
        ],
    }

    llm = FakeNativeLLM(
        [
            LLMReply(
                text="",
                tool_calls=[first, second],
                assistant_message=message,
            ),
            LLMReply(text="fatto"),
        ]
    )

    answer = Agent(
        llm,
        make_registry(),
        vault=None,
    ).ask("ciao")

    assert answer == "fatto"

    second_request = llm.messages[1]

    tool_messages = [
        item
        for item in second_request
        if item["role"] == "tool"
    ]

    assert len(tool_messages) == 2
    assert tool_messages[0]["tool_call_id"] == "c1"
    assert tool_messages[1]["tool_call_id"] == "c2"


def test_native_respects_the_tool_call_limit():
    first = ToolCall(
        tool="demo.echo",
        arguments={"text": "a"},
        id="c1",
    )
    second = ToolCall(
        tool="demo.echo",
        arguments={"text": "b"},
        id="c2",
    )

    llm = FakeNativeLLM(
        [
            LLMReply(
                text="",
                tool_calls=[first, second],
                assistant_message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "demo.echo",
                            "arguments": {"text": "a"},
                        },
                        {
                            "id": "c2",
                            "name": "demo.echo",
                            "arguments": {"text": "b"},
                        },
                    ],
                },
            )
        ]
    )

    audit = FakeAudit()

    answer = Agent(
        llm,
        make_registry(),
        vault=None,
        audit=audit,
        max_tool_calls=1,
    ).ask("ciao")

    assert answer == "Agent stopped after 1 tool calls."
    assert llm.calls == 1

    events = [entry["event"] for entry in audit.entries]

    assert "turn.stop" in events
    assert "tool.call" not in events


def test_native_falls_back_to_text_protocol():
    llm = FakeNativeLLM(
        [NativeToolsUnavailable("modello senza tool")],
        text_answer="risposta testuale",
    )

    audit = FakeAudit()

    answer = Agent(
        llm,
        make_registry(),
        vault=None,
        audit=audit,
    ).ask("ciao")

    assert answer == "risposta testuale"
    assert llm.native_tools is False
    assert llm.calls == 1
    assert llm.text_calls == 1

    fallback = [
        entry
        for entry in audit.entries
        if entry["event"] == "llm.native_fallback"
    ]

    assert len(fallback) == 1


def test_native_failure_after_a_tool_does_not_fall_back():
    call, message = native_call()

    llm = FakeNativeLLM(
        [
            LLMReply(
                text="",
                tool_calls=[call],
                assistant_message=message,
            ),
            NativeToolsUnavailable("sparito"),
        ]
    )

    audit = FakeAudit()

    answer = Agent(
        llm,
        make_registry(),
        vault=None,
        audit=audit,
    ).ask("ciao")

    assert "non più disponibili" in answer

    events = [entry["event"] for entry in audit.entries]

    assert "turn.error" in events
    assert "llm.native_fallback" not in events


def test_native_disabled_uses_text_protocol():
    llm = FakeNativeLLM(
        [],
        native=False,
        text_answer="testo",
    )

    audit = FakeAudit()

    answer = Agent(
        llm,
        make_registry(),
        vault=None,
        audit=audit,
    ).ask("ciao")

    assert answer == "testo"
    assert llm.calls == 0
    assert llm.text_calls == 1
    assert audit.entries[0]["native"] is False


def test_native_builds_assistant_message_when_missing():
    call = ToolCall(
        tool="demo.echo",
        arguments={"text": "x"},
    )

    llm = FakeNativeLLM(
        [
            LLMReply(text="", tool_calls=[call]),
            LLMReply(text="fatto"),
        ]
    )

    answer = Agent(
        llm,
        make_registry(),
        vault=None,
    ).ask("ciao")

    assert answer == "fatto"

    tool_message = llm.messages[1][-1]

    assert tool_message["tool_call_id"] == "call-1"


def test_native_redacts_tool_output():
    class RedactingAudit(FakeAudit):
        include_outputs = False

    call, message = native_call()

    audit = RedactingAudit()

    Agent(
        FakeNativeLLM(
            [
                LLMReply(
                    text="",
                    tool_calls=[call],
                    assistant_message=message,
                ),
                LLMReply(text="fatto"),
            ]
        ),
        make_registry(),
        vault=None,
        audit=audit,
    ).ask("ciao")

    result = [
        entry
        for entry in audit.entries
        if entry["event"] == "tool.result"
    ][0]

    assert result["output"].startswith("<redacted: ")
