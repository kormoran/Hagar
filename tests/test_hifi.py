"""Test della modalità Hi-Fi."""

from __future__ import annotations

import json

import pytest

from core.agent import Agent
from core.hifi import HiFiError, HiFiResolver
from core.tool_call import ToolCall


class FakeLLM:

    provider = "fake"
    model = "fake-hifi"
    supports_native_tools = False
    native_tools = False

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.last_usage = None

    def chat(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)

    def request_tool_call(self, messages, registry):
        self.calls.append(messages)
        return ToolCall(tool="", arguments={})


def interpretations(*items):
    return json.dumps({
        "interpretations": [
            {"text": text, "probability": probability}
            for text, probability in items
        ]
    })


def test_confident_interpretation_wins():
    llm = FakeLLM([
        interpretations(("riassumi il documento", 0.72), ("traduci il documento", 0.18), ("altro", 0.10)),
    ])
    resolver = HiFiResolver(llm, margin=0.20)

    result = resolver.resolve("Sistemami quel documento")

    assert result.needs_clarification is False
    assert result.top.text == "riassumi il documento"
    assert result.margin == pytest.approx(0.54)
    assert "riassumi il documento" in resolver.resolved_question(
        "Sistemami quel documento",
        result,
    )


def test_ambiguous_interpretations_ask_for_clarification():
    llm = FakeLLM([
        interpretations(("sposta il file", 0.42), ("copia il file", 0.40), ("altro", 0.18)),
        "Intendi spostare o copiare il file, oppure altro?",
    ])
    resolver = HiFiResolver(llm, margin=0.20)

    result = resolver.resolve("Sistema quel file")

    assert result.needs_clarification is True
    assert resolver.clarify("Sistema quel file", result) == (
        "Intendi spostare o copiare il file, oppure altro?"
    )


def test_invalid_interpretation_json_is_rejected():
    resolver = HiFiResolver(FakeLLM(["non è JSON"]))

    with pytest.raises(HiFiError):
        resolver.resolve("Domanda")


def test_probabilities_are_normalized():
    resolver = HiFiResolver(
        FakeLLM([
            interpretations(("A", 2), ("B", 1)),
        ])
    )

    # 2 and 1 are outside 0..1: the response is rejected, not silently
    # converted into percentages.
    with pytest.raises(HiFiError):
        resolver.resolve("Domanda")


def test_agent_uses_resolved_question_for_answer():
    llm = FakeLLM([
        interpretations(("crea un file", 0.80), ("leggi un file", 0.10), ("altro", 0.10)),
        "File creato.",
    ])
    resolver = HiFiResolver(llm, margin=0.20)
    agent = Agent(
        llm=llm,
        tool_registry=[],
        vault=None,
        hifi=resolver,
    )

    answer = agent.ask("Crea quel file")

    assert answer == "File creato."
    assert "Interpretazione scelta: crea un file" in (
        llm.calls[-1][-1]["content"]
    )
