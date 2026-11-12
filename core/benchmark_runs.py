"""Storico append-only dei run di benchmark."""

from __future__ import annotations

import json
import os
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BENCHMARK_SUITE_VERSION = 2


class BenchmarkRunError(RuntimeError):
    pass


def default_run_root() -> Path:

    override = os.environ.get("HAGAR_BENCHMARK_RUNS")

    if override:
        return Path(override)

    if os.name == "nt":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or Path.home() / "AppData" / "Local"
        )
    else:
        base = Path(
            os.environ.get("XDG_STATE_HOME")
            or Path.home() / ".local" / "state"
        )

    return base / "Hagar" / "benchmark-runs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def _new_run_id() -> str:

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


class BenchmarkRunStore:
    """Salva ogni benchmark in un file JSON separato."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or default_run_root())

    def save(
        self,
        report: dict[str, Any],
        *,
        suite_version: int = BENCHMARK_SUITE_VERSION,
        run_id: str | None = None,
    ) -> Path:

        provider = str(report.get("provider") or "").strip()
        model = str(report.get("model") or "").strip()

        if not provider or not model:
            raise BenchmarkRunError(
                "benchmark report requires provider and model"
            )

        run_id = run_id or _new_run_id()
        self.root.mkdir(parents=True, exist_ok=True)

        payload = dict(report)
        payload["run_id"] = run_id
        payload["suite_version"] = suite_version
        payload["saved_at"] = _utc_now()
        path = self.root / f"{run_id}.json"
        temporary = path.with_name(f".{path.name}.tmp")

        try:
            temporary.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

        return path

    def load(self, run_id: str) -> dict[str, Any] | None:

        path = self.root / f"{run_id}.json"

        if not path.is_file():
            return None

        try:
            payload = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise BenchmarkRunError(
                f"cannot read benchmark run: {exc}"
            ) from exc

        return payload if isinstance(payload, dict) else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:

        runs = []

        if not self.root.is_dir():
            return runs

        for path in sorted(
            self.root.glob("*.json"),
            reverse=True,
        ):
            try:
                payload = json.loads(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue

            if isinstance(payload, dict):
                payload["_path"] = str(path)
                runs.append(payload)

        runs.sort(
            key=lambda item: (
                str(item.get("saved_at", "")),
                str(item.get("run_id", "")),
            ),
            reverse=True,
        )
        return runs[: max(0, limit)]
