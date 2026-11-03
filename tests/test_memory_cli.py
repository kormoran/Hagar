"""Test dei comandi `/memory`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memory.cli import MemoryCLI
from memory.store import MemoryStore
from memory.vault import Vault


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, event, **fields):
        self.entries.append({"event": event, **fields})


def make_when(hour: int = 12) -> datetime:

    return datetime(
        2026,
        11,
        3,
        hour,
        0,
        0,
        tzinfo=timezone.utc,
    )


@pytest.fixture
def store(tmp_path) -> MemoryStore:

    root = tmp_path / "vault"
    root.mkdir()

    return MemoryStore(
        Vault(root),
        session_id="sess1",
        max_skill_chars=500,
        model="test-model",
    )


def make_cli(
    store,
    answers=None,
    audit=None,
):
    output: list[str] = []

    remaining = iter(answers or [])

    def input_func(prompt):
        output.append(f"PROMPT: {prompt}")
        return next(remaining)

    cli = MemoryCLI(
        store,
        audit=audit,
        input_func=input_func,
        output_func=output.append,
    )

    return cli, output


def test_help(store):
    cli, output = make_cli(store)

    assert cli.handle("/memory") is True

    text = "\n".join(output)

    assert "/memory review" in text
    assert "/memory confirm" in text


def test_unknown_command(store):
    cli, output = make_cli(store)

    cli.handle("/memory altro")

    assert "sconosciuto" in "\n".join(output)


def test_list_defaults_to_candidates(store):
    store.create_skill(
        "Usare uv",
        "uv sync",
        when=make_when(),
    )

    cli, output = make_cli(store)

    cli.handle("/memory list")

    text = "\n".join(output)

    assert "candidate=1" in text
    assert "usare-uv" in text


def test_list_filtered_status(store):
    skill, _ = store.create_skill(
        "Usare uv",
        "uv sync",
        when=make_when(),
    )

    store.set_skill_status(skill.id, "confirmed")

    cli, output = make_cli(store)

    cli.handle("/memory list confirmed")

    text = "\n".join(output)

    assert "confirmed=1" in text
    assert "usare-uv" in text


def test_show(store):
    store.create_skill(
        "Usare uv",
        "Installa con uv sync",
        when=make_when(),
    )

    cli, output = make_cli(store)

    cli.handle("/memory show usare-uv")

    text = "\n".join(output)

    assert "status: candidate" in text
    assert "Installa con uv sync" in text


def test_show_missing(store):
    cli, output = make_cli(store)

    cli.handle("/memory show assente")

    assert "non trovata" in "\n".join(output)


def test_confirm_command(store):
    skill, _ = store.create_skill(
        "Usare uv",
        "uv sync",
        when=make_when(),
    )

    audit = FakeAudit()

    cli, output = make_cli(store, audit=audit)

    cli.handle(f"/memory confirm {skill.id}")

    assert store.get_skill(skill.id).status == "confirmed"

    assert any(
        entry["event"] == "memory.status"
        and entry["skill"] == skill.id
        and entry["to"] == "confirmed"
        for entry in audit.entries
    )


def test_archive_command(store):
    skill, _ = store.create_skill(
        "Usare uv",
        "uv sync",
        when=make_when(),
    )

    cli, _ = make_cli(store)

    cli.handle(f"/memory archive {skill.id}")

    assert store.get_skill(skill.id).status == "archived"


def test_confirm_without_slug(store):
    cli, output = make_cli(store)

    cli.handle("/memory confirm")

    assert "Uso:" in "\n".join(output)


def test_review_confirm_and_keep(store):
    first, _ = store.create_skill(
        "Prima",
        "contenuto uno",
        when=make_when(hour=10),
    )
    second, _ = store.create_skill(
        "Seconda",
        "contenuto due",
        when=make_when(hour=11),
    )

    audit = FakeAudit()

    cli, output = make_cli(
        store,
        answers=["y", "n"],
        audit=audit,
    )

    cli.handle("/memory review")

    assert store.get_skill(first.id).status == "confirmed"
    assert store.get_skill(second.id).status == "candidate"

    text = "\n".join(output)

    assert "Confermata: prima" in text
    assert "Lasciata candidata: seconda" in text

    assert any(
        entry["event"] == "memory.review"
        and entry["skill"] == first.id
        and entry["action"] == "confirm"
        for entry in audit.entries
    )


def test_review_archive_and_skip(store):
    first, _ = store.create_skill(
        "Prima",
        "contenuto uno",
        when=make_when(hour=10),
    )
    second, _ = store.create_skill(
        "Seconda",
        "contenuto due",
        when=make_when(hour=11),
    )

    cli, output = make_cli(
        store,
        answers=["a", "s"],
    )

    cli.handle("/memory review")

    assert store.get_skill(first.id).status == "archived"
    assert store.get_skill(second.id).status == "candidate"

    text = "\n".join(output)

    assert "Archiviata: prima" in text
    assert "Saltata: seconda" in text


def test_review_quit_stops(store):
    for hour in (10, 11):

        store.create_skill(
            f"Skill {hour}",
            "contenuto",
            when=make_when(hour=hour),
        )

    cli, output = make_cli(
        store,
        answers=["q"],
    )

    cli.handle("/memory review")

    assert [
        skill.id
        for skill in store.list_skills(
            status="candidate"
        )
    ] == ["skill-11", "skill-10"]

    assert "Riepilogo" in "\n".join(output)


def test_review_empty(store):
    cli, output = make_cli(store)

    cli.handle("/memory review")

    assert "Nessuna skill candidata" in "\n".join(
        output
    )


def test_handle_ignores_other_lines(store):
    cli, _ = make_cli(store)

    assert cli.handle("ciao") is False
