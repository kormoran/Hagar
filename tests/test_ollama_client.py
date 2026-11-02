"""Test di OllamaClient: parsing robusto e payload HTTP (nessuna rete)."""

from __future__ import annotations

import pytest
import requests

from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry
from llm.ollama_client import OllamaClient


@pytest.fixture
def client() -> OllamaClient:
    return OllamaClient(
        host="http://localhost:11434/",
        model="test-model",
    )


def make_registry() -> ToolRegistry:

    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="filesystem.read_file",
            description="Legge un file.",
            category="filesystem",
            parameters=[
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Percorso del file.",
                )
            ],
            handler=lambda path: path,
        )
    )

    return registry


# =====================================================
# Configurazione
# =====================================================


def test_host_trailing_slash_is_removed(client):
    assert client.host == "http://localhost:11434"


def test_model_and_timeout(client):
    assert client.model == "test-model"
    assert client.timeout == 120


# =====================================================
# Parsing delle risposte del modello
# =====================================================


def test_parse_plain_json(client):
    call = client._parse_tool_call(
        '{"tool": "a.b", "arguments": {"x": 1}}'
    )

    assert call.tool == "a.b"
    assert call.arguments == {"x": 1}


def test_parse_fenced_json(client):
    text = (
        "Ecco la chiamata:\n"
        "```json\n"
        '{"tool": "a.b", "arguments": {"x": 1}}\n'
        "```\n"
    )

    call = client._parse_tool_call(text)

    assert call.tool == "a.b"
    assert call.arguments == {"x": 1}


def test_parse_fenced_without_language(client):
    text = '```\n{"tool": "a.b", "arguments": {}}\n```'

    assert client._parse_tool_call(text).tool == "a.b"


def test_parse_json_inside_prose(client):
    text = (
        'Devo usare {"tool": "a.b", "arguments": '
        '{"x": "y"}} adesso.'
    )

    call = client._parse_tool_call(text)

    assert call.tool == "a.b"
    assert call.arguments == {"x": "y"}


def test_parse_null_tool(client):
    call = client._parse_tool_call(
        '{"tool": null, "arguments": {}}'
    )

    assert call.tool is None
    assert call.arguments == {}


def test_parse_missing_arguments(client):
    call = client._parse_tool_call('{"tool": "a.b"}')

    assert call.arguments == {}


def test_parse_nested_arguments_and_unicode(client):
    text = (
        '{"tool": "w", "arguments": '
        '{"content": "città {ok}", "meta": {"n": 1}}}'
    )

    call = client._parse_tool_call(text)

    assert call.arguments == {
        "content": "città {ok}",
        "meta": {"n": 1},
    }


def test_parse_rejects_non_object_root(client):
    with pytest.raises(RuntimeError, match="Unable to extract"):
        client._parse_tool_call("[1, 2]")


def test_parse_rejects_arguments_not_object(client):
    with pytest.raises(RuntimeError, match="Unable to extract"):
        client._parse_tool_call(
            '{"tool": "a", "arguments": []}'
        )


def test_parse_rejects_tool_not_string(client):
    with pytest.raises(RuntimeError, match="Unable to extract"):
        client._parse_tool_call(
            '{"tool": 7, "arguments": {}}'
        )


def test_parse_without_json_raises(client):
    with pytest.raises(RuntimeError, match="Unable to extract"):
        client._parse_tool_call("nessun json qui")


def test_extract_first_json_object_ignores_invalid_prefix(client):
    text = "{non valido} poi {\"ok\": 1}"

    assert client._extract_first_json_object(
        text
    ) == '{"ok": 1}'


def test_extract_returns_none_without_object(client):
    assert client._extract_first_json_object("niente") is None


def test_parse_parameters_alias(client):
    #
    # qwen3 usa "parameters" invece di "arguments".
    #

    call = client._parse_tool_call(
        '{"tool": "a.b", "parameters": {"x": 1}}'
    )

    assert call.tool == "a.b"
    assert call.arguments == {"x": 1}


def test_parse_arguments_win_over_parameters(client):
    call = client._parse_tool_call(
        '{"tool": "a.b", "arguments": {"x": 1}, '
        '"parameters": {"y": 2}}'
    )

    assert call.arguments == {"x": 1}


def test_parse_null_arguments(client):
    call = client._parse_tool_call(
        '{"tool": null, "arguments": null}'
    )

    assert call.tool is None
    assert call.arguments == {}


def test_prompt_forbids_direct_answers(client, monkeypatch):
    captured = {}

    def fake_chat(messages):
        captured["system"] = messages[0]["content"]
        return '{"tool": null, "arguments": {}}'

    monkeypatch.setattr(client, "chat", fake_chat)

    client.request_tool_call(
        [{"role": "user", "content": "x"}],
        make_registry(),
    )

    assert "'arguments'" in captured["system"]
    assert "Never answer" in captured["system"]


def test_invalid_response_is_repaired(client, monkeypatch):
    replies = iter(
        [
            "Ho letto il file, ecco il riassunto.",
            '{"tool": "filesystem.read_file", '
            '"arguments": {"path": "a.txt"}}',
        ]
    )
    seen = []

    def fake_chat(messages):
        seen.append(messages)
        return next(replies)

    monkeypatch.setattr(client, "chat", fake_chat)

    call = client.request_tool_call(
        [{"role": "user", "content": "leggi a.txt"}],
        make_registry(),
    )

    assert call.tool == "filesystem.read_file"
    assert call.arguments == {"path": "a.txt"}
    assert len(seen) == 2

    repair_messages = seen[1]
    assert repair_messages[-2]["role"] == "assistant"
    assert "Ho letto il file" in repair_messages[-2]["content"]
    assert repair_messages[-1]["role"] == "user"
    assert "SOLO" in repair_messages[-1]["content"]


def test_repair_failure_raises_with_both_responses(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        client,
        "chat",
        lambda messages: "sempre prosa, mai JSON",
    )

    with pytest.raises(
        RuntimeError,
        match="Repair response",
    ):
        client.request_tool_call(
            [{"role": "user", "content": "x"}],
            make_registry(),
        )


# =====================================================
# HTTP
# =====================================================


def test_generate_payload(client, monkeypatch):
    captured = {}

    def fake_post(endpoint, payload):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"response": "ciao"}

    monkeypatch.setattr(client, "_post", fake_post)

    assert client.generate(
        "prompt",
        system_prompt="sistema",
    ) == "ciao"

    assert captured["endpoint"] == "/api/generate"
    assert captured["payload"] == {
        "model": "test-model",
        "prompt": "prompt",
        "stream": False,
        "system": "sistema",
    }


def test_generate_without_system_prompt(client, monkeypatch):
    captured = {}

    def fake_post(endpoint, payload):
        captured["payload"] = payload
        return {"response": "ciao"}

    monkeypatch.setattr(client, "_post", fake_post)

    client.generate("prompt")

    assert "system" not in captured["payload"]


def test_chat_payload(client, monkeypatch):
    captured = {}

    def fake_post(endpoint, payload):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"message": {"content": "risposta"}}

    monkeypatch.setattr(client, "_post", fake_post)

    messages = [{"role": "user", "content": "ciao"}]

    assert client.chat(messages) == "risposta"

    assert captured["endpoint"] == "/api/chat"
    assert captured["payload"]["messages"] == messages
    assert captured["payload"]["stream"] is False


def test_chat_missing_field_raises(client, monkeypatch):
    monkeypatch.setattr(
        client,
        "_post",
        lambda endpoint, payload: {},
    )

    with pytest.raises(KeyError):
        client.chat([{"role": "user", "content": "x"}])


def test_post_raises_on_http_error(client, monkeypatch):
    class Response:
        def raise_for_status(self):
            raise requests.HTTPError("500")

    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: Response(),
    )

    with pytest.raises(requests.HTTPError):
        client.generate("prompt")


# =====================================================
# Tool rendering / request_tool_call
# =====================================================


def test_render_tools_for_prompt(client):
    text = client._render_tools_for_prompt(
        make_registry()
    )

    assert "Name: filesystem.read_file" in text
    assert "Category: filesystem" in text
    assert "Legge un file." in text
    assert "- path (string) [required]" in text


def test_render_tools_without_tools(client):
    assert client._render_tools_for_prompt(
        ToolRegistry()
    ) == "No tools."


def test_request_tool_call_sends_description_and_parses(
    client,
    monkeypatch,
):
    captured = {}

    def fake_chat(messages):
        captured["messages"] = messages
        return '{"tool": "filesystem.read_file", "arguments": {"path": "a.txt"}}'

    monkeypatch.setattr(client, "chat", fake_chat)

    call = client.request_tool_call(
        [{"role": "user", "content": "leggi a.txt"}],
        make_registry(),
    )

    assert call.tool == "filesystem.read_file"
    assert call.arguments == {"path": "a.txt"}

    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert "filesystem.read_file" in messages[0]["content"]
    assert messages[-1]["content"] == "leggi a.txt"
