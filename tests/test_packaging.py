"""Test dei metadati di packaging."""

from __future__ import annotations

import tomllib

from pathlib import Path

import hagar

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def project() -> dict:

    return tomllib.loads(
        PYPROJECT.read_text(encoding="utf-8")
    )


def test_version_matches_pyproject():
    assert hagar.__version__ == project()["project"]["version"]


def test_console_script_entry_point():
    scripts = project()["project"]["scripts"]

    assert scripts["hagar"] == "hagar:main"


def test_declared_packages():
    setuptools = project()["tool"]["setuptools"]

    assert setuptools["py-modules"] == ["hagar"]
    assert set(setuptools["packages"]) == {
        "core",
        "llm",
        "memory",
    }


def test_dependencies_are_declared():
    dependencies = project()["project"]["dependencies"]

    assert any(
        item.startswith("pyyaml")
        for item in dependencies
    )
    assert any(
        item.startswith("requests")
        for item in dependencies
    )


def test_cli_parser_has_core_options():
    parser = hagar.build_parser()

    options = {
        action.dest
        for action in parser._actions
    }

    assert {
        "config",
        "model",
        "no_memory",
        "no_native_tools",
        "version",
    } <= options
