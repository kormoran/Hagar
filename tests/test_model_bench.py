"""Test di benchmark, schede e hardware."""

from __future__ import annotations

from types import SimpleNamespace

from core.command_service import CommandService
from core.benchmark_runs import BenchmarkRunStore
from core.hardware import detect_hardware
from core.model_bench import benchmark_model
from core.model_cards import ModelCardStore
from core.tool_call import ToolCall
from core.usage import TokenUsage


class FakeLLM:

    provider = "fake"
    model = "fake-model"
    supports_native_tools = False

    def __init__(self):
        self.last_usage = TokenUsage(
            input_tokens=10,
            output_tokens=5,
        )

    def chat(self, messages):
        prompt = messages[-1]["content"]

        if isinstance(prompt, list):
            return "red"

        if "JSON" in prompt or "choice" in prompt:
            return '{"choice":"yes","probabilities":{"yes":0.9,"no":0.1}}'

        return "OK"

    def request_tool_call(self, messages, registry):
        return ToolCall(
            tool="bench.echo",
            arguments={},
        )


class FakeVisionLLM:

    provider = "fake"
    model = "vision-model"

    def chat(self, messages):
        content = messages[-1]["content"]
        prompt = content[0]["text"]

        if "dominant color" in prompt:
            return "red"

        if "How many blue" in prompt:
            return "3"

        if "left or to the right" in prompt:
            return "left"

        return "HAGAR 42"


def test_hardware_has_expected_shape():
    info = detect_hardware()

    assert "platform" in info
    assert "cpu" in info
    assert "memory" in info
    assert isinstance(info["gpus"], list)
    assert info["cpu"]["logical_cores"]


def test_benchmark_card_and_last_tested(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.model_bench.detect_hardware",
        lambda: {
            "platform": "test",
            "cpu": {"logical_cores": 8},
            "memory": {"total_bytes": 1024},
            "gpus": [],
        },
    )

    report = benchmark_model(
        FakeLLM(),
        attempts=2,
        tool_attempts=2,
    )

    assert report["capabilities"]["chat"] is True
    assert report["capabilities"]["structured_json"] is True
    assert report["capabilities"]["tool_calling"] is True
    assert report["benchmarks"]["chat"]["successes"] == 2
    assert report["benchmarks"]["structured"]["valid_choice"] == 2
    assert report["benchmarks"]["tool_call"]["successes"] == 2

    report["last_tested_at"] = report["tested_at"]
    store = ModelCardStore(tmp_path / "cards")
    path = store.save(report)

    assert path.is_file()
    loaded = store.load("fake", "fake-model")
    assert loaded["last_tested_at"] == report["tested_at"]
    assert loaded["benchmarks"]["chat"]["successes"] == 2
    assert store.list()[0]["model"] == "fake-model"


def test_model_cards_slug_is_stable(tmp_path):
    store = ModelCardStore(tmp_path / "cards")

    assert store.path("LM Studio", "gemma 3").name == (
        "lm-studio-gemma-3.json"
    )


def test_models_command_runs_benchmark(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.model_bench.detect_hardware",
        lambda: {
            "platform": "test",
            "cpu": {"logical_cores": 8},
            "memory": {"total_bytes": 1024},
            "gpus": [],
        },
    )
    cards = ModelCardStore(tmp_path / "cards")
    commands = CommandService(
        SimpleNamespace(
            llm=FakeLLM(),
            audit=None,
        ),
        SimpleNamespace(),
        model_cards=cards,
        run_store=BenchmarkRunStore(tmp_path / "runs"),
    )

    result = commands.handle("/models test")

    assert result.ok is True
    assert cards.list()[0]["provider"] == "fake"
    assert result.data["last_tested_at"]
    assert result.data["quality"]["suite_version"] == 2
    assert "extraction" in result.data["quality"]["tasks"]
    assert "summary" in result.data["quality"]["tasks"]
    assert "translation" in result.data["quality"]["tasks"]
    assert len(BenchmarkRunStore(tmp_path / "runs").list()) == 1

    history = commands.handle("/models runs")
    assert history.ok is True
    assert len(history.data["runs"]) == 1
    assert history.data["runs"][0]["suite_manifest"]["version"] == 2


def test_models_command_runs_vision_benchmark(tmp_path):
    cards = ModelCardStore(tmp_path / "cards")
    runs = BenchmarkRunStore(tmp_path / "runs")
    commands = CommandService(
        SimpleNamespace(
            llm=FakeVisionLLM(),
            audit=None,
        ),
        SimpleNamespace(),
        model_cards=cards,
        run_store=runs,
    )

    result = commands.handle("/models test vision")

    assert result.ok is True
    assert result.data["vision"]["overall"] == 1.0
    assert result.data["provider"] == "fake"
    assert cards.list()[0]["vision"]["overall"] == 1.0
    assert len(runs.list()) == 1
