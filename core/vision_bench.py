"""Benchmark vision con immagini sintetiche e deterministiche."""

from __future__ import annotations

import base64
import hashlib
import re
import struct
import zlib

from dataclasses import dataclass
from typing import Any, Callable

from core.benchmark_corpus import BenchmarkCorpus
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
    "B": (
        "11110",
        "10001",
        "10001",
        "11110",
        "10001",
        "10001",
        "11110",
    ),
    "C": (
        "01110",
        "10001",
        "10000",
        "10000",
        "10000",
        "10001",
        "01110",
    ),
    "P": (
        "11110",
        "10001",
        "10001",
        "11110",
        "10000",
        "10000",
        "10000",
    ),
    "O": (
        "01110",
        "10001",
        "10001",
        "10001",
        "10001",
        "10001",
        "01110",
    ),
    "T": (
        "11111",
        "00100",
        "00100",
        "00100",
        "00100",
        "00100",
        "00100",
    ),
    "8": (
        "01110",
        "10001",
        "10001",
        "01110",
        "10001",
        "10001",
        "01110",
    ),
    "0": (
        "01110",
        "10001",
        "10001",
        "10001",
        "10001",
        "10001",
        "01110",
    ),
    "J": (
        "00111",
        "00010",
        "00010",
        "00010",
        "10010",
        "10010",
        "01100",
    ),
    "E": (
        "11111",
        "10000",
        "10000",
        "11110",
        "10000",
        "10000",
        "11111",
    ),
    "F": (
        "11111",
        "10000",
        "10000",
        "11110",
        "10000",
        "10000",
        "10000",
    ),
    "M": (
        "10001",
        "11011",
        "10101",
        "10101",
        "10001",
        "10001",
        "10001",
    ),
    "N": (
        "10001",
        "11001",
        "10101",
        "10011",
        "10001",
        "10001",
        "10001",
    ),
    "S": (
        "01111",
        "10000",
        "10000",
        "01110",
        "00001",
        "00001",
        "11110",
    ),
    "L": (
        "10000",
        "10000",
        "10000",
        "10000",
        "10000",
        "10000",
        "11111",
    ),
    "7": (
        "11111",
        "00001",
        "00010",
        "00100",
        "01000",
        "01000",
        "01000",
    ),
    "-": (
        "00000",
        "00000",
        "00000",
        "11111",
        "00000",
        "00000",
        "00000",
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


def _score_keypoints(
    expected: list[str],
) -> Callable[[str], float]:

    def score(text: str) -> float:
        normalized = _normal(text)
        matches = sum(
            1
            for term in expected
            if _normal(term) in normalized
        )
        return matches / len(expected)

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


def _chart_image() -> bytes:

    canvas = _fill(240, 160, (255, 255, 255))
    baseline = 125

    for index, height in enumerate((40, 90, 60)):
        x = 30 + index * 66
        _rect(
            canvas,
            x,
            baseline - height,
            34,
            height,
            (40, 120, 200),
        )

    _text(canvas, 42, 130, "A", scale=3)
    _text(canvas, 108, 130, "B", scale=3)
    _text(canvas, 174, 130, "C", scale=3)

    return _png(240, 160, canvas)


def _ui_image() -> bytes:

    canvas = _fill(240, 100, (245, 245, 245))
    _rect(canvas, 12, 12, 216, 76, (255, 255, 255))
    _text(canvas, 24, 24, "PORT", scale=4)
    _text(canvas, 24, 58, "8080", scale=4)

    return _png(240, 100, canvas)


def _circle(
    canvas: Canvas,
    center_x: int,
    center_y: int,
    radius: int,
    color: Color,
) -> None:

    for y in range(
        max(0, center_y - radius),
        min(len(canvas), center_y + radius + 1),
    ):
        for x in range(
            max(0, center_x - radius),
            min(len(canvas[y]), center_x + radius + 1),
        ):
            if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius ** 2:
                canvas[y][x] = color


def _triangle(
    canvas: Canvas,
    left: int,
    top: int,
    width: int,
    height: int,
    color: Color,
) -> None:

    for row in range(height):
        half = int((row + 1) * (width / 2) / height)
        start = left + width // 2 - half
        end = left + width // 2 + half

        for x in range(
            max(0, start),
            min(len(canvas[0]), end + 1),
        ):
            y = top + row

            if 0 <= y < len(canvas):
                canvas[y][x] = color


def _ocr_small_image() -> bytes:

    canvas = _fill(320, 100, (225, 225, 225))
    _text(canvas, 10, 36, "HAGAR-7B", scale=2, color=(80, 80, 80))

    for x, y in (
        (5, 5), (48, 12), (96, 7), (140, 88),
        (180, 20), (230, 75), (280, 15), (305, 60),
    ):
        canvas[y][x] = (150, 150, 150)

    return _png(320, 100, canvas)


def _chart_months_image() -> bytes:

    canvas = _fill(320, 190, (255, 255, 255))
    baseline = 150

    for index, height in enumerate((35, 70, 115, 55)):
        x = 28 + index * 72
        _rect(
            canvas,
            x,
            baseline - height,
            44,
            height,
            (55, 115, 190),
        )

    for index, label in enumerate(("JAN", "FEB", "MAR", "APR")):
        _text(canvas, 30 + index * 72, 160, label, scale=2)

    return _png(320, 190, canvas)


def _ui_multi_image() -> bytes:

    canvas = _fill(300, 150, (235, 235, 235))
    _rect(canvas, 12, 12, 276, 126, (255, 255, 255))
    _text(canvas, 24, 24, "HOST", scale=2)
    _text(canvas, 24, 54, "LOCALHOST", scale=2)
    _text(canvas, 24, 90, "PORT", scale=2)
    _text(canvas, 24, 116, "8080", scale=2)

    return _png(300, 150, canvas)


def _scene_image() -> bytes:

    canvas = _fill(320, 160, (255, 255, 255))
    _circle(canvas, 65, 80, 28, (210, 30, 30))
    _rect(canvas, 135, 52, 56, 56, (30, 80, 210))
    _triangle(canvas, 225, 48, 56, 64, (30, 160, 70))

    return _png(320, 160, canvas)


def cases(
    corpus: BenchmarkCorpus | None = None,
) -> tuple[VisionCase, ...]:

    corpus = corpus or BenchmarkCorpus.load()
    result = []

    for raw in corpus.vision:

        name = str(raw.get("name") or "")
        image_id = str(raw.get("image") or "")
        prompt = str(raw.get("prompt") or "")
        scorer_name = str(raw.get("scorer") or "")
        expected = raw.get("expected")

        if not name or not prompt:
            raise VisionBenchError(
                "vision case requires name and prompt"
            )

        if scorer_name == "exact":
            scorer = _score_exact(expected)
        elif scorer_name == "number":
            scorer = _score_number(int(expected))
        elif scorer_name == "keypoints":
            if not isinstance(expected, list):
                raise VisionBenchError(
                    "keypoints case requires a list"
                )
            scorer = _score_keypoints(expected)
        else:
            raise VisionBenchError(
                f"unknown vision scorer: {scorer_name!r}"
            )

        result.append(
            VisionCase(
                name=name,
                prompt=prompt,
                expected=expected,
                image_id=image_id,
                image=corpus.image(image_id),
                scorer=scorer,
            )
        )

    return tuple(result)


def manifest(
    corpus: BenchmarkCorpus | None = None,
) -> list[dict[str, Any]]:

    corpus = corpus or BenchmarkCorpus.load()
    case_names = {
        str(case.get("image")): str(case.get("name"))
        for case in corpus.vision
    }

    return [
        {
            "id": image_id,
            "case": case_names.get(image_id, ""),
            "path": entry.get("path"),
            "sha256": entry.get("sha256"),
        }
        for image_id, entry in corpus.images.items()
    ]


def benchmark_vision(
    llm: Any,
    attempts: int = 1,
    corpus: BenchmarkCorpus | None = None,
) -> dict[str, Any]:

    if attempts <= 0:
        raise VisionBenchError("attempts must be positive")

    corpus = corpus or BenchmarkCorpus.load()
    case_results = []

    for case in cases(corpus):

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
        "suite_version": 2,
        "corpus": corpus.suite_name,
        "tested_at": utc_now(),
        "attempts": attempts,
        "images": manifest(corpus),
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
