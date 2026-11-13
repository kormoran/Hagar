"""Test del servizio amministrativo della GUI."""

from __future__ import annotations

import yaml

from pathlib import Path

import pytest

import core.admin as admin_module

from core.admin import AdminError, AdminService
from core.config import ConfigError, ConfigLoader
from hagar import build_harness
from llm.broker_client import BrokerLLMClient


def write_config(
    tmp_path: Path,
    broker: bool = False,
) -> Path:

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    vault = tmp_path / "vault"
    vault.mkdir()

    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "version: 1\n"
        "subjects:\n"
        "  assistant:\n"
        "    default: allow\n",
        encoding="utf-8",
    )

    if broker:

        catalog = tmp_path / "models.yaml"
        catalog.write_text(
            "version: 1\n"
            "models:\n"
            "  - id: ollama/qwen3-8b\n"
            "    provider: ollama\n"
            "    model: qwen3:8b\n"
            "    context_window: 32768\n"
            "    capabilities:\n"
            "      - chat\n"
            "      - tool_calling\n"
            "      - native_tools\n"
            "    locality: local\n"
            "    quality: 0.8\n"
            "    cost_per_1k_input: 0\n"
            "    cost_per_1k_output: 0\n"
            "    enabled: true\n",
            encoding="utf-8",
        )

        profiles = tmp_path / "profiles.yaml"
        profiles.write_text(
            "version: 1\n"
            "profiles:\n"
            "  coding:\n"
            "    required_capabilities:\n"
            "      - chat\n"
            "    privacy: any\n"
            "    prefer: quality\n",
            encoding="utf-8",
        )

    data = {
        "model": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "name": "qwen3:8b",
            "native_tools": True,
            "timeout": 120,
            "max_tokens": 1024,
        },
        "audit": {"enabled": False},
        "policy": {
            "path": str(policy),
            "subject": "assistant",
        },
        "vault": {"path": str(vault)},
        "memory": {"enabled": False},
        "filesystem": {
            "sandbox": [
                {
                    "alias": "workspace",
                    "path": str(workspace),
                    "permissions": "RWX",
                }
            ],
        },
        "permissions": {
            "read": True,
            "write": True,
            "shell": False,
            "network": False,
        },
        "hifi": {
            "enabled": False,
            "margin": 0.2,
            "interpretations": 3,
        },
        "tools": {
            "timeout": 120,
            "repeat_limit": 3,
        },
    }

    if broker:

        data["broker"] = {
            "enabled": True,
            "catalog": str(catalog),
            "profiles": str(profiles),
            "default_profile": "coding",
            "loaded_only": False,
        }

    path = tmp_path / "hagar.yaml"
    path.write_text(
        yaml.safe_dump(data),
        encoding="utf-8",
    )

    return path


def make_admin(
    tmp_path: Path,
    monkeypatch,
    broker: bool = False,
):

    config = ConfigLoader.load(
        write_config(tmp_path, broker=broker)
    )

    monkeypatch.setattr(
        admin_module,
        "model_catalog",
        lambda config, force=False: {
            "current": {
                "provider": config.model.provider,
                "name": config.model.name,
            },
            "providers": [],
        },
    )

    harness = build_harness(config)

    return (
        AdminService(harness),
        harness,
        config,
    )


def settings_dict(
    service: AdminService,
) -> dict:

    return {
        field["key"]: field["value"]
        for group in service.settings()["groups"]
        for field in group["fields"]
    }


def test_config_path_is_available(tmp_path, monkeypatch):

    _, _, config = make_admin(
        tmp_path,
        monkeypatch,
    )

    assert config.config_path is not None
    assert config.config_path.is_file()


def test_tools_list_and_toggle(tmp_path, monkeypatch):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    tools = {
        item["name"]: item
        for item in service.tools()
    }

    assert "calculator.evaluate" in tools
    assert tools["calculator.evaluate"]["enabled"] is True

    updated = service.set_tool(
        "calculator.evaluate",
        False,
    )

    assert updated["enabled"] is False
    assert (
        harness.registry.get(
            "calculator.evaluate"
        ).enabled
        is False
    )

    updated = service.set_tool(
        "calculator.evaluate",
        True,
    )

    assert updated["enabled"] is True


def test_unknown_tool_is_rejected(tmp_path, monkeypatch):

    service, _, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(AdminError):
        service.set_tool("missing.tool", False)


def test_settings_update_and_apply(tmp_path, monkeypatch):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    values = settings_dict(service)

    values.update(
        {
            "hifi.enabled": True,
            "hifi.margin": 0.3,
            "hifi.interpretations": 4,
            "tools.timeout": 7,
            "tools.repeat_limit": 2,
            "model.timeout": 33,
            "model.max_tokens": 512,
            "model.native_tools": False,
            "filesystem.max_write_bytes": 10,
            "filesystem.min_free_bytes": 20,
            "filesystem.session_write_bytes": 30,
            "filesystem.ask_over_bytes": 5,
            "memory.context_turns": 2,
            "memory.context_skills": 1,
            "memory.max_context_chars": 5000,
        }
    )

    service.update_settings(values)

    assert harness.config.hifi.enabled is True
    assert harness.agent.hifi is not None
    assert harness.agent.hifi.margin == 0.3
    assert harness.agent.hifi.interpretations == 4
    assert harness.registry.default_timeout == 7
    assert harness.registry.repeat_limit == 2
    assert harness.config.model.timeout == 33
    assert harness.config.model.max_tokens == 512
    assert harness.llm.native_tools is False
    assert harness.filesystem.limits.max_write_bytes == 10
    assert harness.filesystem.limits.min_free_bytes == 20
    assert harness.filesystem.limits.session_write_bytes == 30
    assert harness.filesystem.limits.ask_over_bytes == 5
    assert harness.config.memory.context_turns == 2
    assert harness.config.memory.context_skills == 1
    assert harness.agent.max_context_chars == 5000

    updated = settings_dict(service)

    assert updated["hifi.enabled"] is True
    assert updated["tools.timeout"] == 7
    assert updated["filesystem.max_write_bytes"] == 10


def test_invalid_setting_does_not_change_state(
    tmp_path,
    monkeypatch,
):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    values = settings_dict(service)
    values["hifi.margin"] = 2.0

    with pytest.raises(AdminError):
        service.update_settings(values)

    assert harness.config.hifi.margin == 0.2


def test_unknown_setting_is_rejected(tmp_path, monkeypatch):

    service, _, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(AdminError):
        service.update_settings(
            {"filesystem.unknown": 1}
        )


def test_reset_from_hagar_yaml(tmp_path, monkeypatch):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    values = settings_dict(service)
    values["hifi.enabled"] = True
    values["tools.timeout"] = 1
    service.update_settings(values)
    service.set_tool("calculator.evaluate", False)

    service.reset_from_config()

    assert harness.config.hifi.enabled is False
    assert harness.agent.hifi is None
    assert harness.registry.default_timeout == 120
    assert harness.config.tools.timeout == 120
    assert harness.registry.get(
        "calculator.evaluate"
    ).enabled is True


def test_change_model_same_provider(tmp_path, monkeypatch):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    service.change_model(
        "ollama",
        "llama3.1:latest",
    )

    assert harness.config.model.provider == "ollama"
    assert harness.config.model.name == "llama3.1:latest"
    assert harness.llm.model == "llama3.1:latest"
    assert harness.agent.llm is harness.llm
    assert harness.llm is not None


def test_change_model_unknown_provider(tmp_path, monkeypatch):

    service, _, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(AdminError):
        service.change_model(
            "does-not-exist",
            "model",
        )


def test_change_model_missing_api_key_is_atomic(
    tmp_path,
    monkeypatch,
):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )

    before = harness.llm

    with pytest.raises(ConfigError):
        service.change_model(
            "openai",
            "gpt-4o",
        )

    assert harness.config.model.provider == "ollama"
    assert harness.llm is before


def test_sandbox_tree_and_permissions(
    tmp_path,
    monkeypatch,
):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    workspace = (
        tmp_path / "workspace"
    )
    sub = workspace / "sub"
    sub.mkdir()

    listing = service.sandbox_list(
        "/home/ai/workspace"
    )

    assert listing["path"] == "/home/ai/workspace"
    assert listing["real_path"] == str(
        workspace.resolve()
    )
    names = {
        item["name"]
        for item in listing["entries"]
    }
    assert "sub" in names

    result = service.sandbox_set_permissions(
        "/home/ai/workspace/sub",
        read=True,
        write=False,
        execute=True,
    )

    assert result["permissions"]["read"] is True
    assert result["permissions"]["write"] is False
    assert result["permissions"]["execute"] is True

    permissions = harness.filesystem.effective_permissions(
        sub
    )

    assert permissions.read is True
    assert permissions.write is False
    assert permissions.create is False
    assert permissions.rename is False
    assert permissions.delete is False
    assert permissions.execute is True


def test_sandbox_mkdir_and_no_delete(
    tmp_path,
    monkeypatch,
):

    service, _, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    workspace = tmp_path / "workspace"

    entry = service.sandbox_mkdir(
        "/home/ai/workspace",
        "new-folder",
    )

    assert entry["kind"] == "directory"
    assert (
        workspace / "new-folder"
    ).is_dir()

    with pytest.raises(AdminError):
        service.sandbox_mkdir(
            "/home/ai",
            "at-root",
        )

    with pytest.raises(AdminError):
        service.sandbox_mkdir(
            "/home/ai/workspace",
            "../escape",
        )


def test_reset_clears_sandbox_overrides(
    tmp_path,
    monkeypatch,
):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    workspace = tmp_path / "workspace"

    service.sandbox_set_permissions(
        "/home/ai/workspace",
        read=True,
        write=False,
        execute=True,
    )

    assert (
        harness.filesystem.effective_permissions(
            workspace
        ).write
        is False
    )

    service.reset_from_config()

    assert (
        harness.filesystem.effective_permissions(
            workspace
        ).write
        is True
    )


def test_control_payload(tmp_path, monkeypatch):

    service, _, _ = make_admin(
        tmp_path,
        monkeypatch,
    )

    payload = service.control()

    assert "tools" in payload
    assert "model" in payload
    assert "settings" in payload
    assert payload["settings"]["config_path"]


def test_broker_state_and_direct_change_is_refused(
    tmp_path,
    monkeypatch,
):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
        broker=True,
    )

    assert isinstance(
        harness.llm,
        BrokerLLMClient,
    )

    state = service.model_state()

    assert state["broker"]["enabled"] is True
    assert state["broker"]["profile"] == "coding"
    assert state["broker"]["selection"] is not None
    assert (
        state["broker"]["selection"]["provider"]
        == "ollama"
    )
    assert (
        state["broker"]["selection"]["model"]
        == "qwen3:8b"
    )

    with pytest.raises(
        AdminError,
        match="broker",
    ):
        service.change_model(
            "ollama",
            "llama3.1:latest",
        )


def test_broker_reset_keeps_broker_client(
    tmp_path,
    monkeypatch,
):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
        broker=True,
    )

    before = harness.llm

    service.reset_from_config()

    assert isinstance(
        harness.llm,
        BrokerLLMClient,
    )
    assert harness.llm is not None
    assert before is not None


def test_broker_model_settings_update_client(
    tmp_path,
    monkeypatch,
):

    service, harness, _ = make_admin(
        tmp_path,
        monkeypatch,
        broker=True,
    )

    values = settings_dict(service)
    values["model.timeout"] = 42
    values["model.max_tokens"] = 256

    service.update_settings(values)

    assert harness.llm.timeout == 42
    assert harness.llm.max_tokens == 256
    assert harness.config.model.timeout == 42
    assert harness.config.model.max_tokens == 256
