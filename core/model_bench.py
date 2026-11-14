"""Benchmark minimi per alimentare le schede tecniche del broker."""

from __future__ import annotations

import json
import math
import statistics
import time

from typing import Any

from core.hardware import detect_hardware
from core.model_cards import utc_now
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


class BenchmarkError(RuntimeError):
    pass


def benchmark_model(
    llm,
    attempts: int = 3,
    tool_attempts: int = 2,
    skip_suites: set[str] | None = None,
) -> dict[str, Any]:
    """Misura chat, JSON strutturato e tool calling.

    Non prova a saturare il modello: produce dati comparabili e onesti
    per il broker, con tentativi ripetuti e latenza a freddo/caldo.
    """

    attempts = max(1, int(attempts))
    tool_attempts = max(0, int(tool_attempts))
    skip = set(skip_suites or ())

    chat = (
        _not_applicable("chat")
        if "chat" in skip
        else _benchmark_chat(llm, attempts)
    )
    structured = (
        _not_applicable("structured")
        if "structured" in skip
        else _benchmark_structured(llm, attempts)
    )
    tools = (
        _not_applicable("tool_call")
        if "tool_call" in skip
        else _benchmark_tools(llm, tool_attempts)
    )

    if (
        not chat.get("not_applicable")
        and chat.get("successes", 0) == 0
        and (
            structured.get("valid_json", 0) > 0
            or tools.get("successes", 0) > 0
        )
    ):
        chat["not_applicable"] = True
        chat["reason"] = (
            "model refuses free chat but passes structured/tool tasks"
        )

    return {
        "tested_at": utc_now(),
        "provider": getattr(llm, "provider", "unknown"),
        "model": getattr(llm, "model", "unknown"),
        "hardware": detect_hardware(),
        "capabilities": {
            "chat": chat["successes"] > 0,
            "structured_json": structured["valid_json"] > 0,
            "tool_calling": tools["successes"] > 0,
            "native_tools": bool(
                getattr(llm, "supports_native_tools", False)
            ),
        },
        "benchmarks": {
            "chat": chat,
            "structured": structured,
            "tool_call": tools,
        },
    }


def _benchmark_chat(llm, attempts: int) -> dict[str, Any]:

    durations = []
    output_tokens = 0
    successes = 0
    errors = []

    for _ in range(attempts):

        started = time.perf_counter()
        try:
            text = llm.chat([
                {
                    "role": "user",
                    "content": "Rispondi esattamente con la parola OK.",
                }
            ])
            success = isinstance(text, str) and bool(text.strip())
        except Exception as exc:
            success = False
            errors.append(str(exc))

        duration = (time.perf_counter() - started) * 1000
        durations.append(duration)

        if success:
            successes += 1

        usage = getattr(llm, "last_usage", None)
        if usage is not None:
            output_tokens += int(
                getattr(usage, "output_tokens", 0)
            )

    total_seconds = sum(durations) / 1000
    return {
        "attempts": attempts,
        "successes": successes,
        "errors": errors,
        "duration_ms": _stats(durations),
        "output_tokens_per_second": (
            round(output_tokens / total_seconds, 3)
            if total_seconds > 0
            else None
        ),
    }


def _benchmark_structured(llm, attempts: int) -> dict[str, Any]:

    durations = []
    valid_json = 0
    valid_choice = 0
    schema_valid = 0
    field_scores = []
    errors = []

    expected_fields = {
        "name": str,
        "age": int,
        "active": bool,
        "choice": str,
        "probabilities": dict,
    }

    for _ in range(attempts):

        started = time.perf_counter()
        try:
            text = llm.chat([
                {
                    "role": "system",
                    "content": (
                        "Rispondi solo con JSON valido, senza markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        'Rispondi con {"name":"Ada","age":36,'
                        '"active":true,"choice":"yes",'
                        '"probabilities":{"yes":0.9,"no":0.1}}'
                    ),
                },
            ])
            payload = _json_object(text)
            valid_json += 1

            if (
                payload.get("choice") in {"yes", "no"}
                and isinstance(payload.get("probabilities"), dict)
            ):
                valid_choice += 1

            matched = sum(
                1
                for key, expected_type in expected_fields.items()
                if key in payload
                and isinstance(payload[key], expected_type)
                and not (
                    expected_type is int
                    and isinstance(payload[key], bool)
                )
            )
            precision = matched / max(len(payload), 1)
            recall = matched / len(expected_fields)
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision + recall > 0
                else 0.0
            )
            field_scores.append(f1)

            if matched == len(expected_fields):
                schema_valid += 1
        except Exception as exc:
            errors.append(str(exc))
            field_scores.append(0.0)

        durations.append((time.perf_counter() - started) * 1000)

    return {
        "attempts": attempts,
        "valid_json": valid_json,
        "valid_choice": valid_choice,
        "schema_valid": schema_valid,
        "field_f1": round(
            sum(field_scores) / len(field_scores),
            4,
        ) if field_scores else 0.0,
        "errors": errors,
        "duration_ms": _stats(durations),
    }


def _benchmark_tools(llm, attempts: int) -> dict[str, Any]:

    if attempts <= 0:
        return {
            "attempts": 0,
            "successes": 0,
            "errors": [],
            "duration_ms": _stats([]),
        }

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="bench.echo",
            description="Echo a benchmark string.",
            category="benchmark",
            capabilities=Capability.COMPUTE,
            parameters=[
                ToolParameter(
                    name="text",
                    param_type="string",
                    description="Text to echo.",
                )
            ],
            handler=lambda text="": text,
        )
    )

    distractors = (
        ("bench.add", "Add two numbers.", "a"),
        ("bench.weather", "Weather for a city.", "city"),
        ("bench.search", "Search local files.", "query"),
        ("bench.translate", "Translate text.", "text"),
        ("bench.summarize", "Summarize text.", "text"),
        ("bench.clock", "Return the time.", None),
        ("bench.remember", "Store a note.", "note"),
        ("bench.unrelated", "Unrelated operation.", "value"),
    )

    for name, description, parameter in distractors:

        registry.register(
            ToolDefinition(
                name=name,
                description=description,
                category="benchmark",
                capabilities=Capability.COMPUTE,
                parameters=(
                    [
                        ToolParameter(
                            name=parameter,
                            param_type="string",
                            description="Parameter.",
                        )
                    ]
                    if parameter
                    else []
                ),
                handler=lambda **kwargs: "ok",
            )
        )

    durations = []
    successes = 0
    argument_matches = 0
    errors = []

    for _ in range(attempts):

        started = time.perf_counter()
        try:
            call = llm.request_tool_call(
                [
                    {
                        "role": "user",
                        "content": (
                            "Chiama il tool bench.echo con "
                            'text="ok". Non rispondere in prosa.'
                        ),
                    }
                ],
                registry,
            )
            tool = getattr(call, "tool", None)
            arguments = getattr(call, "arguments", {})

            if tool == "bench.echo":
                successes += 1

            if (
                tool == "bench.echo"
                and isinstance(arguments, dict)
                and arguments.get("text") == "ok"
            ):
                argument_matches += 1
            else:
                errors.append(
                    f"unexpected tool/arguments: {call!r}"
                )
        except Exception as exc:
            errors.append(str(exc))

        durations.append((time.perf_counter() - started) * 1000)

    return {
        "attempts": attempts,
        "successes": successes,
        "selection_accuracy": round(successes / attempts, 4),
        "argument_matches": argument_matches,
        "argument_accuracy": round(
            argument_matches / attempts,
            4,
        ),
        "errors": errors,
        "duration_ms": _stats(durations),
    }


def _not_applicable(suite: str) -> dict[str, Any]:

    return {
        "attempts": 0,
        "successes": 0,
        "selection_accuracy": 0.0,
        "argument_matches": 0,
        "argument_accuracy": 0.0,
        "valid_json": 0,
        "valid_choice": 0,
        "schema_valid": 0,
        "field_f1": 0.0,
        "errors": [],
        "duration_ms": _stats([]),
        "not_applicable": True,
        "reason": f"{suite} suite not applicable",
    }


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "p50": None,
            "p95": None,
            "max": None,
        }

    ordered = sorted(values)
    return {
        "count": len(values),
        "min": round(ordered[0], 2),
        "mean": round(statistics.mean(ordered), 2),
        "p50": round(_percentile(ordered, 0.50), 2),
        "p95": round(_percentile(ordered, 0.95), 2),
        "max": round(ordered[-1], 2),
    }


def _percentile(values: list[float], fraction: float) -> float:

    if len(values) == 1:
        return values[0]

    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return values[lower]

    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _json_object(text: Any) -> dict[str, Any]:

    if not isinstance(text, str):
        raise BenchmarkError("no text response")

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end < start:
        raise BenchmarkError("no JSON object")

    payload = json.loads(text[start:end + 1])

    if not isinstance(payload, dict):
        raise BenchmarkError("JSON root is not an object")

    return payload
