"""Test live contro un server Ollama reale.

Eseguiti solo con ``--live``; saltati se il server non risponde.
"""

from __future__ import annotations

import os

import pytest
import requests

from core.agent import Agent
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry
from llm.ollama_client import OllamaClient
from memory.store import MemoryStore
from memory.vault import Vault

pytestmark = pytest.mark.live

HOST = os.environ.get(
    "HAGAR_LIVE_OLLAMA_HOST",
    "http://localhost:11434",
)

MODEL = os.environ.get(
    "HAGAR_LIVE_OLLAMA_MODEL",
    "llama3.1:latest",
)


def ollama_models() -> list[str]:

    try:

        response = requests.get(
            f"{HOST}/api/tags",
            timeout=3,
        )

        response.raise_for_status()

    except Exception as exc:

        pytest.skip(
            f"Ollama non raggiungibile su {HOST}: {exc}"
        )

    return [
        model["name"]
        for model in response.json().get(
            "models",
            [],
        )
    ]


def ollama_model() -> str:

    models = ollama_models()

    if MODEL in models:
        return MODEL

    if models:
        return models[0]

    pytest.skip("nessun modello Ollama disponibile")


def make_client() -> OllamaClient:

    return OllamaClient(
        host=HOST,
        model=ollama_model(),
        timeout=120,
    )


def test_chat_returns_text():
    client = make_client()

    answer = client.chat(
        [
            {
                "role": "user",
                "content": "Rispondi solo: ok",
            }
        ]
    )

    assert answer.strip()


def test_tool_selection_returns_registered_tool():
    client = make_client()

    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="filesystem.read_file",
            description="Read a file from the sandbox.",
            category="filesystem",
            handler=lambda path: "contenuto",
            parameters=[
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Path of the file to read.",
                )
            ],
        )
    )

    call = client.request_tool_call(
        [
            {
                "role": "user",
                "content": (
                    "Leggi il file nota.txt. "
                    "Usa esattamente il tool "
                    "filesystem.read_file con path nota.txt."
                ),
            }
        ],
        registry,
    )

    assert call.tool is None or call.tool in registry.tool_names()

    if call.tool is not None:
        assert isinstance(call.arguments, dict)


def test_native_tool_calling():
    from llm.base import NativeToolsUnavailable

    client = make_client()

    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="filesystem.read_file",
            description="Read a file from the sandbox.",
            category="filesystem",
            handler=lambda path: "contenuto",
            parameters=[
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Path of the file to read.",
                )
            ],
        )
    )

    try:

        reply = client.native_step(
            [
                {
                    "role": "user",
                    "content": (
                        "Leggi il file nota.txt usando "
                        "il tool disponibile per leggere "
                        "i file, con path nota.txt."
                    ),
                }
            ],
            registry,
        )

    except NativeToolsUnavailable as exc:

        pytest.skip(
            f"Ollama senza tool nativi: {exc}"
        )

    if reply.tool_calls:

        assert (
            reply.tool_calls[0].tool
            in registry.tool_names()
        )

    else:

        assert reply.text.strip()


def test_agent_stores_the_turn_in_memory(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()

    store = MemoryStore(
        Vault(root),
        session_id="live",
        context_turns=5,
        max_skill_chars=4000,
        model=MODEL,
    )

    agent = Agent(
        make_client(),
        ToolRegistry(),
        vault=None,
        memory=store,
    )

    answer = agent.ask("Rispondi solo: ok")

    assert answer.strip()

    turns = store.recent_turns()

    assert len(turns) == 1
    assert turns[0].question == "Rispondi solo: ok"
    assert turns[0].answer.strip()
