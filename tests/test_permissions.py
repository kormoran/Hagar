"""Test del modello di permessi: capability, regole, evaluator."""

from __future__ import annotations

import pytest

from core.permissions import (
    ALL_CAPABILITIES,
    Capability,
    ConsoleConfirmation,
    ConfirmationRequest,
    DenyAllConfirmation,
    Effect,
    PermissionEvaluator,
    RequestScope,
    Resource,
    Rule,
    Subject,
    capabilities_from_permissions,
    capability_names,
    normalize_path,
)


def make_rule(
    capabilities: Capability,
    effect: Effect,
    **kwargs,
) -> Rule:

    return Rule(
        capabilities=capabilities,
        effect=effect,
        **kwargs,
    )


def make_subject(
    *rules: Rule,
    default: Effect = Effect.DENY,
    name: str = "test",
) -> Subject:

    return Subject(
        name=name,
        rules=tuple(rules),
        default=default,
    )


def make_resource(
    capabilities: Capability,
) -> Resource:

    return Resource(
        kind="tool",
        identifier="demo.tool",
        capabilities=capabilities,
    )


def make_scope(
    tool: str = "demo.tool",
    path: str | None = None,
    namespace: str | None = None,
) -> RequestScope:

    return RequestScope(
        tool=tool,
        path=path,
        namespace=namespace,
    )


# =====================================================
# Capability
# =====================================================


def test_capabilities_combine_with_or():
    mask = (
        Capability.FILESYSTEM_READ
        | Capability.MEMORY_WRITE
    )

    assert capability_names(mask) == [
        "FILESYSTEM_READ",
        "MEMORY_WRITE",
    ]


def test_all_capabilities_contains_every_member():
    for capability in Capability:

        if capability is Capability.NONE:
            continue

        assert ALL_CAPABILITIES & capability


def test_capabilities_from_permissions():
    mask = capabilities_from_permissions(
        read=True,
        write=False,
        shell=False,
    )

    assert mask & Capability.FILESYSTEM_READ
    assert mask & Capability.MEMORY_READ
    assert not mask & Capability.FILESYSTEM_WRITE
    assert mask & Capability.MCP_CALL
    assert mask & Capability.COMPUTE
    assert not mask & Capability.NETWORK
    assert not mask & Capability.AGENT_SPAWN

    mask = capabilities_from_permissions(
        read=True,
        write=False,
        shell=False,
        agents=True,
    )

    assert mask & Capability.AGENT_SPAWN

    mask = capabilities_from_permissions(
        read=True,
        write=True,
        shell=True,
        network=True,
    )

    assert mask & Capability.FILESYSTEM_WRITE
    assert mask & Capability.FILESYSTEM_CREATE
    assert mask & Capability.FILESYSTEM_DELETE
    assert mask & Capability.MEMORY_WRITE
    assert mask & Capability.FILESYSTEM_EXEC
    assert mask & Capability.NETWORK


def test_database_capabilities_from_permissions():
    mask = capabilities_from_permissions(
        read=False,
        write=False,
        shell=False,
    )

    assert not mask & Capability.DATABASE_READ
    assert not mask & Capability.DATABASE_WRITE

    mask = capabilities_from_permissions(
        read=False,
        write=False,
        shell=False,
        database_read=True,
    )

    assert mask & Capability.DATABASE_READ
    assert not mask & Capability.DATABASE_WRITE

    mask = capabilities_from_permissions(
        read=False,
        write=False,
        shell=False,
        database_write=True,
    )

    assert mask & Capability.DATABASE_READ
    assert mask & Capability.DATABASE_WRITE


# =====================================================
# Percorsi e scope
# =====================================================


@pytest.mark.parametrize(
    "value, expected",
    [
        ("a.txt", "a.txt"),
        ("./a.txt", "a.txt"),
        ("note\\a.txt", "note/a.txt"),
        ("note/../a.txt", "a.txt"),
        ("note/", "note"),
        (".", ""),
        ("", ""),
        (None, ""),
        ("/abs/a.txt", "/abs/a.txt"),
    ],
)
def test_normalize_path(value, expected):
    assert normalize_path(value) == expected


def test_request_scope_from_call():
    scope = RequestScope.from_call(
        "filesystem.write_file",
        {"path": "note\\a.txt", "namespace": "skills"},
    )

    assert scope.tool == "filesystem.write_file"
    assert scope.path == "note/a.txt"
    assert scope.namespace == "skills"


def test_request_scope_ignores_non_string_arguments():
    scope = RequestScope.from_call(
        "demo.tool",
        {"path": 42},
    )

    assert scope.path is None


# =====================================================
# Regole
# =====================================================


def test_rule_without_filters_matches_everything():
    rule = make_rule(Capability.FILESYSTEM_READ, Effect.ALLOW)

    assert rule.matches(make_scope()) is True


def test_rule_matches_tool_glob():
    rule = make_rule(
        Capability.FILESYSTEM_READ,
        Effect.ALLOW,
        tools=("filesystem.*",),
    )

    assert rule.matches(
        make_scope("filesystem.read_file")
    ) is True

    assert rule.matches(
        make_scope("memory.search")
    ) is False


def test_rule_matches_path_prefix():
    rule = make_rule(
        Capability.FILESYSTEM_READ,
        Effect.ALLOW,
        paths=("note",),
    )

    assert rule.matches(make_scope(path="note")) is True
    assert rule.matches(make_scope(path="note/a.txt")) is True
    assert rule.matches(make_scope(path="notes/a.txt")) is False
    assert rule.matches(make_scope(path="a.txt")) is False


def test_rule_with_path_does_not_match_call_without_path():
    rule = make_rule(
        Capability.FILESYSTEM_READ,
        Effect.ALLOW,
        paths=("note",),
    )

    assert rule.matches(make_scope(path=None)) is False


def test_rule_matches_namespace_prefix():
    rule = make_rule(
        Capability.MEMORY_READ,
        Effect.ALLOW,
        namespaces=("skills",),
    )

    assert rule.matches(
        make_scope(namespace="skills/python")
    ) is True
    assert rule.matches(
        make_scope(namespace="chat")
    ) is False


# =====================================================
# Evaluator
# =====================================================


def test_default_is_deny():
    evaluator = PermissionEvaluator(ALL_CAPABILITIES)

    decision = evaluator.evaluate(
        make_subject(),
        make_resource(Capability.FILESYSTEM_READ),
        make_scope(),
    )

    assert decision.effect is Effect.DENY
    assert "by default" in decision.reason


def test_allow_rule():
    evaluator = PermissionEvaluator(ALL_CAPABILITIES)

    decision = evaluator.evaluate(
        make_subject(
            make_rule(Capability.FILESYSTEM_READ, Effect.ALLOW)
        ),
        make_resource(Capability.FILESYSTEM_READ),
        make_scope(),
    )

    assert decision.effect is Effect.ALLOW


def test_system_ceiling_denies():
    evaluator = PermissionEvaluator(
        Capability.FILESYSTEM_READ
    )

    decision = evaluator.evaluate(
        make_subject(
            make_rule(Capability.FILESYSTEM_WRITE, Effect.ALLOW)
        ),
        make_resource(Capability.FILESYSTEM_WRITE),
        make_scope(),
    )

    assert decision.effect is Effect.DENY
    assert "outside system ceiling" in decision.reason


def test_deny_overrides_allow_at_same_specificity():
    evaluator = PermissionEvaluator(ALL_CAPABILITIES)

    subject = make_subject(
        make_rule(
            Capability.FILESYSTEM_READ,
            Effect.ALLOW,
            paths=("note",),
        ),
        make_rule(
            Capability.FILESYSTEM_READ,
            Effect.DENY,
            paths=("note",),
        ),
    )

    decision = evaluator.evaluate(
        subject,
        make_resource(Capability.FILESYSTEM_READ),
        make_scope(path="note/a.txt"),
    )

    assert decision.effect is Effect.DENY


def test_specific_rule_wins_over_generic():
    evaluator = PermissionEvaluator(ALL_CAPABILITIES)

    subject = make_subject(
        make_rule(
            Capability.FILESYSTEM_READ,
            Effect.DENY,
            reason="tutto tranne note",
        ),
        make_rule(
            Capability.FILESYSTEM_READ,
            Effect.ALLOW,
            paths=("note",),
        ),
    )

    inside = evaluator.evaluate(
        subject,
        make_resource(Capability.FILESYSTEM_READ),
        make_scope(path="note/a.txt"),
    )

    outside = evaluator.evaluate(
        subject,
        make_resource(Capability.FILESYSTEM_READ),
        make_scope(path="altro/a.txt"),
    )

    assert inside.effect is Effect.ALLOW
    assert outside.effect is Effect.DENY


def test_longer_prefix_wins():
    evaluator = PermissionEvaluator(ALL_CAPABILITIES)

    subject = make_subject(
        make_rule(
            Capability.FILESYSTEM_READ,
            Effect.DENY,
            paths=("note",),
        ),
        make_rule(
            Capability.FILESYSTEM_READ,
            Effect.ALLOW,
            paths=("note/private",),
        ),
    )

    decision = evaluator.evaluate(
        subject,
        make_resource(Capability.FILESYSTEM_READ),
        make_scope(path="note/private/a.txt"),
    )

    assert decision.effect is Effect.ALLOW


def test_required_capabilities_are_anded():
    evaluator = PermissionEvaluator(ALL_CAPABILITIES)

    subject = make_subject(
        make_rule(
            Capability.FILESYSTEM_WRITE,
            Effect.ALLOW,
        ),
        make_rule(
            Capability.FILESYSTEM_CREATE,
            Effect.ASK,
        ),
    )

    decision = evaluator.evaluate(
        subject,
        make_resource(
            Capability.FILESYSTEM_WRITE
            | Capability.FILESYSTEM_CREATE
        ),
        make_scope(),
    )

    assert decision.effect is Effect.ASK


def test_rule_reason_is_reported():
    evaluator = PermissionEvaluator(ALL_CAPABILITIES)

    decision = evaluator.evaluate(
        make_subject(
            make_rule(
                Capability.FILESYSTEM_WRITE,
                Effect.DENY,
                reason="scrittura vietata",
            )
        ),
        make_resource(Capability.FILESYSTEM_WRITE),
        make_scope(),
    )

    assert decision.reason == "scrittura vietata"
    assert decision.rule is not None


def test_no_capability_required_is_allowed():
    evaluator = PermissionEvaluator(Capability.NONE)

    decision = evaluator.evaluate(
        make_subject(),
        make_resource(Capability.NONE),
        make_scope(),
    )

    assert decision.effect is Effect.ALLOW


# =====================================================
# Conferma (ASK)
# =====================================================


def make_request() -> ConfirmationRequest:

    return ConfirmationRequest(
        subject="assistant",
        tool="filesystem.write_file",
        capabilities=Capability.FILESYSTEM_WRITE,
        arguments={"path": "a.txt"},
        reason="test",
    )


def test_deny_all_confirmation_refuses():
    assert DenyAllConfirmation().confirm(make_request()) is False


@pytest.mark.parametrize(
    "answer, approved",
    [
        ("y", True),
        ("Y", True),
        ("yes", True),
        ("s", True),
        ("si", True),
        ("", False),
        ("n", False),
        ("no", False),
        ("forse", False),
    ],
)
def test_console_confirmation(
    monkeypatch,
    capsys,
    answer,
    approved,
):
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": answer,
    )

    assert ConsoleConfirmation().confirm(make_request()) is approved

    output = capsys.readouterr().out

    assert "Permesso richiesto" in output


def test_console_confirmation_on_eof(monkeypatch, capsys):
    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    assert ConsoleConfirmation().confirm(make_request()) is False
