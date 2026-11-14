"""Scelta del profilo broker per un singolo turno."""

from __future__ import annotations

import re

from typing import Any


_CODE = re.compile(
    r"\b(?:code|codice|python|javascript|typescript|rust|java|"
    r"debug|bug|refactor|implementa|funzione|script|patch|"
    r"compila|test|pytest|sql|regex)\b",
    re.IGNORECASE,
)
_EXTRACTION = re.compile(
    r"\b(?:json|estrai|estrazione|extract|schema|structured|"
    r"tabella|parse|parsing|csv)\b",
    re.IGNORECASE,
)
_PRIVATE = re.compile(
    r"\b(?:privato|riservato|locale|offline|solo locale)\b",
    re.IGNORECASE,
)


def choose_profile(
    question: str,
    profiles: Any,
    default: str,
    *,
    images: bool = False,
) -> str:
    """Sceglie un profilo esistente; non inventa profili."""

    names = {
        profile.name
        for profile in getattr(profiles, "enabled", lambda: ())()
    }

    def pick(name: str) -> str | None:
        return name if name in names else None

    if images:

        selected = pick("vision")

        if selected:
            return selected

    text = question or ""

    if _CODE.search(text):

        selected = pick("coding")

        if selected:
            return selected

    if _EXTRACTION.search(text):

        selected = pick("structured_extraction")

        if selected:
            return selected

    if _PRIVATE.search(text):

        selected = pick("private_chat")

        if selected:
            return selected

    for name in ("quick_chat", default):

        selected = pick(name)

        if selected:
            return selected

    enabled = getattr(profiles, "enabled", lambda: ())()

    return enabled[0].name if enabled else default
