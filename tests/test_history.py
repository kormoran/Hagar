"""Test della cronologia chat nel Vault."""

from __future__ import annotations

import os

from memory.store import MemoryStore
from memory.vault import Vault


def make_store(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.ensure_dir("Hagar")
    store = MemoryStore(
        vault,
        session_id="sess-old",
        context_turns=10,
        index_path=tmp_path / "index.db",
    )
    store.ensure()
    return store


def test_new_session_changes_id_and_context(tmp_path):
    store = make_store(tmp_path)

    store.append_turn("t1", "vecchia domanda", "vecchia risposta")
    old = store.context_for("vecchia")[0]

    new_id = store.new_session()

    assert new_id != "sess-old"
    assert store.session_id == new_id
    assert store.context_for("vecchia")[0] is None


def test_sessions_are_listed_and_read(tmp_path):
    store = make_store(tmp_path)

    store.append_turn("t1", "prima domanda", "prima risposta")
    store.append_turn("t2", "seconda domanda", "seconda risposta")

    sessions = store.list_sessions()

    assert len(sessions) == 1
    assert sessions[0]["id"] == "sess-old"
    assert sessions[0]["turns"] == 2
    assert sessions[0]["title"] == "prima domanda"

    turns = store.read_session("sess-old")

    assert [turn["question"] for turn in turns] == [
        "prima domanda",
        "seconda domanda",
    ]


def test_new_session_is_not_in_history_until_a_turn(tmp_path):
    store = make_store(tmp_path)
    store.append_turn("t1", "domanda", "risposta")
    store.new_session("sess-new")

    assert [item["id"] for item in store.list_sessions()] == [
        "sess-old"
    ]

    store.append_turn("t2", "nuova", "risposta")
    ids = [item["id"] for item in store.list_sessions()]

    assert ids == ["sess-new", "sess-old"]


def test_new_session_wins_even_with_equal_filesystem_mtime(tmp_path):
    store = make_store(tmp_path)
    store.append_turn("t1", "vecchia", "risposta")
    store.new_session("sess-new")
    store.append_turn("t2", "nuova", "risposta")

    for path in store.vault.list_files(store.chat_dir, "*.md"):
        os.utime(path, (0, 0))

    assert [
        item["id"] for item in store.list_sessions()
    ] == ["sess-new", "sess-old"]


def test_resume_archived_session_keeps_context(tmp_path):
    store = make_store(tmp_path)
    store.append_turn("t1", "domanda vecchia", "risposta vecchia")

    archived = store.archive_session()

    assert archived

    store.select_session("sess-old")

    assert "domanda vecchia" in (
        store.context_for("vecchia")[0] or ""
    )

    store.append_turn("t2", "domanda nuova", "risposta nuova")

    turns = store.read_session("sess-old")

    assert {turn["turn"] for turn in turns} == {"t1", "t2"}
