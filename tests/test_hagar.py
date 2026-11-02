"""Test del cablaggio del harness (hagar.py) senza rete."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import hagar
from core.audit import read_entries
from core.config import ConfigError, ConfigLoader
from core.tool_call import ToolCall
from core.tool_definition import ToolDefinition
from llm.deepseek_client import DeepSeekClient

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


def write_config(
    tmp_path: Path,
    *,
    write: bool = True,
    mcp_servers=None,
    provider: str = "ollama",
    audit=None,
) -> tuple[Path, Path]:

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    vault = tmp_path / "vault"
    vault.mkdir()

    data = {
        "model": {
            "provider": provider,
            "host": "http://localhost:11434",
            "name": "test-model",
        },
        "vault": {"path": str(vault)},
        "filesystem": {"allowed": [str(workspace)]},
        "permissions": {
            "read": True,
            "write": write,
            "shell": False,
        },
    }

    if mcp_servers is not None:
        data["mcp_servers"] = mcp_servers

    if audit is not None:
        data["audit"] = audit

    path = tmp_path / "hagar.yaml"
    path.write_text(
        yaml.safe_dump(data),
        encoding="utf-8",
    )

    return path, workspace


def test_build_harness_wires_all_components(tmp_path):
    path, workspace = write_config(tmp_path)
    config = ConfigLoader.load(path)

    harness = hagar.build_harness(config)

    assert set(harness.registry.tool_names()) == EXPECTED_TOOLS
    assert harness.filesystem.current_directory == (
        workspace.resolve()
    )
    assert harness.llm.host == "http://localhost:11434"
    assert harness.llm.model == "test-model"
    assert harness.agent.llm is harness.llm
    assert harness.agent.tools is harness.registry
    assert harness.agent.vault is harness.vault
    assert harness.vault.root == tmp_path / "vault"


def test_write_permission_follows_config(tmp_path):
    path, _ = write_config(tmp_path, write=False)
    harness = hagar.build_harness(ConfigLoader.load(path))

    with pytest.raises(PermissionError):
        harness.filesystem.create_file("a.txt")


def test_filesystem_tool_works_end_to_end(tmp_path):
    path, workspace = write_config(tmp_path)
    harness = hagar.build_harness(ConfigLoader.load(path))

    harness.registry.execute(
        "filesystem.create_file",
        path="nota.txt",
        content="ciao",
    )

    assert (workspace / "nota.txt").read_text(
        encoding="utf-8"
    ) == "ciao"

    assert harness.registry.execute(
        "filesystem.read_file",
        path="nota.txt",
    ) == "ciao"


def test_mcp_failure_is_isolated(tmp_path, capsys):
    path, workspace = write_config(
        tmp_path,
        mcp_servers=[
            {
                "endpoint": "http://localhost:9999/mcp",
                "namespace": "gh",
            }
        ],
    )

    def factory(endpoint, namespace):
        raise RuntimeError("connessione rifiutata")

    harness = hagar.build_harness(
        ConfigLoader.load(path),
        mcp_client_factory=factory,
    )

    assert set(harness.registry.tool_names()) == EXPECTED_TOOLS

    output = capsys.readouterr().out

    assert "Failed to load MCP server" in output
    assert "connessione rifiutata" in output


def test_successful_mcp_registration(tmp_path):
    path, _ = write_config(
        tmp_path,
        mcp_servers=[
            {
                "endpoint": "http://localhost:9999/mcp",
                "namespace": "gh",
            }
        ],
    )

    class FakeMCP:
        def __init__(self, endpoint, namespace):
            self.namespace = namespace

        def register_tools(self, registry):
            registry.register(
                ToolDefinition(
                    name=f"mcp.{self.namespace}.ping",
                    description="Ping",
                    category="mcp",
                    origin=f"mcp.{self.namespace}",
                    handler=lambda: "pong",
                )
            )

    harness = hagar.build_harness(
        ConfigLoader.load(path),
        mcp_client_factory=FakeMCP,
    )

    assert "mcp.gh.ping" in harness.registry.tool_names()
    assert harness.registry.execute("mcp.gh.ping") == "pong"


def test_config_path_points_to_project_file():
    assert hagar.CONFIG_PATH.name == "hagar.yaml"
    assert hagar.CONFIG_PATH.parent == Path(
        hagar.__file__
    ).parent


def test_harness_writes_audit_log(tmp_path):
    path, workspace = write_config(tmp_path)

    harness = hagar.build_harness(ConfigLoader.load(path))

    audit_path = tmp_path / "logs" / "audit.jsonl"

    assert harness.audit.path == audit_path
    assert audit_path.exists()

    entries = read_entries(audit_path)

    assert entries[0]["event"] == "harness.start"
    assert entries[0]["provider"] == "ollama"
    assert entries[0]["model"] == "test-model"
    assert entries[0]["workspace"] == str(workspace.resolve())
    assert "filesystem.read_file" in entries[0]["tools"]


def test_audit_can_be_disabled(tmp_path):
    path, _ = write_config(
        tmp_path,
        audit={"enabled": False},
    )

    harness = hagar.build_harness(ConfigLoader.load(path))

    assert harness.audit.enabled is False
    assert not (tmp_path / "logs" / "audit.jsonl").exists()


def test_agent_turn_is_audited(tmp_path):
    path, _ = write_config(tmp_path)

    harness = hagar.build_harness(ConfigLoader.load(path))

    class StubLLM:
        def request_tool_call(self, messages, registry):
            return ToolCall(tool=None, arguments={})

        def chat(self, messages):
            return "risposta"

    harness.agent.llm = StubLLM()

    assert harness.agent.ask("ciao") == "risposta"

    events = [
        entry["event"]
        for entry in read_entries(
            tmp_path / "logs" / "audit.jsonl"
        )
    ]

    assert events == [
        "harness.start",
        "turn.start",
        "turn.answer",
    ]


def test_deepseek_provider_is_selected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    path, _ = write_config(tmp_path, provider="deepseek")

    harness = hagar.build_harness(ConfigLoader.load(path))

    assert isinstance(harness.llm, DeepSeekClient)
    assert harness.llm.api_key == "sk-test"


def test_missing_api_key_is_audited(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    path, _ = write_config(tmp_path, provider="claude")

    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        hagar.build_harness(ConfigLoader.load(path))

    entries = read_entries(
        tmp_path / "logs" / "audit.jsonl"
    )

    assert entries[-1]["event"] == "llm.failed"
    assert "ANTHROPIC_API_KEY" in entries[-1]["error"]


class FakeRegistry:
    def tool_names(self):
        return ["filesystem.read_file"]


class FakeAgent:
    def ask(self, question):
        return f"echo: {question}"


class FakeAudit:
    enabled = True
    path = "logs/audit.jsonl"

    def __init__(self):
        self.entries = []

    def record(self, event, **fields):
        entry = {"event": event, **fields}
        self.entries.append(entry)
        return entry


class FakeHarness:
    registry = FakeRegistry()
    agent = FakeAgent()
    audit = FakeAudit()


def test_main_prints_tools_and_exits(tmp_path, monkeypatch, capsys):
    path, _ = write_config(tmp_path)

    monkeypatch.setattr(hagar, "CONFIG_PATH", path)
    monkeypatch.setattr(
        hagar,
        "build_harness",
        lambda config: FakeHarness(),
    )

    answers = iter(["quit"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    hagar.main()

    output = capsys.readouterr().out

    assert "Harness ready." in output
    assert "filesystem.read_file" in output


def test_main_answers_questions(tmp_path, monkeypatch, capsys):
    path, _ = write_config(tmp_path)

    monkeypatch.setattr(hagar, "CONFIG_PATH", path)
    monkeypatch.setattr(
        hagar,
        "build_harness",
        lambda config: FakeHarness(),
    )

    answers = iter(["ciao", "EXIT"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    hagar.main()

    output = capsys.readouterr().out

    assert "echo: ciao" in output


def test_main_handles_eof(tmp_path, monkeypatch):
    path, _ = write_config(tmp_path)

    monkeypatch.setattr(hagar, "CONFIG_PATH", path)
    monkeypatch.setattr(
        hagar,
        "build_harness",
        lambda config: FakeHarness(),
    )

    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    # Non deve propagare l'eccezione.
    hagar.main()


def test_main_reports_configuration_errors(
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    path, _ = write_config(tmp_path, provider="claude")
    monkeypatch.setattr(hagar, "CONFIG_PATH", path)

    with pytest.raises(SystemExit) as excinfo:
        hagar.main()

    assert excinfo.value.code == 1

    stderr = capsys.readouterr().err

    assert "Errore di configurazione" in stderr
    assert "ANTHROPIC_API_KEY" in stderr
