"""Log in memoria degli eventi della sessione web."""

from __future__ import annotations

import threading

from typing import Any

from core.events import ServiceEvent


MAX_EVENTS = 1000
MAX_OUTPUT = 8000


def _clip(value: Any, limit: int = MAX_OUTPUT) -> str:

    text = str(value)

    if len(text) <= limit:
        return text

    return text[:limit] + "…"


class SessionLog:
    """Registra tool call/result e timeline per la GUI."""

    def __init__(self) -> None:

        self._lock = threading.Lock()
        self._tools: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._thinking: list[dict[str, Any]] = []

    def clear(self) -> None:

        with self._lock:
            self._tools.clear()
            self._events.clear()
            self._thinking.clear()

    def record(
        self,
        event: ServiceEvent,
    ) -> None:

        data = dict(event.data)
        event_type = event.type

        if event_type in {
            "usage.updated",
            "turn.answer",
        }:
            return

        with self._lock:

            self._events.append(
                {
                    "type": event_type,
                    "ts": event.ts,
                    "data": data,
                }
            )
            self._events = self._events[-MAX_EVENTS:]

            if event_type == "thinking":

                self._thinking.append(
                    {
                        "ts": event.ts,
                        "text": _clip(
                            data.get("text", "")
                        ),
                    }
                )
                self._thinking = self._thinking[-100:]

            elif event_type == "tool.call":

                self._tools.append(
                    {
                        "turn": data.get("turn"),
                        "index": data.get("index"),
                        "tool": data.get("tool"),
                        "arguments": data.get("arguments"),
                        "output": "",
                        "success": None,
                        "duration_ms": None,
                        "error": None,
                    }
                )
                self._tools = self._tools[-200:]

            elif event_type == "tool.result":

                match = None

                for item in reversed(self._tools):

                    if (
                        item["turn"] == data.get("turn")
                        and item["index"] == data.get("index")
                    ):
                        match = item
                        break

                if match is None:

                    match = {
                        "turn": data.get("turn"),
                        "index": data.get("index"),
                        "tool": data.get("tool"),
                        "arguments": {},
                        "output": "",
                        "success": None,
                        "duration_ms": None,
                        "error": None,
                    }
                    self._tools.append(match)

                match.update(
                    {
                        "output": _clip(
                            data.get("output", "")
                        ),
                        "success": data.get("success"),
                        "duration_ms": data.get(
                            "duration_ms"
                        ),
                        "error": data.get("error"),
                    }
                )

    def tools(self) -> list[dict[str, Any]]:

        with self._lock:
            return list(self._tools)

    def timeline(self) -> list[dict[str, Any]]:

        with self._lock:
            return list(self._events)

    def thinking(self) -> list[dict[str, Any]]:

        with self._lock:
            return list(self._thinking)
