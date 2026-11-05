from __future__ import annotations

import json

from core.permissions import Capability
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry

from local_tools.clock import Clock


class ClockToolProvider:

    def __init__(
        self,
        clock: Clock,
    ) -> None:

        self.clock = clock

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="clock.now",
                description=(
                    "Return the current local time, date and "
                    "timezone of the host running Hagar."
                ),
                category="clock",
                capabilities=Capability.COMPUTE,
                parameters=[],
                handler=self.now,
            )
        )

    def now(self) -> str:

        return json.dumps(
            self.clock.now(),
            ensure_ascii=False,
            indent=2,
        )
