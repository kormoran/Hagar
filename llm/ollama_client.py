# llm/ollama_client.py

from __future__ import annotations

import requests

from typing import Any

from llm.base import LLMClient


class OllamaClient(LLMClient):
    """Backend Ollama (API nativa /api/chat e /api/generate)."""

    provider = "ollama"

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

        return response["message"]["content"]
