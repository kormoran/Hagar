"""Checkpoint dei file toccati durante un turno.

Non è un snapshot dell'intero workspace: salva solo il contenuto
precedente dei file che una mutazione sta per cambiare. È pensato per
l'undo del singolo turno, non per il versionamento del progetto.
"""

from __future__ import annotations

import os
import stat as stat_module
import time
import uuid

from dataclasses import dataclass, field
from pathlib import Path


MAX_CHECKPOINT_BYTES = 32 * 1024 * 1024


class CheckpointError(RuntimeError):
    pass


@dataclass
class FileSnapshot:
    path: Path
    existed: bool
    data: bytes | None = None
    mode: int | None = None


@dataclass
class WorkspaceCheckpoint:
    checkpoint_id: str = field(
        default_factory=lambda: "cp-" + uuid.uuid4().hex[:12]
    )
    created_at: float = field(default_factory=time.time)
    entries: dict[str, FileSnapshot] = field(default_factory=dict)
    bytes_used: int = 0
    complete: bool = True

    def capture(self, target: Path) -> None:

        key = str(target)

        if key in self.entries:
            return

        try:
            info = target.stat()

        except FileNotFoundError:
            self.entries[key] = FileSnapshot(
                path=target,
                existed=False,
            )
            return

        if not stat_module.S_ISREG(info.st_mode):
            self.complete = False
            return

        data = target.read_bytes()

        if self.bytes_used + len(data) > MAX_CHECKPOINT_BYTES:
            self.complete = False
            return

        self.entries[key] = FileSnapshot(
            path=target,
            existed=True,
            data=data,
            mode=stat_module.S_IMODE(info.st_mode),
        )
        self.bytes_used += len(data)

    def restore(self, sandbox) -> int:
        """Ripristina i file; restituisce il numero di percorsi toccati."""

        if not self.complete:
            raise CheckpointError(
                "checkpoint incompleto: contiene file troppo grandi "
                "o non regolari"
            )

        restored = 0

        for snapshot in reversed(list(self.entries.values())):

            if not snapshot.existed:

                if snapshot.path.exists():
                    snapshot.path.unlink()
                    restored += 1
                continue

            snapshot.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            sandbox._atomic_write_bytes(
                snapshot.path,
                snapshot.data or b"",
            )

            if snapshot.mode is not None:
                try:
                    os.chmod(snapshot.path, snapshot.mode)
                except OSError:
                    pass

            restored += 1

        return restored


def checkpoint_summary(checkpoint: WorkspaceCheckpoint) -> dict:
    return {
        "checkpoint_id": checkpoint.checkpoint_id,
        "created_at": checkpoint.created_at,
        "files": len(checkpoint.entries),
        "bytes": checkpoint.bytes_used,
        "complete": checkpoint.complete,
    }
