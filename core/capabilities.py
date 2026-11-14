"""Capability verificate dei modelli, separate da quelle dichiarate."""

from __future__ import annotations

from typing import Any


CAPABILITIES = frozenset({
    "chat",
    "coding",
    "structured_json",
    "tool_calling",
    "native_tools",
    "vision",
    "ocr",
    "reasoning",
})


def _mean(report: dict[str, Any], task: str) -> float | None:

    quality = report.get("quality")

    if not isinstance(quality, dict):
        return None

    tasks = quality.get("tasks")

    if not isinstance(tasks, dict):
        return None

    value = tasks.get(task)

    if not isinstance(value, dict):
        return None

    mean = value.get("mean")

    if isinstance(mean, bool) or not isinstance(
        mean,
        (int, float),
    ):
        return None

    return float(mean)


def _ocr_mean(report: dict[str, Any]) -> float | None:

    vision = report.get("vision")

    if not isinstance(vision, dict):
        return None

    task = vision.get("tasks", {}).get("vision", {})
    values = []

    for case in task.get("case_results", []):

        if not str(case.get("name", "")).startswith("vision_ocr"):
            continue

        value = case.get("mean")

        if isinstance(value, bool) or not isinstance(
            value,
            (int, float),
        ):
            continue

        values.append(float(value))

    if not values:
        return None

    return sum(values) / len(values)


def verified_capabilities(
    report: dict[str, Any],
) -> dict[str, bool]:
    """Deriva le capability dai risultati già misurati."""

    benchmarks = report.get("benchmarks")
    benchmarks = benchmarks if isinstance(benchmarks, dict) else {}

    chat = benchmarks.get("chat", {})
    structured = benchmarks.get("structured", {})
    tools = benchmarks.get("tool_call", {})

    chat_ok = (
        isinstance(chat, dict)
        and int(chat.get("successes", 0)) > 0
    )
    structured_ok = (
        isinstance(structured, dict)
        and int(structured.get("valid_json", 0)) > 0
    )
    tools_ok = (
        isinstance(tools, dict)
        and int(tools.get("successes", 0)) > 0
    )

    coding_mean = _mean(report, "coding")
    reasoning_mean = _mean(report, "reasoning")

    vision = report.get("vision")
    vision_mean = None

    if isinstance(vision, dict) and not vision.get(
        "not_applicable"
    ):

        overall = vision.get("overall")

        if (
            not isinstance(overall, bool)
            and isinstance(overall, (int, float))
        ):
            vision_mean = float(overall)
    ocr_mean = _ocr_mean(report)
    native = report.get("native_tools")

    if native is None:

        capabilities = report.get("capabilities")

        if isinstance(capabilities, dict):
            native = capabilities.get("native_tools", False)

    return {
        "chat": chat_ok,
        "coding": (
            coding_mean is not None
            and coding_mean >= 0.5
        ),
        "structured_json": structured_ok,
        "tool_calling": tools_ok,
        "native_tools": bool(native),
        "vision": (
            vision_mean is not None
            and vision_mean >= 0.5
        ),
        "ocr": (
            ocr_mean is not None
            and ocr_mean >= 0.5
        ),
        "reasoning": (
            reasoning_mean is not None
            and reasoning_mean >= 0.5
        ),
    }


def enabled_capabilities(
    report: dict[str, Any],
) -> frozenset[str]:
    """Capability verificate positive."""

    values = verified_capabilities(report)
    return frozenset(
        name
        for name, enabled in values.items()
        if enabled
    )
