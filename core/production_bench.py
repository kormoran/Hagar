"""Misura una richiesta con un prompt vicino a quello reale di Hagar."""

from __future__ import annotations

import time

from typing import Any

from core.model_cards import utc_now


def _tool_lines(registry: Any) -> list[str]:

    if registry is None:
        return []

    lines = []

    for tool in registry.list_definitions():

        description = (
            getattr(tool, "short_description", None)
            or tool.description
        )
        lines.append(f"- {tool.name}: {description}")

    return lines


def benchmark_production(
    llm: Any,
    registry: Any = None,
    memory_text: str = "",
    attempts: int = 1,
    user_prompt: str = (
        "Riassumi in una frase cosa sai del progetto e indica "
        "quale tool useresti per cercare un file."
    ),
) -> dict[str, Any]:

    if attempts <= 0:
        raise ValueError("attempts must be positive")

    tools = _tool_lines(registry)
    system = "\n".join([
        "Sei Hagar, un agente locale.",
        "Rispondi in italiano, in modo conciso.",
        "Tool disponibili:",
        *tools,
        "",
        "Memoria:",
        memory_text or "(nessuna memoria)",
    ])
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    samples = []

    for _ in range(attempts):

        started = time.perf_counter()

        try:
            answer = llm.chat(messages)
            error = None
        except Exception as exc:
            answer = ""
            error = str(exc)

        samples.append({
            "duration_ms": round(
                (time.perf_counter() - started) * 1000,
                2,
            ),
            "answer_chars": len(answer),
            "error": error,
        })

    durations = sorted(
        sample["duration_ms"]
        for sample in samples
    )
    p50 = durations[len(durations) // 2]
    p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))]

    return {
        "tested_at": utc_now(),
        "attempts": attempts,
        "prompt_chars": len(system) + len(user_prompt),
        "system_chars": len(system),
        "tools": len(tools),
        "p50_ms": p50,
        "p95_ms": p95,
        "samples": samples,
    }
