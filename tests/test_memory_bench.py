"""Test del benchmark di memoria sintetica."""

from __future__ import annotations

from core.memory_bench import benchmark_memory, cases


class MemoryLLM:
    provider = "fake"
    model = "memory-model"

    def __init__(self):
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        text = " ".join(
            str(message.get("content", "")).casefold()
            for message in messages
        )

        if "atreides" in text:
            return "Atreides"

        if "8443" in text:
            return "8443"

        if "luca" in text:
            return "Luca"

        if "capital of france" in text:
            return "Parigi"

        if "zenith-42" in text:
            return "ZENITH-42"

        if "vega" in text:
            return "Vega"

        return ""


def test_memory_cases_are_synthetic_and_bounded():
    values = cases()

    assert len(values) >= 5
    assert all(case.messages for case in values)
    assert all(case.expected for case in values)


def test_memory_benchmark_scores_recall():
    report = benchmark_memory(MemoryLLM(), attempts=1)

    assert report["tasks"]["memory"]["cases"] == len(cases())
    assert report["overall"] > 0.5


def test_memory_benchmark_records_errors():
    class Broken:
        provider = "fake"
        model = "broken"

        def chat(self, messages):
            raise RuntimeError("boom")

    report = benchmark_memory(Broken(), attempts=1)

    assert report["overall"] == 0.0
    assert report["tasks"]["memory"]["errors"]
