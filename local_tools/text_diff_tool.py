from __future__ import annotations

import json

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry

from local_tools.text_diff import TextDiff


class TextDiffToolProvider:

    def __init__(
        self,
        text_diff: TextDiff,
    ) -> None:

        self.text_diff = text_diff

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="text.diff",
                description=(
                    "Return a unified diff between two texts. "
                    "Use it to compare versions or outputs; "
                    "the diff is not applied."
                ),
                category="text",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="left",
                        param_type="string",
                        description="Original text.",
                    ),
                    ToolParameter(
                        name="right",
                        param_type="string",
                        description="New text.",
                    ),
                    ToolParameter(
                        name="context",
                        param_type="integer",
                        description=(
                            "Context lines, 0..10 (default 3)."
                        ),
                        required=False,
                        default=3,
                    ),
                ],
                handler=self.compare,
            )
        )

    def compare(
        self,
        left: str,
        right: str,
        context: int = 3,
    ) -> str:

        return json.dumps(
            self.text_diff.compare(
                left,
                right,
                context,
            ),
            ensure_ascii=False,
            indent=2,
        )
