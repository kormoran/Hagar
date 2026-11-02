# core/agent.py

from __future__ import annotations

from .tool_call import ToolCall
from .tool_result import ToolResult


class Agent:

    def __init__(
        self,
        llm,
        tool_registry,
        vault,
        max_tool_calls: int = 10,
    ) -> None:

        self.llm = llm
        self.tools = tool_registry
        self.vault = vault

        self.max_tool_calls = (
            max_tool_calls
        )

    # ==================================================
    # Public API
    # ==================================================

    def ask(
        self,
        question: str,
    ) -> str:

        messages = [
            {
                "role": "user",
                "content": question,
            }
        ]

        for _ in range(
            self.max_tool_calls
        ):

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

                    return self.llm.chat(
                        messages
                    )

                except Exception as exc:

                    return (
                        "Errore durante "
                        "la generazione della "
                        f"risposta finale: {exc}"
                    )

            #
            # Esecuzione tool
            #

            tool_result = (
                self._execute_tool(
                    tool_call
                )
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
            # Registrazione risultato
            #

            if tool_result.success:

                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Tool result:\n"
                            f"{tool_result.output}"
                        ),
                    }
                )

            else:

                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Tool execution failed.\n"
                            f"Error:\n"
                            f"{tool_result.error}"
                        ),
                    }
                )

        #
        # Protezione
        # contro loop infiniti.
        #

        return (
            "Agent stopped after "
            f"{self.max_tool_calls} "
            "tool calls."
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