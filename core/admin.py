"""Servizi amministrativi della GUI: tool, modello, configurazione.

Le pagine web sono un'interfaccia per l'utente locale: non espongono
nuovi tool al modello. Ogni modifica passa da qui e viene registrata
nell'audit quando possibile.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from core.config import ConfigLoader
from core.hifi import HiFiResolver
from core.model_catalog import (
    default_host,
    model_catalog,
)
from core.permissions import capability_names
from llm.factory import (
    available_providers,
    create_llm,
)


class AdminError(RuntimeError):
    """Errore dell'interfaccia amministrativa."""


SETTINGS_GROUPS = (
    (
        "Hi-Fi",
        (
            {
                "key": "hifi.enabled",
                "label": "Hi-Fi attivo",
                "type": "bool",
            },
            {
                "key": "hifi.margin",
                "label": "Margine Hi-Fi",
                "type": "float",
                "min": 0.01,
                "max": 0.99,
                "step": 0.01,
            },
            {
                "key": "hifi.interpretations",
                "label": "Interpretazioni",
                "type": "int",
                "min": 2,
                "max": 20,
                "step": 1,
            },
        ),
    ),
    (
        "Tool",
        (
            {
                "key": "tools.timeout",
                "label": "Timeout tool (s)",
                "type": "int",
                "min": 0,
                "max": 3600,
                "step": 1,
            },
            {
                "key": "tools.repeat_limit",
                "label": "Limite ripetizioni",
                "type": "int",
                "min": 0,
                "max": 100,
                "step": 1,
            },
        ),
    ),
    (
        "Modello",
        (
            {
                "key": "model.timeout",
                "label": "Timeout modello (s)",
                "type": "int",
                "min": 1,
                "max": 3600,
                "step": 1,
            },
            {
                "key": "model.max_tokens",
                "label": "Max token",
                "type": "int",
                "min": 1,
                "max": 1_000_000,
                "step": 1,
            },
            {
                "key": "model.native_tools",
                "label": "Native tool calling",
                "type": "bool",
            },
        ),
    ),
    (
        "Filesystem",
        (
            {
                "key": "filesystem.max_write_bytes",
                "label": "Max byte per scrittura",
                "type": "int",
                "min": 0,
                "max": 1_000_000_000_000,
                "step": 1,
            },
            {
                "key": "filesystem.min_free_bytes",
                "label": "Spazio libero minimo",
                "type": "int",
                "min": 0,
                "max": 1_000_000_000_000,
                "step": 1,
            },
            {
                "key": "filesystem.session_write_bytes",
                "label": "Byte per sessione",
                "type": "int",
                "min": 0,
                "max": 1_000_000_000_000,
                "step": 1,
            },
            {
                "key": "filesystem.ask_over_bytes",
                "label": "Soglia conferma byte",
                "type": "int",
                "min": 0,
                "max": 1_000_000_000_000,
                "step": 1,
            },
        ),
    ),
    (
        "Memoria",
        (
            {
                "key": "memory.context_turns",
                "label": "Turni di contesto",
                "type": "int",
                "min": 0,
                "max": 1000,
                "step": 1,
            },
            {
                "key": "memory.context_skills",
                "label": "Skill di contesto",
                "type": "int",
                "min": 0,
                "max": 1000,
                "step": 1,
            },
            {
                "key": "memory.max_context_chars",
                "label": "Max caratteri contesto",
                "type": "int",
                "min": 1000,
                "max": 10_000_000,
                "step": 1000,
            },
        ),
    ),
)

SETTINGS = {
    field["key"]: field
    for _, fields in SETTINGS_GROUPS
    for field in fields
}


def _bool(
    value: Any,
    name: str,
) -> bool:

    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    if isinstance(value, str):

        normalized = value.strip().lower()

        if normalized in {"true", "1", "on", "yes"}:
            return True

        if normalized in {"false", "0", "off", "no"}:
            return False

    raise AdminError(
        f"{name} must be a boolean"
    )


def _number(
    value: Any,
    spec: dict[str, Any],
) -> int | float:

    kind = spec["type"]

    if isinstance(value, bool):
        raise AdminError(
            f"{spec['key']} must be a number"
        )

    try:

        if kind == "int":
            number = int(value)
        else:
            number = float(value)

    except (TypeError, ValueError) as exc:

        raise AdminError(
            f"{spec['key']} must be a number"
        ) from exc

    minimum = spec.get("min")
    maximum = spec.get("max")

    if minimum is not None and number < minimum:
        raise AdminError(
            f"{spec['key']} must be >= {minimum}"
        )

    if maximum is not None and number > maximum:
        raise AdminError(
            f"{spec['key']} must be <= {maximum}"
        )

    return number


def _permissions(
    permissions: Any,
) -> dict[str, bool]:

    return {
        "read": bool(
            getattr(permissions, "read", False)
        ),
        "write": bool(
            getattr(permissions, "write", False)
        ),
        "create": bool(
            getattr(permissions, "create", False)
        ),
        "rename": bool(
            getattr(permissions, "rename", False)
        ),
        "delete": bool(
            getattr(permissions, "delete", False)
        ),
        "execute": bool(
            getattr(permissions, "execute", False)
        ),
    }


class AdminService:
    """API amministrativa sopra un harness già costruito."""

    def __init__(
        self,
        harness: Any,
        usage_sink: Any = None,
    ) -> None:

        self.harness = harness
        self.config = harness.config
        self.usage_sink = usage_sink

    # ==================================================
    # Audit
    # ==================================================

    def _audit(
        self,
        event: str,
        **fields: Any,
    ) -> None:

        audit = getattr(
            self.harness,
            "audit",
            None,
        )

        if audit is None:
            return

        try:
            audit.record(event, **fields)
        except Exception:  # noqa: BLE001
            pass

    # ==================================================
    # Tool
    # ==================================================

    def _tool(
        self,
        name: str,
    ) -> dict[str, Any]:

        tool = self.harness.registry.get(name)

        return {
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "origin": tool.origin,
            "capabilities": capability_names(
                tool.capabilities
            ),
            "enabled": bool(tool.enabled),
        }

    def tools(self) -> list[dict[str, Any]]:

        registry = getattr(
            self.harness,
            "registry",
            None,
        )

        if registry is None:
            return []

        return [
            self._tool(name)
            for name in registry.tool_names()
        ]

    def set_tool(
        self,
        name: str,
        enabled: bool,
    ) -> dict[str, Any]:

        registry = self.harness.registry
        name = str(name or "").strip()

        if not name:
            raise AdminError("tool name is required")

        if name not in registry.tool_names():
            raise AdminError(
                f"unknown tool: {name}"
            )

        enabled = _bool(enabled, "enabled")

        if enabled:
            registry.enable(name)
        else:
            registry.disable(name)

        self._audit(
            "admin.tool",
            tool=name,
            enabled=enabled,
        )

        return self._tool(name)

    # ==================================================
    # Modello
    # ==================================================

    def model_state(
        self,
        force: bool = False,
    ) -> dict[str, Any]:

        return model_catalog(
            self.config,
            force=force,
        )

    def _sync_model_client(self) -> None:

        llm = getattr(
            self.harness,
            "llm",
            None,
        )

        model = self.config.model

        if llm is not None:

            if hasattr(llm, "timeout"):
                llm.timeout = model.timeout

            if hasattr(llm, "max_tokens"):
                llm.max_tokens = model.max_tokens

            if hasattr(llm, "native_tools"):
                llm.native_tools = model.native_tools

    def _install_model(
        self,
        model: Any,
    ) -> None:

        client = create_llm(
            model,
            audit=getattr(
                self.harness,
                "audit",
                None,
            ),
        )

        old = self.config.model

        self.config.model = model
        self.harness.llm = client

        agent = getattr(
            self.harness,
            "agent",
            None,
        )

        if agent is not None:

            agent.llm = client

            hifi = getattr(agent, "hifi", None)

            if hifi is not None:
                hifi.llm = client

        if (
            self.usage_sink is not None
            and hasattr(client, "usage_sink")
        ):
            client.usage_sink = self.usage_sink

        if hasattr(client, "native_tools"):
            client.native_tools = model.native_tools

        self._audit(
            "admin.model_changed",
            from_provider=old.provider,
            from_model=old.name,
            provider=model.provider,
            model=model.name,
        )

    def change_model(
        self,
        provider: str,
        model: str,
    ) -> dict[str, Any]:

        provider = str(provider or "").strip().lower()

        if not provider:
            raise AdminError("provider is required")

        if provider not in available_providers():

            raise AdminError(
                "unknown provider: "
                f"{provider}"
            )

        model = str(model or "").strip()

        if not model:
            raise AdminError("model is required")

        if len(model) > 200:
            raise AdminError("model name is too long")

        if "\x00" in model:
            raise AdminError(
                "model name contains invalid characters"
            )

        current = self.config.model

        if (
            current.provider == provider
            and current.name == model
        ):
            return self.model_state()

        host = (
            current.host
            if current.provider == provider
            else default_host(provider)
        )
        api_key_env = (
            current.api_key_env
            if current.provider == provider
            else None
        )

        new_model = replace(
            current,
            provider=provider,
            name=model,
            host=host,
            api_key_env=api_key_env,
        )

        self._install_model(new_model)

        return self.model_state()

    # ==================================================
    # Configurazione
    # ==================================================

    def _setting_value(
        self,
        config: Any,
        key: str,
    ) -> Any:

        if key == "hifi.enabled":
            return bool(config.hifi.enabled)

        if key == "hifi.margin":
            return float(config.hifi.margin)

        if key == "hifi.interpretations":
            return int(config.hifi.interpretations)

        if key == "tools.timeout":

            value = config.tools.timeout

            return (
                0
                if value is None
                else int(float(value))
            )

        if key == "tools.repeat_limit":
            return int(config.tools.repeat_limit)

        if key == "model.timeout":
            return int(config.model.timeout)

        if key == "model.max_tokens":
            return int(config.model.max_tokens)

        if key == "model.native_tools":
            return bool(config.model.native_tools)

        if key.startswith("filesystem."):
            return int(
                getattr(
                    config.filesystem.limits,
                    key.split(".", 1)[1],
                )
            )

        if key.startswith("memory."):
            return int(
                getattr(
                    config.memory,
                    key.split(".", 1)[1],
                )
            )

        raise AdminError(
            f"unknown setting: {key}"
        )

    def settings(self) -> dict[str, Any]:

        groups = []

        for name, fields in SETTINGS_GROUPS:

            out = []

            for spec in fields:

                item = dict(spec)
                item["value"] = self._setting_value(
                    self.config,
                    spec["key"],
                )
                out.append(item)

            groups.append(
                {
                    "name": name,
                    "fields": out,
                }
            )

        path = getattr(
            self.config,
            "config_path",
            None,
        )

        return {
            "groups": groups,
            "config_path": (
                str(path) if path else None
            ),
        }

    def _apply_settings(
        self,
        values: dict[str, Any],
    ) -> None:

        # Hi-Fi
        self.config.hifi.enabled = bool(
            values["hifi.enabled"]
        )
        self.config.hifi.margin = float(
            values["hifi.margin"]
        )
        self.config.hifi.interpretations = int(
            values["hifi.interpretations"]
        )

        agent = getattr(
            self.harness,
            "agent",
            None,
        )

        if agent is not None:

            if self.config.hifi.enabled:

                resolver = getattr(
                    agent,
                    "hifi",
                    None,
                )

                if resolver is None:

                    agent.hifi = HiFiResolver(
                        self.harness.llm,
                        margin=self.config.hifi.margin,
                        interpretations=(
                            self.config.hifi
                            .interpretations
                        ),
                    )

                else:
                    resolver.llm = self.harness.llm
                    resolver.margin = (
                        self.config.hifi.margin
                    )
                    resolver.interpretations = (
                        self.config.hifi
                        .interpretations
                    )

            else:
                agent.hifi = None

        # Tool
        timeout = float(values["tools.timeout"])
        self.config.tools.timeout = (
            None if timeout <= 0 else timeout
        )
        self.config.tools.repeat_limit = int(
            values["tools.repeat_limit"]
        )

        registry = getattr(
            self.harness,
            "registry",
            None,
        )

        if registry is not None:
            registry.default_timeout = (
                self.config.tools.timeout
            )
            registry.repeat_limit = (
                self.config.tools.repeat_limit
            )

        # Modello
        self.config.model.timeout = int(
            values["model.timeout"]
        )
        self.config.model.max_tokens = int(
            values["model.max_tokens"]
        )
        self.config.model.native_tools = bool(
            values["model.native_tools"]
        )
        self._sync_model_client()

        # Filesystem
        limits = self.config.filesystem.limits

        for name in (
            "max_write_bytes",
            "min_free_bytes",
            "session_write_bytes",
            "ask_over_bytes",
        ):
            setattr(
                limits,
                name,
                int(values[f"filesystem.{name}"]),
            )

        filesystem = getattr(
            self.harness,
            "filesystem",
            None,
        )

        if filesystem is not None:
            fs_limits = filesystem.limits

            for name in (
                "max_write_bytes",
                "min_free_bytes",
                "session_write_bytes",
                "ask_over_bytes",
            ):
                setattr(
                    fs_limits,
                    name,
                    int(
                        values[
                            f"filesystem.{name}"
                        ]
                    ),
                )

        # Memoria
        self.config.memory.context_turns = int(
            values["memory.context_turns"]
        )
        self.config.memory.context_skills = int(
            values["memory.context_skills"]
        )
        self.config.memory.max_context_chars = int(
            values["memory.max_context_chars"]
        )

        memory = getattr(
            self.harness,
            "memory",
            None,
        )

        if memory is not None:

            if hasattr(memory, "context_turns"):
                memory.context_turns = int(
                    values["memory.context_turns"]
                )

            if hasattr(memory, "context_skills"):
                memory.context_skills = int(
                    values["memory.context_skills"]
                )

        if agent is not None:
            agent.max_context_chars = int(
                values["memory.max_context_chars"]
            )

    def update_settings(
        self,
        values: Any,
    ) -> dict[str, Any]:

        if not isinstance(values, dict):
            raise AdminError(
                "values must be an object"
            )

        unknown = set(values) - set(SETTINGS)

        if unknown:
            raise AdminError(
                "unknown settings: "
                + ", ".join(sorted(unknown))
            )

        current = {
            key: self._setting_value(
                self.config,
                key,
            )
            for key in SETTINGS
        }

        for key, value in values.items():

            spec = SETTINGS[key]

            if spec["type"] == "bool":
                current[key] = _bool(value, key)
            else:
                current[key] = _number(value, spec)

        self._apply_settings(current)

        self._audit(
            "admin.settings",
            keys=sorted(values),
        )

        return self.settings()

    def _values_from_config(
        self,
        config: Any,
    ) -> dict[str, Any]:

        return {
            key: self._setting_value(config, key)
            for key in SETTINGS
        }

    def reset_from_config(self) -> dict[str, Any]:

        path = getattr(
            self.config,
            "config_path",
            None,
        )

        if path is None:
            raise AdminError(
                "configuration path is not available"
            )

        fresh = ConfigLoader.load(path)

        current = self.config.model

        if (
            current.provider,
            current.name,
            current.host,
            current.api_key_env,
        ) != (
            fresh.model.provider,
            fresh.model.name,
            fresh.model.host,
            fresh.model.api_key_env,
        ):
            self._install_model(fresh.model)

        else:
            self.config.model = fresh.model
            self._sync_model_client()

        self._apply_settings(
            self._values_from_config(fresh)
        )

        registry = getattr(
            self.harness,
            "registry",
            None,
        )

        if registry is not None:
            for name in registry.tool_names():
                registry.enable(name)

        filesystem = getattr(
            self.harness,
            "filesystem",
            None,
        )

        if filesystem is not None:
            filesystem.clear_permission_overrides()

        self._audit(
            "admin.reset",
            config=str(path),
        )

        return self.control()

    # ==================================================
    # Sandbox
    # ==================================================

    def _real_path(
        self,
        path: str,
    ) -> str | None:

        filesystem = getattr(
            self.harness,
            "filesystem",
            None,
        )

        if filesystem is None:
            return None

        if path.rstrip("/") == filesystem.virtual_root:
            return None

        try:
            return str(
                filesystem.resolve_path(path)
            )

        except Exception:  # noqa: BLE001
            return None

    def _sandbox_entry(
        self,
        info: Any,
    ) -> dict[str, Any]:

        path = str(info.path)
        name = Path(path).name or path

        raw_permissions = info.permissions or {}

        return {
            "name": name,
            "path": path,
            "kind": info.kind,
            "size_bytes": info.size_bytes,
            "exists": bool(info.exists),
            "permissions": {
                key: bool(
                    raw_permissions.get(key, False)
                )
                for key in (
                    "read",
                    "write",
                    "create",
                    "rename",
                    "delete",
                    "execute",
                )
            },
            "real_path": self._real_path(path),
        }

    def sandbox_list(
        self,
        path: str | None = None,
        offset: int = 0,
        limit: int = 500,
    ) -> dict[str, Any]:

        filesystem = getattr(
            self.harness,
            "filesystem",
            None,
        )

        if filesystem is None:
            raise AdminError(
                "filesystem sandbox is not available"
            )

        path = str(
            path or filesystem.virtual_root
        ).strip()

        try:
            offset = max(0, int(offset))
            limit = max(1, min(int(limit), 500))

        except (TypeError, ValueError) as exc:

            raise AdminError(
                "offset and limit must be integers"
            ) from exc

        try:
            listing = filesystem.list_dir(
                path,
                offset=offset,
                limit=limit,
            )

        except PermissionError as exc:

            raise AdminError(str(exc)) from exc

        except (
            FileNotFoundError,
            NotADirectoryError,
            OSError,
        ) as exc:

            raise AdminError(
                f"cannot list sandbox path: {path}"
            ) from exc

        return {
            "path": path,
            "real_path": self._real_path(path),
            "entries": [
                self._sandbox_entry(info)
                for info in listing["entries"]
            ],
            "total_entries": listing[
                "total_entries"
            ],
            "returned_entries": listing[
                "returned_entries"
            ],
            "offset": listing["offset"],
            "has_more": listing["has_more"],
            "message": listing.get("message"),
        }

    def sandbox_set_permissions(
        self,
        path: str,
        read: Any,
        write: Any,
        execute: Any,
    ) -> dict[str, Any]:

        filesystem = getattr(
            self.harness,
            "filesystem",
            None,
        )

        if filesystem is None:
            raise AdminError(
                "filesystem sandbox is not available"
            )

        path = str(path or "").strip()

        if not path:
            raise AdminError("path is required")

        read = _bool(read, "read")
        write = _bool(write, "write")
        execute = _bool(execute, "execute")

        try:
            permissions = filesystem.set_rwx(
                path,
                read=read,
                write=write,
                execute=execute,
            )

        except PermissionError as exc:

            raise AdminError(str(exc)) from exc

        self._audit(
            "admin.sandbox_permissions",
            path=path,
            read=read,
            write=write,
            execute=execute,
        )

        return {
            "path": path,
            "real_path": self._real_path(path),
            "permissions": _permissions(
                permissions
            ),
        }

    def sandbox_mkdir(
        self,
        parent: str,
        name: str,
    ) -> dict[str, Any]:

        filesystem = getattr(
            self.harness,
            "filesystem",
            None,
        )

        if filesystem is None:
            raise AdminError(
                "filesystem sandbox is not available"
            )

        parent = str(parent or "").strip()
        name = str(name or "").strip()

        if not parent or parent.rstrip("/") == (
            filesystem.virtual_root
        ):
            raise AdminError(
                "select a sandbox directory first"
            )

        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
            or len(name) > 128
        ):
            raise AdminError(
                "invalid directory name"
            )

        target = parent.rstrip("/") + "/" + name

        try:
            filesystem.mkdir(target)
            info = filesystem.stat(target)

        except PermissionError as exc:

            raise AdminError(str(exc)) from exc

        except OSError as exc:

            raise AdminError(
                f"cannot create directory: {exc}"
            ) from exc

        self._audit(
            "admin.sandbox_mkdir",
            path=target,
        )

        return self._sandbox_entry(info)

    # ==================================================
    # Vista completa
    # ==================================================

    def control(
        self,
        force: bool = False,
    ) -> dict[str, Any]:

        return {
            "tools": self.tools(),
            "model": self.model_state(force=force),
            "settings": self.settings(),
        }
