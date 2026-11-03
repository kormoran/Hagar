"""Test live dei provider remoti.

Eseguiti solo con ``--live`` e solo se la chiave API è presente.
Il modello è configurabile con le variabili indicate sotto.
"""

from __future__ import annotations

import os

import pytest

from core.models import ModelConfig
from llm.factory import create_llm

pytestmark = pytest.mark.live

PROVIDERS = {
    "deepseek": (
        "DEEPSEEK_API_KEY",
        "HAGAR_LIVE_DEEPSEEK_MODEL",
        "deepseek-chat",
    ),
    "claude": (
        "ANTHROPIC_API_KEY",
        "HAGAR_LIVE_CLAUDE_MODEL",
        "claude-3-5-haiku-latest",
    ),
    "gemini": (
        "GEMINI_API_KEY",
        "HAGAR_LIVE_GEMINI_MODEL",
        "gemini-2.0-flash",
    ),
}


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_provider_chat(provider):
    key_env, model_env, default_model = PROVIDERS[provider]

    if not os.environ.get(key_env, "").strip():

        pytest.skip(
            f"{key_env} non impostata"
        )

    model = os.environ.get(
        model_env,
        default_model,
    )

    client = create_llm(
        ModelConfig(
            provider=provider,
            name=model,
        )
    )

    answer = client.chat(
        [
            {
                "role": "user",
                "content": "Rispondi solo: ok",
            }
        ]
    )

    assert answer.strip()
