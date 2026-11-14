"""Dati e benchmark per la pagina web dei modelli locali."""

from __future__ import annotations

import copy

from pathlib import Path
from typing import Any

from core.benchmark_runs import BenchmarkRunStore
from core.capabilities import verified_capabilities
from core.coding_bench import benchmark_coding
from core.memory_bench import benchmark_memory
from core.model_bench import benchmark_model
from core.model_cards import ModelCardStore, utc_now
from core.models import ModelConfig
from core.production_bench import benchmark_production
from core.provider_models import ProviderModelError, discover
from core.quality_bench import benchmark_quality
from llm.factory import create_llm


DEFAULT_HOSTS = {
    "lmstudio": "http://localhost:1234/v1",
    "ollama": "http://localhost:11434",
}


def _provider_host(config: Any, provider: str) -> str:

    current = getattr(config, "model", None)

    if (
        getattr(current, "provider", None) == provider
        and getattr(current, "host", None)
    ):
        return str(current.host)

    return DEFAULT_HOSTS.get(
        provider,
        "",
    )


def _card_stores(
    cards: ModelCardStore | list[ModelCardStore] | None,
) -> list[ModelCardStore]:

    if isinstance(cards, ModelCardStore):
        return [cards]

    if isinstance(cards, list):
        return cards

    root = Path(__file__).resolve().parent.parent
    candidates = [
        ModelCardStore(),
        ModelCardStore(root / "benchmarks" / "live-cards"),
        ModelCardStore(root / "benchmarks" / "retest-cards"),
    ]
    unique = []
    seen = set()

    for store in candidates:
        key = str(store.root.resolve())

        if key not in seen:
            seen.add(key)
            unique.append(store)

    return unique


def _clean_card(card: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in card.items()
        if key != "_path"
    }


def list_local_models(
    config: Any,
    *,
    timeout: float = 2.0,
    cards: ModelCardStore | list[ModelCardStore] | None = None,
) -> dict[str, Any]:

    store_list = _card_stores(cards)
    card_map = {}

    for store in store_list:
        try:
            for card in store.list():

                provider = str(card.get("provider") or "")
                model = str(card.get("model") or "")

                if not provider or not model:
                    continue

                key = (provider.casefold(), model.casefold())
                previous = card_map.get(key)
                current_date = str(
                    card.get("last_tested_at", "")
                )
                previous_date = str(
                    (previous or {}).get("last_tested_at", "")
                )

                if previous is None or current_date >= previous_date:
                    card_map[key] = card
        except Exception:
            continue

    items = []
    errors = []
    seen = set()

    for provider in DEFAULT_HOSTS:

        host = _provider_host(config, provider)

        try:
            infos = discover(
                provider,
                host,
                timeout=timeout,
            )
        except ProviderModelError as exc:
            errors.append({
                "provider": provider,
                "error": str(exc),
            })
            infos = []

        for info in infos:

            key = (provider.casefold(), info.model.casefold())
            seen.add(key)
            card = card_map.get(key)

            items.append({
                "id": f"{provider}/{info.model}",
                "provider": provider,
                "model": info.model,
                "type": info.model_type,
                "state": info.state,
                "loaded": info.state == "loaded",
                "context_window": info.context_window,
                "quantization": info.quantization,
                "capabilities": sorted(info.capabilities),
                "hagar_capabilities": sorted(
                    info.hagar_capabilities()
                ),
                "has_benchmark": card is not None,
                "last_tested_at": (
                    card.get("last_tested_at")
                    if card
                    else None
                ),
                "card": _clean_card(card) if card else None,
            })

    for (provider, model), card in card_map.items():

        if (provider, model) in seen:
            continue

        items.append({
            "id": f"{provider}/{model}",
            "provider": provider,
            "model": model,
            "type": "unknown",
            "state": "unknown",
            "loaded": False,
            "context_window": None,
            "quantization": None,
            "capabilities": [],
            "hagar_capabilities": [],
            "has_benchmark": True,
            "last_tested_at": card.get("last_tested_at"),
            "card": _clean_card(card),
        })

    items.sort(key=lambda item: (item["provider"], item["model"]))

    return {
        "models": items,
        "errors": errors,
        "generated_at": utc_now(),
    }


def run_model_benchmark(
    config: Any,
    provider: str,
    model: str,
    *,
    registry: Any = None,
    cards: ModelCardStore | None = None,
    runs: BenchmarkRunStore | None = None,
    include_coding: bool = False,
) -> dict[str, Any]:

    provider = provider.strip().lower()
    model = model.strip()

    if provider not in DEFAULT_HOSTS:
        raise ValueError("unsupported local provider")

    if not model:
        raise ValueError("model is required")

    store = cards or ModelCardStore()
    run_store = runs or BenchmarkRunStore()
    host = _provider_host(config, provider)

    llm = create_llm(
        ModelConfig(
            provider=provider,
            host=host,
            name=model,
            timeout=600,
            native_tools=True,
        )
    )

    text = benchmark_model(llm, attempts=1, tool_attempts=1)
    quality = benchmark_quality(llm, attempts=1)
    memory = benchmark_memory(llm, attempts=1)
    coding = (
        benchmark_coding(llm, attempts=1)
        if include_coding
        else None
    )
    production = benchmark_production(
        llm,
        registry=registry,
        attempts=1,
    )

    quality["tasks"]["memory"] = memory["tasks"]["memory"]

    if coding is not None:
        quality["tasks"]["coding_exec"] = (
            coding["tasks"]["coding_exec"]
        )

    card = store.load(provider, model) or {}
    card.update(text)
    card["quality"] = quality
    card["memory"] = memory
    card["production"] = production

    if coding is not None:
        card["coding"] = coding
    card["capabilities_verified"] = verified_capabilities(card)
    card["last_tested_at"] = text["tested_at"]

    store.save(card)

    try:
        run_store.save({
            **text,
            "quality": quality,
            "memory": memory,
            "coding": coding,
            "production": production,
        })
    except Exception:
        pass

    return _clean_card(card)
