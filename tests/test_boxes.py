"""Test delle boxed transform."""

from __future__ import annotations

import json

from core.boxes import BoxRunner
from core.models import BoxesConfig
from core.usage import TokenUsage
from local_tools.box_tool import BoxToolProvider
from core.tool_registry import ToolRegistry


class FakeLLM:

    model = "fake-model"

    def __init__(self):
        self.last_usage = TokenUsage(
            input_tokens=10,
            output_tokens=5,
        )
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        user = messages[-1]["content"]

        if "oggetto JSON" in user:
            return '{"title": "Documento", "value": 42}'
        if "Traduci" in user:
            return "translated"
        return "summary"


def test_summarize_writes_output(sandbox, workspace):
    (workspace / "input.txt").write_text(
        "testo da riassumere",
        encoding="utf-8",
    )
    runner = BoxRunner(
        FakeLLM(),
        sandbox,
        BoxesConfig(enabled=True),
    )

    result = runner.run(
        "summarize",
        "input.txt",
        "summary.txt",
    )

    assert result["box"] == "summarize"
    assert (workspace / "summary.txt").read_text(
        encoding="utf-8"
    ) == "summary"
    assert result["calls"] == 1


def test_translate_and_extract_json(sandbox, workspace):
    (workspace / "input.txt").write_text(
        "hello",
        encoding="utf-8",
    )
    runner = BoxRunner(
        FakeLLM(),
        sandbox,
        BoxesConfig(enabled=True),
    )

    runner.run(
        "translate",
        "input.txt",
        "translated.txt",
        {"target": "it"},
    )
    assert (workspace / "translated.txt").read_text(
        encoding="utf-8"
    ) == "translated"

    runner.run(
        "extract_json",
        "input.txt",
        "data.json",
    )
    payload = json.loads(
        (workspace / "data.json").read_text(encoding="utf-8")
    )
    assert payload["title"] == "Documento"


def test_box_tool_list(sandbox):
    runner = BoxRunner(
        FakeLLM(),
        sandbox,
        BoxesConfig(enabled=True),
    )
    registry = ToolRegistry()
    BoxToolProvider(runner).register_tools(registry)

    payload = json.loads(registry.execute("box.list"))

    assert {item["name"] for item in payload["boxes"]} == {
        "summarize",
        "translate",
        "extract_json",
    }
