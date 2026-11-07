"""Provider LLM built-in e plugin.

Un provider esterno può registrare un entry point ``hagar.llm`` che
restituisce un ``LLMProvider`` o una factory ``(config, audit) -> LLMClient``.
"""

from __future__ import annotations

import os

from typing import Any

from core.config import ConfigError
from core.models import ModelConfig
from core.plugins import LLMProvider
from llm.base import LLMClient
from llm.claude_client import ClaudeClient
from llm.deepseek_client import DeepSeekClient
from llm.gemini_client import GeminiClient
from llm.lmstudio_client import LMStudioClient
from llm.ollama_client import OllamaClient
from llm.openai_client import OpenAIClient


DEFAULT_API_KEY_ENV = {
    "lmstudio": "LMSTUDIO_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "chatgpt": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def resolve_api_key(
    config: ModelConfig,
) -> str:
    """Legge la chiave API dall'ambiente, mai dal file di configurazione."""

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

    if not value.isascii():

        raise ConfigError(
            f"{env_name} contains non-ASCII "
            "characters: the key was probably "
            "not pasted correctly"
        )

    return value


def _ollama(
    config: ModelConfig,
    audit: Any,
) -> LLMClient:

    return OllamaClient(
        model=config.name,
        host=config.host,
        timeout=config.timeout,
        audit=audit,
    )


def _lmstudio(
    config: ModelConfig,
    audit: Any,
) -> LLMClient:

    env_name = (
        config.api_key_env
        or DEFAULT_API_KEY_ENV["lmstudio"]
    )

    api_key = (
        os.environ.get(env_name, "").strip()
        or None
    )

    return LMStudioClient(
        model=config.name,
        host=config.host,
        api_key=api_key,
        timeout=config.timeout,
        audit=audit,
    )


def _openai(
    config: ModelConfig,
    audit: Any,
) -> LLMClient:

    return OpenAIClient(
        api_key=resolve_api_key(config),
        model=config.name,
        base_url=(
            config.host
            or OpenAIClient.DEFAULT_BASE_URL
        ),
        timeout=config.timeout,
        audit=audit,
    )


def _deepseek(
    config: ModelConfig,
    audit: Any,
) -> LLMClient:

    return DeepSeekClient(
        api_key=resolve_api_key(config),
        model=config.name,
        base_url=(
            config.host
            or DeepSeekClient.DEFAULT_BASE_URL
        ),
        timeout=config.timeout,
        audit=audit,
    )


def _claude(
    config: ModelConfig,
    audit: Any,
) -> LLMClient:

    return ClaudeClient(
        api_key=resolve_api_key(config),
        model=config.name,
        max_tokens=config.max_tokens,
        base_url=(
            config.host
            or ClaudeClient.DEFAULT_BASE_URL
        ),
        timeout=config.timeout,
        audit=audit,
    )


def _gemini(
    config: ModelConfig,
    audit: Any,
) -> LLMClient:

    return GeminiClient(
        api_key=resolve_api_key(config),
        model=config.name,
        base_url=(
            config.host
            or GeminiClient.DEFAULT_BASE_URL
        ),
        timeout=config.timeout,
        audit=audit,
    )


BUILTIN_LLM_PROVIDERS = [
    LLMProvider(
        name="ollama",
        version="1.0",
        builtin=True,
        factory=_ollama,
        capabilities=frozenset({"usage", "native_tools"}),
    ),
    LLMProvider(
        name="lmstudio",
        version="1.0",
        builtin=True,
        factory=_lmstudio,
        capabilities=frozenset({
            "usage", "native_tools", "vision", "reasoning",
        }),
    ),
    LLMProvider(
        name="deepseek",
        version="1.0",
        builtin=True,
        factory=_deepseek,
        capabilities=frozenset({
            "usage", "native_tools", "reasoning",
        }),
    ),
    LLMProvider(
        name="openai",
        version="1.0",
        builtin=True,
        factory=_openai,
        capabilities=frozenset({"usage", "native_tools", "vision"}),
    ),
    LLMProvider(
        name="chatgpt",
        version="1.0",
        builtin=True,
        factory=_openai,
        capabilities=frozenset({"usage", "native_tools", "vision"}),
    ),
    LLMProvider(
        name="claude",
        version="1.0",
        builtin=True,
        factory=_claude,
        capabilities=frozenset({"usage", "native_tools", "vision"}),
    ),
    LLMProvider(
        name="gemini",
        version="1.0",
        builtin=True,
        factory=_gemini,
        capabilities=frozenset({"usage", "native_tools", "vision"}),
    ),
]


PUBLIC_PROVIDERS = [
    "ollama",
    "lmstudio",
    "deepseek",
    "openai",
    "claude",
    "gemini",
]
