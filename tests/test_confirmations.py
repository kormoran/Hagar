"""Test del provider di conferma per GUI."""

from __future__ import annotations

import threading
import time

from core.confirmations import ParentBridgeConfirmation
from core.confirmations import QueueConfirmationProvider
from core.permissions import Capability
from core.permissions import ConfirmationRequest


def make_request() -> ConfirmationRequest:
    return ConfirmationRequest(
        subject="assistant",
        tool="filesystem.write_file",
        capabilities=Capability.FILESYSTEM_WRITE,
        arguments={"path": "note.md"},
        reason="write requires approval",
    )


def test_confirmation_is_resolved_from_another_thread():
    events = []
    provider = QueueConfirmationProvider(
        timeout=5,
        event_sink=events.append,
    )
    result = []

    def worker():
        result.append(provider.confirm(make_request()))

    thread = threading.Thread(target=worker)
    thread.start()

    deadline = time.time() + 2
    while not events and time.time() < deadline:
        time.sleep(0.01)

    assert events[0].type == "confirmation.request"
    request_id = events[0].data["id"]

    assert provider.resolve(request_id, True) is True
    thread.join(timeout=2)

    assert result == [True]
    assert events[-1].type == "confirmation.resolved"
    assert events[-1].data["approved"] is True


def test_confirmation_timeout_is_deny():
    provider = QueueConfirmationProvider(timeout=1)

    started = time.time()
    assert provider.confirm(make_request()) is False
    assert time.time() - started >= 0.9


def test_resolve_unknown_id_returns_false():
    provider = QueueConfirmationProvider(timeout=1)

    assert provider.resolve("missing", True) is False


def test_pending_requests_are_serializable():
    provider = QueueConfirmationProvider(timeout=5)
    result = []

    def worker():
        result.append(provider.confirm(make_request()))

    thread = threading.Thread(target=worker)
    thread.start()

    deadline = time.time() + 2
    while not provider.pending_requests() and time.time() < deadline:
        time.sleep(0.01)

    pending = provider.pending_requests()

    assert len(pending) == 1
    assert pending[0]["tool"] == "filesystem.write_file"
    assert pending[0]["capabilities"] == [
        "FILESYSTEM_WRITE"
    ]

    provider.cancel_all()
    thread.join(timeout=2)

    assert result == [False]


def test_cancel_all_clears_pending():
    provider = QueueConfirmationProvider(timeout=5)
    result = []

    def worker():
        result.append(provider.confirm(make_request()))

    thread = threading.Thread(target=worker)
    thread.start()

    deadline = time.time() + 2
    while not provider.pending_requests() and time.time() < deadline:
        time.sleep(0.01)

    assert provider.cancel_all() == 1
    thread.join(timeout=2)

    assert result == [False]
    assert provider.pending_requests() == []


def test_parent_bridge_forwards_approval():
    class Provider:
        def confirm(self, request):
            return True

    bridge = ParentBridgeConfirmation(Provider(), timeout=1)

    assert bridge.confirm(make_request()) is True


def test_parent_bridge_timeout_is_deny():
    class SlowProvider:
        def confirm(self, request):
            time.sleep(0.2)
            return True

    class Audit:
        def __init__(self):
            self.events = []

        def record(self, event, **fields):
            self.events.append((event, fields))

    audit = Audit()
    bridge = ParentBridgeConfirmation(
        SlowProvider(),
        timeout=0.05,
        audit=audit,
        agent_id="a-1",
        parent_id="parent",
    )

    assert bridge.confirm(make_request()) is False
    assert audit.events[0][0] == "confirmation.timeout"
    assert audit.events[0][1]["agent_id"] == "a-1"
