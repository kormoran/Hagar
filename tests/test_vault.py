"""Test del Vault Obsidian."""

from __future__ import annotations

from memory.vault import Vault


def test_markdown_files_are_recursive(tmp_path):
    (tmp_path / "a.md").write_text("A", encoding="utf-8")
    (tmp_path / "note.txt").write_text("X", encoding="utf-8")

    nested = tmp_path / "sub"
    nested.mkdir()
    (nested / "b.md").write_text("B", encoding="utf-8")

    names = sorted(
        path.name
        for path in Vault(tmp_path).markdown_files()
    )

    assert names == ["a.md", "b.md"]


def test_load_all_returns_text(tmp_path):
    (tmp_path / "a.md").write_text(
        "contenuto",
        encoding="utf-8",
    )

    docs = Vault(tmp_path).load_all()

    assert len(docs) == 1
    assert docs[0]["path"].endswith("a.md")
    assert docs[0]["text"] == "contenuto"


def test_empty_vault(tmp_path):
    assert Vault(tmp_path).markdown_files() == []
    assert Vault(tmp_path).load_all() == []


def test_missing_vault_is_empty(tmp_path):
    vault = Vault(tmp_path / "missing")

    assert vault.markdown_files() == []
    assert vault.load_all() == []
