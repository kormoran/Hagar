"""Test dell'integrazione tra ToolRegistry e PermissionEvaluator."""

from __future__ import annotations

import pytest

from core.audit import AuditLog, read_entries
from core.permissions import (
    ALL_CAPABILITIES,
    Capability,
    Effect,
    PermissionDenied,
    PermissionEvaluator,
    Rule,
    Subject,
)
from core.tool_definition import ToolDefinition
from core.tool_registry import ToolRegistry


class FixedConfirmation:
    def __init__(self, approved: bool) -> None:
        self.approved = approved
        self.requests = []

    def confirm(self, request):
        self.requests.append(request)
        return self.approved


def make_subject(
    capabilities: Capability = Capability.FILESYSTEM_READ,
    effect: Effect = Effect.ALLOW,
    **rule_kwargs,
) -> Subject:

    return Subject(
        name="test",
        rules=(
            Rule(
                capabilities=capabilities,
                effect=effect,
                **rule_kwargs,
            ),
        ),
    )


def make_registry(
    subject=None,
    confirmation=None,
    audit=None,
    ceiling: Capability = ALL_CAPABILITIES,
    requires_confirmation: bool = False,
) -> ToolRegistry:

    registry = ToolRegistry(
        evaluator=PermissionEvaluator(ceiling),
        subject=subject,
        confirmation=confirmation,
        audit=audit,
    )

    registry.register(
        ToolDefinition(
            name="demo.read",
            description="Legge qualcosa.",
            category="demo",
            capabilities=Capability.FILESYSTEM_READ,
            handler=lambda: "ok",
            requires_confirmation=requires_confirmation,
        )
    )

    return registry


def test_allowed_tool_executes():
    registry = make_registry(subject=make_subject())

    assert registry.execute("demo.read") == "ok"


def test_default_deny():
    registry = make_registry(
        subject=Subject(name="test")
    )

    with pytest.raises(PermissionDenied) as excinfo:
        registry.execute("demo.read")

    assert excinfo.value.decision.effect is Effect.DENY


def test_deny_rule():
    registry = make_registry(
        subject=make_subject(effect=Effect.DENY)
    )

    with pytest.raises(PermissionDenied):
        registry.execute("demo.read")


def test_ask_with_yes_executes():
    confirmation = FixedConfirmation(True)

    registry = make_registry(
        subject=make_subject(effect=Effect.ASK),
        confirmation=confirmation,
    )

    assert registry.execute("demo.read") == "ok"
    assert len(confirmation.requests) == 1
    assert confirmation.requests[0].tool == "demo.read"


def test_ask_with_no_is_denied():
    registry = make_registry(
        subject=make_subject(effect=Effect.ASK),
        confirmation=FixedConfirmation(False),
    )

    with pytest.raises(
        PermissionDenied,
        match="denied by user",
    ):
        registry.execute("demo.read")


def test_ask_without_confirmation_is_denied():
    registry = make_registry(
        subject=make_subject(effect=Effect.ASK),
    )

    with pytest.raises(PermissionDenied):
        registry.execute("demo.read")


def test_requires_confirmation_becomes_ask():
    registry = make_registry(
        subject=make_subject(effect=Effect.ALLOW),
        requires_confirmation=True,
    )

    with pytest.raises(PermissionDenied):
        registry.execute("demo.read")

    registry = make_registry(
        subject=make_subject(effect=Effect.ALLOW),
        requires_confirmation=True,
        confirmation=FixedConfirmation(True),
    )

    assert registry.execute("demo.read") == "ok"


def test_missing_subject_is_denied():
    registry = make_registry(subject=None)

    with pytest.raises(
        PermissionDenied,
        match="No subject",
    ):
        registry.execute("demo.read")


def test_tool_without_capabilities_is_rejected():
    registry = ToolRegistry(
        evaluator=PermissionEvaluator(ALL_CAPABILITIES),
        subject=make_subject(),
    )

    with pytest.raises(ValueError, match="capabilities"):
        registry.register(
            ToolDefinition(
                name="demo.unsafe",
                description="Senza capability.",
                category="demo",
                handler=lambda: "ok",
            )
        )


def test_registry_without_evaluator_keeps_working():
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="demo.unsafe",
            description="Senza capability.",
            category="demo",
            handler=lambda: "ok",
        )
    )

    assert registry.execute("demo.unsafe") == "ok"


def test_path_scope_is_enforced():
    subject = Subject(
        name="test",
        rules=(
            Rule(
                capabilities=Capability.FILESYSTEM_READ,
                effect=Effect.ALLOW,
                paths=("note",),
            ),
        ),
    )

    registry = make_registry(subject=subject)

    # demo.read non ha il parametro path: la regola non si applica.
    with pytest.raises(PermissionDenied):
        registry.execute("demo.read")


def test_permission_decision_is_audited(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)

    registry = make_registry(
        subject=make_subject(),
        audit=audit,
    )

    registry.execute("demo.read")

    entries = read_entries(path)

    assert [entry["event"] for entry in entries] == [
        "permission.decision"
    ]

    entry = entries[0]

    assert entry["subject"] == "test"
    assert entry["tool"] == "demo.read"
    assert entry["effect"] == "ALLOW"
    assert entry["capabilities"] == ["FILESYSTEM_READ"]


def test_confirmation_is_audited(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)

    registry = make_registry(
        subject=make_subject(effect=Effect.ASK),
        confirmation=FixedConfirmation(False),
        audit=audit,
    )

    with pytest.raises(PermissionDenied):
        registry.execute("demo.read")

    entries = read_entries(path)

    assert [entry["event"] for entry in entries] == [
        "permission.decision",
        "permission.confirmation",
    ]

    assert entries[1]["approved"] is False


def test_disabled_tool_is_rejected_before_permissions():
    registry = make_registry(subject=make_subject())
    registry.disable("demo.read")

    with pytest.raises(RuntimeError, match="disabled"):
        registry.execute("demo.read")
