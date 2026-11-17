"""Test delle azioni di review memoria dalla Web UI."""

from __future__ import annotations

from core.memory_admin import MemoryAdmin
from memory.sqlite_projects import SqliteProjectStore
from memory.sqlite_store import SqliteMemoryStore


class FakeAudit:
    def __init__(self):
        self.entries = []

    def record(self, event, **fields):
        self.entries.append((event, fields))


def make(tmp_path):

    memory = SqliteMemoryStore(
        session_id="s1",
        path=tmp_path / "memory.db",
    )
    memory.ensure()
    projects = SqliteProjectStore(memory.database)
    projects.ensure()
    projects.create_project("Hagar")
    audit = FakeAudit()
    return memory, projects, MemoryAdmin(memory, projects, audit), audit


def test_lists_and_confirms_project_decision(tmp_path):

    memory, projects, admin, audit = make(tmp_path)
    decision = projects.create_decision(
        "hagar",
        "Usare Python",
        "Adottiamo Python.",
    )

    items = admin.list("project")
    assert [item["id"] for item in items] == [decision.id]

    admin.act("project", decision.id, "confirm")

    assert projects.get_decision(
        "hagar",
        decision.id,
    ).status == "active"
    assert audit.entries[-1][0] == "memory.review_web"
    assert admin.list("project") == []


def test_skill_confirm_archive_delete(tmp_path):

    memory, projects, admin, audit = make(tmp_path)
    skill, _ = memory.create_skill("Python", "usare python")

    assert admin.list("skill")[0]["id"] == skill.id

    admin.act("skill", skill.id, "confirm")
    assert memory.get_skill(skill.id).status == "confirmed"

    admin.act("skill", skill.id, "archive")
    assert memory.get_skill(skill.id).status == "archived"

    admin.act("skill", skill.id, "delete")
    assert memory.get_skill(skill.id) is None


def test_summary_status_and_delete(tmp_path):

    memory, projects, admin, audit = make(tmp_path)
    memory.write_summary("riassunto della sessione")

    items = admin.list("summary")
    assert len(items) == 1
    summary_id = items[0]["id"]

    admin.act("summary", summary_id, "confirm")

    with memory.database.connection() as connection:
        status = connection.execute(
            "SELECT status FROM summaries WHERE id = ?",
            (summary_id,),
        ).fetchone()["status"]

    assert status == "confirmed"

    admin.act("summary", summary_id, "delete")

    with memory.database.connection() as connection:
        row = connection.execute(
            "SELECT id FROM summaries WHERE id = ?",
            (summary_id,),
        ).fetchone()

    assert row is None
