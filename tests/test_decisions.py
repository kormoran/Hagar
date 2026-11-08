"""Test dei provider e del tool decisionale."""

from __future__ import annotations

import json

from core.decisions import DecisionRegistry
from core.decisions import DecisionRequest
from core.decisions import LLMDecisionProvider
from core.decisions import LinearDecisionProvider
from core.decisions import build_decision_registry
from local_tools.decision_tool import DecisionToolProvider
from core.tool_registry import ToolRegistry


class FakeLLM:

    model = "fake-model"

    def __init__(self, payload):
        self.payload = payload

    def chat(self, messages):
        return json.dumps(self.payload)


def make_request():
    return DecisionRequest(
        state="questo messaggio è spam",
        question="Come va classificato?",
        choices=("spam", "ham"),
    )


def test_llm_decision_provider_normalizes_probabilities():
    provider = LLMDecisionProvider(
        FakeLLM({
            "choice": "spam",
            "probabilities": {
                "spam": 3,
                "ham": 1,
            },
        })
    )

    result = provider.decide(make_request())

    assert result.choice == "spam"
    assert result.probabilities["spam"] == 0.75
    assert result.probabilities["ham"] == 0.25
    assert result.provider == "llm"


def test_linear_decision_provider(tmp_path):
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps({
            "labels": ["spam", "ham"],
            "weights": {
                "spam": {"spam": 2.0},
                "ham": {"spam": -2.0},
            },
            "bias": {},
        }),
        encoding="utf-8",
    )

    provider = LinearDecisionProvider(model)
    result = provider.decide(make_request())

    assert result.choice == "spam"
    assert result.probabilities["spam"] > 0.9
    assert result.model == str(model)


def test_tool_registers_and_returns_json():
    registry = DecisionRegistry(
        {"llm": LLMDecisionProvider(FakeLLM({
            "choice": "ham",
            "probabilities": {"spam": 0.1, "ham": 0.9},
        }))}
    )
    tools = ToolRegistry()
    DecisionToolProvider(registry).register_tools(tools)

    output = tools.execute(
        "decision.choose",
        state="messaggio",
        question="spam?",
        choices=["spam", "ham"],
    )

    payload = json.loads(output)
    assert payload["choice"] == "ham"
    assert payload["confidence"] == 0.9


class EmptyConfig:

    decisions = type(
        "Decisions",
        (),
        {
            "enabled": True,
            "default": "llm",
            "providers": [],
        },
    )()


def test_build_registry_has_llm_default():
    registry = build_decision_registry(
        EmptyConfig(),
        FakeLLM({
            "choice": "ham",
            "probabilities": {"spam": 0.2, "ham": 0.8},
        }),
    )

    assert registry.names() == ["llm"]
    assert registry.choose(make_request()).choice == "ham"
