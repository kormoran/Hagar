"""Test dei tool filesystem esposti al modello."""

from __future__ import annotations

import json

import pytest

from core.filesystem_tools import FileSystemToolProvider
from core.tool_registry import ToolRegistry

EXPECTED_TOOLS = {
    "filesystem.read_file",
    "filesystem.write_file",
    "filesystem.create_file",
    "filesystem.mkdir",
    "filesystem.chdir",
    "filesystem.delete_file",
    "filesystem.free_space",
    "filesystem.stat",
}


@pytest.fixture
def registry(sandbox) -> ToolRegistry:
    registry = ToolRegistry()
    FileSystemToolProvider(sandbox).register_tools(registry)
    return registry


def test_register_tools(registry):
    assert set(registry.tool_names()) == EXPECTED_TOOLS


def test_tools_are_enabled_and_categorized(registry):
    for name in EXPECTED_TOOLS:
        assert registry.is_enabled(name) is True

    assert len(
        registry.tools_by_category("filesystem")
    ) == len(EXPECTED_TOOLS)

    assert registry.get("filesystem.read_file").origin == "local"


def test_read_write_roundtrip_via_registry(
    registry,
    workspace,
):
    created = registry.execute(
        "filesystem.create_file",
        path="a.txt",
        content="ciao",
    )

    assert "created" in created
    assert registry.execute(
        "filesystem.read_file",
        path="a.txt",
    ) == "ciao"

    written = registry.execute(
        "filesystem.write_file",
        path="a.txt",
        content="nuovo",
    )

    assert "written" in written
    assert (workspace / "a.txt").read_text(
        encoding="utf-8"
    ) == "nuovo"


def test_mkdir_and_chdir(registry, workspace, sandbox):
    registry.execute("filesystem.mkdir", path="sub")

    assert (workspace / "sub").is_dir()

    message = registry.execute(
        "filesystem.chdir",
        path="sub",
    )

    assert "sub" in message
    assert sandbox.current_directory == (
        workspace / "sub"
    ).resolve()


def test_delete_file(registry, workspace):
    registry.execute(
        "filesystem.create_file",
        path="a.txt",
        content="x",
    )

    registry.execute("filesystem.delete_file", path="a.txt")

    assert not (workspace / "a.txt").exists()


def test_free_space(registry):
    free = registry.execute("filesystem.free_space")

    assert int(free) > 0


def test_outside_sandbox_is_rejected(registry, workspace, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("segreto", encoding="utf-8")

    with pytest.raises(PermissionError):
        registry.execute(
            "filesystem.read_file",
            path=str(outside),
        )


def test_unknown_parameter_is_rejected(registry):
    with pytest.raises(TypeError):
        registry.execute(
            "filesystem.read_file",
            path="a.txt",
            unexpected=True,
        )


def test_stat_tool(registry, workspace):
    registry.execute(
        "filesystem.create_file",
        path="a.txt",
        content="città",
    )

    payload = json.loads(
        registry.execute(
            "filesystem.stat",
            path="a.txt",
        )
    )

    assert payload["path"] == "a.txt"
    assert payload["exists"] is True
    assert payload["kind"] == "file"
    assert payload["size_bytes"] == len(
        "città".encode("utf-8")
    )
    assert payload["permissions"]["read"] is True
    assert payload["modified_at"] is not None


def test_stat_tool_missing_path(registry):
    payload = json.loads(
        registry.execute(
            "filesystem.stat",
            path="missing.txt",
        )
    )

    assert payload["exists"] is False
    assert payload["kind"] is None
    assert payload["size_bytes"] is None
    assert payload["permissions"]["read"] is True


def test_stat_tool_directory(registry):
    registry.execute("filesystem.mkdir", path="sub")

    payload = json.loads(
        registry.execute(
            "filesystem.stat",
            path="sub",
        )
    )

    assert payload["kind"] == "directory"
    assert payload["size_bytes"] is None


def test_stat_tool_outside_sandbox(registry, tmp_path):
    with pytest.raises(PermissionError):
        registry.execute(
            "filesystem.stat",
            path=str(tmp_path / "outside.txt"),
        )
