"""Catalogo dichiarato dei modelli e merge con le schede misurate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.model_cards import ModelCardError, ModelCardStore


class ModelRegistryError(RuntimeError):
    pass


def _quality_from_section(
    section: Any,
    task: str,
) -> float | None:

    if isinstance(section, (int, float)) and not isinstance(
        section,
        bool,
    ):
        return float(section)

    if not isinstance(section, dict):
        return None

    tasks = section.get("tasks")

    if not isinstance(tasks, dict):
        return None

    item = tasks.get(task)

    if not isinstance(item, dict):
        return None

    value = item.get("mean", item.get("score"))

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        return None

    return float(value)


CAPABILITIES = frozenset({
    "chat",
    "structured_json",
    "tool_calling",
    "native_tools",
    "vision",
    "reasoning",
})

LOCALITIES = frozenset({
    "local",
    "remote",
    "unknown",
})


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """Un modello dichiarato, arricchito dalla scheda misurata."""

    id: str
    provider: str
    model: str
    context_window: int | None
    capabilities: frozenset[str]
    locality: str = "unknown"
    quality: float | None = None
    cost_per_1k_input: float | None = None
    cost_per_1k_output: float | None = None
    enabled: bool = True
    card: dict[str, Any] | None = field(
        default=None,
        compare=False,
        repr=False,
    )
    card_path: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (
            self.provider.casefold(),
            self.model.casefold(),
        )

    @property
    def measured_at(self) -> str | None:
        if self.card is None:
            return None

        value = self.card.get("last_tested_at")

        return str(value) if value else None

    def has_capability(self, name: str) -> bool:
        return name in self.capabilities

    def measured_quality(self, task: str) -> float | None:
        """Qualità misurata per un task, se presente nella scheda."""

        if not isinstance(self.card, dict):
            return None

        for section in ("quality", "vision"):

            value = _quality_from_section(
                self.card.get(section),
                task,
            )

            if value is not None:
                return value

        return None


    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "model": self.model,
            "context_window": self.context_window,
            "capabilities": sorted(self.capabilities),
            "locality": self.locality,
            "quality": self.quality,
            "cost_per_1k_input": self.cost_per_1k_input,
            "cost_per_1k_output": self.cost_per_1k_output,
            "enabled": self.enabled,
            "measured_at": self.measured_at,
            "card_path": self.card_path,
            "card": self.card,
        }


class ModelRegistry:
    """Catalogo modelli + schede misurate."""

    def __init__(
        self,
        entries: list[ModelEntry],
        *,
        catalog_path: Path | None = None,
    ) -> None:

        self.catalog_path = catalog_path
        self._entries = tuple(entries)
        self._by_id = {entry.id: entry for entry in self._entries}
        self._by_key = {entry.key: entry for entry in self._entries}

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        cards: ModelCardStore | None = None,
    ) -> "ModelRegistry":

        catalog_path = Path(path)

        if not catalog_path.is_file():
            raise ModelRegistryError(
                f"model catalog not found: {catalog_path}"
            )

        try:
            payload = yaml.safe_load(
                catalog_path.read_text(encoding="utf-8")
            )
        except (OSError, yaml.YAMLError) as exc:
            raise ModelRegistryError(
                f"cannot read model catalog: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise ModelRegistryError(
                "model catalog must be a mapping"
            )

        version = payload.get("version", 1)

        if isinstance(version, bool) or version != 1:
            raise ModelRegistryError(
                f"unsupported model catalog version: {version!r}"
            )

        raw_models = payload.get("models")

        if isinstance(raw_models, dict):
            mapped = []

            for name, value in raw_models.items():
                if value is None:
                    value = {}
                if not isinstance(value, dict):
                    raise ModelRegistryError(
                        f"models.{name} must be a mapping"
                    )
                mapped.append({"id": name, **value})

            raw_models = mapped

        if not isinstance(raw_models, list):
            raise ModelRegistryError(
                "model catalog 'models' must be a list or mapping"
            )

        entries = [
            cls._parse_entry(raw, index)
            for index, raw in enumerate(raw_models)
        ]

        cls._validate_unique(entries)

        card_store = cards or ModelCardStore()
        card_map = {}

        try:
            for card in card_store.list():
                provider = str(card.get("provider") or "").strip()
                model = str(card.get("model") or "").strip()

                if provider and model:
                    card_map[
                        (provider.casefold(), model.casefold())
                    ] = card
        except ModelCardError as exc:
            raise ModelRegistryError(
                f"cannot read model cards: {exc}"
            ) from exc

        merged = []

        for entry in entries:
            card = card_map.get(entry.key)

            merged.append(
                ModelEntry(
                    id=entry.id,
                    provider=entry.provider,
                    model=entry.model,
                    context_window=entry.context_window,
                    capabilities=entry.capabilities,
                    locality=entry.locality,
                    quality=entry.quality,
                    cost_per_1k_input=(
                        entry.cost_per_1k_input
                    ),
                    cost_per_1k_output=(
                        entry.cost_per_1k_output
                    ),
                    enabled=entry.enabled,
                    card=card,
                    card_path=(
                        str(card.get("_path"))
                        if card and card.get("_path")
                        else None
                    ),
                )
            )

        return cls(merged, catalog_path=catalog_path)

    @property
    def entries(self) -> tuple[ModelEntry, ...]:
        return self._entries

    def get(self, model_id: str) -> ModelEntry | None:
        return self._by_id.get(model_id)

    def find(
        self,
        provider: str,
        model: str,
    ) -> ModelEntry | None:
        return self._by_key.get(
            (provider.casefold(), model.casefold())
        )

    def enabled(self) -> tuple[ModelEntry, ...]:
        return tuple(
            entry
            for entry in self._entries
            if entry.enabled
        )

    def with_capability(
        self,
        capability: str,
    ) -> tuple[ModelEntry, ...]:
        return tuple(
            entry
            for entry in self._entries
            if entry.enabled
            and entry.has_capability(capability)
        )

    # --------------------------------------------------
    # Parsing
    # --------------------------------------------------

    @classmethod
    def _parse_entry(
        cls,
        raw: Any,
        index: int,
    ) -> ModelEntry:

        where = f"models[{index}]"

        if not isinstance(raw, dict):
            raise ModelRegistryError(
                f"{where} must be a mapping"
            )

        allowed = {
            "id",
            "provider",
            "model",
            "context_window",
            "capabilities",
            "locality",
            "quality",
            "cost_per_1k_input",
            "cost_per_1k_output",
            "enabled",
        }
        unknown = set(raw) - allowed

        if unknown:
            raise ModelRegistryError(
                f"{where}: unknown keys {sorted(unknown)}"
            )

        model_id = cls._required_string(raw, "id", where)
        provider = cls._required_string(raw, "provider", where)
        model = cls._required_string(raw, "model", where)

        context_window = raw.get("context_window")

        if context_window is not None:

            if (
                isinstance(context_window, bool)
                or not isinstance(context_window, int)
                or context_window <= 0
            ):
                raise ModelRegistryError(
                    f"{where}.context_window must be a positive integer"
                )

        raw_capabilities = raw.get("capabilities", [])

        if not isinstance(raw_capabilities, list):
            raise ModelRegistryError(
                f"{where}.capabilities must be a list"
            )

        capabilities = set()

        for capability in raw_capabilities:

            if not isinstance(capability, str) or not capability.strip():
                raise ModelRegistryError(
                    f"{where}.capabilities entries must be strings"
                )

            name = capability.strip()

            if name not in CAPABILITIES:
                raise ModelRegistryError(
                    f"{where}.capabilities: unknown capability "
                    f"{name!r}; expected {sorted(CAPABILITIES)}"
                )

            capabilities.add(name)

        locality = raw.get("locality", "unknown")

        if not isinstance(locality, str) or locality not in LOCALITIES:
            raise ModelRegistryError(
                f"{where}.locality must be one of "
                f"{sorted(LOCALITIES)}"
            )

        quality = cls._optional_number(
            raw,
            "quality",
            where,
            minimum=0.0,
            maximum=1.0,
        )
        cost_input = cls._optional_number(
            raw,
            "cost_per_1k_input",
            where,
            minimum=0.0,
        )
        cost_output = cls._optional_number(
            raw,
            "cost_per_1k_output",
            where,
            minimum=0.0,
        )

        enabled = raw.get("enabled", True)

        if not isinstance(enabled, bool):
            raise ModelRegistryError(
                f"{where}.enabled must be a boolean"
            )

        return ModelEntry(
            id=model_id,
            provider=provider,
            model=model,
            context_window=context_window,
            capabilities=frozenset(capabilities),
            locality=locality,
            quality=quality,
            cost_per_1k_input=cost_input,
            cost_per_1k_output=cost_output,
            enabled=enabled,
        )

    @staticmethod
    def _required_string(
        raw: dict[str, Any],
        key: str,
        where: str,
    ) -> str:

        value = raw.get(key)

        if not isinstance(value, str) or not value.strip():
            raise ModelRegistryError(
                f"{where}.{key} must be a non-empty string"
            )

        return value.strip()

    @staticmethod
    def _optional_number(
        raw: dict[str, Any],
        key: str,
        where: str,
        *,
        minimum: float,
        maximum: float | None = None,
    ) -> float | None:

        value = raw.get(key)

        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(
            value,
            (int, float),
        ):
            raise ModelRegistryError(
                f"{where}.{key} must be a number"
            )

        number = float(value)

        if number < minimum:
            raise ModelRegistryError(
                f"{where}.{key} must be >= {minimum}"
            )

        if maximum is not None and number > maximum:
            raise ModelRegistryError(
                f"{where}.{key} must be <= {maximum}"
            )

        return number

    @staticmethod
    def _validate_unique(
        entries: list[ModelEntry],
    ) -> None:

        ids = set()
        keys = set()

        for entry in entries:

            if entry.id in ids:
                raise ModelRegistryError(
                    f"duplicate model id: {entry.id}"
                )

            if entry.key in keys:
                raise ModelRegistryError(
                    "duplicate provider/model: "
                    f"{entry.provider}/{entry.model}"
                )

            ids.add(entry.id)
            keys.add(entry.key)
