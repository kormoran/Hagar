"""Test del ToolRegistry."""

from __future__ import annotations

import pytest

from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


def make_tool(
    name: str = "demo.tool",
    category: str = "demo",
    handler=None,
    **overrides,
) -> ToolDefinition:

    return ToolDefinition(
        name=name,
        description=f"Tool {name}",
        category=category,
        handler=handler or (lambda **kwargs: "ok"),
        **overrides,
    )


def test_register_and_get():
    registry = ToolRegistry()
    tool = make_tool()

    registry.register(tool)

    assert registry.exists("demo.tool") is True
    assert registry.get("demo.tool") is tool


def test_duplicate_registration_raises():
    registry = ToolRegistry()
    registry.register(make_tool())

    with pytest.raises(RuntimeError, match="already registered"):
        registry.register(make_tool())


def test_unknown_tool_raises():
    registry = ToolRegistry()

    assert registry.exists("missing") is False

    with pytest.raises(RuntimeError, match="unknown tool"):
        registry.get("missing")


def test_tool_names_are_sorted():
    registry = ToolRegistry()
    registry.register(make_tool("b.tool"))
    registry.register(make_tool("a.tool"))

    assert registry.tool_names() == ["a.tool", "b.tool"]


def test_compact_descriptions_are_applied():
    registry = ToolRegistry(compact_descriptions=True)
    tool = make_tool("filesystem.read_file")
    tool.description = "Read a UTF-8 file from the sandbox."
    tool.parameters = [
        ToolParameter(
            name="path",
            param_type="string",
            description="Path of the file to read.",
        )
    ]

    registry.register(tool)

    assert tool.short_description == "Read a UTF-8 file."
    assert tool.parameters[0].short_description == "File path."


def test_tool_timeout_override_is_applied():
    registry = ToolRegistry(
        timeout_overrides={"ocr.pdf": 900},
    )
    tool = make_tool("ocr.pdf")
    registry.register(tool)

    assert tool.timeout == 900


def test_unregister():
    registry = ToolRegistry()
    registry.register(make_tool())

    registry.unregister("demo.tool")

    assert registry.exists("demo.tool") is False

    # Rimuovere un tool inesistente non è un errore.
    registry.unregister("demo.tool")


def test_execute_passes_arguments():
    received = {}

    def handler(**kwargs):
        received.update(kwargs)
        return "risultato"

    registry = ToolRegistry()
    registry.register(make_tool(handler=handler))

    assert registry.execute(
        "demo.tool",
        path="a.txt",
        count=2,
    ) == "risultato"

    assert received == {"path": "a.txt", "count": 2}


def test_execute_propagates_handler_errors():
    def handler(**kwargs):
        raise ValueError("boom")

    registry = ToolRegistry()
    registry.register(make_tool(handler=handler))

    with pytest.raises(ValueError, match="boom"):
        registry.execute("demo.tool")


def test_disable_and_enable():
    registry = ToolRegistry()
    registry.register(make_tool())

    registry.disable("demo.tool")

    assert registry.is_enabled("demo.tool") is False

    with pytest.raises(RuntimeError, match="disabled"):
        registry.execute("demo.tool")

    registry.enable("demo.tool")

    assert registry.is_enabled("demo.tool") is True
    assert registry.execute("demo.tool") == "ok"


def test_list_definitions_excludes_disabled():
    registry = ToolRegistry()
    registry.register(make_tool("a.tool"))
    registry.register(make_tool("b.tool"))
    registry.disable("b.tool")

    definitions = registry.list_definitions()

    assert [tool.name for tool in definitions] == ["a.tool"]


def test_list_tools_metadata():
    registry = ToolRegistry()
    registry.register(
        make_tool(
            origin="mcp.github",
            requires_confirmation=True,
        )
    )

    tools = registry.list_tools()

    assert tools == [
        {
            "name": "demo.tool",
            "description": "Tool demo.tool",
            "category": "demo",
            "requires_confirmation": True,
        }
    ]


def test_tools_by_category():
    registry = ToolRegistry()
    registry.register(make_tool("a.tool", category="filesystem"))
    registry.register(make_tool("b.tool", category="filesystem"))
    registry.register(make_tool("c.tool", category="mcp"))
    registry.disable("b.tool")

    definitions = registry.tools_by_category("filesystem")

    assert [tool.name for tool in definitions] == ["a.tool"]
