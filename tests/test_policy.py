"""Test del caricamento di policy.yaml."""

from __future__ import annotations

import pytest
import yaml

from core.permissions import (
    Capability,
    Effect,
    PolicyError,
    load_policies,
)


def write_policy(
    tmp_path,
    data,
    name: str = "policy.yaml",
):

    path = tmp_path / name
    path.write_text(
        yaml.safe_dump(data),
        encoding="utf-8",
    )

    return path


def valid_policy():

    return {
        "version": 1,
        "subjects": {
            "assistant": {
                "default": "deny",
                "rules": [
                    {
                        "capabilities": [
                            "FILESYSTEM_READ",
                        ],
                        "effect": "allow",
                        "tools": ["filesystem.*"],
                        "paths": ["note"],
                        "reason": "lettura note",
                    },
                    {
                        "capabilities": [
                            "FILESYSTEM_WRITE",
                            "FILESYSTEM_CREATE",
                        ],
                        "effect": "ask",
                    },
                ],
            }
        },
    }


def test_load_valid_policy(tmp_path):
    policies = load_policies(
        write_policy(tmp_path, valid_policy())
    )

    assert set(policies.subjects) == {"assistant"}

    subject = policies.get("assistant")

    assert subject.name == "assistant"
    assert subject.kind == "agent"
    assert subject.default is Effect.DENY
    assert len(subject.rules) == 2

    first = subject.rules[0]

    assert first.capabilities == Capability.FILESYSTEM_READ
    assert first.effect is Effect.ALLOW
    assert first.tools == ("filesystem.*",)
    assert first.paths == ("note",)
    assert first.reason == "lettura note"


def test_multiple_capabilities_are_combined(tmp_path):
    policies = load_policies(
        write_policy(tmp_path, valid_policy())
    )

    second = policies.get("assistant").rules[1]

    assert second.capabilities & Capability.FILESYSTEM_WRITE
    assert second.capabilities & Capability.FILESYSTEM_CREATE
    assert not second.capabilities & Capability.FILESYSTEM_READ
    assert second.effect is Effect.ASK


def test_capability_names_are_case_insensitive(tmp_path):
    data = valid_policy()
    data["subjects"]["assistant"]["rules"][0][
        "capabilities"
    ] = ["filesystem_read"]

    policies = load_policies(
        write_policy(tmp_path, data)
    )

    assert policies.get(
        "assistant"
    ).rules[0].capabilities == Capability.FILESYSTEM_READ


def test_default_deny_when_omitted(tmp_path):
    data = {
        "subjects": {
            "assistant": {
                "rules": [
                    {
                        "capabilities": ["FILESYSTEM_READ"],
                        "effect": "allow",
                    }
                ]
            }
        }
    }

    policies = load_policies(
        write_policy(tmp_path, data)
    )

    assert policies.get("assistant").default is Effect.DENY


def test_empty_subjects_is_deny_all(tmp_path):
    policies = load_policies(
        write_policy(tmp_path, {"version": 1})
    )

    assert policies.subjects == {}

    subject = policies.get("assistant")

    assert subject.default is Effect.DENY
    assert subject.rules == ()


def test_unknown_subject_is_deny_all(tmp_path):
    policies = load_policies(
        write_policy(tmp_path, valid_policy())
    )

    subject = policies.get("sconosciuto")

    assert subject.default is Effect.DENY
    assert subject.rules == ()


def test_missing_file(tmp_path):
    with pytest.raises(PolicyError, match="not found"):
        load_policies(tmp_path / "missing.yaml")


def test_empty_file(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(PolicyError, match="empty"):
        load_policies(path)


def test_invalid_yaml(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("subjects: [unclosed\n", encoding="utf-8")

    with pytest.raises(PolicyError, match="Invalid YAML"):
        load_policies(path)


def test_root_must_be_mapping(tmp_path):
    with pytest.raises(PolicyError, match="root"):
        load_policies(
            write_policy(tmp_path, ["a", "b"])
        )


def test_unknown_top_level_key(tmp_path):
    with pytest.raises(PolicyError, match="Unknown policy keys"):
        load_policies(
            write_policy(
                tmp_path,
                {
                    "version": 1,
                    "subjects": {},
                    "boh": True,
                },
            )
        )


def test_unsupported_version(tmp_path):
    with pytest.raises(PolicyError, match="version"):
        load_policies(
            write_policy(
                tmp_path,
                {"version": 2, "subjects": {}},
            )
        )


def test_unknown_capability(tmp_path):
    data = valid_policy()
    data["subjects"]["assistant"]["rules"][0][
        "capabilities"
    ] = ["NON_ESISTE"]

    with pytest.raises(PolicyError, match="unknown capability"):
        load_policies(write_policy(tmp_path, data))


def test_unknown_effect(tmp_path):
    data = valid_policy()
    data["subjects"]["assistant"]["rules"][0][
        "effect"
    ] = "forse"

    with pytest.raises(PolicyError, match="unknown effect"):
        load_policies(write_policy(tmp_path, data))


def test_capabilities_are_required(tmp_path):
    data = valid_policy()
    del data["subjects"]["assistant"]["rules"][0][
        "capabilities"
    ]

    with pytest.raises(PolicyError, match="capabilities"):
        load_policies(write_policy(tmp_path, data))


def test_capabilities_must_not_be_empty(tmp_path):
    data = valid_policy()
    data["subjects"]["assistant"]["rules"][0][
        "capabilities"
    ] = []

    with pytest.raises(PolicyError, match="capabilities"):
        load_policies(write_policy(tmp_path, data))


def test_effect_is_required(tmp_path):
    data = valid_policy()
    del data["subjects"]["assistant"]["rules"][0]["effect"]

    with pytest.raises(PolicyError, match="effect"):
        load_policies(write_policy(tmp_path, data))


def test_unknown_rule_key(tmp_path):
    data = valid_policy()
    data["subjects"]["assistant"]["rules"][0]["boh"] = 1

    with pytest.raises(PolicyError, match="unknown keys"):
        load_policies(write_policy(tmp_path, data))


def test_tools_must_be_a_list(tmp_path):
    data = valid_policy()
    data["subjects"]["assistant"]["rules"][0][
        "tools"
    ] = "filesystem.*"

    with pytest.raises(PolicyError, match="tools"):
        load_policies(write_policy(tmp_path, data))


def test_subject_must_be_mapping(tmp_path):
    with pytest.raises(PolicyError, match="subjects.assistant"):
        load_policies(
            write_policy(
                tmp_path,
                {
                    "subjects": {
                        "assistant": ["allow"],
                    }
                },
            )
        )


def test_unknown_subject_key(tmp_path):
    data = valid_policy()
    data["subjects"]["assistant"]["boh"] = True

    with pytest.raises(PolicyError, match="unknown keys"):
        load_policies(write_policy(tmp_path, data))


def test_subject_kind_is_validated(tmp_path):
    data = valid_policy()
    data["subjects"]["assistant"]["kind"] = "robot"

    with pytest.raises(PolicyError, match="kind"):
        load_policies(write_policy(tmp_path, data))
