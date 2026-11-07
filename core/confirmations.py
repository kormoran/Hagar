"""Conferme non interattive per GUI e server locale."""

from __future__ import annotations

import threading
import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.events import EventSink
from core.events import emit
from core.permissions import ConfirmationRequest
from core.permissions import capability_names


@dataclass
class PendingConfirmation:
    """Richiesta ASK in attesa di una risposta dalla GUI."""

    id: str
    request: ConfirmationRequest
    created_at: str
    timeout: int
    event: threading.Event = field(
        default_factory=threading.Event
    )
    approved: bool = False


class QueueConfirmationProvider:
    """
    Provider di conferma basato su coda e ``threading.Event``.

    Il thread dell'agente si blocca su ``confirm()``; il server HTTP
    resta libero e chiama ``resolve()`` quando l'utente risponde. Un
    timeout equivale a rifiuto.
    """

    def __init__(
        self,
        timeout: int = 300,
        event_sink: EventSink | None = None,
    ) -> None:

        if timeout <= 0:

            raise ValueError(
                "confirmation timeout must be positive"
            )

        self.timeout = int(timeout)
        self.event_sink = event_sink
        self._pending: dict[str, PendingConfirmation] = {}
        self._lock = threading.Lock()

    # ==================================================
    # ConfirmationProvider
    # ==================================================

    def confirm(
        self,
        request: ConfirmationRequest,
    ) -> bool:

        pending = PendingConfirmation(
            id=uuid.uuid4().hex[:12],
            request=request,
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
            timeout=self.timeout,
        )

        with self._lock:
            self._pending[pending.id] = pending

        emit(
            self.event_sink,
            "confirmation.request",
            id=pending.id,
            subject=request.subject,
            tool=request.tool,
            capabilities=capability_names(
                request.capabilities
            ),
            arguments=dict(request.arguments),
            reason=request.reason,
            agent_id=request.agent_id,
            parent_id=request.parent_id,
            timeout=self.timeout,
            created_at=pending.created_at,
        )

        try:

            answered = pending.event.wait(
                self.timeout
            )

        finally:

            with self._lock:
                self._pending.pop(pending.id, None)

        if not answered:
            return False

        return bool(pending.approved)

    # ==================================================
    # API per la GUI
    # ==================================================

    def resolve(
        self,
        request_id: str,
        approved: bool,
    ) -> bool:
        """Risponde a una richiesta; False se l'id non esiste."""

        with self._lock:
            pending = self._pending.get(request_id)

            if pending is None:
                return False

            pending.approved = bool(approved)
            pending.event.set()

        emit(
            self.event_sink,
            "confirmation.resolved",
            id=request_id,
            approved=bool(approved),
        )

        return True

    def pending_requests(self) -> list[dict[str, Any]]:
        """Elenco serializzabile delle richieste ancora aperte."""

        with self._lock:
            pending = list(self._pending.values())

        return [
            {
                "id": item.id,
                "created_at": item.created_at,
                "timeout": item.timeout,
                "subject": item.request.subject,
                "tool": item.request.tool,
                "capabilities": capability_names(
                    item.request.capabilities
                ),
                "arguments": dict(item.request.arguments),
                "reason": item.request.reason,
                "agent_id": item.request.agent_id,
                "parent_id": item.request.parent_id,
            }
            for item in pending
        ]

    def cancel_all(self) -> int:
        """Rifiuta tutte le richieste pendenti."""

        with self._lock:
            pending = list(self._pending.values())

            for item in pending:
                item.approved = False
                item.event.set()

        return len(pending)


class ParentBridgeConfirmation:
    """Inoltra un ASK del figlio al canale umano, con timeout."""

    def __init__(
        self,
        provider: Any,
        timeout: int = 180,
        audit: Any = None,
        agent_id: str | None = None,
        parent_id: str | None = None,
    ) -> None:

        self.provider = provider
        self.timeout = int(timeout)
        self.audit = audit
        self.agent_id = agent_id
        self.parent_id = parent_id

    def confirm(
        self,
        request: ConfirmationRequest,
    ) -> bool:

        if self.provider is None:
            return False

        result = {"approved": False}
        done = threading.Event()

        def ask() -> None:

            try:
                result["approved"] = bool(
                    self.provider.confirm(request)
                )
            finally:
                done.set()

        thread = threading.Thread(
            target=ask,
            name="hagar-subagent-confirmation",
            daemon=True,
        )
        thread.start()

        if not done.wait(self.timeout):

            if self.audit is not None:

                self.audit.record(
                    "confirmation.timeout",
                    agent_id=self.agent_id,
                    parent=self.parent_id,
                    tool=request.tool,
                    capabilities=capability_names(
                        request.capabilities
                    ),
                )

            return False

        return bool(result["approved"])
