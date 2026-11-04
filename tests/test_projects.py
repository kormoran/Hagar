"""Test della memoria di progetto, summary e archivio."""

from __future__ import annotations

import json

from pathlib import Path

import pytest

from memory.projects import ProjectError, ProjectStore
from memory.project_cli import ProjectCLI
from memory.session import SessionSummarizer
from memory.store import MemoryStore
from memory.vault import Vault


def make_store(
    tmp_path,
    session="sess-1",
) -> tuple[Vault, MemoryStore, ProjectStore]:

    vault = Vault(tmp_path / "vault")
    vault.root.mkdir()

    memory = MemoryStore(
        vault,
        session_id=session,
        subdir="Hagar",
        context_turns=10,
        context_skills=3,
        max_skill_chars=4000,
        model="test-model",
    )
    memory.ensure()

    projects = ProjectStore(vault, "Hagar")
    projects.ensure()

    return vault, memory, projects


class FakeSummaryLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return json.dumps(self.payload)


def add_turn(memory, question, answer, turn="t1"):
    memory.begin_turn(turn)
    memory.append_turn(turn, question, answer)
    memory.end_turn()


def test_project_crud_and_decision(tmp_path):
    _, _, projects = make_store(tmp_path)

    project = projects.create_project("Hagar")

    assert project.id == "hagar"
    assert projects.get_project("hagar").title == "Hagar"
    assert projects.list_projects()[0].id == "hagar"

    decision = projects.create_decision(
        "hagar",
        "Usare alias",
        "Adottiamo gli alias.",
        alternatives=["path piatti"],
        rationale="Evita ambiguità tra volumi.",
        session="sess-1",
    )

    assert decision.status == "candidate"
    assert decision.alternatives == ("path piatti",)

    active = projects.set_decision_status(
        "hagar",
        decision.id,
        "active",
    )

    assert active.status == "active"
    assert active.reviewed_at is not None

    index = projects.context_index(
        "hagar",
        max_decisions=10,
    )[0]

    assert "Hagar" in index
    assert "Usare alias" in index
    assert "path piatti" not in index


def test_project_cli_commands(tmp_path):
    _, _, projects = make_store(tmp_path)
    current = {"id": None}
    output = []

    cli = ProjectCLI(
        projects,
        lambda: current["id"],
        lambda value: current.update(id=value),
        output=output.append,
        input_func=lambda prompt: "Hagar",
    )

    cli.handle("/project new Hagar")

    assert current["id"] == "hagar"
    assert any("Buon lavoro" in line for line in output)

    cli.handle("/project free")
    assert current["id"] is None

    cli.handle("/project select hagar")
    assert current["id"] == "hagar"

    cli.handle("/project status")
    assert any("Progetto attivo" in line for line in output)

    cli.handle("/project archive hagar")
    assert projects.get_project("hagar").status == "archived"

    cli.handle("/project unarchive hagar")
    assert projects.get_project("hagar").status == "active"


def test_project_cli_archives_over_limit(tmp_path):
    _, _, projects = make_store(tmp_path)
    project = projects.create_project("Hagar")
    current = {"id": None}
    output = []

    for index in range(3):
        decision = projects.create_decision(
            project.id,
            f"Decisione {index}",
            "Testo",
        )
        projects.set_decision_status(
            project.id,
            decision.id,
            "active",
        )

    cli = ProjectCLI(
        projects,
        lambda: current["id"],
        lambda value: current.update(id=value),
        output=output.append,
        input_func=lambda prompt: "y",
        max_active=1,
        interactive=True,
    )

    cli.handle("/project select hagar")

    assert current["id"] is None
    assert projects.get_project("hagar").status == "archived"
    assert any("archiviato" in line for line in output)


def test_session_summary_archives_and_creates_candidate(
    tmp_path,
):
    vault, memory, projects = make_store(tmp_path)
    projects.create_project("Hagar")

    add_turn(
        memory,
        "Quale strada scegliamo?",
        "Scegliamo la strada A.",
    )

    llm = FakeSummaryLLM(
        {
            "summary": "Sessione breve: scelta A.",
            "decisions": [
                {
                    "title": "Scegliere A",
                    "decision": "Adottiamo A.",
                    "alternatives": ["B"],
                    "rationale": "A è più semplice.",
                }
            ],
        }
    )

    result = SessionSummarizer(
        memory,
        projects=projects,
        project_id="hagar",
        llm=llm,
        input_func=lambda prompt: "",
    ).finish()

    assert result["turns"] == 1
    assert result["archived"]
    assert result["decisions"]

    assert not list(
        (vault.root / "Hagar" / "chat").glob("*.md")
    )
    assert list(
        (vault.root / "Hagar" / "archive" / "chat").glob("*.md")
    )
    summaries = list(
        (vault.root / "Hagar" / "summaries").glob("*.md")
    )
    assert summaries
    assert "Sessione breve" in summaries[0].read_text(
        encoding="utf-8"
    )

    decisions = projects.list_decisions("hagar")

    assert len(decisions) == 1
    assert decisions[0].status == "candidate"
    assert decisions[0].auto_saved is True


def test_session_review_can_activate_decision(tmp_path):
    _, memory, projects = make_store(tmp_path)
    projects.create_project("Hagar")
    add_turn(memory, "Domanda", "Risposta")

    llm = FakeSummaryLLM(
        {
            "summary": "Summary.",
            "decisions": [
                {
                    "title": "Decisione",
                    "decision": "Facciamo X.",
                    "alternatives": [],
                    "rationale": "Per Y.",
                }
            ],
        }
    )

    answers = iter(["y", "y"])

    SessionSummarizer(
        memory,
        projects=projects,
        project_id="hagar",
        llm=llm,
        input_func=lambda prompt: next(answers),
        output_func=lambda text: None,
    ).finish()

    decisions = projects.list_decisions(
        "hagar",
        status="active",
    )

    assert len(decisions) == 1
    assert decisions[0].title == "Decisione"


def test_summary_fallback_without_llm(tmp_path):
    _, memory, projects = make_store(tmp_path)
    projects.create_project("Hagar")
    add_turn(memory, "Domanda importante", "Risposta")

    result = SessionSummarizer(
        memory,
        projects=projects,
        project_id="hagar",
        llm=None,
        input_func=lambda prompt: "",
    ).finish()

    assert "Sessione" in result["summary"]
    assert result["decisions"] == []


def test_project_context_tool_without_project(tmp_path):
    _, _, projects = make_store(tmp_path)

    from core.tool_registry import ToolRegistry
    from memory.project_tools import ProjectToolProvider

    registry = ToolRegistry()
    ProjectToolProvider(
        projects,
        lambda: None,
    ).register_tools(registry)

    payload = json.loads(
        registry.execute("memory.project_context")
    )

    assert "error" in payload


def test_project_context_tool_returns_decisions(tmp_path):
    _, _, projects = make_store(tmp_path)
    projects.create_project("Hagar")
    decision = projects.create_decision(
        "hagar",
        "Usare alias",
        "Adottiamo gli alias.",
        rationale="Meno ambiguità.",
    )
    projects.set_decision_status(
        "hagar",
        decision.id,
        "active",
    )

    from core.tool_registry import ToolRegistry
    from memory.project_tools import ProjectToolProvider

    registry = ToolRegistry()
    ProjectToolProvider(
        projects,
        lambda: "hagar",
    ).register_tools(registry)

    payload = json.loads(
        registry.execute(
            "memory.project_context",
            query="alias",
        )
    )

    assert payload["project"] == "hagar"
    assert payload["decisions"][0]["title"] == "Usare alias"


def test_agent_injects_project_index(tmp_path):
    _, memory, projects = make_store(tmp_path)
    projects.create_project("Hagar")
    decision = projects.create_decision(
        "hagar",
        "Usare alias",
        "Adottiamo gli alias.",
    )
    projects.set_decision_status(
        "hagar",
        decision.id,
        "active",
    )

    from core.agent import Agent
    from core.tool_registry import ToolRegistry

    agent = Agent(
        llm=None,
        tool_registry=ToolRegistry(),
        vault=memory.vault,
        memory=memory,
        project_store=projects,
        project_id="hagar",
        max_context_chars=6000,
    )

    context = agent._memory_context(
        "turn-1",
        "domanda",
    )

    assert "Hagar" in context
    assert "Usare alias" in context
    assert "memory.project_context" in context


def test_agent_injects_free_summary(tmp_path):
    _, memory, _ = make_store(tmp_path)
    memory.write_summary("Riassunto attività libera.")

    from core.agent import Agent
    from core.tool_registry import ToolRegistry

    agent = Agent(
        llm=None,
        tool_registry=ToolRegistry(),
        vault=memory.vault,
        memory=memory,
    )

    context = agent._memory_context(
        "turn-1",
        "domanda",
    )

    assert "Riassunto attività libera." in context


def test_project_cli_options_are_mutually_exclusive():
    from hagar import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--project", "hagar", "--free"]
        )
