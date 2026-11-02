"""Test della factory dei backend LLM."""

from __future__ import annotations

import pytest

from core.config import ConfigError
from core.models import ModelConfig
from llm.claude_client import ClaudeClient
from llm.deepseek_client import DeepSeekClient
from llm.factory import (
    available_providers,
    create_llm,
    resolve_api_key,
)
from llm.gemini_client import GeminiClient
from llm.ollama_client import OllamaClient


def test_supported_providers():
    assert available_providers() == [
        "ollama",
        "deepseek",
        "claude",
        "gemini",
    ]


def test_ollama_uses_default_host():
    llm = create_llm(
        ModelConfig(provider="ollama", name="qwen3:8b")
    )

    assert isinstance(llm, OllamaClient)
    assert llm.host == "http://localhost:11434"
    assert llm.model == "qwen3:8b"


def test_ollama_uses_configured_host():
    llm = create_llm(
        ModelConfig(
            provider="ollama",
            name="qwen3:8b",
            host="http://gpu-box:11434",
        )
    )

    assert llm.host == "http://gpu-box:11434"


def test_provider_is_case_insensitive():
    llm = create_llm(
        ModelConfig(provider="OLLAMA", name="m")
    )

    assert isinstance(llm, OllamaClient)


def test_deepseek_reads_api_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")

    llm = create_llm(
        ModelConfig(
            provider="deepseek",
            name="deepseek-chat",
        )
    )

    assert isinstance(llm, DeepSeekClient)
    assert llm.api_key == "sk-deepseek"
    assert llm.model == "deepseek-chat"


def test_claude_reads_api_key_and_max_tokens(
    monkeypatch,
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")

    llm = create_llm(
        ModelConfig(
            provider="claude",
            name="claude-model",
            max_tokens=512,
        )
    )

    assert isinstance(llm, ClaudeClient)
    assert llm.api_key == "sk-ant"
    assert llm.max_tokens == 512


def test_gemini_reads_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-gemini")

    llm = create_llm(
        ModelConfig(
            provider="gemini",
            name="gemini-2.0-flash",
        )
    )

    assert isinstance(llm, GeminiClient)
    assert llm.api_key == "sk-gemini"


@pytest.mark.parametrize(
    "provider, env_name",
    [
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("claude", "ANTHROPIC_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
    ],
)
def test_missing_api_key_is_reported(
    provider,
    env_name,
    monkeypatch,
):
    monkeypatch.delenv(env_name, raising=False)

    with pytest.raises(
        ConfigError,
        match=env_name,
    ):
        create_llm(
            ModelConfig(
                provider=provider,
                name="model",
            )
        )


def test_api_key_env_can_be_overridden(monkeypatch):
    monkeypatch.setenv("MY_PROVIDER_KEY", "sk-custom")

    llm = create_llm(
        ModelConfig(
            provider="gemini",
            name="gemini-2.0-flash",
            api_key_env="MY_PROVIDER_KEY",
        )
    )

    assert llm.api_key == "sk-custom"


def test_blank_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")

    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        resolve_api_key(
            ModelConfig(
                provider="deepseek",
                name="deepseek-chat",
            )
        )


def test_unknown_provider_is_rejected():
    with pytest.raises(
        ConfigError,
        match="Unsupported model provider",
    ):
        create_llm(
            ModelConfig(provider="acme", name="model")
        )


def test_audit_is_passed_to_the_client():
    audit = object()

    llm = create_llm(
        ModelConfig(provider="ollama", name="m"),
        audit=audit,
    )

    assert llm.audit is audit
