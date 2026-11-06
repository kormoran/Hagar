"""Backend OpenAI/ChatGPT."""

from __future__ import annotations

from typing import Any

from llm.openai_compatible import OpenAICompatibleClient


class OpenAIClient(OpenAICompatibleClient):
    """
    Backend dell'API OpenAI (ChatGPT via API).

    Il nome del modello è quello dell'API, ad esempio ``gpt-4o`` o
    ``gpt-4.1``. Non confondere l'abbonamento ChatGPT con l'API: servono
    una chiave OpenAI e credito API.
    """

    provider = "openai"

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 120,
        audit: Any = None,
    ) -> None:

        if not api_key:

            raise ValueError(
                "api_key is required"
            )

        super().__init__(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            audit=audit,
        )
