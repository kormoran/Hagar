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
                name="flow.repair",
                description=(
                    "Propone una correzione per un errore di validazione di "
                    "Hagar Flow senza eseguire il codice. Restituisce il "
                    "sorgente corretto; il chiamante deve poi usare "
                    "flow.run per eseguirlo."
                ),
                category="flow",
                capabilities=Capability.FLOW_EXEC,
                parameters=[
                    ToolParameter(
                        "code",
                        "string",
                        "Sorgente Hagar Flow da riparare; non un file .py.",
                    )
                ],
                handler=self.repair_code,
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
                    "Non ripara il codice: usa flow.repair e poi richiama "
                    "flow.run con il sorgente corretto."
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

    def repair_code(self, code: str) -> str:
        try:
            validate(
                code,
                self.runner.primitives,
                max_source_chars=self.runner.config.max_source_chars,
            )
        except FlowValidationError as exc:
            error = exc.as_dict()
        else:
            return json.dumps(
                {
                    "ok": True,
                    "repaired": False,
                    "code": code,
                    "attempts": 0,
                    "error": None,
                },
                ensure_ascii=False,
                indent=2,
            )

        current = code
        last_error = error
        attempts = 0

        while attempts < self.repairer.max_attempts:
            attempts += 1
            self.runner.record(
                "flow.repair.attempt",
                attempt=attempts,
            )
            candidate = self.repairer.propose(
                current,
                last_error,
            )

            if candidate is None:
                break

            try:
                validate(
                    candidate,
                    self.runner.primitives,
                    max_source_chars=self.runner.config.max_source_chars,
                )
            except FlowValidationError as exc:
                current = candidate
                last_error = exc.as_dict()
                continue

            self.runner.record(
                "flow.repair.result",
                attempts=attempts,
            )
            return json.dumps(
                {
                    "ok": True,
                    "repaired": True,
                    "code": candidate,
                    "attempts": attempts,
                    "error": last_error,
                },
                ensure_ascii=False,
                indent=2,
            )

        self.runner.record(
            "flow.repair.gave_up",
            attempts=attempts,
        )
        return json.dumps(
            {
                "ok": False,
                "repaired": False,
                "code": None,
                "attempts": attempts,
                "error": last_error,
            },
            ensure_ascii=False,
            indent=2,
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
                "repair_attempts": 0,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
