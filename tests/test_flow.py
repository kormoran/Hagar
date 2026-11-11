"""Test del DSL Hagar Flow."""

from __future__ import annotations

import pytest

from core.boxes import BoxRunner
from core.flow import FlowRunner, validate
from core.flow.errors import FlowValidationError
from core.models import BoxesConfig, FlowConfig
from core.tool_registry import ToolRegistry
from local_tools.flow_primitives import FlowPrimitiveProvider


class _FakeLLM:

    model = "fake"

    def chat(self, messages):
        return "summary"


def test_box_primitive(sandbox, workspace):
    (workspace / "input.txt").write_text(
        "testo",
        encoding="utf-8",
    )
    registry = ToolRegistry()
    box_runner = BoxRunner(
        _FakeLLM(),
        sandbox,
        BoxesConfig(enabled=True),
    )
    provider = FlowPrimitiveProvider(sandbox, box_runner)
    provider.register_tools(registry)
    runner = FlowRunner(
        registry,
        FlowConfig(enabled=True),
        provider.primitives,
    )

    result = runner.run(
        "box.summarize('input.txt', 'summary.txt')\n"
        "return fs.read('summary.txt')\n"
    )

    assert result.ok is True
    assert result.result == "summary"


def make_runner(sandbox, **overrides):
    registry = ToolRegistry()
    provider = FlowPrimitiveProvider(sandbox)
    provider.register_tools(registry)
    config = FlowConfig(
        enabled=True,
        **overrides,
    )
    return FlowRunner(
        registry,
        config,
        provider.primitives,
    )


def test_return_and_loop(sandbox):
    runner = make_runner(sandbox)

    result = runner.run(
        "values = []\n"
        "for item in [1, 2, 3]:\n"
        "    values.append(item * 2)\n"
        "return values\n"
    )

    assert result.ok is True
    assert result.result == [2, 4, 6]


def test_filesystem_primitives(sandbox, workspace):
    (workspace / "input.txt").write_text(
        "hello",
        encoding="utf-8",
    )
    runner = make_runner(sandbox)

    result = runner.run(
        "text = fs.read('input.txt')\n"
        "fs.write('output.txt', text.upper())\n"
        "return fs.list('.')\n"
    )

    assert result.ok is True
    assert (workspace / "output.txt").read_text(
        encoding="utf-8"
    ) == "HELLO"
    assert any(
        "output.txt" in item
        for item in result.result
    )


def test_list_comprehension(sandbox):
    runner = make_runner(sandbox)

    result = runner.run(
        "values = [1, 2, 3, 4]\n"
        "doubled = [item * 2 for item in values if item > 2]\n"
        "return doubled\n"
    )

    assert result.ok is True
    assert result.result == [6, 8]


def test_list_comprehension_scope_does_not_leak(sandbox):
    runner = make_runner(sandbox)

    result = runner.run(
        "item = 99\n"
        "values = [item for item in [1, 2]]\n"
        "return [item, values]\n"
    )

    assert result.ok is True
    assert result.result == [99, [1, 2]]


def test_list_comprehension_rejects_two_for():
    with pytest.raises(FlowValidationError):
        validate(
            "[x for x in [1] for y in [2]]",
            {"fs.read"},
        )


def test_dict_comprehension_is_rejected():
    with pytest.raises(FlowValidationError):
        validate(
            "{x: x for x in [1]}",
            {"fs.read"},
        )


def test_imports_and_functions_are_rejected():
    with pytest.raises(FlowValidationError):
        validate("import os", {"fs.read"})

    with pytest.raises(FlowValidationError):
        validate("def f():\n    return 1", {"fs.read"})


def test_dunder_is_rejected():
    with pytest.raises(FlowValidationError):
        validate("x = (1).__class__", {"fs.read"})


def test_step_budget(sandbox):
    runner = make_runner(sandbox, max_steps=3)

    result = runner.run(
        "x = 0\n"
        "while x < 10:\n"
        "    x = x + 1\n"
        "return x\n"
    )

    assert result.ok is False
    assert "budget" in result.error["message"].lower()


def test_unknown_primitive(sandbox):
    runner = make_runner(sandbox)

    result = runner.run("return fs.nope()")

    assert result.ok is False
    assert result.error["kind"] == "validation"


def test_path_outside_sandbox(sandbox):
    runner = make_runner(sandbox)

    result = runner.run("return fs.read('/etc/passwd')")

    assert result.ok is False
    assert result.error["kind"] == "runtime"
