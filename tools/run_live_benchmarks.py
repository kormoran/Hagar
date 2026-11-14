"""Esegue tutti i benchmark sui modelli LM Studio, uno alla volta."""

from __future__ import annotations

import json
import os
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from core.benchmark_runs import BenchmarkRunStore
from core.benchmark_suite import manifest as benchmark_manifest
from core.capabilities import verified_capabilities
from core.model_bench import benchmark_model
from core.model_cards import ModelCardStore, utc_now
from core.quality_bench import benchmark_quality
from core.vision_bench import benchmark_vision
from core.models import ModelConfig
from llm.factory import create_llm


HOST = "http://localhost:1234/v1"
META_URL = "http://localhost:1234/api/v0/models"
OUTPUT = Path("Docs/BENCH_TESTS.md")
CARD_ROOT = Path("benchmarks/live-cards")
RUN_ROOT = Path("benchmarks/live-runs")
ATTEMPTS = max(1, int(os.environ.get("HAGAR_BENCH_ATTEMPTS", "1")))


def write_document(
    results: list[dict[str, Any]],
    *,
    started: str,
    current: str | None = None,
    finished: str | None = None,
) -> None:

    lines = [
        "# Hagar benchmark live — LM Studio",
        "",
        f"Avvio: `{started}`",
        f"Aggiornato: `{utc_now()}`",
        f"Host: `{HOST}`",
        "",
    ]

    if finished:
        lines.append(f"Completato: `{finished}`")
    elif current:
        lines.append(f"In corso: `{current}`")
    else:
        lines.append("Stato: preparazione")

    lines.extend([
        "",
        "## Politica",
        "",
        "```text",
        "llm/vlm: benchmark testo + qualità",
        "vlm: anche benchmark vision",
        "embeddings: esclusi",
        "un modello alla volta",
        "errori registrati, si continua",
        f"ripetizioni per test: {ATTEMPTS}",
        "```",
        "",
        "## Riepilogo",
        "",
        "| Modello | Tipo | Capabilities | Qualità | Vision | Errori |",
        "|---|---|---|---|---|---|",
    ])

    for item in results:
        text = item.get("text") or {}
        quality = item.get("quality") or {}
        vision = item.get("vision") or {}
        errors = item.get("errors") or []
        verified = item.get("capabilities_verified") or {}

        lines.append(
            "| "
            + " | ".join([
                f"`{item['id']}`",
                item.get("type", ""),
                ", ".join(
                    name
                    for name, enabled in verified.items()
                    if enabled
                ) or "n/d",
                (
                    f"{quality.get('overall', 0):.4f}"
                    if quality
                    else "n/d"
                ),
                (
                    f"{vision.get('overall', 0):.4f}"
                    if vision
                    else "n/d"
                ),
                str(len(errors)),
            ])
            + " |"
        )

    lines.extend(["", "## Dettaglio", ""])

    for item in results:

        lines.extend([
            f"### `{item['id']}`",
            "",
            f"- tipo: `{item.get('type', 'unknown')}`",
            f"- quantizzazione: `{item.get('quantization', 'unknown')}`",
            f"- contesto max: `{item.get('max_context', 'unknown')}`",
        ])

        verified = item.get("capabilities_verified") or {}

        if verified:
            lines.append(
                "- capability verificate: "
                + ", ".join(
                    name
                    for name, enabled in verified.items()
                    if enabled
                )
            )

        text = item.get("text") or {}

        if text.get("ok"):
            chat = text["benchmarks"]["chat"]
            structured = text["benchmarks"]["structured"]
            tools = text["benchmarks"]["tool_call"]
            lines.extend([
                (
                    "- testo: "
                    f"chat {chat['successes']}/{chat['attempts']}, "
                    f"p50 {chat['duration_ms']['p50']} ms, "
                    f"JSON {structured['valid_json']}/"
                    f"{structured['attempts']}, "
                    f"tool {tools['successes']}/{tools['attempts']}"
                ),
            ])
        elif item.get("text_attempted"):
            lines.append("- testo: fallito")

        quality = item.get("quality") or {}

        if quality:
            lines.append(
                "- qualità: "
                f"{quality.get('overall', 0):.4f}"
            )

            for task, value in quality.get("tasks", {}).items():
                lines.append(
                    f"  - {task}: {value.get('mean', 0):.4f}"
                )

        vision = item.get("vision") or {}

        if vision:
            lines.append(
                "- vision: "
                f"{vision.get('overall', 0):.4f}"
            )

            for case in vision.get("tasks", {}).get(
                "vision",
                {},
            ).get("case_results", []):
                lines.append(
                    f"  - {case.get('name')}: "
                    f"{case.get('mean', 0):.4f}"
                )

        if item.get("errors"):
            lines.append("- errori:")

            for error in item["errors"]:
                lines.append(f"  - `{error}`")

        lines.append("")

    lines.extend([
        "## File",
        "",
        "```text",
        "schede: benchmarks/live-cards/",
        "run:    benchmarks/live-runs/",
        "```",
        "",
    ])

    temporary = OUTPUT.with_name(f".{OUTPUT.name}.tmp")
    temporary.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, OUTPUT)


def load_models() -> list[dict[str, Any]]:

    response = requests.get(META_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    models = payload.get("data")

    if not isinstance(models, list):
        raise RuntimeError("LM Studio metadata without data")

    return sorted(
        (
            model
            for model in models
            if isinstance(model, dict)
            and model.get("id")
        ),
        key=lambda model: (
            str(model.get("type")),
            str(model.get("id")),
        ),
    )


def run() -> None:

    started = utc_now()
    models = load_models()
    skip = {
        item.strip()
        for item in os.environ.get("HAGAR_BENCH_SKIP", "").split(",")
        if item.strip()
    }
    cards = ModelCardStore(CARD_ROOT)
    runs = BenchmarkRunStore(RUN_ROOT)
    suite_manifest = benchmark_manifest()
    results: list[dict[str, Any]] = []
    known = {str(model["id"]): model for model in models}

    for model in models:
        model_id = str(model["id"])
        model_type = str(model.get("type") or "unknown")

        item = {
            "id": model_id,
            "type": model_type,
            "quantization": model.get("quantization"),
            "max_context": model.get("max_context_length"),
            "text": None,
            "quality": None,
            "vision": None,
            "errors": [],
            "text_attempted": model_type in {"llm", "vlm"},
        }
        results.append(item)

        completed = cards.load("lmstudio", model_id)

        if (
            completed
            and completed.get("benchmarks")
            and completed.get("quality")
            and (
                model_type != "vlm"
                or completed.get("vision")
            )
        ):
            item["text"] = {
                "ok": True,
                "benchmarks": completed["benchmarks"],
                "tested_at": completed.get("tested_at"),
            }
            item["quality"] = completed.get("quality")
            item["vision"] = completed.get("vision")
            item["capabilities_verified"] = (
                completed.get("capabilities_verified")
                or verified_capabilities(completed)
            )
            write_document(
                results,
                started=started,
                current=f"già completato {model_id}",
            )
            print(f"skip {model_id}: already completed", flush=True)
            continue

        if model_id in skip:
            item["errors"].append("saltato: bloccato nella run precedente")
            write_document(
                results,
                started=started,
                current=f"salto {model_id}",
            )
            print(f"skip {model_id}: configured skip", flush=True)
            continue

        if model_type == "embeddings":
            item["errors"].append("embedding model: non chat")
            write_document(
                results,
                started=started,
                current=f"salto {model_id}",
            )
            print(f"skip {model_id}: embeddings", flush=True)
            continue

        if model_type not in {"llm", "vlm"}:
            item["errors"].append(
                f"unsupported model type: {model_type}"
            )
            write_document(
                results,
                started=started,
                current=f"salto {model_id}",
            )
            continue

        write_document(
            results,
            started=started,
            current=model_id,
        )
        print(f"start {model_id} ({model_type})", flush=True)

        config = ModelConfig(
            provider="lmstudio",
            host=HOST,
            name=model_id,
            max_tokens=512,
            timeout=300,
            native_tools=True,
        )

        try:
            llm = create_llm(config)
        except Exception as exc:
            item["errors"].append(
                f"create_llm: {exc}"
            )
            write_document(
                results,
                started=started,
                current=model_id,
            )
            continue

        text_report = None

        try:
            text_report = benchmark_model(
                llm,
                attempts=ATTEMPTS,
                tool_attempts=ATTEMPTS,
            )
            item["text"] = {
                "ok": True,
                "benchmarks": text_report["benchmarks"],
                "tested_at": text_report["tested_at"],
            }
        except Exception as exc:
            item["errors"].append(f"text: {exc}")

        quality_report = None

        try:
            quality_report = benchmark_quality(
                llm,
                attempts=ATTEMPTS,
            )
            item["quality"] = quality_report
        except Exception as exc:
            item["errors"].append(f"quality: {exc}")

        if text_report is not None:

            combined = dict(text_report)
            combined["quality"] = quality_report
            item["capabilities_verified"] = verified_capabilities(
                combined
            )

            card = cards.load("lmstudio", model_id) or {}
            card.update(text_report)
            card["quality"] = quality_report
            card["capabilities_verified"] = item[
                "capabilities_verified"
            ]
            card["last_tested_at"] = text_report["tested_at"]

            if model_type != "vlm":
                card["vision"] = {
                    "not_applicable": True,
                    "reason": "model type does not support vision",
                }

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

        write_document(
            results,
            started=started,
            current=model_id,
        )
        print(f"text done {model_id}", flush=True)

        if model_type == "vlm":

            vision_report = None

            try:
                vision_report = benchmark_vision(
                    llm,
                    attempts=ATTEMPTS,
                )
                item["vision"] = vision_report
            except Exception as exc:
                item["errors"].append(f"vision: {exc}")

            if vision_report is not None:

                card = cards.load("lmstudio", model_id) or {}
                card["vision"] = vision_report
                card["capabilities_verified"] = (
                    verified_capabilities(card)
                )
                item["capabilities_verified"] = card[
                    "capabilities_verified"
                ]
                card["last_tested_at"] = (
                    vision_report["tested_at"]
                )

                try:
                    cards.save(card)
                except Exception as exc:
                    item["errors"].append(f"card vision: {exc}")

                try:
                    run_report = {
                        "provider": "lmstudio",
                        "model": model_id,
                        "tested_at": vision_report["tested_at"],
                        "vision": vision_report,
                        "suite_manifest": suite_manifest,
                    }
                    runs.save(run_report)
                except Exception as exc:
                    item["errors"].append(f"run vision: {exc}")

            write_document(
                results,
                started=started,
                current=model_id,
            )
            print(f"vision done {model_id}", flush=True)

    write_document(
        results,
        started=started,
        finished=utc_now(),
    )
    print("complete", flush=True)


if __name__ == "__main__":
    run()
