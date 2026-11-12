"""Benchmark vision con immagini sintetiche e deterministiche."""

from __future__ import annotations

import base64
import hashlib
import re
import struct
import zlib

from dataclasses import dataclass
from typing import Any, Callable

from core.model_cards import utc_now


class VisionBenchError(RuntimeError):
    pass


Color = tuple[int, int, int]
Canvas = list[list[Color]]


def _chunk(kind: bytes, data: bytes) -> bytes:

    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(
            ">I",
            zlib.crc32(kind + data) & 0xFFFFFFFF,
        )
    )


def _png(width: int, height: int, canvas: Canvas) -> bytes:

    raw = b"".join(
        b"\x00" + b"".join(
            bytes(pixel)
            for pixel in row
        )
        for row in canvas
    )
    header = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,
        2,
        0,
        0,
        0,
    )

    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def _fill(
    width: int,
    height: int,
    color: Color,
) -> Canvas:

    return [
        [color for _ in range(width)]
        for _ in range(height)
    ]


def _rect(
    canvas: Canvas,
    x: int,
    y: int,
    width: int,
    height: int,
    color: Color,
) -> None:

    for row in range(y, min(y + height, len(canvas))):
        for column in range(x, min(x + width, len(canvas[row]))):
            canvas[row][column] = color


_GLYPHS = {
    "H": (
        "10001",
        "10001",
        "10001",
        "11111",
        "10001",
        "10001",
        "10001",
    ),
    "A": (
        "01110",
        "10001",
        "10001",
        "11111",
        "10001",
        "10001",
        "10001",
    ),
    "G": (
        "01110",
        "10001",
        "10000",
        "10111",
        "10001",
        "10001",
        "01110",
    ),
    "R": (
        "11110",
        "10001",
        "10001",
        "11110",
        "10100",
        "10010",
        "10001",
    ),
    "4": (
        "00010",
        "00110",
        "01010",
        "10010",
        "11111",
        "00010",
        "00010",
    ),
    "2": (
        "01110",
        "10001",
        "00001",
        "00010",
        "00100",
        "01000",
        "11111",
    ),
    " ": (
        "00000",
        "00000",
        "00000",
        "00000",
        "00000",
        "00000",
        "00000",
    ),
}


def _text(
    canvas: Canvas,
    x: int,
    y: int,
    value: str,
    scale: int = 4,
    color: Color = (0, 0, 0),
) -> None:

    cursor = x

    for character in value.upper():

        glyph = _GLYPHS.get(character)

        if glyph is None:
            cursor += 6 * scale
            continue

        for row_index, row in enumerate(glyph):
            for column_index, pixel in enumerate(row):

                if pixel == "1":
                    _rect(
                        canvas,
                        cursor + column_index * scale,
                        y + row_index * scale,
                        scale,
                        scale,
                        color,
                    )

        cursor += 6 * scale


@dataclass(frozen=True, slots=True)
class VisionCase:
    name: str
    prompt: str
    expected: Any
    image_id: str
    image: bytes
    scorer: Callable[[str], float]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.image).hexdigest()


def _normal(text: str) -> str:

    return re.sub(
        r"\s+",
        " ",
        text.strip().casefold(),
    ).strip(" .,;:!?\"'`")


def _score_exact(expected: str) -> Callable[[str], float]:

    def score(text: str) -> float:
        return 1.0 if _normal(text) == _normal(expected) else 0.0

    return score


def _score_number(expected: int) -> Callable[[str], float]:

    def score(text: str) -> float:
        match = re.search(r"\b(\d+)\b", text)
        return (
            1.0
            if match is not None and int(match.group(1)) == expected
            else 0.0
        )

    return score


def _color_image() -> bytes:

    canvas = _fill(96, 96, (220, 20, 20))
    return _png(96, 96, canvas)


def _count_image() -> bytes:

    canvas = _fill(128, 96, (255, 255, 255))

    for index in range(3):
        _rect(
            canvas,
            20 + index * 32,
            30,
            20,
            20,
            (20, 80, 220),
        )

    return _png(128, 96, canvas)


def _spatial_image() -> bytes:

    canvas = _fill(128, 64, (255, 255, 255))
    _rect(canvas, 20, 22, 20, 20, (220, 20, 20))
    _rect(canvas, 88, 22, 20, 20, (20, 80, 220))

    return _png(128, 64, canvas)


def _ocr_image() -> bytes:

    canvas = _fill(220, 56, (255, 255, 255))
    _text(canvas, 8, 8, "HAGAR 42", scale=4)

    return _png(220, 56, canvas)


def cases() -> tuple[VisionCase, ...]:

    return (
        VisionCase(
            name="vision_color",
            prompt=(
                "What is the dominant color of this image? "
                "Answer with one word: red, blue or green."
            ),
            expected="red",
            image_id="color_red_01",
            image=_color_image(),
            scorer=_score_exact("red"),
        ),
        VisionCase(
            name="vision_count",
            prompt=(
                "How many blue squares are in this image? "
                "Answer with only the number."
            ),
            expected=3,
            image_id="count_three_01",
            image=_count_image(),
            scorer=_score_number(3),
        ),
        VisionCase(
            name="vision_spatial",
            prompt=(
                "Is the red square to the left or to the right "
                "of the blue square? Answer only left or right."
            ),
            expected="left",
            image_id="spatial_left_01",
            image=_spatial_image(),
            scorer=_score_exact("left"),
        ),
        VisionCase(
            name="vision_ocr",
            prompt=(
                "Read the text in this image. "
                "Answer only with the text."
            ),
            expected="HAGAR 42",
            image_id="ocr_hagar_42",
            image=_ocr_image(),
            scorer=_score_exact("hagar 42"),
        ),
    )


def manifest() -> list[dict[str, Any]]:

    return [
        {
            "id": case.image_id,
            "case": case.name,
            "sha256": case.sha256,
            "bytes": len(case.image),
        }
        for case in cases()
    ]


def benchmark_vision(
    llm: Any,
    attempts: int = 1,
) -> dict[str, Any]:

    if attempts <= 0:
        raise VisionBenchError("attempts must be positive")

    case_results = []

    for case in cases():

        scores = []
        errors = []

        for _ in range(attempts):

            try:
                response = llm.chat([
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": case.prompt,
                            },
                            {
                                "type": "image",
                                "mime_type": "image/png",
                                "data": base64.b64encode(
                                    case.image
                                ).decode("ascii"),
                            },
                        ],
                    }
                ])
            except Exception as exc:
                errors.append(str(exc))
                scores.append(0.0)
                continue

            scores.append(
                max(0.0, min(1.0, case.scorer(response)))
            )

        case_results.append({
            "name": case.name,
            "image_id": case.image_id,
            "sha256": case.sha256,
            "attempts": attempts,
            "scores": scores,
            "mean": round(sum(scores) / len(scores), 4),
            "errors": errors,
        })

    scores = [
        score
        for item in case_results
        for score in item["scores"]
    ]

    return {
        "suite_version": 1,
        "tested_at": utc_now(),
        "attempts": attempts,
        "images": manifest(),
        "tasks": {
            "vision": {
                "attempts": attempts,
                "cases": len(case_results),
                "scores": scores,
                "mean": round(sum(scores) / len(scores), 4),
                "errors": [
                    error
                    for item in case_results
                    for error in item["errors"]
                ],
                "case_results": case_results,
            }
        },
        "overall": round(sum(scores) / len(scores), 4),
    }
