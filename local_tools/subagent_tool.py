"""Tool plugin per subagenti asincroni."""

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
                name="agent.spawn",
                description=(
                    "Start a read-only subagent on a focused task. "
                    "The subagent gets a private workspace with copies "
                    "of the listed input files. Returns immediately."
                ),
                category="agent",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="task",
                        param_type="string",
                        description="Focused task.",
                    ),
                    ToolParameter(
                        name="context",
                        param_type="string",
                        description="Optional context.",
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        name="inputs",
                        param_type="array",
                        description=(
                            "Input file paths in the parent workspace, "
                            "to copy into the subagent workspace."
                        ),
                        required=False,
                        default=[],
                    ),
                ],
                handler=self.spawn,
            )
        )

        registry.register(
            ToolDefinition(
                name="agent.status",
                description=(
                    "Return the status and usage of a subagent."
                ),
                category="agent",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="agent_id",
                        param_type="string",
                        description="Subagent id.",
                    ),
                ],
                handler=self.status,
            )
        )

        registry.register(
            ToolDefinition(
                name="agent.wait",
                description=(
                    "Wait for a subagent, up to timeout seconds."
                ),
                category="agent",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="agent_id",
                        param_type="string",
                        description="Subagent id.",
                    ),
                    ToolParameter(
                        name="timeout",
                        param_type="number",
                        description="Seconds to wait.",
                        required=False,
                        default=30,
                    ),
                ],
                handler=self.wait,
            )
        )

        registry.register(
            ToolDefinition(
                name="agent.result",
                description=(
                    "Return the result of a completed subagent."
                ),
                category="agent",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="agent_id",
                        param_type="string",
                        description="Subagent id.",
                    ),
                ],
                handler=self.result,
            )
        )

        registry.register(
            ToolDefinition(
                name="agent.cancel",
                description="Request cancellation of a subagent.",
                category="agent",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="agent_id",
                        param_type="string",
                        description="Subagent id.",
                    ),
                ],
                handler=self.cancel,
            )
        )

        registry.register(
            ToolDefinition(
                name="agent.run",
                description=(
                    "Synchronous compatibility helper: spawn and wait."
                ),
                category="agent",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="task",
                        param_type="string",
                        description="Focused task.",
                    ),
                    ToolParameter(
                        name="context",
                        param_type="string",
                        description="Optional context.",
                        required=False,
                        default="",
                    ),
                ],
                handler=self.run,
            )
        )

    @staticmethod
    def _dump(value) -> str:

        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        )

    def spawn(
        self,
        task: str,
        context: str = "",
        inputs=None,
    ) -> str:

        if inputs is None:
            inputs = []

        if not isinstance(inputs, list):

            return self._dump({
                "status": "failed",
                "error": "inputs must be a list",
            })

        try:
            agent_id = self.manager.spawn(
                AgentSpec(
                    task=task,
                    context=context,
                    inputs=tuple(str(value) for value in inputs),
                )
            )

        except SubagentBusy as exc:

            return self._dump({
                "status": "failed",
                "error": str(exc),
            })

        return self._dump({
            "agent_id": agent_id,
            "status": "running",
        })

    def status(self, agent_id: str) -> str:

        try:
            data = self.manager.status(agent_id)
        except KeyError as exc:
            return self._dump({
                "status": "failed",
                "error": str(exc),
            })

        return self._dump(data)

    def wait(
        self,
        agent_id: str,
        timeout: float = 30,
    ) -> str:

        try:
            result = self.manager.wait(
                agent_id,
                timeout=float(timeout),
            )
        except KeyError as exc:
            return self._dump({
                "status": "failed",
                "error": str(exc),
            })

        if result is None:
            return self._dump({
                "agent_id": agent_id,
                "status": "timeout",
            })

        return self._dump(result.as_dict())

    def result(self, agent_id: str) -> str:

        result = self.manager.result(agent_id)

        if result is not None:
            return self._dump(result.as_dict())

        return self.status(agent_id)

    def cancel(self, agent_id: str) -> str:

        return self._dump({
            "agent_id": agent_id,
            "cancelled": self.manager.cancel(agent_id),
        })

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

            return self._dump({
                "status": "failed",
                "error": str(exc),
            })

        return self._dump(result.as_dict())
