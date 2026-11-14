"""Test dei dati della pagina modelli."""

from __future__ import annotations

from types import SimpleNamespace

from core.model_browser import list_local_models
from core.model_cards import ModelCardStore


def test_cards_from_multiple_roots_are_visible(tmp_path, monkeypatch):
    import core.model_browser as browser

    monkeypatch.setattr(
        browser,
        "discover",
        lambda provider, host, timeout=2.0: [],
    )
    store = ModelCardStore(tmp_path / "cards")
    store.save({
        "provider": "lmstudio",
        "model": "test-model",
        "last_tested_at": "2026-11-14T10:00:00+00:00",
        "benchmarks": {
            "chat": {
                "attempts": 1,
                "successes": 1,
            }
        },
    })

    data = list_local_models(
        SimpleNamespace(
            model=SimpleNamespace(
                provider="lmstudio",
                name="current",
                host="http://localhost:1234/v1",
            )
        ),
        cards=[store],
    )

    item = next(
        item
        for item in data["models"]
        if item["model"] == "test-model"
    )
    assert item["has_benchmark"] is True
    assert item["card"]["benchmarks"]["chat"]["successes"] == 1
