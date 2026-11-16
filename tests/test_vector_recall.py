"""Test del recall vettoriale del progetto in RAM."""

from __future__ import annotations

import math

from memory.sqlite_projects import SqliteProjectStore
from memory.sqlite_store import SqliteMemoryStore
from memory.vector_index import MemoryEmbeddingIndex
from memory.vector_recall import ProjectVectorRecall


class FakeEngine:
    config = type("Config", (), {"model": "fake"})()
    dimensions = 3

    @staticmethod
    def _vector(text):
        lowered = text.lower()

        if "alpha" in lowered:
            return [1.0, 0.0, 0.0]

        if "weak-a" in lowered:
            return [0.835, math.sqrt(1 - 0.835 ** 2), 0.0]

        if "weak-b" in lowered:
            return [0.820, math.sqrt(1 - 0.820 ** 2), 0.0]

        if "low" in lowered:
            return [0.80, 0.6, 0.0]

        return [0.0, 0.0, 1.0]

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


def make(tmp_path):

    memory = SqliteMemoryStore(
        session_id="s1",
        path=tmp_path / "memory.db",
    )
    memory.ensure()
    projects = SqliteProjectStore(memory.database)
    projects.ensure()
    projects.create_project("Hagar")
    return memory, projects


def test_strong_match_is_injected(tmp_path):

    memory, projects = make(tmp_path)
    projects.create_decision(
        "hagar",
        "Alpha",
        "usare alpha",
    )
    index = MemoryEmbeddingIndex(memory.database, FakeEngine())
    index.reindex()

    recall = ProjectVectorRecall(
        memory.database,
        index,
    )

    text, hits = recall.context("alpha", "hagar")

    assert text is not None
    assert "alpha" in text
    assert hits
    assert hits[0]["score"] == 1.0


def test_weak_match_without_margin_is_discarded(tmp_path):

    memory, projects = make(tmp_path)
    projects.create_decision("hagar", "Weak A", "weak-a")
    projects.create_decision("hagar", "Weak B", "weak-b")
    index = MemoryEmbeddingIndex(memory.database, FakeEngine())
    index.reindex()

    recall = ProjectVectorRecall(
        memory.database,
        index,
    )

    text, hits = recall.context("alpha", "hagar")

    assert text is None
    assert hits == []


def test_low_score_is_discarded(tmp_path):

    memory, projects = make(tmp_path)
    projects.create_decision("hagar", "Low", "low")
    index = MemoryEmbeddingIndex(memory.database, FakeEngine())
    index.reindex()

    recall = ProjectVectorRecall(
        memory.database,
        index,
    )

    assert recall.context("alpha", "hagar") == (None, [])
