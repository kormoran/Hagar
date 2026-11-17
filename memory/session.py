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

CHUNK_PROMPT = """\
Sei Hagar. Riassumi solo la parte di sessione che ricevi.
Rispondi SOLO con un oggetto JSON:
{
  "summary": "riassunto conciso ma completo di questa parte",
  "decisions": [
    {
      "title": "titolo breve",
      "decision": "cosa è stato deciso",
      "alternatives": ["strada scartata 1"],
      "rationale": "perché"
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
        session_id: str | None = None,
        context_window: int | None = None,
        embedding_index: Any = None,
    ) -> None:

        self.memory = memory
        self.projects = projects
        self.project_id = project_id
        self.llm = llm
        self.audit = audit
        self.input_func = input_func or input
        self.output = output_func or print
        self.summary_max_chars = int(summary_max_chars)
        self.session_id = session_id or memory.session_id
        self.context_window = (
            int(context_window)
            if context_window
            else 8192
        )
        self.embedding_index = embedding_index

    def finish(
        self,
        *,
        archive: bool = True,
    ) -> dict[str, Any]:

        turns = self._turns()

        if not turns:
            return {
                "turns": 0,
                "summary": None,
                "archived": [],
                "decisions": [],
            }

        transcript = self._transcript(turns)

        summary, proposed = self._generate_with_context(
            transcript,
            turns,
        )

        if len(summary) > self.summary_max_chars:
            summary = (
                summary[: self.summary_max_chars]
                .rstrip()
                + "…"
            )

        archived = (
            self.memory.archive_session(
                project=self.project_id,
            )
            if archive
            else []
        )

        digest = self._archived_digest(
            archived,
            transcript,
        )

        summary_path = self.memory.write_summary(
            summary,
            project=self.project_id,
            archived=archived,
            transcript_sha256=digest,
            session_id=self.session_id,
        )

        self._index_summary(
            summary_path,
            summary,
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
                        session=self.session_id,
                        auto_saved=False,
                    )

                except Exception:
                    continue

                created_ids.append(decision.id)
                self._index_decision(
                    decision.id,
                    item,
                )

            self._review(created_ids)

        self._record(
            "memory.summary",
            session=self.session_id,
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

    def _turns(self) -> list[Turn]:

        if self.session_id == self.memory.session_id:
            return self.memory.session_turns()

        rows = self.memory.read_session(self.session_id)

        return [
            Turn(
                session=str(row["session"]),
                turn_id=str(row["turn"]),
                timestamp=str(row["timestamp"]),
                question=str(row["question"]),
                answer=str(row["answer"]),
            )
            for row in rows
        ]

    def _budget_chars(self) -> int:

        tokens = max(512, int(self.context_window))
        reserve = 1024
        available = max(256, tokens - reserve)
        return max(1000, available * 4)

    def _turn_text(self, turn: Turn) -> str:

        return (
            f"[{turn.timestamp}] Utente: "
            f"{_clip(turn.question, 1500)}\n"
            f"Hagar: {_clip(turn.answer, 2500)}"
        )

    def _transcript(
        self,
        turns: list[Turn],
    ) -> str:

        return "\n".join(
            self._turn_text(turn)
            for turn in turns
        )

    def _chunks(
        self,
        turns: list[Turn],
        budget: int,
    ) -> list[tuple[str, list[Turn]]]:

        chunks: list[tuple[str, list[Turn]]] = []
        current: list[Turn] = []
        current_len = 0

        for turn in turns:

            text = self._turn_text(turn)

            if current and current_len + len(text) + 1 > budget:

                chunks.append(
                    (
                        "\n".join(
                            self._turn_text(item)
                            for item in current
                        ),
                        current,
                    )
                )
                current = []
                current_len = 0

            if len(text) > budget:

                if current:

                    chunks.append(
                        (
                            "\n".join(
                                self._turn_text(item)
                                for item in current
                            ),
                            current,
                        )
                    )
                    current = []
                    current_len = 0

                for start in range(0, len(text), budget):
                    chunks.append(
                        (
                            text[start:start + budget],
                            [],
                        )
                    )
                continue

            current.append(turn)
            current_len += len(text) + 1

        if current:

            chunks.append(
                (
                    "\n".join(
                        self._turn_text(item)
                        for item in current
                    ),
                    current,
                )
            )

        return chunks or [("", [])]

    @staticmethod
    def _text_chunks(
        text: str,
        budget: int,
    ) -> list[str]:

        if len(text) <= budget:
            return [text]

        chunks = []
        current: list[str] = []
        current_len = 0

        for paragraph in text.split("\n\n"):

            if current and current_len + len(paragraph) + 2 > budget:

                chunks.append("\n\n".join(current))
                current = []
                current_len = 0

            if len(paragraph) > budget:

                for start in range(0, len(paragraph), budget):
                    chunks.append(paragraph[start:start + budget])
                continue

            current.append(paragraph)
            current_len += len(paragraph) + 2

        if current:
            chunks.append("\n\n".join(current))

        return chunks

    def _generate_with_context(
        self,
        transcript: str,
        turns: list[Turn],
    ) -> tuple[str, list[dict[str, Any]]]:

        budget = self._budget_chars()

        if len(transcript) <= budget:
            return self._generate(
                transcript,
                turns,
                prompt=SUMMARY_PROMPT,
            )

        partials: list[str] = []
        decisions: list[dict[str, Any]] = []

        for chunk, chunk_turns in self._chunks(turns, budget):

            summary, proposed = self._generate(
                chunk,
                chunk_turns,
                prompt=CHUNK_PROMPT,
            )
            partials.append(summary)
            decisions.extend(proposed)

        combined = "\n\n".join(partials)

        while len(combined) > budget:

            groups = self._text_chunks(combined, budget)

            if len(groups) <= 1:
                combined = groups[0] if groups else ""
                break

            partials = [
                self._generate(
                    group,
                    [],
                    prompt=CHUNK_PROMPT,
                )[0]
                for group in groups
            ]
            combined = "\n\n".join(partials)

        final, proposed = self._generate(
            combined,
            turns,
            prompt=SUMMARY_PROMPT,
        )
        decisions.extend(proposed)

        unique = []
        seen = set()

        for item in decisions:
            key = (
                str(item.get("title", "")).strip(),
                str(item.get("decision", "")).strip(),
            )

            if not key[0] or key in seen:
                continue

            seen.add(key)
            unique.append(item)

        return final, unique[:20]

    def _generate(
        self,
        transcript: str,
        turns: list[Turn],
        *,
        prompt: str = SUMMARY_PROMPT,
    ) -> tuple[str, list[dict[str, Any]]]:

        if self.llm is not None:

            try:

                raw = self.llm.chat(
                    [
                        {
                            "role": "system",
                            "content": prompt,
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
            f"Sessione {self.session_id}: "
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

    def _index_summary(
        self,
        path: Any,
        text: str,
    ) -> None:

        if self.embedding_index is None:
            return

        raw = str(path).replace("\\", "/")

        if not raw.startswith("sqlite:summary/"):
            return

        summary_id = raw.rsplit("/", 1)[-1]

        try:

            self.embedding_index.upsert(
                "summary",
                summary_id,
                text,
                project=self.project_id,
                status="candidate",
            )

        except Exception as exc:

            self._record(
                "memory.embedding_failed",
                entity="summary",
                entity_id=summary_id,
                error=str(exc),
            )

    def _index_decision(
        self,
        decision_id: str,
        item: dict[str, Any],
    ) -> None:

        if self.embedding_index is None:
            return

        try:

            self.embedding_index.upsert(
                "decision",
                decision_id,
                "\n".join([
                    str(item.get("title", "")),
                    str(item.get("decision", "")),
                    str(item.get("rationale", "")),
                ]),
                project=self.project_id,
                status="candidate",
            )

        except Exception as exc:

            self._record(
                "memory.embedding_failed",
                entity="decision",
                entity_id=decision_id,
                error=str(exc),
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
