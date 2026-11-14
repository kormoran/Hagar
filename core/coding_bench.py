"""Benchmark coding con esecuzione di unit test locali."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from dataclasses import dataclass
from typing import Any

from core.model_cards import utc_now


class CodingBenchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CodingCase:
    name: str
    prompt: str
    tests: str


def cases() -> tuple[CodingCase, ...]:

    return (
        CodingCase(
            name="coding_add",
            prompt=(
                "Scrivi solo una funzione Python `add(a, b)` che "
                "restituisce la somma. Nessun testo, nessun markdown."
            ),
            tests=(
                "assert add(2, 3) == 5\n"
                "assert add(-1, 1) == 0\n"
                "assert add(0, 0) == 0\n"
            ),
        ),
        CodingCase(
            name="coding_is_even",
            prompt=(
                "Scrivi solo una funzione Python `is_even(n)` che "
                "restituisce True per i numeri pari. "
                "Nessun testo, nessun markdown."
            ),
            tests=(
                "assert is_even(2) is True\n"
                "assert is_even(3) is False\n"
                "assert is_even(0) is True\n"
            ),
        ),
    )


def _extract_code(text: str) -> str:

    match = re.search(
        r"```(?:python|py)?\s*(.*?)```",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if match is not None:
        return match.group(1).strip()

    return text.strip()


def _execute(
    code: str,
    tests: str,
    timeout: float,
) -> tuple[bool, str]:

    source = code + "\n\n" + tests + "\n"

    with tempfile.TemporaryDirectory(
        prefix="hagar-coding-bench-",
        ignore_cleanup_errors=True,
    ) as directory:

        try:
            os.chmod(directory, 0o755)
        except OSError:
            pass

        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
        }

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    source,
                ],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except OSError as exc:
            return False, str(exc)

        if result.returncode == 0:
            return True, ""

        detail = (result.stderr or result.stdout).strip()
        return False, detail[-1000:]


def benchmark_coding(
    llm: Any,
    attempts: int = 1,
    timeout: float = 10.0,
) -> dict[str, Any]:

    if attempts <= 0:
        raise CodingBenchError("attempts must be positive")

    case_results = []

    for case in cases():

        scores = []
        errors = []
        durations = []

        for _ in range(attempts):

            started = time.perf_counter()

            try:
                response = llm.chat([
                    {
                        "role": "user",
                        "content": case.prompt,
                    }
                ])
            except Exception as exc:
                errors.append(str(exc))
                scores.append(0.0)
                durations.append(
                    (time.perf_counter() - started) * 1000
                )
                continue

            code = _extract_code(str(response))
            ok, error = _execute(code, case.tests, timeout)
            scores.append(1.0 if ok else 0.0)
            durations.append(
                (time.perf_counter() - started) * 1000
            )

            if error:
                errors.append(error)

        case_results.append({
            "name": case.name,
            "attempts": attempts,
            "scores": scores,
            "mean": round(sum(scores) / len(scores), 4),
            "errors": errors,
            "duration_ms": _stats(durations),
        })

    scores = [
        score
        for case in case_results
        for score in case["scores"]
    ]
    mean = round(sum(scores) / len(scores), 4) if scores else 0.0

    return {
        "suite_version": 1,
        "tested_at": utc_now(),
        "attempts": attempts,
        "tasks": {
            "coding_exec": {
                "attempts": attempts,
                "cases": len(case_results),
                "scores": scores,
                "mean": mean,
                "errors": [
                    error
                    for case in case_results
                    for error in case["errors"]
                ],
                "case_results": case_results,
            }
        },
        "overall": mean,
    }


def _stats(values: list[float]) -> dict[str, Any]:

    if not values:
        return {
            "count": 0,
            "p50": None,
            "p95": None,
            "max": None,
        }

    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        index = (len(ordered) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        weight = index - lower
        return (
            ordered[lower] * (1 - weight)
            + ordered[upper] * weight
        )

    return {
        "count": len(ordered),
        "p50": round(percentile(0.50), 2),
        "p95": round(percentile(0.95), 2),
        "max": round(ordered[-1], 2),
    }
