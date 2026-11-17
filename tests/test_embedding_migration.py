"""Test della migrazione automatica dei vettori."""

from __future__ import annotations

from memory.database import MemoryDatabase
from memory.migration import EmbeddingMigration


class FakeIndex:
    def __init__(self, model="new-model"):
        self.model = model
        self.calls = []

    def reindex(self, **kwargs):
        self.calls.append(kwargs)
        return {"updated": 1, "pruned": 1}


class FakeConfirmation:
    def __init__(self, approved=True):
        self.approved = approved
        self.requests = []

    def confirm(self, request):
        self.requests.append(request)
        return self.approved


class FakeAudit:
    def __init__(self):
        self.entries = []

    def record(self, event, **fields):
        self.entries.append((event, fields))


def make_db(tmp_path, models):

    database = MemoryDatabase(tmp_path / "memory.db")
    database.ensure()

    with database.connection() as connection:
        for model in models:
            connection.execute(
                "INSERT INTO memory_embeddings("
                "entity, entity_id, project, status, model, dimensions, "
                "vector, content_hash, updated_at"
                ") VALUES ('skill', ?, NULL, 'confirmed', ?, 3, ?, 'h', ?)",
                (
                    model,
                    model,
                    b"x",
                    "2026-01-01T00:00:00+00:00",
                ),
            )

    return database


def test_changed_model_asks_and_reindexes(tmp_path):

    database = make_db(tmp_path, ["old-model"])
    index = FakeIndex("new-model")
    confirmation = FakeConfirmation(True)
    audit = FakeAudit()

    result = EmbeddingMigration(
        database,
        index,
        confirmation,
        audit,
    ).migrate()

    assert result == "migrated"
    assert index.calls == [{"prune_other_models": True}]
    assert confirmation.requests[0].tool == "embedding.migrate"
    assert confirmation.requests[0].arguments["old_vectors"] == 1
    assert audit.entries[0][0] == "memory.embedding_migration"


def test_declined_migration_does_not_reindex(tmp_path):

    database = make_db(tmp_path, ["old-model"])
    index = FakeIndex("new-model")
    confirmation = FakeConfirmation(False)

    result = EmbeddingMigration(
        database,
        index,
        confirmation,
    ).migrate()

    assert result == "declined"
    assert index.calls == []


def test_unchanged_model_does_not_prompt(tmp_path):

    database = make_db(tmp_path, ["new-model"])
    index = FakeIndex("new-model")
    confirmation = FakeConfirmation(True)

    result = EmbeddingMigration(
        database,
        index,
        confirmation,
    ).migrate()

    assert result == "unchanged"
    assert confirmation.requests == []
    assert index.calls == []
