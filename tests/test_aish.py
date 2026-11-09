"""Test di AIsh: linguaggio, policy e comandi whitelisted."""

from __future__ import annotations

import json

import pytest

from core.aish import AishError
from core.filesystem_tools import FileSystemToolProvider
from core.permissions import (
    ALL_CAPABILITIES,
    Effect,
    PermissionEvaluator,
    Subject,
)
from core.tool_registry import ToolRegistry
from local_tools.aish_tool import AishToolProvider


@pytest.fixture
def aish_registry(sandbox):
    registry = ToolRegistry(
        evaluator=PermissionEvaluator(ALL_CAPABILITIES),
        subject=Subject(
            name="assistant",
            default=Effect.ALLOW,
        ),
    )
    FileSystemToolProvider(sandbox).register_tools(registry)
    AishToolProvider(registry, sandbox).register_tools(registry)
    return registry


def run(registry, script):
    return json.loads(
        registry.execute("aish.exec", script=script)
    )


def test_aish_pwd_and_echo(aish_registry):
    result = run(aish_registry, "pwd")

    assert result["success"] is True
    assert result["stdout"] == "/home/ai/root\n"

    result = run(aish_registry, "echo ciao mondo")

    assert result["stdout"] == "ciao mondo\n"


def test_aish_read_and_pipeline(aish_registry, workspace):
    (workspace / "a.txt").write_text(
        "uno\ndue\ntre\n",
        encoding="utf-8",
    )

    result = run(aish_registry, "cat a.txt | grep due | wc -l")

    assert result["stdout"] == "1\n"
    assert [item["command"] for item in result["commands"]] == [
        "cat",
        "grep",
        "wc",
    ]


def test_aish_rejects_redirection_and_host_commands(aish_registry):
    with pytest.raises(AishError):
        aish_registry.execute(
            "aish.exec",
            script="echo x > a.txt",
        )

    with pytest.raises(AishError):
        aish_registry.execute(
            "aish.exec",
            script="bash -c whoami",
        )


def test_aish_rm_requires_prior_read(aish_registry, workspace):
    (workspace / "a.txt").write_text("x", encoding="utf-8")

    with pytest.raises(Exception, match="non è stato letto"):
        aish_registry.execute(
            "aish.exec",
            script="rm a.txt",
        )

    run(aish_registry, "cat a.txt")
    result = run(aish_registry, "rm a.txt")

    assert result["success"] is True
    assert not (workspace / "a.txt").exists()


def test_aish_rejects_mutation_in_pipeline(aish_registry):
    with pytest.raises(AishError):
        aish_registry.execute(
            "aish.exec",
            script="echo x | rm y",
        )
