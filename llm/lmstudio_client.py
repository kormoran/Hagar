"""Backend LM Studio (API OpenAI-compatibile locale)."""

from __future__ import annotations

from typing import Any

from llm.openai_compatible import OpenAICompatibleClient


class LMStudioClient(OpenAICompatibleClient):
    """
    Backend di LM Studio.

    LM Studio espone un server OpenAI-compatibile, di norma su
    ``http://localhost:1234/v1``. Non richiede una chiave, salvo che il
    server sia stato configurato per richiederla.
    """

    provider = "lmstudio"

    DEFAULT_BASE_URL = "http://localhost:1234/v1"

    @classmethod
    def _content(
        cls,
        content: Any,
    ) -> Any:

        if isinstance(content, list):

            for part in content:

                if (
                    isinstance(part, dict)
                    and part.get("mime_type")
                    == "image/webp"
                ):

                    raise RuntimeError(
                        "LM Studio non supporta WebP: "
                        "usa PNG o JPEG, oppure converti "
                        "l'immagine nella GUI."
                    )

        return super()._content(content)

    def __init__(
        self,
        model: str,
        host: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
        audit: Any = None,
    ) -> None:

        super().__init__(
            model=model,
            base_url=(
                host or self.DEFAULT_BASE_URL
            ),
            api_key=api_key,
            timeout=timeout,
            audit=audit,
        )
