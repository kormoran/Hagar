"""Spill degli output e potatura del contesto."""

from __future__ import annotations

from typing import Any


class OutputSpiller:
    """Sposta gli output grandi in un ArtifactStore."""

    def __init__(
        self,
        store: Any = None,
        max_inline_chars: int = 12_000,
        preview_chars: int = 1_200,
    ) -> None:

        self.store = store
        self.max_inline_chars = max(0, int(max_inline_chars))
        self.preview_chars = max(0, int(preview_chars))

    def spill(
        self,
        text: str,
        *,
        owner: str,
        tool: str,
    ) -> tuple[str, str | None]:

        if (
            self.store is None
            or len(text) <= self.max_inline_chars
        ):
            return text, None

        ref = self.store.put_text(
            text,
            owner=owner,
        )
        preview = text[: self.preview_chars]
        replacement = (
            f"[output spill: artifact_id={ref.artifact_id}; "
            f"size={ref.size} bytes; tool={tool}]\n"
            f"{preview}\n"
            "[... output completo nell'artifact ...]"
        )
        return replacement, ref.artifact_id


class ContextCompactor:
    """Sostituisce i risultati vecchi quando il contesto cresce troppo."""

    def __init__(
        self,
        max_chars: int = 24_000,
        keep_recent: int = 8,
    ) -> None:

        self.max_chars = max(0, int(max_chars))
        self.keep_recent = max(1, int(keep_recent))

    def compact(
        self,
        messages: list[dict[str, Any]],
    ) -> int:

        if self.max_chars <= 0:
            return 0

        total = sum(
            len(message.get("content", ""))
            for message in messages
            if isinstance(message.get("content"), str)
        )

        if total <= self.max_chars:
            return 0

        cutoff = max(0, len(messages) - self.keep_recent)
        removed = 0

        for index, message in enumerate(messages):

            if index >= cutoff:
                break

            if message.get("role") == "system":
                continue

            content = message.get("content")

            if not isinstance(content, str):
                continue

            if content.startswith("[context omitted"):
                continue

            messages[index] = {
                **message,
                "content": (
                    "[context omitted: old tool or conversation result]"
                ),
            }
            removed += 1

        return removed
