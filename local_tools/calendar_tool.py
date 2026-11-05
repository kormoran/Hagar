from __future__ import annotations

import json

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry

from local_tools.calendar import Calendar


class CalendarToolProvider:

    def __init__(
        self,
        calendar: Calendar,
    ) -> None:

        self.calendar = calendar

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="calendar.date",
                description=(
                    "Return the current date in the Julian or "
                    "Islamic calendar. The model chooses the "
                    "calendar with the 'calendar' argument."
                ),
                category="calendar",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="calendar",
                        param_type="string",
                        description=(
                            "'julian' or 'islamic'."
                        ),
                    ),
                    ToolParameter(
                        name="date",
                        param_type="string",
                        description=(
                            "Optional Gregorian date in "
                            "YYYY-MM-DD format; default today."
                        ),
                        required=False,
                        default="",
                    ),
                ],
                handler=self.date,
            )
        )

    def date(
        self,
        calendar: str,
        date: str = "",
    ) -> str:

        return json.dumps(
            self.calendar.convert(calendar, date),
            ensure_ascii=False,
            indent=2,
        )
