from __future__ import annotations

import json

from .core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from .core.tool_registry import ToolRegistry
from .core.permissions import Capability


class UnitConverterToolProvider:

    def __init__(
        self,
        unit_converter,
    ) -> None:

        self.unit_converter = unit_converter

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="units.convert",
                capabilities=Capability.CALCULATOR,
                description=(
                    "Convert a value "
                    "between compatible "
                    "measurement units."
                ),
                category="units",
                parameters=[
                    ToolParameter(
                        name="value",
                        param_type="number",
                        description=(
                            "Value to convert."
                        ),
                    ),
                    ToolParameter(
                        name="from_unit",
                        param_type="string",
                        description=(
                            "Source unit."
                        ),
                    ),
                    ToolParameter(
                        name="to_unit",
                        param_type="string",
                        description=(
                            "Destination unit."
                        ),
                    ),
                ],
                handler=self.convert,
            )
        )

    # ==========================================
    # Tool handlers
    # ==========================================

    def convert(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
    ) -> str:

        result = self.unit_converter.convert(
            value,
            from_unit,
            to_unit,
        )

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )