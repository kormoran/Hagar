"""Test dello store di memoria su vault."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memory.store import (
    MemoryError,
    MemoryStore,
    slugify,
)
from memory.vault import Vault, VaultError

TZ = timezone(timedelta(hours=1))


def make_when(
    day: int = 3,
    hour: int = 12,
) -> datetime:

    return datetime(
        2026,
        11,
        day,
        hour,
        0,
        0,
        tzinfo=TZ,
    )


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    return Vault(root)


@pytest.fixture
def store(vault):
    return MemoryStore(
        vault,
        session_id="sess1",
        subdir="Hagar",
        context_turns=3,
        max_skill_chars=100,
        model="test-model",
    )


# =====================================================
# Vault
# =====================================================


def test_vault_rejects_paths_outside_root(vault):
    with pytest.raises(VaultError):
        vault.read("../fuori.md")


def test_vault_write_and_read(vault):
    vault.write("note/a.md", "contenuto")

    assert vault.read("note/a.md") == "contenuto"
    assert vault.file_exists("note/a.md") is True


def test_vault_list_files(vault):
    vault.write("chat/a.md", "a")
    vault.write("chat/b.md", "b")
    vault.write("chat/c.txt", "c")

    names = [
        path.name
        for path in vault.list_files("chat", "*.md")
    ]

    assert names == ["a.md", "b.md"]


def test_store_ensure_creates_directories(store, tmp_path):
    store.ensure()

    assert (tmp_path / "vault" / "Hagar" / "chat").is_dir()
    assert (tmp_path / "vault" / "Hagar" / "skills").is_dir()


def test_store_ensure_requires_vault(tmp_path):
    store = MemoryStore(
        Vault(tmp_path / "missing"),
        session_id="s1",
    )

    with pytest.raises(MemoryError, match="Vault not found"):
        store.ensure()


# =====================================================
# Memoria episodica
# =====================================================


def test_append_turn_creates_session_note(store, tmp_path):
    turn = store.append_turn(
        "turn1",
        "Domanda",
        "Risposta",
        when=make_when(),
    )

    path = (
        tmp_path
        / "vault"
        / "Hagar"
        / "chat"
        / "2026-11-03-sess1.md"
    )

    assert path.exists()
    assert turn.session == "sess1"
    assert turn.turn_id == "turn1"
    assert turn.timestamp == "2026-11-03T12:00:00+01:00"

    text = path.read_text(encoding="utf-8")

    assert "session: sess1" in text
    assert "## 2026-11-03T12:00:00+01:00 · turn1" in text
    assert "**Utente:** Domanda" in text
    assert "**Hagar:** Risposta" in text


def test_append_multiple_turns(store):
    store.append_turn("t1", "Q1", "A1", when=make_when(hour=10))
    store.append_turn("t2", "Q2", "A2", when=make_when(hour=11))

    turns = store.recent_turns()

    assert [turn.question for turn in turns] == ["Q1", "Q2"]


def test_recent_turns_limit(store):
    store.append_turn("t1", "Q1", "A1", when=make_when(hour=10))
    store.append_turn("t2", "Q2", "A2", when=make_when(hour=11))
    store.append_turn("t3", "Q3", "A3", when=make_when(hour=12))

    turns = store.recent_turns(limit=2)

    assert [turn.question for turn in turns] == ["Q2", "Q3"]


def test_recent_turns_can_filter_session(store):
    store.append_turn("t1", "Q1", "A1", when=make_when(hour=10))

    assert store.recent_turns(session="sess1") != []
    assert store.recent_turns(session="altro") == []


def test_context_text_is_empty_without_turns(store):
    assert store.context_text() == (None, 0)


def test_context_text_contains_recent_turns(store):
    store.append_turn("t1", "Q1", "A1", when=make_when(hour=10))
    store.append_turn("t2", "Q2", "A2", when=make_when(hour=11))

    text, count = store.context_text()

    assert count == 2
    assert "Q1" in text
    assert "A2" in text
    assert text.index("Q1") < text.index("Q2")


def test_context_text_truncates_long_answers(vault):
    store = MemoryStore(
        vault,
        session_id="sess1",
        context_turns=5,
    )

    store.append_turn(
        "t1",
        "Q",
        "x" * 2000,
        when=make_when(),
    )

    text, _ = store.context_text()

    assert "…" in text
    assert len(text) < 2000


def test_search_turns(store):
    store.append_turn(
        "t1",
        "Come si usa Python?",
        "Con un venv",
        when=make_when(hour=10),
    )
    store.append_turn(
        "t2",
        "Che tempo fa?",
        "Non lo so",
        when=make_when(hour=11),
    )

    assert [
        turn.question
        for turn in store.search_turns("python")
    ] == ["Come si usa Python?"]

    assert [
        turn.question
        for turn in store.search_turns("VENV")
    ] == ["Come si usa Python?"]

    assert store.search_turns("assente") == []


def test_search_turns_respects_limit(store):
    for index in range(5):
        store.append_turn(
            f"t{index}",
            f"python {index}",
            "ok",
            when=make_when(hour=10 + index),
        )

    assert len(store.search_turns("python", limit=2)) == 2


# =====================================================
# Memoria semantica
# =====================================================


def test_create_skill(store, tmp_path):
    store.begin_turn("turn7")

    skill, duplicate = store.create_skill(
        "Usare uv",
        "Esegui `uv sync`.",
        kind="procedure",
        tags=["python", "tooling"],
        when=make_when(),
    )

    assert duplicate is False
    assert skill.id == "usare-uv"
    assert skill.status == "candidate"
    assert skill.kind == "procedure"
    assert skill.tags == ("python", "tooling")
    assert skill.source_session == "sess1"
    assert skill.source_turn == "turn7"
    assert skill.model == "test-model"

    path = (
        tmp_path
        / "vault"
        / "Hagar"
        / "skills"
        / "usare-uv.md"
    )

    assert path.exists()

    text = path.read_text(encoding="utf-8")

    assert "status: candidate" in text
    assert "source_turn: turn7" in text
    assert "Esegui `uv sync`." in text


def test_create_skill_duplicate_does_not_overwrite(store):
    first, _ = store.create_skill(
        "Titolo",
        "Contenuto originale",
        when=make_when(),
    )

    second, duplicate = store.create_skill(
        "Titolo",
        "Contenuto nuovo",
        when=make_when(hour=13),
    )

    assert duplicate is True
    assert second.id == first.id

    text = store.vault.read(second.path)

    assert "Contenuto originale" in text
    assert "Contenuto nuovo" not in text

    stored = store.get_skill(first.id)

    assert stored is not None


def test_create_skill_validates_input(store):
    with pytest.raises(MemoryError, match="title"):
        store.create_skill("", "contenuto")

    with pytest.raises(MemoryError, match="content"):
        store.create_skill("titolo", "")

    with pytest.raises(MemoryError, match="kind"):
        store.create_skill("titolo", "testo", kind="altro")

    with pytest.raises(MemoryError, match="max_skill_chars"):
        store.create_skill("titolo", "x" * 200)


def test_create_skill_requires_session_id(vault):
    with pytest.raises(MemoryError, match="session_id"):
        MemoryStore(vault, session_id="")


def test_create_skill_rejects_unsafe_subdir(vault):
    with pytest.raises(MemoryError, match="vault_subdir"):
        MemoryStore(
            vault,
            session_id="s",
            subdir="../fuori",
        )

    with pytest.raises(MemoryError, match="vault_subdir"):
        MemoryStore(
            vault,
            session_id="s",
            subdir="I:/assoluto",
        )


def test_slugify():
    assert slugify("Usare uv per Python") == "usare-uv-per-python"
    assert slugify("Città e caffè") == "citta-e-caffe"
    assert slugify("../../evil") == "evil"
    assert slugify("!!!").startswith("skill-")
    assert slugify("???").startswith("skill-")


def test_tags_normalization(store):
    skill, _ = store.create_skill(
        "Con tag",
        "testo",
        tags="python, tooling, python",
        when=make_when(),
    )

    assert skill.tags == ("python", "tooling")

    skill, _ = store.create_skill(
        "Altri tag",
        "testo",
        tags=["a", "", 3, "b"],
        when=make_when(),
    )

    assert skill.tags == ("a", "b")


def test_list_skills(store):
    store.create_skill("Uno", "testo", kind="fact", when=make_when(hour=10))
    store.create_skill("Due", "testo", kind="procedure", when=make_when(hour=11))

    all_skills = store.list_skills()

    assert [skill.id for skill in all_skills] == ["due", "uno"]

    facts = store.list_skills(kind="fact")

    assert [skill.id for skill in facts] == ["uno"]

    assert store.list_skills(status="confirmed") == []


def test_list_skills_rejects_unknown_filters(store):
    with pytest.raises(MemoryError, match="kind"):
        store.list_skills(kind="altro")

    with pytest.raises(MemoryError, match="status"):
        store.list_skills(status="altro")


def test_get_missing_skill(store):
    assert store.get_skill("assente") is None


def test_current_turn_is_cleared(store):
    store.begin_turn("turn1")
    store.end_turn()

    skill, _ = store.create_skill(
        "Senza turno",
        "testo",
        when=make_when(),
    )

    assert skill.source_turn is None
