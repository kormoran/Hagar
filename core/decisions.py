"""Decision providers: LLM decisori e classificatori locali."""

from __future__ import annotations

import json
import math
import re

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Protocol


class DecisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class DecisionRequest:
    state: str
    question: str
    choices: tuple[str, ...]

    def validate(self) -> None:

        if not isinstance(self.state, str) or not self.state.strip():
            raise DecisionError("state must be non-empty")

        if not isinstance(self.question, str) or not self.question.strip():
            raise DecisionError("question must be non-empty")

        if not self.choices:
            raise DecisionError("choices must be non-empty")

        if len(set(self.choices)) != len(self.choices):
            raise DecisionError("choices must be unique")

        if len(self.choices) > 50:
            raise DecisionError("too many choices (max 50)")

        if len(self.state) > 200_000:
            raise DecisionError("state is too large")


@dataclass(frozen=True)
class DecisionResult:
    choice: str
    probabilities: dict[str, float]
    provider: str
    model: str | None = None

    @property
    def confidence(self) -> float:
        return float(self.probabilities.get(self.choice, 0.0))

    def as_dict(self) -> dict[str, Any]:
        return {
            "choice": self.choice,
            "confidence": round(self.confidence, 6),
            "probabilities": {
                key: round(value, 6)
                for key, value in self.probabilities.items()
            },
            "provider": self.provider,
            "model": self.model,
        }


class DecisionProvider(Protocol):
    name: str

    def decide(self, request: DecisionRequest) -> DecisionResult:
        ...


class LLMDecisionProvider:
    """Usa un LLM testuale come decisore con output JSON."""

    def __init__(
        self,
        llm,
        name: str = "llm",
        model: str | None = None,
    ) -> None:
        self.llm = llm
        self.name = name
        self.model = model or getattr(llm, "model", None)

    def decide(self, request: DecisionRequest) -> DecisionResult:

        request.validate()

        prompt = (
            "You are a decision model. Do not explain. "
            "Return only a JSON object with exactly these keys: "
            '"choice" and "probabilities". '
            "The choice must be one of the supplied labels; "
            "probabilities must sum to 1.\n\n"
            f"STATE:\n{request.state}\n\n"
            f"QUESTION:\n{request.question}\n\n"
            f"CHOICES:\n{json.dumps(list(request.choices), ensure_ascii=False)}"
        )

        text = self.llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You produce calibrated structured decisions. "
                        "Never invent labels."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )

        payload = _parse_json_object(text)
        raw_choice = payload.get("choice")
        raw_probabilities = payload.get("probabilities")

        if raw_choice not in request.choices:
            raise DecisionError(
                "decision model returned an invalid choice"
            )

        if not isinstance(raw_probabilities, dict):
            raise DecisionError(
                "decision model returned no probabilities"
            )

        probabilities: dict[str, float] = {}

        for choice in request.choices:

            value = raw_probabilities.get(choice)

            if not isinstance(value, (int, float)):
                raise DecisionError(
                    f"missing probability for {choice!r}"
                )

            if not math.isfinite(float(value)) or float(value) < 0:
                raise DecisionError(
                    f"invalid probability for {choice!r}"
                )

            probabilities[choice] = float(value)

        total = sum(probabilities.values())

        if total <= 0:
            raise DecisionError("probabilities sum to zero")

        probabilities = {
            key: value / total
            for key, value in probabilities.items()
        }

        return DecisionResult(
            choice=str(raw_choice),
            probabilities=probabilities,
            provider=self.name,
            model=self.model,
        )


class LinearDecisionProvider:
    """Classificatore lineare locale caricato da JSON."""

    def __init__(
        self,
        path: str | Path,
        name: str = "linear",
    ) -> None:

        self.name = name
        self.path = Path(path)
        self.model = str(self.path)

        try:
            payload = json.loads(
                self.path.read_text(encoding="utf-8")
            )

        except (OSError, ValueError) as exc:
            raise DecisionError(
                f"cannot load linear decision model: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise DecisionError("linear model must be a JSON object")

        self.labels = payload.get("labels")
        self.weights = payload.get("weights", {})
        self.bias = payload.get("bias", {})

        if (
            not isinstance(self.labels, list)
            or not self.labels
            or not all(isinstance(item, str) for item in self.labels)
        ):
            raise DecisionError(
                "linear model labels must be a non-empty list"
            )

        if not isinstance(self.weights, dict):
            raise DecisionError("linear model weights must be an object")

        self._labels = tuple(self.labels)

    def decide(self, request: DecisionRequest) -> DecisionResult:

        request.validate()

        for choice in request.choices:
            if choice not in self._labels:
                raise DecisionError(
                    f"linear model does not know label {choice!r}"
                )

        tokens = _tokens(request.state)

        logits: dict[str, float] = {}

        for label in request.choices:

            label_weights = self.weights.get(label, {})

            if not isinstance(label_weights, dict):
                raise DecisionError(
                    f"weights for {label!r} must be an object"
                )

            score = float(self.bias.get(label, 0.0))

            for token in tokens:
                value = label_weights.get(token)
                if isinstance(value, (int, float)):
                    score += float(value)

            logits[label] = score

        probabilities = _softmax(logits)

        return DecisionResult(
            choice=max(probabilities, key=probabilities.get),
            probabilities=probabilities,
            provider=self.name,
            model=self.model,
        )


class DecisionRegistry:
    """Provider disponibili e provider predefinito."""

    def __init__(
        self,
        providers: dict[str, DecisionProvider],
        default: str = "llm",
    ) -> None:

        if not providers:
            raise DecisionError("no decision providers configured")

        self.providers = providers
        self.default = default

        if default not in providers:
            raise DecisionError(
                f"default decision provider not found: {default}"
            )

    def choose(
        self,
        request: DecisionRequest,
        provider: str | None = None,
    ) -> DecisionResult:

        name = provider or self.default
        selected = self.providers.get(name)

        if selected is None:
            raise DecisionError(
                f"unknown decision provider: {name}"
            )

        return selected.decide(request)

    def names(self) -> list[str]:
        return sorted(self.providers)


def build_decision_registry(
    config,
    llm,
) -> DecisionRegistry | None:

    settings = getattr(config, "decisions", None)

    if settings is not None and not settings.enabled:
        return None

    providers: dict[str, DecisionProvider] = {
        "llm": LLMDecisionProvider(llm)
    }
    default = getattr(settings, "default", "llm")

    for entry in getattr(settings, "providers", []):

        if entry.type == "llm":
            providers[entry.name] = LLMDecisionProvider(
                llm,
                name=entry.name,
                model=entry.model,
            )

        elif entry.type == "linear":
            providers[entry.name] = LinearDecisionProvider(
                entry.path,
                name=entry.name,
            )

    if default not in providers:
        raise DecisionError(
            f"default decision provider not found: {default}"
        )

    return DecisionRegistry(providers, default=default)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9àèéìòù]+", text.lower())


def _softmax(values: dict[str, float]) -> dict[str, float]:

    if not values:
        raise DecisionError("cannot compute empty softmax")

    maximum = max(values.values())
    exponentials = {
        key: math.exp(value - maximum)
        for key, value in values.items()
    }
    total = sum(exponentials.values())

    if total <= 0:
        raise DecisionError("invalid decision scores")

    return {
        key: value / total
        for key, value in exponentials.items()
    }


def _parse_json_object(text: Any) -> dict[str, Any]:

    if not isinstance(text, str):
        raise DecisionError("decision model returned no text")

    stripped = text.strip()

    if stripped.startswith("```"):

        lines = stripped.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start < 0 or end < start:
        raise DecisionError("decision model returned no JSON object")

    try:
        payload = json.loads(stripped[start:end + 1])

    except ValueError as exc:
        raise DecisionError(
            f"invalid decision JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise DecisionError("decision JSON must be an object")

    return payload
