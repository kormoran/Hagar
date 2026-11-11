"""Test delle primitive di memoria del DSL Flow."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.flow import FlowRunner
from core.models import FlowConfig
from core.tool_registry import ToolRegistry
from local_tools.flow_primitives import FlowPrimitiveProvider
from memory.store import MemoryStore
from memory.vault import Vault


@pytest.fixture
def memory(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()

    store = MemoryStore(
        Vault(root),
        session_id="s1",
        context_turns=5,
        max_skill_chars=2000,
        model="test-model",
        index_path=tmp_path / "index.db",
    )
    store.ensure()
    store.create_skill(
        "Release Hagar",
        "Il tag deve puntare al commit di preparazione.",
        kind="fact",
        tags=["release"],
    )
    store.append_turn(
        "t1",
        "Come si prepara la release?",
        "Si prepara il tag.",
    )
    return store


def make_runner(sandbox, memory=None, projects=None):
    registry = ToolRegistry()
    provider = FlowPrimitiveProvider(
        sandbox,
        memory=memory,
        project_store=projects,
        project_id_getter=lambda: "p1",
    )
    provider.register_tools(registry)
    return FlowRunner(
        registry,
        FlowConfig(enabled=True),
        provider.primitives,
    ), provider


def test_memory_search_and_skill(sandbox, memory):
    runner, _ = make_runner(sandbox, memory)

    result = runner.run(
        "items = memory.search('release')\n"
        "if len(items) == 0:\n"
        "    return None\n"
        "skill = memory.skill(items[0]['id'])\n"
        "return skill['content']\n"
    )

    assert result.ok is True
    assert "commit di preparazione" in result.result


def test_memory_context(sandbox, memory):
    runner, _ = make_runner(sandbox, memory)

    result = runner.run(
        "turns = memory.context(query='release')\n"
        "return turns[0]['question']\n"
    )

    assert result.ok is True
    assert "release" in result.result.lower()


def test_project_context(sandbox):
    class Projects:

        def list_decisions(self, project_id, status="active", limit=10):
            return [
                SimpleNamespace(
                    summary=lambda: {
                        "id": "d1",
                        "title": "Usare SQLite",
                    },
                    decision="SQLite",
                    alternatives=["JSON"],
                    rationale="Transazioni",
                )
            ]

        def search_decisions(self, project_id, query, limit=10):
            return []

    runner, _ = make_runner(
        sandbox,
        projects=Projects(),
    )

    result = runner.run(
        "items = project.context()\n"
        "return items[0]['decision']\n"
    )

    assert result.ok is True
    assert result.result == "SQLite"
