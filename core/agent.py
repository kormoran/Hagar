# core/agent.py

from __future__ import annotations

import sys
import threading
import time
import uuid

from typing import Any

from core.events import EventSink
from core.events import emit
from core.hifi import HiFiError
from core.context import ContextCompactor, OutputSpiller
from core.images import ImageInput
from core.images import MAX_IMAGES
from core.tool_call import ToolCall
from core.tool_result import ToolResult
from llm.base import NativeToolsUnavailable


class AgentCancelled(RuntimeError):
    """Il turno è stato interrotto dall'utente."""


class AgentTimedOut(RuntimeError):
    """Il turno ha superato la deadline a parete."""


class Agent:

    def __init__(
        self,
        llm,
        tool_registry,
        vault,
        max_tool_calls: int = 10,
        audit: Any = None,
        memory: Any = None,
        project_store: Any = None,
        project_id: str | None = None,
        max_context_chars: int = 6000,
        context_project_memories: int = 10,
        event_sink: EventSink | None = None,
        agent_id: str | None = None,
        deadline: float | None = None,
        turn_timeout: float | None = None,
        hifi: Any = None,
        artifact_store: Any = None,
        max_inline_output_chars: int = 12_000,
        context_compactor: ContextCompactor | None = None,
    ) -> None:

        self.llm = llm
        self.tools = tool_registry
        self.vault = vault

        self.event_sink = event_sink
        self.agent_id = agent_id
        self.deadline = deadline
        self.turn_timeout = turn_timeout
        self.hifi = hifi
        self.output_spiller = OutputSpiller(
            artifact_store,
            max_inline_chars=max_inline_output_chars,
        )
        self.context_compactor = (
            context_compactor or ContextCompactor()
        )
        self._cancel = threading.Event()

        self.max_tool_calls = (
            max_tool_calls
        )

        self.audit = audit
        self.memory = memory
        self.project_store = project_store
        self.project_id = project_id
        self.max_context_chars = int(max_context_chars)
        self.context_project_memories = int(
            context_project_memories
        )

    # ==================================================
    # Cancellazione
    # ==================================================

    def cancel(self) -> None:
        """Richiede l'interruzione del turno in corso."""

        self._cancel.set()

    def reset_cancel(self) -> None:
        self._cancel.clear()

    def _check_cancel(
        self,
        turn: str,
    ) -> None:

        if not self._cancel.is_set():
            if (
                self.deadline is not None
                and time.monotonic() > self.deadline
            ):
                self._record(
                    "turn.timed_out",
                    turn=turn,
                    agent_id=self.agent_id,
                )
                raise AgentTimedOut(
                    "wall-clock deadline exceeded"
                )

            return

        self._record(
            "turn.cancelled",
            turn=turn,
            agent_id=self.agent_id,
        )

        raise AgentCancelled("turn cancelled by user")

    # ==================================================
    # Public API
    # ==================================================

    def ask(
        self,
        question: str,
        images: list[ImageInput] | None = None,
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
        self.reset_cancel()

        if self.turn_timeout is not None:
            self.deadline = (
                time.monotonic()
                + max(0.0, float(self.turn_timeout))
            )

        if hasattr(self.tools, "begin_turn"):
            self.tools.begin_turn()

        content: Any = question

        if images:

            content = [
                {
                    "type": "text",
                    "text": question,
                },
                *[
                    image.as_message_part()
                    for image in images
                ],
            ]

        messages = [
            {
                "role": "user",
                "content": content,
            }
        ]

        if self.memory is not None:

            context = self._memory_context(
                turn,
                question,
            )

            if context:

                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": context,
                    },
                )

        native = bool(
            getattr(
                self.llm,
                "supports_native_tools",
                False,
            )
            and getattr(
                self.llm,
                "native_tools",
                False,
            )
        )

        self._record(
            "turn.start",
            turn=turn,
            question=question,
            max_tool_calls=self.max_tool_calls,
            native=native,
        )

        try:

            if self.hifi is not None and not images:

                try:

                    hifi_result = self.hifi.resolve(question)

                except HiFiError as exc:

                    self._record(
                        "hifi.failed",
                        turn=turn,
                        error=str(exc),
                    )

                else:

                    self._record(
                        "hifi.interpretations",
                        turn=turn,
                        **hifi_result.audit(),
                    )

                    if hifi_result.needs_clarification:

                        clarification = self.hifi.clarify(
                            question,
                            hifi_result,
                        )

                        self._record(
                            "hifi.clarification",
                            turn=turn,
                            answer=clarification,
                        )

                        self._record(
                            "turn.answer",
                            turn=turn,
                            answer=clarification,
                            tool_calls=0,
                        )

                        self._remember(
                            turn,
                            question,
                            clarification,
                        )

                        return clarification

                    effective_question = (
                        self.hifi.resolved_question(
                            question,
                            hifi_result,
                        )
                    )

                    messages[-1]["content"] = effective_question

                    self._record(
                        "hifi.resolved",
                        turn=turn,
                        choice=hifi_result.top.text,
                        probability=round(
                            hifi_result.top.probability,
                            6,
                        ),
                        margin=round(hifi_result.margin, 6),
                    )

            if native:

                try:

                    return self._run_native(
                        turn,
                        messages,
                        question,
                        attached_images=len(images or []),
                    )

                except NativeToolsUnavailable as exc:

                    #
                    # Fallback: il modello non accetta i tool nativi.
                    # Si riparte dal protocollo testuale, ma solo se
                    # non è già stato eseguito alcun tool.
                    #

                    self._record(
                        "llm.native_fallback",
                        turn=turn,
                        error=str(exc),
                    )

                    self.llm.native_tools = False

            return self._run(
                turn,
                messages,
                question,
                attached_images=len(images or []),
            )

        finally:

            self._memory_end()

    def _run(
        self,
        turn: str,
        messages: list[dict[str, Any]],
        question: str,
        attached_images: int = 0,
    ) -> str:

        executed = 0

        while True:

            self._compact_messages(turn, messages)
            self._check_cancel(turn)

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

            reasoning = getattr(
                self.llm,
                "last_reasoning",
                "",
            )

            if reasoning:

                emit(
                    self.event_sink,
                    "thinking",
                    turn=turn,
                    text=reasoning,
                )

            #
            # Nessun tool richiesto:
            # genera la risposta finale.
            #

            self._check_cancel(turn)

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

                self._check_cancel(turn)

                self._record(
                    "turn.answer",
                    turn=turn,
                    answer=answer,
                    tool_calls=executed,
                )

                self._remember(
                    turn,
                    question,
                    answer,
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

            self._check_cancel(turn)

            tool_result = self._execute_and_record(
                turn,
                executed,
                tool_call,
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

            attached_images = self._attach_images(
                messages,
                turn,
                tool_result,
                attached_images,
            )

    def _run_native(
        self,
        turn: str,
        messages: list[dict[str, Any]],
        question: str,
        attached_images: int = 0,
    ) -> str:
        """
        Ciclo agentico con tool calling nativo del provider.

        Il modello può restituire più chiamate nello stesso turno; i
        risultati tornano come messaggi ``tool`` con l'id della chiamata.
        """

        executed = 0

        while True:

            self._compact_messages(turn, messages)
            self._check_cancel(turn)

            try:

                reply = self.llm.native_step(
                    messages,
                    self.tools,
                )

            except NativeToolsUnavailable:

                if executed == 0:
                    raise

                self._record(
                    "turn.error",
                    turn=turn,
                    stage="native_step",
                    error="native tools unavailable",
                )

                return (
                    "Errore durante la richiesta "
                    "al modello: native tools "
                    "non più disponibili."
                )

            except Exception as exc:

                self._record(
                    "turn.error",
                    turn=turn,
                    stage="native_step",
                    error=str(exc),
                )

                return (
                    "Errore durante "
                    "la richiesta al modello: "
                    f"{exc}"
                )

            if reply.reasoning:

                emit(
                    self.event_sink,
                    "thinking",
                    turn=turn,
                    text=reply.reasoning,
                )

            #
            # Nessuna chiamata: è la risposta finale.
            #

            self._check_cancel(turn)

            if not reply.tool_calls:

                answer = reply.text

                self._record(
                    "turn.answer",
                    turn=turn,
                    answer=answer,
                    tool_calls=executed,
                )

                self._remember(
                    turn,
                    question,
                    answer,
                )

                return answer

            #
            # Protezione contro loop infiniti: il limite vale per
            # l'intero turno, non per singola richiesta.
            #

            if (
                executed + len(reply.tool_calls)
                > self.max_tool_calls
            ):

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

            for index, call in enumerate(
                reply.tool_calls
            ):

                if not call.id:

                    call.id = (
                        f"call-{executed + index + 1}"
                    )

            assistant_message = (
                reply.assistant_message
                or self._assistant_message(
                    reply.text,
                    reply.tool_calls,
                )
            )

            messages.append(assistant_message)

            for call in reply.tool_calls:

                executed += 1

                self._check_cancel(turn)

                tool_result = (
                    self._execute_and_record(
                        turn,
                        executed,
                        call,
                    )
                )

                if tool_result.success:

                    content = tool_result.output

                else:

                    content = (
                        "Error: "
                        f"{tool_result.error}"
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.tool,
                        "content": content,
                    }
                )

                attached_images = self._attach_images(
                    messages,
                    turn,
                    tool_result,
                    attached_images,
                )

    @staticmethod
    def _assistant_message(
        text: str,
        calls: list[ToolCall],
    ) -> dict[str, Any]:

        return {
            "role": "assistant",
            "content": text,
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.tool,
                    "arguments": call.arguments,
                }
                for call in calls
            ],
        }

    # ==================================================
    # Tool execution
    # ==================================================

    def _execute_and_record(
        self,
        turn: str,
        index: int,
        tool_call: ToolCall,
    ) -> ToolResult:

        self._record(
            "tool.call",
            turn=turn,
            index=index,
            tool=tool_call.tool,
            arguments=tool_call.arguments,
        )

        emit(
            self.event_sink,
            "tool.call",
            turn=turn,
            index=index,
            tool=tool_call.tool,
            arguments=tool_call.arguments,
        )

        started = time.perf_counter()

        tool_result = self._execute_tool(
            tool_call
        )

        duration_ms = round(
            (
                time.perf_counter()
                - started
            )
            * 1000,
            2,
        )

        output = tool_result.output

        if not getattr(
            self.audit,
            "include_outputs",
            True,
        ):

            output = (
                f"<redacted: "
                f"{len(tool_result.output)} chars>"
            )

        self._record(
            "tool.result",
            turn=turn,
            index=index,
            tool=tool_call.tool,
            success=tool_result.success,
            duration_ms=duration_ms,
            output=output,
            error=tool_result.error,
        )

        event_output = output

        if len(event_output) > 8000:

            event_output = (
                event_output[:8000]
                + f"\n… [truncated {len(output) - 8000} chars]"
            )

        emit(
            self.event_sink,
            "tool.result",
            turn=turn,
            index=index,
            tool=tool_call.tool,
            success=tool_result.success,
            duration_ms=duration_ms,
            output=event_output,
            error=tool_result.error,
        )

        return tool_result

    def _compact_messages(
        self,
        turn: str,
        messages: list[dict[str, Any]],
    ) -> None:

        removed = self.context_compactor.compact(messages)

        if removed:
            self._record(
                "context.compacted",
                turn=turn,
                messages=removed,
            )

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

            if isinstance(result, ToolResult):

                if result.tool_name is None:
                    result.tool_name = tool_call.tool

                return self._spill_result(result)

            return self._spill_result(
                ToolResult(
                    tool_name=tool_call.tool,
                    success=True,
                    output=str(result),
                    error=None,
                )
            )

        except Exception as exc:

            return ToolResult(
                tool_name=tool_call.tool,
                success=False,
                output="",
                error=str(exc),
            )

    def _spill_result(
        self,
        result: ToolResult,
    ) -> ToolResult:

        if not result.success or not result.output:
            return result

        try:
            output, artifact_id = self.output_spiller.spill(
                result.output,
                owner=self.agent_id or "main",
                tool=result.tool_name or "unknown",
            )
        except Exception as exc:
            self._record(
                "tool.spill_failed",
                tool=result.tool_name,
                error=str(exc),
            )
            return result

        if artifact_id is None:
            return result

        original_chars = len(result.output)
        result.output = output
        result.artifact_id = artifact_id
        self._record(
            "tool.spilled",
            tool=result.tool_name,
            artifact_id=artifact_id,
            original_chars=original_chars,
        )
        return result

    def _attach_images(
        self,
        messages: list[dict[str, Any]],
        turn: str,
        result: ToolResult,
        attached: int,
    ) -> int:

        if not result.images:
            return attached

        remaining = MAX_IMAGES - attached
        selected = result.images[:max(0, remaining)]
        skipped = len(result.images) - len(selected)

        if selected:

            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Immagine allegata dal tool "
                                f"{result.tool_name}."
                            ),
                        },
                        *[
                            image.as_message_part()
                            for image in selected
                        ],
                    ],
                }
            )

        self._record(
            "vision.attached",
            turn=turn,
            tool=result.tool_name,
            count=len(selected),
            skipped=skipped,
        )

        return attached + len(selected)

    # ==================================================
    # Memory
    # ==================================================

    def _memory_context(
        self,
        turn: str,
        question: str,
    ) -> str | None:

        try:

            self.memory.begin_turn(turn)

            context_for = getattr(
                self.memory,
                "context_for",
                None,
            )

            if context_for is not None:

                context, count, skills = context_for(
                    question
                )

            else:

                context, count = (
                    self.memory.context_text()
                )

                skills = 0

            project_text = ""
            project_decisions = 0
            summary_text = ""

            if (
                self.project_store is not None
                and self.project_id
            ):

                project_text, project_decisions = (
                    self.project_store.context_index(
                        self.project_id,
                        max_decisions=(
                            self.context_project_memories
                        ),
                        max_chars=self.max_context_chars,
                    )
                )

            elif self.memory is not None:

                latest_summary = getattr(
                    self.memory,
                    "latest_summary",
                    None,
                )

                if latest_summary is not None:

                    summary_text = (
                        latest_summary(free_only=True) or ""
                    )

            parts = [
                part
                for part in (
                    project_text,
                    summary_text,
                    context,
                )
                if part
            ]

            context = "\n\n".join(parts) or None

            trimmed = False

            if (
                context
                and self.max_context_chars > 0
                and len(context) > self.max_context_chars
            ):

                context = (
                    context[: self.max_context_chars]
                    .rstrip()
                    + "…"
                )
                trimmed = True

        except Exception as exc:

            self._record(
                "memory.failed",
                turn=turn,
                stage="context",
                error=str(exc),
            )

            return None

        if context:

            self._record(
                "memory.context",
                turn=turn,
                turns=count,
                skills=skills,
                project=self.project_id,
                project_decisions=project_decisions,
                chars=len(context),
                trimmed=trimmed,
            )

            if trimmed:

                self._record(
                    "memory.context_trimmed",
                    turn=turn,
                    chars=len(context),
                    limit=self.max_context_chars,
                )

        return context

    def _remember(
        self,
        turn: str,
        question: str,
        answer: str,
    ) -> None:

        if self.memory is None:
            return

        try:

            self.memory.append_turn(
                turn,
                question,
                answer,
            )

        except Exception as exc:

            self._record(
                "memory.failed",
                turn=turn,
                stage="append",
                error=str(exc),
            )

        else:

            self._record(
                "memory.turn",
                turn=turn,
            )

    def _memory_end(self) -> None:

        if self.memory is None:
            return

        try:

            self.memory.end_turn()

        except Exception as exc:

            self._record(
                "memory.failed",
                stage="end",
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

        if self.agent_id:
            fields.setdefault("agent_id", self.agent_id)

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
