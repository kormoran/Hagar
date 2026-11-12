"""Profili dei task per il broker LLM."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.model_registry import CAPABILITIES


class TaskProfileError(RuntimeError):
    pass


PRIVACY = frozenset({
    "any",
    "local_only",
    "remote_only",
})

PREFERENCES = frozenset({
    "quality",
    "latency",
    "cost",
    "context",
    "balanced",
})


@dataclass(frozen=True, slots=True)
class TaskProfile:
    """Requisiti di un task, indipendenti dal provider."""

    name: str
    required_capabilities: frozenset[str] = frozenset()
    min_context: int | None = None
    privacy: str = "any"
    max_latency_ms: int | None = None
    max_cost_per_1k_input: float | None = None
    max_cost_per_1k_output: float | None = None
    quality_floor: float | None = None
    prefer: str = "balanced"
    description: str = ""
    enabled: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required_capabilities": sorted(
                self.required_capabilities
            ),
            "min_context": self.min_context,
            "privacy": self.privacy,
            "max_latency_ms": self.max_latency_ms,
            "max_cost_per_1k_input": self.max_cost_per_1k_input,
            "max_cost_per_1k_output": self.max_cost_per_1k_output,
            "quality_floor": self.quality_floor,
            "prefer": self.prefer,
            "description": self.description,
            "enabled": self.enabled,
        }


class TaskProfileStore:
    """Carica e valida i profili da YAML."""

    def __init__(
        self,
        profiles: list[TaskProfile],
        *,
        path: Path | None = None,
    ) -> None:

        self.path = path
        self._profiles = tuple(profiles)
        self._by_name = {
            profile.name: profile
            for profile in self._profiles
        }

    @classmethod
    def load(
        cls,
        path: str | Path,
    ) -> "TaskProfileStore":

        profile_path = Path(path)

        if not profile_path.is_file():
            raise TaskProfileError(
                f"task profiles not found: {profile_path}"
            )

        try:
            payload = yaml.safe_load(
                profile_path.read_text(encoding="utf-8")
            )
        except (OSError, yaml.YAMLError) as exc:
            raise TaskProfileError(
                f"cannot read task profiles: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise TaskProfileError(
                "task profiles must be a mapping"
            )

        version = payload.get("version", 1)

        if isinstance(version, bool) or version != 1:
            raise TaskProfileError(
                f"unsupported task profiles version: {version!r}"
            )

        raw_profiles = payload.get("profiles")

        if isinstance(raw_profiles, dict):

            mapped = []

            for name, value in raw_profiles.items():

                if value is None:
                    value = {}

                if not isinstance(value, dict):
                    raise TaskProfileError(
                        f"profiles.{name} must be a mapping"
                    )

                mapped.append({"name": name, **value})

            raw_profiles = mapped

        if not isinstance(raw_profiles, list):
            raise TaskProfileError(
                "task profiles 'profiles' must be a list or mapping"
            )

        profiles = [
            cls._parse_profile(raw, index)
            for index, raw in enumerate(raw_profiles)
        ]

        names = set()

        for profile in profiles:

            if profile.name in names:
                raise TaskProfileError(
                    f"duplicate task profile: {profile.name}"
                )

            names.add(profile.name)

        return cls(profiles, path=profile_path)

    @property
    def profiles(self) -> tuple[TaskProfile, ...]:
        return self._profiles

    def get(self, name: str) -> TaskProfile | None:
        return self._by_name.get(name)

    def enabled(self) -> tuple[TaskProfile, ...]:
        return tuple(
            profile
            for profile in self._profiles
            if profile.enabled
        )

    # --------------------------------------------------
    # Parsing
    # --------------------------------------------------

    @classmethod
    def _parse_profile(
        cls,
        raw: Any,
        index: int,
    ) -> TaskProfile:

        where = f"profiles[{index}]"

        if not isinstance(raw, dict):
            raise TaskProfileError(
                f"{where} must be a mapping"
            )

        allowed = {
            "name",
            "required_capabilities",
            "min_context",
            "privacy",
            "max_latency_ms",
            "max_cost_per_1k_input",
            "max_cost_per_1k_output",
            "quality_floor",
            "prefer",
            "description",
            "enabled",
        }
        unknown = set(raw) - allowed

        if unknown:
            raise TaskProfileError(
                f"{where}: unknown keys {sorted(unknown)}"
            )

        name = raw.get("name")

        if not isinstance(name, str) or not name.strip():
            raise TaskProfileError(
                f"{where}.name must be a non-empty string"
            )

        raw_capabilities = raw.get(
            "required_capabilities",
            [],
        )

        if not isinstance(raw_capabilities, list):
            raise TaskProfileError(
                f"{where}.required_capabilities must be a list"
            )

        capabilities = set()

        for capability in raw_capabilities:

            if not isinstance(capability, str) or not capability.strip():
                raise TaskProfileError(
                    f"{where}.required_capabilities entries "
                    "must be strings"
                )

            capability = capability.strip()

            if capability not in CAPABILITIES:
                raise TaskProfileError(
                    f"{where}.required_capabilities: unknown "
                    f"capability {capability!r}"
                )

            capabilities.add(capability)

        min_context = raw.get("min_context")

        if min_context is not None:

            if (
                isinstance(min_context, bool)
                or not isinstance(min_context, int)
                or min_context <= 0
            ):
                raise TaskProfileError(
                    f"{where}.min_context must be a positive integer"
                )

        privacy = raw.get("privacy", "any")

        if not isinstance(privacy, str) or privacy not in PRIVACY:
            raise TaskProfileError(
                f"{where}.privacy must be one of {sorted(PRIVACY)}"
            )

        max_latency = raw.get("max_latency_ms")

        if max_latency is not None:

            if (
                isinstance(max_latency, bool)
                or not isinstance(max_latency, int)
                or max_latency <= 0
            ):
                raise TaskProfileError(
                    f"{where}.max_latency_ms must be a positive integer"
                )

        max_cost_input = cls._optional_number(
            raw,
            "max_cost_per_1k_input",
            where,
        )
        max_cost_output = cls._optional_number(
            raw,
            "max_cost_per_1k_output",
            where,
        )
        quality_floor = cls._optional_number(
            raw,
            "quality_floor",
            where,
            maximum=1.0,
        )

        prefer = raw.get("prefer", "balanced")

        if not isinstance(prefer, str) or prefer not in PREFERENCES:
            raise TaskProfileError(
                f"{where}.prefer must be one of {sorted(PREFERENCES)}"
            )

        description = raw.get("description", "")

        if not isinstance(description, str):
            raise TaskProfileError(
                f"{where}.description must be a string"
            )

        enabled = raw.get("enabled", True)

        if not isinstance(enabled, bool):
            raise TaskProfileError(
                f"{where}.enabled must be a boolean"
            )

        return TaskProfile(
            name=name.strip(),
            required_capabilities=frozenset(capabilities),
            min_context=min_context,
            privacy=privacy,
            max_latency_ms=max_latency,
            max_cost_per_1k_input=max_cost_input,
            max_cost_per_1k_output=max_cost_output,
            quality_floor=quality_floor,
            prefer=prefer,
            description=description,
            enabled=enabled,
        )

    @staticmethod
    def _optional_number(
        raw: dict[str, Any],
        key: str,
        where: str,
        *,
        maximum: float | None = None,
    ) -> float | None:

        value = raw.get(key)

        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(
            value,
            (int, float),
        ):
            raise TaskProfileError(
                f"{where}.{key} must be a number"
            )

        number = float(value)

        if number < 0:
            raise TaskProfileError(
                f"{where}.{key} must be >= 0"
            )

        if maximum is not None and number > maximum:
            raise TaskProfileError(
                f"{where}.{key} must be <= {maximum}"
            )

        return number
