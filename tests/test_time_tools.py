"""Test dei tool locali clock, calendar e think."""

from __future__ import annotations

import json
import re

from core.permissions import Capability
from core.tool_registry import ToolRegistry
from local_tools.calendar import Calendar
from local_tools.calendar_tool import CalendarToolProvider
from local_tools.clock import Clock
from local_tools.clock_tool import ClockToolProvider
from local_tools.think import Think
from local_tools.think_tool import ThinkToolProvider


def test_clock_returns_local_time_and_offset():
    payload = Clock().now()

    assert payload["timezone"]
    assert re.fullmatch(
        r"[+-]\d{2}:\d{2}",
        payload["utc_offset"],
    )
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        payload["date"],
    )
    assert re.fullmatch(
        r"\d{2}:\d{2}:\d{2}",
        payload["time"],
    )
    assert payload["iso"].startswith(payload["date"])


def test_calendar_julian_conversion():
    result = Calendar().convert(
        "julian",
        "2026-11-05",
    )

    assert result["success"] is True
    assert result["calendar"] == "julian"
    assert result["year"] == 2026
    assert result["month"] == 10
    assert result["day"] == 23
    assert result["month_name"] == "October"
    assert result["weekday"] == "Thursday"


def test_calendar_islamic_conversion():
    result = Calendar().convert(
        "islamic",
        "2024-03-11",
    )

    assert result["success"] is True
    assert result["calendar"] == "islamic"
    assert result["year"] == 1445
    assert result["month"] == 9
    assert result["day"] == 1
    assert result["month_name"] == "Ramadan"


def test_calendar_aliases_and_errors():
    calendar = Calendar()

    assert calendar.convert(
        "giuliano",
        "2026-11-05",
    )["success"] is True
    assert calendar.convert(
        "hijri",
        "2026-11-05",
    )["success"] is True

    invalid = calendar.convert("mayan", "2026-11-05")

    assert invalid["success"] is False
    assert "julian" in invalid["error"]

    invalid_date = calendar.convert("julian", "not-a-date")

    assert invalid_date["success"] is False


def test_think_returns_exact_text():
    thought = "Passo 1: α\nPasso 2: β — identico."

    assert Think().echo(thought) == thought


def test_local_time_tools_are_registered():
    registry = ToolRegistry()

    ClockToolProvider(Clock()).register_tools(registry)
    CalendarToolProvider(Calendar()).register_tools(registry)
    ThinkToolProvider(Think()).register_tools(registry)

    assert set(registry.tool_names()) == {
        "clock.now",
        "calendar.date",
        "think.echo",
    }

    assert registry.get("clock.now").capabilities == (
        Capability.COMPUTE
    )
    assert registry.get("calendar.date").capabilities == (
        Capability.COMPUTE
    )
    assert registry.get("think.echo").capabilities == (
        Capability.COMPUTE
    )


def test_local_time_tool_handlers():
    registry = ToolRegistry()

    ClockToolProvider(Clock()).register_tools(registry)
    CalendarToolProvider(Calendar()).register_tools(registry)
    ThinkToolProvider(Think()).register_tools(registry)

    clock = json.loads(
        registry.execute("clock.now")
    )

    assert clock["timezone"]

    calendar = json.loads(
        registry.execute(
            "calendar.date",
            calendar="julian",
            date="2026-11-05",
        )
    )

    assert calendar["day"] == 23
    assert calendar["month"] == 10

    thought = "uno\ndue"

    assert (
        registry.execute(
            "think.echo",
            thought=thought,
        )
        == thought
    )
