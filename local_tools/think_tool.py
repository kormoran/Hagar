from __future__ import annotations

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry

from local_tools.think import Think


class ThinkToolProvider:

    def __init__(
        self,
        think: Think,
    ) -> None:

        self.think = think

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="think.echo",
                description=(
                    "Echo the given thought back unchanged. "
                    "Use it to externalize an intermediate "
                    "step during long reasoning chains."
                ),
                category="think",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="thought",
                        param_type="string",
                        description=(
                            "Text to echo back unchanged."
                        ),
                    ),
                ],
                handler=self.echo,
            )
        )

    def echo(
        self,
        thought: str,
    ) -> str:

        return self.think.echo(thought)
