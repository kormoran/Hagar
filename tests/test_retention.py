"""Test della retention temporale della memoria."""

from __future__ import annotations

from datetime import datetime, timedelta

from memory.retention import MemoryRetention
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


def old(days=40):

    return (
        datetime.now().astimezone() - timedelta(days=days)
    ).isoformat(timespec="seconds")


def test_candidate_ttl_archives_old_items(tmp_path):

    memory, projects = make(tmp_path)
    skill, _ = memory.create_skill("Old", "contenuto vecchio")
    decision = projects.create_decision(
        "hagar",
        "Old decision",
        "decisione vecchia",
    )
    memory.write_summary("summary vecchio")
    memory.append_turn("t1", "domanda", "risposta")

    with memory.database.connection() as connection:
        connection.execute(
            "UPDATE skills SET created_at = ? WHERE id = ?",
            (old(), skill.id),
        )
        connection.execute(
            "UPDATE decisions SET created_at = ? WHERE id = ?",
            (old(), decision.id),
        )
        connection.execute(
            "UPDATE summaries SET created_at = ?",
            (old(),),
        )
        connection.execute(
            "UPDATE sessions SET updated_at = ?",
            (old(),),
        )

    counts = MemoryRetention(
        memory.database,
        candidate_ttl_days=30,
        chat_retention_days=30,
    ).sweep()

    assert counts["skills"] == 1
    assert counts["decisions"] == 1
    assert counts["summaries"] == 1
    assert counts["sessions"] == 1
    assert memory.get_skill(skill.id).status == "archived"
    assert projects.get_decision(
        "hagar",
        decision.id,
    ).status == "archived"


def test_summary_retention_archives_confirmed(tmp_path):

    memory, projects = make(tmp_path)
    memory.write_summary("summary confermato")

    with memory.database.connection() as connection:
        connection.execute(
            "UPDATE summaries SET status = 'confirmed', "
            "created_at = ?",
            (old(),),
        )

    counts = MemoryRetention(
        memory.database,
        candidate_ttl_days=0,
        summary_retention_days=10,
    ).sweep()

    assert counts["summaries"] == 1
