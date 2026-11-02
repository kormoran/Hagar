# core/agent.py

from __future__ import annotations

import sys
import time
import uuid

from typing import Any

from core.tool_call import ToolCall
from core.tool_result import ToolResult


class Agent:

    def __init__(
        self,
        llm,
        tool_registry,
        vault,
        max_tool_calls: int = 10,
        audit: Any = None,
    ) -> None:

        self.llm = llm
        self.tools = tool_registry
        self.vault = vault

        self.max_tool_calls = (
            max_tool_calls
        )

        self.audit = audit

    # ==================================================
    # Public API
    # ==================================================

    def ask(
        self,
        question: str,
    ) -> str:
        """
        Ciclo agentico multi-step.

        Il modello può chiedere al massimo ``max_tool_calls`` esecuzioni;
        dopo l'ultima gli viene comunque concessa una richiesta finale per
        formulare la risposta. Se insiste con un altro tool, il ciclo si
        interrompe (protezione contro loop infiniti).

        Ogni passo viene registrato nell'audit log: domanda, scelta del
        tool, argomenti, esito, durata e risposta finale.
        """

        turn = uuid.uuid4().hex[:8]

        messages = [
            {
                "role": "user",
                "content": question,
            }
        ]

        executed = 0

        self._record(
            "turn.start",
            turn=turn,
            question=question,
            max_tool_calls=self.max_tool_calls,
        )

        while True:

            #
            # Richiesta al modello:
            # serve un tool?
            #

            try:

                tool_call = (
                    self.llm.request_tool_call(
                        messages,
                        self.tools,
                    )
                )

            except Exception as exc:

                self._record(
                    "turn.error",
                    turn=turn,
                    stage="request_tool_call",
                    error=str(exc),
                )

                return (
                    "Errore durante "
                    "la richiesta al modello: "
                    f"{exc}"
                )

            #
            # Nessun tool richiesto:
            # genera la risposta finale.
            #

            if not tool_call.tool:

                try:

                    answer = self.llm.chat(
                        messages
                    )

                except Exception as exc:

                    self._record(
                        "turn.error",
                        turn=turn,
                        stage="final_answer",
                        error=str(exc),
                    )

                    return (
                        "Errore durante "
                        "la generazione della "
                        f"risposta finale: {exc}"
                    )

                self._record(
                    "turn.answer",
                    turn=turn,
                    answer=answer,
                    tool_calls=executed,
                )

                return answer

            #
            # Protezione contro loop infiniti.
            #

            if executed >= self.max_tool_calls:

                answer = (
                    "Agent stopped after "
                    f"{self.max_tool_calls} "
                    "tool calls."
                )

                self._record(
                    "turn.stop",
                    turn=turn,
                    tool_calls=executed,
                    max_tool_calls=(
                        self.max_tool_calls
                    ),
                )

                return answer

            #
            # Esecuzione tool
            #

            executed += 1

            self._record(
                "tool.call",
                turn=turn,
                index=executed,
                tool=tool_call.tool,
                arguments=tool_call.arguments,
            )

            started = time.perf_counter()

            tool_result = (
                self._execute_tool(
                    tool_call
                )
            )

            duration_ms = round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000,
                2,
            )

            self._record(
                "tool.result",
                turn=turn,
                index=executed,
                tool=tool_call.tool,
                success=tool_result.success,
                duration_ms=duration_ms,
                output=tool_result.output,
                error=tool_result.error,
            )

            #
            # Registrazione chiamata
            # nella cronologia.
            #

            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "Tool call:\n"
                        f"tool="
                        f"{tool_call.tool}\n"
                        f"arguments="
                        f"{tool_call.arguments}"
                    ),
                }
            )

            #
            # Registrazione risultato.
            #
            # Il risultato è un turno "user": i backend remoti
            # (Claude, Gemini) non accettano messaggi di sistema
            # in mezzo al dialogo, e il modello lo legge come input.
            #

            if tool_result.success:

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Tool result "
                            f"({tool_result.tool_name}, "
                            "success):\n"
                            f"{tool_result.output}"
                        ),
                    }
                )

            else:

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Tool execution failed "
                            f"({tool_result.tool_name}).\n"
                            f"Error:\n"
                            f"{tool_result.error}"
                        ),
                    }
                )

    # ==================================================
    # Tool execution
    # ==================================================

    def _execute_tool(
        self,
        tool_call: ToolCall,
    ) -> ToolResult:

        try:

            result = (
                self.tools.execute(
                    tool_call.tool,
                    **tool_call.arguments,
                )
            )

            return ToolResult(
                tool_name=tool_call.tool,
                success=True,
                output=str(result),
                error=None,
            )

        except Exception as exc:

            return ToolResult(
                tool_name=tool_call.tool,
                success=False,
                output="",
                error=str(exc),
            )

    # ==================================================
    # Audit
    # ==================================================

    def _record(
        self,
        event: str,
        **fields: Any,
    ) -> None:

        if self.audit is None:
            return

        try:

            self.audit.record(event, **fields)

        except Exception as exc:

            #
            # Un audit log rotto non deve fermare l'agente,
            # ma il guasto va visto.
            #

            print(
                f"Audit log error: {exc}",
                file=sys.stderr,
            )
