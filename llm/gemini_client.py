# llm/gemini_client.py

from __future__ import annotations

import requests

from typing import Any

from core.tool_call import ToolCall
from llm.base import (
    LLMClient,
    LLMReply,
    NativeToolsUnavailable,
)


class GeminiClient(LLMClient):
    """
    Backend Google Gemini (Generative Language API).

    I messaggi di sistema diventano ``systemInstruction``; il ruolo
    ``assistant`` diventa ``model``.
    """

    provider = "gemini"

    supports_native_tools = True

    DEFAULT_BASE_URL = (
        "https://generativelanguage.googleapis.com/v1beta"
    )

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

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        system, contents = self._convert_messages(
            messages
        )

        payload: dict[str, Any] = {
            "contents": contents,
        }

        if system:

            payload["systemInstruction"] = {
                "parts": [{"text": system}],
            }

        response = requests.post(
            (
                f"{self.base_url}/models/"
                f"{self.model}:generateContent"
            ),
            json=payload,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

        response.raise_for_status()

        data = response.json()

        candidates = data.get("candidates") or []

        if not candidates:

            detail = (
                data.get("promptFeedback")
                or "no candidates"
            )

            raise RuntimeError(
                "Gemini response contains no "
                f"candidates: {detail}"
            )

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        return "".join(
            part.get("text", "")
            for part in parts
        )

    # ==================================================
    # Native tool calling
    # ==================================================

    def _native_request(
        self,
        messages: list[dict[str, Any]],
        registry,
    ) -> LLMReply:

        names = self._native_tool_names(registry)

        system, contents = (
            self._convert_native_messages(
                messages,
                names,
            )
        )

        payload: dict[str, Any] = {
            "contents": contents,
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": names[tool.name],
                            "description": (
                                tool.description
                            ),
                            "parameters": (
                                self._parameters_schema(
                                    tool
                                )
                            ),
                        }
                        for tool in (
                            registry.list_definitions()
                        )
                    ]
                }
            ],
        }

        if system:

            payload["systemInstruction"] = {
                "parts": [{"text": system}],
            }

        response = requests.post(
            (
                f"{self.base_url}/models/"
                f"{self.model}:generateContent"
            ),
            json=payload,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

        if response.status_code in {400, 404, 422}:

            raise NativeToolsUnavailable(
                "Gemini rejected native tools "
                f"(HTTP {response.status_code})"
            )

        response.raise_for_status()

        data = response.json()

        candidates = data.get("candidates") or []

        if not candidates:

            detail = (
                data.get("promptFeedback")
                or "no candidates"
            )

            raise RuntimeError(
                "Gemini response contains no "
                f"candidates: {detail}"
            )

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        texts: list[str] = []

        reverse = {
            native: original
            for original, native in names.items()
        }

        calls: list[ToolCall] = []

        for part in parts:

            if isinstance(part.get("text"), str):
                texts.append(part["text"])

            function_call = part.get("functionCall")

            if isinstance(function_call, dict):

                native_name = function_call.get("name")

                if not native_name:
                    continue

                calls.append(
                    ToolCall(
                        tool=reverse.get(
                            native_name,
                            native_name,
                        ),
                        arguments=(
                            function_call.get("args")
                            or {}
                        ),
                        id=f"gemini-{len(calls)}",
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
        names: dict[str, str] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:

        system_parts: list[str] = []

        contents: list[dict[str, Any]] = []

        for message in messages:

            role = message.get("role", "user")

            content = message.get("content", "")

            if role == "system":

                system_parts.append(content)
                continue

            if role == "tool":

                parts = [
                    {
                        "functionResponse": {
                            "name": (
                                GeminiClient
                                ._mapped_tool_name(
                                    message.get(
                                        "name",
                                        "",
                                    ),
                                    names,
                                )
                            ),
                            "response": {
                                "result": content,
                            },
                        }
                    }
                ]

                target = "user"

            elif (
                role == "assistant"
                and message.get("tool_calls")
            ):

                parts = []

                if content:
                    parts.append({"text": content})

                for call in message["tool_calls"]:

                    parts.append(
                        {
                            "functionCall": {
                                "name": (
                                    GeminiClient
                                    ._mapped_tool_name(
                                        call["name"],
                                        names,
                                    )
                                ),
                                "args": call["arguments"],
                            }
                        }
                    )

                target = "model"

            else:

                parts = [{"text": content}]

                target = (
                    "model"
                    if role == "assistant"
                    else "user"
                )

            if (
                contents
                and contents[-1]["role"] == target
            ):

                contents[-1]["parts"].extend(parts)

            else:

                contents.append(
                    {
                        "role": target,
                        "parts": parts,
                    }
                )

        system = "\n\n".join(
            part
            for part in system_parts
            if part.strip()
        )

        if not contents:

            contents.append(
                {
                    "role": "user",
                    "parts": [{"text": ""}],
                }
            )

        return system, contents

    # ==================================================
    # Message conversion
    # ==================================================

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Estrae i messaggi di sistema e mappa i ruoli Gemini.

        Restituisce ``(system, contents)``.
        """

        system_parts: list[str] = []

        contents: list[dict[str, Any]] = []

        for message in messages:

            role = message.get("role", "user")

            content = message.get("content", "")

            if role == "system":

                system_parts.append(content)

                continue

            target = (
                "model"
                if role == "assistant"
                else "user"
            )

            if (
                contents
                and contents[-1]["role"] == target
            ):

                contents[-1]["parts"][0]["text"] += (
                    "\n\n" + content
                )

            else:

                contents.append(
                    {
                        "role": target,
                        "parts": [{"text": content}],
                    }
                )

        system = "\n\n".join(
            part
            for part in system_parts
            if part.strip()
        )

        if not contents:

            contents.append(
                {
                    "role": "user",
                    "parts": [{"text": ""}],
                }
            )

        return system, contents
