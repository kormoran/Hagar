"""Tool plugin per eseguire un subagente sincrono."""

from __future__ import annotations

import json

from core.permissions import Capability
from core.subagents import AgentSpec
from core.subagents import SubagentBusy
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry


class SubagentToolProvider:

    def __init__(self, manager) -> None:

        self.manager = manager

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="agent.run",
                description=(
                    "Run a synchronous read-only subagent on a "
                    "focused task. The subagent has its own LLM "
                    "client and no memory writes or confirmations."
                ),
                category="agent",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="task",
                        param_type="string",
                        description=(
                            "Focused task for the subagent."
                        ),
                    ),
                    ToolParameter(
                        name="context",
                        param_type="string",
                        description=(
                            "Optional context supplied by the parent."
                        ),
                        required=False,
                        default="",
                    ),
                ],
                handler=self.run,
            )
        )

    def run(
        self,
        task: str,
        context: str = "",
    ) -> str:

        try:
            result = self.manager.run(
                AgentSpec(
                    task=task,
                    context=context,
                )
            )

        except SubagentBusy as exc:

            return json.dumps(
                {
                    "status": "failed",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )

        return json.dumps(
            result.as_dict(),
            ensure_ascii=False,
            indent=2,
        )
