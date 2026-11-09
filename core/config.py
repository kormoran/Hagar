from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Any

import re
import yaml

from .models import (
    AppConfig,
    AuditConfig,
    MemoryConfig,
    ModelConfig,
    PolicyConfig,
    VaultConfig,
    FileSystemConfig,
    FileSystemLimits,
    SandboxMount,
    PermissionConfig,
    RagConfig,
    MCPServerConfig,
    MCPAuthConfig,
    MCPOAuthConfig,
    DecisionProviderConfig,
    DecisionsConfig,
    HiFiConfig,
)

_RESERVED_ALIASES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ConfigError(RuntimeError):
    pass


def _mapping(
    value: Any,
    name: str,
) -> dict[str, Any]:

    if not isinstance(value, dict):

        raise ConfigError(
            f"'{name}' must be a mapping"
        )

    return value


def _text(
    section: dict[str, Any],
    key: str,
    name: str,
) -> str:

    value = section.get(key)

    if not isinstance(value, str) or not value.strip():

        raise ConfigError(
            f"{name} must be a non-empty string"
        )

    return value


def _optional_text(
    section: dict[str, Any],
    key: str,
    name: str,
) -> str | None:

    value = section.get(key)

    if value is None:
        return None

    if not isinstance(value, str) or not value.strip():

        raise ConfigError(
            f"{name} must be a non-empty string when provided"
        )

    return value


def _positive_int(
    section: dict[str, Any],
    key: str,
    name: str,
    default: int,
) -> int:

    value = section.get(key, default)

    if isinstance(value, bool) or not isinstance(
        value,
        int,
    ):

        raise ConfigError(
            f"{name} must be an integer"
        )

    if value <= 0:

        raise ConfigError(
            f"{name} must be greater than zero"
        )

    return value


def _fraction(
    section: dict[str, Any],
    key: str,
    name: str,
    default: float,
) -> float:

    value = section.get(key, default)

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):

        raise ConfigError(
            f"{name} must be a number"
        )

    value = float(value)

    if not 0.0 < value < 1.0:

        raise ConfigError(
            f"{name} must be between 0 and 1"
        )

    return value


def _non_negative_int(
    section: dict[str, Any],
    key: str,
    name: str,
    default: int,
) -> int:

    value = section.get(key, default)

    if isinstance(value, bool) or not isinstance(
        value,
        int,
    ):

        raise ConfigError(
            f"{name} must be an integer"
        )

    if value < 0:

        raise ConfigError(
            f"{name} must be zero or greater"
        )

    return value


class ConfigLoader:

    @staticmethod
    def load(filename: str | Path) -> AppConfig:

        path = Path(filename)

        if not path.exists():

            raise ConfigError(
                f"Configuration file not found: {path}"
            )

        try:

            with open(
                path,
                "r",
                encoding="utf-8",
            ) as fp:

                data = yaml.safe_load(fp)

        except yaml.YAMLError as exc:

            raise ConfigError(
                f"Invalid YAML in {path}: {exc}"
            ) from exc

        except OSError as exc:

            raise ConfigError(
                f"Cannot read configuration {path}: {exc}"
            ) from exc

        if data is None:

            raise ConfigError(
                f"Configuration file is empty: {path}"
            )

        config = ConfigLoader._parse(data)

        #
        # I percorsi relativi dell'audit log sono relativi al file di
        # configurazione: il log non deve cambiare posizione solo perché
        # il harness è stato avviato da un'altra directory.
        #

        if not config.audit.path.is_absolute():

            config.audit.path = (
                path.resolve().parent
                / config.audit.path
            )

        #
        # Anche le policy sono relative al file di configurazione: il
        # harness deve trovarle anche se avviato da un'altra directory.
        #

        if not config.policy.path.is_absolute():

            config.policy.path = (
                path.resolve().parent
                / config.policy.path
            )

        #
        # Il token cache OAuth, se relativo, segue la configurazione.
        #

        for server in config.mcp_servers:

            oauth = (
                server.auth.oauth
                if server.auth is not None
                else None
            )

            if (
                oauth is not None
                and oauth.token_cache is not None
                and not oauth.token_cache.is_absolute()
            ):

                oauth.token_cache = (
                    path.resolve().parent
                    / oauth.token_cache
                )

        return config

    @staticmethod
    def _parse(data: Any) -> AppConfig:

        if not isinstance(data, dict):

            raise ConfigError(
                "Configuration root must be a mapping"
            )

        # -------------------------
        # Model
        # -------------------------

        model_data = _mapping(
            data.get("model"),
            "model",
        )

        native_tools = model_data.get(
            "native_tools",
            True,
        )

        if not isinstance(native_tools, bool):

            raise ConfigError(
                "model.native_tools must be a boolean"
            )

        model = ModelConfig(
            provider=_text(
                model_data,
                "provider",
                "model.provider",
            ),
            name=_text(
                model_data,
                "name",
                "model.name",
            ),
            host=_optional_text(
                model_data,
                "host",
                "model.host",
            ),
            max_tokens=_positive_int(
                model_data,
                "max_tokens",
                "model.max_tokens",
                1024,
            ),
            timeout=_positive_int(
                model_data,
                "timeout",
                "model.timeout",
                120,
            ),
            api_key_env=_optional_text(
                model_data,
                "api_key_env",
                "model.api_key_env",
            ),
            native_tools=native_tools,
        )

        # -------------------------
        # Vault
        # -------------------------

        vault_data = _mapping(
            data.get("vault"),
            "vault",
        )

        vault = VaultConfig(
            path=Path(
                _text(
                    vault_data,
                    "path",
                    "vault.path",
                )
            ).expanduser()
        )

        # -------------------------
        # Filesystem
        # -------------------------

        filesystem_data = _mapping(
            data.get("filesystem"),
            "filesystem",
        )

        sandbox_data = filesystem_data.get("sandbox")

        if not isinstance(sandbox_data, list) or not sandbox_data:

            raise ConfigError(
                "filesystem.sandbox must be a "
                "non-empty list of mounts"
            )

        mounts: list[SandboxMount] = []
        seen_aliases: set[str] = set()

        for index, entry in enumerate(sandbox_data):

            prefix = f"filesystem.sandbox[{index}]"

            entry = _mapping(entry, prefix)

            alias = entry.get("alias")

            if not isinstance(alias, str) or not alias.strip():

                raise ConfigError(
                    f"{prefix}.alias must be a "
                    "non-empty string"
                )

            alias = alias.strip()

            if not _ALIAS_RE.fullmatch(alias):

                raise ConfigError(
                    f"{prefix}.alias is not a valid "
                    "single path segment"
                )

            if alias.split(".", 1)[0].lower() in _RESERVED_ALIASES:

                raise ConfigError(
                    f"{prefix}.alias is a reserved name"
                )

            if alias.endswith((".", " ")):

                raise ConfigError(
                    f"{prefix}.alias must not end "
                    "with a dot or a space"
                )

            normalized_alias = alias.casefold()

            if normalized_alias in seen_aliases:

                raise ConfigError(
                    f"{prefix}.alias duplicates "
                    f"{alias!r} (case-insensitive)"
                )

            seen_aliases.add(normalized_alias)

            path_value = entry.get("path")

            if not isinstance(path_value, str) or not path_value.strip():

                raise ConfigError(
                    f"{prefix}.path must be a "
                    "non-empty string"
                )

            permissions_value = entry.get(
                "permissions",
                "R",
            )

            if not isinstance(permissions_value, str):

                raise ConfigError(
                    f"{prefix}.permissions must be a string"
                )

            normalized_permissions = permissions_value.strip().upper()

            if not normalized_permissions or any(
                char not in "RWX"
                for char in normalized_permissions
            ):

                raise ConfigError(
                    f"{prefix}.permissions must contain "
                    "only R, W and X"
                )

            permissions = "".join(
                char
                for char in "RWX"
                if char in normalized_permissions
            )

            mounts.append(
                SandboxMount(
                    alias=alias,
                    path=Path(path_value).expanduser(),
                    permissions=permissions,
                )
            )

        limits_data = _mapping(
            filesystem_data.get("limits", {}),
            "filesystem.limits",
        )

        limit_defaults = {
            "max_write_bytes": 0,
            "min_free_bytes": 0,
            "session_write_bytes": 0,
            "ask_over_bytes": 0,
        }

        limit_values: dict[str, int] = {}

        for name, default in limit_defaults.items():

            value = limits_data.get(name, default)

            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):

                raise ConfigError(
                    f"filesystem.limits.{name} must be "
                    "a non-negative integer"
                )

            limit_values[name] = value

        filesystem = FileSystemConfig(
            sandbox=mounts,
            limits=FileSystemLimits(**limit_values),
        )

        # -------------------------
        # Permissions (optional)
        # -------------------------

        permissions_data = _mapping(
            data.get("permissions", {}),
            "permissions",
        )

        defaults = {
            "read": True,
            "write": False,
            "shell": False,
            "network": False,
            "agents": False,
        }

        values: dict[str, bool] = {}

        for name, default in defaults.items():

            value = permissions_data.get(
                name,
                default,
            )

            if not isinstance(value, bool):

                raise ConfigError(
                    f"permissions.{name} must be a boolean"
                )

            values[name] = value

        permissions = PermissionConfig(**values)

        # -------------------------
        # RAG (optional)
        # -------------------------

        rag_data = _mapping(
            data.get("rag", {}),
            "rag",
        )

        rag = RagConfig(
            top_k=_positive_int(
                rag_data,
                "top_k",
                "rag.top_k",
                8,
            )
        )

        # -------------------------
        # Audit (optional)
        # -------------------------

        audit_data = _mapping(
            data.get("audit", {}),
            "audit",
        )

        audit_enabled = audit_data.get(
            "enabled",
            True,
        )

        if not isinstance(audit_enabled, bool):

            raise ConfigError(
                "audit.enabled must be a boolean"
            )

        audit_path = audit_data.get(
            "path",
            "logs/audit.jsonl",
        )

        if not isinstance(audit_path, str) or not audit_path.strip():

            raise ConfigError(
                "audit.path must be a non-empty string"
            )

        audit_include_outputs = audit_data.get(
            "include_outputs",
            True,
        )

        if not isinstance(audit_include_outputs, bool):

            raise ConfigError(
                "audit.include_outputs must be a boolean"
            )

        audit = AuditConfig(
            enabled=audit_enabled,
            path=Path(audit_path).expanduser(),
            max_field_chars=_positive_int(
                audit_data,
                "max_field_chars",
                "audit.max_field_chars",
                2000,
            ),
            max_bytes=_non_negative_int(
                audit_data,
                "max_bytes",
                "audit.max_bytes",
                5_000_000,
            ),
            include_outputs=audit_include_outputs,
            max_files=_positive_int(
                audit_data,
                "max_files",
                "audit.max_files",
                100,
            ),
        )

        # -------------------------
        # Policy (optional)
        # -------------------------

        policy_data = _mapping(
            data.get("policy", {}),
            "policy",
        )

        policy_path = policy_data.get(
            "path",
            "policy.yaml",
        )

        if not isinstance(policy_path, str) or not policy_path.strip():

            raise ConfigError(
                "policy.path must be a non-empty string"
            )

        policy_subject = policy_data.get(
            "subject",
            "assistant",
        )

        if not isinstance(policy_subject, str) or not policy_subject.strip():

            raise ConfigError(
                "policy.subject must be a non-empty string"
            )

        policy = PolicyConfig(
            path=Path(policy_path).expanduser(),
            subject=policy_subject,
        )

        # -------------------------
        # Memory (optional)
        # -------------------------

        memory_data = _mapping(
            data.get("memory", {}),
            "memory",
        )

        memory_enabled = memory_data.get(
            "enabled",
            True,
        )

        if not isinstance(memory_enabled, bool):

            raise ConfigError(
                "memory.enabled must be a boolean"
            )

        memory_subdir = memory_data.get(
            "vault_subdir",
            "Hagar",
        )

        memory_backend = memory_data.get(
            "backend",
            "sqlite",
        )

        if memory_backend not in {"sqlite", "markdown"}:

            raise ConfigError(
                "memory.backend must be 'sqlite' or 'markdown'"
            )

        memory_database = memory_data.get("database")

        if memory_database is not None and (
            not isinstance(memory_database, str)
            or not memory_database.strip()
        ):

            raise ConfigError(
                "memory.database must be a non-empty string"
            )

        if not isinstance(memory_subdir, str) or not memory_subdir.strip():

            raise ConfigError(
                "memory.vault_subdir must be a "
                "non-empty string"
            )

        subdir_path = Path(memory_subdir)
        windows_path = PureWindowsPath(memory_subdir)

        if (
            subdir_path.is_absolute()
            or ".." in subdir_path.parts
            or windows_path.drive
            or windows_path.root
        ):

            raise ConfigError(
                "memory.vault_subdir must stay inside the vault"
            )

        memory = MemoryConfig(
            enabled=memory_enabled,
            backend=memory_backend,
            database=(
                memory_database.strip()
                if memory_database is not None
                else None
            ),
            vault_subdir=memory_subdir.strip(),
            context_turns=_non_negative_int(
                memory_data,
                "context_turns",
                "memory.context_turns",
                10,
            ),
            context_skills=_non_negative_int(
                memory_data,
                "context_skills",
                "memory.context_skills",
                3,
            ),
            max_skill_chars=_positive_int(
                memory_data,
                "max_skill_chars",
                "memory.max_skill_chars",
                4000,
            ),
            context_project_memories=_non_negative_int(
                memory_data,
                "context_project_memories",
                "memory.context_project_memories",
                10,
            ),
            max_context_chars=_positive_int(
                memory_data,
                "max_context_chars",
                "memory.max_context_chars",
                6000,
            ),
            project_max_active=_positive_int(
                memory_data,
                "project_max_active",
                "memory.project_max_active",
                200,
            ),
            summary_max_chars=_positive_int(
                memory_data,
                "summary_max_chars",
                "memory.summary_max_chars",
                4000,
            ),
        )

        # -------------------------
        # Decision providers (optional)
        # -------------------------

        decisions_data = _mapping(
            data.get("decisions", {}) or {},
            "decisions",
        )
        decisions_enabled = decisions_data.get(
            "enabled",
            True,
        )

        if not isinstance(decisions_enabled, bool):

            raise ConfigError(
                "decisions.enabled must be a boolean"
            )

        decisions_default = str(
            decisions_data.get("default", "llm")
        ).strip()

        if not decisions_default:

            raise ConfigError(
                "decisions.default must be non-empty"
            )

        raw_decisions = decisions_data.get(
            "providers",
            [],
        )

        if raw_decisions is None:
            raw_decisions = []

        if not isinstance(raw_decisions, list):

            raise ConfigError(
                "decisions.providers must be a list"
            )

        decision_providers: list[DecisionProviderConfig] = []

        for index, entry in enumerate(raw_decisions):

            if not isinstance(entry, dict):

                raise ConfigError(
                    f"decisions.providers[{index}] "
                    "must be a mapping"
                )

            name = _text(
                entry,
                "name",
                f"decisions.providers[{index}].name",
            ).strip()
            provider_type = str(
                entry.get("type", "llm")
            ).strip().lower()

            if provider_type not in {"llm", "linear"}:

                raise ConfigError(
                    f"decisions.providers[{index}].type "
                    "must be 'llm' or 'linear'"
                )

            model_path = _optional_text(
                entry,
                "path",
                f"decisions.providers[{index}].path",
            )

            if provider_type == "linear" and not model_path:

                raise ConfigError(
                    f"decisions.providers[{index}].path "
                    "is required for linear"
                )

            decision_providers.append(
                DecisionProviderConfig(
                    name=name,
                    type=provider_type,
                    path=(
                        str(Path(model_path).expanduser())
                        if model_path
                        else None
                    ),
                    model=_optional_text(
                        entry,
                        "model",
                        f"decisions.providers[{index}].model",
                    ),
                )
            )

        decisions = DecisionsConfig(
            enabled=decisions_enabled,
            default=decisions_default,
            providers=decision_providers,
        )

        # -------------------------
        # MCP servers (optional)
        # -------------------------

        raw_servers = data.get("mcp_servers", [])

        if raw_servers is None:
            raw_servers = []

        if not isinstance(raw_servers, list):

            raise ConfigError(
                "mcp_servers must be a list"
            )

        mcp_servers: list[MCPServerConfig] = []

        for index, entry in enumerate(raw_servers):

            if not isinstance(entry, dict):

                raise ConfigError(
                    f"mcp_servers[{index}] must be a mapping"
                )

            auth_data = entry.get("auth")

            auth: MCPAuthConfig | None = None

            if auth_data is not None:

                if not isinstance(auth_data, dict):

                    raise ConfigError(
                        f"mcp_servers[{index}].auth "
                        "must be a mapping"
                    )

                auth_type = _text(
                    auth_data,
                    "type",
                    f"mcp_servers[{index}].auth.type",
                ).strip().lower()

                if auth_type not in {
                    "bearer",
                    "header",
                    "oauth",
                }:

                    raise ConfigError(
                        f"mcp_servers[{index}].auth.type "
                        "must be 'bearer', 'header' "
                        "or 'oauth'"
                    )

                token_env: str | None = None

                header = "Authorization"

                oauth: MCPOAuthConfig | None = None

                if auth_type == "oauth":

                    if "token_env" in auth_data:

                        raise ConfigError(
                            f"mcp_servers[{index}].auth."
                            "token_env is not valid "
                            "with type 'oauth'"
                        )

                    if "header" in auth_data:

                        raise ConfigError(
                            f"mcp_servers[{index}].auth."
                            "header is not valid "
                            "with type 'oauth'"
                        )

                    oauth_data = auth_data.get(
                        "oauth",
                        {},
                    )

                    if oauth_data is None:
                        oauth_data = {}

                    if not isinstance(oauth_data, dict):

                        raise ConfigError(
                            f"mcp_servers[{index}].auth."
                            "oauth must be a mapping"
                        )

                    raw_scopes = oauth_data.get(
                        "scopes",
                        [],
                    )

                    if raw_scopes is None:
                        raw_scopes = []

                    if not isinstance(raw_scopes, list) or any(
                        not isinstance(scope, str)
                        or not scope.strip()
                        for scope in raw_scopes
                    ):

                        raise ConfigError(
                            f"mcp_servers[{index}].auth."
                            "oauth.scopes must be a list "
                            "of strings"
                        )

                    scopes = [
                        scope.strip()
                        for scope in raw_scopes
                    ]

                    redirect_port = _non_negative_int(
                        oauth_data,
                        "redirect_port",
                        f"mcp_servers[{index}].auth."
                        "oauth.redirect_port",
                        8765,
                    )

                    if redirect_port > 65535:

                        raise ConfigError(
                            f"mcp_servers[{index}].auth."
                            "oauth.redirect_port must be "
                            "between 0 and 65535"
                        )

                    token_cache_raw = _optional_text(
                        oauth_data,
                        "token_cache",
                        f"mcp_servers[{index}].auth."
                        "oauth.token_cache",
                    )

                    oauth = MCPOAuthConfig(
                        authorization_server=_optional_text(
                            oauth_data,
                            "authorization_server",
                            f"mcp_servers[{index}].auth."
                            "oauth.authorization_server",
                        ),
                        client_id=_optional_text(
                            oauth_data,
                            "client_id",
                            f"mcp_servers[{index}].auth."
                            "oauth.client_id",
                        ),
                        client_secret_env=_optional_text(
                            oauth_data,
                            "client_secret_env",
                            f"mcp_servers[{index}].auth."
                            "oauth.client_secret_env",
                        ),
                        scopes=scopes,
                        audience=_optional_text(
                            oauth_data,
                            "audience",
                            f"mcp_servers[{index}].auth."
                            "oauth.audience",
                        ),
                        redirect_port=redirect_port,
                        token_cache=(
                            Path(
                                token_cache_raw
                            ).expanduser()
                            if token_cache_raw
                            else None
                        ),
                        timeout=_positive_int(
                            oauth_data,
                            "timeout",
                            f"mcp_servers[{index}].auth."
                            "oauth.timeout",
                            300,
                        ),
                    )

                    if (
                        oauth.client_secret_env
                        and not oauth.client_id
                    ):

                        raise ConfigError(
                            f"mcp_servers[{index}].auth."
                            "oauth.client_secret_env "
                            "requires client_id"
                        )

                else:

                    if "oauth" in auth_data:

                        raise ConfigError(
                            f"mcp_servers[{index}].auth."
                            "oauth is valid only "
                            "with type 'oauth'"
                        )

                    token_env = _text(
                        auth_data,
                        "token_env",
                        f"mcp_servers[{index}].auth."
                        "token_env",
                    )

                    if auth_type == "header":

                        header = _text(
                            auth_data,
                            "header",
                            f"mcp_servers[{index}].auth."
                            "header",
                        )

                    if not re.fullmatch(
                        r"[A-Za-z0-9-]+",
                        header,
                    ):

                        raise ConfigError(
                            f"mcp_servers[{index}].auth."
                            "header must contain only "
                            "letters, digits and hyphens"
                        )

                auth = MCPAuthConfig(
                    type=auth_type,
                    token_env=token_env,
                    header=header,
                    oauth=oauth,
                )

            mcp_servers.append(
                MCPServerConfig(
                    endpoint=_text(
                        entry,
                        "endpoint",
                        f"mcp_servers[{index}].endpoint",
                    ),
                    namespace=_text(
                        entry,
                        "namespace",
                        f"mcp_servers[{index}].namespace",
                    ),
                    auth=auth,
                )
            )

        # -------------------------
        # Hi-Fi mode (optional)
        # -------------------------

        hifi_data = _mapping(
            data.get("hifi", {}) or {},
            "hifi",
        )

        hifi_enabled = hifi_data.get("enabled", False)

        if not isinstance(hifi_enabled, bool):

            raise ConfigError(
                "hifi.enabled must be a boolean"
            )

        hifi_interpretations = _positive_int(
            hifi_data,
            "interpretations",
            "hifi.interpretations",
            3,
        )

        if hifi_interpretations < 2:

            raise ConfigError(
                "hifi.interpretations must be at least 2"
            )

        hifi = HiFiConfig(
            enabled=hifi_enabled,
            margin=_fraction(
                hifi_data,
                "margin",
                "hifi.margin",
                0.20,
            ),
            interpretations=hifi_interpretations,
        )

        return AppConfig(
            model=model,
            vault=vault,
            filesystem=filesystem,
            permissions=permissions,
            rag=rag,
            mcp_servers=mcp_servers,
            audit=audit,
            policy=policy,
            memory=memory,
            decisions=decisions,
            hifi=hifi,
        )
