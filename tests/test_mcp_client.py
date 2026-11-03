"""Test di MCPClient con un trasporto HTTP finto (nessuna rete)."""

from __future__ import annotations

import json

import pytest
import requests

from core.permissions import Capability
from core.models import MCPAuthConfig
from core.tool_registry import ToolRegistry
from llm.mcp_client import (
    MCPClient,
    resolve_auth_headers,
)


class FakeResponse:
    def __init__(
        self,
        payload,
        status_code=200,
        headers=None,
        text="",
    ):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {
            "Content-Type": "application/json",
        }
        self.text = text

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

        item = self.responses.pop(0)

        if isinstance(item, FakeResponse):
            return item

        return FakeResponse(item)


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


def initialized(*responses):
    """Risposte per initialize + notifica, seguite da ``responses``."""

    return (
        {"result": {}},
        {},
        *responses,
    )


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
        {},
    )

    result = client.initialize()

    assert result["protocolVersion"] == "2025-03-26"
    assert client._initialized is True

    payload = http.calls[0]["payload"]

    assert payload["method"] == "initialize"
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    assert payload["params"]["protocolVersion"] == "2025-03-26"


def test_initialize_sends_initialized_notification(
    client,
    monkeypatch,
):
    http = install(
        monkeypatch,
        {"result": {}},
        {},
    )

    client.initialize()

    notification = http.calls[1]["payload"]

    assert notification["method"] == (
        "notifications/initialized"
    )
    assert notification["jsonrpc"] == "2.0"
    assert "id" not in notification


def test_ensure_initialized_runs_once(client, monkeypatch):
    http = install(
        monkeypatch,
        *initialized({"result": {"tools": []}}),
    )

    client.ensure_initialized()
    client.ensure_initialized()

    assert len(http.calls) == 2

    client.list_tools()

    assert len(http.calls) == 3


def test_request_ids_increment(client, monkeypatch):
    http = install(
        monkeypatch,
        *initialized(
            {"result": {"tools": []}},
            {"result": {"tools": []}},
        ),
    )

    client.list_tools()
    client.list_tools()

    assert [
        call["payload"].get("id")
        for call in http.calls
    ] == [1, None, 2, 3]


def test_sse_response_is_decoded(client, monkeypatch):
    event = (
        "event: message\n"
        'data: {"jsonrpc": "2.0", "id": 1, '
        '"result": {"protocolVersion": "sse"}}\n\n'
    )

    install(
        monkeypatch,
        FakeResponse(
            {},
            headers={
                "Content-Type": "text/event-stream",
            },
            text=event,
        ),
        {},
    )

    assert client.initialize()["protocolVersion"] == "sse"


def test_sse_without_matching_id_raises(
    client,
    monkeypatch,
):
    event = (
        'data: {"jsonrpc": "2.0", "id": 99, '
        '"result": {}}\n\n'
    )

    install(
        monkeypatch,
        FakeResponse(
            {},
            headers={
                "Content-Type": "text/event-stream",
            },
            text=event,
        ),
    )

    with pytest.raises(RuntimeError, match="SSE"):
        client.initialize()


# =====================================================
# Tool discovery / execution
# =====================================================


def test_list_tools(client, monkeypatch):
    tools = [{"name": "ping"}]

    install(
        monkeypatch,
        *initialized({"result": {"tools": tools}}),
    )

    assert client.list_tools() == tools


def test_list_tools_rejects_invalid_payload(
    client,
    monkeypatch,
):
    install(
        monkeypatch,
        *initialized(
            {"result": {"tools": {"name": "ping"}}}
        ),
    )

    with pytest.raises(RuntimeError, match="must be a list"):
        client.list_tools()


def test_call_tool(client, monkeypatch):
    http = install(
        monkeypatch,
        *initialized(
            {
                "result": {
                    "content": [
                        {"type": "text", "text": "pong"}
                    ]
                }
            }
        ),
    )

    result = client.call_tool(
        "ping",
        {"message": "ciao"},
    )

    assert result == "pong"

    payload = http.calls[-1]["payload"]

    assert payload["method"] == "tools/call"
    assert payload["params"] == {
        "name": "ping",
        "arguments": {"message": "ciao"},
    }


def test_text_blocks_are_joined(client, monkeypatch):
    install(
        monkeypatch,
        *initialized(
            {
                "result": {
                    "content": [
                        {"type": "text", "text": "A"},
                        {"type": "image", "data": "x"},
                        {"type": "text", "text": "B"},
                    ]
                }
            }
        ),
    )

    assert client.call_tool("ping", {}) == "A\nB"


def test_error_result_is_raised(client, monkeypatch):
    install(
        monkeypatch,
        *initialized(
            {
                "result": {
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "boom"}
                    ],
                }
            }
        ),
    )

    with pytest.raises(RuntimeError, match="boom"):
        client.call_tool("ping", {})


def test_structured_content_is_json(client, monkeypatch):
    install(
        monkeypatch,
        *initialized(
            {
                "result": {
                    "structuredContent": {"a": 1}
                }
            }
        ),
    )

    payload = client.call_tool("ping", {})

    assert json.loads(payload) == {"a": 1}


def test_result_without_text_is_json(client, monkeypatch):
    install(
        monkeypatch,
        *initialized(
            {
                "result": {
                    "content": [{"type": "image"}],
                    "meta": {"n": 1},
                }
            }
        ),
    )

    payload = client.call_tool("ping", {})

    decoded = json.loads(payload)

    assert decoded["meta"] == {"n": 1}


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
    http_error = FakeResponse({}, status_code=500)

    def fake_post(url, json=None, headers=None, timeout=None):
        return http_error

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(requests.HTTPError):
        client.initialize()


def test_headers_and_timeout(client, monkeypatch):
    http = install(
        monkeypatch,
        {"result": {}},
        {},
    )

    client.initialize()

    headers = http.calls[0]["headers"]

    assert "application/json" in headers["Accept"]
    assert "text/event-stream" in headers["Accept"]
    assert http.calls[0]["timeout"] == 30


# =====================================================
# Autenticazione
# =====================================================


def test_auth_headers_are_merged():
    client = MCPClient(
        endpoint="http://localhost:8080/mcp",
        namespace="gh",
        headers={
            "Authorization": "Bearer secret",
        },
    )

    headers = client._headers()

    assert headers["Authorization"] == "Bearer secret"
    assert "text/event-stream" in headers["Accept"]


def test_auth_headers_are_request_headers(
    monkeypatch,
):
    http = install(
        monkeypatch,
        {"result": {}},
        {},
    )

    client = MCPClient(
        endpoint="http://localhost:8080/mcp",
        namespace="gh",
        headers={
            "Authorization": "Bearer secret",
        },
    )

    client.initialize()

    assert (
        http.calls[0]["headers"]["Authorization"]
        == "Bearer secret"
    )


def test_headers_are_not_shared():
    client = MCPClient(
        endpoint="http://localhost:8080/mcp",
        namespace="gh",
    )

    headers = client._headers()
    headers["Authorization"] = "Bearer x"

    assert "Authorization" not in client._headers()


def test_resolve_bearer_headers(monkeypatch):
    monkeypatch.setenv("MCP_TOKEN", "secret")

    headers = resolve_auth_headers(
        MCPAuthConfig(
            type="bearer",
            token_env="MCP_TOKEN",
        )
    )

    assert headers == {
        "Authorization": "Bearer secret",
    }


def test_resolve_custom_header(monkeypatch):
    monkeypatch.setenv("MCP_KEY", "secret")

    headers = resolve_auth_headers(
        MCPAuthConfig(
            type="header",
            header="X-API-Key",
            token_env="MCP_KEY",
        )
    )

    assert headers == {"X-API-Key": "secret"}


def test_resolve_auth_requires_token(
    monkeypatch,
):
    monkeypatch.delenv("MCP_TOKEN", raising=False)

    with pytest.raises(
        ValueError,
        match="MCP_TOKEN",
    ):
        resolve_auth_headers(
            MCPAuthConfig(
                type="bearer",
                token_env="MCP_TOKEN",
            )
        )


def test_resolve_auth_rejects_non_ascii(
    monkeypatch,
):
    monkeypatch.setenv("MCP_TOKEN", "\u2022")

    with pytest.raises(
        ValueError,
        match="non-ASCII",
    ):
        resolve_auth_headers(
            MCPAuthConfig(
                type="bearer",
                token_env="MCP_TOKEN",
            )
        )


class FakeTokenProvider:
    def __init__(self):
        self.value = "old"
        self.refreshes = 0

    def token(self):
        return self.value

    def refresh(self):
        self.refreshes += 1
        self.value = "new"


def test_oauth_401_is_retried(monkeypatch):
    http = install(
        monkeypatch,
        FakeResponse({}, status_code=401),
        {"result": {}},
        {},
    )

    provider = FakeTokenProvider()

    client = MCPClient(
        endpoint="http://localhost:8080/mcp",
        namespace="gh",
        token_provider=provider,
    )

    client.initialize()

    assert provider.refreshes == 1

    assert http.calls[0]["headers"][
        "Authorization"
    ] == "Bearer old"

    assert http.calls[1]["headers"][
        "Authorization"
    ] == "Bearer new"

    assert http.calls[2]["headers"][
        "Authorization"
    ] == "Bearer new"


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
    assert tool.capabilities == Capability.MCP_CALL
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
        *initialized(
            {
                "result": {
                    "content": [
                        {"type": "text", "text": "ok"}
                    ]
                }
            }
        ),
    )

    tool = client.convert_tool({"name": "ping"})

    assert tool.handler(message="ciao") == "ok"

    call = http.calls[-1]["payload"]

    assert call["method"] == "tools/call"
    assert call["params"] == {
        "name": "ping",
        "arguments": {"message": "ciao"},
    }


def test_register_tools(client, monkeypatch):
    install(
        monkeypatch,
        *initialized(
            {
                "result": {
                    "tools": [
                        {"name": "ping"},
                        {"name": "echo"},
                    ]
                }
            }
        ),
    )

    registry = ToolRegistry()
    client.register_tools(registry)

    assert registry.tool_names() == [
        "mcp.gh.echo",
        "mcp.gh.ping",
    ]

    assert registry.get("mcp.gh.ping").category == "mcp"
