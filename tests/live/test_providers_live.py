"""Test live dei provider remoti.

Eseguiti solo con ``--live`` e solo se la chiave API è presente.
Il modello è configurabile con le variabili indicate sotto.
"""

from __future__ import annotations

import os

import pytest

from core.agent import Agent
from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.filesystem_tools import FileSystemToolProvider
from core.models import ModelConfig
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry
from llm.factory import create_llm

pytestmark = pytest.mark.live

PROVIDERS = {
    "deepseek": (
        "DEEPSEEK_API_KEY",
        "HAGAR_LIVE_DEEPSEEK_MODEL",
        "deepseek-flash",
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


def test_deepseek_native_tool_calling():
    if not os.environ.get(
        "DEEPSEEK_API_KEY",
        "",
    ).strip():

        pytest.skip("DEEPSEEK_API_KEY non impostata")

    model = os.environ.get(
        "HAGAR_LIVE_DEEPSEEK_MODEL",
        "deepseek-flash",
    )

    client = create_llm(
        ModelConfig(
            provider="deepseek",
            name=model,
        )
    )

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

    assert reply.tool_calls, (
        "DeepSeek non ha scelto un tool; "
        f"testo: {reply.text!r}"
    )

    call = reply.tool_calls[0]

    assert call.tool == "filesystem.read_file"
    assert call.arguments == {"path": "nota.txt"}


def test_deepseek_agent_reads_a_file(tmp_path):
    if not os.environ.get(
        "DEEPSEEK_API_KEY",
        "",
    ).strip():

        pytest.skip("DEEPSEEK_API_KEY non impostata")

    model = os.environ.get(
        "HAGAR_LIVE_DEEPSEEK_MODEL",
        "deepseek-flash",
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "nota.txt").write_text(
        "Il numero segreto è 42.\n",
        encoding="utf-8",
    )

    sandbox = FileSystemSandbox(
        roots={
            workspace: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
                rename=True,
                delete=True,
                execute=True,
            )
        },
        current_directory=workspace,
    )

    registry = ToolRegistry()

    FileSystemToolProvider(
        sandbox
    ).register_tools(registry)

    class Audit:
        include_outputs = True

        def __init__(self):
            self.entries = []

        def record(self, event, **fields):
            self.entries.append(
                {"event": event, **fields}
            )

    audit = Audit()

    agent = Agent(
        create_llm(
            ModelConfig(
                provider="deepseek",
                name=model,
            )
        ),
        registry,
        vault=None,
        audit=audit,
        max_tool_calls=3,
    )

    answer = agent.ask(
        "Leggi il file nota.txt e dimmi "
        "quale numero contiene. Usa il tool "
        "disponibile per leggere i file."
    )

    calls = [
        entry
        for entry in audit.entries
        if entry["event"] == "tool.call"
    ]

    assert calls, "DeepSeek non ha eseguito tool"

    assert calls[0]["tool"] == "filesystem.read_file"
    assert "42" in answer
