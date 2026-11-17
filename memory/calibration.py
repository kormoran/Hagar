"""Calibrazione ufficiale delle soglie di recall vettoriale."""

from __future__ import annotations

import json
import math

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Iterable


class CalibrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CalibrationPair:

    query: str
    positives: tuple[str, ...]
    negatives: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CalibrationResult:

    model: str
    dimensions: int
    queries: int
    positives: int
    negatives: int
    min_score: float
    strong_score: float
    margin: float
    precision: float
    recall: float
    f1: float
    provider: str = ""
    revision: str = ""
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:

        return {
            "model": self.model,
            "provider": self.provider,
            "revision": self.revision,
            "dimensions": self.dimensions,
            "queries": self.queries,
            "positives": self.positives,
            "negatives": self.negatives,
            "memory": {
                "vector_min_score": self.min_score,
                "vector_strong_score": self.strong_score,
                "vector_margin": self.margin,
            },
            "metrics": {
                "precision": round(self.precision, 4),
                "recall": round(self.recall, 4),
                "f1": round(self.f1, 4),
            },
            "notes": list(self.notes),
        }

    def as_yaml(self) -> str:

        lines = [
            "# Generato da `hagar calibrate`.",
            f"# provider: {self.provider}",
            f"# model: {self.model}",
            f"# revision: {self.revision}",
            f"# queries: {self.queries}",
            f"# precision: {self.precision:.4f}",
            f"# recall: {self.recall:.4f}",
            f"# f1: {self.f1:.4f}",
            "memory:",
            f"  vector_min_score: {self.min_score:.3f}",
            f"  vector_strong_score: {self.strong_score:.3f}",
            f"  vector_margin: {self.margin:.3f}",
        ]

        for note in self.notes:
            lines.append(f"# nota: {note}")

        return "\n".join(lines) + "\n"


def load_pairs(path: str | Path) -> list[CalibrationPair]:

    source = Path(path)

    if not source.is_file():
        raise CalibrationError(
            f"calibration dataset not found: {source}"
        )

    text = source.read_text(encoding="utf-8").strip()

    if not text:
        raise CalibrationError("calibration dataset is empty")

    raw_items: list[Any]

    if text.startswith("["):
        try:
            raw_items = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CalibrationError(
                f"invalid calibration JSON: {exc}"
            ) from exc
    else:
        raw_items = []

        for number, line in enumerate(text.splitlines(), start=1):

            line = line.strip()

            if not line or line.startswith("#"):
                continue

            try:
                raw_items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CalibrationError(
                    f"invalid calibration JSONL at line {number}: {exc}"
                ) from exc

    pairs = []

    for number, item in enumerate(raw_items, start=1):

        if not isinstance(item, dict):
            raise CalibrationError(
                f"calibration item {number} must be an object"
            )

        query = item.get("query")

        if not isinstance(query, str) or not query.strip():
            raise CalibrationError(
                f"calibration item {number} has no query"
            )

        positives = _texts(
            item.get("positives", item.get("positive")),
            f"item {number} positives",
        )
        negatives = _texts(
            item.get("negatives", item.get("negative")),
            f"item {number} negatives",
        )

        if not positives:
            raise CalibrationError(
                f"calibration item {number} has no positives"
            )

        if not negatives:
            raise CalibrationError(
                f"calibration item {number} has no negatives"
            )

        pairs.append(
            CalibrationPair(
                query=query.strip(),
                positives=positives,
                negatives=negatives,
            )
        )

    if not pairs:
        raise CalibrationError("calibration dataset has no items")

    return pairs


def _texts(value: Any, name: str) -> tuple[str, ...]:

    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise CalibrationError(f"{name} must be a string or a list")

    result = tuple(
        str(item).strip()
        for item in values
        if str(item).strip()
    )

    if not result:
        raise CalibrationError(f"{name} is empty")

    return result


def _cosine(left: list[float], right: list[float]) -> float:

    return sum(
        a * b
        for a, b in zip(left, right)
    )


def calibrate(
    engine: Any,
    pairs: Iterable[CalibrationPair],
    *,
    min_precision: float = 0.90,
) -> CalibrationResult:

    items = list(pairs)

    if not items:
        raise CalibrationError("no calibration pairs")

    if not 0.0 < min_precision <= 1.0:
        raise CalibrationError(
            "min_precision must be between 0 and 1"
        )

    documents: list[str] = []
    labels: list[bool] = []
    grouped: list[tuple[list[float], list[float]]] = []

    for item in items:

        query_vector = engine.embed_query(item.query)
        positive_vectors = engine.embed_documents(
            list(item.positives)
        )
        negative_vectors = engine.embed_documents(
            list(item.negatives)
        )

        for text in item.positives:
            documents.append(text)
            labels.append(True)

        for text in item.negatives:
            documents.append(text)
            labels.append(False)

        grouped.append((
            [
                _cosine(query_vector, vector)
                for vector in positive_vectors
            ],
            [
                _cosine(query_vector, vector)
                for vector in negative_vectors
            ],
        ))

    scores = sorted({
        round(score, 6)
        for positive, negative in grouped
        for score in (*positive, *negative)
    })

    if not scores:
        raise CalibrationError("calibration produced no scores")

    candidates = sorted(set([0.0, 1.0, *scores]))
    best = None

    for threshold in candidates:

        true_positive = 0
        false_positive = 0
        false_negative = 0

        for positive, negative in grouped:

            true_positive += sum(
                score >= threshold
                for score in positive
            )
            false_positive += sum(
                score >= threshold
                for score in negative
            )
            false_negative += sum(
                score < threshold
                for score in positive
            )

        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 1.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )

        if best is None or (f1, threshold) > (
            best[0],
            best[1],
        ):
            best = (f1, threshold, precision, recall)

    assert best is not None
    _, min_score, precision, recall = best
    min_score = round(float(min_score), 3)

    strong_candidates = [
        threshold
        for threshold in candidates
        if threshold >= min_score
    ]
    strong_score = min_score

    for threshold in strong_candidates:

        true_positive = 0
        false_positive = 0

        for positive, negative in grouped:
            true_positive += sum(
                score >= threshold
                for score in positive
            )
            false_positive += sum(
                score >= threshold
                for score in negative
            )

        candidate_precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 1.0
        )

        if (
            true_positive > 0
            and candidate_precision >= min_precision
        ):
            strong_score = max(
                strong_score,
                round(float(threshold), 3),
            )

    gaps = sorted(
        max(positive) - max(negative)
        for positive, negative in grouped
        if positive and negative
    )
    margin = 0.04

    if gaps:
        position = max(
            0,
            min(
                len(gaps) - 1,
                int(math.floor(len(gaps) * 0.25)),
            ),
        )
        margin = max(
            0.02,
            min(0.20, round(gaps[position], 3)),
        )

    notes = []

    if len(items) < 20:
        notes.append(
            "campione piccolo: meno di 20 query, "
            "calibrare con dati reali"
        )

    if strong_score < min_score:
        strong_score = min_score

    return CalibrationResult(
        model=str(getattr(engine.config, "model", "unknown")),
        dimensions=int(getattr(engine, "dimensions", 0)),
        queries=len(items),
        positives=sum(len(item.positives) for item in items),
        negatives=sum(len(item.negatives) for item in items),
        min_score=min_score,
        strong_score=strong_score,
        margin=float(margin),
        precision=float(precision),
        recall=float(recall),
        f1=float(best[0]),
        provider=str(getattr(engine.config, "provider", "")),
        revision=str(
            getattr(
                getattr(
                    getattr(engine, "provider", None),
                    "manifest",
                    None,
                ),
                "revision",
                "",
            )
        ),
        notes=tuple(notes),
    )
