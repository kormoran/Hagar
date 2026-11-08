"""Tool della classe ``decision``: scelta strutturata, non generativa."""

from __future__ import annotations

import json

from core.decisions import DecisionError
from core.decisions import DecisionRegistry
from core.decisions import DecisionRequest
from core.permissions import Capability
from core.tool_definition import ToolDefinition
from core.tool_definition import ToolParameter
from core.tool_registry import ToolRegistry


class DecisionToolProvider:
    """Registra ``decision.choose`` su un registry di provider."""

    def __init__(
        self,
        decisions: DecisionRegistry,
        audit=None,
    ) -> None:
        self.decisions = decisions
        self.audit = audit

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="decision.choose",
                description=(
                    "Ask a decision model or local classifier to choose "
                    "one label from a fixed set. Returns the chosen label, "
                    "calibrated probabilities and the provider used. Use it "
                    "for classification, routing, judging or guardrails."
                ),
                category="decision",
                capabilities=Capability.DECISION,
                parameters=[
                    ToolParameter(
                        name="state",
                        param_type="string",
                        description="Input text or state to classify.",
                    ),
                    ToolParameter(
                        name="question",
                        param_type="string",
                        description="Decision question.",
                    ),
                    ToolParameter(
                        name="choices",
                        param_type="array",
                        description="Allowed labels.",
                    ),
                    ToolParameter(
                        name="provider",
                        param_type="string",
                        description="Optional provider name.",
                        required=False,
                        default=None,
                    ),
                ],
                handler=self.choose,
            )
        )

    def choose(
        self,
        state: str,
        question: str,
        choices,
        provider: str | None = None,
    ) -> str:

        if (
            not isinstance(choices, (list, tuple))
            or not choices
            or not all(
                isinstance(item, str) and item.strip()
                for item in choices
            )
        ):
            raise DecisionError(
                "choices must be a non-empty list of strings"
            )

        request = DecisionRequest(
            state=state,
            question=question,
            choices=tuple(item.strip() for item in choices),
        )
        result = self.decisions.choose(
            request,
            provider=provider,
        )

        if self.audit is not None:

            self.audit.record(
                "decision.result",
                provider=result.provider,
                model=result.model,
                choice=result.choice,
                confidence=result.confidence,
                choices=list(request.choices),
            )

        return json.dumps(
            result.as_dict(),
            ensure_ascii=False,
        )
