"""Test del contratto plugin per tool e provider LLM."""

from __future__ import annotations

import core.plugins as plugins
from core.plugins import LLMProvider
from core.plugins import PluginContext
from core.plugins import ToolPlugin
from core.plugins import load_llm_providers
from core.plugins import load_tool_plugins
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event, **fields):
        self.events.append((event, fields))


def make_plugin():
    def register(registry, context):
        registry.register(
            ToolDefinition(
                name="demo.echo",
                description="Echo",
                category="demo",
                handler=lambda text="": text,
            )
        )

    return ToolPlugin(
        name="demo",
        version="1.0",
        register=register,
        builtin=True,
    )


def test_tool_plugin_is_registered():
    registry = ToolRegistry()
    audit = Audit()

    failures = load_tool_plugins(
        [make_plugin()],
        registry,
        PluginContext(),
        audit=audit,
    )

    assert failures == []
    assert registry.tool_names() == ["demo.echo"]
    assert audit.events == []


def test_external_tool_entry_point_is_discovered(monkeypatch):
    class Entry:
        name = "external"

        def load(self):
            return lambda registry, context: registry.register(
                ToolDefinition(
                    name="external.echo",
                    description="Echo",
                    category="external",
                    handler=lambda text="": text,
                )
            )

    monkeypatch.setattr(
        plugins,
        "_entry_points",
        lambda group: [Entry()]
        if group == plugins.TOOL_GROUP
        else [],
    )

    registry = ToolRegistry()
    audit = Audit()

    failures = load_tool_plugins(
        [],
        registry,
        PluginContext(),
        audit=audit,
    )

    assert failures == []
    assert registry.tool_names() == ["external.echo"]
    assert audit.events[0][0] == "plugin.loaded"
    assert audit.events[0][1]["plugin"] == "external"


def test_broken_plugin_is_isolated():
    def broken(registry, context):
        raise RuntimeError("boom")

    plugin = ToolPlugin(
        name="broken",
        version="1.0",
        register=broken,
    )

    registry = ToolRegistry()
    audit = Audit()

    failures = load_tool_plugins(
        [plugin],
        registry,
        PluginContext(),
        audit=audit,
    )

    assert len(failures) == 1
    assert failures[0].name == "broken"
    assert registry.tool_names() == []
    assert audit.events[0][0] == "plugin.error"


def test_llm_provider_plugin_is_loadable():
    provider = LLMProvider(
        name="demo-llm",
        version="1.0",
        factory=lambda config, audit: object(),
        capabilities=frozenset({"vision"}),
    )

    providers, failures = load_llm_providers([provider])

    assert failures == []
    assert providers["demo-llm"].capabilities == {"vision"}
    assert providers["demo-llm"].factory(None, None) is not None


def test_duplicate_builtin_llm_provider_is_rejected(monkeypatch):
    class Entry:
        name = "ollama"

        def load(self):
            return lambda config, audit: object()

    monkeypatch.setattr(
        plugins,
        "_entry_points",
        lambda group: [Entry()]
        if group == plugins.LLM_GROUP
        else [],
    )

    providers, failures = load_llm_providers(
        [
            LLMProvider(
                name="ollama",
                version="1.0",
                factory=lambda config, audit: object(),
                builtin=True,
            )
        ]
    )

    assert "ollama" in providers
    assert len(failures) == 1
    assert "already registered" in failures[0].error
