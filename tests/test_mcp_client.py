"""Test di MCPClient con un trasporto HTTP finto (nessuna rete)."""

from __future__ import annotations

import pytest
import requests

from core.tool_registry import ToolRegistry
from llm.mcp_client import MCPClient


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
    """Sostituisce requests.post e registra le chiamate."""

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
                "payload": json,
                "headers": headers,
                "timeout": timeout,
            }
        )

        if not self.responses:
            raise AssertionError(
                "richiesta HTTP inattesa"
            )

        return FakeResponse(self.responses.pop(0))


@pytest.fixture
def client() -> MCPClient:
    return MCPClient(
        endpoint="http://localhost:8080/mcp/",
        namespace="gh",
    )


def install(
    monkeypatch,
    *responses,
) -> FakeHTTP:

    http = FakeHTTP(*responses)
    monkeypatch.setattr(requests, "post", http)
    return http


# =====================================================
# Configurazione
# =====================================================


def test_endpoint_is_normalized(client):
    assert client.endpoint == "http://localhost:8080/mcp"


def test_namespace_is_required():
    with pytest.raises(ValueError):
        MCPClient("http://x", "")

    with pytest.raises(ValueError):
        MCPClient("http://x", "   ")


# =====================================================
# Lifecycle
# =====================================================


def test_initialize(client, monkeypatch):
    http = install(
        monkeypatch,
        {"result": {"protocolVersion": "2025-03-26"}},
    )

    result = client.initialize()

    assert result["protocolVersion"] == "2025-03-26"
    assert client._initialized is True

    payload = http.calls[0]["payload"]

    assert payload["method"] == "initialize"
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    assert payload["params"]["protocolVersion"] == "2025-03-26"


def test_ensure_initialized_runs_once(client, monkeypatch):
    http = install(
        monkeypatch,
        {"result": {}},
        {"result": {"tools": []}},
    )

    client.ensure_initialized()
    client.ensure_initialized()

    assert len(http.calls) == 1

    client.list_tools()

    assert len(http.calls) == 2


def test_request_ids_increment(client, monkeypatch):
    http = install(
        monkeypatch,
        {"result": {}},
        {"result": {"tools": []}},
        {"result": {"tools": []}},
    )

    client.list_tools()
    client.list_tools()

    assert [
        call["payload"]["id"]
        for call in http.calls
    ] == [1, 2, 3]


# =====================================================
# Tool discovery / execution
# =====================================================


def test_list_tools(client, monkeypatch):
    tools = [{"name": "ping"}]

    install(
        monkeypatch,
        {"result": {}},
        {"result": {"tools": tools}},
    )

    assert client.list_tools() == tools


def test_list_tools_rejects_invalid_payload(
    client,
    monkeypatch,
):
    install(
        monkeypatch,
        {"result": {}},
        {"result": {"tools": {"name": "ping"}}},
    )

    with pytest.raises(RuntimeError, match="must be a list"):
        client.list_tools()


def test_call_tool(client, monkeypatch):
    http = install(
        monkeypatch,
        {"result": {}},
        {"result": {"content": "pong"}},
    )

    result = client.call_tool(
        "ping",
        {"message": "ciao"},
    )

    assert result == {"content": "pong"}

    payload = http.calls[-1]["payload"]

    assert payload["method"] == "tools/call"
    assert payload["params"] == {
        "name": "ping",
        "arguments": {"message": "ciao"},
    }


def test_jsonrpc_error_is_raised(client, monkeypatch):
    install(
        monkeypatch,
        {
            "error": {
                "code": -32601,
                "message": "Method not found",
            }
        },
    )

    with pytest.raises(RuntimeError, match="Method not found"):
        client.initialize()


def test_malformed_error_is_raised(client, monkeypatch):
    install(monkeypatch, {"error": "boom"})

    with pytest.raises(RuntimeError, match="boom"):
        client.initialize()


def test_non_object_response_is_rejected(client, monkeypatch):
    install(monkeypatch, [{"result": {}}])

    with pytest.raises(RuntimeError, match="JSON object"):
        client.initialize()


def test_result_must_be_object(client, monkeypatch):
    install(monkeypatch, {"result": []})

    with pytest.raises(RuntimeError, match="'result'"):
        client.initialize()


def test_http_error_is_raised(client, monkeypatch):
    http = FakeHTTP()
    http.responses.append({"result": {}})
    http_error = FakeResponse({}, status_code=500)

    def fake_post(url, json=None, headers=None, timeout=None):
        http.calls.append({"payload": json})
        return http_error

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(requests.HTTPError):
        client.initialize()


def test_headers_and_timeout(client, monkeypatch):
    http = install(monkeypatch, {"result": {}})

    client.initialize()

    headers = http.calls[0]["headers"]

    assert "application/json" in headers["Accept"]
    assert "text/event-stream" in headers["Accept"]
    assert http.calls[0]["timeout"] == 30


# =====================================================
# Conversione in ToolDefinition
# =====================================================


def test_convert_tool(client):
    tool = client.convert_tool(
        {
            "name": "create_issue",
            "description": "Crea una issue.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Titolo",
                    },
                    "body": {"type": "string"},
                },
                "required": ["title"],
            },
        }
    )

    assert tool.name == "mcp.gh.create_issue"
    assert tool.category == "mcp"
    assert tool.origin == "mcp.gh"
    assert tool.description == "Crea una issue."

    assert [p.name for p in tool.parameters] == [
        "title",
        "body",
    ]
    assert tool.parameters[0].required is True
    assert tool.parameters[0].param_type == "string"
    assert tool.parameters[0].description == "Titolo"
    assert tool.parameters[1].required is False


def test_convert_tool_without_schema(client):
    tool = client.convert_tool({"name": "ping"})

    assert tool.name == "mcp.gh.ping"
    assert tool.parameters == []
    assert tool.description == ""


def test_convert_tool_handler_calls_remote(client, monkeypatch):
    http = install(
        monkeypatch,
        {"result": {}},
        {"result": {"content": "ok"}},
    )

    tool = client.convert_tool({"name": "ping"})

    assert tool.handler(message="ciao") == {"content": "ok"}

    call = http.calls[-1]["payload"]

    assert call["method"] == "tools/call"
    assert call["params"] == {
        "name": "ping",
        "arguments": {"message": "ciao"},
    }


def test_register_tools(client, monkeypatch):
    install(
        monkeypatch,
        {"result": {}},
        {
            "result": {
                "tools": [
                    {"name": "ping"},
                    {"name": "echo"},
                ]
            }
        },
    )

    registry = ToolRegistry()
    client.register_tools(registry)

    assert registry.tool_names() == [
        "mcp.gh.echo",
        "mcp.gh.ping",
    ]

    assert registry.get("mcp.gh.ping").category == "mcp"
