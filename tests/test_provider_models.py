"""Test dei metadati normalizzati dei provider."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.command_service import CommandService
from core.provider_models import (
    ProviderModelError,
    discover,
    from_lmstudio,
    from_ollama,
)


def test_lmstudio_model_info():
    info = from_lmstudio({
        "id": "gemma-3-27b-it",
        "type": "vlm",
        "max_context_length": 131072,
        "quantization": "Q3_K_L",
        "state": "loaded",
        "capabilities": ["tool_use"],
    })

    assert info.provider == "lmstudio"
    assert info.model == "gemma-3-27b-it"
    assert info.model_type == "vlm"
    assert info.context_window == 131072
    assert info.quantization == "Q3_K_L"
    assert info.state == "loaded"
    assert "text_generation" in info.capabilities
    assert "vision" in info.capabilities
    assert "tool_calling" in info.capabilities
    assert info.hagar_capabilities() == frozenset({
        "vision",
        "tool_calling",
    })


def test_ollama_model_info():
    info = from_ollama(
        {
            "name": "qwen3:8b",
            "details": {
                "family": "qwen3",
                "quantization_level": "Q4_K_M",
                "context_length": 40960,
            },
        },
        {
            "capabilities": ["completion", "tools", "thinking"],
        },
    )

    assert info.model == "qwen3:8b"
    assert info.model_type == "qwen3"
    assert info.context_window == 40960
    assert info.quantization == "Q4_K_M"
    assert "text_generation" in info.capabilities
    assert info.hagar_capabilities() == frozenset({
        "reasoning",
        "tool_calling",
    })


def test_discovery_rejects_unknown_provider():
    with pytest.raises(ProviderModelError):
        discover("unknown")


def test_models_discover_command(monkeypatch):
    import core.command_service as command_module

    monkeypatch.setattr(
        command_module,
        "discover",
        lambda provider, host=None: [
            from_lmstudio({
                "id": "local",
                "type": "llm",
                "max_context_length": 4096,
                "capabilities": ["tool_use"],
            })
        ],
    )
    harness = SimpleNamespace(
        config=SimpleNamespace(
            model=SimpleNamespace(
                provider="lmstudio",
                host="http://localhost:1234/v1",
            )
        ),
        audit=None,
    )
    commands = CommandService(
        harness,
        SimpleNamespace(),
    )

    result = commands.handle("/models discover lmstudio")

    assert result.ok is True
    assert result.data["provider"] == "lmstudio"
    assert result.data["models"][0]["model"] == "local"
    assert "tool_calling" in result.data["models"][0][
        "hagar_capabilities"
    ]
