"""Confronta calling nativo e protocollo JSON testuale.

Stesso modello, stessi tool, stessi task: misura scelta del tool,
correttezza degli argomenti, latenza e riparazioni del protocollo
testuale.

Esempi:

    .\\.venv\\Scripts\\python.exe tools\\bench_native.py --provider ollama
    .\\.venv\\Scripts\\python.exe tools\\bench_native.py --provider deepseek
    .\\.venv\\Scripts\\python.exe tools\\bench_native.py --provider deepseek --mode native
"""

from __future__ import annotations

import argparse
import json
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import ConfigError
from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.filesystem_tools import FileSystemToolProvider
from core.models import ModelConfig
from core.tool_registry import ToolRegistry
from llm.base import NativeToolsUnavailable
from llm.factory import create_llm

DEFAULT_MODELS = {
    "ollama": "llama3.1:latest",
    "deepseek": "deepseek-flash",
    "claude": "claude-3-5-haiku-latest",
    "gemini": "gemini-2.0-flash",
}


@dataclass(frozen=True, slots=True)
class Task:
    name: str
    prompt: str
    tool: str | None
    arguments: dict[str, Any]


@dataclass(slots=True)
class Outcome:
    task: str
    mode: str
    status: str
    tool: str | None
    arguments: dict[str, Any]
    seconds: float
    repairs: int
    detail: str


TASKS = (
    Task(
        "read_file",
        "Leggi il file nota.txt.",
        "filesystem.read_file",
        {"path": "nota.txt"},
    ),
    Task(
        "write_file",
        "Scrivi 'ciao' nel file esistente saluto.txt.",
        "filesystem.write_file",
        {"path": "saluto.txt", "content": "ciao"},
    ),
    Task(
        "create_file",
        "Crea un nuovo file todo.md con il contenuto "
        "'- fare la spesa'.",
        "filesystem.create_file",
        {"path": "todo.md", "content": "- fare la spesa"},
    ),
    Task(
        "mkdir",
        "Crea la cartella output.",
        "filesystem.mkdir",
        {"path": "output"},
    ),
    Task(
        "stat",
        "Dimmi la dimensione del file nota.txt.",
        "filesystem.stat",
        {"path": "nota.txt"},
    ),
    Task(
        "free_space",
        "Quanto spazio libero c'è?",
        "filesystem.free_space",
        {},
    ),
    Task(
        "chdir",
        "Entra nella cartella docs.",
        "filesystem.chdir",
        {"path": "docs"},
    ),
    Task(
        "delete_file",
        "Elimina il file vecchio.txt.",
        "filesystem.delete_file",
        {"path": "vecchio.txt"},
    ),
    Task(
        "no_tool",
        "Quanto fa 2 + 2? Rispondi solo con il numero.",
        None,
        {},
    ),
)


class Recorder:
    """Audit minimo per contare le riparazioni del protocollo testuale."""

    include_outputs = True

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, event: str, **fields: Any) -> None:
        self.entries.append({"event": event, **fields})


def normalize_path(value: Any) -> str:
    return (
        str(value)
        .replace("\\", "/")
        .lstrip("./")
        .rstrip("/")
    )


def normalize_text(value: Any) -> str:
    return (
        str(value)
        .strip()
        .strip('"')
        .strip("'")
        .strip()
    )


def arguments_match(
    actual: dict[str, Any],
    expected: dict[str, Any],
) -> bool:

    for key, wanted in expected.items():

        if key == "path":

            if normalize_path(
                actual.get("path", "")
            ) != normalize_path(wanted):
                return False

        elif key == "content":

            if normalize_text(
                actual.get("content", "")
            ) != normalize_text(wanted):
                return False

        elif str(actual.get(key, "")).strip() != str(
            wanted
        ).strip():

            return False

    return True


def evaluate(
    task: Task,
    call,
    calls_count: int,
) -> tuple[str, str]:

    if task.tool is None:

        if call is None or not call.tool:
            return "ok", "nessun tool"

        return (
            "unexpected_tool",
            f"{call.tool} {call.arguments}",
        )

    if call is None or not call.tool:
        return "no_tool", "nessun tool"

    if call.tool != task.tool:
        return (
            "wrong_tool",
            f"{call.tool} {call.arguments}",
        )

    if not arguments_match(
        call.arguments,
        task.arguments,
    ):
        return (
            "wrong_args",
            f"{call.tool} {call.arguments}",
        )

    extra = (
        f", +{calls_count - 1} chiamate"
        if calls_count > 1
        else ""
    )

    return "ok", extra


def run_one(
    client,
    registry: ToolRegistry,
    recorder: Recorder,
    task: Task,
    mode: str,
) -> Outcome:

    recorder.entries.clear()

    started = time.perf_counter()

    try:

        if mode == "native":

            reply = client.native_step(
                [
                    {
                        "role": "user",
                        "content": task.prompt,
                    }
                ],
                registry,
            )

            calls_count = len(reply.tool_calls)

            call = (
                reply.tool_calls[0]
                if reply.tool_calls
                else None
            )

        else:

            call = client.request_tool_call(
                [
                    {
                        "role": "user",
                        "content": task.prompt,
                    }
                ],
                registry,
            )

            calls_count = 1 if call.tool else 0

    except NativeToolsUnavailable as exc:

        return Outcome(
            task.name,
            mode,
            "unavailable",
            None,
            {},
            time.perf_counter() - started,
            0,
            str(exc),
        )

    except Exception as exc:

        return Outcome(
            task.name,
            mode,
            "error",
            None,
            {},
            time.perf_counter() - started,
            0,
            f"{type(exc).__name__}: {exc}",
        )

    seconds = time.perf_counter() - started

    status, detail = evaluate(
        task,
        call,
        calls_count,
    )

    repairs = sum(
        1
        for entry in recorder.entries
        if entry["event"] == "llm.repaired"
    )

    return Outcome(
        task.name,
        mode,
        status,
        call.tool if call else None,
        call.arguments if call else {},
        seconds,
        repairs,
        detail,
    )


def describe(outcome: Outcome) -> str:

    seconds = f"{outcome.seconds:.2f}s"

    if outcome.status == "ok":

        detail = (
            f" {outcome.detail}"
            if outcome.detail and not outcome.detail.startswith(",")
            else ""
        )

        repairs = (
            f", {outcome.repairs} repair"
            if outcome.repairs
            else ""
        )

        return f"ok{detail} {seconds}{repairs}"

    if outcome.status == "unavailable":
        return f"nativo non disponibile ({seconds})"

    return (
        f"{outcome.status}: "
        f"{outcome.detail[:70]} ({seconds})"
    )


def summary(outcomes: list[Outcome]) -> dict[str, Any]:

    total = len(outcomes)

    ok = sum(
        1
        for outcome in outcomes
        if outcome.status == "ok"
    )

    return {
        "total": total,
        "ok": ok,
        "accuracy": (
            round(ok / total, 3)
            if total
            else 0.0
        ),
        "seconds_avg": round(
            sum(
                outcome.seconds
                for outcome in outcomes
            )
            / total,
            3,
        )
        if total
        else 0.0,
        "repairs": sum(
            outcome.repairs
            for outcome in outcomes
        ),
        "errors": sum(
            1
            for outcome in outcomes
            if outcome.status in {"error", "unavailable"}
        ),
    }


def build_registry() -> ToolRegistry:
    """
    Registra i tool filesystem reali.

    I handler non vengono eseguiti: al benchmark interessa la scelta del
    tool e degli argomenti, non il filesystem.
    """

    workspace = Path.cwd()

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

    return registry


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Confronta calling nativo e "
            "protocollo JSON testuale."
        )
    )

    parser.add_argument(
        "--provider",
        default="ollama",
        choices=sorted(DEFAULT_MODELS),
    )

    parser.add_argument(
        "--model",
        default=None,
        help="default per provider",
    )

    parser.add_argument(
        "--host",
        default=None,
        help="base URL opzionale (Ollama o proxy)",
    )

    parser.add_argument(
        "--mode",
        default="both",
        choices=["native", "text", "both"],
    )

    parser.add_argument(
        "--tasks",
        default=None,
        help="nomi separati da virgola",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="output JSON",
    )

    args = parser.parse_args()

    model = (
        args.model
        or DEFAULT_MODELS[args.provider]
    )

    recorder = Recorder()

    try:

        client = create_llm(
            ModelConfig(
                provider=args.provider,
                name=model,
                host=args.host,
            ),
            audit=recorder,
        )

    except ConfigError as exc:

        print(f"Errore di configurazione: {exc}")
        return 1

    registry = build_registry()

    selected = list(TASKS)

    if args.tasks:

        wanted = {
            name.strip()
            for name in args.tasks.split(",")
            if name.strip()
        }

        selected = [
            task
            for task in TASKS
            if task.name in wanted
        ]

        if not selected:

            print("Nessun task corrispondente.")
            return 1

    modes = (
        ["native", "text"]
        if args.mode == "both"
        else [args.mode]
    )

    print(
        f"{args.provider} / {model} — "
        f"{len(selected)} task, "
        f"modalità: {args.mode}"
    )

    results: list[Outcome] = []

    for task in selected:

        row = {}

        for mode in modes:

            outcome = run_one(
                client,
                registry,
                recorder,
                task,
                mode,
            )

            results.append(outcome)

            row[mode] = describe(outcome)

        print(f"\n{task.name}")

        for mode in modes:

            print(f"  {mode:<7} {row[mode]}")

    print("\nRiepilogo")

    payload: dict[str, Any] = {
        "provider": args.provider,
        "model": model,
        "tasks": [
            {
                "name": task.name,
                "tool": task.tool,
                "arguments": task.arguments,
            }
            for task in selected
        ],
        "modes": {},
    }

    for mode in modes:

        outcomes = [
            outcome
            for outcome in results
            if outcome.mode == mode
        ]

        stats = summary(outcomes)

        payload["modes"][mode] = stats

        print(
            f"  {mode:<7} "
            f"{stats['ok']}/{stats['total']} ok, "
            f"media {stats['seconds_avg']:.2f}s, "
            f"{stats['repairs']} riparazioni, "
            f"{stats['errors']} errori"
        )

    if args.json:

        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
