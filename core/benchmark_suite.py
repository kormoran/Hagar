"""Manifest versionato delle suite di benchmark."""

from __future__ import annotations

from typing import Any

from core.benchmark_corpus import BenchmarkCorpus


BENCHMARK_SUITE_VERSION = 3


def manifest() -> dict[str, Any]:

    corpus = BenchmarkCorpus.load()

    return {
        "version": BENCHMARK_SUITE_VERSION,
        "suite": corpus.suite_name,
        "corpus": corpus.manifest,
    }
