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
from llm.lmstudio_client import LMStudioClient
from llm.ollama_client import OllamaClient
from llm.openai_client import OpenAIClient


def test_supported_providers():
    assert available_providers() == [
        "ollama",
        "lmstudio",
        "deepseek",
        "openai",
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


def test_deepseek_uses_configured_base_url(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk")

    llm = create_llm(
        ModelConfig(
            provider="deepseek",
            name="deepseek-chat",
            host="http://proxy:1234",
        )
    )

    assert llm.base_url == "http://proxy:1234"


def test_openai_uses_default_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    llm = create_llm(
        ModelConfig(
            provider="openai",
            name="gpt-4o",
        )
    )

    assert isinstance(llm, OpenAIClient)
    assert llm.base_url == OpenAIClient.DEFAULT_BASE_URL
    assert llm.api_key == "sk-openai"


def test_chatgpt_is_an_alias_for_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    llm = create_llm(
        ModelConfig(
            provider="chatgpt",
            name="gpt-4o",
        )
    )

    assert isinstance(llm, OpenAIClient)
    assert llm.provider == "openai"


def test_lmstudio_uses_local_default_without_key():
    llm = create_llm(
        ModelConfig(
            provider="lmstudio",
            name="local-model",
        )
    )

    assert isinstance(llm, LMStudioClient)
    assert llm.base_url == LMStudioClient.DEFAULT_BASE_URL
    assert llm.api_key is None


def test_lmstudio_uses_configured_host():
    llm = create_llm(
        ModelConfig(
            provider="lmstudio",
            name="local-model",
            host="http://gpu:1234/v1",
        )
    )

    assert llm.base_url == "http://gpu:1234/v1"


def test_claude_uses_configured_base_url(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk")

    llm = create_llm(
        ModelConfig(
            provider="claude",
            name="claude-model",
            host="http://proxy:1234",
        )
    )

    assert llm.base_url == "http://proxy:1234"


def test_gemini_uses_configured_base_url(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk")

    llm = create_llm(
        ModelConfig(
            provider="gemini",
            name="gemini-2.0-flash",
            host="http://proxy:1234",
        )
    )

    assert llm.base_url == "http://proxy:1234"


def test_remote_providers_keep_default_base_url(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk")
    monkeypatch.setenv("GEMINI_API_KEY", "sk")

    deepseek = create_llm(
        ModelConfig(provider="deepseek", name="deepseek-chat")
    )
    openai = create_llm(
        ModelConfig(provider="openai", name="gpt-4o")
    )
    claude = create_llm(
        ModelConfig(provider="claude", name="claude-model")
    )
    gemini = create_llm(
        ModelConfig(provider="gemini", name="gemini-2.0-flash")
    )

    assert deepseek.base_url == DeepSeekClient.DEFAULT_BASE_URL
    assert openai.base_url == OpenAIClient.DEFAULT_BASE_URL
    assert claude.base_url == ClaudeClient.DEFAULT_BASE_URL
    assert gemini.base_url == GeminiClient.DEFAULT_BASE_URL


def test_factory_enables_native_tools_by_default():
    llm = create_llm(
        ModelConfig(provider="ollama", name="m")
    )

    assert llm.native_tools is True


def test_factory_can_disable_native_tools():
    llm = create_llm(
        ModelConfig(
            provider="ollama",
            name="m",
            native_tools=False,
        )
    )

    assert llm.native_tools is False


def test_factory_passes_model_timeout():
    llm = create_llm(
        ModelConfig(
            provider="lmstudio",
            name="m",
            timeout=300,
        )
    )

    assert llm.timeout == 300


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
        ("openai", "OPENAI_API_KEY"),
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


def test_non_ascii_api_key_is_reported(monkeypatch):
    monkeypatch.setenv(
        "DEEPSEEK_API_KEY",
        "\u2022",
    )

    with pytest.raises(
        ConfigError,
        match="non-ASCII",
    ):
        create_llm(
            ModelConfig(
                provider="deepseek",
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
