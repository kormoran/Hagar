"""Test dei comandi di console /help, /tools, /status, /mcp, /audit."""

from __future__ import annotations

import json

from pathlib import Path
from types import SimpleNamespace

from core.console_commands import ConsoleCommands
from core.permissions import Capability
from core.tool_definition import ToolDefinition


def tool(
    name: str,
    category: str,
    origin: str = "local",
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=name,
        category=category,
        capabilities=Capability.COMPUTE,
        origin=origin,
        handler=lambda: "",
    )


class FakeRegistry:
    def __init__(self, tools):
        self.tools = tools

    def list_definitions(self):
        return self.tools


class FakeMemory:
    STATUSES = ("candidate", "confirmed", "archived")

    def __init__(self):
        self.vault = SimpleNamespace(
            list_files=lambda path, pattern: [],
        )
        self.chat_dir = Path("chat")
        self.summaries_dir = Path("summaries")
        self.archive_chat_dir = Path("archive")

    def list_skills(self, status=None, limit=1000):
        return {
            "candidate": [1],
            "confirmed": [1, 2],
            "archived": [],
        }[status]


class FakeProjectStore:
    def get_project(self, project_id):
        return SimpleNamespace(
            id=project_id,
            title="Hagar",
            active_decisions=3,
        )


def make_harness(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        "\n".join(
            json.dumps(entry)
            for entry in [
                {
                    "ts": "2026-11-06T00:00:00+00:00",
                    "event": "turn.start",
                    "turn": "t1",
                },
                {
                    "ts": "2026-11-06T00:00:01+00:00",
                    "event": "tool.call",
                    "turn": "t1",
                    "tool": "clock.now",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = SimpleNamespace(
        model=SimpleNamespace(
            provider="ollama",
            name="llama3.1:latest",
        ),
        policy=SimpleNamespace(
            path=Path("policy.yaml"),
            subject="assistant",
        ),
        vault=SimpleNamespace(path=Path("vault")),
        memory=SimpleNamespace(vault_subdir="Hagar"),
        mcp_servers=[
            SimpleNamespace(
                namespace="atlassian",
                endpoint="https://mcp.example/mcp",
            )
        ],
    )

    return SimpleNamespace(
        config=config,
        audit=SimpleNamespace(
            enabled=True,
            path=audit_path,
            session_id="session-1",
        ),
        llm=SimpleNamespace(
            supports_native_tools=True,
            native_tools=True,
        ),
        registry=FakeRegistry(
            [
                tool("clock.now", "clock"),
                tool("text.diff", "text"),
                tool(
                    "mcp.atlassian.search",
                    "mcp",
                    origin="mcp.atlassian",
                ),
            ]
        ),
        memory=FakeMemory(),
        filesystem=SimpleNamespace(
            current_directory=Path("/workspace"),
            aliases={"root": Path("/workspace")},
        ),
        project_id="hagar",
        project_store=FakeProjectStore(),
        policy_error=None,
    )


def test_help_lists_commands(tmp_path, capsys):
    commands = ConsoleCommands(make_harness(tmp_path))

    assert commands.handle("/help") is True

    output = capsys.readouterr().out

    for command in (
        "/help",
        "/tools",
        "/status",
        "/mcp",
        "/audit",
        "/project",
        "/memory",
    ):
        assert command in output


def test_tools_groups_by_category(tmp_path, capsys):
    commands = ConsoleCommands(make_harness(tmp_path))

    commands.handle("/tools")

    output = capsys.readouterr().out

    assert "Tool disponibili: 3" in output
    assert "[clock]" in output
    assert "clock.now" in output
    assert "think.echo" not in output


def test_tools_can_filter_category(tmp_path, capsys):
    commands = ConsoleCommands(make_harness(tmp_path))

    commands.handle("/tools mcp")

    output = capsys.readouterr().out

    assert "mcp.atlassian.search" in output
    assert "clock.now" not in output


def test_status_reports_session_and_memory(tmp_path, capsys):
    commands = ConsoleCommands(make_harness(tmp_path))

    commands.handle("/status")

    output = capsys.readouterr().out

    assert "Sessione: session-1" in output
    assert "ollama / llama3.1:latest" in output
    assert "Progetto: Hagar [hagar]" in output
    assert "candidate=1" in output
    assert "confirmed=2" in output
    assert "Audit:" in output


def test_mcp_lists_server_and_tools(tmp_path, capsys):
    commands = ConsoleCommands(make_harness(tmp_path))

    commands.handle("/mcp")

    output = capsys.readouterr().out

    assert "Server MCP configurati: 1" in output
    assert "tool importati: 1" in output
    assert "[atlassian]" in output
    assert "mcp.atlassian.search" in output


def test_audit_shows_last_events(tmp_path, capsys):
    commands = ConsoleCommands(make_harness(tmp_path))

    commands.handle("/audit 1")

    output = capsys.readouterr().out

    assert "Ultimi 1 eventi" in output
    assert "tool.call" in output
    assert "tool=clock.now" in output
    assert "turn.start" not in output


def test_unknown_slash_command_is_not_sent_to_model(tmp_path, capsys):
    commands = ConsoleCommands(make_harness(tmp_path))

    assert commands.handle("/nope") is True

    assert "Comando sconosciuto" in capsys.readouterr().out
    assert commands.handle("ciao") is False
