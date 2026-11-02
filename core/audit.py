# core/audit.py

from __future__ import annotations

import json
import sys
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRUNCATION_SUFFIX = "...<truncated {remaining} chars>"


def utc_now() -> str:
    """Timestamp ISO 8601 in UTC, con millisecondi."""

    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    )


def _jsonable(value: Any) -> Any:
    """Rende serializzabile qualunque valore senza perdere informazione."""

    if value is None or isinstance(
        value,
        (bool, int, float, str),
    ):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]

    return repr(value)


class AuditLog:
    """
    Audit log append-only in formato JSON Lines.

    Ogni riga è un evento autonomo con timestamp, id di sessione e nome
    dell'evento. Il file cresce in sola aggiunta: una sessione non
    sovrascrive mai le precedenti, e l'id di sessione le distingue.

    La scrittura è "best effort": un errore di I/O non deve fermare il
    harness, ma viene segnalato su stderr una sola volta. Il log non
    contiene chiavi API: i client passano solo metadati e contenuti.
    """

    def __init__(
        self,
        path: str | Path,
        max_field_chars: int = 2000,
        enabled: bool = True,
        session_id: str | None = None,
    ) -> None:

        self.path = Path(path)

        self.max_field_chars = int(max_field_chars)

        self.enabled = enabled

        self.session_id = (
            session_id or uuid.uuid4().hex[:12]
        )

        self._warned = False

    # ==================================================
    # Public API
    # ==================================================

    def record(
        self,
        event: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """
        Registra un evento e restituisce la voce scritta.

        La voce viene restituita anche quando il log è disabilitato o la
        scrittura fallisce: serve ai test e a chi vuole ispezionare il
        flusso senza toccare il disco.
        """

        entry: dict[str, Any] = {
            "ts": utc_now(),
            "session": self.session_id,
            "event": event,
        }

        for key, value in fields.items():
            entry[key] = self._prepare(value)

        if not self.enabled:
            return entry

        try:

            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with self.path.open(
                "a",
                encoding="utf-8",
                newline="\n",
            ) as handle:

                handle.write(
                    json.dumps(
                        entry,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        except OSError as exc:

            if not self._warned:

                self._warned = True

                print(
                    "Audit log write failed "
                    f"({self.path}): {exc}",
                    file=sys.stderr,
                )

        return entry

    # ==================================================
    # Serialization
    # ==================================================

    def _prepare(self, value: Any) -> Any:

        return self._truncate(
            _jsonable(value)
        )

    def _truncate(self, value: Any) -> Any:

        limit = self.max_field_chars

        if limit <= 0:
            return value

        if isinstance(value, str):

            if len(value) <= limit:
                return value

            remaining = len(value) - limit

            return (
                value[:limit]
                + TRUNCATION_SUFFIX.format(
                    remaining=remaining
                )
            )

        if isinstance(value, list):

            return [
                self._truncate(item)
                for item in value
            ]

        if isinstance(value, dict):

            return {
                key: self._truncate(item)
                for key, item in value.items()
            }

        return value


def read_entries(
    path: str | Path,
) -> list[dict[str, Any]]:
    """Legge un audit log e restituisce gli eventi in ordine."""

    path = Path(path)

    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        for line in handle:

            line = line.strip()

            if line:

                entries.append(
                    json.loads(line)
                )

    return entries
