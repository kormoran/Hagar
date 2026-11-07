"""Test della contabilità token."""

from __future__ import annotations

from core.usage import TokenUsage
from core.usage import UsageLedger
from core.usage import usage_from_anthropic
from core.usage import usage_from_gemini
from core.usage import usage_from_ollama
from core.usage import usage_from_openai


def test_openai_usage_includes_cached_and_reasoning():
    usage = usage_from_openai(
        {
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
                "prompt_tokens_details": {
                    "cached_tokens": 40,
                },
                "completion_tokens_details": {
                    "reasoning_tokens": 10,
                },
            }
        }
    )

    assert usage.input_tokens == 120
    assert usage.output_tokens == 30
    assert usage.cached_input_tokens == 40
    assert usage.reasoning_tokens == 10
    assert usage.total_tokens == 150
    assert usage.source == "provider"


def test_anthropic_usage_includes_cache():
    usage = usage_from_anthropic(
        {
            "usage": {
                "input_tokens": 80,
                "output_tokens": 20,
                "cache_read_input_tokens": 50,
                "cache_creation_input_tokens": 10,
            }
        }
    )

    assert usage.input_tokens == 80
    assert usage.output_tokens == 20
    assert usage.cached_input_tokens == 60
    assert usage.total_tokens == 100


def test_gemini_usage_includes_thought_tokens():
    usage = usage_from_gemini(
        {
            "usageMetadata": {
                "promptTokenCount": 70,
                "candidatesTokenCount": 15,
                "cachedContentTokenCount": 5,
                "thoughtsTokenCount": 4,
            }
        }
    )

    assert usage.input_tokens == 70
    assert usage.output_tokens == 15
    assert usage.cached_input_tokens == 5
    assert usage.reasoning_tokens == 4
    assert usage.total_tokens == 85


def test_ollama_usage():
    usage = usage_from_ollama(
        {
            "prompt_eval_count": 22,
            "eval_count": 8,
        }
    )

    assert usage.input_tokens == 22
    assert usage.output_tokens == 8
    assert usage.total_tokens == 30


def test_missing_usage_is_marked():
    usage = usage_from_openai({})

    assert usage.total_tokens == 0
    assert usage.source == "missing"


def test_ledger_totals_and_events():
    events = []
    ledger = UsageLedger(events.append)

    ledger.record(
        TokenUsage(
            input_tokens=10,
            output_tokens=4,
            cached_input_tokens=2,
        ),
        provider="openai",
        model="gpt-4o",
    )
    ledger.record(
        TokenUsage(
            input_tokens=5,
            output_tokens=3,
            reasoning_tokens=1,
        ),
        provider="openai",
        model="gpt-4o",
    )

    snapshot = ledger.snapshot()

    assert snapshot == {
        "input_tokens": 15,
        "output_tokens": 7,
        "cached_input_tokens": 2,
        "reasoning_tokens": 1,
        "total_tokens": 22,
        "calls": 2,
    }
    assert events[-1].type == "usage.updated"
    assert events[-1].data["total_tokens"] == 22
    assert events[-1].data["provider"] == "openai"


def test_ledger_reset():
    ledger = UsageLedger()
    ledger.record(TokenUsage(input_tokens=1, output_tokens=1))

    ledger.reset()

    assert ledger.snapshot()["total_tokens"] == 0
    assert ledger.snapshot()["calls"] == 0
