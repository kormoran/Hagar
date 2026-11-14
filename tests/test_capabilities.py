"""Test delle capability verificate."""

from __future__ import annotations

from types import SimpleNamespace

from core.broker import Broker
from core.capabilities import enabled_capabilities, verified_capabilities
from core.model_registry import ModelEntry, ModelRegistry
from core.task_profile import TaskProfile, TaskProfileStore


def report() -> dict:
    return {
        "benchmarks": {
            "chat": {"successes": 0},
            "structured": {"valid_json": 1},
            "tool_call": {"successes": 1},
        },
        "quality": {
            "tasks": {
                "coding": {"mean": 1.0},
                "reasoning": {"mean": 1.0},
            }
        },
        "vision": {
            "overall": 0.8,
            "tasks": {
                "vision": {
                    "case_results": [
                        {"name": "vision_ocr", "mean": 1.0}
                    ]
                }
            },
        },
        "capabilities": {"native_tools": True},
    }


def test_verified_capabilities_from_report():
    values = verified_capabilities(report())

    assert values["chat"] is False
    assert values["coding"] is True
    assert values["structured_json"] is True
    assert values["tool_calling"] is True
    assert values["native_tools"] is True
    assert values["vision"] is True
    assert values["ocr"] is True
    assert values["reasoning"] is True

    enabled = enabled_capabilities(report())
    assert "chat" not in enabled
    assert "coding" in enabled


def test_verified_capabilities_override_declared():
    entry = ModelEntry(
        id="lmstudio/coder",
        provider="lmstudio",
        model="coder",
        context_window=32768,
        capabilities=frozenset({"chat", "tool_calling"}),
        card={
            "capabilities_verified": {
                "chat": False,
                "coding": True,
                "tool_calling": True,
            }
        },
    )

    assert entry.has_capability("chat") is True
    assert entry.has_effective_capability("chat") is False
    assert entry.effective_capabilities == frozenset({
        "coding",
        "tool_calling",
    })


def test_broker_uses_verified_capabilities():
    coder = ModelEntry(
        id="lmstudio/coder",
        provider="lmstudio",
        model="coder",
        context_window=32768,
        capabilities=frozenset({"chat", "coding", "tool_calling"}),
        card={
            "capabilities_verified": {
                "chat": False,
                "coding": True,
                "tool_calling": True,
            },
            "quality": {
                "tasks": {
                    "coding": {"mean": 1.0},
                }
            },
        },
    )
    registry = ModelRegistry([coder])
    profiles = TaskProfileStore([
        TaskProfile(
            name="coding",
            required_capabilities=frozenset({
                "coding",
                "tool_calling",
            }),
        ),
        TaskProfile(
            name="chat",
            required_capabilities=frozenset({"chat"}),
        ),
    ])
    broker = Broker(registry, profiles)

    assert broker.select("coding").entry.id == "lmstudio/coder"

    try:
        broker.select("chat")
    except Exception as exc:
        assert "no eligible" in str(exc)
    else:
        raise AssertionError("chat should be excluded")


def test_not_applicable_vision_is_not_a_capability():
    value = verified_capabilities({
        "vision": {
            "not_applicable": True,
            "overall": None,
        },
    })

    assert value["vision"] is False


def test_verified_native_tools_from_report():
    value = verified_capabilities({
        "capabilities": {"native_tools": True},
    })

    assert value["native_tools"] is True


def test_legacy_card_is_backfilled_from_report():
    entry = ModelEntry(
        id="lmstudio/legacy",
        provider="lmstudio",
        model="legacy",
        context_window=32768,
        capabilities=frozenset({"chat"}),
        card=report(),
    )

    assert entry.effective_capabilities == frozenset({
        "coding",
        "structured_json",
        "tool_calling",
        "native_tools",
        "vision",
        "ocr",
        "reasoning",
    })
