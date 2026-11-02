# llm/factory.py

from __future__ import annotations

import os

from typing import Any

from core.config import ConfigError
from core.models import ModelConfig
from llm.base import LLMClient
from llm.claude_client import ClaudeClient
from llm.deepseek_client import DeepSeekClient
from llm.gemini_client import GeminiClient
from llm.ollama_client import OllamaClient

SUPPORTED_PROVIDERS = (
    "ollama",
    "deepseek",
    "claude",
    "gemini",
)

DEFAULT_API_KEY_ENV = {
    "deepseek": "DEEPSEEK_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def available_providers() -> list[str]:
    """Provider supportati, nell'ordine in cui vengono elencati gli errori."""

    return list(SUPPORTED_PROVIDERS)


def resolve_api_key(
    config: ModelConfig,
) -> str:
    """
    Legge la chiave API dall'ambiente.

    Le chiavi non compaiono mai nel file di configurazione: il YAML dice
    solo quale variabile leggere (``model.api_key_env``), e solo se il
    nome predefinito del provider non va bene.
    """

    provider = config.provider.strip().lower()

    env_name = (
        config.api_key_env
        or DEFAULT_API_KEY_ENV.get(provider)
    )

    if not env_name:

        raise ConfigError(
            f"Provider '{provider}' does not use an API key"
        )

    value = os.environ.get(env_name, "").strip()

    if not value:

        raise ConfigError(
            f"Missing API key for provider "
            f"'{provider}': set the {env_name} "
            f"environment variable"
        )

    return value


def create_llm(
    config: ModelConfig,
    audit: Any = None,
) -> LLMClient:
    """Costruisce il client del provider indicato dalla configurazione."""

    provider = config.provider.strip().lower()

    if provider == "ollama":

        return OllamaClient(
            model=config.name,
            host=config.host,
            audit=audit,
        )

    if provider == "deepseek":

        return DeepSeekClient(
            api_key=resolve_api_key(config),
            model=config.name,
            audit=audit,
        )

    if provider == "claude":

        return ClaudeClient(
            api_key=resolve_api_key(config),
            model=config.name,
            max_tokens=config.max_tokens,
            audit=audit,
        )

    if provider == "gemini":

        return GeminiClient(
            api_key=resolve_api_key(config),
            model=config.name,
            audit=audit,
        )

    raise ConfigError(
        f"Unsupported model provider: "
        f"'{config.provider}'. Supported: "
        + ", ".join(SUPPORTED_PROVIDERS)
    )
