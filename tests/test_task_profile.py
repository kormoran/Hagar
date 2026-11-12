"""Test dei profili di task."""

from __future__ import annotations

import pytest
import yaml

from core.task_profile import TaskProfileError, TaskProfileStore


def write_profiles(path, profiles, version=1):
    path.write_text(
        yaml.safe_dump(
            {"version": version, "profiles": profiles},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_profiles_load_mapping(tmp_path):
    path = write_profiles(
        tmp_path / "profiles.yaml",
        {
            "coding": {
                "required_capabilities": [
                    "chat",
                    "tool_calling",
                ],
                "min_context": 16000,
                "privacy": "local_only",
                "max_latency_ms": 30000,
                "quality_floor": 0.7,
                "quality_task": "coding",
                "prefer": "quality",
            }
        },
    )

    store = TaskProfileStore.load(path)
    profile = store.get("coding")

    assert profile is not None
    assert profile.name == "coding"
    assert profile.required_capabilities == frozenset({
        "chat",
        "tool_calling",
    })
    assert profile.min_context == 16000
    assert profile.privacy == "local_only"
    assert profile.max_latency_ms == 30000
    assert profile.quality_floor == 0.7
    assert profile.quality_task == "coding"
    assert profile.prefer == "quality"


def test_profiles_load_list_and_filter(tmp_path):
    path = write_profiles(
        tmp_path / "profiles.yaml",
        [
            {
                "name": "a",
                "required_capabilities": ["chat"],
            },
            {
                "name": "b",
                "required_capabilities": ["tool_calling"],
                "enabled": False,
            },
        ],
    )

    store = TaskProfileStore.load(path)

    assert [profile.name for profile in store.enabled()] == ["a"]
    assert store.get("b") is not None
    assert store.get("missing") is None


@pytest.mark.parametrize(
    "profile",
    [
        {"name": "", "required_capabilities": ["chat"]},
        {"name": "a", "required_capabilities": ["telepathy"]},
        {"name": "a", "required_capabilities": "chat"},
        {"name": "a", "min_context": 0},
        {"name": "a", "min_context": True},
        {"name": "a", "privacy": "moon"},
        {"name": "a", "prefer": "vibes"},
        {"name": "a", "quality_floor": 1.1},
        {"name": "a", "max_latency_ms": -1},
        {"name": "a", "max_cost_per_1k_input": -1},
        {"name": "a", "bogus": True},
        {"name": "a", "quality_task": ""},
    ],
)
def test_profiles_reject_invalid(tmp_path, profile):
    path = write_profiles(
        tmp_path / "profiles.yaml",
        [profile],
    )

    with pytest.raises(TaskProfileError):
        TaskProfileStore.load(path)


def test_profiles_reject_duplicates(tmp_path):
    path = write_profiles(
        tmp_path / "profiles.yaml",
        [
            {"name": "a"},
            {"name": "a"},
        ],
    )

    with pytest.raises(TaskProfileError):
        TaskProfileStore.load(path)


def test_profiles_reject_bad_version(tmp_path):
    path = write_profiles(
        tmp_path / "profiles.yaml",
        [],
        version=2,
    )

    with pytest.raises(TaskProfileError):
        TaskProfileStore.load(path)


def test_profiles_reject_missing_file(tmp_path):
    with pytest.raises(TaskProfileError):
        TaskProfileStore.load(tmp_path / "missing.yaml")
