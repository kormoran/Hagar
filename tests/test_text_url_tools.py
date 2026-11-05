"""Test dei tool locali text.diff e url.parse."""

from __future__ import annotations

import json

from core.permissions import Capability
from core.tool_registry import ToolRegistry
from local_tools.text_diff import TextDiff
from local_tools.text_diff_tool import TextDiffToolProvider
from local_tools.url_parse import UrlParser
from local_tools.url_parse_tool import UrlParseToolProvider


def test_text_diff_reports_changes():
    result = TextDiff().compare(
        "alpha\nbeta\n",
        "alpha\ngamma\n",
    )

    assert result["success"] is True
    assert result["identical"] is False
    assert "-beta" in result["diff"]
    assert "+gamma" in result["diff"]
    assert result["added_lines"] == 1
    assert result["removed_lines"] == 1
    assert result["truncated"] is False


def test_text_diff_identical_and_limits():
    text = "same\n"

    result = TextDiff().compare(text, text)

    assert result["identical"] is True
    assert result["diff"] == ""

    too_long = "x" * (TextDiff.MAX_INPUT_CHARS + 1)

    result = TextDiff().compare(too_long, "y")

    assert result["success"] is False
    assert "MAX_INPUT_CHARS" in result["error"]


def test_text_diff_context_is_bounded():
    result = TextDiff().compare(
        "a\nb\nc\n",
        "a\nB\nc\n",
        context=99,
    )

    assert result["success"] is True
    assert " b" in result["diff"] or "-b" in result["diff"]


def test_url_parse_absolute_and_redacts_credentials():
    parser = UrlParser()

    result = parser.parse(
        "https://user:secret@example.com:8443/"
        "a/b?q=1&flag&q=2#frag"
    )

    assert result["success"] is True
    assert result["scheme"] == "https"
    assert result["host"] == "example.com"
    assert result["port"] == 8443
    assert result["path"] == "/a/b"
    assert result["fragment"] == "frag"
    assert result["has_credentials"] is True
    assert "secret" not in result["url"]
    assert result["url"].startswith("https://***@example.com")
    assert result["query_params"] == [
        {"name": "q", "value": "1"},
        {"name": "flag", "value": ""},
        {"name": "q", "value": "2"},
    ]


def test_url_parse_relative_and_errors():
    parser = UrlParser()

    relative = parser.parse("../a?x=1")

    assert relative["success"] is True
    assert relative["is_absolute"] is False
    assert relative["path"] == "../a"
    assert relative["query_params"] == [
        {"name": "x", "value": "1"}
    ]

    invalid = parser.parse("https://example.com:bad/")

    assert invalid["success"] is False

    control = parser.parse("https://example.com/\n")

    assert control["success"] is False


def test_text_and_url_tools_are_registered():
    registry = ToolRegistry()

    TextDiffToolProvider(TextDiff()).register_tools(registry)
    UrlParseToolProvider(UrlParser()).register_tools(registry)

    assert set(registry.tool_names()) == {
        "text.diff",
        "url.parse",
    }

    assert registry.get("text.diff").capabilities == (
        Capability.COMPUTE
    )
    assert registry.get("url.parse").capabilities == (
        Capability.COMPUTE
    )

    diff = json.loads(
        registry.execute(
            "text.diff",
            left="a",
            right="b",
        )
    )

    assert diff["identical"] is False

    parsed = json.loads(
        registry.execute(
            "url.parse",
            url="https://example.com/path",
        )
    )

    assert parsed["host"] == "example.com"
