# core/audit.py

from __future__ import annotations

import hashlib
import json
import sys
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRUNCATION_SUFFIX = "...<truncated {remaining} chars>"

DEFAULT_MAX_BYTES = 5_000_000

DEFAULT_MAX_FILES = 100


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


def _hash_entry(entry: dict[str, Any]) -> str:
    """
    Hash canonico della voce, escluso il campo ``hash``.

    Il dizionario ha valori già resi JSON-serializzabili da
    ``AuditLog._prepare``; l'ordinamento delle chiavi rende l'hash
    indipendente dall'ordine di inserimento.
    """

    payload = {
        key: value
        for key, value in entry.items()
        if key != "hash"
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def verify_chain(
    entries: list[dict[str, Any]],
) -> bool:
    """
    Verifica integrità e concatenamento di una lista di voci.

    Il ``prev`` della prima voce non è verificabile senza il file
    precedente (rotazione): si controlla solo che ogni voce abbia
    l'hash giusto e che i collegamenti interni combacino.
    """

    previous: str | None = None

    for index, entry in enumerate(entries):

        if not isinstance(entry, dict):
            return False

        digest = entry.get("hash")

        if not isinstance(digest, str):
            return False

        if digest != _hash_entry(entry):
            return False

        if index > 0 and entry.get("prev") != previous:
            return False

        previous = digest

    return True


class AuditLog:
    """
    Audit log append-only in formato JSON Lines.

    Ogni riga è un evento autonomo con timestamp, id di sessione, nome
    dell'evento, hash della voce e hash della voce precedente: il file è
    tamper-evident, anche se resta best effort.

    La scrittura non deve mai fermare il harness: un errore di I/O viene
    segnalato su stderr una sola volta. Il log non contiene chiavi API.

    Con ``max_bytes`` > 0 il file viene ruotato in ``<nome>.1`` quando
    supera la soglia (una sola copia di backup). Con
    ``include_outputs=False`` il chiamante può evitare di registrare
    l'output dei tool.
    """

    def __init__(
        self,
        path: str | Path,
        max_field_chars: int = 2000,
        enabled: bool = True,
        session_id: str | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        include_outputs: bool = True,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> None:

        self.path = Path(path)

        self.max_field_chars = int(max_field_chars)

        self.enabled = enabled

        self.session_id = (
            session_id or uuid.uuid4().hex[:12]
        )

        self.max_bytes = int(max_bytes)

        self.include_outputs = include_outputs

        self.max_files = int(max_files)

        self._warned = False

        if self.enabled:

            self._prune()

            self._last_hash = self._read_last_hash()

        else:

            self._last_hash = None

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

        entry["prev"] = self._last_hash

        digest = _hash_entry(entry)

        entry["hash"] = digest

        if not self.enabled:

            self._last_hash = digest
            return entry

        try:

            self._rotate()

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

            self._last_hash = digest

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
    # Rotation / chain
    # ==================================================

    def _rotate(self) -> None:

        if self.max_bytes <= 0:
            return

        try:

            if not self.path.exists():
                return

            if self.path.stat().st_size < self.max_bytes:
                return

            stamp = datetime.now(
                timezone.utc
            ).strftime("%Y%m%dT%H%M%S%fZ")

            backup = self.path.with_name(
                f"{self.path.name}.{stamp}"
            )

            index = 2

            while backup.exists():

                backup = self.path.with_name(
                    f"{self.path.name}.{stamp}-{index}"
                )

                index += 1

            self.path.rename(backup)

            self._prune()

        except OSError:

            #
            # La rotazione è un'igiene, non una condizione per
            # scrivere: se fallisce il log continua a crescere.
            #

            pass

    def _backup_files(self) -> list[Path]:

        if not self.path.parent.exists():
            return []

        return sorted(
            (
                candidate
                for candidate in self.path.parent.glob(
                    self.path.name + ".*"
                )
                if candidate.is_file()
            ),
            key=lambda candidate: candidate.name,
        )

    def _prune(self) -> None:
        """
        Tiene al massimo ``max_files`` file, incluso quello attivo.

        I backup sono ordinati per nome: il timestamp ha larghezza fissa,
        quindi l'ordine lessicografico è anche cronologico.
        """

        if self.max_files <= 0:
            return

        backups = self._backup_files()

        excess = len(backups) + 1 - self.max_files

        for backup in backups[: max(0, excess)]:

            try:

                backup.unlink()

            except OSError:

                pass

    @staticmethod
    def _last_hash_in(
        path: Path,
    ) -> str | None:

        last: str | None = None

        try:

            with path.open(
                "r",
                encoding="utf-8",
            ) as handle:

                for line in handle:

                    line = line.strip()

                    if not line:
                        continue

                    try:

                        entry = json.loads(line)

                    except json.JSONDecodeError:

                        continue

                    if isinstance(entry, dict):

                        digest = entry.get("hash")

                        if isinstance(digest, str):
                            last = digest

        except OSError:

            return None

        return last

    def _read_last_hash(self) -> str | None:

        candidates: list[Path] = []

        if self.path.exists():
            candidates.append(self.path)

        candidates.extend(
            reversed(self._backup_files())
        )

        for candidate in candidates:

            digest = self._last_hash_in(
                candidate
            )

            if digest:
                return digest

        return None

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
