"""Test del benchmark coding eseguibile."""

from __future__ import annotations

from core.coding_bench import benchmark_coding


class CodingLLM:
    provider = "fake"
    model = "coding-model"

    def chat(self, messages):
        prompt = messages[-1]["content"]

        if "add(a, b)" in prompt:
            return "def add(a, b):\n    return a + b"

        return "def is_even(n):\n    return n % 2 == 0"


def test_coding_benchmark_executes_unit_tests():
    report = benchmark_coding(CodingLLM(), attempts=1)

    assert report["tasks"]["coding_exec"]["cases"] == 2
    assert report["overall"] == 1.0


def test_coding_benchmark_reports_failure():
    class Broken(CodingLLM):
        def chat(self, messages):
            return "def add(a, b):\n    return a - b"

    report = benchmark_coding(Broken(), attempts=1)

    assert report["overall"] < 1.0
    assert report["tasks"]["coding_exec"]["errors"]
