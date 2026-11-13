"""Test del broker LLM puro."""

from __future__ import annotations

import pytest

from core.broker import Broker, BrokerError
from core.model_registry import ModelEntry, ModelRegistry
from core.task_profile import TaskProfile, TaskProfileStore


def entry(
    model_id,
    *,
    quality=0.8,
    context=32768,
    locality="local",
    latency=2000,
    cost=0.0,
    capabilities=("chat", "tool_calling"),
    enabled=True,
    measured_quality=None,
):
    card = None

    if latency is not None:
        card = {
            "benchmarks": {
                "chat": {
                    "duration_ms": {"p50": latency}
                }
            }
        }

    if measured_quality is not None:
        card = card or {}
        card["quality"] = {
            "tasks": {
                "coding": {"mean": measured_quality},
            }
        }

    return ModelEntry(
        id=model_id,
        provider="lmstudio",
        model=model_id,
        context_window=context,
        capabilities=frozenset(capabilities),
        locality=locality,
        quality=quality,
        cost_per_1k_input=cost,
        cost_per_1k_output=cost,
        enabled=enabled,
        card=card,
    )


def coding_profile(**overrides):
    values = {
        "name": "coding",
        "required_capabilities": frozenset({
            "chat",
            "tool_calling",
        }),
        "min_context": 16000,
        "privacy": "local_only",
        "max_latency_ms": 30000,
        "quality_floor": 0.5,
        "prefer": "quality",
    }
    values.update(overrides)
    return TaskProfile(**values)


def make_broker(entries, profiles=None, **kwargs):
    registry = ModelRegistry(entries)
    store = TaskProfileStore(
        profiles or [coding_profile()]
    )
    return Broker(registry, store, **kwargs)


def test_loaded_only_excludes_models_not_in_runtime():
    broker = make_broker(
        [
            entry("loaded", quality=0.80),
            entry("not-loaded", quality=0.99),
        ],
        loaded_only=True,
    )
    broker.set_loaded_models("lmstudio", ["loaded"])

    selection = broker.select("coding")

    assert selection.entry.id == "loaded"


def test_refresh_sets_loaded_models():
    calls = []

    def refresh():
        calls.append(True)

    broker = make_broker(
        [entry("loaded")],
        loaded_only=True,
        refresh=refresh,
        refresh_interval=0,
    )
    broker.set_loaded_models("lmstudio", ["loaded"])

    assert broker.select("coding").entry.id == "loaded"
    assert calls


def test_loaded_only_unknown_state_is_not_excluded():
    broker = make_broker(
        [entry("unknown")],
        loaded_only=True,
    )

    assert broker.loaded_state(broker.registry.get("unknown")) is None
    assert broker.select("coding").entry.id == "unknown"


def test_select_prefers_quality():
    fast = entry("fast", quality=0.80, latency=1000)
    quality = entry("quality", quality=0.95, latency=12000)
    broker = make_broker([fast, quality])

    selection = broker.select("coding")

    assert selection.entry.id == "quality"
    assert selection.score > 0
    assert any("quality" in reason for reason in selection.reasons)


def test_local_only_excludes_remote():
    remote = entry(
        "remote",
        quality=0.99,
        locality="remote",
        latency=500,
    )
    local = entry("local", quality=0.70)
    broker = make_broker([remote, local])

    selection = broker.select("coding")

    assert selection.entry.id == "local"
    assert any(
        item["model_id"] == "remote"
        and any("local_only" in reason for reason in item["reasons"])
        for item in selection.excluded
    )


def test_context_and_latency_filters():
    small = entry("small", context=4000)
    slow = entry("slow", latency=60000)
    good = entry("good", context=32000, latency=1000)
    broker = make_broker([small, slow, good])

    selection = broker.select("coding")

    assert selection.entry.id == "good"
    excluded = {
        item["model_id"]: item["reasons"]
        for item in selection.excluded
    }
    assert any("context" in reason for reason in excluded["small"])
    assert any("latency" in reason for reason in excluded["slow"])


def test_cost_and_quality_filters():
    expensive = entry("expensive", quality=0.95, cost=2.0)
    cheap = entry("cheap", quality=0.80, cost=0.0)
    broker = make_broker([expensive, cheap])
    profile = coding_profile(
        max_cost_per_1k_input=0.5,
    )

    selection = broker.select(profile)

    assert selection.entry.id == "cheap"
    assert any(
        item["model_id"] == "expensive"
        and any("cost" in reason for reason in item["reasons"])
        for item in selection.excluded
    )


def test_quality_floor_excludes_unknown_and_low():
    unknown = entry("unknown", quality=None)
    low = entry("low", quality=0.4)
    good = entry("good", quality=0.9)
    broker = make_broker([unknown, low, good])

    selection = broker.select(
        coding_profile(quality_floor=0.5)
    )

    assert selection.entry.id == "good"
    assert {
        item["model_id"]
        for item in selection.excluded
    } == {"unknown", "low"}


def test_no_eligible_model_reports_exclusions():
    broker = make_broker([
        entry("small", context=1000),
    ])

    with pytest.raises(BrokerError) as exc:
        broker.select("coding")

    assert exc.value.excluded
    assert "no eligible" in str(exc.value)


def test_missing_card_is_penalized_but_eligible():
    measured = entry("measured", quality=0.8, latency=2000)
    unmeasured = entry(
        "unmeasured",
        quality=0.8,
        latency=None,
    )
    broker = make_broker([measured, unmeasured])

    selection = broker.select(
        coding_profile(max_latency_ms=None)
    )

    assert selection.entry.id == "measured"
    assert selection.entry.card is not None


def test_explain_lists_ranked_and_excluded():
    broker = make_broker([
        entry("best", quality=0.95),
        entry("ok", quality=0.75),
        entry("remote", quality=0.99, locality="remote"),
    ])

    report = broker.explain("coding")

    assert report["profile"] == "coding"
    assert report["selected"]["model_id"] == "best"
    assert len(report["ranked"]) == 2
    assert any(
        item["model_id"] == "remote"
        for item in report["excluded"]
    )


def test_disabled_model_and_unknown_profile():
    broker = make_broker([
        entry("good", enabled=True),
        entry("disabled", enabled=False),
    ])

    assert broker.select("coding").entry.id == "good"

    with pytest.raises(BrokerError):
        broker.select("missing")


def test_quality_floor_uses_measured_quality():
    declared_high = entry(
        "declared-high",
        quality=0.95,
        measured_quality=0.40,
    )
    measured_high = entry(
        "measured-high",
        quality=0.70,
        measured_quality=0.90,
    )
    broker = make_broker([declared_high, measured_high])

    selection = broker.select(
        coding_profile(quality_floor=0.50)
    )

    assert selection.entry.id == "measured-high"
    assert any(
        item["model_id"] == "declared-high"
        for item in selection.excluded
    )


def test_selection_serializes():
    broker = make_broker([entry("good")])

    payload = broker.select("coding").as_dict()

    assert payload["profile"] == "coding"
    assert payload["model_id"] == "good"
    assert payload["score"] <= 1.0
    assert payload["excluded"] == []
