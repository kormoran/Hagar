# llm/gemini_client.py

from __future__ import annotations

import requests

from typing import Any

from llm.base import LLMClient


class GeminiClient(LLMClient):
    """
    Backend Google Gemini (Generative Language API).

    I messaggi di sistema diventano ``systemInstruction``; il ruolo
    ``assistant`` diventa ``model``.
    """

    provider = "gemini"

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
