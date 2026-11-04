"""Chiusura sessione: summary, archivio chat e memorie di progetto."""

from __future__ import annotations

import hashlib
import json

from typing import Any

from memory.projects import ProjectStore
from memory.store import MemoryStore, Turn, _clip


SUMMARY_PROMPT = """\
Sei Hagar. Riassumi la sessione di lavoro per una memoria storica.
Rispondi SOLO con un oggetto JSON:
{
  "summary": "riassunto conciso ma completo",
  "decisions": [
    {
      "title": "titolo breve",
      "decision": "cosa è stato deciso",
      "alternatives": ["strada scartata 1", "strada scartata 2"],
      "rationale": "perché è stata scelta questa strada"
    }
  ]
}
Non inventare decisioni. Se non ci sono decisioni, usa una lista vuota.
"""


class SessionSummarizer:
    """Genera il summary di fine sessione e gestisce la review."""

    def __init__(
        self,
        memory: MemoryStore,
        projects: ProjectStore | None = None,
        project_id: str | None = None,
        llm: Any = None,
        audit: Any = None,
        input_func: Any = None,
        output_func: Any = None,
        summary_max_chars: int = 4000,
    ) -> None:

        self.memory = memory
        self.projects = projects
        self.project_id = project_id
        self.llm = llm
        self.audit = audit
        self.input_func = input_func or input
        self.output = output_func or print
        self.summary_max_chars = int(summary_max_chars)

    def finish(self) -> dict[str, Any]:

        turns = self.memory.session_turns()

        if not turns:
            return {
                "turns": 0,
                "summary": None,
                "archived": [],
                "decisions": [],
            }

        transcript = self._transcript(turns)

        summary, proposed = self._generate(
            transcript,
            turns,
        )

        if len(summary) > self.summary_max_chars:
            summary = (
                summary[: self.summary_max_chars]
                .rstrip()
                + "…"
            )

        archived = self.memory.archive_session()

        digest = self._archived_digest(
            archived,
            transcript,
        )

        summary_path = self.memory.write_summary(
            summary,
            project=self.project_id,
            archived=archived,
            transcript_sha256=digest,
        )

        created_ids: list[str] = []

        if self.projects is not None and self.project_id:

            self.projects.set_project_summary(
                self.project_id,
                summary,
            )

            for item in proposed:

                try:
                    decision = self.projects.create_decision(
                        self.project_id,
                        title=item.get("title", ""),
                        decision=item.get("decision", ""),
                        alternatives=item.get("alternatives"),
                        rationale=item.get(
                            "rationale",
                            "",
                        ),
                        session=self.memory.session_id,
                        auto_saved=False,
                    )

                except Exception:
                    continue

                created_ids.append(decision.id)

            self._review(created_ids)

        self._record(
            "memory.summary",
            session=self.memory.session_id,
            turns=len(turns),
            archived=len(archived),
            decisions=len(created_ids),
            summary_path=str(summary_path).replace("\\", "/"),
        )

        return {
            "turns": len(turns),
            "summary": summary,
            "summary_path": summary_path,
            "archived": archived,
            "decisions": created_ids,
        }

    # ==================================================
    # Generazione
    # ==================================================

    def _transcript(
        self,
        turns: list[Turn],
    ) -> str:

        lines = []

        for turn in turns:

            lines.append(
                f"[{turn.timestamp}] Utente: "
                f"{_clip(turn.question, 1500)}"
            )
            lines.append(
                f"Hagar: {_clip(turn.answer, 2500)}"
            )

        return "\n".join(lines)

    def _archived_digest(
        self,
        archived: list[str],
        fallback: str,
    ) -> str:

        chunks: list[str] = []

        for path in archived:

            try:
                chunks.append(self.memory.vault.read(path))

            except Exception:
                continue

        payload = (
            "\n".join(chunks)
            if chunks
            else fallback
        )

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    def _generate(
        self,
        transcript: str,
        turns: list[Turn],
    ) -> tuple[str, list[dict[str, Any]]]:

        if self.llm is not None:

            try:

                raw = self.llm.chat(
                    [
                        {
                            "role": "system",
                            "content": SUMMARY_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": transcript,
                        },
                    ]
                )

                payload = self._parse(raw)

                if payload is not None:

                    summary = payload.get("summary")

                    if isinstance(summary, str) and summary.strip():

                        decisions = payload.get(
                            "decisions",
                            [],
                        )

                        if not isinstance(decisions, list):
                            decisions = []

                        return summary.strip(), [
                            item
                            for item in decisions
                            if isinstance(item, dict)
                        ][:20]

            except Exception:
                pass

        return self._fallback(turns), []

    def _parse(
        self,
        text: str,
    ) -> dict[str, Any] | None:

        start = text.find("{")
        end = text.rfind("}")

        if start < 0 or end <= start:
            return None

        try:
            payload = json.loads(
                text[start:end + 1]
            )

        except json.JSONDecodeError:
            return None

        return payload if isinstance(payload, dict) else None

    def _fallback(
        self,
        turns: list[Turn],
    ) -> str:

        questions = [
            turn.question.strip()
            for turn in turns
            if turn.question.strip()
        ]

        lines = [
            f"Sessione {self.memory.session_id}: "
            f"{len(turns)} turni.",
        ]

        if questions:
            lines.append(
                "Argomenti: " + "; ".join(
                    _clip(question, 200)
                    for question in questions[-8:]
                )
            )

        lines.append(
            "Summary generato meccanicamente: "
            "il modello non era disponibile."
        )

        return "\n".join(lines)

    # ==================================================
    # Review
    # ==================================================

    def _review(
        self,
        created_ids: list[str],
    ) -> None:

        if self.projects is None or not self.project_id:
            return

        queue = self.projects.review_queue(
            self.project_id
        )

        if not queue:
            return

        try:

            answer = self.input_func(
                f"Rivedere {len(queue)} memorie di progetto? "
                "(y/N): "
            ).strip().lower()

        except (EOFError, KeyboardInterrupt):

            answer = ""

        if answer not in {"y", "yes", "s", "si", "sì"}:

            self.projects.mark_auto_saved(
                self.project_id,
                created_ids,
            )
            self._record(
                "project.review",
                project=self.project_id,
                reviewed=False,
                auto_saved=len(created_ids),
            )
            return

        approved = 0

        for decision in queue:

            self.output("")
            self.output(
                f"[{decision.id}] {decision.title}"
            )
            self.output(
                f"Decisione: {decision.decision}"
            )

            if decision.alternatives:
                self.output(
                    "Alternative: "
                    + "; ".join(decision.alternatives)
                )

            if decision.rationale:
                self.output(
                    f"Motivo: {decision.rationale}"
                )

            try:

                choice = self.input_func(
                    "Confermi? (y/N/a/s/q): "
                ).strip().lower()

            except (EOFError, KeyboardInterrupt):

                break

            if choice in {"q", "quit", "esci"}:
                break

            if choice in {"y", "yes", "s", "si", "sì"}:

                self.projects.set_decision_status(
                    self.project_id,
                    decision.id,
                    "active",
                )
                approved += 1

            elif choice in {"a", "archive", "archivia"}:

                self.projects.set_decision_status(
                    self.project_id,
                    decision.id,
                    "archived",
                )

        self._record(
            "project.review",
            project=self.project_id,
            reviewed=True,
            approved=approved,
        )

    def _record(
        self,
        event: str,
        **fields: Any,
    ) -> None:

        if self.audit is None:
            return

        try:
            self.audit.record(event, **fields)

        except Exception:
            pass
