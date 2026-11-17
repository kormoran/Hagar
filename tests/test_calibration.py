"""Test della calibrazione ufficiale delle soglie."""

from __future__ import annotations

import json

import pytest

from memory.calibration import CalibrationError
from memory.calibration import calibrate
from memory.calibration import load_pairs


class FakeEngine:
    dimensions = 2
    config = type("Config", (), {"model": "fake-model"})()

    @staticmethod
    def _vector(text):

        if (
            "positivo" in text.lower()
            or "domanda" in text.lower()
        ):
            return [1.0, 0.0]

        return [0.0, 1.0]

    def embed_query(self, text):
        return self._vector(text)

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]


def write_dataset(tmp_path, items):

    path = tmp_path / "calibration.jsonl"
    path.write_text(
        "\n".join(json.dumps(item) for item in items) + "\n",
        encoding="utf-8",
    )
    return path


def test_load_and_calibrate(tmp_path):

    path = write_dataset(
        tmp_path,
        [
            {
                "query": "domanda uno",
                "positive": ["documento positivo uno"],
                "negative": ["documento negativo uno"],
            },
            {
                "query": "domanda due",
                "positive": ["documento positivo due"],
                "negative": ["documento negativo due"],
            },
        ],
    )

    pairs = load_pairs(path)
    result = calibrate(FakeEngine(), pairs)

    assert result.model == "fake-model"
    assert result.queries == 2
    assert result.positives == 2
    assert result.negatives == 2
    assert 0.0 <= result.min_score <= 1.0
    assert result.strong_score >= result.min_score
    assert result.margin >= 0.02
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert "memory:" in result.as_yaml()


def test_invalid_item_requires_negative(tmp_path):

    path = write_dataset(
        tmp_path,
        [
            {
                "query": "domanda",
                "positive": ["positivo"],
            },
        ],
    )

    with pytest.raises(CalibrationError):
        load_pairs(path)


def test_invalid_jsonl_reports_line(tmp_path):

    path = tmp_path / "broken.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(CalibrationError) as error:
        load_pairs(path)

    assert "line 1" in str(error.value)
