"""Test della scelta del profilo per turno."""

from __future__ import annotations

from core.models import BrokerConfig
from core.task_profile import TaskProfile, TaskProfileStore
from core.task_router import choose_profile


def profiles(*names: str) -> TaskProfileStore:
    return TaskProfileStore([
        TaskProfile(name=name)
        for name in names
    ])


def test_routes_coding_request():
    store = profiles("quick_chat", "coding", "structured_extraction")

    assert choose_profile(
        "Scrivi una funzione Python con pytest",
        store,
        "coding",
    ) == "coding"


def test_routes_extraction_request():
    store = profiles("quick_chat", "coding", "structured_extraction")

    assert choose_profile(
        "Estrai un JSON con questo schema",
        store,
        "coding",
    ) == "structured_extraction"


def test_routes_private_request():
    store = profiles("quick_chat", "private_chat")

    assert choose_profile(
        "Rispondi in locale, è un dato privato",
        store,
        "quick_chat",
    ) == "private_chat"


def test_routes_images_to_vision_when_available():
    store = profiles("quick_chat", "vision")

    assert choose_profile(
        "Cosa vedi?",
        store,
        "quick_chat",
        images=True,
    ) == "vision"


def test_falls_back_when_profile_is_missing():
    store = profiles("quick_chat")

    assert choose_profile(
        "Refactor di una funzione Python",
        store,
        "coding",
    ) == "quick_chat"


def test_auto_route_default_is_enabled():
    assert BrokerConfig().auto_route is True
