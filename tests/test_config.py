"""Test di ConfigLoader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.config import (
    ConfigLoader,
    ConfigError,
)

RESOURCE_DIR = Path(__file__).parent / "resources"


def base_config(tmp_path: Path) -> dict:

    return {
        "model": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "name": "test-model",
        },
        "vault": {
            "path": str(tmp_path / "vault"),
        },
        "filesystem": {
            "sandbox": [
                {
                    "alias": "workspace",
                    "path": str(tmp_path / "workspace"),
                    "permissions": "RWX",
                }
            ],
        },
        "permissions": {
            "read": True,
            "write": False,
            "shell": False,
        },
        "rag": {
            "top_k": 8,
        },
    }


def write_yaml(tmp_path: Path, data) -> Path:

    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(data),
        encoding="utf-8",
    )

    return path


# =====================================================
# File di esempio
# =====================================================


def test_load_valid_config():
    cfg = ConfigLoader.load(RESOURCE_DIR / "valid.yaml")

    assert cfg.model.provider == "ollama"
    assert cfg.model.name == "qwen3:30b"

    assert cfg.permissions.read is True
    assert cfg.permissions.write is False

    assert cfg.rag.top_k == 8

    assert len(cfg.filesystem.sandbox) == 1
    assert cfg.filesystem.sandbox[0].alias == "workspace"
    assert cfg.filesystem.sandbox[0].permissions == "R"


def test_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        ConfigLoader.load("does_not_exist.yaml")


def test_invalid_rag_value():
    with pytest.raises(ConfigError, match="top_k"):
        ConfigLoader.load(RESOURCE_DIR / "invalid_rag.yaml")


def test_permissions_defaults():
    cfg = ConfigLoader.load(RESOURCE_DIR / "defaults.yaml")

    assert cfg.permissions.read is True
    assert cfg.permissions.write is False
    assert cfg.permissions.shell is False
    assert cfg.permissions.network is False


def test_missing_model_key():
    with pytest.raises(ConfigError, match="'model'"):
        ConfigLoader.load(RESOURCE_DIR / "missing_model.yaml")


# =====================================================
# Struttura del documento
# =====================================================


def test_empty_file(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ConfigError, match="empty"):
        ConfigLoader.load(path)


def test_root_must_be_mapping(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="root"):
        ConfigLoader.load(path)


def test_invalid_yaml_syntax(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("model: [unclosed\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid YAML"):
        ConfigLoader.load(path)


def test_model_section_required(tmp_path):
    data = base_config(tmp_path)
    del data["model"]

    with pytest.raises(ConfigError, match="'model'"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_vault_section_required(tmp_path):
    data = base_config(tmp_path)
    del data["vault"]

    with pytest.raises(ConfigError, match="'vault'"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_filesystem_section_required(tmp_path):
    data = base_config(tmp_path)
    del data["filesystem"]

    with pytest.raises(ConfigError, match="'filesystem'"):
        ConfigLoader.load(write_yaml(tmp_path, data))


# =====================================================
# Validazione dei campi
# =====================================================


def test_model_fields_must_be_strings(tmp_path):
    data = base_config(tmp_path)
    data["model"]["name"] = 123

    with pytest.raises(ConfigError, match="model.name"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_empty_model_field(tmp_path):
    data = base_config(tmp_path)
    data["model"]["host"] = "  "

    with pytest.raises(ConfigError, match="model.host"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_permissions_must_be_boolean(tmp_path):
    data = base_config(tmp_path)
    data["permissions"]["write"] = "yes"

    with pytest.raises(ConfigError, match="permissions.write"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_permissions_network_can_be_enabled(tmp_path):
    data = base_config(tmp_path)
    data["permissions"]["network"] = True

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.permissions.network is True


def test_permissions_network_must_be_boolean(tmp_path):
    data = base_config(tmp_path)
    data["permissions"]["network"] = "yes"

    with pytest.raises(ConfigError, match="permissions.network"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_sandbox_must_be_a_list(tmp_path):
    data = base_config(tmp_path)
    data["filesystem"]["sandbox"] = "workspace"

    with pytest.raises(ConfigError, match="filesystem.sandbox"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_sandbox_must_not_be_empty(tmp_path):
    data = base_config(tmp_path)
    data["filesystem"]["sandbox"] = []

    with pytest.raises(ConfigError, match="filesystem.sandbox"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_sandbox_entry_must_be_a_mapping(tmp_path):
    data = base_config(tmp_path)
    data["filesystem"]["sandbox"] = [42]

    with pytest.raises(ConfigError, match="filesystem.sandbox\\[0\\]"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_sandbox_alias_is_required(tmp_path):
    data = base_config(tmp_path)
    del data["filesystem"]["sandbox"][0]["alias"]

    with pytest.raises(ConfigError, match="alias"):
        ConfigLoader.load(write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    "alias",
    ["", "..", "a/b", "a\\b", ".hidden", "CON", "con.txt", "a:"],
)
def test_sandbox_alias_is_validated(tmp_path, alias):
    data = base_config(tmp_path)
    data["filesystem"]["sandbox"][0]["alias"] = alias

    with pytest.raises(ConfigError, match="alias"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_sandbox_aliases_are_case_insensitively_unique(
    tmp_path,
):
    data = base_config(tmp_path)
    data["filesystem"]["sandbox"].append(
        {
            "alias": "Workspace",
            "path": str(tmp_path / "other"),
            "permissions": "R",
        }
    )

    with pytest.raises(ConfigError, match="duplicates"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_sandbox_permissions_are_canonicalized(tmp_path):
    data = base_config(tmp_path)
    data["filesystem"]["sandbox"][0]["permissions"] = "xwr"

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.filesystem.sandbox[0].permissions == "RWX"


def test_sandbox_permissions_are_validated(tmp_path):
    data = base_config(tmp_path)
    data["filesystem"]["sandbox"][0]["permissions"] = "RXZ"

    with pytest.raises(ConfigError, match="permissions"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_sandbox_permissions_default_to_read(tmp_path):
    data = base_config(tmp_path)
    del data["filesystem"]["sandbox"][0]["permissions"]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.filesystem.sandbox[0].permissions == "R"


def test_top_k_must_be_integer(tmp_path):
    data = base_config(tmp_path)
    data["rag"]["top_k"] = "8"

    with pytest.raises(ConfigError, match="rag.top_k"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_top_k_must_be_positive(tmp_path):
    data = base_config(tmp_path)
    data["rag"]["top_k"] = 0

    with pytest.raises(ConfigError, match="greater than zero"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_top_k_rejects_boolean(tmp_path):
    data = base_config(tmp_path)
    data["rag"]["top_k"] = True

    with pytest.raises(ConfigError, match="rag.top_k"):
        ConfigLoader.load(write_yaml(tmp_path, data))


# =====================================================
# Sezioni opzionali
# =====================================================


def test_optional_sections_defaults(tmp_path):
    data = base_config(tmp_path)
    del data["permissions"]
    del data["rag"]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.permissions.read is True
    assert cfg.permissions.write is False
    assert cfg.permissions.shell is False
    assert cfg.rag.top_k == 8
    assert cfg.mcp_servers == []


def test_mcp_servers_are_parsed(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "http://localhost:8080/mcp",
            "namespace": "github",
        },
        {
            "endpoint": "http://localhost:8081/mcp",
            "namespace": "obsidian",
        },
    ]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert len(cfg.mcp_servers) == 2
    assert cfg.mcp_servers[0].namespace == "github"
    assert (
        cfg.mcp_servers[1].endpoint
        == "http://localhost:8081/mcp"
    )


def test_mcp_servers_must_be_list(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = {"endpoint": "x"}

    with pytest.raises(ConfigError, match="mcp_servers"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_mcp_server_requires_endpoint(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [{"namespace": "github"}]

    with pytest.raises(
        ConfigError,
        match=r"mcp_servers\[0\].endpoint",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_mcp_auth_bearer_is_parsed(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "http://localhost:8080/mcp",
            "namespace": "github",
            "auth": {
                "type": "bearer",
                "token_env": "GITHUB_TOKEN",
            },
        }
    ]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    auth = cfg.mcp_servers[0].auth

    assert auth is not None
    assert auth.type == "bearer"
    assert auth.token_env == "GITHUB_TOKEN"
    assert auth.header == "Authorization"


def test_mcp_auth_header_is_parsed(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "http://localhost:8080/mcp",
            "namespace": "custom",
            "auth": {
                "type": "header",
                "header": "X-API-Key",
                "token_env": "CUSTOM_MCP_KEY",
            },
        }
    ]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    auth = cfg.mcp_servers[0].auth

    assert auth is not None
    assert auth.type == "header"
    assert auth.header == "X-API-Key"


def test_mcp_auth_is_optional(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "http://localhost:8080/mcp",
            "namespace": "github",
        }
    ]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.mcp_servers[0].auth is None


def test_mcp_auth_must_be_mapping(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "http://localhost:8080/mcp",
            "namespace": "github",
            "auth": "token",
        }
    ]

    with pytest.raises(
        ConfigError,
        match=r"mcp_servers\[0\].auth",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    "auth",
    [
        {"type": "bearer"},
        {"type": "basic", "token_env": "KEY"},
        {"type": "header", "token_env": "KEY"},
        {
            "type": "header",
            "header": "Bad Header",
            "token_env": "KEY",
        },
    ],
)
def test_mcp_auth_is_validated(tmp_path, auth):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "http://localhost:8080/mcp",
            "namespace": "github",
            "auth": auth,
        }
    ]

    with pytest.raises(ConfigError, match="auth"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_mcp_oauth_is_parsed(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "https://mcp.example.com/mcp",
            "namespace": "oauth",
            "auth": {
                "type": "oauth",
                "oauth": {
                    "authorization_server": (
                        "https://auth.example.com"
                    ),
                    "client_id": "client-1",
                    "client_secret_env": "MCP_CLIENT_SECRET",
                    "scopes": ["read", "write"],
                    "redirect_port": 9000,
                    "token_cache": "cache/oauth.json",
                    "timeout": 120,
                },
            },
        }
    ]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    auth = cfg.mcp_servers[0].auth

    assert auth is not None
    assert auth.type == "oauth"
    assert auth.token_env is None

    oauth = auth.oauth

    assert oauth is not None
    assert oauth.authorization_server == (
        "https://auth.example.com"
    )
    assert oauth.client_id == "client-1"
    assert oauth.client_secret_env == "MCP_CLIENT_SECRET"
    assert oauth.scopes == ["read", "write"]
    assert oauth.redirect_port == 9000
    assert oauth.token_cache == (
        tmp_path / "cache" / "oauth.json"
    )
    assert oauth.timeout == 120


def test_mcp_oauth_defaults(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "https://mcp.example.com/mcp",
            "namespace": "oauth",
            "auth": {"type": "oauth"},
        }
    ]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    oauth = cfg.mcp_servers[0].auth.oauth

    assert oauth is not None
    assert oauth.client_id is None
    assert oauth.scopes == []
    assert oauth.redirect_port == 8765
    assert oauth.token_cache is None
    assert oauth.timeout == 300


def test_mcp_oauth_rejects_token_env(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "https://mcp.example.com/mcp",
            "namespace": "oauth",
            "auth": {
                "type": "oauth",
                "token_env": "TOKEN",
            },
        }
    ]

    with pytest.raises(ConfigError, match="token_env"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_mcp_oauth_rejects_oauth_block_for_bearer(
    tmp_path,
):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "https://mcp.example.com/mcp",
            "namespace": "oauth",
            "auth": {
                "type": "bearer",
                "token_env": "TOKEN",
                "oauth": {},
            },
        }
    ]

    with pytest.raises(ConfigError, match="oauth"):
        ConfigLoader.load(write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    "oauth",
    [
        {"scopes": "read"},
        {"scopes": [1]},
        {"redirect_port": 70000},
    ],
)
def test_mcp_oauth_is_validated(tmp_path, oauth):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "https://mcp.example.com/mcp",
            "namespace": "oauth",
            "auth": {
                "type": "oauth",
                "oauth": oauth,
            },
        }
    ]

    with pytest.raises(ConfigError, match="oauth"):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_mcp_oauth_rejects_secret_without_client(
    tmp_path,
):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "https://mcp.example.com/mcp",
            "namespace": "oauth",
            "auth": {
                "type": "oauth",
                "oauth": {
                    "client_secret_env": "SECRET",
                },
            },
        }
    ]

    with pytest.raises(
        ConfigError,
        match="client_secret_env",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_mcp_oauth_must_be_mapping(tmp_path):
    data = base_config(tmp_path)
    data["mcp_servers"] = [
        {
            "endpoint": "https://mcp.example.com/mcp",
            "namespace": "oauth",
            "auth": {
                "type": "oauth",
                "oauth": [],
            },
        }
    ]

    with pytest.raises(ConfigError, match="oauth"):
        ConfigLoader.load(write_yaml(tmp_path, data))


# =====================================================
# Percorsi
# =====================================================


def test_paths_are_path_objects(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert isinstance(cfg.vault.path, Path)
    assert isinstance(cfg.filesystem.sandbox[0].path, Path)


def test_tilde_is_expanded(tmp_path):
    data = base_config(tmp_path)
    data["vault"]["path"] = "~/vault"
    data["filesystem"]["sandbox"][0]["path"] = (
        "~/workspace"
    )

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.vault.path == Path("~/vault").expanduser()
    assert cfg.filesystem.sandbox[0].path == Path(
        "~/workspace"
    ).expanduser()


# =====================================================
# Model: provider e campi opzionali
# =====================================================


def test_model_host_is_optional(tmp_path):
    data = base_config(tmp_path)
    del data["model"]["host"]

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.model.host is None


def test_model_max_tokens_default(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert cfg.model.max_tokens == 1024


def test_model_max_tokens_custom(tmp_path):
    data = base_config(tmp_path)
    data["model"]["max_tokens"] = 4096

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.model.max_tokens == 4096


@pytest.mark.parametrize(
    "value",
    [0, -1, "1024", True],
)
def test_model_max_tokens_is_validated(tmp_path, value):
    data = base_config(tmp_path)
    data["model"]["max_tokens"] = value

    with pytest.raises(
        ConfigError,
        match="model.max_tokens",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_model_native_tools_defaults_to_true(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert cfg.model.native_tools is True


def test_model_native_tools_can_be_disabled(tmp_path):
    data = base_config(tmp_path)
    data["model"]["native_tools"] = False

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.model.native_tools is False


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_model_native_tools_must_be_boolean(tmp_path, value):
    data = base_config(tmp_path)
    data["model"]["native_tools"] = value

    with pytest.raises(
        ConfigError,
        match="model.native_tools",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_api_key_env_is_optional(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert cfg.model.api_key_env is None


def test_api_key_env_is_parsed(tmp_path):
    data = base_config(tmp_path)
    data["model"]["api_key_env"] = "MY_PROVIDER_KEY"

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.model.api_key_env == "MY_PROVIDER_KEY"


def test_api_key_env_must_be_string(tmp_path):
    data = base_config(tmp_path)
    data["model"]["api_key_env"] = 5

    with pytest.raises(
        ConfigError,
        match="model.api_key_env",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


# =====================================================
# Audit
# =====================================================


def test_audit_defaults(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert cfg.audit.enabled is True
    assert cfg.audit.max_field_chars == 2000
    assert cfg.audit.path == (
        tmp_path / "logs" / "audit.jsonl"
    )


def test_audit_section(tmp_path):
    data = base_config(tmp_path)
    data["audit"] = {
        "enabled": False,
        "path": "audit/custom.jsonl",
        "max_field_chars": 120,
    }

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.audit.enabled is False
    assert cfg.audit.path == (
        tmp_path / "audit" / "custom.jsonl"
    )
    assert cfg.audit.max_field_chars == 120


def test_audit_absolute_path_is_kept(tmp_path):
    target = tmp_path / "elsewhere" / "audit.jsonl"
    data = base_config(tmp_path)
    data["audit"] = {"path": str(target)}

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.audit.path == target


def test_audit_path_is_relative_to_config_file(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()

    path = nested / "config.yaml"
    path.write_text(
        yaml.safe_dump(base_config(tmp_path)),
        encoding="utf-8",
    )

    cfg = ConfigLoader.load(path)

    assert cfg.audit.path == (
        nested / "logs" / "audit.jsonl"
    )


@pytest.mark.parametrize(
    "value",
    ["yes", 1, None],
)
def test_audit_enabled_must_be_boolean(tmp_path, value):
    data = base_config(tmp_path)
    data["audit"] = {"enabled": value}

    with pytest.raises(
        ConfigError,
        match="audit.enabled",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_audit_path_must_be_string(tmp_path):
    data = base_config(tmp_path)
    data["audit"] = {"path": 5}

    with pytest.raises(
        ConfigError,
        match="audit.path",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


@pytest.mark.parametrize("value", [0, -5, "100"])
def test_audit_max_field_chars_must_be_positive(
    tmp_path,
    value,
):
    data = base_config(tmp_path)
    data["audit"] = {"max_field_chars": value}

    with pytest.raises(
        ConfigError,
        match="audit.max_field_chars",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_audit_hardening_defaults(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert cfg.audit.max_bytes == 5_000_000
    assert cfg.audit.include_outputs is True


def test_audit_hardening_section(tmp_path):
    data = base_config(tmp_path)
    data["audit"] = {
        "max_bytes": 1024,
        "include_outputs": False,
    }

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.audit.max_bytes == 1024
    assert cfg.audit.include_outputs is False


@pytest.mark.parametrize(
    "value",
    [-1, "1024", True],
)
def test_audit_max_bytes_is_validated(tmp_path, value):
    data = base_config(tmp_path)
    data["audit"] = {"max_bytes": value}

    with pytest.raises(
        ConfigError,
        match="audit.max_bytes",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_audit_include_outputs_must_be_boolean(tmp_path):
    data = base_config(tmp_path)
    data["audit"] = {"include_outputs": "no"}

    with pytest.raises(
        ConfigError,
        match="audit.include_outputs",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_audit_max_files_defaults_to_100(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert cfg.audit.max_files == 100


def test_audit_max_files_can_be_configured(tmp_path):
    data = base_config(tmp_path)
    data["audit"] = {"max_files": 7}

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.audit.max_files == 7


@pytest.mark.parametrize(
    "value",
    [0, -1, "100", True],
)
def test_audit_max_files_is_validated(tmp_path, value):
    data = base_config(tmp_path)
    data["audit"] = {"max_files": value}

    with pytest.raises(
        ConfigError,
        match="audit.max_files",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


# =====================================================
# Policy
# =====================================================


def test_policy_defaults(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert cfg.policy.path == tmp_path / "policy.yaml"
    assert cfg.policy.subject == "assistant"


def test_policy_section(tmp_path):
    data = base_config(tmp_path)
    data["policy"] = {
        "path": "rules/policy.yaml",
        "subject": "researcher",
    }

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.policy.path == (
        tmp_path / "rules" / "policy.yaml"
    )
    assert cfg.policy.subject == "researcher"


def test_policy_absolute_path_is_kept(tmp_path):
    target = tmp_path / "elsewhere" / "policy.yaml"

    data = base_config(tmp_path)
    data["policy"] = {"path": str(target)}

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.policy.path == target


def test_policy_path_must_be_string(tmp_path):
    data = base_config(tmp_path)
    data["policy"] = {"path": 5}

    with pytest.raises(
        ConfigError,
        match="policy.path",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_policy_subject_must_be_string(tmp_path):
    data = base_config(tmp_path)
    data["policy"] = {"subject": 5}

    with pytest.raises(
        ConfigError,
        match="policy.subject",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


# =====================================================
# Memory
# =====================================================


def test_memory_defaults(tmp_path):
    cfg = ConfigLoader.load(
        write_yaml(tmp_path, base_config(tmp_path))
    )

    assert cfg.memory.enabled is True
    assert cfg.memory.vault_subdir == "Hagar"
    assert cfg.memory.context_turns == 10
    assert cfg.memory.context_skills == 3
    assert cfg.memory.max_skill_chars == 4000


def test_memory_section(tmp_path):
    data = base_config(tmp_path)
    data["memory"] = {
        "enabled": False,
        "vault_subdir": "Ai",
        "context_turns": 3,
        "context_skills": 5,
        "max_skill_chars": 1200,
    }

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.memory.enabled is False
    assert cfg.memory.vault_subdir == "Ai"
    assert cfg.memory.context_turns == 3
    assert cfg.memory.context_skills == 5
    assert cfg.memory.max_skill_chars == 1200


@pytest.mark.parametrize(
    "value",
    ["yes", 1, None],
)
def test_memory_enabled_must_be_boolean(tmp_path, value):
    data = base_config(tmp_path)
    data["memory"] = {"enabled": value}

    with pytest.raises(
        ConfigError,
        match="memory.enabled",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    "value",
    ["", "I:/fuori", "../fuori"],
)
def test_memory_subdir_must_stay_inside(tmp_path, value):
    data = base_config(tmp_path)
    data["memory"] = {"vault_subdir": value}

    with pytest.raises(
        ConfigError,
        match="memory.vault_subdir",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_memory_context_turns_can_be_zero(tmp_path):
    data = base_config(tmp_path)
    data["memory"] = {"context_turns": 0}

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.memory.context_turns == 0


@pytest.mark.parametrize(
    "value",
    [-1, "3", True],
)
def test_memory_context_turns_is_validated(tmp_path, value):
    data = base_config(tmp_path)
    data["memory"] = {"context_turns": value}

    with pytest.raises(
        ConfigError,
        match="memory.context_turns",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


def test_memory_context_skills_can_be_zero(tmp_path):
    data = base_config(tmp_path)
    data["memory"] = {"context_skills": 0}

    cfg = ConfigLoader.load(write_yaml(tmp_path, data))

    assert cfg.memory.context_skills == 0


@pytest.mark.parametrize(
    "value",
    [-1, "3", True],
)
def test_memory_context_skills_is_validated(tmp_path, value):
    data = base_config(tmp_path)
    data["memory"] = {"context_skills": value}

    with pytest.raises(
        ConfigError,
        match="memory.context_skills",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))


@pytest.mark.parametrize("value", [0, -5, "4000"])
def test_memory_max_skill_chars_is_validated(
    tmp_path,
    value,
):
    data = base_config(tmp_path)
    data["memory"] = {"max_skill_chars": value}

    with pytest.raises(
        ConfigError,
        match="memory.max_skill_chars",
    ):
        ConfigLoader.load(write_yaml(tmp_path, data))
