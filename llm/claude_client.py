# llm/claude_client.py

from __future__ import annotations

import requests

from typing import Any

from core.tool_call import ToolCall
from llm.base import (
    LLMClient,
    LLMReply,
    NativeToolsUnavailable,
)


class ClaudeClient(LLMClient):
    """
    Backend Anthropic Claude (Messages API).

    L'API vuole il prompt di sistema in un campo separato e ammette solo
    turni ``user``/``assistant`` alternati: la conversazione interna viene
    normalizzata prima dell'invio.
    """

    provider = "claude"

    supports_native_tools = True

    DEFAULT_BASE_URL = "https://api.anthropic.com"

    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 1024,
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

        self.max_tokens = max_tokens

        self.base_url = base_url.rstrip("/")

        self.timeout = timeout

    # ==================================================
    # Chat API
    # ==================================================

    def _headers(self) -> dict[str, str]:

        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        system, converted = self._convert_messages(
            messages
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": converted,
        }

        if system:
            payload["system"] = system

        response = requests.post(
            f"{self.base_url}/v1/messages",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )

        response.raise_for_status()

        data = response.json()

        blocks = data.get("content")

        if not isinstance(blocks, list):

            raise RuntimeError(
                "Claude response contains no content"
            )

        return "".join(
            block.get("text", "")
            for block in blocks
            if block.get("type") == "text"
        )

    # ==================================================
    # Native tool calling
    # ==================================================

    def _native_request(
        self,
        messages: list[dict[str, Any]],
        registry,
    ) -> LLMReply:

        system, converted = (
            self._convert_native_messages(messages)
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": converted,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": (
                        self._parameters_schema(tool)
                    ),
                }
                for tool in registry.list_definitions()
            ],
        }

        if system:
            payload["system"] = system

        response = requests.post(
            f"{self.base_url}/v1/messages",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )

        if response.status_code in {400, 404, 422}:

            raise NativeToolsUnavailable(
                "Claude rejected native tools "
                f"(HTTP {response.status_code})"
            )

        response.raise_for_status()

        data = response.json()

        blocks = data.get("content")

        if not isinstance(blocks, list):

            raise RuntimeError(
                "Claude response contains no content"
            )

        texts: list[str] = []

        calls: list[ToolCall] = []

        for block in blocks:

            block_type = block.get("type")

            if block_type == "text":

                texts.append(block.get("text", ""))

            elif block_type == "tool_use":

                name = block.get("name")

                if not name:
                    continue

                calls.append(
                    ToolCall(
                        tool=name,
                        arguments=block.get("input") or {},
                        id=(
                            block.get("id")
                            or f"claude-{len(calls)}"
                        ),
                    )
                )

        text = "".join(texts)

        return LLMReply(
            text=text,
            tool_calls=calls,
            assistant_message=(
                self._assistant_message(text, calls)
            ),
        )

    @staticmethod
    def _convert_native_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:

        system_parts: list[str] = []

        converted: list[dict[str, Any]] = []

        for message in messages:

            role = message.get("role", "user")

            content = message.get("content", "")

            if role == "system":

                system_parts.append(content)
                continue

            if role == "tool":

                blocks = [
                    {
                        "type": "tool_result",
                        "tool_use_id": message.get(
                            "tool_call_id"
                        ),
                        "content": content,
                    }
                ]

                target = "user"

            elif (
                role == "assistant"
                and message.get("tool_calls")
            ):

                blocks = []

                if content:
                    blocks.append(
                        {"type": "text", "text": content}
                    )

                for call in message["tool_calls"]:

                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call["id"],
                            "name": call["name"],
                            "input": call["arguments"],
                        }
                    )

                target = "assistant"

            else:

                blocks = [
                    {"type": "text", "text": content}
                ]

                target = (
                    "assistant"
                    if role == "assistant"
                    else "user"
                )

            if (
                converted
                and converted[-1]["role"] == target
            ):

                converted[-1]["content"].extend(blocks)

            else:

                converted.append(
                    {
                        "role": target,
                        "content": blocks,
                    }
                )

        system = "\n\n".join(
            part
            for part in system_parts
            if part.strip()
        )

        if not converted:

            converted.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ""}
                    ],
                }
            )

        return system, converted

    # ==================================================
    # Message conversion
    # ==================================================

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """
        Estrae i messaggi di sistema e rende i turni alternati.

        Restituisce ``(system, messages)`` dove ``system`` è la
        concatenazione dei messaggi di sistema (eventualmente vuota).
        """

        system_parts: list[str] = []

        converted: list[dict[str, str]] = []

        for message in messages:

            role = message.get("role", "user")

            content = message.get("content", "")

            if role == "system":

                system_parts.append(content)

                continue

            target = (
                "assistant"
                if role == "assistant"
                else "user"
            )

            if (
                converted
                and converted[-1]["role"] == target
            ):

                converted[-1]["content"] += (
                    "\n\n" + content
                )

            else:

                converted.append(
                    {
                        "role": target,
                        "content": content,
                    }
                )

        system = "\n\n".join(
            part
            for part in system_parts
            if part.strip()
        )

        if not converted:

            converted.append(
                {
                    "role": "user",
                    "content": "",
                }
            )

        return system, converted
