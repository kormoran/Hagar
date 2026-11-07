"""Client per API OpenAI-compatibili (OpenAI, LM Studio)."""

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


class OpenAICompatibleClient(LLMClient):
    """
    Backend che parla il protocollo OpenAI Chat Completions.

    Le sottoclassi cambiano solo provider, base URL e gestione della
    chiave. Il formato dei messaggi, dei tool e delle risposte resta
    quello OpenAI: ``tools`` in richiesta e ``tool_calls`` in risposta.
    """

    supports_native_tools = True

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
        audit: Any = None,
    ) -> None:

        super().__init__(
            model=model,
            audit=audit,
        )

        self.base_url = (
            base_url or self.DEFAULT_BASE_URL
        ).rstrip("/")

        self.api_key = api_key

        self.timeout = timeout

    # ==================================================
    # HTTP helpers
    # ==================================================

    def _headers(self) -> dict[str, str]:

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:

            headers["Authorization"] = (
                f"Bearer {self.api_key}"
            )

        return headers

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

    def _post(
        self,
        payload: dict[str, Any],
    ):
        return requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )

    # ==================================================
    # Chat API
    # ==================================================

    @staticmethod
    def _reasoning(message: dict[str, Any]) -> str:

        value = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or ""
        )

        return str(value).strip()

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        response = self._post(
            {
                "model": self.model,
                "messages": self._openai_messages(messages),
                "stream": False,
            }
        )

        detail = self._error_detail(response)

        if response.status_code >= 400:

            raise RuntimeError(
                f"{self.provider} HTTP "
                f"{response.status_code}: {detail}"
            )

        response.raise_for_status()

        data = response.json()

        self._set_usage(usage_from_openai(data))

        choices = data.get("choices") or []

        if not choices:

            raise RuntimeError(
                f"{self.provider} response contains "
                "no choices"
            )

        message = choices[0].get("message") or {}

        self.last_reasoning = self._reasoning(message)

        content = message.get("content")

        return content or ""

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
                    "description": tool.description,
                    "parameters": self._parameters_schema(
                        tool
                    ),
                },
            }
            for tool in registry.list_definitions()
        ]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_native_messages(
                messages,
                names,
            ),
            "stream": False,
        }

        if tools:

            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = self._post(payload)

        detail = self._error_detail(response)

        if response.status_code in {400, 404, 422}:

            raise NativeToolsUnavailable(
                f"{self.provider} rejected native tools "
                f"(HTTP {response.status_code}): {detail}"
            )

        if response.status_code >= 400:

            raise RuntimeError(
                f"{self.provider} HTTP "
                f"{response.status_code}: {detail}"
            )

        response.raise_for_status()

        data = response.json()

        choices = data.get("choices") or []

        if not choices:

            raise RuntimeError(
                f"{self.provider} response contains "
                "no choices"
            )

        message = choices[0].get("message") or {}

        text = message.get("content") or ""

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
                        or f"{self.provider}-{index}"
                    ),
                )
            )

        return LLMReply(
            text=text,
            tool_calls=calls,
            assistant_message=(
                self._assistant_message(text, calls)
            ),
            usage=usage_from_openai(data),
            reasoning=self._reasoning(message),
        )

    # ==================================================
    # Message translation
    # ==================================================

    @classmethod
    def _content(
        cls,
        content: Any,
    ) -> Any:

        if not isinstance(content, list):
            return content

        converted = []

        for part in content:

            if not isinstance(part, dict):
                continue

            if part.get("type") == "text":

                converted.append(
                    {
                        "type": "text",
                        "text": part.get("text", ""),
                    }
                )

            elif part.get("type") == "image":

                converted.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                "data:"
                                f"{part.get('mime_type', 'image/png')}"
                                ";base64,"
                                f"{part.get('data', '')}"
                            )
                        },
                    }
                )

        return converted

    @classmethod
    def _openai_messages(
        cls,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        return [
            {
                **message,
                "content": cls._content(
                    message.get("content", "")
                ),
            }
            for message in messages
        ]

    @classmethod
    def _to_native_messages(
        cls,
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
                                        cls._mapped_tool_name(
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
                        "content": cls._content(
                            message.get("content", "")
                        ),
                    }
                )

        return converted
