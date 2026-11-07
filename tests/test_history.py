"""Test della cronologia chat nel Vault."""

from __future__ import annotations

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
