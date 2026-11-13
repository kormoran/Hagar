"""Test live delle primitive di memoria di Hagar Flow."""

from __future__ import annotations

import os
import re

import pytest

from core.flow import FlowRunner, LANGUAGE_CARD
from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.models import FlowConfig, ModelConfig
from core.tool_registry import ToolRegistry
from llm.factory import create_llm
from local_tools.flow_primitives import FlowPrimitiveProvider
from memory.sqlite_store import SqliteMemoryStore

pytestmark = pytest.mark.live

MODEL = os.environ.get(
    "HAGAR_LIVE_LMSTUDIO_MODEL",
    "qwen2.5-coder-7b-instruct",
)
HOST = os.environ.get(
    "HAGAR_LIVE_LMSTUDIO_HOST",
    "http://localhost:1234/v1",
)


def extract_code(text: str) -> str:
    match = re.search(
        r"```(?:python|hagar|flow)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else text


def test_lmstudio_memory_search_and_skill(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    memory = SqliteMemoryStore(
        session_id="live-s1",
        path=tmp_path / "memory.db",
        context_turns=5,
    )
    memory.ensure()
    memory.create_skill(
        "Release Hagar",
        "Il tag deve puntare al commit di preparazione.",
        kind="fact",
        tags=["release"],
    )
    memory.append_turn(
        "t1",
        "Come si prepara la release?",
        "Si prepara il tag.",
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
        aliases={"root": workspace},
    )

    registry = ToolRegistry()
    provider = FlowPrimitiveProvider(
        sandbox,
        memory=memory,
    )
    provider.register_tools(registry)
    runner = FlowRunner(
        registry,
        FlowConfig(enabled=True),
        provider.primitives,
    )

    prompt = f"""{LANGUAGE_CARD}

Primitive:
memory.search(query, kind="", status="", limit=10) -> list[dict]
memory.skill(skill_id) -> dict | None

Scrivi ESATTAMENTE questo codice, senza cambiarlo:

items = memory.search("release", kind="fact")
skill = memory.skill(items[0]["id"])
return skill["content"]

Restituisci solo il codice, non un file .py.
"""

    raw = create_llm(
        ModelConfig(
            provider="lmstudio",
            name=MODEL,
            host=HOST,
            timeout=180,
        )
    ).chat(
        [
            {
                "role": "system",
                "content": "Scrivi Hagar Flow, non Python completo.",
            },
            {"role": "user", "content": prompt},
        ]
    )

    result = runner.run(extract_code(raw))

    assert result.ok, {
        "error": result.error,
        "raw": raw,
        "search": memory.index.search("release", kind="fact"),
    }
    assert "commit di preparazione" in str(result.result)
