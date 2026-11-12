"""Benchmark qualità deterministico, senza dataset esterni."""

from __future__ import annotations

import json
import re

from dataclasses import dataclass
from typing import Any, Callable

from core.model_cards import utc_now


class QualityBenchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QualityCase:
    name: str
    prompt: str
    expected: Any
    scorer: Callable[[str], float]


def _json_object(text: str) -> dict[str, Any] | None:

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if match is None:
        return None

    try:
        payload = json.loads(match.group(0))
    except ValueError:
        return None

    return payload if isinstance(payload, dict) else None


def _normal_text(value: Any) -> str:

    text = str(value).strip().casefold()
    text = re.sub(r"\s+", " ", text)

    return text.strip(" \t\r\n.,;:!?\"'`")


def _score_extraction(text: str) -> float:

    payload = _json_object(text)

    if payload is None:
        return 0.0

    expected = {
        "name": "Mario Rossi",
        "age": 42,
        "city": "Roma",
    }
    matches = 0

    for key, value in expected.items():

        actual = payload.get(key)

        if key == "age":

            try:
                actual = int(actual)
            except (TypeError, ValueError):
                actual = None

        if _normal_text(actual) == _normal_text(value):
            matches += 1

    return matches / len(expected)


def _score_instruction(text: str) -> float:

    return 1.0 if _normal_text(text) == "hagar" else 0.0


def _score_reasoning(text: str) -> float:

    return 1.0 if re.search(r"\b7\b", text) else 0.0


def _score_coding(text: str) -> float:

    return 1.0 if re.search(r"\b3\b", text) else 0.0


def cases() -> tuple[QualityCase, ...]:

    return (
        QualityCase(
            name="extraction",
            prompt=(
                "Estrai nome, eta e citta da questo testo. "
                "Rispondi solo con un oggetto JSON con le chiavi "
                "name, age, city.\n\n"
                "Mario Rossi, 42 anni, Roma."
            ),
            expected={
                "name": "Mario Rossi",
                "age": 42,
                "city": "Roma",
            },
            scorer=_score_extraction,
        ),
        QualityCase(
            name="instruction",
            prompt=(
                "Rispondi esattamente con la parola HAGAR, "
                "senza altro testo."
            ),
            expected="HAGAR",
            scorer=_score_instruction,
        ),
        QualityCase(
            name="reasoning",
            prompt=(
                "Quanto fa 3 + 4? Rispondi solo con il numero."
            ),
            expected="7",
            scorer=_score_reasoning,
        ),
        QualityCase(
            name="coding",
            prompt=(
                "Cosa stampa questo codice Python?\n"
                "print(len([1, 2, 3]))\n"
                "Rispondi solo con il numero."
            ),
            expected="3",
            scorer=_score_coding,
        ),
    )


def benchmark_quality(
    llm: Any,
    attempts: int = 2,
) -> dict[str, Any]:

    if attempts <= 0:
        raise QualityBenchError("attempts must be positive")

    tasks = {}

    for case in cases():

        scores = []
        errors = []

        for _ in range(attempts):

            try:
                response = llm.chat([
                    {
                        "role": "user",
                        "content": case.prompt,
                    }
                ])
            except Exception as exc:
                errors.append(str(exc))
                scores.append(0.0)
                continue

            scores.append(
                max(0.0, min(1.0, case.scorer(response)))
            )

        mean = sum(scores) / len(scores)
        tasks[case.name] = {
            "attempts": attempts,
            "scores": scores,
            "mean": round(mean, 4),
            "errors": errors,
        }

    means = [
        item["mean"]
        for item in tasks.values()
    ]

    return {
        "suite_version": 1,
        "tested_at": utc_now(),
        "attempts": attempts,
        "tasks": tasks,
        "overall": round(
            sum(means) / len(means),
            4,
        ),
    }
