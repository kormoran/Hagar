"""Test del repair loop di Hagar Flow."""

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


def test_repairs_validation_error(sandbox):
    llm = FakeLLM(["return 1 + 1"])
    provider = make_provider(sandbox, llm)

    payload = json.loads(
        provider.run_code("import os\nreturn 0")
    )

    assert payload["ok"] is True
    assert payload["result"] == 2
    assert payload["repair_attempts"] == 1
    assert llm.calls == 1


def test_does_not_repair_runtime_error(sandbox):
    llm = FakeLLM(["return 1 + 1"])
    provider = make_provider(sandbox, llm)

    payload = json.loads(
        provider.run_code("return fs.read('/missing')")
    )

    assert payload["ok"] is False
    assert payload["error"]["kind"] == "runtime"
    assert payload["repair_attempts"] == 0
    assert llm.calls == 0


def test_repair_attempts_are_bounded(sandbox):
    llm = FakeLLM([
        "import os\nreturn 0",
        "import os\nreturn 0",
    ])
    provider = make_provider(sandbox, llm, repair_attempts=2)

    payload = json.loads(
        provider.run_code("import os\nreturn 0")
    )

    assert payload["ok"] is False
    assert payload["error"]["kind"] == "validation"
    assert payload["repair_attempts"] == 2
    assert llm.calls == 2


def test_zero_attempts_does_not_call_llm(sandbox):
    llm = FakeLLM(["return 1"])
    provider = make_provider(sandbox, llm, repair_attempts=0)

    payload = json.loads(
        provider.run_code("import os\nreturn 0")
    )

    assert payload["ok"] is False
    assert payload["repair_attempts"] == 0
    assert llm.calls == 0
