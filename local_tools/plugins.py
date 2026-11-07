"""Tool built-in registrati attraverso il contratto plugin."""

from __future__ import annotations

from core.plugins import PluginContext
from core.plugins import ToolPlugin
from core.tool_registry import ToolRegistry

from local_tools.calendar import Calendar
from local_tools.calendar_tool import CalendarToolProvider
from local_tools.calculator import Calculator
from local_tools.clock import Clock
from local_tools.clock_tool import ClockToolProvider
from local_tools.feeder import Feeder
from local_tools.feeder_tool import FeederToolProvider
from local_tools.math_tools import MathToolsProvider
from local_tools.statistics import Stats_calc
from local_tools.text_diff import TextDiff
from local_tools.text_diff_tool import TextDiffToolProvider
from local_tools.think import Think
from local_tools.think_tool import ThinkToolProvider
from local_tools.unit_converter import UnitConverter
from local_tools.unit_converter_tool import UnitConverterToolProvider
from local_tools.url_parse import UrlParser
from local_tools.url_parse_tool import UrlParseToolProvider


def register_clock(
    registry: ToolRegistry,
    context: PluginContext,
) -> None:
    ClockToolProvider(Clock()).register_tools(registry)


def register_calendar(
    registry: ToolRegistry,
    context: PluginContext,
) -> None:
    CalendarToolProvider(Calendar()).register_tools(registry)


def register_think(
    registry: ToolRegistry,
    context: PluginContext,
) -> None:
    ThinkToolProvider(Think()).register_tools(registry)


def register_text_diff(
    registry: ToolRegistry,
    context: PluginContext,
) -> None:
    TextDiffToolProvider(TextDiff()).register_tools(registry)


def register_url_parse(
    registry: ToolRegistry,
    context: PluginContext,
) -> None:
    UrlParseToolProvider(UrlParser()).register_tools(registry)


def register_math(
    registry: ToolRegistry,
    context: PluginContext,
) -> None:
    MathToolsProvider(
        Calculator(),
        Stats_calc(),
    ).register_tools(registry)


def register_unit_converter(
    registry: ToolRegistry,
    context: PluginContext,
) -> None:
    UnitConverterToolProvider(
        UnitConverter()
    ).register_tools(registry)


def register_feeder(
    registry: ToolRegistry,
    context: PluginContext,
) -> None:
    FeederToolProvider(Feeder()).register_tools(registry)


BUILTIN_TOOL_PLUGINS = [
    ToolPlugin(
        name="clock",
        version="1.0",
        builtin=True,
        register=register_clock,
    ),
    ToolPlugin(
        name="calendar",
        version="1.0",
        builtin=True,
        register=register_calendar,
    ),
    ToolPlugin(
        name="think",
        version="1.0",
        builtin=True,
        register=register_think,
    ),
    ToolPlugin(
        name="text-diff",
        version="1.0",
        builtin=True,
        register=register_text_diff,
    ),
    ToolPlugin(
        name="url-parse",
        version="1.0",
        builtin=True,
        register=register_url_parse,
    ),
    ToolPlugin(
        name="math",
        version="1.0",
        builtin=True,
        register=register_math,
    ),
    ToolPlugin(
        name="unit-converter",
        version="1.0",
        builtin=True,
        register=register_unit_converter,
    ),
    ToolPlugin(
        name="feeder",
        version="1.0",
        builtin=True,
        register=register_feeder,
    ),
]
