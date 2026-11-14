"""Test del benchmark vision sintetico."""

from __future__ import annotations

from core.images import ImageInput
from core.vision_bench import benchmark_vision, cases, manifest


class FakeVisionLLM:
    provider = "fake"
    model = "vision-model"

    def __init__(self, wrong=None, error=None):
        self.wrong = wrong or {}
        self.error = error
        self.calls = []

    def chat(self, messages):
        content = messages[-1]["content"]
        prompt = content[0]["text"]
        self.calls.append(prompt)

        if self.error is not None:
            raise self.error

        if "dominant color" in prompt:
            return self.wrong.get("color", "red")

        if "How many blue" in prompt:
            return self.wrong.get("count", "3")

        if "left or to the right" in prompt:
            return self.wrong.get("spatial", "left")

        if "Read the text" in prompt:
            return self.wrong.get("ocr", "HAGAR 42")

        if "small text" in prompt:
            return self.wrong.get("ocr_small", "HAGAR-7B")

        if "Which bar" in prompt:
            return self.wrong.get("chart", "B")

        if "Which month" in prompt:
            return self.wrong.get("chart_months", "MAR")

        if "PORT" in prompt:
            return self.wrong.get("ui", "8080")

        if "Which field" in prompt:
            return self.wrong.get("ui_multi", "PORT")

        if "Describe the image" in prompt:
            return self.wrong.get(
                "scene",
                "A red circle is on the left, a blue square in the "
                "center, a green triangle on the right.",
            )

        return "unknown"


def test_vision_not_applicable_skips_llm():
    llm = FakeVisionLLM()

    report = benchmark_vision(llm, applicable=False)

    assert report["not_applicable"] is True
    assert report["overall"] is None
    assert llm.calls == []


def test_manifest_has_fixed_images():
    entries = manifest()

    assert len(entries) == 10
    assert {item["case"] for item in entries} == {
        "vision_color",
        "vision_count",
        "vision_spatial",
        "vision_ocr",
        "vision_chart",
        "vision_ui",
        "vision_ocr_small",
        "vision_chart_months",
        "vision_ui_multi",
        "vision_scene_description",
    }
    assert len({item["sha256"] for item in entries}) == 10

    for case in cases():
        image = ImageInput.from_bytes(case.image)
        assert image.mime_type == "image/png"


def test_vision_benchmark_perfect_answers():
    report = benchmark_vision(FakeVisionLLM(), attempts=1)

    assert report["suite_version"] == 2
    assert report["overall"] == 1.0
    assert report["tasks"]["vision"]["mean"] == 1.0
    assert len(report["images"]) == 10


def test_vision_benchmark_partial_and_errors():
    report = benchmark_vision(
        FakeVisionLLM(wrong={"count": "2"}),
        attempts=1,
    )

    assert report["overall"] == 0.9
    assert report["tasks"]["vision"]["mean"] == 0.9

    failing = benchmark_vision(
        FakeVisionLLM(error=RuntimeError("vision offline")),
        attempts=2,
    )

    assert failing["overall"] == 0.0
    assert all(
        len(item["errors"]) == 2
        for item in failing["tasks"]["vision"]["case_results"]
    )
