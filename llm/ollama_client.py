# llm/ollama_client.py

from __future__ import annotations

import requests

from typing import Any

from llm.base import (
    LLMClient,
    LLMReply,
    NativeToolsUnavailable,
)
from core.tool_call import ToolCall
from core.usage import usage_from_ollama


class OllamaClient(LLMClient):
    """Backend Ollama (API nativa /api/chat e /api/generate)."""

    provider = "ollama"

    supports_native_tools = True

    DEFAULT_HOST = "http://localhost:11434"

    def __init__(
        self,
        model: str,
        host: str | None = None,
        timeout: int = 120,
        audit: Any = None,
    ) -> None:

        super().__init__(
            model=model,
            audit=audit,
        )

        self.host = (
            host or self.DEFAULT_HOST
        ).rstrip("/")

        self.timeout = timeout

    # ==================================================
    # HTTP helper
    # ==================================================

    def _post(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        response = requests.post(
            f"{self.host}{endpoint}",
            json=payload,
            timeout=self.timeout,
        )

        response.raise_for_status()

        return response.json()

    # ==================================================
    # Generate API
    # ==================================================

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        if system_prompt:
            payload["system"] = system_prompt

        response = self._post(
            "/api/generate",
            payload,
        )

        self._set_usage(usage_from_ollama(response))

        return response["response"]

    # ==================================================
    # Chat API
    # ==================================================

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        response = self._post(
            "/api/chat",
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
            },
        )

        self._set_usage(usage_from_ollama(response))

        return response["message"]["content"]

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

        response = requests.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=self.timeout,
        )

        if response.status_code in {400, 404, 422}:

            raise NativeToolsUnavailable(
                "Ollama rejected native tools "
                f"(HTTP {response.status_code})"
            )

        response.raise_for_status()

        data = response.json()

        message = data.get("message", {})

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
                        or f"ollama-{index}"
                    ),
                )
            )

        return LLMReply(
            text=text,
            tool_calls=calls,
            assistant_message=(
                self._assistant_message(text, calls)
            ),
            usage=usage_from_ollama(data),
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
                        "content": message.get(
                            "content",
                            "",
                        ),
                        "tool_name": (
                            OllamaClient._mapped_tool_name(
                                message.get("name", ""),
                                names,
                            )
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
                                "function": {
                                    "name": (
                                        OllamaClient._mapped_tool_name(
                                            call["name"],
                                            names,
                                        )
                                    ),
                                    "arguments": (
                                        call["arguments"]
                                    ),
                                }
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
