"""Filtri di sicurezza per le memorie candidate."""

from __future__ import annotations

import re

from typing import Any

from memory.errors import MemoryError


SECRET_PATTERNS = [
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        re.IGNORECASE,
    ),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|password|passwd|secret|token)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+-]{12,}"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{20,}"),
]


def contains_secret(text: str) -> bool:

    return any(
        pattern.search(text)
        for pattern in SECRET_PATTERNS
    )


def ensure_candidate_text(
    *values: Any,
) -> None:

    text = "\n".join(
        str(value)
        for value in values
        if value is not None
    )

    if contains_secret(text):
        raise MemoryError(
            "memory rejected: potential secret or credential "
            "detected"
        )


def normalize_text(text: str) -> str:

    return " ".join(text.lower().split())
