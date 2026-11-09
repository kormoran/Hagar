"""Test della sandbox del filesystem (core/filesystem.py)."""

from __future__ import annotations

import os
import re

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)


def make_sandbox(
    root: Path,
    **permissions: bool,
) -> FileSystemSandbox:

    return FileSystemSandbox(
        roots={
            root: DirectoryPermissions(**permissions)
        },
        current_directory=root,
    )


# =====================================================
# Path resolution
# =====================================================


def test_resolve_relative_path(sandbox, workspace):
    assert sandbox.resolve_path(
        "a.txt"
    ) == (workspace / "a.txt").resolve()


def test_resolve_absolute_path(sandbox, workspace):
    target = workspace / "sub" / "a.txt"
    assert sandbox.resolve_path(str(target)) == target.resolve()


def test_resolve_none_returns_current_directory(
    sandbox,
    workspace,
):
    assert sandbox.resolve_path(None) == workspace.resolve()


def test_parent_path(sandbox, workspace):
    assert sandbox.parent_path(
        "sub/a.txt"
    ) == (workspace / "sub").resolve()


def test_path_exists(sandbox, workspace):
    (workspace / "a.txt").write_text("x", encoding="utf-8")

    assert sandbox.path_exists("a.txt") is True
    assert sandbox.path_exists("missing.txt") is False


def test_find_root(sandbox, workspace, tmp_path):
    root, perms = sandbox.find_root(workspace / "a.txt")

    assert root == workspace.resolve()
    assert perms.read is True
    assert sandbox.find_root(tmp_path) is None


# =====================================================
# Permission resolution
# =====================================================


def test_default_permissions_are_restrictive(tmp_path):
    sandbox = FileSystemSandbox(
        roots={tmp_path: DirectoryPermissions()},
        current_directory=tmp_path,
    )

    effective = sandbox.effective_permissions(
        tmp_path / "a.txt"
    )

    assert effective.read is True
    assert effective.write is False
    assert effective.create is False
    assert effective.delete is False


def test_nested_root_overrides_permissions(tmp_path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    sandbox = FileSystemSandbox(
        roots={
            parent: DirectoryPermissions(
                read=True,
                write=False,
                create=False,
            ),
            child: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
            ),
        },
        current_directory=child,
    )

    assert sandbox.effective_permissions(
        child / "a.txt"
    ).write is True

    assert sandbox.effective_permissions(
        parent / "b.txt"
    ).write is False


def test_outside_sandbox_raises(sandbox, tmp_path):
    with pytest.raises(PermissionError, match="outside sandbox"):
        sandbox.effective_permissions(tmp_path)


def test_none_permissions_inherit_from_outer_root(tmp_path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    sandbox = FileSystemSandbox(
        roots={
            parent: DirectoryPermissions(
                read=False,
                write=True,
            ),
            child: DirectoryPermissions(),
        },
        current_directory=child,
    )

    effective = sandbox.effective_permissions(child)
    assert effective.read is False
    assert effective.write is True


# =====================================================
# Guardian
# =====================================================


def test_guardian_allows_allowed_path(sandbox, workspace):
    assert sandbox.FS_Guardian("read", workspace) == ""


def test_guardian_denies_outside_path(sandbox, tmp_path):
    error = sandbox.FS_Guardian("read", tmp_path)

    assert "outside allowed directories" in error
    assert "relative to the current sandbox" in error


def test_root_absolute_path_is_denied(sandbox):
    with pytest.raises(PermissionError, match="relative"):
        sandbox.read_file("/outside.txt")


def test_guardian_reports_missing_permissions(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=False,
        write=False,
        create=False,
        delete=False,
    )

    assert "Read access denied" in sandbox.FS_Guardian(
        "read",
        tmp_path / "a.txt",
    )
    assert "Write access denied" in sandbox.FS_Guardian(
        "write",
        tmp_path / "a.txt",
    )
    assert "Create access denied" in sandbox.FS_Guardian(
        "create",
        tmp_path / "a.txt",
    )
    assert "Delete access denied" in sandbox.FS_Guardian(
        "delete",
        tmp_path / "a.txt",
    )


def test_disk_space_check(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=True,
        write=True,
    )

    assert sandbox.check_disk_space(
        tmp_path / "a.txt",
        0,
    ) is None

    error = sandbox.check_disk_space(
        tmp_path / "a.txt",
        10**18,
    )

    assert "Insufficient disk space" in error


def test_guardian_reports_disk_space_error(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=True,
        write=True,
    )

    error = sandbox.FS_Guardian(
        "write",
        tmp_path / "a.txt",
        required_space=10**18,
    )

    assert "Insufficient disk space" in error


# =====================================================
# Directory operations
# =====================================================


def test_mkdir_creates_nested_directories(sandbox, workspace):
    sandbox.mkdir("a/b/c")

    assert (workspace / "a" / "b" / "c").is_dir()


def test_mkdir_requires_create_permission(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=True,
        write=True,
        create=False,
    )

    with pytest.raises(PermissionError, match="Create access denied"):
        sandbox.mkdir("sub")


def test_chdir_changes_current_directory(sandbox, workspace):
    (workspace / "sub").mkdir()

    sandbox.chdir("sub")

    assert sandbox.current_directory == (
        workspace / "sub"
    ).resolve()

    assert sandbox.resolve_path("a.txt") == (
        workspace / "sub" / "a.txt"
    ).resolve()


def test_chdir_to_file_raises(sandbox, workspace):
    (workspace / "a.txt").write_text("x", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        sandbox.chdir("a.txt")


def test_chdir_outside_sandbox_raises(sandbox, tmp_path):
    with pytest.raises(PermissionError):
        sandbox.chdir(str(tmp_path))


# =====================================================
# File operations
# =====================================================


def test_read_file(sandbox, workspace):
    (workspace / "a.txt").write_text(
        "contenuto",
        encoding="utf-8",
    )

    assert sandbox.read_file("a.txt") == "contenuto"


def test_read_file_is_utf8(sandbox):
    sandbox.create_file("citta.txt", "città àèìòù")

    assert sandbox.read_file("citta.txt") == "città àèìòù"


def test_read_missing_file_raises(sandbox):
    with pytest.raises(FileNotFoundError):
        sandbox.read_file("missing.txt")


def test_read_directory_raises(sandbox):
    sandbox.mkdir("sub")

    with pytest.raises(FileNotFoundError):
        sandbox.read_file("sub")


def test_read_outside_sandbox_raises(sandbox, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("segreto", encoding="utf-8")

    with pytest.raises(PermissionError, match="outside"):
        sandbox.read_file(str(outside))


def test_traversal_is_denied(sandbox, tmp_path):
    (tmp_path / "outside.txt").write_text(
        "segreto",
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="outside"):
        sandbox.read_file("../outside.txt")


def test_write_file_overwrites(sandbox, workspace):
    (workspace / "a.txt").write_text("vecchio", encoding="utf-8")

    sandbox.read_file("a.txt")
    sandbox.write_file("a.txt", "nuovo")

    assert (workspace / "a.txt").read_text(
        encoding="utf-8"
    ) == "nuovo"


def test_write_file_requires_existing_file(sandbox):
    with pytest.raises(FileNotFoundError):
        sandbox.write_file("nuovo.txt", "x")


def test_write_cannot_bypass_create_permission(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=True,
        write=True,
        create=False,
    )

    with pytest.raises(FileNotFoundError):
        sandbox.write_file("nuovo.txt", "x")


def test_write_denied_without_permission(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=True,
        write=False,
    )

    (tmp_path / "a.txt").write_text("x", encoding="utf-8")

    with pytest.raises(PermissionError, match="Write access denied"):
        sandbox.write_file("a.txt", "y")


def test_create_file(sandbox, workspace):
    sandbox.create_file("nuovo.txt", "contenuto")

    assert (workspace / "nuovo.txt").read_text(
        encoding="utf-8"
    ) == "contenuto"


def test_create_file_default_content_is_empty(sandbox, workspace):
    sandbox.create_file("vuoto.txt")

    assert (workspace / "vuoto.txt").read_text(
        encoding="utf-8"
    ) == ""


def test_create_existing_file_raises(sandbox, workspace):
    (workspace / "a.txt").write_text("x", encoding="utf-8")

    with pytest.raises(FileExistsError):
        sandbox.create_file("a.txt", "y")


def test_create_file_missing_parent_raises(sandbox):
    with pytest.raises(FileNotFoundError):
        sandbox.create_file("missing/a.txt", "x")


def test_create_file_denied_without_permission(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=True,
        write=True,
        create=False,
    )

    with pytest.raises(PermissionError, match="Create access denied"):
        sandbox.create_file("a.txt", "x")


def test_delete_file(sandbox, workspace):
    (workspace / "a.txt").write_text("x", encoding="utf-8")

    sandbox.read_file("a.txt")
    sandbox.delete_file("a.txt")

    assert not (workspace / "a.txt").exists()


def test_delete_missing_file_raises(sandbox):
    with pytest.raises(FileNotFoundError):
        sandbox.delete_file("missing.txt")


def test_delete_directory_raises(sandbox):
    sandbox.mkdir("sub")

    with pytest.raises(IsADirectoryError):
        sandbox.delete_file("sub")


def test_delete_denied_without_permission(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=True,
        delete=False,
    )

    (tmp_path / "a.txt").write_text("x", encoding="utf-8")

    with pytest.raises(PermissionError, match="Delete access denied"):
        sandbox.delete_file("a.txt")


# =====================================================
# Symlinks
# =====================================================


def test_symlink_is_hidden(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    outside = tmp_path / "outside.txt"
    outside.write_text("segreto", encoding="utf-8")

    link = root / "link.txt"

    try:
        link.symlink_to(outside)

    except (OSError, NotImplementedError):
        pytest.skip("symlink non disponibili su questo sistema")

    sandbox = make_sandbox(
        root,
        read=True,
        write=True,
        create=True,
        delete=True,
    )

    with pytest.raises(FileNotFoundError):
        sandbox.read_file("link.txt")


def test_symlink_component_is_rejected_before_resolution(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "link.txt").write_text("x", encoding="utf-8")

    link = root / "link.txt"
    original = Path.is_symlink

    def fake_is_symlink(self):
        return self == link or original(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    sandbox = make_sandbox(
        root,
        read=True,
    )

    with pytest.raises(FileNotFoundError):
        sandbox.read_file("link.txt")


# =====================================================
# Disk info
# =====================================================


def test_free_space_returns_int(sandbox):
    free = sandbox.free_space()

    assert isinstance(free, int)
    assert free > 0


# =====================================================
# Metadata (stat)
# =====================================================

ISO_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"
)


def test_stat_file(sandbox, workspace):
    (workspace / "a.txt").write_text(
        "città",
        encoding="utf-8",
    )

    info = sandbox.stat("a.txt")

    assert info.path == "/home/ai/root/a.txt"
    assert info.exists is True
    assert info.kind == "file"
    assert info.size_bytes == len(
        "città".encode("utf-8")
    )
    assert info.size_bytes == (
        workspace / "a.txt"
    ).stat().st_size
    assert info.permissions["read"] is True


def test_stat_timestamps_are_iso(sandbox, workspace):
    (workspace / "a.txt").write_text("x", encoding="utf-8")

    info = sandbox.stat("a.txt")

    assert ISO_TIMESTAMP.match(info.modified_at)
    assert ISO_TIMESTAMP.match(info.accessed_at)


def test_stat_modification_time(sandbox, workspace):
    target = workspace / "a.txt"
    target.write_text("x", encoding="utf-8")

    timestamp = 1_700_000_000
    os.utime(target, (timestamp, timestamp))

    info = sandbox.stat("a.txt")

    expected = datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).astimezone().isoformat(timespec="seconds")

    assert info.modified_at == expected
    assert info.accessed_at == expected


def test_stat_creation_time(sandbox, workspace):
    (workspace / "a.txt").write_text("x", encoding="utf-8")

    info = sandbox.stat("a.txt")

    if os.name == "nt":
        assert info.created_at is not None
        assert ISO_TIMESTAMP.match(info.created_at)


def test_stat_directory(sandbox):
    sandbox.mkdir("sub")

    info = sandbox.stat("sub")

    assert info.exists is True
    assert info.kind == "directory"
    assert info.size_bytes is None


def test_stat_missing_path(sandbox):
    info = sandbox.stat("missing.txt")

    assert info.exists is False
    assert info.kind is None
    assert info.size_bytes is None
    assert info.created_at is None
    assert info.modified_at is None
    assert info.accessed_at is None

    # I permessi si conoscono comunque: sono quelli della sandbox.
    assert info.permissions["read"] is True
    assert info.permissions["write"] is True


def test_stat_permissions_follow_sandbox(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()

    child = root / "child"
    child.mkdir()

    sandbox = FileSystemSandbox(
        roots={
            root: DirectoryPermissions(
                read=True,
                write=False,
                create=False,
            ),
            child: DirectoryPermissions(
                write=True,
            ),
        },
        current_directory=root,
    )

    info = sandbox.stat("child")

    assert info.permissions == {
        "read": True,
        "write": True,
        "create": False,
        "rename": False,
        "delete": False,
        "execute": False,
    }


def test_stat_read_denied(tmp_path):
    sandbox = make_sandbox(
        tmp_path,
        read=False,
    )

    with pytest.raises(PermissionError, match="Read access denied"):
        sandbox.stat("a.txt")


def test_stat_outside_sandbox_raises(sandbox, tmp_path):
    with pytest.raises(PermissionError):
        sandbox.stat("../outside.txt")
