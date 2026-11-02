from __future__ import annotations

import requests

from typing import Any

from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


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
    ) -> None:

        self.endpoint = endpoint.rstrip("/")

        self.namespace = namespace

        self.timeout = timeout

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

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }

        if params is not None:
            payload["params"] = params

        response = requests.post(
            self.endpoint,
            json=payload,
            headers={
                "Accept":
                    "application/json, "
                    "text/event-stream"
            },
            timeout=self.timeout,
        )

        response.raise_for_status()

        body = response.json()

        if "error" in body:

            error = body["error"]

            raise RuntimeError(
                "MCP error "
                f"{error.get('code')}: "
                f"{error.get('message')}"
            )

        return body.get(
            "result",
            {},
        )

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

        return result.get(
            "tools",
            [],
        )

    # ==================================================
    # Tool execution
    # ==================================================

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:

        self.ensure_initialized()

        result = self._request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        return result

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