"""Test del service layer, senza console e senza rete."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.service import HarnessService
from memory.projects import ProjectError


class FakeAgent:
    def __init__(self) -> None:
        self.project_id = None
        self.answer = "risposta"
        self.error = None
        self.questions = []

    def ask(self, question):
        self.questions.append(question)

        if self.error is not None:
            raise self.error

        return self.answer


class FakeAudit:
    enabled = True
    path = "logs/audit.jsonl"
    session_id = "session-1"

    def __init__(self):
        self.entries = []

    def record(self, event, **fields):
        self.entries.append((event, fields))


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
        self.created = []

    def list_projects(self, include_archived=False):
        return list(self.projects)

    def get_project(self, project_id):
        for project in self.projects:
            if project.id == project_id:
                return project
        return None

    def create_project(self, name):
        project = SimpleNamespace(
            id=name.lower().replace(" ", "-"),
            title=name,
            status="active",
            active_decisions=0,
        )
        self.projects.append(project)
        self.created.append(name)
        return project


class FakeRegistry:
    def tool_names(self):
        return ["demo.echo"]


def make_harness():
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
    )

    agent = FakeAgent()
    harness = SimpleNamespace(
        config=config,
        agent=agent,
        audit=FakeAudit(),
        registry=FakeRegistry(),
        memory=None,
        memory_error=None,
        policy_error=None,
        project_store=FakeProjectStore(),
        project_id=None,
        project_state={"id": None},
    )

    return harness


def test_ask_returns_answer_and_emits_events():
    harness = make_harness()
    events = []
    service = HarnessService(harness, events.append)

    assert service.ask("ciao") == "risposta"
    assert harness.agent.questions == ["ciao"]
    assert [event.type for event in events] == [
        "turn.start",
        "turn.answer",
    ]
    assert events[1].data["answer"] == "risposta"
    assert events[1].data["duration_ms"] >= 0


def test_ask_error_emits_error_and_reraises():
    harness = make_harness()
    harness.agent.error = RuntimeError("modello giù")
    events = []
    service = HarnessService(harness, events.append)

    with pytest.raises(RuntimeError, match="modello giù"):
        service.ask("ciao")

    assert [event.type for event in events] == [
        "turn.start",
        "turn.error",
    ]
    assert events[1].data["error"] == "modello giù"


def test_set_and_clear_project_updates_harness_and_agent():
    harness = make_harness()
    events = []
    service = HarnessService(harness, events.append)

    service.set_project("hagar")

    assert harness.project_id == "hagar"
    assert harness.project_state["id"] == "hagar"
    assert harness.agent.project_id == "hagar"
    assert service.current_project()["title"] == "Hagar"

    service.clear_project()

    assert harness.project_id is None
    assert harness.project_state["id"] is None
    assert harness.agent.project_id is None
    assert [event.type for event in events] == [
        "project.changed",
        "project.changed",
    ]


def test_set_unknown_project_is_rejected():
    service = HarnessService(make_harness())

    with pytest.raises(ProjectError, match="not found"):
        service.set_project("missing")


def test_create_project_selects_it():
    harness = make_harness()
    service = HarnessService(harness)

    project = service.create_project("Nuovo Progetto")

    assert project["id"] == "nuovo-progetto"
    assert harness.project_id == "nuovo-progetto"
    assert harness.agent.project_id == "nuovo-progetto"
    assert harness.project_store.created == ["Nuovo Progetto"]


def test_status_is_structured():
    harness = make_harness()
    service = HarnessService(harness)

    service.set_project("hagar")
    status = service.status()

    assert status["session_id"] == "session-1"
    assert status["model"] == {
        "provider": "lmstudio",
        "name": "local-model",
    }
    assert status["project"]["id"] == "hagar"
    assert status["memory"]["enabled"] is False
    assert status["tools"] == ["demo.echo"]
    assert status["policy"]["subject"] == "assistant"


def test_list_projects_returns_plain_dicts():
    service = HarnessService(make_harness())

    assert service.list_projects() == [
        {
            "id": "hagar",
            "title": "Hagar",
            "status": "active",
            "active_decisions": 2,
        }
    ]
