"""Tool del DSL Hagar Flow."""

from __future__ import annotations

import json

from core.flow import (
    FlowRunner,
    FlowValidationError,
    LANGUAGE_CARD,
    validate,
)
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


class FlowToolProvider:

    def __init__(
        self,
        runner: FlowRunner,
    ) -> None:

        self.runner = runner

    def register_tools(self, registry: ToolRegistry) -> None:

        registry.register(
            ToolDefinition(
                name="flow.reference",
                description=(
                    "Restituisce il riferimento compatto di Hagar Flow: "
                    "sintassi consentita, primitive e limiti."
                ),
                category="flow",
                capabilities=Capability.FLOW_EXEC,
                parameters=[],
                handler=self.reference,
            )
        )

        registry.register(
            ToolDefinition(
                name="flow.validate",
                description=(
                    "Valida codice Hagar Flow senza eseguirlo. "
                    "Hagar Flow è un sottoinsieme lineare di Python: "
                    "niente import, class, def, lambda, try, comprehension "
                    "o accesso a oggetti Python."
                ),
                category="flow",
                capabilities=Capability.FLOW_EXEC,
                parameters=[
                    ToolParameter(
                        "code",
                        "string",
                        "Sorgente Hagar Flow.",
                    )
                ],
                handler=self.validate_code,
            )
        )

        registry.register(
            ToolDefinition(
                name="flow.run",
                description=(
                    "Esegue codice Hagar Flow, un sottoinsieme lineare e "
                    "ristretto di Python. Non è Python: niente import, "
                    "class, def, lambda, try, comprehension o accesso a "
                    "oggetti. Usa solo le primitive elencate da "
                    "flow.reference. Se la validazione fallisce, correggi "
                    "il codice in base all'errore."
                ),
                category="flow",
                capabilities=Capability.FLOW_EXEC,
                parameters=[
                    ToolParameter(
                        "code",
                        "string",
                        (
                            "Sorgente Hagar Flow. Sintassi Python ristretta; "
                            "nessun import."
                        ),
                    )
                ],
                handler=self.run_code,
            )
        )

    def reference(self) -> str:
        lines = []

        for name in sorted(self.runner.primitives):
            tool = self.runner.registry.get(name)
            parameters = ", ".join(
                (
                    parameter.name
                    if parameter.required
                    else f"{parameter.name}={parameter.default!r}"
                )
                for parameter in tool.parameters
            )
            lines.append(
                f"- {name}({parameters}): {tool.description}"
            )

        return (
            LANGUAGE_CARD
            + "\nPRIMITIVE DISPONIBILI:\n"
            + ("\n".join(lines) or "- nessuna")
            + "\n"
        )

    def validate_code(self, code: str) -> str:
        try:
            validate(
                code,
                self.runner.primitives,
                max_source_chars=self.runner.config.max_source_chars,
            )
        except FlowValidationError as exc:
            return json.dumps(
                {"ok": False, "error": exc.as_dict()},
                ensure_ascii=False,
                indent=2,
            )

        return json.dumps(
            {"ok": True, "error": None},
            ensure_ascii=False,
        )

    def run_code(self, code: str) -> str:
        result = self.runner.run(code)
        return json.dumps(
            {
                "ok": result.ok,
                "result": result.result,
                "error": result.error,
                "steps": result.steps,
                "tool_calls": result.tool_calls,
                "duration_ms": result.duration_ms,
                "trace": result.trace,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
