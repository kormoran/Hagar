"""Test del CommandService strutturato, senza console."""

from __future__ import annotations

from types import SimpleNamespace

from core.command_service import CommandService
from core.permissions import Capability
from core.service import HarnessService


class FakeAudit:
    enabled = False
    path = "audit.jsonl"
    session_id = "s1"

    def record(self, event, **fields):
        pass


class FakeRegistry:
    def __init__(self, tools):
        self.tools = tools

    def list_definitions(self):
        return self.tools

    def tool_names(self):
        return [tool.name for tool in self.tools]


class FakeProjectStore:
    def __init__(self):
        self.projects = [
            SimpleNamespace(
                id="hagar",
                title="Hagar",
                status="active",
                active_decisions=2,
            )
        ]

    def list_projects(self, include_archived=False):
        return list(self.projects)

    def get_project(self, project_id):
        return next(
            (
                project
                for project in self.projects
                if project.id == project_id
            ),
            None,
        )

    def create_project(self, name):
        project = SimpleNamespace(
            id=name.lower().replace(" ", "-"),
            title=name,
            status="active",
            active_decisions=0,
        )
        self.projects.append(project)
        return project

    def set_project_status(self, project_id, status):
        project = self.get_project(project_id)
        project.status = status
        return project


class FakeSkill:
    def __init__(self, skill_id, title, status):
        self.id = skill_id
        self.title = title
        self.status = status
        self.content = "contenuto"

    def summary(self):
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
        }


class FakeMemory:
    STATUSES = ("candidate", "confirmed", "archived")

    def __init__(self):
        self.skills = [
            FakeSkill("demo", "Demo", "candidate"),
        ]

    def list_skills(self, kind=None, status=None, limit=50):
        return [
            skill for skill in self.skills
            if status is None or skill.status == status
        ]

    def get_skill(self, skill_id):
        return next(
            (
                skill for skill in self.skills
                if skill.id == skill_id
            ),
            None,
        )

    def set_skill_status(self, skill_id, status):
        skill = self.get_skill(skill_id)
        skill.status = status
        return skill

    def search_archive(self, query, limit=10):
        return (
            [
                {
                    "session": "s1",
                    "turn": "t1",
                    "date": "2026-11-07",
                    "question": query,
                }
            ],
            1,
        )

    def read_archive(self, session, offset=0, limit=20):
        return {
            "session": session,
            "turns": [
                {
                    "session": session,
                    "turn": "t1",
                    "timestamp": "2026-11-07T00:00:00",
                    "question": "domanda",
                }
            ],
            "total_turns": 1,
            "has_more": False,
        }


def make_service(memory=None):
    config = SimpleNamespace(
        model=SimpleNamespace(
            provider="lmstudio",
            name="local-model",
        ),
        policy=SimpleNamespace(
            path="policy.yaml",
            subject="assistant",
        ),
        vault=SimpleNamespace(path="vault"),
        memory=SimpleNamespace(
            vault_subdir="Hagar",
            summary_max_chars=4000,
        ),
        mcp_servers=[],
    )

    harness = SimpleNamespace(
        config=config,
        audit=FakeAudit(),
        registry=FakeRegistry([]),
        memory=memory,
        memory_error=None,
        policy_error=None,
        project_store=FakeProjectStore(),
        project_id=None,
        project_state={"id": None},
        agent=SimpleNamespace(project_id=None),
    )

    return harness, CommandService(
        harness,
        HarnessService(harness),
    )


def test_help_lists_commands():
    _, commands = make_service()

    result = commands.handle("/help")

    assert result.ok is True
    assert "/tools" in "\n".join(result.lines)
    assert "/memory" in "\n".join(result.lines)


def test_tools_returns_categories_and_capabilities():
    harness, commands = make_service()
    harness.registry.tools = [
        SimpleNamespace(
            name="clock.now",
            category="clock",
            capabilities=Capability.COMPUTE,
            origin="local",
            requires_confirmation=False,
        )
    ]

    result = commands.handle("/tools")

    assert result.ok is True
    assert result.data["count"] == 1
    assert result.data["categories"]["clock"][0]["name"] == (
        "clock.now"
    )
    assert result.data["categories"]["clock"][0]["capabilities"] == [
        "COMPUTE"
    ]


def test_status_returns_structured_data():
    _, commands = make_service()

    result = commands.handle("/status")

    assert result.ok is True
    assert result.data["model"]["provider"] == "lmstudio"
    assert result.data["project"] is None
    assert "Memoria: disattivata" in "\n".join(result.lines)


def test_project_list_and_select():
    harness, commands = make_service()

    result = commands.handle("/project list")

    assert result.ok is True
    assert result.data["projects"][0]["id"] == "hagar"
    assert result.data["current"] is None

    selected = commands.handle("/project select hagar")

    assert selected.ok is True
    assert harness.project_id == "hagar"
    assert selected.data["project"]["title"] == "Hagar"


def test_project_new_and_free():
    harness, commands = make_service()

    created = commands.handle("/project new Nuovo Progetto")

    assert created.ok is True
    assert harness.project_id == "nuovo-progetto"

    freed = commands.handle("/project free")

    assert freed.ok is True
    assert harness.project_id is None


def test_unknown_project_command_is_error():
    _, commands = make_service()

    result = commands.handle("/project nope")

    assert result.ok is False
    assert "sconosciuto" in result.error


def test_memory_list_and_show():
    _, commands = make_service(memory=FakeMemory())

    listed = commands.handle("/memory list")

    assert listed.ok is True
    assert listed.data["skills"][0]["id"] == "demo"

    shown = commands.handle("/memory show demo")

    assert shown.ok is True
    assert shown.data["content"] == "contenuto"


def test_memory_archive_search_is_not_a_skill_slug():
    _, commands = make_service(memory=FakeMemory())

    result = commands.handle("/memory archive search TOCTOU")

    assert result.ok is True
    assert result.data["total"] == 1
    assert result.data["hits"][0]["question"] == "TOCTOU"


def test_memory_archive_read_uses_structured_result():
    _, commands = make_service(memory=FakeMemory())

    result = commands.handle("/memory archive read s1")

    assert result.ok is True
    assert result.data["session"] == "s1"
    assert result.data["turns"][0]["turn"] == "t1"


def test_memory_review_requires_console():
    _, commands = make_service(memory=FakeMemory())

    result = commands.handle("/memory review")

    assert result.ok is False
    assert result.requires_input is True


def test_unknown_slash_command_is_structured():
    _, commands = make_service()

    result = commands.handle("/nope")

    assert result.ok is False
    assert result.command == "/nope"
    assert "sconosciuto" in "\n".join(result.lines)
