"""Fixture condivise dalla suite.

Il path del progetto viene inserito in ``sys.path`` anche quando i test
vengono lanciati da una directory diversa dalla radice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.filesystem import (  # noqa: E402
    DirectoryPermissions,
    FileSystemSandbox,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Radice scrivibile della sandbox."""

    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def sandbox(workspace: Path) -> FileSystemSandbox:
    """Sandbox con tutti i permessi sulla radice temporanea."""

    return FileSystemSandbox(
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
    )
