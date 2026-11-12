"""Test del corpus benchmark e dei suoi hash."""

from __future__ import annotations

import shutil

import pytest

from core.benchmark_corpus import (
    BenchmarkCorpus,
    BenchmarkCorpusError,
    default_corpus_root,
)
from core.benchmark_suite import manifest as suite_manifest
from core.quality_bench import cases as quality_cases
from core.vision_bench import cases as vision_cases


def test_default_corpus_is_complete():
    corpus = BenchmarkCorpus.load()

    assert len(corpus.texts) == 7
    assert len(corpus.references) == 2
    assert len(corpus.images) == 6
    assert len(quality_cases(corpus)) == 8
    assert len(vision_cases(corpus)) == 6
    assert corpus.text("it_technical").strip()
    assert corpus.reference("it_broker_en").strip()
    assert corpus.image("chart_bars_01").startswith(
        b"\x89PNG\r\n\x1a\n"
    )


def test_suite_manifest_contains_hashes():
    manifest = suite_manifest()

    assert manifest["version"] == 3
    assert manifest["suite"]
    assert len(manifest["corpus"]["texts"]) == 7
    assert len(manifest["corpus"]["images"]) == 6


def test_corpus_rejects_unknown_samples():
    corpus = BenchmarkCorpus.load()

    with pytest.raises(BenchmarkCorpusError):
        corpus.text("missing")

    with pytest.raises(BenchmarkCorpusError):
        corpus.image("missing")


def test_corpus_rejects_changed_file(tmp_path):
    source = default_corpus_root()
    target = tmp_path / "corpus"
    shutil.copytree(source, target)

    path = target / "text" / "it_technical.md"
    path.write_text("contenuto cambiato", encoding="utf-8")

    with pytest.raises(BenchmarkCorpusError):
        BenchmarkCorpus.load(target)
