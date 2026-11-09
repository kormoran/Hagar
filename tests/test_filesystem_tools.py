"""Test dei tool filesystem esposti al modello."""

from __future__ import annotations

import json

import pytest

from core.filesystem import (
    DirectoryPermissions,
    FileSystemSandbox,
)
from core.filesystem_tools import FileSystemToolProvider
from core.models import FileSystemLimits
from core.permissions import (
    ALL_CAPABILITIES,
    Capability,
    Effect,
    PermissionDenied,
    PermissionEvaluator,
    Subject,
)
from core.tool_registry import ToolRegistry

EXPECTED_TOOLS = {
    "filesystem.read_file",
    "filesystem.write_file",
    "filesystem.edit_file",
    "filesystem.create_file",
    "filesystem.mkdir",
    "filesystem.chdir",
    "filesystem.list_dir",
    "filesystem.read_chunk",
    "filesystem.rename",
    "filesystem.copy_file",
    "filesystem.delete_file",
    "filesystem.search",
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


def test_tool_capabilities(registry):
    expected = {
        "filesystem.read_file": Capability.FILESYSTEM_READ,
        "filesystem.write_file": Capability.FILESYSTEM_WRITE,
        "filesystem.edit_file": Capability.FILESYSTEM_WRITE,
        "filesystem.create_file": Capability.FILESYSTEM_CREATE,
        "filesystem.mkdir": Capability.FILESYSTEM_CREATE,
        "filesystem.chdir": Capability.FILESYSTEM_READ,
        "filesystem.list_dir": Capability.FILESYSTEM_READ,
        "filesystem.read_chunk": Capability.FILESYSTEM_READ,
        "filesystem.rename": Capability.FILESYSTEM_WRITE,
        "filesystem.copy_file": Capability.FILESYSTEM_CREATE,
        "filesystem.delete_file": Capability.FILESYSTEM_DELETE,
        "filesystem.search": Capability.FILESYSTEM_READ,
        "filesystem.free_space": Capability.FILESYSTEM_READ,
        "filesystem.stat": Capability.FILESYSTEM_READ,
    }

    for name, capability in expected.items():

        assert registry.get(name).capabilities == capability


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
    assert "/home/ai/root/a.txt" in created
    assert str(workspace) not in created
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
    assert "/home/ai/root/sub" in message
    assert str(workspace) not in message
    assert sandbox.current_directory == (
        workspace / "sub"
    ).resolve()


def test_list_dir_tool_paginates(registry, workspace):
    for name in ("a.txt", "b.txt", "c.txt"):
        registry.execute(
            "filesystem.create_file",
            path=name,
            content="x",
        )

    page = json.loads(
        registry.execute(
            "filesystem.list_dir",
            offset=1,
            limit=1,
        )
    )

    assert page["total_entries"] == 3
    assert page["returned_entries"] == 1
    assert page["next_offset"] == 2
    assert page["has_more"] is True
    assert page["entries"][0]["path"] == "/home/ai/root/b.txt"


def test_edit_file_requires_read_and_rejects_ambiguous_match(
    sandbox,
    workspace,
):
    (workspace / "a.txt").write_text(
        "uno due uno",
        encoding="utf-8",
    )

    with pytest.raises(PermissionError):
        sandbox.edit_file("a.txt", "due", "tre")

    sandbox.read_file("a.txt")

    with pytest.raises(ValueError):
        sandbox.edit_file("a.txt", "uno", "tre")

    assert sandbox.edit_file(
        "a.txt",
        "due",
        "tre",
    ) == 1

    assert (workspace / "a.txt").read_text(
        encoding="utf-8"
    ) == "uno tre uno"
    assert not list(workspace.glob(".*.tmp"))


def test_write_rejects_stale_observation(sandbox, workspace):
    (workspace / "a.txt").write_text("prima", encoding="utf-8")
    sandbox.read_file("a.txt")

    (workspace / "a.txt").write_text("esterno", encoding="utf-8")

    with pytest.raises(PermissionError):
        sandbox.write_file("a.txt", "interno")


def test_edit_file_requires_observation(sandbox, workspace):
    (workspace / "a.txt").write_text("testo", encoding="utf-8")

    with pytest.raises(PermissionError):
        sandbox.edit_file("a.txt", "testo", "nuovo")


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

    assert payload["path"] == "/home/ai/root/a.txt"
    assert str(workspace) not in payload["path"]
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


class RecordingConfirmation:
    def __init__(self, approved=True):
        self.approved = approved
        self.requests = []

    def confirm(self, request):
        self.requests.append(request)
        return self.approved


def make_ask_registry(workspace):
    sandbox = FileSystemSandbox(
        roots={
            workspace: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
                rename=True,
                delete=True,
                execute=True,
            )
        },
        current_directory=workspace,
        aliases={"root": workspace},
        limits=FileSystemLimits(ask_over_bytes=5),
    )

    confirmation = RecordingConfirmation(approved=True)

    registry = ToolRegistry(
        evaluator=PermissionEvaluator(ALL_CAPABILITIES),
        subject=Subject(
            name="assistant",
            default=Effect.ALLOW,
        ),
        confirmation=confirmation,
    )
    FileSystemToolProvider(sandbox).register_tools(registry)

    return registry, confirmation, workspace


def test_ask_over_bytes_asks_once(workspace):
    registry, confirmation, workspace = make_ask_registry(
        workspace
    )

    registry.execute(
        "filesystem.create_file",
        path="a.txt",
        content="123456",
    )

    assert len(confirmation.requests) == 1
    assert "ask_over_bytes" in (
        confirmation.requests[0].reason or ""
    )
    assert (workspace / "a.txt").exists()


def test_ask_over_bytes_denied(workspace):
    registry, confirmation, workspace = make_ask_registry(
        workspace
    )
    confirmation.approved = False

    with pytest.raises(PermissionDenied):
        registry.execute(
            "filesystem.create_file",
            path="a.txt",
            content="123456",
        )

    assert not (workspace / "a.txt").exists()


def test_read_chunk_path_is_virtual(
    registry,
    workspace,
):
    registry.execute(
        "filesystem.create_file",
        path="a.txt",
        content="abcdef",
    )

    payload = json.loads(
        registry.execute(
            "filesystem.read_chunk",
            path="a.txt",
            offset=0,
            length=3,
        )
    )

    assert payload["path"] == "/home/ai/root/a.txt"
    assert str(workspace) not in payload["path"]


def test_copy_and_rename_paths_are_virtual(
    registry,
    workspace,
):
    registry.execute(
        "filesystem.create_file",
        path="a.txt",
        content="a",
    )

    copied = json.loads(
        registry.execute(
            "filesystem.copy_file",
            source="a.txt",
            destination="b.txt",
        )
    )

    assert copied["source"] == "/home/ai/root/a.txt"
    assert copied["destination"] == "/home/ai/root/b.txt"
    assert str(workspace) not in json.dumps(copied)

    renamed = json.loads(
        registry.execute(
            "filesystem.rename",
            source="b.txt",
            destination="c.txt",
        )
    )

    assert renamed["destination"] == "/home/ai/root/c.txt"
    assert str(workspace) not in json.dumps(renamed)


def test_search_paths_are_virtual(registry, workspace):
    registry.execute("filesystem.mkdir", path="sub")
    registry.execute(
        "filesystem.create_file",
        path="sub/a.py",
        content="a",
    )

    payload = json.loads(
        registry.execute(
            "filesystem.search",
            pattern="*.py",
            path="sub",
        )
    )

    assert payload["searched_path"] == "/home/ai/root/sub"
    assert payload["results"][0]["path"] == (
        "/home/ai/root/sub/a.py"
    )
    assert str(workspace) not in json.dumps(payload)
