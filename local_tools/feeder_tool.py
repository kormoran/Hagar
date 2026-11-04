from __future__ import annotations

import json

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import (
    ToolRegistry,
)


class FeederToolProvider:

    def __init__(
        self,
        feeder,
    ) -> None:

        self.feeder = feeder

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="feed.read",
                capabilities=Capability.NETWORK,
                description=(
                    "Read an RSS or Atom "
                    "feed and return the "
                    "latest entries."
                ),
                category="feed",
                parameters=[
                    ToolParameter(
                        name="url",
                        param_type="string",
                        description=(
                            "Feed URL."
                        ),
                    ),
                    ToolParameter(
                        name="max_items",
                        param_type="integer",
                        description=(
                            "Maximum number of "
                            "items to return."
                        ),
                        required=False,
                        default=20,
                    ),
                ],
                handler=self.read,
            )
        )

    # ==========================================
    # Tool handlers
    # ==========================================

    def read(
        self,
        url: str,
        max_items: int = 20,
    ) -> str:

        result = self.feeder.read(
            url,
            max_items,
        )

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )