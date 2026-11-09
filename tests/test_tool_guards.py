"""Test di timeout e repeat guard del registry."""

from __future__ import annotations

import time

import pytest

from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry, ToolTimeoutError


def make_tool(handler, timeout=None):
    return ToolDefinition(
        name="probe.echo",
        description="probe",
        category="probe",
        handler=handler,
        timeout=timeout,
    )


def test_repeated_tool_call_is_blocked():
    registry = ToolRegistry()
    calls = []

    def handler(value):
        calls.append(value)
        return value

    registry.register(make_tool(handler))
    registry.begin_turn()

    assert registry.execute("probe.echo", value="x") == "x"
    assert registry.execute("probe.echo", value="x") == "x"

    with pytest.raises(RuntimeError, match="repeated"):
        registry.execute("probe.echo", value="x")

    assert len(calls) == 2


def test_repeat_guard_resets_per_turn():
    registry = ToolRegistry()
    registry.register(make_tool(lambda value: value))
    registry.begin_turn()

    registry.execute("probe.echo", value="x")
    registry.execute("probe.echo", value="x")
    registry.begin_turn()

    assert registry.execute("probe.echo", value="x") == "x"


def test_tool_timeout_raises():
    registry = ToolRegistry()

    def slow(value):
        time.sleep(0.2)
        return value

    registry.register(make_tool(slow, timeout=0.01))

    started = time.perf_counter()

    with pytest.raises(ToolTimeoutError):
        registry.execute("probe.echo", value="x")

    assert time.perf_counter() - started < 0.15
