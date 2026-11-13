"""Test del catalogo modelli."""

from __future__ import annotations

import pytest
import yaml

from core.model_cards import ModelCardStore
from core.model_registry import ModelRegistry, ModelRegistryError


def write_catalog(path, models, version=1):
    path.write_text(
        yaml.safe_dump(
            {"version": version, "models": models},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_registry_loads_list_and_merges_card(tmp_path):
    catalog = write_catalog(
        tmp_path / "models.yaml",
        [
            {
                "id": "lmstudio/coder",
                "provider": "lmstudio",
                "model": "coder",
                "context_window": 32768,
                "capabilities": [
                    "chat",
                    "tool_calling",
                ],
                "locality": "local",
                "quality": 0.8,
                "cost_per_1k_input": 0,
                "cost_per_1k_output": 0,
            }
        ],
    )
    cards = ModelCardStore(tmp_path / "cards")
    cards.save(
        {
            "provider": "lmstudio",
            "model": "coder",
            "last_tested_at": "2026-11-12T20:00:00+00:00",
            "capabilities": {"tool_calling": True},
            "benchmarks": {},
            "quality": {
                "tasks": {
                    "coding": {"mean": 0.75},
                }
            },
            "vision": {
                "tasks": {
                    "vision": {"mean": 0.50},
                }
            },
        }
    )

    registry = ModelRegistry.load(catalog, cards=cards)
    entry = registry.get("lmstudio/coder")

    assert entry is not None
    assert entry.provider == "lmstudio"
    assert entry.model == "coder"
    assert entry.context_window == 32768
    assert entry.has_capability("tool_calling")
    assert entry.measured_quality("coding") == 0.75
    assert entry.measured_quality("vision") == 0.50
    assert entry.measured_quality("missing") is None
    assert entry.card is not None
    assert entry.measured_at == "2026-11-12T20:00:00+00:00"
    assert entry.card_path is not None
    assert registry.find("LMSTUDIO", "CODER") is entry


def test_registry_accepts_mapping(tmp_path):
    catalog = write_catalog(
        tmp_path / "models.yaml",
        {
            "local/chat": {
                "provider": "lmstudio",
                "model": "chat",
                "capabilities": ["chat"],
            }
        },
    )

    registry = ModelRegistry.load(
        catalog,
        cards=ModelCardStore(tmp_path / "cards"),
    )

    assert registry.get("local/chat") is not None
    assert registry.enabled()[0].id == "local/chat"


def test_registry_filters(tmp_path):
    catalog = write_catalog(
        tmp_path / "models.yaml",
        [
            {
                "id": "a",
                "provider": "p",
                "model": "a",
                "capabilities": ["chat"],
            },
            {
                "id": "b",
                "provider": "p",
                "model": "b",
                "capabilities": ["chat", "tool_calling"],
                "enabled": False,
            },
            {
                "id": "c",
                "provider": "p",
                "model": "c",
                "capabilities": ["tool_calling"],
            },
        ],
    )
    registry = ModelRegistry.load(
        catalog,
        cards=ModelCardStore(tmp_path / "cards"),
    )

    assert [entry.id for entry in registry.enabled()] == ["a", "c"]
    assert [
        entry.id
        for entry in registry.with_capability("tool_calling")
    ] == ["c"]


@pytest.mark.parametrize(
    "models",
    [
        [
            {
                "id": "a",
                "provider": "p",
                "model": "a",
            },
            {
                "id": "a",
                "provider": "p",
                "model": "b",
            },
        ],
        [
            {
                "id": "a",
                "provider": "p",
                "model": "a",
            },
            {
                "id": "b",
                "provider": "P",
                "model": "A",
            },
        ],
    ],
)
def test_registry_rejects_duplicates(tmp_path, models):
    catalog = write_catalog(
        tmp_path / "models.yaml",
        models,
    )

    with pytest.raises(ModelRegistryError):
        ModelRegistry.load(
            catalog,
            cards=ModelCardStore(tmp_path / "cards"),
        )


@pytest.mark.parametrize(
    "entry",
    [
        {"id": "a", "provider": "p", "model": "a", "bogus": 1},
        {"id": "a", "provider": "p", "model": "a", "context_window": 0},
        {"id": "a", "provider": "p", "model": "a", "context_window": True},
        {"id": "a", "provider": "p", "model": "a", "quality": 1.1},
        {"id": "a", "provider": "p", "model": "a", "locality": "moon"},
        {"id": "a", "provider": "p", "model": "a", "capabilities": ["telepathy"]},
        {"id": "a", "provider": "", "model": "a"},
    ],
)
def test_registry_rejects_invalid_entries(tmp_path, entry):
    catalog = write_catalog(
        tmp_path / "models.yaml",
        [entry],
    )

    with pytest.raises(ModelRegistryError):
        ModelRegistry.load(
            catalog,
            cards=ModelCardStore(tmp_path / "cards"),
        )


def test_registry_rejects_unknown_version(tmp_path):
    catalog = write_catalog(
        tmp_path / "models.yaml",
        [],
        version=2,
    )

    with pytest.raises(ModelRegistryError):
        ModelRegistry.load(
            catalog,
            cards=ModelCardStore(tmp_path / "cards"),
        )


def test_registry_rejects_missing_catalog(tmp_path):
    with pytest.raises(ModelRegistryError):
        ModelRegistry.load(
            tmp_path / "missing.yaml",
            cards=ModelCardStore(tmp_path / "cards"),
        )
