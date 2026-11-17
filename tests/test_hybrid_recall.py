"""Test del routing FTS/vettoriale."""

from __future__ import annotations

from memory.hybrid_recall import FtsRecall
from memory.hybrid_recall import HybridRecall
from memory.hybrid_recall import needs_lexical
from memory.sqlite_store import SqliteMemoryStore


class FakeRecall:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def context(self, question, project_id):
        self.calls += 1
        return self.answer, []


def test_lexical_hints_are_recognized():

    assert needs_lexical("errore E123")
    assert needs_lexical("src/core/agent.py")
    assert needs_lexical("versione 3.13")
    assert not needs_lexical("come funziona il progetto?")


def test_hybrid_uses_fts_for_exact_terms():

    vector = FakeRecall("vettoriale")
    fts = FakeRecall("esatto")
    hybrid = HybridRecall(vector, fts)

    text, _ = hybrid.context("src/core/agent.py", "hagar")

    assert text == "esatto"
    assert fts.calls == 1
    assert vector.calls == 0


def test_hybrid_uses_vectors_for_semantic_questions():

    vector = FakeRecall("vettoriale")
    fts = FakeRecall("esatto")
    hybrid = HybridRecall(vector, fts)

    text, _ = hybrid.context(
        "come funziona il progetto?",
        "hagar",
    )

    assert text == "vettoriale"
    assert vector.calls == 1
    assert fts.calls == 0


def test_fts_recall_returns_confirmed_exact_match(tmp_path):

    memory = SqliteMemoryStore(
        session_id="s1",
        path=tmp_path / "memory.db",
    )
    memory.ensure()
    memory.write_summary(
        "Errore E123 durante il caricamento del progetto."
    )

    with memory.database.connection() as connection:
        connection.execute(
            "UPDATE summaries SET status = 'confirmed'"
        )
        connection.execute(
            "UPDATE memory_fts SET status = 'confirmed' "
            "WHERE entity = 'summary'"
        )

    text, hits = FtsRecall(
        memory.database,
    ).context("errore E123", "hagar")

    assert text is not None
    assert "E123" in text
    assert hits[0]["mode"] == "fts"

