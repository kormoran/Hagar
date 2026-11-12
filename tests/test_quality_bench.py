"""Test del benchmark di qualità."""

from __future__ import annotations

from core.quality_bench import QualityBenchError, benchmark_quality


class FakeLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

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

        if "3 + 4" in prompt:
            return self.responses.get("reasoning", "7")

        if "print(len" in prompt:
            return self.responses.get("coding", "3")

        if "Riassumi" in prompt:
            return self.responses.get(
                "summary",
                "Hagar 0.8 introduce il broker e i modelli locali. "
                "La memoria arriva nella 0.9, il runtime locale dopo la 1.0.",
            )

        if "Traduci in inglese" in prompt:
            return self.responses.get(
                "translation_it_en",
                "Hagar runs tools in the sandbox. The report is in "
                "/home/ai/workspace/report.txt and the command is "
                "`hagar --config hagar.yaml`.",
            )

        if "Traduci in italiano" in prompt:
            return self.responses.get(
                "translation_en_it",
                "Il broker sceglie un modello, ma non concede mai "
                "capability.",
            )

        return "OK"


def test_quality_benchmark_perfect_answers():
    report = benchmark_quality(FakeLLM(), attempts=2)

    assert report["suite_version"] == 2
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
