from __future__ import annotations

from typing import Any

from .tool_definition import ToolDefinition


class ToolRegistry:
    """
    Registry of all tools available to the agent.

    Responsibilities:
        - register tool definitions
        - list available tools
        - execute tools
        - enable/disable tools
        - provide metadata to the LLM
    """

    def __init__(self) -> None:

        self._tools: dict[
            str,
            ToolDefinition
        ] = {}

    # ==================================================
    # Registration
    # ==================================================

    def register(
        self,
        tool: ToolDefinition,
    ) -> None:

        if tool.name in self._tools:

            raise RuntimeError(
                f"tool already registered: "
                f"{tool.name}"
            )

        self._tools[tool.name] = tool

    def unregister(
        self,
        name: str,
    ) -> None:

        self._tools.pop(
            name,
            None,
        )

    # ==================================================
    # Lookup
    # ==================================================

    def exists(
        self,
        name: str,
    ) -> bool:

        return name in self._tools

    def get(
        self,
        name: str,
    ) -> ToolDefinition:

        tool = self._tools.get(name)

        if tool is None:

            raise RuntimeError(
                f"unknown tool: {name}"
            )

        return tool

    def tool_names(
        self,
    ) -> list[str]:

        return sorted(
            self._tools.keys()
        )

    # ==================================================
    # Enable / Disable
    # ==================================================

    def enable(
        self,
        name: str,
    ) -> None:

        self.get(name).enabled = True

    def disable(
        self,
        name: str,
    ) -> None:

        self.get(name).enabled = False

    def is_enabled(
        self,
        name: str,
    ) -> bool:

        return self.get(name).enabled

    # ==================================================
    # Metadata
    # ==================================================


    def list_definitions(
        self,
    ) -> list[ToolDefinition]:

        return [
            tool
            for tool in self._tools.values()
            if tool.enabled
        ]

    def list_tools(
        self,
    ) -> list[dict[str, Any]]:

        result = []

        for tool in self._tools.values():

            if not tool.enabled:
                continue

            result.append(
                {
                    "name": tool.name,
                    "description": (
                        tool.description
                    ),
                    "category": (
                        tool.category
                    ),
                    "requires_confirmation": (
                        tool.requires_confirmation
                    ),
                }
            )

        return result

    def tools_by_category(
        self,
        category: str,
    ) -> list[ToolDefinition]:

        return [
            tool
            for tool in self._tools.values()
            if (
                tool.category == category
                and tool.enabled
            )
        ]

    # ==================================================
    # Execution
    # ==================================================

    def execute(
        self,
        name: str,
        **kwargs,
    ) -> Any:

        tool = self.get(name)

        if not tool.enabled:

            raise RuntimeError(
                f"tool disabled: {name}"
            )

        return tool.handler(
            **kwargs
        )