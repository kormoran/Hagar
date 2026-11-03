from __future__ import annotations

import json
import os
import requests

from typing import Any

from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry
from core.permissions import Capability


def resolve_auth_headers(
    auth: Any,
) -> dict[str, str]:
    """
    Traduce la configurazione auth in header HTTP.

    Il token si legge solo dall'ambiente; non viene mai registrato
    nell'audit né incluso nei messaggi d'errore.
    """

    if auth is None:
        return {}

    token = os.environ.get(
        auth.token_env,
        "",
    ).strip()

    if not token:

        raise ValueError(
            "MCP auth token missing: set the "
            f"{auth.token_env} environment variable"
        )

    if not token.isascii():

        raise ValueError(
            f"{auth.token_env} contains non-ASCII "
            "characters"
        )

    if auth.type == "bearer":

        return {
            "Authorization": f"Bearer {token}",
        }

    if auth.type == "header":

        return {
            auth.header: token,
        }

    raise ValueError(
        f"Unsupported MCP auth type: {auth.type}"
    )


class MCPClient:
    """
    MCP client (tool support only).

    Supported methods:

        initialize
        tools/list
        tools/call
    """

    def __init__(
        self,
        endpoint: str,
        namespace: str,
        timeout: int = 30,
        headers: dict[str, str] | None = None,
    ) -> None:

        if not isinstance(
            namespace,
            str,
        ) or not namespace.strip():

            raise ValueError(
                "namespace must be a non-empty string"
            )

        self.endpoint = endpoint.rstrip("/")

        self.namespace = namespace.strip()

        self.timeout = timeout

        self.headers = {
            "Accept":
                "application/json, text/event-stream",
        }

        if headers:
            self.headers.update(headers)

        self._request_id = 0

        self._initialized = False

    # ==================================================
    # JSON-RPC
    # ==================================================

    def _next_id(self) -> int:

        self._request_id += 1

        return self._request_id

    def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        request_id = self._next_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }

        if params is not None:
            payload["params"] = params

        response = requests.post(
            self.endpoint,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )

        response.raise_for_status()

        body = self._decode(
            response,
            request_id,
        )

        if not isinstance(body, dict):

            raise RuntimeError(
                "MCP response is not a JSON object"
            )

        if "error" in body:

            error = body["error"]

            if not isinstance(error, dict):

                raise RuntimeError(
                    f"MCP error: {error}"
                )

            raise RuntimeError(
                "MCP error "
                f"{error.get('code')}: "
                f"{error.get('message')}"
            )

        result = body.get(
            "result",
            {},
        )

        if not isinstance(result, dict):

            raise RuntimeError(
                "MCP response 'result' must be an object"
            )

        return result

    def _headers(self) -> dict[str, str]:

        return dict(self.headers)

    @staticmethod
    def _decode(
        response,
        request_id: int,
    ) -> Any:
        """
        Legge la risposta JSON-RPC, anche quando arriva in SSE.

        Il transport MCP "streamable HTTP" può rispondere con
        ``text/event-stream``: in quel caso si cerca l'evento con
        l'id della richiesta.
        """

        content_type = ""

        if getattr(response, "headers", None):

            content_type = response.headers.get(
                "Content-Type",
                "",
            )

        if "text/event-stream" not in content_type:

            return response.json()

        for line in response.text.splitlines():

            line = line.strip()

            if not line.startswith("data:"):
                continue

            payload = line[len("data:"):].strip()

            if not payload:
                continue

            try:

                message = json.loads(payload)

            except json.JSONDecodeError:

                continue

            if (
                isinstance(message, dict)
                and message.get("id") == request_id
            ):

                return message

        raise RuntimeError(
            "MCP: nessuna risposta JSON-RPC "
            "nello stream SSE"
        )

    def _notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:

        payload = {
            "jsonrpc": "2.0",
            "method": method,
        }

        if params is not None:
            payload["params"] = params

        response = requests.post(
            self.endpoint,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )

        response.raise_for_status()

    # ==================================================
    # MCP lifecycle
    # ==================================================

    def initialize(
        self,
    ) -> dict[str, Any]:

        result = self._request(
            "initialize",
            {
                "protocolVersion":
                    "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name":
                        "local-harness",
                    "version":
                        "0.1.0",
                },
            },
        )

        #
        # Notifica richiesta dal protocollo prima di usare i tool.
        #

        self._notify("notifications/initialized")

        self._initialized = True

        return result

    def ensure_initialized(
        self,
    ) -> None:

        if self._initialized:
            return

        self.initialize()

    # ==================================================
    # Tool discovery
    # ==================================================

    def list_tools(
        self,
    ) -> list[dict[str, Any]]:

        self.ensure_initialized()

        result = self._request(
            "tools/list"
        )

        tools = result.get(
            "tools",
            [],
        )

        if not isinstance(tools, list):

            raise RuntimeError(
                "MCP tools/list: 'tools' must be a list"
            )

        return tools

    # ==================================================
    # Tool execution
    # ==================================================

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:

        self.ensure_initialized()

        result = self._request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        return self._normalize_result(result)

    @staticmethod
    def _normalize_result(
        result: dict[str, Any],
    ) -> str:
        """
        Riduce il risultato MCP a testo, come i tool locali.

        Preferisce i blocchi ``text``; usa ``structuredContent`` o
        l'intero oggetto JSON come fallback. Un risultato con
        ``isError`` diventa un errore del tool.
        """

        texts: list[str] = []

        content = result.get("content")

        if isinstance(content, list):

            for item in content:

                if (
                    isinstance(item, dict)
                    and item.get("type") == "text"
                    and isinstance(item.get("text"), str)
                ):

                    texts.append(item["text"])

        message = "\n".join(texts)

        if result.get("isError"):

            raise RuntimeError(
                message or "MCP tool returned an error"
            )

        if message:
            return message

        structured = result.get(
            "structuredContent"
        )

        if structured is not None:

            return json.dumps(
                structured,
                ensure_ascii=False,
            )

        return json.dumps(
            result,
            ensure_ascii=False,
        )

    # ==================================================
    # Tool conversion
    # ==================================================

    def convert_tool(
        self,
        tool_data: dict[str, Any],
    ) -> ToolDefinition:

        parameters: list[
            ToolParameter
        ] = []

        schema = tool_data.get(
            "inputSchema",
            {},
        )

        properties = schema.get(
            "properties",
            {},
        )

        required = set(
            schema.get(
                "required",
                [],
            )
        )

        for (
            parameter_name,
            metadata,
        ) in properties.items():

            parameters.append(
                ToolParameter(
                    name=parameter_name,
                    param_type=metadata.get(
                        "type",
                        "string",
                    ),
                    description=metadata.get(
                        "description",
                        "",
                    ),
                    required=(
                        parameter_name
                        in required
                    ),
                )
            )

        remote_name = (
            tool_data["name"]
        )

        public_name = (
            f"mcp."
            f"{self.namespace}."
            f"{remote_name}"
        )

        return ToolDefinition(
            name=public_name,
            description=tool_data.get(
                "description",
                "",
            ),
            category="mcp",
            parameters=parameters,
            capabilities=Capability.MCP_CALL,
            origin=f"mcp.{self.namespace}",
            handler=self._build_handler(
                remote_name
            ),
        )

    # ==================================================
    # Registry integration
    # ==================================================

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        discovered_tools = (
            self.list_tools()
        )

        for tool_data in (
            discovered_tools
        ):

            registry.register(
                self.convert_tool(
                    tool_data
                )
            )

    # ==================================================
    # Internal helpers
    # ==================================================

    def _build_handler(
        self,
        remote_name: str,
    ):

        def handler(
            **kwargs,
        ) -> Any:

            return self.call_tool(
                remote_name,
                kwargs,
            )

        return handler