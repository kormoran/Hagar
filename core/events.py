"""Eventi condivisi tra agent, registry e service layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from typing import Callable


@dataclass(frozen=True)
class ServiceEvent:
    """Evento osservabile da CLI, GUI, test o subagenti."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: str = ""


EventSink = Callable[[ServiceEvent], None]


def make_event(
    event_type: str,
    **data: Any,
) -> ServiceEvent:
    """Costruisce un evento con timestamp UTC."""

    return ServiceEvent(
        type=event_type,
        data=data,
        ts=datetime.now(timezone.utc).isoformat(),
    )


def emit(
    sink: EventSink | None,
    event_type: str,
    **data: Any,
) -> None:
    """Emette un evento se il sink è configurato, senza propagare errori."""

    if sink is None:
        return

    try:
        sink(make_event(event_type, **data))
    except Exception:
        pass
