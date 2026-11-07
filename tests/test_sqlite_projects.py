"""Test di progetti e decisioni sul database SQLite."""

from __future__ import annotations

from memory.sqlite_projects import SqliteProjectStore
from memory.sqlite_store import SqliteMemoryStore


def make_stores(tmp_path):
    memory = SqliteMemoryStore(
        session_id="s1",
        path=tmp_path / "memory.db",
    )
    memory.ensure()
    projects = SqliteProjectStore(memory.database)
    projects.ensure()
    return memory, projects


def test_project_and_decision_lifecycle(tmp_path):
    _, projects = make_stores(tmp_path)

    project = projects.create_project("Hagar")
    assert project.id == "hagar"
    assert projects.get_project("hagar").title == "Hagar"

    decision = projects.create_decision(
        "hagar",
        "Usare SQLite",
        "SQLite è la fonte di verità.",
        alternatives=["Vault"],
        rationale="Transazioni e concorrenza.",
    )

    assert decision.status == "candidate"
    assert projects.list_decisions("hagar")[0].id == decision.id

    active = projects.set_decision_status(
        "hagar",
        decision.id,
        "active",
    )
    assert active.status == "active"
    assert projects.get_project("hagar").active_decisions == 1

    text, count = projects.context_index("hagar")
    assert count == 1
    assert "Usare SQLite" in text


def test_project_search_and_archive(tmp_path):
    _, projects = make_stores(tmp_path)
    project = projects.create_project("Hagar")
    projects.create_decision(
        project.id,
        "Alias sandbox",
        "Usare alias.",
        rationale="Nessun path host.",
    )

    hits = projects.search_decisions(project.id, "host")
    assert hits

    archived = projects.set_project_status(
        project.id,
        "archived",
    )
    assert archived.status == "archived"
    assert projects.list_projects() == []
    assert projects.list_projects(include_archived=True)
