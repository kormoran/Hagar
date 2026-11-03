"""Test di ToolDefinition e ToolParameter."""

from __future__ import annotations

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)


def make_definition(**overrides) -> ToolDefinition:

    data = {
        "name": "demo.tool",
        "description": "descrizione",
        "category": "demo",
        "handler": lambda: "ok",
    }

    data.update(overrides)

    return ToolDefinition(**data)


def test_parameter_defaults():
    parameter = ToolParameter(
        name="path",
        param_type="string",
        description="Percorso",
    )

    assert parameter.required is True
    assert parameter.default is None


def test_parameter_optional_with_default():
    parameter = ToolParameter(
        name="content",
        param_type="string",
        description="Contenuto",
        required=False,
        default="",
    )

    assert parameter.required is False
    assert parameter.default == ""


def test_definition_defaults():
    tool = make_definition()

    assert tool.parameters == []
    assert tool.capabilities is Capability.NONE
    assert tool.origin == "local"
    assert tool.enabled is True
    assert tool.requires_confirmation is False


def test_definition_accepts_origin():
    tool = make_definition(
        origin="mcp.github",
        category="mcp",
    )

    assert tool.origin == "mcp.github"
    assert tool.category == "mcp"


def test_parameters_are_not_shared_between_instances():
    first = make_definition()
    second = make_definition()

    first.parameters.append(
        ToolParameter(
            name="x",
            param_type="string",
            description="x",
        )
    )

    assert second.parameters == []
