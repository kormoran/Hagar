"""Tool del DSL Hagar Flow."""

from __future__ import annotations

import json

from core.flow import (
    FlowRunner,
    FlowValidationError,
    LANGUAGE_CARD,
    validate,
)
from core.flow.repair import FlowRepairer
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


class FlowToolProvider:

    def __init__(
        self,
        runner: FlowRunner,
        llm=None,
    ) -> None:

        self.runner = runner
        self.repairer = FlowRepairer(
            llm,
            max_attempts=runner.config.repair_attempts,
            audit=runner.audit,
        )

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
                    "Hagar Flow è un sottoinsieme di Python: niente import, "
                    "class, def, lambda, try, dict/set comprehension, "
                    "generatori o accesso a oggetti Python. Sono ammesse "
                    "list comprehension con un solo for."
                ),
                category="flow",
                capabilities=Capability.FLOW_EXEC,
                parameters=[
                    ToolParameter(
                        "code",
                        "string",
                        "Sorgente Hagar Flow; non un file .py.",
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
                    "class, def, lambda, try, comprehension con più di un "
                    "for, dict/set comprehension o accesso a oggetti. "
                    "Usa solo le primitive elencate da flow.reference. "
                    "Genera il sorgente, non un file .py. "
                    "Gli errori di validazione possono essere riparati "
                    "automaticamente con un numero limitato di tentativi."
                ),
                category="flow",
                capabilities=Capability.FLOW_EXEC,
                parameters=[
                    ToolParameter(
                        "code",
                        "string",
                        (
                            "Sorgente Hagar Flow. Sintassi Python ristretta; "
                            "nessun import. Non creare un file .py: restituisci "
                            "solo il testo del sorgente."
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
        attempts = 0

        while (
            not result.ok
            and result.error is not None
            and result.error.get("kind") == "validation"
            and attempts < self.repairer.max_attempts
        ):
            attempts += 1
            candidate = self.repairer.propose(
                code,
                result.error,
            )

            if candidate is None:
                break

            self.runner.record(
                "flow.repair.attempt",
                attempt=attempts,
            )
            code = candidate
            result = self.runner.run(code)

        if (
            not result.ok
            and attempts > 0
            and result.error is not None
            and result.error.get("kind") == "validation"
        ):
            self.runner.record(
                "flow.repair.gave_up",
                attempts=attempts,
            )

        if result.ok:
            self.runner.record(
                "flow.repair.result",
                attempts=attempts,
            )

        return json.dumps(
            {
                "ok": result.ok,
                "result": result.result,
                "error": result.error,
                "steps": result.steps,
                "tool_calls": result.tool_calls,
                "duration_ms": result.duration_ms,
                "trace": result.trace,
                "repair_attempts": attempts,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
