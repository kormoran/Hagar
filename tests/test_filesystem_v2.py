"""Test delle estensioni filesystem: list, search, chunk, copy, rename."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)


def test_list_dir_returns_metadata(sandbox, workspace):
    (workspace / "b.txt").write_text("b", encoding="utf-8")
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    (workspace / "sub").mkdir()

    entries = sandbox.list_dir(".")

    assert [entry.path for entry in entries] == [
        "sub",
        "a.txt",
        "b.txt",
    ]
    assert entries[0].kind == "directory"
    assert entries[1].size_bytes == 1


def test_list_dir_can_inspect_subdirectory(
    sandbox,
    workspace,
):
    (workspace / "sub").mkdir()
    (workspace / "sub" / "a.txt").write_text(
        "a",
        encoding="utf-8",
    )

    entries = sandbox.list_dir("sub")

    assert [Path(entry.path) for entry in entries] == [
        Path("sub/a.txt")
    ]


def test_list_dir_rejects_missing_directory(sandbox):
    with pytest.raises(FileNotFoundError):
        sandbox.list_dir("assente")


def test_search_glob_and_truncation(sandbox, workspace):
    (workspace / "a.py").write_text("a", encoding="utf-8")
    (workspace / "b.py").write_text("b", encoding="utf-8")
    (workspace / "c.txt").write_text("c", encoding="utf-8")

    result = sandbox.search("*.py", max_results=1)

    assert result["total_matches"] == 2
    assert result["returned_matches"] == 1
    assert result["truncated"] is True
    assert result["results"][0].path == "a.py"


def test_search_rejects_escaping_pattern(sandbox):
    with pytest.raises(ValueError, match="sandbox"):
        sandbox.search("../*")


def test_read_chunk_has_more(sandbox, workspace):
    (workspace / "a.txt").write_bytes(b"abcdef")

    first = sandbox.read_chunk("a.txt", offset=0, length=3)
    second = sandbox.read_chunk("a.txt", offset=3, length=3)

    assert first["content"] == "abc"
    assert first["has_more"] is True
    assert second["content"] == "def"
    assert second["has_more"] is False


def test_read_chunk_validates_arguments(sandbox, workspace):
    (workspace / "a.txt").write_bytes(b"abc")

    with pytest.raises(ValueError, match="offset"):
        sandbox.read_chunk("a.txt", offset=-1)

    with pytest.raises(ValueError, match="length"):
        sandbox.read_chunk("a.txt", length=0)


def test_copy_file(sandbox, workspace):
    (workspace / "a.txt").write_text(
        "contenuto",
        encoding="utf-8",
    )

    sandbox.copy_file("a.txt", "b.txt")

    assert (workspace / "b.txt").read_text(
        encoding="utf-8"
    ) == "contenuto"


def test_copy_file_refuses_existing_destination(
    sandbox,
    workspace,
):
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    (workspace / "b.txt").write_text("b", encoding="utf-8")

    with pytest.raises(FileExistsError):
        sandbox.copy_file("a.txt", "b.txt")


def test_rename_file(sandbox, workspace):
    (workspace / "a.txt").write_text("a", encoding="utf-8")

    sandbox.rename("a.txt", "b.txt")

    assert not (workspace / "a.txt").exists()
    assert (workspace / "b.txt").read_text(
        encoding="utf-8"
    ) == "a"


def test_rename_requires_rename_permission(
    workspace,
):
    sandbox = FileSystemSandbox(
        roots={
            workspace: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
                rename=False,
                delete=True,
                execute=True,
            )
        },
        current_directory=workspace,
    )

    (workspace / "a.txt").write_text("a", encoding="utf-8")

    with pytest.raises(PermissionError):
        sandbox.rename("a.txt", "b.txt")


def test_rename_requires_destination_create(
    workspace,
):
    read_only = workspace / "readonly"
    read_only.mkdir()

    sandbox = FileSystemSandbox(
        roots={
            workspace: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
                rename=True,
                delete=True,
                execute=True,
            ),
            read_only: DirectoryPermissions(
                create=False,
            ),
        },
        current_directory=workspace,
    )

    (workspace / "a.txt").write_text("a", encoding="utf-8")

    with pytest.raises(PermissionError):
        sandbox.rename("a.txt", "readonly/b.txt")


def test_rename_refuses_existing_destination(
    sandbox,
    workspace,
):
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    (workspace / "b.txt").write_text("b", encoding="utf-8")

    with pytest.raises(FileExistsError):
        sandbox.rename("a.txt", "b.txt")


def test_stat_exposes_rename_permission(sandbox):
    info = sandbox.stat(".")

    assert info.permissions["rename"] is True
