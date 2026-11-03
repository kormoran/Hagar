"""Test del cablaggio del harness (hagar.py) senza rete."""

from __future__ import annotations

import json

from pathlib import Path

import pytest
import yaml

import hagar
from core.audit import read_entries
from core.config import ConfigError, ConfigLoader
from core.permissions import (
    Capability,
    Effect,
    PermissionDenied,
)
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
    "memory.create_skill",
    "memory.list_skills",
    "memory.get_context",
}

DEFAULT_POLICY = {
    "version": 1,
    "subjects": {
        "assistant": {
            "default": "deny",
            "rules": [
                {
                    "capabilities": [
                        "FILESYSTEM_READ",
                        "FILESYSTEM_WRITE",
                        "FILESYSTEM_CREATE",
                        "FILESYSTEM_DELETE",
                        "MEMORY_READ",
                        "MEMORY_WRITE",
                        "MCP_CALL",
                    ],
                    "effect": "allow",
                }
            ],
        }
    },
}


def write_config(
    tmp_path: Path,
    *,
    write: bool = True,
    mcp_servers=None,
    provider: str = "ollama",
    audit=None,
    policy="permissive",
    memory=None,
    vault_exists: bool = True,
) -> tuple[Path, Path]:

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    vault = tmp_path / "vault"

    if vault_exists:
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

    if memory is not None:
        data["memory"] = memory

    if policy is not None:

        (tmp_path / "policy.yaml").write_text(
            yaml.safe_dump(
                DEFAULT_POLICY if policy == "permissive" else policy
            ),
            encoding="utf-8",
        )

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
    assert harness.agent.memory is harness.memory
    assert harness.memory is not None
    assert harness.memory_error is None
    assert harness.vault.root == tmp_path / "vault"


def test_write_permission_follows_config(tmp_path):
    path, _ = write_config(tmp_path, write=False)
    harness = hagar.build_harness(ConfigLoader.load(path))

    with pytest.raises(PermissionError):
        harness.filesystem.create_file("a.txt")


class RecordingConfirmation:
    def __init__(self, approved=True):
        self.approved = approved
        self.requests = []

    def confirm(self, request):
        self.requests.append(request)
        return self.approved


def test_missing_policy_denies_all(tmp_path):
    path, _ = write_config(tmp_path, policy=None)

    harness = hagar.build_harness(ConfigLoader.load(path))

    assert harness.policy_error is not None
    assert harness.registry.subject.default is Effect.DENY

    with pytest.raises(PermissionDenied):
        harness.registry.execute(
            "filesystem.read_file",
            path="nota.txt",
        )


def test_invalid_policy_denies_all(tmp_path):
    path, _ = write_config(
        tmp_path,
        policy={
            "version": 1,
            "subjects": {
                "assistant": {
                    "rules": [
                        {
                            "capabilities": ["NON_ESISTE"],
                            "effect": "allow",
                        }
                    ]
                }
            },
        },
    )

    harness = hagar.build_harness(ConfigLoader.load(path))

    assert "unknown capability" in harness.policy_error

    events = [
        entry["event"]
        for entry in read_entries(
            tmp_path / "logs" / "audit.jsonl"
        )
    ]

    assert events[0] == "policy.failed"


def test_policy_path_scope(tmp_path):
    path, workspace = write_config(
        tmp_path,
        policy={
            "version": 1,
            "subjects": {
                "assistant": {
                    "default": "deny",
                    "rules": [
                        {
                            "capabilities": ["FILESYSTEM_READ"],
                            "effect": "allow",
                            "paths": ["note"],
                        }
                    ],
                }
            },
        },
    )

    (workspace / "note").mkdir()
    (workspace / "note" / "a.txt").write_text(
        "dentro",
        encoding="utf-8",
    )
    (workspace / "fuori.txt").write_text(
        "fuori",
        encoding="utf-8",
    )

    harness = hagar.build_harness(ConfigLoader.load(path))

    assert harness.registry.execute(
        "filesystem.read_file",
        path="note/a.txt",
    ) == "dentro"

    with pytest.raises(PermissionDenied):
        harness.registry.execute(
            "filesystem.read_file",
            path="fuori.txt",
        )


def test_ask_confirmation_accepts(tmp_path):
    path, workspace = write_config(
        tmp_path,
        policy={
            "version": 1,
            "subjects": {
                "assistant": {
                    "default": "deny",
                    "rules": [
                        {
                            "capabilities": ["FILESYSTEM_CREATE"],
                            "effect": "ask",
                        }
                    ],
                }
            },
        },
    )

    confirmation = RecordingConfirmation(True)

    harness = hagar.build_harness(
        ConfigLoader.load(path),
        confirmation=confirmation,
    )

    harness.registry.execute(
        "filesystem.create_file",
        path="a.txt",
        content="x",
    )

    assert (workspace / "a.txt").exists()
    assert len(confirmation.requests) == 1
    assert confirmation.requests[0].tool == (
        "filesystem.create_file"
    )


def test_ask_confirmation_refuses(tmp_path):
    path, workspace = write_config(
        tmp_path,
        policy={
            "version": 1,
            "subjects": {
                "assistant": {
                    "default": "deny",
                    "rules": [
                        {
                            "capabilities": ["FILESYSTEM_CREATE"],
                            "effect": "ask",
                        }
                    ],
                }
            },
        },
    )

    harness = hagar.build_harness(
        ConfigLoader.load(path),
        confirmation=RecordingConfirmation(False),
    )

    with pytest.raises(
        PermissionDenied,
        match="denied by user",
    ):
        harness.registry.execute(
            "filesystem.create_file",
            path="a.txt",
            content="x",
        )

    assert not (workspace / "a.txt").exists()


def test_main_warns_when_policy_missing(
    tmp_path,
    monkeypatch,
    capsys,
):
    path, _ = write_config(tmp_path, policy=None)

    answers = iter(["quit"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    hagar.main(["--config", str(path)])

    output = capsys.readouterr().out

    assert "DENY ALL" in output
    assert "ATTENZIONE" in output


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
                    capabilities=Capability.MCP_CALL,
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


def test_resolve_config_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("HAGAR_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)

    assert hagar.resolve_config() == tmp_path / "hagar.yaml"


def test_resolve_config_uses_env(tmp_path, monkeypatch):
    target = tmp_path / "custom.yaml"
    monkeypatch.setenv("HAGAR_CONFIG", str(target))

    assert hagar.resolve_config() == target


def test_resolve_config_explicit_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("HAGAR_CONFIG", "ignored.yaml")

    target = tmp_path / "x.yaml"

    assert hagar.resolve_config(str(target)) == target


def test_harness_writes_audit_log(tmp_path):
    path, workspace = write_config(tmp_path)

    harness = hagar.build_harness(ConfigLoader.load(path))

    audit_path = tmp_path / "logs" / "audit.jsonl"

    assert harness.audit.path == audit_path
    assert audit_path.exists()
    assert harness.audit.max_bytes == 5_000_000
    assert harness.audit.include_outputs is True

    entries = read_entries(audit_path)

    assert entries[0]["event"] == "policy.loaded"
    assert entries[0]["path"] == str(tmp_path / "policy.yaml")

    assert entries[1]["event"] == "memory.enabled"

    start = entries[2]

    assert start["event"] == "harness.start"
    assert start["provider"] == "ollama"
    assert start["model"] == "test-model"
    assert start["workspace"] == str(workspace.resolve())
    assert "filesystem.read_file" in start["tools"]
    assert "memory.create_skill" in start["tools"]
    assert start["policy"]["subject"] == "assistant"
    assert start["policy"]["error"] is None
    assert start["memory"]["enabled"] is True


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
        "policy.loaded",
        "memory.enabled",
        "harness.start",
        "turn.start",
        "turn.answer",
        "memory.turn",
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


def test_memory_tools_work_end_to_end(tmp_path):
    path, _ = write_config(tmp_path)

    harness = hagar.build_harness(ConfigLoader.load(path))

    payload = json.loads(
        harness.registry.execute(
            "memory.create_skill",
            title="Test memoria",
            content="Fai questo.",
            kind="procedure",
        )
    )

    assert payload["status"] == "candidate"
    assert payload["id"] == "test-memoria"

    assert (
        tmp_path
        / "vault"
        / "Hagar"
        / "skills"
        / "test-memoria.md"
    ).exists()


def test_memory_disabled_by_config(tmp_path):
    path, _ = write_config(
        tmp_path,
        memory={"enabled": False},
    )

    harness = hagar.build_harness(ConfigLoader.load(path))

    assert harness.memory is None
    assert harness.memory_error is None
    assert "memory.create_skill" not in (
        harness.registry.tool_names()
    )


def test_memory_disabled_when_vault_missing(tmp_path):
    path, _ = write_config(
        tmp_path,
        vault_exists=False,
    )

    harness = hagar.build_harness(ConfigLoader.load(path))

    assert harness.memory is None
    assert "Vault not found" in harness.memory_error

    assert "memory.create_skill" not in (
        harness.registry.tool_names()
    )

    events = [
        entry["event"]
        for entry in read_entries(
            tmp_path / "logs" / "audit.jsonl"
        )
    ]

    assert "memory.disabled" in events


def test_turn_is_stored_in_the_vault(tmp_path):
    path, _ = write_config(tmp_path)

    harness = hagar.build_harness(ConfigLoader.load(path))

    class StubLLM:
        def request_tool_call(self, messages, registry):
            return ToolCall(tool=None, arguments={})

        def chat(self, messages):
            return "risposta"

    harness.agent.llm = StubLLM()

    assert harness.agent.ask("domanda") == "risposta"

    files = list(
        (
            tmp_path
            / "vault"
            / "Hagar"
            / "chat"
        ).glob("*.md")
    )

    assert len(files) == 1

    text = files[0].read_text(encoding="utf-8")

    assert "**Utente:** domanda" in text
    assert "**Hagar:** risposta" in text


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
    policy_error = None
    memory = None
    memory_error = None


def test_main_prints_tools_and_exits(tmp_path, monkeypatch, capsys):
    path, _ = write_config(tmp_path)

    monkeypatch.setattr(
        hagar,
        "build_harness",
        lambda config, **kwargs: FakeHarness(),
    )

    answers = iter(["quit"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    hagar.main(["--config", str(path)])

    output = capsys.readouterr().out

    assert "Harness ready." in output
    assert "filesystem.read_file" in output


def test_main_answers_questions(tmp_path, monkeypatch, capsys):
    path, _ = write_config(tmp_path)

    monkeypatch.setattr(
        hagar,
        "build_harness",
        lambda config, **kwargs: FakeHarness(),
    )

    answers = iter(["ciao", "EXIT"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    hagar.main(["--config", str(path)])

    output = capsys.readouterr().out

    assert "echo: ciao" in output


def test_main_handles_eof(tmp_path, monkeypatch):
    path, _ = write_config(tmp_path)

    monkeypatch.setattr(
        hagar,
        "build_harness",
        lambda config, **kwargs: FakeHarness(),
    )

    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    # Non deve propagare l'eccezione.
    hagar.main(["--config", str(path)])


def test_main_reports_configuration_errors(
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    path, _ = write_config(tmp_path, provider="claude")

    with pytest.raises(SystemExit) as excinfo:
        hagar.main(["--config", str(path)])

    assert excinfo.value.code == 1

    stderr = capsys.readouterr().err

    assert "Errore di configurazione" in stderr
    assert "ANTHROPIC_API_KEY" in stderr


def test_main_cli_overrides(tmp_path, monkeypatch):
    path, _ = write_config(tmp_path)

    captured = {}

    def fake_build(config, **kwargs):
        captured["model"] = config.model.name
        captured["memory"] = config.memory.enabled
        captured["native"] = config.model.native_tools
        return FakeHarness()

    monkeypatch.setattr(hagar, "build_harness", fake_build)

    answers = iter(["quit"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(answers),
    )

    hagar.main(
        [
            "--config",
            str(path),
            "--model",
            "override-model",
            "--no-memory",
            "--no-native-tools",
        ]
    )

    assert captured == {
        "model": "override-model",
        "memory": False,
        "native": False,
    }


def test_main_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        hagar.main(["--version"])

    assert excinfo.value.code == 0
    assert "hagar 0.2.0" in capsys.readouterr().out
