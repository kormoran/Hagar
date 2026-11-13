"""Ritesta i modelli LM Studio con risultati anomali."""

from __future__ import annotations

import json
import os

from pathlib import Path
from typing import Any

from core.benchmark_runs import BenchmarkRunStore
from core.benchmark_suite import manifest as benchmark_manifest
from core.capabilities import verified_capabilities
from core.model_bench import benchmark_model
from core.model_cards import ModelCardStore, utc_now
from core.models import ModelConfig
from core.provider_models import discover_lmstudio
from core.quality_bench import benchmark_quality
from llm.factory import create_llm


HOST = "http://localhost:1234/v1"
OUTPUT = Path("Docs/BENCH_RETEST.md")
CARD_ROOT = Path("benchmarks/retest-cards")
RUN_ROOT = Path("benchmarks/retest-runs")
MODELS = [
    "lmstudio-community/meta-llama-3.1-8b-instruct",
    "microsoft/phi-4-reasoning-plus",
    "qwen3.5-35b-a3b",
]
OLD = {
    "lmstudio-community/meta-llama-3.1-8b-instruct": {
        "quality": 0.0534,
        "chat": "1/1",
    },
    "microsoft/phi-4-reasoning-plus": {
        "quality": 0.0,
        "chat": "1/1",
    },
    "qwen3.5-35b-a3b": {
        "quality": 0.2182,
        "chat": "1/1",
    },
}


def write_report(results: list[dict[str, Any]], current=None) -> None:

    lines = [
        "# Hagar benchmark — retest mirato",
        "",
        f"Aggiornato: `{utc_now()}`",
        f"Host: `{HOST}`",
        "",
        "## Confronto",
        "",
        "| Modello | Qualità vecchia | Qualità nuova | Chat | Capability | Errori |",
        "|---|---|---|---|---|---|",
    ]

    for item in results:
        quality = item.get("quality") or {}
        verified = item.get("capabilities_verified") or {}
        lines.append(
            "| "
            + " | ".join([
                f"`{item['model']}`",
                f"{item['old_quality']:.4f}",
                (
                    f"{quality.get('overall', 0):.4f}"
                    if quality
                    else "n/d"
                ),
                (
                    f"{item.get('chat_successes', 0)}/"
                    f"{item.get('chat_attempts', 0)}"
                    if item.get("text_ok")
                    else "fail"
                ),
                ", ".join(
                    name
                    for name, enabled in verified.items()
                    if enabled
                ) or "n/d",
                str(len(item.get("errors") or [])),
            ])
            + " |"
        )

    if current:
        lines.extend(["", f"In corso: `{current}`"])

    lines.extend(["", "## Dettaglio", ""])

    for item in results:
        lines.extend([
            f"### `{item['model']}`",
            "",
            f"- qualità precedente: `{item['old_quality']:.4f}`",
        ])

        if item.get("quality"):
            quality = item["quality"]
            lines.append(
                f"- qualità nuova: `{quality['overall']:.4f}`"
            )
            for task, value in quality.get("tasks", {}).items():
                lines.append(
                    f"  - {task}: `{value.get('mean', 0):.4f}`"
                )
        else:
            lines.append("- qualità nuova: non disponibile")

        if item.get("text_ok"):
            chat = item["benchmarks"]["chat"]
            lines.append(
                f"- chat: `{chat['successes']}/{chat['attempts']}`, "
                f"p50 `{chat['duration_ms']['p50']:.2f} ms`"
            )
        else:
            lines.append("- chat: fallita")

        if item.get("errors"):
            lines.append("- errori:")
            for error in item["errors"]:
                lines.append(f"  - `{error}`")

        lines.append("")

    temporary = OUTPUT.with_name(f".{OUTPUT.name}.tmp")
    temporary.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, OUTPUT)


def run() -> None:

    infos = {
        info.model: info
        for info in discover_lmstudio(HOST)
    }
    cards = ModelCardStore(CARD_ROOT)
    runs = BenchmarkRunStore(RUN_ROOT)
    suite_manifest = benchmark_manifest()
    results = []

    for model in MODELS:
        info = infos.get(model)
        item = {
            "model": model,
            "old_quality": OLD[model]["quality"],
            "quality": None,
            "text_ok": False,
            "benchmarks": None,
            "capabilities_verified": {},
            "errors": [],
        }
        results.append(item)
        write_report(results, current=model)

        if info is None:
            item["errors"].append("modello non presente in LM Studio")
            write_report(results, current=model)
            continue

        config = ModelConfig(
            provider="lmstudio",
            host=HOST,
            name=model,
            max_tokens=512,
            timeout=600,
            native_tools=True,
        )

        try:
            llm = create_llm(config)
        except Exception as exc:
            item["errors"].append(f"create_llm: {exc}")
            write_report(results, current=model)
            continue

        text_report = None
        quality_report = None

        try:
            text_report = benchmark_model(
                llm,
                attempts=1,
                tool_attempts=1,
            )
            item["text_ok"] = True
            item["benchmarks"] = text_report["benchmarks"]
            chat = text_report["benchmarks"]["chat"]
            item["chat_successes"] = chat["successes"]
            item["chat_attempts"] = chat["attempts"]
        except Exception as exc:
            item["errors"].append(f"text: {exc}")

        try:
            quality_report = benchmark_quality(llm, attempts=1)
            item["quality"] = quality_report
        except Exception as exc:
            item["errors"].append(f"quality: {exc}")

        if text_report is not None:
            combined = dict(text_report)
            combined["quality"] = quality_report
            item["capabilities_verified"] = verified_capabilities(
                combined
            )

            card = cards.load("lmstudio", model) or {}
            card.update(text_report)
            card["quality"] = quality_report
            card["capabilities_verified"] = item[
                "capabilities_verified"
            ]
            card["last_tested_at"] = text_report["tested_at"]

            try:
                cards.save(card)
            except Exception as exc:
                item["errors"].append(f"card: {exc}")

            try:
                run_report = dict(text_report)
                run_report["quality"] = quality_report
                run_report["suite_manifest"] = suite_manifest
                runs.save(run_report)
            except Exception as exc:
                item["errors"].append(f"run: {exc}")

        write_report(results, current=model)
        print(f"done {model}", flush=True)

    write_report(results)
    print(json.dumps(results, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    run()
