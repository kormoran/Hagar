"""Plugin di Hagar: tool e provider LLM.

I plugin Python girano nello stesso processo e sono considerati trusted:
possono usare l'API del processo. La policy, il sandbox e l'audit restano
nell'host; un plugin non può concedere permessi.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any
from typing import Callable


TOOL_GROUP = "hagar.tools"
LLM_GROUP = "hagar.llm"


class PluginError(RuntimeError):
    pass


@dataclass(frozen=True)
class PluginContext:
    """Dipendenze che l'host passa a un plugin di tool."""

    config: Any = None
    audit: Any = None
    filesystem: Any = None
    memory: Any = None
    project_store: Any = None
    project_state: dict[str, Any] | None = None
    subagents: Any = None


@dataclass(frozen=True)
class ToolPlugin:
    """Un plugin che registra uno o più ToolDefinition."""

    name: str
    version: str
    register: Callable[[Any, PluginContext], None]
    builtin: bool = False


@dataclass(frozen=True)
class LLMProvider:
    """Factory di un client LLM e capability dichiarate."""

    name: str
    version: str
    factory: Callable[[Any, Any], Any]
    capabilities: frozenset[str] = frozenset()
    builtin: bool = False


@dataclass(frozen=True)
class PluginFailure:
    group: str
    name: str
    error: str


def _entry_points(group: str) -> list[Any]:

    discovered = entry_points()

    if hasattr(discovered, "select"):

        return list(discovered.select(group=group))

    return list(discovered.get(group, []))


def _normalize_tool(
    name: str,
    target: Any,
) -> ToolPlugin:

    if isinstance(target, ToolPlugin):
        return target

    if hasattr(target, "register") and hasattr(target, "name"):
        return ToolPlugin(
            name=str(target.name),
            version=str(
                getattr(target, "version", "external")
            ),
            register=target.register,
            builtin=bool(getattr(target, "builtin", False)),
        )

    if callable(target):
        return ToolPlugin(
            name=name,
            version="external",
            register=target,
            builtin=False,
        )

    raise PluginError(
        f"tool plugin {name!r} must expose ToolPlugin "
        "or a register(registry, context) callable"
    )


def _normalize_llm(
    name: str,
    target: Any,
) -> LLMProvider:

    if isinstance(target, LLMProvider):
        return target

    if hasattr(target, "factory") and hasattr(target, "name"):
        return LLMProvider(
            name=str(target.name),
            version=str(
                getattr(target, "version", "external")
            ),
            factory=target.factory,
            capabilities=frozenset(
                getattr(target, "capabilities", ())
            ),
            builtin=bool(getattr(target, "builtin", False)),
        )

    if callable(target):
        return LLMProvider(
            name=name,
            version="external",
            factory=target,
            builtin=False,
        )

    raise PluginError(
        f"LLM plugin {name!r} must expose LLMProvider "
        "or a factory(config, audit) callable"
    )


def _audit_load(
    audit: Any,
    group: str,
    name: str,
    version: str,
) -> None:

    if audit is None:
        return

    try:
        audit.record(
            "plugin.loaded",
            plugin_group=group,
            plugin=name,
            version=version,
        )
    except Exception:
        pass


def _audit_failure(
    audit: Any,
    failure: PluginFailure,
) -> None:

    if audit is None:
        return

    try:
        audit.record(
            "plugin.error",
            plugin_group=failure.group,
            plugin=failure.name,
            error=failure.error,
        )
    except Exception:
        pass


def load_tool_plugins(
    builtins: list[ToolPlugin],
    registry: Any,
    context: PluginContext,
    audit: Any = None,
) -> list[PluginFailure]:
    """Registra built-in e plugin esterni; isola i plugin guasti."""

    failures: list[PluginFailure] = []
    plugins = list(builtins)

    for entry in _entry_points(TOOL_GROUP):

        try:
            plugins.append(
                _normalize_tool(
                    entry.name,
                    entry.load(),
                )
            )

        except Exception as exc:
            failure = PluginFailure(
                group=TOOL_GROUP,
                name=entry.name,
                error=str(exc),
            )
            failures.append(failure)
            _audit_failure(audit, failure)

    seen: set[str] = set()

    for plugin in plugins:

        if not plugin.name or not plugin.version:
            failure = PluginFailure(
                group=TOOL_GROUP,
                name=plugin.name or "<unnamed>",
                error="name and version are required",
            )
            failures.append(failure)
            _audit_failure(audit, failure)
            continue

        if plugin.name in seen:
            failure = PluginFailure(
                group=TOOL_GROUP,
                name=plugin.name,
                error="duplicate plugin name",
            )
            failures.append(failure)
            _audit_failure(audit, failure)
            continue

        seen.add(plugin.name)

        try:
            plugin.register(registry, context)
        except Exception as exc:
            failure = PluginFailure(
                group=TOOL_GROUP,
                name=plugin.name,
                error=str(exc),
            )
            failures.append(failure)
            _audit_failure(audit, failure)
            continue

        if not plugin.builtin:

            _audit_load(
                audit,
                TOOL_GROUP,
                plugin.name,
                plugin.version,
            )

    return failures


def load_llm_providers(
    builtins: list[LLMProvider],
    audit: Any = None,
) -> tuple[dict[str, LLMProvider], list[PluginFailure]]:
    """Built-in più provider esterni; i nomi duplicati restano al built-in."""

    providers = {
        provider.name: provider
        for provider in builtins
    }
    failures: list[PluginFailure] = []

    for entry in _entry_points(LLM_GROUP):

        try:
            provider = _normalize_llm(
                entry.name,
                entry.load(),
            )

        except Exception as exc:
            failure = PluginFailure(
                group=LLM_GROUP,
                name=entry.name,
                error=str(exc),
            )
            failures.append(failure)
            _audit_failure(audit, failure)
            continue

        if provider.name in providers:
            failure = PluginFailure(
                group=LLM_GROUP,
                name=provider.name,
                error="provider already registered",
            )
            failures.append(failure)
            _audit_failure(audit, failure)
            continue

        providers[provider.name] = provider

        if not provider.builtin:

            _audit_load(
                audit,
                LLM_GROUP,
                provider.name,
                provider.version,
            )

    return providers, failures
