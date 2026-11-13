"""Catalogo dei provider LLM e dei modelli selezionabili dalla GUI.

I modelli "statici" sono suggerimenti noti; le schede dei modelli
provati e i provider locali (Ollama, LM Studio) arricchiscono la lista.
Nessuna chiave API viene letta o restituita.
"""

from __future__ import annotations

import time

from typing import Any

import requests

from core.model_cards import ModelCardStore
from llm.factory import available_providers


STATIC_MODELS = {
    "ollama": [
        "llama3.1:latest",
        "qwen3:8b",
    ],
    "lmstudio": [],
    "deepseek": [
        "deepseek-flash",
        "deepseek-v4-pro",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4.1",
    ],
    "claude": [
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-latest",
    ],
    "gemini": [
        "gemini-2.0-flash",
    ],
}

LOCAL_HOSTS = {
    "ollama": "http://localhost:11434",
    "lmstudio": "http://localhost:1234/v1",
}

CACHE_TTL = 10.0

_cache: dict[str, Any] = {
    "key": None,
    "at": 0.0,
    "data": None,
}


def default_host(
    provider: str,
) -> str | None:
    """Host predefinito per un provider locale."""

    return LOCAL_HOSTS.get(
        provider.strip().lower()
    )


def _local_models(
    provider: str,
    current: Any,
) -> list[str]:

    base = LOCAL_HOSTS.get(provider)

    if base is None:
        return []

    if (
        getattr(current, "provider", None) == provider
        and getattr(current, "host", None)
    ):
        base = current.host

    try:

        if provider == "ollama":

            response = requests.get(
                base.rstrip("/") + "/api/tags",
                timeout=2,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("models") or []
            return sorted(
                {
                    str(item.get("name"))
                    for item in items
                    if isinstance(item, dict)
                    and item.get("name")
                }
            )

        if provider == "lmstudio":

            response = requests.get(
                base.rstrip("/") + "/models",
                timeout=2,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("data") or []
            return sorted(
                {
                    str(item.get("id"))
                    for item in items
                    if isinstance(item, dict)
                    and item.get("id")
                }
            )

    except Exception:  # noqa: BLE001
        return []

    return []


def _cards() -> list[dict[str, Any]]:

    try:
        return ModelCardStore().list()
    except Exception:  # noqa: BLE001
        return []


def model_catalog(
    config: Any,
    force: bool = False,
) -> dict[str, Any]:
    """Provider disponibili, modelli noti e selezione corrente."""

    current = getattr(config, "model", None)
    key = (
        getattr(current, "provider", None),
        getattr(current, "name", None),
        getattr(current, "host", None),
    )

    now = time.monotonic()

    if (
        not force
        and _cache["data"] is not None
        and _cache["key"] == key
        and now - _cache["at"] < CACHE_TTL
    ):
        return _cache["data"]

    cards = _cards()

    providers = []

    for name in available_providers():

        models = set(STATIC_MODELS.get(name, []))

        for card in cards:

            if str(card.get("provider")) == name:

                model = card.get("model")

                if model:
                    models.add(str(model))

        if name in LOCAL_HOSTS:
            models.update(_local_models(name, current))

        providers.append(
            {
                "name": name,
                "models": sorted(models),
            }
        )

    data = {
        "current": {
            "provider": getattr(
                current,
                "provider",
                "",
            ),
            "name": getattr(current, "name", ""),
        },
        "providers": providers,
    }

    _cache.update(
        {
            "key": key,
            "at": now,
            "data": data,
        }
    )

    return data
