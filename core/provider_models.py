"""Metadati normalizzati dei modelli esposti dai runtime locali."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests


class ProviderModelError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderModelInfo:
    """Scheda minima e provider-independent del runtime."""

    provider: str
    model: str
    model_type: str = "unknown"
    context_window: int | None = None
    quantization: str | None = None
    state: str | None = None
    capabilities: frozenset[str] = frozenset()
    raw: dict[str, Any] = field(
        default_factory=dict,
        compare=False,
        repr=False,
    )

    @property
    def key(self) -> tuple[str, str]:
        return (
            self.provider.casefold(),
            self.model.casefold(),
        )

    def has_capability(self, name: str) -> bool:
        return name in self.capabilities

    def hagar_capabilities(self) -> frozenset[str]:
        """Solo le capability che Hagar può usare direttamente."""

        mapping = {
            "tools": "tool_calling",
            "tool_calling": "tool_calling",
            "vision": "vision",
            "thinking": "reasoning",
            "reasoning": "reasoning",
            "ocr": "ocr",
        }

        return frozenset(
            mapped
            for source, mapped in mapping.items()
            if source in self.capabilities
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "model_type": self.model_type,
            "context_window": self.context_window,
            "quantization": self.quantization,
            "state": self.state,
            "capabilities": sorted(self.capabilities),
            "hagar_capabilities": sorted(
                self.hagar_capabilities()
            ),
        }


def _positive_int(value: Any) -> int | None:

    if isinstance(value, bool) or not isinstance(value, int):
        return None

    return value if value > 0 else None


def _lmstudio_capabilities(
    payload: dict[str, Any],
) -> frozenset[str]:

    model_type = str(payload.get("type") or "").lower()
    values = set()

    if model_type in {"llm", "vlm"}:
        values.add("text_generation")

    if model_type == "vlm":
        values.add("vision")

    if model_type == "embeddings":
        values.add("embedding")

    for item in payload.get("capabilities") or []:

        name = str(item).lower()

        if name == "tool_use":
            values.add("tool_calling")
        elif name:
            values.add(name)

    return frozenset(values)


def from_lmstudio(
    payload: dict[str, Any],
    *,
    provider: str = "lmstudio",
) -> ProviderModelInfo:

    model = str(payload.get("id") or "").strip()

    if not model:
        raise ProviderModelError("LM Studio model without id")

    return ProviderModelInfo(
        provider=provider,
        model=model,
        model_type=str(payload.get("type") or "unknown"),
        context_window=_positive_int(
            payload.get("max_context_length")
        ),
        quantization=(
            str(payload["quantization"])
            if payload.get("quantization")
            else None
        ),
        state=(
            str(payload["state"])
            if payload.get("state")
            else None
        ),
        capabilities=_lmstudio_capabilities(payload),
        raw=payload,
    )


def _ollama_capabilities(
    show: dict[str, Any],
) -> frozenset[str]:

    values = set()

    for item in show.get("capabilities") or []:

        name = str(item).lower()

        if name == "completion":
            values.add("text_generation")
        elif name == "tools":
            values.add("tool_calling")
        elif name == "thinking":
            values.add("reasoning")
        elif name in {"vision", "embedding", "ocr"}:
            values.add(name)
        elif name:
            values.add(name)

    return frozenset(values)


def from_ollama(
    tag: dict[str, Any],
    show: dict[str, Any] | None = None,
    *,
    provider: str = "ollama",
) -> ProviderModelInfo:

    model = str(tag.get("name") or "").strip()

    if not model:
        raise ProviderModelError("Ollama model without name")

    show = show or {}
    details = tag.get("details") or show.get("details") or {}
    model_info = show.get("model_info") or {}
    context = (
        details.get("context_length")
        or model_info.get("general.context_length")
        or model_info.get("context_length")
    )
    quantization = details.get("quantization_level")

    if isinstance(quantization, dict):
        quantization = None

    return ProviderModelInfo(
        provider=provider,
        model=model,
        model_type=str(details.get("family") or "unknown"),
        context_window=_positive_int(context),
        quantization=(
            str(quantization) if quantization else None
        ),
        state="loaded" if show.get("loaded") else None,
        capabilities=_ollama_capabilities(show),
        raw={"tag": tag, "show": show},
    )


def discover_lmstudio(
    host: str = "http://localhost:1234/v1",
    *,
    timeout: float = 5.0,
) -> list[ProviderModelInfo]:

    base = host.rstrip("/")
    url = (
        base[:-3] + "/api/v0/models"
        if base.endswith("/v1")
        else base + "/api/v0/models"
    )

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise ProviderModelError(
            f"cannot read LM Studio models: {exc}"
        ) from exc

    items = payload.get("data") if isinstance(payload, dict) else None

    if not isinstance(items, list):
        raise ProviderModelError(
            "LM Studio response without model data"
        )

    return [
        from_lmstudio(item)
        for item in items
        if isinstance(item, dict) and item.get("id")
    ]


def discover_ollama(
    host: str = "http://localhost:11434",
    *,
    timeout: float = 5.0,
) -> list[ProviderModelInfo]:

    base = host.rstrip("/")

    try:
        response = requests.get(
            base + "/api/tags",
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise ProviderModelError(
            f"cannot read Ollama models: {exc}"
        ) from exc

    items = payload.get("models") if isinstance(payload, dict) else None

    if not isinstance(items, list):
        raise ProviderModelError(
            "Ollama response without model data"
        )

    result = []

    for tag in items:

        if not isinstance(tag, dict) or not tag.get("name"):
            continue

        show = {}

        try:
            response = requests.post(
                base + "/api/show",
                json={"model": tag["name"]},
                timeout=timeout,
            )
            response.raise_for_status()
            candidate = response.json()

            if isinstance(candidate, dict):
                show = candidate
        except Exception:
            show = {}

        result.append(
            from_ollama(tag, show)
        )

    return result


def discover(
    provider: str,
    host: str | None = None,
    *,
    timeout: float = 5.0,
) -> list[ProviderModelInfo]:

    name = provider.strip().lower()

    if name == "lmstudio":
        return discover_lmstudio(
            host or "http://localhost:1234/v1",
            timeout=timeout,
        )

    if name == "ollama":
        return discover_ollama(
            host or "http://localhost:11434",
            timeout=timeout,
        )

    raise ProviderModelError(
        f"provider discovery not supported: {provider}"
    )
