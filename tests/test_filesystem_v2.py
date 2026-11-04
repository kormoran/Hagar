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

    entries = sandbox.list_dir(".")["entries"]

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

    entries = sandbox.list_dir("sub")["entries"]

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
    assert result["message"] == (
        "voci: riportate solo le prime 1 di 2"
    )
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


def test_file_and_directory_names_can_contain_spaces(
    sandbox,
    workspace,
):
    (workspace / "my docs").mkdir()
    (workspace / "my docs" / "my file.txt").write_text(
        "contenuto",
        encoding="utf-8",
    )

    assert sandbox.read_file(
        "my docs/my file.txt"
    ) == "contenuto"

    info = sandbox.stat("my docs/my file.txt")

    assert info.path == (
        "/home/ai/root/my docs/my file.txt"
    )

    entries = sandbox.list_dir("my docs")["entries"]

    assert [entry.path for entry in entries] == [
        "/home/ai/root/my docs/my file.txt"
    ]


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

    entries = sandbox.list_dir("/home/ai")["entries"]

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


def test_read_chunk_preserves_utf8(
    sandbox,
    workspace,
):
    (workspace / "a.txt").write_text(
        "èa",
        encoding="utf-8",
    )

    first = sandbox.read_chunk("a.txt", 0, 1)

    assert first["content"] == "è"
    assert first["offset"] == 0
    assert first["length"] == 2
    assert first["next_offset"] == 2
    assert first["has_more"] is True

    second = sandbox.read_chunk(
        "a.txt",
        first["next_offset"],
        1,
    )

    assert second["content"] == "a"
    assert second["has_more"] is False


def test_read_chunk_realigns_inside_utf8(
    sandbox,
    workspace,
):
    (workspace / "a.txt").write_text(
        "è",
        encoding="utf-8",
    )

    result = sandbox.read_chunk("a.txt", 1, 1)

    assert result["offset"] == 0
    assert result["length"] == 2
    assert result["content"] == "è"
    assert result["has_more"] is False


def test_read_file_rejects_larger_than_one_chunk(
    sandbox,
    workspace,
):
    (workspace / "small.txt").write_text(
        "a" * sandbox.CHUNK_SIZE,
        encoding="utf-8",
    )
    (workspace / "large.txt").write_text(
        "a" * (sandbox.CHUNK_SIZE + 1),
        encoding="utf-8",
    )

    assert sandbox.read_file("small.txt") == (
        "a" * sandbox.CHUNK_SIZE
    )

    with pytest.raises(ValueError, match="read_chunk"):
        sandbox.read_file("large.txt")


def test_list_dir_limit_and_message(sandbox, workspace):
    for index in range(105):
        (workspace / f"{index:03}.txt").write_text(
            "x",
            encoding="utf-8",
        )

    result = sandbox.list_dir(".")

    assert result["total_entries"] == 105
    assert result["returned_entries"] == sandbox.MAX_DIR_ENTRIES
    assert result["truncated"] is True
    assert result["message"] == (
        "voci: riportate solo le prime 100 di 105"
    )


def test_symlinks_are_invisible(sandbox, workspace, tmp_path):
    (workspace / "a.txt").write_text(
        "dentro",
        encoding="utf-8",
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("fuori", encoding="utf-8")

    link = workspace / "link.txt"
    linkdir = workspace / "linkdir"

    try:
        link.symlink_to(outside)
        linkdir.symlink_to(
            tmp_path,
            target_is_directory=True,
        )
    except (OSError, NotImplementedError):
        pytest.skip("symlink non disponibili su questo sistema")

    with pytest.raises(FileNotFoundError):
        sandbox.stat("link.txt")

    with pytest.raises(FileNotFoundError):
        sandbox.read_file("link.txt")

    with pytest.raises(FileNotFoundError):
        sandbox.read_chunk("link.txt")

    with pytest.raises(FileNotFoundError):
        sandbox.delete_file("link.txt")

    listing = sandbox.list_dir(".")

    assert [
        entry.path for entry in listing["entries"]
    ] == ["/home/ai/root/a.txt"]

    search = sandbox.search("*")

    assert [
        entry.path for entry in search["results"]
    ] == ["/home/ai/root/a.txt"]

    with pytest.raises(
        FileNotFoundError,
        match="Directory not found",
    ):
        sandbox.chdir("linkdir")
