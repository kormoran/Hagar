"""Test della policy adattiva dei timeout."""

from __future__ import annotations

from core.model_registry import ModelEntry
from core.timeouts import TimeoutPolicy


def entry(p95: float | None, p50: float | None = None) -> ModelEntry:
    benchmarks = {}

    if p95 is not None or p50 is not None:
        benchmarks = {
            "chat": {
                "duration_ms": {
                    "p50": p50,
                    "p95": p95,
                }
            }
        }

    return ModelEntry(
        id="lmstudio/test",
        provider="lmstudio",
        model="test",
        context_window=32768,
        capabilities=frozenset({"chat"}),
        card={"benchmarks": benchmarks},
    )


def test_request_timeout_uses_p95_and_clamps():
    policy = TimeoutPolicy(
        floor_seconds=30,
        ceiling_seconds=900,
        safety_factor=1.5,
    )

    assert policy.request_timeout(
        entry(10000),
        [{"role": "user", "content": "x"}],
        512,
        fallback=600,
    ) == 30.0

    value = policy.request_timeout(
        entry(200000),
        [{"role": "user", "content": "x" * 10000}],
        1024,
        fallback=600,
    )

    assert value is not None
    assert value > 200
    assert value <= 900


def test_request_timeout_falls_back_without_card():
    policy = TimeoutPolicy()
    value = policy.request_timeout(
        None,
        [],
        512,
        fallback=120,
    )

    assert value == 120.0


def test_turn_timeout_has_ceiling():
    policy = TimeoutPolicy(
        floor_seconds=30,
        ceiling_seconds=900,
        turn_ceiling_seconds=1800,
    )

    value = policy.turn_timeout(entry(200000), max_calls=10)

    assert value is not None
    assert 30 <= value <= 1800


def test_disabled_policy_keeps_fallback():
    policy = TimeoutPolicy(enabled=False)

    assert policy.request_timeout(
        entry(1000),
        [],
        512,
        fallback=42,
    ) == 42
    assert policy.turn_timeout(entry(1000)) is None
