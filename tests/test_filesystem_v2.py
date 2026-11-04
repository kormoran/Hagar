"""Test delle estensioni filesystem: list, search, chunk, copy, rename."""

from __future__ import annotations

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
        "/home/ai/root/sub",
        "/home/ai/root/a.txt",
        "/home/ai/root/b.txt",
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

    assert [entry.path for entry in entries] == [
        "/home/ai/root/sub/a.txt"
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
    assert result["results"][0].path == "/home/ai/root/a.py"


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


def test_stat_hides_real_path_even_for_absolute_input(
    sandbox,
    workspace,
):
    target = workspace / "a.txt"
    target.write_text("a", encoding="utf-8")

    info = sandbox.stat(str(target))

    assert info.path == "/home/ai/root/a.txt"
    assert str(workspace) not in info.path


def test_virtual_paths_are_accepted_as_input(
    sandbox,
    workspace,
):
    (workspace / "a.txt").write_text(
        "a",
        encoding="utf-8",
    )

    assert sandbox.read_file("/home/ai/root/a.txt") == "a"
    assert sandbox.virtual_path(".") == "/home/ai/root"


def test_errors_do_not_expose_real_path(
    sandbox,
    workspace,
):
    with pytest.raises(FileNotFoundError) as exc:
        sandbox.read_file("missing.txt")

    assert "/home/ai/root/missing.txt" in str(exc.value)
    assert str(workspace) not in str(exc.value)


def test_virtual_path_is_stable_after_chdir(
    sandbox,
    workspace,
):
    (workspace / "sub").mkdir()
    (workspace / "sub" / "a.txt").write_text(
        "a",
        encoding="utf-8",
    )

    sandbox.chdir("sub")

    assert sandbox.stat("a.txt").path == (
        "/home/ai/root/sub/a.txt"
    )
    assert sandbox.virtual_path(".") == "/home/ai/root/sub"


def make_alias_sandbox(tmp_path):
    first = tmp_path / "documenti"
    second = tmp_path / "ebooks"
    first.mkdir()
    second.mkdir()

    return FileSystemSandbox(
        roots={
            first: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
                rename=True,
                delete=True,
                execute=True,
            ),
            second: DirectoryPermissions(
                read=True,
                write=False,
                create=False,
                rename=False,
                delete=False,
                execute=True,
            ),
        },
        current_directory=first,
        aliases={
            "documenti": first,
            "ebooks": second,
        },
    ), first, second


def test_virtual_root_lists_aliases(tmp_path):
    sandbox, first, second = make_alias_sandbox(tmp_path)
    (first / "a.txt").write_text("a", encoding="utf-8")
    (second / "b.txt").write_text("b", encoding="utf-8")

    info = sandbox.stat("/home/ai")

    assert info.path == "/home/ai"
    assert info.kind == "directory"
    assert info.exists is True

    entries = sandbox.list_dir("/home/ai")

    assert [entry.path for entry in entries] == [
        "/home/ai/documenti",
        "/home/ai/ebooks",
    ]


def test_alias_paths_are_independent(tmp_path):
    sandbox, first, second = make_alias_sandbox(tmp_path)
    (first / "same.txt").write_text(
        "primo",
        encoding="utf-8",
    )
    (second / "same.txt").write_text(
        "secondo",
        encoding="utf-8",
    )

    assert sandbox.read_file(
        "/home/ai/documenti/same.txt"
    ) == "primo"
    assert sandbox.read_file(
        "/home/ai/ebooks/same.txt"
    ) == "secondo"


def test_alias_lookup_is_case_insensitive(tmp_path):
    sandbox, first, _ = make_alias_sandbox(tmp_path)
    (first / "a.txt").write_text("a", encoding="utf-8")

    assert sandbox.read_file(
        "/home/ai/Documenti/a.txt"
    ) == "a"


def test_virtual_path_cannot_escape_alias(tmp_path):
    sandbox, first, _ = make_alias_sandbox(tmp_path)
    (tmp_path / "outside.txt").write_text(
        "segreto",
        encoding="utf-8",
    )

    with pytest.raises(PermissionError):
        sandbox.read_file(
            "/home/ai/documenti/../outside.txt"
        )


def test_alias_permissions_are_per_mount(tmp_path):
    sandbox, first, second = make_alias_sandbox(tmp_path)

    sandbox.create_file(
        "/home/ai/documenti/a.txt",
        "a",
    )

    with pytest.raises(PermissionError):
        sandbox.create_file(
            "/home/ai/ebooks/b.txt",
            "b",
        )


def test_chdir_requires_execute_permission(tmp_path):
    first = tmp_path / "documenti"
    first.mkdir()
    sandbox = FileSystemSandbox(
        roots={
            first: DirectoryPermissions(
                read=True,
                write=False,
                create=False,
                rename=False,
                delete=False,
                execute=False,
            )
        },
        current_directory=first,
        aliases={"documenti": first},
    )

    with pytest.raises(PermissionError):
        sandbox.chdir("/home/ai/documenti")


def test_chdir_to_virtual_root_is_rejected(tmp_path):
    sandbox, first, _ = make_alias_sandbox(tmp_path)

    with pytest.raises(PermissionError):
        sandbox.chdir("/home/ai")

    sandbox.chdir("/home/ai/documenti")

    assert sandbox.current_directory == first.resolve()


def test_root_search_spans_aliases(tmp_path):
    sandbox, first, second = make_alias_sandbox(tmp_path)
    (first / "a.py").write_text("a", encoding="utf-8")
    (second / "b.py").write_text("b", encoding="utf-8")

    result = sandbox.search("*.py", path="/home/ai")

    assert result["searched_path"] == "/home/ai"
    assert result["total_matches"] == 2
    assert {
        item.path for item in result["results"]
    } == {
        "/home/ai/documenti/a.py",
        "/home/ai/ebooks/b.py",
    }


def test_outside_error_does_not_expose_real_path(
    sandbox,
    workspace,
):
    with pytest.raises(PermissionError) as exc:
        sandbox.read_file(
            str(workspace.parent / "outside.txt")
        )

    assert str(workspace) not in str(exc.value)
