"""Benchmark sintetico di memoria e aderenza al contesto."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import time

from core.model_cards import utc_now


class MemoryBenchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MemoryCase:
    name: str
    messages: tuple[dict[str, str], ...]
    expected: tuple[str, ...]
    forbidden: tuple[str, ...] = ()
    task: str = "memory"
    long_context: bool = False


def _case(
    name: str,
    turns: list[tuple[str, str]],
    expected: tuple[str, ...],
    *,
    forbidden: tuple[str, ...] = (),
    long_context: bool = False,
) -> MemoryCase:

    return MemoryCase(
        name=name,
        messages=tuple(
            {"role": role, "content": content}
            for role, content in turns
        ),
        expected=expected,
        forbidden=forbidden,
        long_context=long_context,
    )


def cases() -> tuple[MemoryCase, ...]:

    return (
        _case(
            "memory_recall_simple",
            [
                ("user", "Ricorda: il progetto si chiama Atreides."),
                ("assistant", "Ok, progetto Atreides."),
                ("user", "Come si chiama il progetto?"),
            ],
            ("atreides",),
        ),
        _case(
            "memory_distractor",
            [
                ("user", (
                    "Il deploy usa la porta 8443. "
                    "La porta 8080 è solo sviluppo."
                )),
                ("assistant", "Ok."),
                ("user", "Quale porta usa il deploy?"),
            ],
            ("8443",),
            forbidden=("8080",),
        ),
        _case(
            "memory_contradiction",
            [
                ("user", "Il referente è Mario."),
                ("assistant", "Ok."),
                ("user", "Aggiornamento: il referente ora è Luca."),
                ("assistant", "Ok."),
                ("user", "Chi è il referente attuale?"),
            ],
            ("luca",),
            forbidden=("mario",),
        ),
        _case(
            "memory_instruction_retention",
            [
                ("user", "Da ora rispondi sempre in italiano."),
                ("assistant", "Va bene."),
                ("user", "What is the capital of France?"),
            ],
            ("parigi",),
        ),
        _case(
            "memory_long_context",
            [
                ("user", (
                    "Memorizza questo codice: ZENITH-42. "
                    + ("Contesto irrilevante. " * 220)
                    + "Qual è il codice?"
                )),
            ],
            ("zenith-42", "zenith 42"),
            long_context=True,
        ),
        _case(
            "memory_false_premise",
            [
                ("user", "Il server si chiama Vega."),
                ("assistant", "Ok."),
                ("user", "Il server si chiama Vega o Sirio?"),
            ],
            ("vega",),
            forbidden=("sirio",),
        ),
    )


def _score(
    text: str,
    expected: tuple[str, ...],
    forbidden: tuple[str, ...],
) -> float:

    normalized = " ".join(str(text).casefold().split())

    if not normalized:
        return 0.0

    hits = sum(
        1
        for item in expected
        if item.casefold() in normalized
    )
    bad = sum(
        1
        for item in forbidden
        if item.casefold() in normalized
    )
    score = hits / max(len(expected), 1)
    score -= min(0.5, 0.25 * bad)

    return max(0.0, min(1.0, score))


def benchmark_memory(
    llm: Any,
    attempts: int = 1,
) -> dict[str, Any]:

    if attempts <= 0:
        raise MemoryBenchError("attempts must be positive")

    case_results = []

    for case in cases():

        scores = []
        errors = []
        latencies = []

        for _ in range(attempts):

            started = time.perf_counter()

            try:
                response = llm.chat(list(case.messages))
            except Exception as exc:
                errors.append(str(exc))
                scores.append(0.0)
                latencies.append(
                    (time.perf_counter() - started) * 1000
                )
                continue

            latencies.append(
                (time.perf_counter() - started) * 1000
            )
            scores.append(
                _score(response, case.expected, case.forbidden)
            )

        case_results.append({
            "name": case.name,
            "task": case.task,
            "long_context": case.long_context,
            "attempts": attempts,
            "scores": scores,
            "mean": round(sum(scores) / len(scores), 4),
            "errors": errors,
            "duration_ms": _stats(latencies),
            "expected": list(case.expected),
            "forbidden": list(case.forbidden),
        })

    scores = [
        score
        for case in case_results
        for score in case["scores"]
    ]
    mean = round(sum(scores) / len(scores), 4) if scores else 0.0

    return {
        "suite_version": 1,
        "tested_at": utc_now(),
        "attempts": attempts,
        "tasks": {
            "memory": {
                "attempts": attempts,
                "cases": len(case_results),
                "scores": scores,
                "mean": mean,
                "errors": [
                    error
                    for case in case_results
                    for error in case["errors"]
                ],
                "case_results": case_results,
            }
        },
        "overall": mean,
    }


def _stats(values: list[float]) -> dict[str, Any]:

    if not values:
        return {
            "count": 0,
            "p50": None,
            "p95": None,
            "max": None,
        }

    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        index = (len(ordered) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        weight = index - lower
        return (
            ordered[lower] * (1 - weight)
            + ordered[upper] * weight
        )

    return {
        "count": len(ordered),
        "p50": round(percentile(0.50), 2),
        "p95": round(percentile(0.95), 2),
        "max": round(ordered[-1], 2),
    }
