"""Verifica il dataset sintetico di calibrazione."""

from __future__ import annotations

from pathlib import Path

from memory.calibration import load_pairs


DATASET = (
    Path(__file__).resolve().parent.parent
    / "calibration"
    / "hagar-calibration-300.jsonl"
)


def test_calibration_dataset_shape():

    pairs = load_pairs(DATASET)

    assert len(pairs) == 60
    assert sum(len(pair.positives) for pair in pairs) == 120
    assert sum(len(pair.negatives) for pair in pairs) == 180

    texts = [
        text
        for pair in pairs
        for text in (*pair.positives, *pair.negatives)
    ]

    assert len(texts) == 300
    assert len(set(texts)) == 300
    assert all(150 <= len(text) <= 1200 for text in texts)
    assert all(20 <= len(pair.query) <= 120 for pair in pairs)
