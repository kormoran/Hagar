"""Token usage: normalizzazione e contabilità di sessione."""

from __future__ import annotations

import threading

from dataclasses import dataclass
from typing import Any
from typing import Callable

from core.events import EventSink
from core.events import emit


def _non_negative_int(value: Any) -> int:

    if isinstance(value, bool):
        return 0

    if isinstance(value, int) and value >= 0:
        return value

    return 0


@dataclass(frozen=True)
class TokenUsage:
    """Usage normalizzato di una singola chiamata LLM."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    source: str = "provider"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict[str, int | str]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "source": self.source,
        }


def usage_from_openai(
    payload: dict[str, Any],
) -> TokenUsage:
    """OpenAI, DeepSeek e LM Studio (Chat Completions)."""

    usage = payload.get("usage") or {}

    if not isinstance(usage, dict):
        return TokenUsage(source="missing")

    prompt_details = (
        usage.get("prompt_tokens_details") or {}
    )
    completion_details = (
        usage.get("completion_tokens_details") or {}
    )

    input_tokens = _non_negative_int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
    )
    output_tokens = _non_negative_int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
    )
    cached = _non_negative_int(
        prompt_details.get("cached_tokens")
        or usage.get("cached_input_tokens")
    )
    reasoning = _non_negative_int(
        completion_details.get("reasoning_tokens")
    )

    source = (
        "provider"
        if input_tokens or output_tokens
        else "missing"
    )

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        reasoning_tokens=reasoning,
        source=source,
    )


def usage_from_anthropic(
    payload: dict[str, Any],
) -> TokenUsage:
    """Claude Messages API."""

    usage = payload.get("usage") or {}

    if not isinstance(usage, dict):
        return TokenUsage(source="missing")

    input_tokens = _non_negative_int(
        usage.get("input_tokens")
    )
    output_tokens = _non_negative_int(
        usage.get("output_tokens")
    )
    cached = _non_negative_int(
        usage.get("cache_read_input_tokens")
    )
    cache_creation = _non_negative_int(
        usage.get("cache_creation_input_tokens")
    )
    reasoning = _non_negative_int(
        usage.get("reasoning_tokens")
    )

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached + cache_creation,
        reasoning_tokens=reasoning,
        source=(
            "provider"
            if input_tokens or output_tokens
            else "missing"
        ),
    )


def usage_from_gemini(
    payload: dict[str, Any],
) -> TokenUsage:
    """Google Generative Language API."""

    usage = payload.get("usageMetadata") or {}

    if not isinstance(usage, dict):
        return TokenUsage(source="missing")

    input_tokens = _non_negative_int(
        usage.get("promptTokenCount")
    )
    output_tokens = _non_negative_int(
        usage.get("candidatesTokenCount")
    )
    cached = _non_negative_int(
        usage.get("cachedContentTokenCount")
    )
    reasoning = _non_negative_int(
        usage.get("thoughtsTokenCount")
    )

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        reasoning_tokens=reasoning,
        source=(
            "provider"
            if input_tokens or output_tokens
            else "missing"
        ),
    )


def usage_from_ollama(
    payload: dict[str, Any],
) -> TokenUsage:
    """Ollama /api/chat e /api/generate."""

    input_tokens = _non_negative_int(
        payload.get("prompt_eval_count")
    )
    output_tokens = _non_negative_int(
        payload.get("eval_count")
    )

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        source=(
            "provider"
            if input_tokens or output_tokens
            else "missing"
        ),
    )


UsageSink = Callable[[TokenUsage, str, str], None]


class UsageLedger:
    """Totali di token per la sessione corrente."""

    def __init__(
        self,
        event_sink: EventSink | None = None,
    ) -> None:

        self.event_sink = event_sink
        self._lock = threading.Lock()
        self._input = 0
        self._output = 0
        self._cached = 0
        self._reasoning = 0
        self._calls = 0

    def record(
        self,
        usage: TokenUsage,
        provider: str = "",
        model: str = "",
    ) -> None:

        with self._lock:

            self._input += usage.input_tokens
            self._output += usage.output_tokens
            self._cached += usage.cached_input_tokens
            self._reasoning += usage.reasoning_tokens
            self._calls += 1

            snapshot = self._snapshot_locked()

        emit(
            self.event_sink,
            "usage.updated",
            **snapshot,
            provider=provider,
            model=model,
            call=usage.as_dict(),
        )

    def _snapshot_locked(self) -> dict[str, int]:

        return {
            "input_tokens": self._input,
            "output_tokens": self._output,
            "cached_input_tokens": self._cached,
            "reasoning_tokens": self._reasoning,
            "total_tokens": self._input + self._output,
            "calls": self._calls,
        }

    def snapshot(self) -> dict[str, int]:

        with self._lock:
            return self._snapshot_locked()

    def reset(self) -> None:

        with self._lock:

            self._input = 0
            self._output = 0
            self._cached = 0
            self._reasoning = 0
            self._calls = 0
