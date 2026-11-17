"""Test dell'indicizzazione automatica delle memorie."""

from __future__ import annotations

from memory.sqlite_projects import SqliteProjectStore
from memory.sqlite_store import SqliteMemoryStore


class FakeIndex:
    def __init__(self):
        self.calls = []

    def upsert(self, entity, entity_id, text, **kwargs):
        self.calls.append((entity, entity_id, text, kwargs))


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


def test_skill_and_decision_are_indexed_on_creation(tmp_path):

    memory, projects = make(tmp_path)
    index = FakeIndex()
    memory.embedding_index = index
    projects.embedding_index = index

    memory.create_skill("Python", "usare python")
    projects.create_decision(
        "hagar",
        "Python",
        "usare python",
    )

    assert [call[0] for call in index.calls] == [
        "skill",
        "decision",
    ]
    assert index.calls[0][3]["status"] == "candidate"
    assert index.calls[1][3]["project"] == "hagar"


def test_skill_status_updates_embedding_status(tmp_path):

    memory, _ = make(tmp_path)
    skill, _ = memory.create_skill("Python", "usare python")

    with memory.database.connection() as connection:
        connection.execute(
            "INSERT INTO memory_embeddings("
            "entity, entity_id, project, status, model, dimensions, "
            "vector, content_hash, updated_at"
            ") VALUES ('skill', ?, NULL, 'candidate', 'm', 1, ?, 'h', ?)",
            (skill.id, b"x", "2026-01-01"),
        )

    memory.set_skill_status(skill.id, "confirmed")

    with memory.database.connection() as connection:
        row = connection.execute(
            "SELECT status FROM memory_embeddings "
            "WHERE entity = 'skill' AND entity_id = ?",
            (skill.id,),
        ).fetchone()

    assert row["status"] == "confirmed"


def test_skill_update_reindexes_content(tmp_path):

    memory, _ = make(tmp_path)
    index = FakeIndex()
    memory.embedding_index = index
    skill, _ = memory.create_skill("Python", "usare python")
    index.calls.clear()

    memory.update_skill(
        skill.id,
        title="Python 3",
        content="usare python 3",
    )

    assert index.calls
    assert index.calls[-1][0] == "skill"
