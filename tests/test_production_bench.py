"""Test del benchmark con prompt production-like."""

from __future__ import annotations

from core.production_bench import benchmark_production
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry


class CaptureLLM:
    provider = "fake"
    model = "production"

    def __init__(self):
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        return "ok"


def test_production_benchmark_includes_tools_and_memory():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="filesystem.read_file",
            description="Read a file.",
            category="filesystem",
            handler=lambda **kwargs: "ok",
        )
    )
    llm = CaptureLLM()

    report = benchmark_production(
        llm,
        registry=registry,
        memory_text="Il progetto si chiama Atreides.",
        attempts=1,
    )

    system = llm.messages[0]["content"]
    assert "filesystem.read_file" in system
    assert "Atreides" in system
    assert report["tools"] == 1
    assert report["p50_ms"] >= 0
