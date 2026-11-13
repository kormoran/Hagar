# llm/deepseek_client.py

from __future__ import annotations

import json
import requests

from typing import Any

from core.tool_call import ToolCall
from core.usage import usage_from_openai
from llm.base import (
    LLMClient,
    LLMReply,
    NativeToolsUnavailable,
)
from llm.reply_text import clean_text, reply_text


class DeepSeekClient(LLMClient):
    """
    Backend DeepSeek.

    Usa l'API compatibile OpenAI: POST /chat/completions con
    autenticazione Bearer. I messaggi di sistema restano nel dialogo.
    """

    provider = "deepseek"

    supports_native_tools = True

    DEFAULT_BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 120,
        audit: Any = None,
    ) -> None:

        super().__init__(
            model=model,
            audit=audit,
        )

        if not api_key:

            raise ValueError(
                "api_key is required"
            )

        self.api_key = api_key

        self.base_url = base_url.rstrip("/")

        self.timeout = timeout

    # ==================================================
    # Chat API
    # ==================================================

    def _headers(self) -> dict[str, str]:

        return {
            "Authorization":
                f"Bearer {self.api_key}",
            "Content-Type":
                "application/json",
        }

    @staticmethod
    def _error_detail(response) -> str:
        """Estrae il messaggio d'errore dell'API, se presente."""

        try:

            data = response.json()

        except Exception:

            text = getattr(response, "text", "") or ""

            return text.strip()[:500] or "no response body"

        if isinstance(data, dict):

            error = data.get("error")

            if isinstance(error, dict):

                message = (
                    error.get("message")
                    or error.get("type")
                )

                if message:
                    return str(message)

            message = data.get("message")

            if isinstance(message, str):
                return message

        return str(data)[:500]

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        response = requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
            },
            headers=self._headers(),
            timeout=self.timeout,
        )

        if response.status_code >= 400:

            raise RuntimeError(
                "DeepSeek HTTP "
                f"{response.status_code}: "
                f"{self._error_detail(response)}"
            )

        response.raise_for_status()

        data = response.json()

        self._set_usage(usage_from_openai(data))

        choices = data.get("choices") or []

        if not choices:

            raise RuntimeError(
                "DeepSeek response contains no choices"
            )

        message = choices[0]["message"]

        self.last_reasoning = clean_text(
            message.get("reasoning_content")
            or message.get("reasoning")
            or ""
        )
        text, fallback = reply_text(
            message.get("content"),
            self.last_reasoning,
        )

        if fallback:
            self._record(
                "llm.reasoning_fallback",
                chars=len(text),
            )

        return text

    # ==================================================
    # Native tool calling
    # ==================================================

    def _native_request(
        self,
        messages: list[dict[str, Any]],
        registry,
    ) -> LLMReply:

        names = self._native_tool_names(registry)

        tools = [
            {
                "type": "function",
                "function": {
                    "name": names[tool.name],
                    "description": (
                        tool.short_description
                        or tool.description
                    ),
                    "parameters": self._parameters_schema(
                        tool,
                        compact=registry.compact_descriptions,
                    ),
                },
            }
            for tool in registry.list_definitions()
        ]

        response = requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": self._to_native_messages(
                    messages,
                    names,
                ),
                "stream": False,
                "tools": tools,
                #
                # Il modello può ragionare, ma per il calling nativo
                # la modalità non-thinking è più rapida e diretta.
                #
                "thinking": {"type": "disabled"},
            },
            headers=self._headers(),
            timeout=self.timeout,
        )

        detail = self._error_detail(response)

        if response.status_code in {400, 404, 422}:

            raise NativeToolsUnavailable(
                "DeepSeek rejected native tools "
                f"(HTTP {response.status_code}): {detail}"
            )

        if response.status_code >= 400:

            raise RuntimeError(
                "DeepSeek HTTP "
                f"{response.status_code}: {detail}"
            )

        response.raise_for_status()

        data = response.json()

        choices = data.get("choices") or []

        if not choices:

            raise RuntimeError(
                "DeepSeek response contains no choices"
            )

        message = choices[0].get("message", {})

        reasoning = clean_text(
            message.get("reasoning_content")
            or message.get("reasoning")
            or ""
        )
        raw_text = clean_text(message.get("content"))
        text, fallback = reply_text(
            message.get("content"),
            reasoning,
        )

        reverse = {
            native: original
            for original, native in names.items()
        }

        calls: list[ToolCall] = []

        for index, raw in enumerate(
            message.get("tool_calls") or []
        ):

            function = raw.get("function", {})

            native_name = function.get("name")

            if not native_name:
                continue

            calls.append(
                ToolCall(
                    tool=reverse.get(
                        native_name,
                        native_name,
                    ),
                    arguments=self._parse_arguments(
                        function.get("arguments")
                    ),
                    id=(
                        raw.get("id")
                        or f"deepseek-{index}"
                    ),
                )
            )

        if calls and fallback:
            text = raw_text
            fallback = False

        self.last_reasoning = reasoning

        if fallback:
            self._record(
                "llm.reasoning_fallback",
                chars=len(text),
            )

        return LLMReply(
            text=text,
            tool_calls=calls,
            assistant_message=(
                self._assistant_message(text, calls)
            ),
            usage=usage_from_openai(data),
            reasoning=reasoning,
        )

    @staticmethod
    def _to_native_messages(
        messages: list[dict[str, Any]],
        names: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:

        converted: list[dict[str, Any]] = []

        for message in messages:

            role = message.get("role")

            if role == "tool":

                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get(
                            "tool_call_id"
                        ),
                        "content": message.get(
                            "content",
                            "",
                        ),
                    }
                )

            elif (
                role == "assistant"
                and message.get("tool_calls")
            ):

                converted.append(
                    {
                        "role": "assistant",
                        "content": message.get(
                            "content",
                            "",
                        ),
                        "tool_calls": [
                            {
                                "id": call["id"],
                                "type": "function",
                                "function": {
                                    "name": (
                                        DeepSeekClient
                                        ._mapped_tool_name(
                                            call["name"],
                                            names,
                                        )
                                    ),
                                    "arguments": json.dumps(
                                        call["arguments"],
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                            for call in message[
                                "tool_calls"
                            ]
                        ],
                    }
                )

            else:

                converted.append(
                    {
                        "role": role,
                        "content": message.get(
                            "content",
                            "",
                        ),
                    }
                )

        return converted
