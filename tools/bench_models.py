"""Confronto rapido dei modelli Ollama sul protocollo dei tool.

Esegue alcune attivita' rappresentative (lettura, metadati, creazione,
chat senza tool) contro una sandbox temporanea e stampa un risultato
JSON per ogni combinazione modello/attivita'.

Uso:

    python tools/bench_models.py
    python tools/bench_models.py qwen3:8b llama3.1:latest

Richiede un server Ollama attivo e i modelli gia' scaricati.
"""

from __future__ import annotations

import json
import shutil
import sys
import time

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import hagar  # noqa: E402

from core.audit import read_entries  # noqa: E402
from core.config import ConfigLoader  # noqa: E402
from core.models import (  # noqa: E402
    FileSystemConfig,
    ModelConfig,
    PermissionConfig,
)

WORK = PROJECT_ROOT / ".bench"
WORKSPACE = WORK / "ws"
AUDIT = WORK / "audit.jsonl"

DEFAULT_MODELS = [
    "qwen3:8b",
    "llama3.1:latest",
    "hermes3:8b",
    "gemma:latest",
]

MAX_TOOL_CALLS = 4

TASKS = [
    (
        "read",
        "Leggi il file nota.txt e dimmi in una frase cosa contiene.",
    ),
    (
        "stat",
        "Quanto e' grande in byte il file nota.txt? "
        "Usa gli strumenti disponibili.",
    ),
    (
        "create",
        "Crea un file chiamato nuovo.txt che contenga "
        "esattamente il testo: ciao",
    ),
    (
        "chat",
        "Ciao, chi sei? Rispondi in una frase.",
    ),
]


def prepare() -> None:

    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)

    WORKSPACE.mkdir(parents=True)

    (WORKSPACE / "nota.txt").write_text(
        "Il cielo e' azzurro e il mare e' blu.\n",
        encoding="utf-8",
    )


def run_task(
    harness,
    task: str,
    question: str,
) -> dict:
    """Esegue un turno e ne riassume gli eventi di audit."""

    before = len(read_entries(AUDIT))

    started = time.perf_counter()

    try:

        answer = harness.agent.ask(question)
        error = None

    except Exception as exc:

        answer = ""
        error = repr(exc)

    elapsed = time.perf_counter() - started

    entries = read_entries(AUDIT)[before:]

    result = {
        "task": task,
        "seconds": round(elapsed, 1),
        "repaired": any(
            entry["event"] == "llm.protocol_error"
            for entry in entries
        ),
        "calls": [
            {
                "tool": entry["tool"],
                "args": entry["arguments"],
            }
            for entry in entries
            if entry["event"] == "tool.call"
        ],
        "results": [
            entry["success"]
            for entry in entries
            if entry["event"] == "tool.result"
        ],
        "created": None,
        "answer": (
            answer if error is None else error
        )[:160].replace("\n", " "),
    }

    if task == "create":

        target = WORKSPACE / "nuovo.txt"

        result["created"] = (
            target.exists()
            and target.read_text(
                encoding="utf-8"
            ).strip() == "ciao"
        )

    return result


def main() -> None:

    models = sys.argv[1:] or DEFAULT_MODELS

    if AUDIT.exists():
        AUDIT.unlink()

    for model in models:

        prepare()

        config = ConfigLoader.load(hagar.CONFIG_PATH)

        config.model = ModelConfig(
            provider="ollama",
            host="http://localhost:11434",
            name=model,
        )

        config.filesystem = FileSystemConfig(
            allowed=[WORKSPACE]
        )

        config.permissions = PermissionConfig(
            read=True,
            write=True,
            shell=False,
        )

        config.audit.path = AUDIT
        config.audit.max_field_chars = 500

        harness = hagar.build_harness(config)

        harness.agent.max_tool_calls = MAX_TOOL_CALLS

        for task, question in TASKS:

            result = run_task(
                harness,
                task,
                question,
            )

            result["model"] = model

            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
