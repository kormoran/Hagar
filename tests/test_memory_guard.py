"""Test dei filtri di sicurezza per le memorie candidate."""

from __future__ import annotations

import pytest

from memory.errors import MemoryError
from memory.sqlite_projects import SqliteProjectStore
from memory.sqlite_store import SqliteMemoryStore


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


def test_skill_with_secret_is_rejected(tmp_path):

    memory, _ = make(tmp_path)

    with pytest.raises(MemoryError):

        memory.create_skill(
            "API key",
            "api_key=abcdefghijklmnopqrstuvwxyz",
        )


def test_duplicate_skill_can_be_reviewed(tmp_path):

    memory, _ = make(tmp_path)

    first, _ = memory.create_skill(
        "Prima",
        "stesso contenuto",
    )
    second, _ = memory.create_skill(
        "Seconda",
        "stesso contenuto",
    )

    assert second.id != first.id


def test_decision_with_secret_is_rejected(tmp_path):

    _, projects = make(tmp_path)

    with pytest.raises(MemoryError):

        projects.create_decision(
            "hagar",
            "Token",
            "token=abcdefghijklmnopqrstuvwxyz",
        )
