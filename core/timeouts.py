"""Stima dei timeout LLM a partire dalle schede misurate."""

from __future__ import annotations

import json

from dataclasses import dataclass
from typing import Any

from core.model_registry import ModelEntry


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    enabled: bool = True
    floor_seconds: float = 30.0
    ceiling_seconds: float = 900.0
    safety_factor: float = 1.5
    cold_start_seconds: float = 120.0
    turn_ceiling_seconds: float = 1800.0

    @classmethod
    def from_config(cls, config: Any) -> "TimeoutPolicy":

        return cls(
            enabled=bool(getattr(config, "adaptive", True)),
            floor_seconds=float(
                getattr(config, "floor_seconds", 30.0)
            ),
            ceiling_seconds=float(
                getattr(config, "ceiling_seconds", 900.0)
            ),
            safety_factor=float(
                getattr(config, "safety_factor", 1.5)
            ),
            cold_start_seconds=float(
                getattr(config, "cold_start_seconds", 120.0)
            ),
            turn_ceiling_seconds=float(
                getattr(
                    config,
                    "turn_ceiling_seconds",
                    1800.0,
                )
            ),
        )

    def request_timeout(
        self,
        entry: ModelEntry | None,
        messages: list[dict[str, Any]] | None,
        max_tokens: int,
        fallback: float | None,
    ) -> float | None:
        """Timeout per una singola chiamata, con floor/ceiling."""

        if not self.enabled:
            return fallback

        if entry is None:
            return self._clamp(fallback)

        p95 = _latency_ms(entry)

        if p95 is None:
            return self._clamp(fallback)

        input_chars = _message_chars(messages or [])
        input_tokens = max(1, input_chars // 4)
        output_tokens = max(1, int(max_tokens))

        # La scheda misura un prompt breve: aggiungo un fattore prudente
        # per prompt lunghi e output lunghi.
        input_factor = 1.0 + min(
            2.0,
            max(0, input_tokens - 1000) / 16000.0,
        )
        output_factor = 1.0 + min(
            1.0,
            max(0, output_tokens - 256) / 4096.0,
        )
        estimate = (
            (p95 / 1000.0)
            * self.safety_factor
            * input_factor
            * output_factor
        )

        return self._clamp(estimate)

    def turn_timeout(
        self,
        entry: ModelEntry | None,
        max_calls: int = 10,
    ) -> float | None:
        """Tetto prudente per un turno agentico."""

        if not self.enabled:
            return None

        request = self.request_timeout(
            entry,
            [],
            512,
            fallback=self.ceiling_seconds,
        )

        if request is None:
            return self._clamp(self.turn_ceiling_seconds)

        calls = max(2, int(max_calls))
        estimate = (
            request * calls / 2.0
            + self.cold_start_seconds
        )

        return self._clamp(
            estimate,
            ceiling=self.turn_ceiling_seconds,
        )

    def _clamp(
        self,
        value: float | None,
        *,
        ceiling: float | None = None,
    ) -> float | None:

        if value is None:
            return None

        maximum = ceiling or self.ceiling_seconds

        return max(
            self.floor_seconds,
            min(float(maximum), float(value)),
        )


def _latency_ms(entry: ModelEntry) -> float | None:

    card = entry.card

    if not isinstance(card, dict):
        return None

    try:
        chat = card["benchmarks"]["chat"]["duration_ms"]
    except (KeyError, TypeError):
        return None

    value = chat.get("p95") or chat.get("p50")

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        return None

    return max(0.0, float(value))


def _message_chars(
    messages: list[dict[str, Any]],
) -> int:

    try:
        return len(
            json.dumps(
                messages,
                ensure_ascii=False,
                default=str,
            )
        )
    except (TypeError, ValueError):
        return sum(
            len(str(message.get("content", "")))
            for message in messages
            if isinstance(message, dict)
        )
