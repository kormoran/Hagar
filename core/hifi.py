"""Pre-pass Hi-Fi: interpreta la richiesta prima di rispondere."""

from __future__ import annotations

import json
import re

from dataclasses import dataclass
from typing import Any


class HiFiError(RuntimeError):
    """La classificazione delle interpretazioni non è utilizzabile."""


@dataclass(frozen=True)
class Interpretation:
    text: str
    probability: float


@dataclass(frozen=True)
class HiFiResult:
    interpretations: list[Interpretation]
    margin: float
    needs_clarification: bool

    @property
    def top(self) -> Interpretation:
        return self.interpretations[0]

    @property
    def second(self) -> Interpretation:
        return self.interpretations[1]

    def audit(self) -> dict[str, Any]:
        return {
            "needs_clarification": self.needs_clarification,
            "margin": round(self.margin, 6),
            "interpretations": [
                {
                    "text": item.text,
                    "probability": round(item.probability, 6),
                }
                for item in self.interpretations
            ],
        }


class HiFiResolver:
    """Classifica le interpretazioni e formula eventuali chiarimenti."""

    def __init__(
        self,
        llm: Any,
        *,
        margin: float = 0.20,
        interpretations: int = 3,
    ) -> None:
        self.llm = llm
        self.margin = float(margin)
        self.interpretations = int(interpretations)

        if not 0.0 < self.margin < 1.0:
            raise ValueError("margin must be between 0 and 1")

        if self.interpretations < 2:
            raise ValueError("interpretations must be at least 2")

    def resolve(self, question: str) -> HiFiResult:
        prompt = (
            "La richiesta dell'utente è:\n"
            "<<<\n"
            f"{question}\n"
            ">>>\n\n"
            f"Fornisci le {self.interpretations} interpretazioni più "
            "probabili di questa richiesta e una stima numerica della "
            "probabilità di ciascuna.\n\n"
            "Rispondi SOLO con JSON valido, senza markdown, in questa forma:\n"
            '{"interpretations": ['
            '{"text": "prima interpretazione", "probability": 0.6}, '
            '{"text": "seconda interpretazione", "probability": 0.3}, '
            '{"text": "terza interpretazione", "probability": 0.1}'
            "]}\n"
            "Le probabilità devono essere numeri tra 0 e 1 e la loro "
            "somma deve essere 1."
        )

        try:
            raw = self.llm.chat([
                {
                    "role": "system",
                    "content": (
                        "Sei un analista delle intenzioni dell'utente. "
                        "Non rispondere alla richiesta: classifica solo "
                        "le interpretazioni possibili."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ])
        except Exception as exc:
            raise HiFiError(
                f"interpretation request failed: {exc}"
            ) from exc

        interpretations = self._parse(str(raw))
        top, second = interpretations[0], interpretations[1]
        margin = top.probability - second.probability

        return HiFiResult(
            interpretations=interpretations,
            margin=margin,
            needs_clarification=margin <= self.margin,
        )

    def clarify(
        self,
        question: str,
        result: HiFiResult,
    ) -> str:
        """Chiede al modello di formulare la domanda di chiarimento."""

        prompt = (
            "La richiesta dell'utente è:\n"
            "<<<\n"
            f"{question}\n"
            ">>>\n\n"
            "Le due interpretazioni più probabili sono:\n"
            f"A) {result.top.text}\n"
            f"B) {result.second.text}\n\n"
            "Scrivi all'utente una breve domanda di chiarimento: "
            "chiedi se intende A, B, oppure un'altra interpretazione. "
            "Non rispondere alla richiesta originale. "
            "Usa al massimo tre frasi."
        )

        try:
            text = self.llm.chat([
                {
                    "role": "system",
                    "content": (
                        "Sei Hagar. Devi solo chiedere un chiarimento, "
                        "senza eseguire la richiesta."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ])
        except Exception:
            text = ""

        if isinstance(text, str) and text.strip():
            return text.strip()

        return self.fallback_clarification(result)

    @staticmethod
    def fallback_clarification(result: HiFiResult) -> str:
        return (
            "Non sono sicuro di aver capito la richiesta. "
            f"Intendi:\nA) {result.top.text}\n"
            f"B) {result.second.text}\n"
            "Oppure un'altra interpretazione?"
        )

    @staticmethod
    def resolved_question(question: str, result: HiFiResult) -> str:
        return (
            f"Interpretazione scelta: {result.top.text}\n"
            f"Probabilità stimata: {result.top.probability:.0%}\n\n"
            f"Richiesta originale:\n{question}\n\n"
            "Rispondi alla richiesta originale tenendo conto "
            "dell'interpretazione scelta."
        )

    # ==================================================
    # Parsing
    # ==================================================

    def _parse(self, text: str) -> list[Interpretation]:

        payload = self._json_payload(text)

        raw_items = payload.get("interpretations")

        if not isinstance(raw_items, list):

            raise HiFiError(
                "response must contain an interpretations list"
            )

        items: list[Interpretation] = []

        for index, raw in enumerate(raw_items):

            if not isinstance(raw, dict):
                continue

            raw_text = raw.get("text") or raw.get("interpretation")
            raw_probability = raw.get(
                "probability",
                raw.get("p"),
            )

            if not isinstance(raw_text, str) or not raw_text.strip():
                continue

            probability = self._probability(raw_probability)

            if probability is None:
                continue

            items.append(
                Interpretation(
                    text=raw_text.strip(),
                    probability=probability,
                )
            )

        if len(items) < 2:

            raise HiFiError(
                "at least two valid interpretations are required"
            )

        items.sort(
            key=lambda item: item.probability,
            reverse=True,
        )
        items = items[: self.interpretations]

        total = sum(item.probability for item in items)

        if total <= 0:

            raise HiFiError(
                "interpretation probabilities must be positive"
            )

        normalized = [
            Interpretation(
                text=item.text,
                probability=item.probability / total,
            )
            for item in items
        ]

        return normalized

    @staticmethod
    def _json_payload(text: str) -> dict[str, Any]:

        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            text.strip(),
            flags=re.IGNORECASE,
        )

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start < 0 or end < start:

            raise HiFiError("response does not contain JSON")

        try:
            payload = json.loads(cleaned[start:end + 1])
        except (TypeError, ValueError) as exc:

            raise HiFiError(
                f"invalid interpretation JSON: {exc}"
            ) from exc

        if not isinstance(payload, dict):

            raise HiFiError("interpretation JSON must be an object")

        return payload

    @staticmethod
    def _probability(value: Any) -> float | None:

        if isinstance(value, bool):
            return None

        if isinstance(value, str):

            text = value.strip()

            if text.endswith("%"):
                try:
                    number = float(text[:-1]) / 100
                except ValueError:
                    return None
            else:
                try:
                    number = float(text)
                except ValueError:
                    return None

        elif isinstance(value, (int, float)):
            number = float(value)

        else:
            return None

        if not 0.0 <= number <= 1.0:
            return None

        return number
