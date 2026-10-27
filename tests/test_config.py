from pathlib import Path

import pytest

from core.config import (
    ConfigLoader,
    ConfigError,
)


RESOURCE_DIR = (
    Path(__file__).parent
    / "resources"
)

def test_load_valid_config():

    cfg = ConfigLoader.load(
        RESOURCE_DIR / "valid.yaml"
    )

    assert cfg.model.provider == "ollama"
    assert cfg.model.name == "qwen3:30b"

    assert cfg.permissions.read is True
    assert cfg.permissions.write is False

    assert cfg.rag.top_k == 8

    assert len(
        cfg.filesystem.allowed
    ) == 1
    
def test_missing_file():

    with pytest.raises(ConfigError):
        ConfigLoader.load(
            "does_not_exist.yaml"
        )

def test_invalid_rag_value():

    with pytest.raises(ConfigError):
        ConfigLoader.load(
            RESOURCE_DIR
            / "invalid_rag.yaml"
        )

def test_permissions_defaults():

    cfg = ConfigLoader.load(
        RESOURCE_DIR
        / "defaults.yaml"
    )

    assert cfg.permissions.read is True
    assert cfg.permissions.write is False
    assert cfg.permissions.shell is False

    