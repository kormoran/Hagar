"""Esegue i benchmark P1 su un modello 8B locale."""

from __future__ import annotations

import json
import os

from pathlib import Path

from core.coding_bench import benchmark_coding
from core.config import ConfigLoader
from core.memory_bench import benchmark_memory
from core.model_bench import benchmark_model
from core.models import ModelConfig
from core.production_bench import benchmark_production
from core.quality_bench import benchmark_quality
from hagar import build_harness
from llm.factory import create_llm


MODEL = os.environ.get(
    "HAGAR_P1_MODEL",
    "lmstudio-community/meta-llama-3.1-8b-instruct",
)
HOST = "http://localhost:1234/v1"
OUTPUT = Path(
    os.environ.get("HAGAR_P1_OUTPUT", "Docs/BENCH_P1_8B.md")
)


def main() -> None:

    config = ConfigLoader.load("hagar.yaml")
    harness = build_harness(config)
    llm = create_llm(
        ModelConfig(
            provider="lmstudio",
            host=HOST,
            name=MODEL,
            timeout=600,
            native_tools=True,
        )
    )

    text = benchmark_model(llm, attempts=1, tool_attempts=1)
    quality = benchmark_quality(llm, attempts=1)
    memory = benchmark_memory(llm, attempts=1)
    coding = benchmark_coding(llm, attempts=1)
    production = benchmark_production(
        llm,
        registry=harness.agent.tools,
        attempts=1,
    )

    quality["tasks"]["memory"] = memory["tasks"]["memory"]
    quality["tasks"]["coding_exec"] = coding["tasks"]["coding_exec"]

    payload = {
        "model": MODEL,
        "text": text,
        "quality": quality,
        "memory": memory,
        "coding": coding,
        "production": production,
    }
    OUTPUT.write_text(
        "# Hagar benchmark P1 — modello 8B\n\n"
        f"Modello: `{MODEL}`\n\n"
        f"- chat: {text['benchmarks']['chat']['successes']}/"
        f"{text['benchmarks']['chat']['attempts']}\n"
        f"- JSON valido: {text['benchmarks']['structured']['valid_json']}/"
        f"{text['benchmarks']['structured']['attempts']}\n"
        f"- JSON field F1: {text['benchmarks']['structured']['field_f1']}\n"
        f"- tool: {text['benchmarks']['tool_call']['successes']}/"
        f"{text['benchmarks']['tool_call']['attempts']}\n"
        f"- tool args: {text['benchmarks']['tool_call']['argument_accuracy']}\n"
        f"- qualità: {quality['overall']:.4f}\n"
        f"- memoria: {memory['overall']:.4f}\n"
        f"- coding eseguibile: {coding['overall']:.4f}\n"
        f"- production p50/p95: {production['p50_ms']} / "
        f"{production['p95_ms']} ms\n"
        f"- tool nel prompt production: {production['tools']}\n\n"
        "```json\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
