from __future__ import annotations

import json

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry

from MCP_tools.calculator import Calculator
from MCP_tools.statistics import Stats_calc


class MathToolsProvider:

    def __init__(
        self,
        calculator: Calculator,
        statistics: Stats_calc,
    ) -> None:

        self.calculator = calculator
        self.statistics = statistics

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="statistics.compute",
                capabilities=Capability.COMPUTE,
                description=(
                    "Compute statistics on "
                    "a collection of values."
                ),
                category="statistics",
                parameters=[
                    ToolParameter(
                        name="operation",
                        param_type="string",
                        description=(
                            "Statistic operation "
                            "(mean, median, stdev, "
                            "variance, min, max, "
                            "sum, count)."
                        ),
                    ),
                    ToolParameter(
                        name="values",
                        param_type="array",
                        description=(
                            "List of numeric values."
                        ),
                    ),
                ],
                handler=self.compute_statistics,
            )
        )

        registry.register(
            ToolDefinition(
                name="calculator.evaluate",
                capabilities=Capability.COMPUTE,
                description=(
                    "Evaluate a mathematical "
                    "expression safely."
                ),
                category="calculator",
                parameters=[
                    ToolParameter(
                        name="expression",
                        param_type="string",
                        description=(
                            "Mathematical expression "
                            "to evaluate."
                        ),
                    )
                ],
                handler=self.evaluate,
            )
        )

    # ==========================================
    # Tool handlers
    # ==========================================

    def evaluate(
        self,
        expression: str,
    ) -> str:

        result = self.calculator.evaluate(
            expression
        )

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )

    def compute_statistics(
        self,
        operation: str,
        values: list,
    ) -> str:

        result = self.statistics.compute(
            operation,
            values,
        )

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
