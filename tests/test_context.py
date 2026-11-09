"""Test di spill output e compattazione del contesto."""

from __future__ import annotations

from types import SimpleNamespace

from core.context import ContextCompactor, OutputSpiller


class FakeStore:

    def __init__(self):
        self.text = None

    def put_text(self, text, owner):
        self.text = text
        return SimpleNamespace(
            artifact_id="art-test",
            size=len(text.encode("utf-8")),
        )


def test_output_spiller_keeps_small_output_inline():
    spiller = OutputSpiller(FakeStore(), max_inline_chars=10)

    text, artifact = spiller.spill(
        "short",
        owner="main",
        tool="filesystem.read_file",
    )

    assert text == "short"
    assert artifact is None


def test_output_spiller_creates_artifact_for_large_output():
    store = FakeStore()
    spiller = OutputSpiller(
        store,
        max_inline_chars=5,
        preview_chars=3,
    )

    text, artifact = spiller.spill(
        "0123456789",
        owner="main",
        tool="filesystem.read_file",
    )

    assert artifact == "art-test"
    assert "artifact_id=art-test" in text
    assert "012" in text
    assert store.text == "0123456789"


def test_context_compactor_prunes_old_messages():
    compactor = ContextCompactor(max_chars=20, keep_recent=2)
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old " * 10},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "recent"},
    ]

    removed = compactor.compact(messages)

    assert removed > 0
    assert messages[0]["content"] == "system"
    assert "context omitted" in messages[1]["content"]
    assert messages[-1]["content"] == "recent"
