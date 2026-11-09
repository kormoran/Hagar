"""Test del tool text.transform."""

from __future__ import annotations

import json

import pytest

from core.tool_registry import ToolRegistry
from local_tools.text_transform_tool import TextTransformToolProvider


@pytest.fixture
def registry(sandbox):
    registry = ToolRegistry()
    TextTransformToolProvider(sandbox).register_tools(registry)
    return registry


def run(registry, **kwargs):
    return json.loads(
        registry.execute("text.transform", **kwargs)
    )


def test_grep_and_line_numbers(registry):
    result = run(
        registry,
        operation="grep",
        text="errore uno\nok\nerrore due\n",
        pattern="errore",
        line_numbers=True,
    )

    assert result["text"] == "1:errore uno\n3:errore due\n"
    assert result["matches"] == 2


def test_sort_numeric_and_unique(registry):
    result = run(
        registry,
        operation="sort",
        text="10\n2\n10\n",
        numeric=True,
        unique=True,
    )

    assert result["text"] == "2\n10\n"


def test_cut(registry):
    result = run(
        registry,
        operation="cut",
        text="a,b,c\n1,2,3\n",
        delimiter=",",
        fields="2",
    )

    assert result["text"] == "b\n2\n"


def test_sed_replace(registry):
    result = run(
        registry,
        operation="sed_replace",
        text="uno due uno",
        pattern="uno",
        replacement="tre",
        global_replace=True,
    )

    assert result["text"] == "tre due tre"


def test_transform_requires_one_source(registry):
    with pytest.raises(Exception):
        registry.execute(
            "text.transform",
            operation="wc",
        )
