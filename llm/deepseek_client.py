# llm/deepseek_client.py

from __future__ import annotations

import requests

from typing import Any

from llm.base import LLMClient


class DeepSeekClient(LLMClient):
    """
    Backend DeepSeek.

    Usa l'API compatibile OpenAI: POST /chat/completions con
    autenticazione Bearer. I messaggi di sistema restano nel dialogo.
    """

    provider = "deepseek"

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
            headers={
                "Authorization":
                    f"Bearer {self.api_key}",
                "Content-Type":
                    "application/json",
            },
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
