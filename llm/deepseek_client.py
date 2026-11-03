# llm/deepseek_client.py

from __future__ import annotations

import json
import requests

from typing import Any

from core.tool_call import ToolCall
from llm.base import (
    LLMClient,
    LLMReply,
    NativeToolsUnavailable,
)


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

        response.raise_for_status()

        data = response.json()

        choices = data.get("choices") or []

        if not choices:

            raise RuntimeError(
                "DeepSeek response contains no choices"
            )

        return choices[0]["message"]["content"]

    # ==================================================
    # Native tool calling
    # ==================================================

    def _native_request(
        self,
        messages: list[dict[str, Any]],
        registry,
    ) -> LLMReply:

        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": self._parameters_schema(
                        tool
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
                    messages
                ),
                "stream": False,
                "tools": tools,
            },
            headers=self._headers(),
            timeout=self.timeout,
        )

        if response.status_code in {400, 404, 422}:

            raise NativeToolsUnavailable(
                "DeepSeek rejected native tools "
                f"(HTTP {response.status_code})"
            )

        response.raise_for_status()

        data = response.json()

        choices = data.get("choices") or []

        if not choices:

            raise RuntimeError(
                "DeepSeek response contains no choices"
            )

        message = choices[0].get("message", {})

        text = message.get("content") or ""

        calls: list[ToolCall] = []

        for index, raw in enumerate(
            message.get("tool_calls") or []
        ):

            function = raw.get("function", {})

            name = function.get("name")

            if not name:
                continue

            calls.append(
                ToolCall(
                    tool=name,
                    arguments=self._parse_arguments(
                        function.get("arguments")
                    ),
                    id=(
                        raw.get("id")
                        or f"deepseek-{index}"
                    ),
                )
            )

        return LLMReply(
            text=text,
            tool_calls=calls,
            assistant_message=(
                self._assistant_message(text, calls)
            ),
        )

    @staticmethod
    def _to_native_messages(
        messages: list[dict[str, Any]],
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
                                    "name": call["name"],
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
