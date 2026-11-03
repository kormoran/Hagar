"""Test del calling nativo: payload e parsing per ogni provider."""

from __future__ import annotations

import pytest
import requests

from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry
from llm.base import NativeToolsUnavailable
from llm.claude_client import ClaudeClient
from llm.deepseek_client import DeepSeekClient
from llm.gemini_client import GeminiClient
from llm.ollama_client import OllamaClient


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


class FakeHTTP:
    def __init__(self, payload, status_code=200):
        self.response = FakeResponse(
            payload,
            status_code,
        )
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
                "payload": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return self.response


def install(monkeypatch, payload, status_code=200):
    http = FakeHTTP(payload, status_code)
    monkeypatch.setattr(requests, "post", http)
    return http


def make_registry() -> ToolRegistry:

    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="filesystem.read_file",
            description="Legge un file.",
            category="filesystem",
            handler=lambda **kwargs: "contenuto",
            parameters=[
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Percorso",
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    param_type="integer",
                    description="Righe massime",
                    required=False,
                ),
            ],
        )
    )

    return registry


def ollama() -> OllamaClient:
    return OllamaClient(
        model="llama3.1",
        host="http://test",
    )


def deepseek() -> DeepSeekClient:
    return DeepSeekClient(
        api_key="sk",
        model="deepseek-chat",
        base_url="http://test",
    )


def claude() -> ClaudeClient:
    return ClaudeClient(
        api_key="sk",
        model="claude",
        base_url="http://test",
    )


def gemini() -> GeminiClient:
    return GeminiClient(
        api_key="sk",
        model="gemini",
        base_url="http://test",
    )


# =====================================================
# Schema condiviso
# =====================================================


def test_parameters_schema_marks_required_fields():
    schema = OllamaClient._parameters_schema(
        make_registry().get("filesystem.read_file")
    )

    assert schema["type"] == "object"
    assert schema["required"] == ["path"]
    assert schema["properties"]["path"] == {
        "type": "string",
        "description": "Percorso",
    }
    assert schema["properties"]["limit"]["type"] == (
        "integer"
    )


def test_parse_arguments_accepts_object_and_json():
    assert OllamaClient._parse_arguments(
        {"path": "a"}
    ) == {"path": "a"}
    assert OllamaClient._parse_arguments(
        '{"path": "a"}'
    ) == {"path": "a"}
    assert OllamaClient._parse_arguments(None) == {}


@pytest.mark.parametrize("value", ["non-json", [1, 2], 42])
def test_parse_arguments_rejects_invalid(value):
    with pytest.raises(RuntimeError):
        OllamaClient._parse_arguments(value)


# =====================================================
# Ollama
# =====================================================


def test_ollama_native_sends_tools(monkeypatch):
    http = install(
        monkeypatch,
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "filesystem.read_file",
                            "arguments": {"path": "nota.txt"},
                        }
                    }
                ],
            }
        },
    )

    reply = ollama().native_step(
        [{"role": "user", "content": "leggi"}],
        make_registry(),
    )

    assert reply.tool_calls[0].tool == "filesystem.read_file"
    assert reply.tool_calls[0].arguments == {
        "path": "nota.txt"
    }
    assert reply.tool_calls[0].id == "ollama-0"

    payload = http.calls[0]["payload"]

    assert payload["tools"][0]["type"] == "function"
    assert (
        payload["tools"][0]["function"]["name"]
        == "filesystem.read_file"
    )
    assert (
        payload["tools"][0]["function"]["parameters"][
            "required"
        ]
        == ["path"]
    )


def test_ollama_native_parses_string_arguments(monkeypatch):
    install(
        monkeypatch,
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "filesystem.read_file",
                            "arguments": '{"path": "x"}',
                        }
                    }
                ],
            }
        },
    )

    reply = ollama().native_step(
        [{"role": "user", "content": "leggi"}],
        make_registry(),
    )

    assert reply.tool_calls[0].arguments == {"path": "x"}


def test_ollama_native_text_only(monkeypatch):
    install(
        monkeypatch,
        {"message": {"content": "ok"}},
    )

    reply = ollama().native_step(
        [{"role": "user", "content": "ciao"}],
        make_registry(),
    )

    assert reply.text == "ok"
    assert reply.tool_calls == []
    assert reply.assistant_message is not None


def test_ollama_native_rejected(monkeypatch):
    install(monkeypatch, {}, status_code=400)

    with pytest.raises(NativeToolsUnavailable):
        ollama().native_step(
            [{"role": "user", "content": "x"}],
            make_registry(),
        )


def test_ollama_converts_prior_tool_messages():
    messages = [
        {"role": "user", "content": "leggi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "name": "filesystem.read_file",
                    "arguments": {"path": "x"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "filesystem.read_file",
            "content": "contenuto",
        },
    ]

    converted = OllamaClient._to_native_messages(
        messages
    )

    assert converted[1]["tool_calls"][0]["function"] == {
        "name": "filesystem.read_file",
        "arguments": {"path": "x"},
    }
    assert converted[2]["role"] == "tool"
    assert converted[2]["content"] == "contenuto"


# =====================================================
# DeepSeek
# =====================================================


def test_deepseek_native_parses_tool_calls(monkeypatch):
    http = install(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": (
                                        "filesystem.read_file"
                                    ),
                                    "arguments": (
                                        '{"path": "x"}'
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        },
    )

    reply = deepseek().native_step(
        [{"role": "user", "content": "leggi"}],
        make_registry(),
    )

    assert reply.tool_calls[0].id == "call_1"
    assert reply.tool_calls[0].arguments == {"path": "x"}

    payload = http.calls[0]["payload"]

    assert payload["tools"][0]["type"] == "function"
    assert payload["messages"] == [
        {"role": "user", "content": "leggi"}
    ]


def test_deepseek_native_converts_tool_results():
    messages = [
        {"role": "user", "content": "leggi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "name": "filesystem.read_file",
                    "arguments": {"path": "x"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "filesystem.read_file",
            "content": "contenuto",
        },
    ]

    converted = DeepSeekClient._to_native_messages(
        messages
    )

    assert converted[2] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": "contenuto",
    }
    assert converted[1]["tool_calls"][0]["function"][
        "arguments"
    ] == '{"path": "x"}'


def test_deepseek_native_rejected(monkeypatch):
    install(monkeypatch, {}, status_code=422)

    with pytest.raises(NativeToolsUnavailable):
        deepseek().native_step(
            [{"role": "user", "content": "x"}],
            make_registry(),
        )


# =====================================================
# Claude
# =====================================================


def test_claude_native_parses_tool_use(monkeypatch):
    http = install(
        monkeypatch,
        {
            "content": [
                {"type": "text", "text": "Leggo."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "filesystem.read_file",
                    "input": {"path": "x"},
                },
            ]
        },
    )

    reply = claude().native_step(
        [{"role": "user", "content": "leggi"}],
        make_registry(),
    )

    assert reply.text == "Leggo."
    assert reply.tool_calls[0].id == "toolu_1"
    assert reply.tool_calls[0].arguments == {"path": "x"}

    payload = http.calls[0]["payload"]

    assert payload["tools"][0]["input_schema"][
        "required"
    ] == ["path"]
    assert "parameters" not in payload["tools"][0]


def test_claude_native_converts_tool_cycle():
    messages = [
        {"role": "system", "content": "Sei un agente."},
        {"role": "user", "content": "leggi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "toolu_1",
                    "name": "filesystem.read_file",
                    "arguments": {"path": "x"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "toolu_1",
            "name": "filesystem.read_file",
            "content": "contenuto",
        },
    ]

    system, converted = (
        ClaudeClient._convert_native_messages(messages)
    )

    assert system == "Sei un agente."
    assert converted[0]["role"] == "user"
    assert converted[1]["content"][0] == {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "filesystem.read_file",
        "input": {"path": "x"},
    }
    assert converted[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": "contenuto",
    }


def test_claude_native_rejected(monkeypatch):
    install(monkeypatch, {}, status_code=400)

    with pytest.raises(NativeToolsUnavailable):
        claude().native_step(
            [{"role": "user", "content": "x"}],
            make_registry(),
        )


# =====================================================
# Gemini
# =====================================================


def test_gemini_native_parses_function_call(monkeypatch):
    http = install(
        monkeypatch,
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Leggo."},
                            {
                                "functionCall": {
                                    "name": (
                                        "filesystem.read_file"
                                    ),
                                    "args": {"path": "x"},
                                }
                            },
                        ]
                    }
                }
            ]
        },
    )

    reply = gemini().native_step(
        [{"role": "user", "content": "leggi"}],
        make_registry(),
    )

    assert reply.text == "Leggo."
    assert reply.tool_calls[0].tool == "filesystem.read_file"
    assert reply.tool_calls[0].arguments == {"path": "x"}

    payload = http.calls[0]["payload"]

    declaration = payload["tools"][0][
        "functionDeclarations"
    ][0]

    assert declaration["name"] == "filesystem.read_file"
    assert declaration["parameters"]["required"] == [
        "path"
    ]


def test_gemini_native_converts_tool_cycle():
    messages = [
        {"role": "user", "content": "leggi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "g1",
                    "name": "filesystem.read_file",
                    "arguments": {"path": "x"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "g1",
            "name": "filesystem.read_file",
            "content": "contenuto",
        },
    ]

    _, contents = (
        GeminiClient._convert_native_messages(messages)
    )

    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0] == {
        "functionCall": {
            "name": "filesystem.read_file",
            "args": {"path": "x"},
        }
    }
    assert contents[2]["parts"][0] == {
        "functionResponse": {
            "name": "filesystem.read_file",
            "response": {"result": "contenuto"},
        }
    }


def test_gemini_native_rejected(monkeypatch):
    install(monkeypatch, {}, status_code=404)

    with pytest.raises(NativeToolsUnavailable):
        gemini().native_step(
            [{"role": "user", "content": "x"}],
            make_registry(),
        )
