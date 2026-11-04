"""Test dei tool locali in MCP_tools."""

from __future__ import annotations

import json

import pytest

from core.permissions import Capability
from core.tool_registry import ToolRegistry
from MCP_tools.calculator import Calculator
from MCP_tools.feeder import Feeder
from MCP_tools.feeder_tool import FeederToolProvider
from MCP_tools.math_tools import MathToolsProvider
from MCP_tools.statistics import Stats_calc
from MCP_tools.unit_converter import UnitConverter
from MCP_tools.unit_converter_tool import (
    UnitConverterToolProvider,
)

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Notizie</title>
    <link>https://example.com</link>
    <description>Feed di prova</description>
    <item>
      <title>Prima</title>
      <link>https://example.com/1</link>
      <description><![CDATA[<b>Testo</b> uno]]></description>
      <pubDate>Mon, 03 Nov 2026 10:00:00 GMT</pubDate>
      <author>Autore</author>
    </item>
    <item>
      <title>Seconda</title>
      <link>https://example.com/2</link>
      <description>Testo due</description>
    </item>
  </channel>
</rss>
"""


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}"
            )


def test_calculator_arithmetic():
    calc = Calculator()

    assert calc.evaluate("2 + 3 * 4")["result"] == 14
    assert calc.evaluate("sqrt(9)")["result"] == 3
    assert calc.evaluate("2 ** 10")["result"] == 1024


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "(1).__class__",
        "9 ** 999999",
        "True",
        "round(1.5, ndigits=1)",
        "1 / 0",
        "lambda: 1",
    ],
)
def test_calculator_rejects_unsafe_or_invalid(
    expression,
):
    result = Calculator().evaluate(expression)

    assert result["success"] is False


def test_statistics_operations():
    stats = Stats_calc()

    assert stats.compute("mean", [1, 2, 3])["result"] == 2
    assert stats.compute("count", [1, 2, 3])["result"] == 3
    assert stats.compute("stdev", [1, 2])["success"] is True
    assert stats.compute("stdev", [1])["success"] is False
    assert stats.compute("mean", [])["success"] is False
    assert stats.compute("altro", [1])["success"] is False


def test_unit_conversions():
    units = UnitConverter()

    assert units.convert(1, "km", "m")["result"] == 1000
    assert units.convert(0, "c", "f")["result"] == 32
    assert units.convert(180, "deg", "rad")["result"] == pytest.approx(
        3.141592653589793
    )
    assert units.convert(1, "kg", "g")["result"] == 1000
    assert units.convert(1, "kg", "m")["success"] is False


def test_math_provider_registers_tools():
    registry = ToolRegistry()

    MathToolsProvider(
        Calculator(),
        Stats_calc(),
    ).register_tools(registry)

    assert set(registry.tool_names()) == {
        "calculator.evaluate",
        "statistics.compute",
    }

    assert registry.get("calculator.evaluate").capabilities == (
        Capability.COMPUTE
    )

    payload = json.loads(
        registry.execute(
            "calculator.evaluate",
            expression="2 + 2",
        )
    )

    assert payload["result"] == 4


def test_unit_provider_registers_tool():
    registry = ToolRegistry()

    UnitConverterToolProvider(
        UnitConverter()
    ).register_tools(registry)

    assert registry.tool_names() == ["units.convert"]
    assert registry.get("units.convert").capabilities == (
        Capability.COMPUTE
    )

    payload = json.loads(
        registry.execute(
            "units.convert",
            value=1,
            from_unit="km",
            to_unit="m",
        )
    )

    assert payload["result"] == 1000


def test_feed_provider_registers_tool():
    registry = ToolRegistry()

    FeederToolProvider(
        Feeder()
    ).register_tools(registry)

    assert registry.tool_names() == ["feed.read"]
    assert registry.get("feed.read").capabilities == (
        Capability.NETWORK
    )


def test_feed_read_rss(monkeypatch):
    def fake_get(url, timeout, headers):
        return FakeResponse(RSS)

    monkeypatch.setattr(
        "MCP_tools.feeder.requests.get",
        fake_get,
    )

    result = Feeder().read(
        "https://example.com/feed",
        max_items=1,
    )

    assert result["success"] is True
    assert result["feed"]["title"] == "Notizie"
    assert result["total_items"] == 2
    assert result["returned_items"] == 1
    assert result["truncated"] is True
    assert result["items"][0]["title"] == "Prima"
    assert result["items"][0]["summary"] == "Testo uno"


def test_feed_rejects_non_http_url():
    result = Feeder().read("file:///etc/passwd")

    assert result["success"] is False
    assert "http" in result["error"]


def test_feed_reports_http_error(monkeypatch):
    monkeypatch.setattr(
        "MCP_tools.feeder.requests.get",
        lambda url, timeout, headers: FakeResponse(
            b"",
            status_code=500,
        ),
    )

    result = Feeder().read("https://example.com/feed")

    assert result["success"] is False


def test_feed_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr(
        "MCP_tools.feeder.requests.get",
        lambda url, timeout, headers: FakeResponse(
            b"x" * (Feeder.MAX_BYTES + 1)
        ),
    )

    result = Feeder().read("https://example.com/feed")

    assert result["success"] is False
    assert "larger" in result["error"]
