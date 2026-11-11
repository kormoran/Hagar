"""Tool per le boxed transform."""

from __future__ import annotations

import json

from core.boxes import BoxRunner
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


class BoxToolProvider:

    def __init__(
        self,
        runner: BoxRunner,
    ) -> None:

        self.runner = runner

    def register_tools(self, registry: ToolRegistry) -> None:

        registry.register(
            ToolDefinition(
                name="box.list",
                description=(
                    "List available bounded LLM transforms "
                    "(summarize, translate, extract_json)."
                ),
                category="box",
                capabilities=Capability.BOX_EXEC,
                parameters=[],
                handler=self.list_boxes,
            )
        )

        registry.register(
            ToolDefinition(
                name="box.run",
                description=(
                    "Run a bounded LLM transform on a sandbox file. "
                    "The model supplies a box name, input/output paths and "
                    "declared options; it cannot provide a free prompt."
                ),
                category="box",
                capabilities=Capability.BOX_EXEC,
                parameters=[
                    ToolParameter(
                        "box",
                        "string",
                        "Box name from box.list.",
                    ),
                    ToolParameter(
                        "input",
                        "string",
                        "Input file in the sandbox.",
                    ),
                    ToolParameter(
                        "output",
                        "string",
                        "Output file in the sandbox.",
                    ),
                    ToolParameter(
                        "options",
                        "object",
                        "Declared box options.",
                        required=False,
                        default=None,
                    ),
                ],
                handler=self.run_box,
            )
        )

    def list_boxes(self) -> str:
        return json.dumps(
            {"boxes": self.runner.list_boxes()},
            ensure_ascii=False,
            indent=2,
        )

    def run_box(
        self,
        box: str,
        input: str,
        output: str,
        options: dict | None = None,
    ) -> str:
        return json.dumps(
            self.runner.run(
                box,
                input,
                output,
                options,
            ),
            ensure_ascii=False,
            indent=2,
        )
