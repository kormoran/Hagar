"""Test della consultazione dell'archivio chat."""

from __future__ import annotations

import json

from memory.cli import MemoryCLI
from memory.store import MemoryStore
from memory.tools import MemoryToolProvider
from memory.vault import Vault


def make_memory(
    tmp_path,
    session="sess-1",
    turns=(),
):
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

    for index, (question, answer) in enumerate(turns):

        turn = f"t{index}"
        memory.begin_turn(turn)
        memory.append_turn(turn, question, answer)
        memory.end_turn()

    return memory


def test_archive_search_and_read(tmp_path):
    memory = make_memory(
        tmp_path,
        turns=[
            ("Perche TOCTOU?", "Perche il caso e' malevolo."),
            ("Altra domanda", "Altra risposta."),
        ],
    )

    memory.archive_session(project="hagar")

    hits, total = memory.search_archive("TOCTOU")

    assert total == 1
    assert hits[0]["session"] == "sess-1"
    assert hits[0]["project"] == "hagar"
    assert "malevolo" in hits[0]["answer"]

    payload = memory.read_archive("sess-1", offset=0, limit=1)

    assert payload["total_turns"] == 2
    assert len(payload["turns"]) == 1
    assert payload["has_more"] is True
    assert payload["next_offset"] == 1

    payload = memory.read_archive(
        "sess-1",
        offset=1,
        limit=10,
    )

    assert len(payload["turns"]) == 1
    assert payload["has_more"] is False
    assert payload["project"] == "hagar"


def test_archive_project_filter(tmp_path):
    first = make_memory(
        tmp_path,
        session="sess-a",
        turns=[("alpha", "risposta alpha")],
    )
    first.archive_session(project="hagar")

    second = MemoryStore(
        first.vault,
        session_id="sess-b",
        subdir="Hagar",
        context_turns=10,
        context_skills=3,
        max_skill_chars=4000,
        model="test-model",
    )
    second.ensure()
    second.begin_turn("t0")
    second.append_turn("t0", "alpha", "risposta alpha")
    second.end_turn()
    second.archive_session(project="other")

    hits, total = first.search_archive(
        "alpha",
        project="hagar",
    )

    assert total == 1
    assert hits[0]["session"] == "sess-a"

    hits, total = first.search_archive("alpha")

    assert total == 2


def test_archive_read_missing_or_invalid(tmp_path):
    memory = make_memory(tmp_path)

    assert memory.read_archive("missing") is None

    try:
        memory.read_archive("../escape")

    except Exception as exc:
        assert "invalid" in str(exc).lower()

    else:
        raise AssertionError("invalid session accepted")


def test_memory_cli_archive_commands(tmp_path):
    memory = make_memory(
        tmp_path,
        turns=[("Domanda TOCTOU", "Risposta TOCTOU")],
    )
    memory.archive_session(project="hagar")

    output = []
    cli = MemoryCLI(
        memory,
        output_func=output.append,
    )

    cli.handle("/memory archive search TOCTOU")
    cli.handle("/memory archive read sess-1")

    text = "\n".join(output)

    assert "Archivio:" in text
    assert "sess-1" in text
    assert "Domanda TOCTOU" in text
    assert "Utente:" in text


def test_archive_tools(tmp_path):
    from core.tool_registry import ToolRegistry

    memory = make_memory(
        tmp_path,
        turns=[("Domanda TOCTOU", "Risposta TOCTOU")],
    )
    memory.archive_session(project="hagar")

    registry = ToolRegistry()
    MemoryToolProvider(memory).register_tools(registry)

    search = json.loads(
        registry.execute(
            "memory.archive_search",
            query="TOCTOU",
        )
    )

    assert search["total"] == 1
    assert search["results"][0]["session"] == "sess-1"

    read = json.loads(
        registry.execute(
            "memory.archive_read",
            session="sess-1",
        )
    )

    assert read["total_turns"] == 1
    assert read["turns"][0]["question"] == "Domanda TOCTOU"
