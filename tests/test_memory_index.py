"""Test dell'indice SQLite delle memorie."""

from __future__ import annotations

from pathlib import Path

from memory.index import MemoryIndex
from memory.vault import Vault


def make_index(tmp_path) -> tuple[Vault, MemoryIndex]:
    vault = Vault(tmp_path / "vault")
    vault.ensure_dir("Hagar")
    index = MemoryIndex(
        vault,
        path=tmp_path / "index" / "memory.db",
    )
    return vault, index


def write_notes(vault: Vault) -> None:
    vault.write(
        "Hagar/skills/uv.md",
        "---\n"
        "title: Usare uv\n"
        "status: confirmed\n"
        "---\n"
        "# Usare uv\n\n"
        "TOCTOU e symlink sono fuori dall'indice delle note.\n",
    )
    vault.write(
        "Hagar/projects/hagar/decisions/2026-01-01-token.md",
        "---\n"
        "title: Contare i token\n"
        "status: active\n"
        "project: hagar\n"
        "---\n"
        "# Contare i token\n\n"
        "Il ledger somma input e output.\n",
    )
    vault.write(
        "Hagar/chat/session-1.md",
        "---\n"
        "session: session-1\n"
        "---\n"
        "# Chat\n\n"
        "Una conversazione sul broker LLM.\n",
    )


def test_sync_indexes_documents_and_kinds(tmp_path):
    vault, index = make_index(tmp_path)
    write_notes(vault)

    changed = index.sync()
    stats = index.stats()

    assert changed == 3
    assert stats["documents"] == 3
    assert stats["kinds"]["skill"] == 1
    assert stats["kinds"]["decision"] == 1
    assert stats["kinds"]["chat"] == 1


def test_search_finds_content(tmp_path):
    vault, index = make_index(tmp_path)
    write_notes(vault)

    results = index.search("TOCTOU")

    assert len(results) == 1
    assert results[0]["path"].endswith("skills/uv.md")
    assert results[0]["kind"] == "skill"


def test_documents_excludes_chat_and_reads_content(tmp_path):
    vault, index = make_index(tmp_path)
    write_notes(vault)

    documents = index.documents()

    assert {item["kind"] for item in documents} == {
        "skill",
        "decision",
    }

    skill = index.document("Hagar/skills/uv.md")

    assert skill is not None
    assert "TOCTOU" in skill["content"]
    assert index.document("Hagar/chat/session-1.md") is None


def test_search_filters_project_and_kind(tmp_path):
    vault, index = make_index(tmp_path)
    write_notes(vault)

    results = index.search(
        "token",
        project="hagar",
        kind="decision",
    )

    assert len(results) == 1
    assert results[0]["project"] == "hagar"
    assert results[0]["kind"] == "decision"


def test_sync_is_incremental_and_removes_deleted(tmp_path):
    vault, index = make_index(tmp_path)
    write_notes(vault)

    assert index.sync() == 3
    assert index.sync() == 0

    vault.write(
        "Hagar/skills/uv.md",
        "---\ntitle: Usare uv\n---\n# Usare uv\n\nNuovo testo.\n",
    )
    assert index.sync() == 1

    vault._resolve("Hagar/chat/session-1.md").unlink()
    assert index.sync() == 1
    assert index.stats()["documents"] == 2


def test_rebuild_restores_index(tmp_path):
    vault, index = make_index(tmp_path)
    write_notes(vault)
    index.sync()

    index.path.unlink()
    index.rebuild()

    assert index.stats()["documents"] == 3
    assert index.search("broker")


def test_search_empty_query_returns_nothing(tmp_path):
    vault, index = make_index(tmp_path)
    write_notes(vault)

    assert index.search("   ") == []
