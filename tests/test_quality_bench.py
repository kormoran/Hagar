"""Test del benchmark di qualità."""

from __future__ import annotations

from core.benchmark_corpus import BenchmarkCorpus
from core.quality_bench import QualityBenchError, benchmark_quality


class FakeLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []
        self.corpus = BenchmarkCorpus.load()

    def chat(self, messages):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)

        if self.error is not None:
            raise self.error

        if "Mario Rossi" in prompt:
            return self.responses.get(
                "extraction",
                '{"name":"Mario Rossi","age":42,"city":"Roma"}',
            )

        if "HAGAR" in prompt:
            return self.responses.get("instruction", "HAGAR")

        if "componenti" in prompt:
            return self.responses.get("reasoning", "6")

        if "print(len" in prompt:
            return self.responses.get("coding", "3")

        if "Riassumi" in prompt:

            if "sandbox" in prompt:
                return self.responses.get(
                    "summary",
                    "Hagar usa una sandbox, una policy e dei tool; "
                    "il broker sceglie il modello e resta fuori dalla 1.0.",
                )

            return self.responses.get(
                "summary",
                "Il catalogo e le schede misurate alimentano i profili; "
                "il broker registra la scelta nell'audit.",
            )

        if "Traduci in inglese" in prompt:
            return self.responses.get(
                "translation_it_en",
                self.corpus.reference("it_broker_en"),
            )

        if "Traduci in italiano" in prompt:
            return self.responses.get(
                "translation_en_it",
                self.corpus.reference("en_broker_it"),
            )

        return "OK"


def test_quality_benchmark_perfect_answers():
    report = benchmark_quality(FakeLLM(), attempts=2)

    assert report["suite_version"] == 3
    assert report["overall"] == 1.0
    assert set(report["tasks"]) == {
        "extraction",
        "instruction",
        "reasoning",
        "coding",
        "summary",
        "translation",
    }
    assert all(
        item["mean"] == 1.0
        for item in report["tasks"].values()
    )


def test_quality_benchmark_partial_extraction():
    llm = FakeLLM(
        responses={
            "extraction": '{"name":"Mario Rossi","age":41,"city":"Roma"}'
        }
    )

    report = benchmark_quality(llm, attempts=1)

    assert report["tasks"]["extraction"]["mean"] == 0.6667


def test_quality_benchmark_invalid_json_is_zero():
    llm = FakeLLM(responses={"extraction": "non è JSON"})

    report = benchmark_quality(llm, attempts=1)

    assert report["tasks"]["extraction"]["mean"] == 0.0


def test_quality_benchmark_errors_are_reported():
    report = benchmark_quality(
        FakeLLM(error=RuntimeError("offline")),
        attempts=2,
    )

    assert report["overall"] == 0.0
    assert all(
        len(item["errors"]) == 2 * item["cases"]
        for item in report["tasks"].values()
    )


def test_quality_benchmark_rejects_bad_attempts():
    try:
        benchmark_quality(FakeLLM(), attempts=0)
    except QualityBenchError:
        pass
    else:
        raise AssertionError("attempts=0 should fail")
