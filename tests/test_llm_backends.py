"""Test dei backend DeepSeek, Claude e Gemini (nessuna rete)."""

from __future__ import annotations

import pytest
import requests

from core.audit import AuditLog, read_entries
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry
from llm.claude_client import ClaudeClient
from llm.deepseek_client import DeepSeekClient
from llm.gemini_client import GeminiClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}"
            )

    def json(self):
        return self.payload


class Recorder:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(
        self,
        url,
        json=None,
        headers=None,
        timeout=None,
    ):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )

        if not self.responses:
            raise AssertionError(
                "richiesta HTTP inattesa"
            )

        return FakeResponse(self.responses.pop(0))


def install(monkeypatch, *responses) -> Recorder:
    http = Recorder(*responses)
    monkeypatch.setattr(requests, "post", http)
    return http


def make_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="demo.echo",
            description="Echo",
            category="demo",
            handler=lambda **kwargs: "ok",
        )
    )

    return registry


def user_message(text: str = "ciao") -> dict:
    return {"role": "user", "content": text}


# =====================================================
# DeepSeek
# =====================================================


def test_deepseek_chat(monkeypatch):
    http = install(
        monkeypatch,
        {"choices": [{"message": {"content": "risposta"}}]},
    )

    client = DeepSeekClient(
        api_key="sk-deepseek",
        model="deepseek-chat",
    )

    assert client.chat([user_message()]) == "risposta"

    call = http.calls[0]

    assert call["url"] == (
        "https://api.deepseek.com/chat/completions"
    )
    assert call["json"] == {
        "model": "deepseek-chat",
        "messages": [user_message()],
        "stream": False,
    }
    assert call["headers"]["Authorization"] == (
        "Bearer sk-deepseek"
    )


def test_deepseek_generate_uses_chat(monkeypatch):
    http = install(
        monkeypatch,
        {"choices": [{"message": {"content": "ok"}}]},
    )

    client = DeepSeekClient(
        api_key="sk",
        model="deepseek-chat",
    )

    assert client.generate("domanda", "sistema") == "ok"

    messages = http.calls[0]["json"]["messages"]

    assert messages == [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "domanda"},
    ]


def test_deepseek_without_choices_raises(monkeypatch):
    install(monkeypatch, {"choices": []})

    client = DeepSeekClient(api_key="sk", model="m")

    with pytest.raises(RuntimeError, match="no choices"):
        client.chat([user_message()])


def test_deepseek_http_error(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: FakeResponse({}, 500),
    )

    client = DeepSeekClient(api_key="sk", model="m")

    with pytest.raises(requests.HTTPError):
        client.chat([user_message()])


def test_deepseek_requires_api_key():
    with pytest.raises(ValueError):
        DeepSeekClient(api_key="", model="m")


# =====================================================
# Claude
# =====================================================


def test_claude_chat(monkeypatch):
    http = install(
        monkeypatch,
        {
            "content": [
                {"type": "text", "text": "A"},
                {"type": "tool_use", "id": "x"},
                {"type": "text", "text": "B"},
            ]
        },
    )

    client = ClaudeClient(
        api_key="sk-ant",
        model="claude-model",
        max_tokens=256,
    )

    assert client.chat([user_message()]) == "AB"

    call = http.calls[0]

    assert call["url"] == (
        "https://api.anthropic.com/v1/messages"
    )
    assert call["json"]["max_tokens"] == 256
    assert call["json"]["messages"] == [user_message()]

    headers = call["headers"]

    assert headers["x-api-key"] == "sk-ant"
    assert headers["anthropic-version"] == "2023-06-01"


def test_claude_system_is_hoisted(monkeypatch):
    http = install(
        monkeypatch,
        {"content": [{"type": "text", "text": "ok"}]},
    )

    client = ClaudeClient(api_key="sk", model="m")

    client.chat(
        [
            {"role": "system", "content": "regole"},
            {"role": "user", "content": "domanda"},
        ]
    )

    payload = http.calls[0]["json"]

    assert payload["system"] == "regole"

    assert all(
        message["role"] != "system"
        for message in payload["messages"]
    )


def test_claude_consecutive_turns_are_merged(monkeypatch):
    http = install(
        monkeypatch,
        {"content": [{"type": "text", "text": "ok"}]},
    )

    client = ClaudeClient(api_key="sk", model="m")

    client.chat(
        [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "c"},
            {"role": "assistant", "content": "d"},
        ]
    )

    messages = http.calls[0]["json"]["messages"]

    assert messages == [
        {"role": "user", "content": "a\n\nb"},
        {"role": "assistant", "content": "c\n\nd"},
    ]


def test_claude_conversion_keeps_order():
    system, messages = ClaudeClient._convert_messages(
        [
            {"role": "system", "content": "S1"},
            {"role": "user", "content": "u1"},
            {"role": "system", "content": "S2"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ]
    )

    assert system == "S1\n\nS2"
    assert messages == [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]


def test_claude_conversion_of_empty_messages():
    system, messages = ClaudeClient._convert_messages([])

    assert system == ""
    assert messages == [{"role": "user", "content": ""}]


def test_claude_empty_content(monkeypatch):
    install(monkeypatch, {"content": []})

    client = ClaudeClient(api_key="sk", model="m")

    assert client.chat([user_message()]) == ""


def test_claude_without_content_raises(monkeypatch):
    install(monkeypatch, {"content": "testo"})

    client = ClaudeClient(api_key="sk", model="m")

    with pytest.raises(RuntimeError, match="no content"):
        client.chat([user_message()])


def test_claude_http_error(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: FakeResponse({}, 429),
    )

    client = ClaudeClient(api_key="sk", model="m")

    with pytest.raises(requests.HTTPError):
        client.chat([user_message()])


# =====================================================
# Gemini
# =====================================================


def test_gemini_chat(monkeypatch):
    http = install(
        monkeypatch,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "A"},
                            {"text": "B"},
                        ]
                    }
                }
            ]
        },
    )

    client = GeminiClient(
        api_key="sk-gemini",
        model="gemini-2.0-flash",
    )

    assert client.chat([user_message()]) == "AB"

    call = http.calls[0]

    assert call["url"].endswith(
        "/models/gemini-2.0-flash:generateContent"
    )
    assert call["headers"]["x-goog-api-key"] == "sk-gemini"


def test_gemini_roles_and_system(monkeypatch):
    http = install(
        monkeypatch,
        {
            "candidates": [
                {"content": {"parts": [{"text": "ok"}]}}
            ]
        },
    )

    client = GeminiClient(api_key="sk", model="m")

    client.chat(
        [
            {"role": "system", "content": "regole"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ]
    )

    payload = http.calls[0]["json"]

    assert payload["systemInstruction"] == {
        "parts": [{"text": "regole"}]
    }

    assert [item["role"] for item in payload["contents"]] == [
        "user",
        "model",
        "user",
    ]


def test_gemini_conversion_merges_turns():
    system, contents = GeminiClient._convert_messages(
        [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "c"},
        ]
    )

    assert system == ""
    assert contents == [
        {"role": "user", "parts": [{"text": "a\n\nb"}]},
        {"role": "model", "parts": [{"text": "c"}]},
    ]


def test_gemini_without_candidates_raises(monkeypatch):
    install(
        monkeypatch,
        {
            "candidates": [],
            "promptFeedback": {
                "blockReason": "SAFETY",
            },
        },
    )

    client = GeminiClient(api_key="sk", model="m")

    with pytest.raises(RuntimeError, match="SAFETY"):
        client.chat([user_message()])


def test_gemini_http_error(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: FakeResponse({}, 503),
    )

    client = GeminiClient(api_key="sk", model="m")

    with pytest.raises(requests.HTTPError):
        client.chat([user_message()])


def test_gemini_requires_api_key():
    with pytest.raises(ValueError):
        GeminiClient(api_key="", model="m")


# =====================================================
# Logica condivisa (LLMClient)
# =====================================================


def test_request_tool_call_repairs_via_backend(
    monkeypatch,
):
    http = install(
        monkeypatch,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "risposta in prosa"}]
                    }
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"tool": "demo.echo", '
                                    '"arguments": {"x": 1}}'
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )

    client = GeminiClient(api_key="sk", model="m")

    call = client.request_tool_call(
        [user_message()],
        make_registry(),
    )

    assert call.tool == "demo.echo"
    assert call.arguments == {"x": 1}
    assert len(http.calls) == 2


def test_tool_choice_is_audited(monkeypatch, tmp_path):
    install(
        monkeypatch,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"tool": null, '
                                    '"arguments": {}}'
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )

    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)

    client = GeminiClient(
        api_key="sk",
        model="gemini-2.0-flash",
        audit=audit,
    )

    client.request_tool_call(
        [user_message()],
        make_registry(),
    )

    entries = read_entries(path)

    assert [entry["event"] for entry in entries] == [
        "llm.tool_choice"
    ]

    entry = entries[0]

    assert entry["provider"] == "gemini"
    assert entry["model"] == "gemini-2.0-flash"
    assert entry["tool"] is None


def test_repair_is_audited(monkeypatch, tmp_path):
    install(
        monkeypatch,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "prosa"}]
                    }
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"tool": "demo.echo", '
                                    '"arguments": {}}'
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )

    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)

    client = GeminiClient(
        api_key="sk",
        model="m",
        audit=audit,
    )

    client.request_tool_call(
        [user_message()],
        make_registry(),
    )

    events = [
        entry["event"]
        for entry in read_entries(path)
    ]

    assert events == [
        "llm.protocol_error",
        "llm.repaired",
        "llm.tool_choice",
    ]


def test_failed_repair_is_audited(monkeypatch, tmp_path):
    install(
        monkeypatch,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "prosa"}]
                    }
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "ancora prosa"}]
                    }
                }
            ]
        },
    )

    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)

    client = GeminiClient(
        api_key="sk",
        model="m",
        audit=audit,
    )

    with pytest.raises(RuntimeError):
        client.request_tool_call(
            [user_message()],
            make_registry(),
        )

    events = [
        entry["event"]
        for entry in read_entries(path)
    ]

    assert events == [
        "llm.protocol_error",
        "llm.repair_failed",
    ]
