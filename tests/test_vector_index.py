"""Test dell'indice vettoriale SQLite."""

from __future__ import annotations

from types import SimpleNamespace

from memory.sqlite_projects import SqliteProjectStore
from memory.sqlite_store import SqliteMemoryStore
from memory.vector_index import MemoryEmbeddingIndex


class FakeEngine:
    config = SimpleNamespace(model="fake-embedding")
    dimensions = 3

    @staticmethod
    def _vector(text):
        lowered = text.lower()

        if "python" in lowered:
            return [1.0, 0.0, 0.0]

        if "sql" in lowered:
            return [0.0, 1.0, 0.0]

        return [0.0, 0.0, 1.0]

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


def make_store(tmp_path):

    memory = SqliteMemoryStore(
        session_id="s1",
        path=tmp_path / "memory.db",
    )
    memory.ensure()
    return memory


def test_reindex_and_cosine_search(tmp_path):

    memory = make_store(tmp_path)
    memory.create_skill("Python", "usare python per gli script")
    memory.create_skill("SQL", "query sql in sola lettura")
    memory.write_summary("riunione sul progetto")

    index = MemoryEmbeddingIndex(
        memory.database,
        FakeEngine(),
    )

    counts = index.reindex()

    assert counts["updated"] == 3
    assert index.stats()["total"] == 3

    hits = index.search("python", limit=2)

    assert hits[0].entity == "skill"
    assert hits[0].score == 1.0

    assert index.search("python", entity_types=["summary"]) == []


def test_project_filter_and_delete(tmp_path):

    memory = make_store(tmp_path)
    projects = SqliteProjectStore(memory.database)
    projects.ensure()
    projects.create_project("Hagar")
    projects.create_decision(
        "hagar",
        "Usare Python",
        "Adottiamo Python.",
    )

    index = MemoryEmbeddingIndex(
        memory.database,
        FakeEngine(),
    )
    index.reindex()

    hits = index.search(
        "python",
        project="hagar",
    )
    assert len(hits) == 1
    assert hits[0].entity == "decision"

    index.delete("decision", hits[0].entity_id)
    assert index.search("python", project="hagar") == []


def test_unchanged_text_is_not_reembedded(tmp_path):

    memory = make_store(tmp_path)
    memory.create_skill("Python", "usare python")
    index = MemoryEmbeddingIndex(memory.database, FakeEngine())

    first = index.reindex()
    second = index.reindex()

    assert first["updated"] == 1
    assert second["updated"] == 0
    assert second["unchanged"] >= 1
