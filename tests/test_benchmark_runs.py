"""Test dello storico dei run di benchmark."""

from __future__ import annotations

import json

import pytest

from core.benchmark_runs import (
    BenchmarkRunError,
    BenchmarkRunStore,
)


def report(model="test-model"):
    return {
        "provider": "fake",
        "model": model,
        "tested_at": "2026-11-12T20:00:00+00:00",
        "quality": {"overall": 0.75},
    }


def test_save_list_and_load(tmp_path):
    store = BenchmarkRunStore(tmp_path / "runs")
    path = store.save(report(), run_id="run-1")

    assert path.is_file()
    loaded = store.load("run-1")

    assert loaded is not None
    assert loaded["run_id"] == "run-1"
    assert loaded["suite_version"] == 2
    assert loaded["provider"] == "fake"
    assert loaded["saved_at"]

    listed = store.list()

    assert len(listed) == 1
    assert listed[0]["run_id"] == "run-1"


def test_runs_are_append_only(tmp_path):
    store = BenchmarkRunStore(tmp_path / "runs")
    store.save(report("a"), run_id="run-a")
    store.save(report("b"), run_id="run-b")

    assert {item["model"] for item in store.list()} == {"a", "b"}


def test_limit_and_missing(tmp_path):
    store = BenchmarkRunStore(tmp_path / "runs")
    store.save(report("a"), run_id="run-a")
    store.save(report("b"), run_id="run-b")

    assert len(store.list(limit=1)) == 1
    assert store.load("missing") is None


def test_invalid_report_is_rejected(tmp_path):
    store = BenchmarkRunStore(tmp_path / "runs")

    with pytest.raises(BenchmarkRunError):
        store.save({"model": "no-provider"})


def test_malformed_file_is_ignored(tmp_path):
    store = BenchmarkRunStore(tmp_path / "runs")
    store.root.mkdir(parents=True)
    (store.root / "bad.json").write_text(
        json.dumps({"provider": "fake", "model": "x"}),
        encoding="utf-8",
    )
    (store.root / "broken.json").write_text(
        "{not json",
        encoding="utf-8",
    )

    assert len(store.list()) == 1
