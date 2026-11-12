"""Benchmark qualità deterministico, senza dataset esterni."""

from __future__ import annotations

import json
import re

from collections import Counter
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


def _translation_scorer(
    reference: str,
    required: tuple[str, ...],
) -> Callable[[str], float]:

    def score(text: str) -> float:

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

    return score


def _score_summary(text: str) -> float:

    if not text.strip():
        return 0.0

    required = (
        "broker",
        "modelli locali",
        "memoria",
        "1.0",
    )
    matches = sum(
        1
        for term in required
        if _normal_text(term) in _normal_text(text)
    )
    length_score = 1.0 if len(text.strip()) <= 500 else 0.5

    return (
        0.8 * (matches / len(required))
        + 0.2 * length_score
    )


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
        QualityCase(
            name="summary",
            prompt=(
                "Riassumi in al massimo due frasi, in italiano:\n\n"
                "Hagar 0.8 introduce il broker LLM e la scelta del "
                "modello per task. La 0.9 si occupera' del ciclo di "
                "vita delle memorie. I modelli locali restano gestiti "
                "da LM Studio e Ollama. Il runtime locale integrato "
                "arrivera' dopo la 1.0."
            ),
            expected=(
                "broker, modelli locali, memoria, 1.0"
            ),
            scorer=_score_summary,
            task="summary",
        ),
        QualityCase(
            name="translation_it_en",
            prompt=(
                "Traduci in inglese. Rispondi solo con la traduzione:\n\n"
                "Hagar esegue i tool nella sandbox. Il report e' in "
                "/home/ai/workspace/report.txt e il comando e' "
                "`hagar --config hagar.yaml`."
            ),
            expected=(
                "Hagar runs tools in the sandbox. The report is in "
                "/home/ai/workspace/report.txt and the command is "
                "`hagar --config hagar.yaml`."
            ),
            scorer=_translation_scorer(
                (
                    "Hagar runs tools in the sandbox. The report is in "
                    "/home/ai/workspace/report.txt and the command is "
                    "`hagar --config hagar.yaml`."
                ),
                (
                    "/home/ai/workspace/report.txt",
                    "hagar --config hagar.yaml",
                ),
            ),
            task="translation",
        ),
        QualityCase(
            name="translation_en_it",
            prompt=(
                "Traduci in italiano. Rispondi solo con la traduzione:\n\n"
                "The broker chooses a model, but it never grants "
                "capabilities."
            ),
            expected=(
                "Il broker sceglie un modello, ma non concede mai "
                "capability."
            ),
            scorer=_translation_scorer(
                (
                    "Il broker sceglie un modello, ma non concede mai "
                    "capability."
                ),
                ("broker", "modello", "capability"),
            ),
            task="translation",
        ),
    )


def benchmark_quality(
    llm: Any,
    attempts: int = 2,
) -> dict[str, Any]:

    if attempts <= 0:
        raise QualityBenchError("attempts must be positive")

    cases_results = []
    grouped: dict[str, list[dict[str, Any]]] = {}

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

        result = {
            "name": case.name,
            "attempts": attempts,
            "scores": scores,
            "mean": round(sum(scores) / len(scores), 4),
            "errors": errors,
        }
        cases_results.append(result)
        grouped.setdefault(
            case.task or case.name,
            [],
        ).append(result)

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
        "suite_version": 2,
        "tested_at": utc_now(),
        "attempts": attempts,
        "tasks": tasks,
        "cases": cases_results,
        "overall": round(
            sum(means) / len(means),
            4,
        ),
    }
