"""Broker LLM puro: filtra e ordina i modelli del registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from core.model_registry import ModelEntry, ModelRegistry
from core.task_profile import TaskProfile, TaskProfileStore


class BrokerError(RuntimeError):

    def __init__(
        self,
        message: str,
        *,
        excluded: list[dict[str, Any]] | None = None,
    ) -> None:

        super().__init__(message)
        self.excluded = excluded or []


@dataclass(frozen=True, slots=True)
class Selection:
    profile: str
    entry: ModelEntry
    score: float
    reasons: tuple[str, ...]
    excluded: tuple[dict[str, Any], ...] = field(
        default_factory=tuple
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "model_id": self.entry.id,
            "provider": self.entry.provider,
            "model": self.entry.model,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "excluded": list(self.excluded),
        }


class Broker:
    """Selezione deterministica di un modello per un TaskProfile."""

    WEIGHTS = {
        "balanced": {
            "quality": 0.35,
            "latency": 0.25,
            "cost": 0.20,
            "context": 0.20,
        },
        "quality": {
            "quality": 0.70,
            "latency": 0.15,
            "cost": 0.075,
            "context": 0.075,
        },
        "latency": {
            "quality": 0.20,
            "latency": 0.60,
            "cost": 0.10,
            "context": 0.10,
        },
        "cost": {
            "quality": 0.20,
            "latency": 0.10,
            "cost": 0.60,
            "context": 0.10,
        },
        "context": {
            "quality": 0.20,
            "latency": 0.10,
            "cost": 0.10,
            "context": 0.60,
        },
    }

    def __init__(
        self,
        registry: ModelRegistry,
        profiles: TaskProfileStore,
    ) -> None:

        self.registry = registry
        self.profiles = profiles

    def select(
        self,
        profile: str | TaskProfile,
    ) -> Selection:

        task = self._profile(profile)
        eligible: list[tuple[ModelEntry, float, list[str]]] = []
        excluded: list[dict[str, Any]] = []

        for entry in self.registry.enabled():
            reasons = self._exclusion_reasons(entry, task)

            if reasons:
                excluded.append({
                    "model_id": entry.id,
                    "reasons": reasons,
                })
                continue

            score, score_reasons = self._score(entry, task)
            eligible.append((entry, score, score_reasons))

        if not eligible:
            raise BrokerError(
                "no eligible model for profile "
                f"{task.name!r}",
                excluded=excluded,
            )

        eligible.sort(
            key=lambda item: (
                -item[1],
                -(item[0].quality or 0.0),
                item[0].id,
            )
        )
        entry, score, reasons = eligible[0]

        return Selection(
            profile=task.name,
            entry=entry,
            score=score,
            reasons=tuple(
                [
                    *reasons,
                    f"score {score:.4f}",
                ]
            ),
            excluded=tuple(excluded),
        )

    def explain(
        self,
        profile: str | TaskProfile,
    ) -> dict[str, Any]:

        task = self._profile(profile)
        ranked = []
        excluded = []

        for entry in self.registry.enabled():
            reasons = self._exclusion_reasons(entry, task)

            if reasons:
                excluded.append({
                    "model_id": entry.id,
                    "reasons": reasons,
                })
                continue

            score, score_reasons = self._score(entry, task)
            ranked.append({
                "model_id": entry.id,
                "provider": entry.provider,
                "model": entry.model,
                "score": round(score, 4),
                "reasons": score_reasons,
            })

        ranked.sort(
            key=lambda item: (
                -item["score"],
                item["model_id"],
            )
        )

        return {
            "profile": task.name,
            "selected": ranked[0] if ranked else None,
            "ranked": ranked,
            "excluded": excluded,
        }

    # --------------------------------------------------
    # Profile / filters
    # --------------------------------------------------

    def _profile(
        self,
        profile: str | TaskProfile,
    ) -> TaskProfile:

        if isinstance(profile, TaskProfile):
            if not profile.enabled:
                raise BrokerError(
                    f"task profile is disabled: {profile.name}"
                )
            return profile

        task = self.profiles.get(profile)

        if task is None:
            raise BrokerError(
                f"unknown task profile: {profile}"
            )

        if not task.enabled:
            raise BrokerError(
                f"task profile is disabled: {profile}"
            )

        return task

    def _exclusion_reasons(
        self,
        entry: ModelEntry,
        task: TaskProfile,
    ) -> list[str]:

        reasons = []

        missing = task.required_capabilities - entry.capabilities

        if missing:
            reasons.append(
                "missing capabilities: "
                + ", ".join(sorted(missing))
            )

        if task.privacy == "local_only" and entry.locality != "local":
            reasons.append(
                f"privacy local_only, model is {entry.locality}"
            )

        if task.privacy == "remote_only" and entry.locality != "remote":
            reasons.append(
                f"privacy remote_only, model is {entry.locality}"
            )

        if task.min_context is not None:

            if entry.context_window is None:
                reasons.append("context window unknown")
            elif entry.context_window < task.min_context:
                reasons.append(
                    f"context {entry.context_window} < "
                    f"{task.min_context}"
                )

        latency = _chat_p50(entry)

        if task.max_latency_ms is not None:

            if latency is None:
                reasons.append("latency unknown")
            elif latency > task.max_latency_ms:
                reasons.append(
                    f"p50 latency {latency:.0f}ms > "
                    f"{task.max_latency_ms}ms"
                )

        if task.max_cost_per_1k_input is not None:

            if entry.cost_per_1k_input is None:
                reasons.append("input cost unknown")
            elif (
                entry.cost_per_1k_input
                > task.max_cost_per_1k_input
            ):
                reasons.append(
                    "input cost "
                    f"{entry.cost_per_1k_input:g} > "
                    f"{task.max_cost_per_1k_input:g}"
                )

        if task.max_cost_per_1k_output is not None:

            if entry.cost_per_1k_output is None:
                reasons.append("output cost unknown")
            elif (
                entry.cost_per_1k_output
                > task.max_cost_per_1k_output
            ):
                reasons.append(
                    "output cost "
                    f"{entry.cost_per_1k_output:g} > "
                    f"{task.max_cost_per_1k_output:g}"
                )

        if task.quality_floor is not None:

            if entry.quality is None:
                reasons.append("quality unknown")
            elif entry.quality < task.quality_floor:
                reasons.append(
                    f"quality {entry.quality:g} < "
                    f"{task.quality_floor:g}"
                )

        return reasons

    # --------------------------------------------------
    # Score
    # --------------------------------------------------

    def _score(
        self,
        entry: ModelEntry,
        task: TaskProfile,
    ) -> tuple[float, list[str]]:

        weights = self.WEIGHTS[task.prefer]
        reasons = []

        quality = entry.quality

        if quality is None:
            quality_score = 0.30
            reasons.append("quality unknown, penalty")
        else:
            quality_score = _clamp(quality, 0.0, 1.0)
            reasons.append(f"quality {quality:.2f}")

        latency = _chat_p50(entry)

        if latency is None:
            latency_score = 0.30
            reasons.append("latency unknown, penalty")
        else:
            latency_score = 1.0 / (
                1.0 + max(latency, 0.0) / 5000.0
            )
            reasons.append(f"p50 latency {latency:.0f}ms")

        cost = _cost(entry)

        if cost is None:
            cost_score = 0.30
            reasons.append("cost unknown, penalty")
        else:
            cost_score = 1.0 / (1.0 + max(cost, 0.0))
            reasons.append(f"cost {cost:g}")

        context = entry.context_window

        if context is None:
            context_score = 0.30
            reasons.append("context unknown, penalty")
        else:
            floor = task.min_context or 32768
            context_score = _clamp(
                context / max(floor * 2, 1),
                0.0,
                1.0,
            )
            reasons.append(f"context {context}")

        score = (
            quality_score * weights["quality"]
            + latency_score * weights["latency"]
            + cost_score * weights["cost"]
            + context_score * weights["context"]
        )

        return _clamp(score, 0.0, 1.0), reasons


def _chat_p50(entry: ModelEntry) -> float | None:

    card = entry.card

    if not isinstance(card, dict):
        return None

    try:
        value = (
            card["benchmarks"]["chat"]["duration_ms"]["p50"]
        )
    except (KeyError, TypeError):
        return None

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        return None

    return float(value)


def _cost(entry: ModelEntry) -> float | None:

    values = [
        value
        for value in (
            entry.cost_per_1k_input,
            entry.cost_per_1k_output,
        )
        if value is not None
    ]

    return max(values) if values else None


def _clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:

    return max(minimum, min(value, maximum))
