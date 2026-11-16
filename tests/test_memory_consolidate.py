"""Consolidamento e retention delle skill."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from memory.cli import MemoryCLI
from memory.consolidate import apply_skill_retention
from memory.consolidate import find_duplicate_skills
from memory.consolidate import merge_skills
from memory.consolidate import retention_candidates
from memory.sqlite_store import SqliteMemoryStore


def make_store(tmp_path) -> SqliteMemoryStore:

    store = SqliteMemoryStore(
        session_id="test",
        path=tmp_path / "memory.db",
    )
    store.ensure()
    return store


def test_find_and_merge_duplicate_skills(tmp_path):

    store = make_store(tmp_path)

    target, _ = store.create_skill(
        "Usare uv",
        "Esegui uv sync per installare le dipendenze.",
    )
    duplicate, _ = store.create_skill(
        "Installare con uv",
        "Esegui uv sync per installare le dipendenze del progetto.",
    )

    store.set_skill_status(target.id, "confirmed")

    groups = find_duplicate_skills(store, threshold=0.5)

    assert len(groups) == 1
    assert groups[0].target.id == target.id
    assert groups[0].duplicates[0].id == duplicate.id

    merged = merge_skills(
        store,
        target.id,
        [duplicate.id],
    )

    assert "dipendenze" in merged.content
    assert merged.tags == ()
    assert store.get_skill(duplicate.id).status == "archived"
    assert store.get_skill(target.id).status == "confirmed"


def test_merge_rejects_confirmed_into_candidate(tmp_path):

    store = make_store(tmp_path)

    source, _ = store.create_skill(
        "Fonte",
        "contenuto confermato",
    )
    target, _ = store.create_skill(
        "Target",
        "contenuto candidato",
    )
    store.set_skill_status(source.id, "confirmed")

    import pytest
    from memory.store import MemoryError

    with pytest.raises(MemoryError, match="confirmed"):
        merge_skills(store, target.id, [source.id])


def test_retention_archives_oldest_confirmed(tmp_path):

    store = make_store(tmp_path)

    skills = []

    for hour in (10, 11, 12):

        skill, _ = store.create_skill(
            f"Ricordo {hour}",
            f"contenuto {hour}",
            when=datetime(
                2026,
                11,
                14,
                hour,
                tzinfo=timezone.utc,
            ),
        )
        store.set_skill_status(skill.id, "confirmed")
        skills.append(skill)

    candidates = retention_candidates(store, 2)

    assert [skill.id for skill in candidates] == [skills[0].id]

    archived = apply_skill_retention(store, 2)

    assert [skill.id for skill in archived] == [skills[0].id]
    assert store.get_skill(skills[0].id).status == "archived"
    assert store.get_skill(skills[1].id).status == "confirmed"


def test_cli_duplicates_merge_and_retention(tmp_path):

    store = make_store(tmp_path)
    output = []

    target, _ = store.create_skill(
        "Usare uv",
        "Esegui uv sync per installare le dipendenze.",
    )
    duplicate, _ = store.create_skill(
        "Installare con uv",
        "Esegui uv sync per installare le dipendenze.",
    )
    store.set_skill_status(target.id, "confirmed")
    store.set_skill_status(duplicate.id, "confirmed")

    cli = MemoryCLI(
        store,
        output_func=output.append,
        max_active_skills=1,
    )

    assert cli.handle("/memory duplicates 0.5") is True
    assert any("Gruppi di skill simili" in line for line in output)

    output.clear()
    assert cli.handle(
        f"/memory merge {target.id} {duplicate.id}"
    ) is True
    assert store.get_skill(duplicate.id).status == "archived"

    output.clear()
    assert cli.handle("/memory retention") is True
    assert any("Retention skill" in line or "confermate" in line for line in output)
