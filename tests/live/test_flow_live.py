"""Test live di Hagar Flow e delle box con LM Studio.

Eseguiti solo con ``pytest --live``.
"""

from __future__ import annotations

import os
import re

import pytest

from core.boxes import BoxRunner
from core.flow import FlowRunner, LANGUAGE_CARD
from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.models import (
    BoxesConfig,
    FlowConfig,
    ModelConfig,
)
from core.tool_registry import ToolRegistry
from llm.factory import create_llm
from local_tools.flow_primitives import FlowPrimitiveProvider

pytestmark = pytest.mark.live

MODEL = os.environ.get(
    "HAGAR_LIVE_LMSTUDIO_MODEL",
    "qwen2.5-coder-7b-instruct",
)
HOST = os.environ.get(
    "HAGAR_LIVE_LMSTUDIO_HOST",
    "http://localhost:1234/v1",
)


def make_llm():
    return create_llm(
        ModelConfig(
            provider="lmstudio",
            name=MODEL,
            host=HOST,
            timeout=180,
        )
    )


def make_sandbox(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

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
    return sandbox, workspace


def extract_code(text: str) -> str:
    match = re.search(
        r"```(?:python)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else text


def test_lmstudio_generates_flow(tmp_path):
    sandbox, workspace = make_sandbox(tmp_path)
    (workspace / "a.py").write_text(
        "x = 1\n",
        encoding="utf-8",
    )

    registry = ToolRegistry()
    provider = FlowPrimitiveProvider(sandbox)
    provider.register_tools(registry)
    runner = FlowRunner(
        registry,
        FlowConfig(enabled=True),
        provider.primitives,
    )

    prompt = f"""{LANGUAGE_CARD}

Primitive:
fs.read(path) -> str
fs.write(path, text)
fs.list(path=".") -> list[str]
fs.exists(path) -> bool

Scrivi SOLO codice Hagar Flow, senza spiegazioni e senza markdown,
che legge /home/ai/root/a.py e restituisce il contenuto con return.
"""

    raw = make_llm().chat(
        [
            {
                "role": "system",
                "content": "Scrivi Hagar Flow, non Python completo.",
            },
            {"role": "user", "content": prompt},
        ]
    )
    result = runner.run(extract_code(raw))

    assert result.ok, result.error
    assert "x = 1" in result.result


def test_lmstudio_box_summarize(tmp_path):
    sandbox, workspace = make_sandbox(tmp_path)
    (workspace / "doc.txt").write_text(
        "Hagar e un harness per agenti. Supporta tool, memoria SQLite "
        "e policy. Le boxed transform riassumono documenti. Flow e un "
        "DSL ristretto.\n",
        encoding="utf-8",
    )

    runner = BoxRunner(
        make_llm(),
        sandbox,
        BoxesConfig(enabled=True),
    )
    result = runner.run(
        "summarize",
        "doc.txt",
        "summary.txt",
        {"style": "short"},
    )

    output = (workspace / "summary.txt").read_text(
        encoding="utf-8"
    )

    assert result["calls"] == 1
    assert output.strip()
    assert output.strip() != (workspace / "doc.txt").read_text(
        encoding="utf-8"
    ).strip()
