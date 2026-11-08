"""Schede tecniche versionate dei modelli provati."""

from __future__ import annotations

import json
import os
import re

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CARD_VERSION = 1


class ModelCardError(RuntimeError):
    pass


def default_card_root() -> Path:

    override = os.environ.get("HAGAR_MODEL_CARDS")

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

    return base / "Hagar" / "models"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def model_slug(provider: str, model: str) -> str:
    raw = f"{provider}-{model}".lower()
    return re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-")


class ModelCardStore:
    """Salva una scheda JSON per provider/modello."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or default_card_root())

    def path(self, provider: str, model: str) -> Path:
        return (
            self.root
            / provider.lower()
            / f"{model_slug(provider, model)}.json"
        )

    def save(self, card: dict[str, Any]) -> Path:

        provider = str(card.get("provider") or "").strip()
        model = str(card.get("model") or "").strip()

        if not provider or not model:
            raise ModelCardError(
                "provider and model are required"
            )

        payload = dict(card)
        payload["card_version"] = CARD_VERSION
        payload["last_tested_at"] = (
            payload.get("last_tested_at") or utc_now()
        )

        path = self.path(provider, model)
        path.parent.mkdir(parents=True, exist_ok=True)
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

    def load(
        self,
        provider: str,
        model: str,
    ) -> dict[str, Any] | None:

        path = self.path(provider, model)

        if not path.is_file():
            return None

        try:
            payload = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ModelCardError(
                f"cannot read model card: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise ModelCardError("model card must be an object")

        return payload

    def list(self) -> list[dict[str, Any]]:

        cards = []

        if not self.root.is_dir():
            return cards

        for path in sorted(self.root.glob("*/*.json")):
            try:
                payload = json.loads(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                payload["_path"] = str(path)
                cards.append(payload)

        cards.sort(
            key=lambda item: str(item.get("last_tested_at", "")),
            reverse=True,
        )
        return cards
