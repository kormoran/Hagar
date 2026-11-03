"""Test dei tool di memoria."""

from __future__ import annotations

import json

import pytest

from core.permissions import (
    ALL_CAPABILITIES,
    Capability,
    Effect,
    PermissionDenied,
    PermissionEvaluator,
    Rule,
    Subject,
)
from core.tool_registry import ToolRegistry
from memory.store import MemoryError, MemoryStore
from memory.tools import MemoryToolProvider
from memory.vault import Vault


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()

    return MemoryStore(
        Vault(root),
        session_id="s1",
        context_turns=5,
        max_skill_chars=200,
        model="test-model",
    )


@pytest.fixture
def registry(store):
    registry = ToolRegistry()
    MemoryToolProvider(store).register_tools(registry)
    return registry


def test_tools_are_registered(registry):
    assert set(registry.tool_names()) == {
        "memory.create_skill",
        "memory.list_skills",
        "memory.get_context",
    }

    create = registry.get("memory.create_skill")

    assert create.capabilities == Capability.MEMORY_WRITE
    assert create.policy_namespace == "skills"

    context = registry.get("memory.get_context")

    assert context.capabilities == Capability.MEMORY_READ
    assert context.policy_namespace == "chat"


def test_create_skill_tool(registry):
    payload = json.loads(
        registry.execute(
            "memory.create_skill",
            title="Usare uv",
            content="Esegui uv sync.",
            kind="procedure",
            tags=["python"],
        )
    )

    assert payload["id"] == "usare-uv"
    assert payload["status"] == "candidate"
    assert payload["kind"] == "procedure"
    assert payload["tags"] == ["python"]
    assert payload["duplicate"] is False
    assert payload["path"].endswith("skills/usare-uv.md")


def test_create_skill_duplicate(registry):
    registry.execute(
        "memory.create_skill",
        title="Titolo",
        content="Primo",
    )

    payload = json.loads(
        registry.execute(
            "memory.create_skill",
            title="Titolo",
            content="Secondo",
        )
    )

    assert payload["duplicate"] is True


def test_create_skill_validation(registry):
    with pytest.raises(MemoryError):
        registry.execute(
            "memory.create_skill",
            title="",
            content="x",
        )

    with pytest.raises(MemoryError):
        registry.execute(
            "memory.create_skill",
            title="Titolo",
            content="x" * 300,
        )


def test_list_skills_tool(registry):
    registry.execute(
        "memory.create_skill",
        title="Uno",
        content="testo",
        kind="fact",
    )
    registry.execute(
        "memory.create_skill",
        title="Due",
        content="testo",
        kind="procedure",
    )

    payload = json.loads(
        registry.execute("memory.list_skills")
    )

    assert len(payload) == 2
    assert payload[0]["id"] == "due"

    facts = json.loads(
        registry.execute(
            "memory.list_skills",
            kind="fact",
        )
    )

    assert [item["id"] for item in facts] == ["uno"]


def test_get_context_tool(registry, store):
    store.append_turn("t1", "Domanda uno", "Risposta uno")
    store.append_turn("t2", "Domanda due", "Risposta due")

    payload = json.loads(
        registry.execute(
            "memory.get_context",
            limit=5,
        )
    )

    assert len(payload) == 2
    assert payload[0]["turn"] == "t1"
    assert payload[1]["question"] == "Domanda due"


def test_get_context_search(registry, store):
    store.append_turn("t1", "Python?", "Sì")
    store.append_turn("t2", "Meteo?", "No")

    payload = json.loads(
        registry.execute(
            "memory.get_context",
            query="python",
        )
    )

    assert [item["turn"] for item in payload] == ["t1"]


def test_get_context_limit_is_clamped(registry, store):
    for index in range(3):
        store.append_turn(
            f"t{index}",
            f"Q{index}",
            "A",
        )

    payload = json.loads(
        registry.execute(
            "memory.get_context",
            limit=0,
        )
    )

    assert len(payload) == 1


def test_memory_write_requires_capability(store):
    subject = Subject(
        name="test",
        rules=(
            Rule(
                capabilities=Capability.MEMORY_READ,
                effect=Effect.ALLOW,
            ),
        ),
    )

    registry = ToolRegistry(
        evaluator=PermissionEvaluator(ALL_CAPABILITIES),
        subject=subject,
    )

    MemoryToolProvider(store).register_tools(registry)

    with pytest.raises(PermissionDenied):
        registry.execute(
            "memory.create_skill",
            title="Titolo",
            content="Testo",
        )

    assert json.loads(
        registry.execute("memory.list_skills")
    ) == []


def test_namespace_scope_is_applied(store):
    subject = Subject(
        name="test",
        rules=(
            Rule(
                capabilities=Capability.MEMORY_READ,
                effect=Effect.ALLOW,
                namespaces=("chat",),
            ),
        ),
    )

    registry = ToolRegistry(
        evaluator=PermissionEvaluator(ALL_CAPABILITIES),
        subject=subject,
    )

    MemoryToolProvider(store).register_tools(registry)

    # get_context usa il namespace "chat": permesso.
    assert json.loads(
        registry.execute("memory.get_context")
    ) == []

    # list_skills usa il namespace "skills": negato.
    with pytest.raises(PermissionDenied):
        registry.execute("memory.list_skills")
