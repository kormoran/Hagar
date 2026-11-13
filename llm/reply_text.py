"""Normalizzazione delle risposte LLM tra content e reasoning."""

from __future__ import annotations

import re

from typing import Any


_SPECIAL_TOKEN = re.compile(r"<\|[^|]*\|>")
_TURN_TAG = re.compile(
    r"</?(?:start_of_turn|end_of_turn|im_start|im_end|"
    r"bos|eos|channel|constrain|message)\b[^>]*>",
    re.IGNORECASE,
)
_CHANNEL_FINAL = re.compile(
    r"<\|channel\|>\s*final\s*",
    re.IGNORECASE,
)
_CHANNEL_THOUGHT = re.compile(
    r"<\|channel\|>\s*(?:thought|analysis)\s*",
    re.IGNORECASE,
)
_THOUGHT_BLOCK = re.compile(
    r"<(?:thinking|thought|reasoning|analysis)\b[^>]*>"
    r".*?"
    r"</(?:thinking|thought|reasoning|analysis)>",
    re.IGNORECASE | re.DOTALL,
)
_UNCLOSED_THOUGHT = re.compile(
    r"<(?:thinking|thought|reasoning|analysis)\b[^>]*>"
    r".*$",
    re.IGNORECASE | re.DOTALL,
)
_ROLE_PREFIX = re.compile(
    r"^(?:assistant|model|system|user)\s*[:>\n]\s*",
    re.IGNORECASE,
)
_ANSWER_TAGS = (
    "answer",
    "final",
    "response",
    "output",
    "result",
    "text",
)

_HTML_TAGS = frozenset({
    "a",
    "b",
    "br",
    "code",
    "div",
    "em",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
})


def _stringify(value: Any) -> str:

    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):

        parts = []

        for item in value:

            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):

                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])

        return "".join(parts)

    if isinstance(value, dict):

        for key in ("text", "content", "reasoning"):
            if isinstance(value.get(key), str):
                return value[key]

    return str(value)


def clean_text(value: Any) -> str:
    """Rimuove i wrapper noti, lasciando intatto HTML generico."""

    text = _stringify(value)

    if not text:
        return ""

    text = _CHANNEL_FINAL.sub("", text)
    text = _CHANNEL_THOUGHT.sub("", text)
    text = _SPECIAL_TOKEN.sub("", text)
    text = _TURN_TAG.sub("", text)
    text = _THOUGHT_BLOCK.sub("", text)
    text = _UNCLOSED_THOUGHT.sub("", text)
    text = _ROLE_PREFIX.sub("", text.strip())

    for tag in _ANSWER_TAGS:

        match = re.search(
            rf"<{tag}\b[^>]*>(.*?)</{tag}>",
            text,
            re.IGNORECASE | re.DOTALL,
        )

        if match is not None and match.group(1).strip():
            text = match.group(1)
            break

    wrapper = re.fullmatch(
        r"<(?!\|)([A-Za-z][\w:-]*)\b[^>]*>"
        r"(.*?)"
        r"</\1>",
        text.strip(),
        re.IGNORECASE | re.DOTALL,
    )

    if (
        wrapper is not None
        and wrapper.group(1).casefold() not in _HTML_TAGS
    ):
        text = wrapper.group(2)

    return text.strip()


def reply_text(
    content: Any,
    reasoning: Any = "",
) -> tuple[str, bool]:
    """Restituisce testo e indicatore di fallback dal reasoning."""

    text = clean_text(content)

    if text:
        return text, False

    fallback = clean_text(reasoning)

    return fallback, bool(fallback)
