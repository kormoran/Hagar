# llm/base.py

from __future__ import annotations

import json
import re

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.tool_call import ToolCall
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry


class NativeToolsUnavailable(RuntimeError):
    """Il provider o il modello non supporta il calling nativo."""


@dataclass(slots=True)
class LLMReply:
    """
    Risposta di un passo nativo: testo e/o chiamate tool.

    ``assistant_message`` è il messaggio canonico da riaccodare alla
    conversazione (ruolo assistant con ``tool_calls``), che ogni backend
    traduce nel proprio formato.
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(
        default_factory=list
    )
    assistant_message: dict[str, Any] | None = None


class LLMClient(ABC):
    """
    Interfaccia comune di tutti i backend LLM.

    Un backend concreto implementa solo :meth:`chat`; la selezione dei
    tool, il rendering dei metadati, il parsing robusto del JSON e la
    riparazione del protocollo sono condivisi.

    Il dialogo usa soltanto i ruoli ``user`` e ``assistant``: ogni backend
    traduce verso il proprio formato. In questo modo lo stesso ciclo
    agentico funziona su Ollama, DeepSeek, Claude e Gemini.
    """

    provider = "base"

    supports_native_tools = False

    def __init__(
        self,
        model: str,
        audit: Any = None,
    ) -> None:

        if not model:

            raise ValueError(
                "model must be a non-empty string"
            )

        self.model = model

        self.audit = audit

        #
        # Può essere spento dalla configurazione o dal fallback automatico.
        #

        self.native_tools = True

    # ==================================================
    # Native tool calling
    # ==================================================

    def native_step(
        self,
        messages: list[dict[str, Any]],
        registry: ToolRegistry,
    ) -> LLMReply:

        if not self.supports_native_tools:

            raise NativeToolsUnavailable(
                f"{self.provider} does not support native tools"
            )

        reply = self._native_request(
            messages,
            registry,
        )

        for call in reply.tool_calls:

            self._record(
                "llm.tool_choice",
                tool=call.tool,
                arguments=call.arguments,
                mode="native",
            )

        return reply

    def _native_request(
        self,
        messages: list[dict[str, Any]],
        registry: ToolRegistry,
    ) -> LLMReply:

        raise NativeToolsUnavailable(
            f"{self.provider} does not implement "
            f"native tool calling"
        )

    @staticmethod
    def _native_tool_name(
        name: str,
    ) -> str:
        """
        Nome del tool accettato dalle API di function calling.

        OpenAI/DeepSeek e Claude ammettono solo lettere, cifre, ``_`` e
        ``-``; i nostri nomi usano il punto (``filesystem.read_file``).
        """

        sanitized = re.sub(
            r"[^A-Za-z0-9_-]+",
            "__",
            name,
        )

        return (sanitized or "tool")[:64]

    @classmethod
    def _native_tool_names(
        cls,
        registry: ToolRegistry,
    ) -> dict[str, str]:
        """Mappa nome interno -> nome nativo, senza collisioni."""

        mapping: dict[str, str] = {}

        used: set[str] = set()

        for tool in registry.list_definitions():

            base = cls._native_tool_name(tool.name)

            candidate = base

            index = 2

            while candidate in used:

                suffix = f"_{index}"

                candidate = (
                    base[: max(1, 64 - len(suffix))]
                    + suffix
                )

                index += 1

            used.add(candidate)

            mapping[tool.name] = candidate

        return mapping

    @classmethod
    def _mapped_tool_name(
        cls,
        name: str,
        names: dict[str, str] | None,
    ) -> str:

        if names and name in names:
            return names[name]

        return cls._native_tool_name(name)

    @staticmethod
    def _parameters_schema(
        tool: ToolDefinition,
    ) -> dict[str, Any]:

        properties: dict[str, Any] = {}

        required: list[str] = []

        for parameter in tool.parameters:

            properties[parameter.name] = {
                "type": parameter.param_type,
                "description": parameter.description,
            }

            if parameter.required:
                required.append(parameter.name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        return schema

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

    @staticmethod
    def _parse_arguments(
        value: Any,
    ) -> dict[str, Any]:

        if value is None:
            return {}

        if isinstance(value, dict):
            return value

        if isinstance(value, str):

            try:

                parsed = json.loads(value)

            except json.JSONDecodeError as exc:

                raise RuntimeError(
                    "tool arguments are not valid JSON"
                ) from exc

            if isinstance(parsed, dict):
                return parsed

        raise RuntimeError(
            "tool arguments must be a JSON object"
        )

    # ==================================================
    # Backend API
    # ==================================================

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """Invia il dialogo al modello e restituisce il testo."""

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Generazione one-shot.

        Il default è costruito su :meth:`chat`; un backend può
        sovrascriverlo se offre una API dedicata.
        """

        messages: list[dict[str, str]] = []

        if system_prompt:

            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        return self.chat(messages)

    # ==================================================
    # Tool selection
    # ==================================================

    def request_tool_call(
        self,
        messages: list[dict[str, str]],
        registry: ToolRegistry,
    ) -> ToolCall:

        full_messages = [
            self._tool_selection_prompt(registry),
            *messages,
        ]

        response = self.chat(
            full_messages
        )

        try:

            call = self._parse_tool_call(
                response
            )

        except RuntimeError as first_error:

            self._record(
                "llm.protocol_error",
                stage="tool_selection",
                response=response,
                error=str(first_error),
            )

            #
            # Il modello ha ignorato il protocollo JSON
            # (prosa, markdown, chiavi sbagliate...).
            # Un solo tentativo di riparazione, poi errore esplicito:
            # la Prima Legge vieta di fidarsi della prosa.
            #

            repaired_response = self.chat(
                [
                    *full_messages,
                    {
                        "role": "assistant",
                        "content": response,
                    },
                    {
                        "role": "user",
                        "content": (
                            "La tua risposta precedente non "
                            "rispettava il protocollo. Rispondi "
                            "SOLO con un oggetto JSON, senza "
                            "altro testo, nella forma:\n"
                            '{"tool": <nome tool oppure null>, '
                            '"arguments": {...}}'
                        ),
                    },
                ]
            )

            try:

                call = self._parse_tool_call(
                    repaired_response
                )

            except RuntimeError:

                self._record(
                    "llm.repair_failed",
                    stage="tool_selection",
                    first_response=response,
                    repair_response=(
                        repaired_response
                    ),
                )

                raise RuntimeError(
                    "Unable to extract a valid "
                    "ToolCall from model response.\n\n"
                    "First response:\n"
                    f"{response}\n\n"
                    "Repair response:\n"
                    f"{repaired_response}"
                ) from first_error

            self._record(
                "llm.repaired",
                stage="tool_selection",
                first_response=response,
                repaired_response=(
                    repaired_response
                ),
                tool=call.tool,
            )

        self._record(
            "llm.tool_choice",
            tool=call.tool,
            arguments=call.arguments,
        )

        return call

    def _tool_selection_prompt(
        self,
        registry: ToolRegistry,
    ) -> dict[str, str]:

        tools_description = (
            self._render_tools_for_prompt(
                registry
            )
        )

        return {
            "role": "system",
            "content": (
                "You are an autonomous agent.\n\n"
                "You may choose one tool to call.\n\n"
                "Available tools:\n\n"
                f"{tools_description}\n\n"
                "Respond ONLY with valid JSON.\n"
                "Use exactly the keys 'tool' and 'arguments'.\n"
                "Never answer the user's question in this step.\n\n"
                "If a tool must be executed:\n\n"
                "{\n"
                '  "tool": "tool_name",\n'
                '  "arguments": {\n'
                '    "param": "value"\n'
                "  }\n"
                "}\n\n"
                "If no tool is required:\n\n"
                "{\n"
                '  "tool": null,\n'
                '  "arguments": {}\n'
                "}\n"
            ),
        }

    # ==================================================
    # Tool rendering
    # ==================================================

    def _render_tools_for_prompt(
        self,
        registry: ToolRegistry,
    ) -> str:

        sections: list[str] = []

        for tool in (
            registry.list_definitions()
        ):

            sections.append(
                self._render_tool(tool)
            )

        if not sections:
            return "No tools."

        return "\n\n".join(
            sections
        )

    def _render_tool(
        self,
        tool: ToolDefinition,
    ) -> str:

        lines = [
            f"Name: {tool.name}",
            f"Category: {tool.category}",
            (
                f"Description: "
                f"{tool.description}"
            ),
        ]

        if tool.parameters:

            lines.append(
                "Parameters:"
            )

            for param in (
                tool.parameters
            ):

                lines.append(
                    self._render_parameter(
                        param
                    )
                )

        return "\n".join(lines)

    @staticmethod
    def _render_parameter(
        param: ToolParameter,
    ) -> str:

        required = (
            "required"
            if param.required
            else "optional"
        )

        return (
            f"- {param.name} "
            f"({param.param_type}) "
            f"[{required}] "
            f": {param.description}"
        )

    # ==================================================
    # JSON parsing
    # ==================================================

    def _parse_tool_call(
        self,
        response_text: str,
    ) -> ToolCall:

        response_text = response_text.strip()

        #
        # Tentativo 1:
        # JSON puro
        #

        try:

            return self._tool_call_from_json(
                response_text
            )

        except Exception:
            pass

        #
        # Tentativo 2:
        # blocco markdown ```json
        #

        markdown_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            response_text,
            flags=re.DOTALL,
        )

        if markdown_match:

            try:

                return (
                    self._tool_call_from_json(
                        markdown_match.group(1)
                    )
                )

            except Exception:
                pass

        #
        # Tentativo 3:
        # primo oggetto JSON presente
        #

        json_candidate = (
            self._extract_first_json_object(
                response_text
            )
        )

        if json_candidate:

            try:

                return (
                    self._tool_call_from_json(
                        json_candidate
                    )
                )

            except Exception:
                pass

        raise RuntimeError(
            "Unable to extract a valid "
            "ToolCall from model response.\n\n"
            f"{response_text}"
        )

    def _extract_first_json_object(
        self,
        text: str,
    ) -> str | None:

        start = text.find("{")

        while start != -1:

            depth = 0

            for i in range(
                start,
                len(text),
            ):

                char = text[i]

                if char == "{":
                    depth += 1

                elif char == "}":

                    depth -= 1

                    if depth == 0:

                        candidate = (
                            text[start:i + 1]
                        )

                        try:

                            json.loads(
                                candidate
                            )

                            return candidate

                        except Exception:
                            break

            start = text.find(
                "{",
                start + 1,
            )

        return None

    def _tool_call_from_json(
        self,
        text: str,
    ) -> ToolCall:

        data = json.loads(text)

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "JSON root must be an object"
            )

        tool = data.get("tool")

        #
        # Il protocollo chiede "arguments", ma alcuni modelli
        # (qwen3 compreso) usano "parameters" o null.
        #

        arguments = data.get("arguments")

        if arguments is None:
            arguments = data.get("parameters")

        if arguments is None:
            arguments = {}

        if tool is not None and not isinstance(
            tool,
            str,
        ):
            raise ValueError(
                "'tool' must be string or null"
            )

        if not isinstance(
            arguments,
            dict,
        ):
            raise ValueError(
                "'arguments' must be an object"
            )

        return ToolCall(
            tool=tool,
            arguments=arguments,
        )

    # ==================================================
    # Audit
    # ==================================================

    def _record(
        self,
        event: str,
        **fields: Any,
    ) -> None:

        if self.audit is not None:

            self.audit.record(
                event,
                provider=self.provider,
                model=self.model,
                **fields,
            )
