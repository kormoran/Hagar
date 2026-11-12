"""Benchmark qualità deterministico basato sul corpus fisso."""

from __future__ import annotations

import json
import re

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from core.benchmark_corpus import BenchmarkCorpus
from core.model_cards import utc_now


class QualityBenchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QualityCase:
    name: str
    prompt: str
    expected: Any
    scorer: Callable[[str], float]
    task: str = ""


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


def _score_extraction(
    text: str,
    expected: dict[str, Any],
) -> float:

    payload = _json_object(text)

    if payload is None:
        return 0.0

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


def _score_exact(text: str, expected: Any) -> float:

    return (
        1.0
        if _normal_text(text) == _normal_text(expected)
        else 0.0
    )


def _score_number(text: str, expected: int) -> float:

    match = re.search(r"\b(\d+)\b", text)

    return (
        1.0
        if match is not None and int(match.group(1)) == expected
        else 0.0
    )


def _char_ngrams(text: str, size: int) -> Counter:

    text = re.sub(r"\s+", " ", text.casefold()).strip()

    return Counter(
        text[index:index + size]
        for index in range(len(text) - size + 1)
    )


def _chrf(
    hypothesis: str,
    reference: str,
    *,
    max_n: int = 3,
    beta: float = 2.0,
) -> float:

    precisions = []
    recalls = []

    for size in range(1, max_n + 1):

        expected = _char_ngrams(reference, size)
        actual = _char_ngrams(hypothesis, size)

        if not expected:
            continue

        overlap = sum(
            min(count, actual.get(gram, 0))
            for gram, count in expected.items()
        )
        precision = overlap / max(sum(actual.values()), 1)
        recall = overlap / sum(expected.values())
        precisions.append(precision)
        recalls.append(recall)

    if not precisions:
        return 0.0

    precision = sum(precisions) / len(precisions)
    recall = sum(recalls) / len(recalls)

    if precision + recall == 0:
        return 0.0

    beta_squared = beta * beta
    return (
        (1 + beta_squared) * precision * recall
        / (beta_squared * precision + recall)
    )


def _score_translation(
    text: str,
    reference: str,
    required: tuple[str, ...],
) -> float:

    chrf = _chrf(text, reference)
    matches = sum(
        1
        for term in required
        if _normal_text(term) in _normal_text(text)
    )
    required_score = (
        matches / len(required)
        if required
        else 1.0
    )

    return 0.7 * chrf + 0.3 * required_score


def _score_summary(
    text: str,
    expected: list[str],
) -> float:

    if not text.strip():
        return 0.0

    matches = sum(
        1
        for term in expected
        if _normal_text(term) in _normal_text(text)
    )
    length_score = 1.0 if len(text.strip()) <= 500 else 0.5

    return (
        0.8 * (matches / len(expected))
        + 0.2 * length_score
    )


def _make_scorer(
    case: dict[str, Any],
    corpus: BenchmarkCorpus,
) -> Callable[[str], float]:

    name = str(case.get("scorer") or "")
    expected = case.get("expected")

    if name == "extraction":

        if not isinstance(expected, dict):
            raise QualityBenchError(
                "extraction case requires an expected object"
            )

        return lambda text: _score_extraction(text, expected)

    if name == "exact":

        return lambda text: _score_exact(text, expected)

    if name == "number":

        if isinstance(expected, bool) or not isinstance(
            expected,
            int,
        ):
            raise QualityBenchError(
                "number case requires an integer expected value"
            )

        return lambda text: _score_number(text, expected)

    if name == "summary":

        if not isinstance(expected, list):
            raise QualityBenchError(
                "summary case requires a list of key points"
            )

        return lambda text: _score_summary(text, expected)

    if name == "translation":

        reference_id = case.get("reference")

        if not isinstance(reference_id, str):
            raise QualityBenchError(
                "translation case requires a reference"
            )

        required = case.get("required", [])

        if not isinstance(required, list):
            raise QualityBenchError(
                "translation required terms must be a list"
            )

        reference = corpus.reference(reference_id)
        terms = tuple(str(item) for item in required)
        return lambda text: _score_translation(
            text,
            reference,
            terms,
        )

    raise QualityBenchError(
        f"unknown quality scorer: {name!r}"
    )


def cases(
    corpus: BenchmarkCorpus | None = None,
) -> tuple[QualityCase, ...]:

    corpus = corpus or BenchmarkCorpus.load()
    result = []

    for raw in corpus.quality:

        sample_id = str(raw.get("sample") or "")
        sample = corpus.text(sample_id).strip()
        prompt = str(raw.get("prompt") or "")
        name = str(raw.get("name") or "")

        if not name or not prompt:
            raise QualityBenchError(
                "quality case requires name and prompt"
            )

        result.append(
            QualityCase(
                name=name,
                prompt=prompt.replace("{text}", sample),
                expected=raw.get("expected"),
                scorer=_make_scorer(raw, corpus),
                task=str(raw.get("task") or name),
            )
        )

    return tuple(result)


def benchmark_quality(
    llm: Any,
    attempts: int = 2,
    corpus: BenchmarkCorpus | None = None,
) -> dict[str, Any]:

    if attempts <= 0:
        raise QualityBenchError("attempts must be positive")

    corpus = corpus or BenchmarkCorpus.load()
    cases_results = []
    grouped: dict[str, list[dict[str, Any]]] = {}

    for case in cases(corpus):

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

        result = {
            "name": case.name,
            "attempts": attempts,
            "scores": scores,
            "mean": round(sum(scores) / len(scores), 4),
            "errors": errors,
        }
        cases_results.append(result)
        grouped.setdefault(case.task or case.name, []).append(result)

    tasks = {}

    for task_name, task_cases in grouped.items():

        scores = [
            score
            for item in task_cases
            for score in item["scores"]
        ]
        tasks[task_name] = {
            "attempts": attempts,
            "cases": len(task_cases),
            "scores": scores,
            "mean": round(sum(scores) / len(scores), 4),
            "errors": [
                error
                for item in task_cases
                for error in item["errors"]
            ],
        }

    means = [
        item["mean"]
        for item in tasks.values()
    ]

    return {
        "suite_version": 3,
        "corpus": corpus.suite_name,
        "tested_at": utc_now(),
        "attempts": attempts,
        "tasks": tasks,
        "cases": cases_results,
        "overall": round(
            sum(means) / len(means),
            4,
        ),
    }
