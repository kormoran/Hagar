"""Test del repair esplicito di Hagar Flow."""

from __future__ import annotations

import json

from core.flow import FlowRunner
from core.models import FlowConfig
from core.tool_registry import ToolRegistry
from local_tools.flow_primitives import FlowPrimitiveProvider
from local_tools.flow_tool import FlowToolProvider


class FakeLLM:

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if not self.responses:
            return "return 0"
        return self.responses.pop(0)


def make_provider(sandbox, llm, repair_attempts=2):
    registry = ToolRegistry(repeat_limit=0)
    primitives = FlowPrimitiveProvider(sandbox)
    primitives.register_tools(registry)
    runner = FlowRunner(
        registry,
        FlowConfig(
            enabled=True,
            repair_attempts=repair_attempts,
        ),
        primitives.primitives,
    )
    return FlowToolProvider(runner, llm=llm)


def test_repair_returns_code_without_running_it(sandbox, workspace):
    llm = FakeLLM(["return 1 + 1"])
    provider = make_provider(sandbox, llm)

    payload = json.loads(
        provider.repair_code("import os\nreturn 0")
    )

    assert payload["ok"] is True
    assert payload["repaired"] is True
    assert payload["attempts"] == 1
    assert payload["code"] == "return 1 + 1"
    assert llm.calls == 1
    # repair non deve eseguire il codice né produrre file.
    assert not (workspace / "repaired.py").exists()


def test_flow_run_does_not_repair(sandbox):
    llm = FakeLLM(["return 1 + 1"])
    provider = make_provider(sandbox, llm)

    payload = json.loads(
        provider.run_code("import os\nreturn 0")
    )

    assert payload["ok"] is False
    assert payload["error"]["kind"] == "validation"
    assert payload["repair_attempts"] == 0
    assert llm.calls == 0


def test_repair_attempts_are_bounded(sandbox):
    llm = FakeLLM([
        "import os\nreturn 0",
        "import os\nreturn 0",
    ])
    provider = make_provider(sandbox, llm, repair_attempts=2)

    payload = json.loads(
        provider.repair_code("import os\nreturn 0")
    )

    assert payload["ok"] is False
    assert payload["repaired"] is False
    assert payload["attempts"] == 2
    assert llm.calls == 2


def test_zero_attempts_does_not_call_llm(sandbox):
    llm = FakeLLM(["return 1"])
    provider = make_provider(sandbox, llm, repair_attempts=0)

    payload = json.loads(
        provider.repair_code("import os\nreturn 0")
    )

    assert payload["ok"] is False
    assert payload["attempts"] == 0
    assert llm.calls == 0
