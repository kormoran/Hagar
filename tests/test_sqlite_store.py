"""Test del backend SQLite delle memorie."""

from __future__ import annotations

import threading

from types import SimpleNamespace

from core.command_service import CommandService
from memory.sqlite_store import SqliteMemoryStore


def make_store(tmp_path, session="s1"):
    store = SqliteMemoryStore(
        session_id=session,
        path=tmp_path / "memory.db",
    )
    store.ensure()
    return store


def test_turns_are_persisted_and_listed(tmp_path):
    store = make_store(tmp_path)

    store.append_turn("t1", "prima domanda", "prima risposta")
    store.append_turn("t2", "seconda domanda", "seconda risposta")

    assert [turn.turn_id for turn in store.session_turns()] == [
        "t1",
        "t2",
    ]
    sessions = store.list_sessions()
    assert sessions[0]["id"] == "s1"
    assert sessions[0]["turns"] == 2
    assert store.read_session("s1")[0]["question"] == "prima domanda"


def test_archive_and_search(tmp_path):
    store = make_store(tmp_path)
    store.append_turn("t1", "come si fa", "così")

    store.archive_session()

    hits, total = store.search_archive("così")
    assert total == 1
    assert hits[0]["session"] == "s1"

    archive = store.read_archive("s1")
    assert archive["total_turns"] == 1
    assert archive["turns"][0]["turn"] == "t1"


def test_skill_lifecycle_and_recall(tmp_path):
    store = make_store(tmp_path)

    skill, duplicate = store.create_skill(
        "Deploy Hagar",
        "Usa il runner di test prima del deploy.",
        tags=["deploy", "test"],
    )

    assert duplicate is False
    assert store.get_skill(skill.id).status == "candidate"

    store.set_skill_status(skill.id, "confirmed")

    found = store.find_relevant_skills("come fare il deploy?")
    assert found and found[0].id == skill.id
    assert store.get_skill(skill.id).status == "confirmed"


def test_concurrent_appends_are_serialized(tmp_path):
    store = make_store(tmp_path)
    errors = []

    def worker(index):
        try:
            store.append_turn(
                f"t{index}",
                f"domanda {index}",
                f"risposta {index}",
            )
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(index,))
        for index in range(20)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert not errors
    assert len(store.session_turns(limit=100)) == 20


def test_index_compatibility(tmp_path):
    store = make_store(tmp_path)
    store.create_skill("Nota", "contenuto speciale")

    results = store.index.search("speciale")
    assert results
    assert store.index.document(results[0]["path"])["content"]
    assert store.index.stats()["skills"] == 1


def test_memory_commands_list_sessions_and_backup(tmp_path):
    store = make_store(tmp_path)
    store.append_turn("t1", "domanda", "risposta")
    commands = CommandService(
        SimpleNamespace(memory=store),
        SimpleNamespace(),
    )

    sessions = commands.handle("/memory sessions")
    assert sessions.ok is True
    assert sessions.data["sessions"][0]["id"] == "s1"

    chat = commands.handle("/memory chat s1")
    assert chat.ok is True
    assert chat.data["turns"][0]["turn"] == "t1"

    stats = commands.handle("/memory stats")
    assert stats.ok is True
    assert stats.data["turns"] == 1

    backup = commands.handle(
        f"/memory backup {tmp_path / 'backup.db'}"
    )
    assert backup.ok is True
    assert (tmp_path / "backup.db").exists()
