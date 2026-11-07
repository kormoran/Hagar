# llm/factory.py

"""Factory dei provider LLM, con provider built-in e plugin esterni."""

from __future__ import annotations

from typing import Any

from core.config import ConfigError
from core.models import ModelConfig
from core.plugins import PluginFailure
from core.plugins import load_llm_providers
from llm.base import LLMClient
from llm.plugins import BUILTIN_LLM_PROVIDERS
from llm.plugins import DEFAULT_API_KEY_ENV
from llm.plugins import PUBLIC_PROVIDERS
from llm.plugins import resolve_api_key


SUPPORTED_PROVIDERS = tuple(PUBLIC_PROVIDERS)

_provider_cache: dict[str, Any] | None = None
_plugin_failures: list[PluginFailure] = []


def _providers() -> dict[str, Any]:
    """Carica built-in e plugin una sola volta."""

    global _provider_cache
    global _plugin_failures

    if _provider_cache is None:

        _provider_cache, _plugin_failures = load_llm_providers(
            BUILTIN_LLM_PROVIDERS,
        )

    return _provider_cache


def available_providers() -> list[str]:
    """Provider built-in e plugin, senza alias interni."""

    providers = _providers()
    names = list(PUBLIC_PROVIDERS)

    for name in providers:

        if name not in names and name != "chatgpt":
            names.append(name)

    return names


def _with_native(
    client: LLMClient,
    config: ModelConfig,
) -> LLMClient:
    """Applica il flag di calling nativo al client."""

    client.native_tools = config.native_tools

    return client


def create_llm(
    config: ModelConfig,
    audit: Any = None,
) -> LLMClient:
    """Costruisce il client del provider indicato dalla configurazione."""

    provider = config.provider.strip().lower()
    providers = _providers()

    if audit is not None:

        for failure in _plugin_failures:

            audit.record(
                "plugin.error",
                plugin_group=failure.group,
                plugin=failure.name,
                error=failure.error,
            )

    spec = providers.get(provider)

    if spec is None:

        raise ConfigError(
            f"Unsupported model provider: "
            f"'{config.provider}'. Supported: "
            + ", ".join(available_providers())
        )

    client = spec.factory(config, audit)

    return _with_native(client, config)
