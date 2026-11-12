"""Manifest versionato delle suite di benchmark."""

from __future__ import annotations

from typing import Any

from core.quality_bench import cases as quality_cases
from core.vision_bench import manifest as vision_manifest


BENCHMARK_SUITE_VERSION = 2


def manifest() -> dict[str, Any]:

    return {
        "version": BENCHMARK_SUITE_VERSION,
        "quality": {
            "suite_version": 2,
            "cases": [
                {
                    "name": case.name,
                    "task": case.task or case.name,
                    "prompt": case.prompt,
                    "expected": case.expected,
                }
                for case in quality_cases()
            ],
        },
        "vision": {
            "suite_version": 1,
            "images": vision_manifest(),
        },
    }
