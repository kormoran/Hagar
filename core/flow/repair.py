"""Riparazione bounded del codice Hagar Flow."""

from __future__ import annotations

import re

from core.flow.language import LANGUAGE_CARD


SYSTEM_PROMPT = (
    "Sei un riparatore di Hagar Flow. Hagar Flow non è Python completo: "
    "niente import, class, def, lambda, try, comprehension con più di un "
    "for, dict/set comprehension, generatori o accesso a oggetti Python. "
    "Non creare file .py. Restituisci solo il sorgente Hagar Flow corretto, "
    "senza spiegazioni."
)


class FlowRepairer:

    def __init__(
        self,
        llm,
        max_attempts: int = 2,
        audit=None,
    ) -> None:

        self.llm = llm
        self.max_attempts = max(0, int(max_attempts))
        self.audit = audit

    def propose(self, code: str, error: dict) -> str | None:

        if self.llm is None or self.max_attempts <= 0:
            return None

        self._record(
            "flow.repair.start",
            line=error.get("line"),
            message=error.get("message"),
        )

        prompt = (
            f"{LANGUAGE_CARD}\n\n"
            "CODICE DA CORREGGERE:\n"
            "```hagar\n"
            f"{code}\n"
            "```\n\n"
            "ERRORE:\n"
            f"{error.get('message', '')}\n"
            f"riga: {error.get('line')}\n"
            f"hint: {error.get('hint')}\n\n"
            "Restituisci SOLO il codice Hagar Flow corretto, "
            "senza creare file .py."
        )

        try:
            raw = self.llm.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
        except Exception as exc:
            self._record(
                "flow.repair.error",
                error=str(exc),
            )
            return None

        candidate = self._extract(str(raw)).strip()

        if not candidate:
            self._record("flow.repair.empty")
            return None

        return candidate

    @staticmethod
    def _extract(text: str) -> str:

        match = re.search(
            r"```(?:python|hagar|flow)?\s*(.*?)```",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        return match.group(1) if match else text

    def _record(self, event: str, **fields) -> None:
        if self.audit is not None:
            self.audit.record(event, **fields)
