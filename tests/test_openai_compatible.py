"""Test dei backend OpenAI e LM Studio (nessuna rete)."""

from __future__ import annotations

import pytest
import requests

from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry
from llm.base import NativeToolsUnavailable
from llm.lmstudio_client import LMStudioClient
from llm.openai_client import OpenAIClient


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
# OpenAI
# =====================================================


def test_openai_chat(monkeypatch):
    http = install(
        monkeypatch,
        {"choices": [{"message": {"content": "risposta"}}]},
    )

    client = OpenAIClient(
        api_key="sk-openai",
        model="gpt-4o",
    )

    assert client.chat([user_message()]) == "risposta"

    call = http.calls[0]

    assert call["url"] == (
        "https://api.openai.com/v1/chat/completions"
    )
    assert call["json"] == {
        "model": "gpt-4o",
        "messages": [user_message()],
        "stream": False,
    }
    assert call["headers"]["Authorization"] == (
        "Bearer sk-openai"
    )


def test_openai_native_tool_call(monkeypatch):
    install(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "demo__echo",
                                    "arguments": (
                                        '{"text": "x"}'
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        },
    )

    client = OpenAIClient(
        api_key="sk",
        model="gpt-4o",
    )

    reply = client.native_step(
        [user_message()],
        make_registry(),
    )

    assert reply.tool_calls[0].tool == "demo.echo"
    assert reply.tool_calls[0].arguments == {
        "text": "x"
    }
    assert reply.tool_calls[0].id == "call_1"


def test_openai_native_fallback_on_400(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {
                "error": {
                    "message": "tools unsupported",
                }
            },
            400,
        ),
    )

    client = OpenAIClient(api_key="sk", model="m")
    client.native_tools = True

    with pytest.raises(NativeToolsUnavailable):
        client.native_step(
            [user_message()],
            make_registry(),
        )


def test_openai_http_error_includes_api_message(
    monkeypatch,
):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {"error": {"message": "quota exceeded"}},
            429,
        ),
    )

    client = OpenAIClient(api_key="sk", model="m")

    with pytest.raises(RuntimeError, match="quota exceeded"):
        client.chat([user_message()])


# =====================================================
# LM Studio
# =====================================================


def test_lmstudio_uses_local_default_and_no_auth(
    monkeypatch,
):
    http = install(
        monkeypatch,
        {"choices": [{"message": {"content": "ok"}}]},
    )

    client = LMStudioClient(model="local-model")

    assert client.chat([user_message()]) == "ok"

    call = http.calls[0]

    assert call["url"] == (
        "http://localhost:1234/v1/chat/completions"
    )
    assert "Authorization" not in call["headers"]


def test_lmstudio_uses_custom_host_and_key(monkeypatch):
    http = install(
        monkeypatch,
        {"choices": [{"message": {"content": "ok"}}]},
    )

    client = LMStudioClient(
        model="m",
        host="http://gpu:1234/v1",
        api_key="local-key",
    )

    client.chat([user_message()])

    call = http.calls[0]

    assert call["url"] == (
        "http://gpu:1234/v1/chat/completions"
    )
    assert call["headers"]["Authorization"] == (
        "Bearer local-key"
    )


def test_lmstudio_native_tool_call(monkeypatch):
    install(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_lm",
                                "type": "function",
                                "function": {
                                    "name": "demo__echo",
                                    "arguments": {
                                        "text": "x"
                                    },
                                },
                            }
                        ],
                    }
                }
            ]
        },
    )

    client = LMStudioClient(model="local-model")

    reply = client.native_step(
        [user_message()],
        make_registry(),
    )

    assert reply.tool_calls[0].tool == "demo.echo"
    assert reply.tool_calls[0].arguments == {
        "text": "x"
    }
