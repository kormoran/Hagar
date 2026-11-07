"""Export del database SQLite in una struttura Markdown compatibile."""

from __future__ import annotations

import os

from collections import defaultdict
from pathlib import Path
from typing import Any

from memory.store import MemoryError, _frontmatter


class MarkdownExportError(MemoryError):
    pass


class MarkdownExporter:
    """Esporta chat, skill, summary, progetti e decisioni in Markdown."""

    def __init__(
        self,
        memory,
        projects=None,
        root: str | Path = ".",
    ) -> None:

        self.memory = memory
        self.projects = projects
        self.root = Path(root)

    def export(
        self,
        force: bool = False,
    ) -> dict[str, Any]:

        if not hasattr(self.memory, "database"):
            raise MarkdownExportError(
                "export is available only for the sqlite backend"
            )

        base = self.root / "Hagar"

        if base.exists() and any(base.iterdir()) and not force:
            raise MarkdownExportError(
                f"target is not empty: {base} "
                "(use --force to overwrite generated files)"
            )

        base.mkdir(parents=True, exist_ok=True)

        files = 0
        files += self._export_chats(base)
        files += self._export_skills(base)
        files += self._export_summaries(base)
        files += self._export_projects(base)

        return {
            "root": str(base),
            "files": files,
            "backend": "sqlite",
        }

    # ==================================================
    # Scrittura
    # ==================================================

    @staticmethod
    def _write(path: Path, text: str) -> None:

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        payload = text.encode("utf-8")

        try:

            with temporary.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temporary, path)

        finally:

            temporary.unlink(missing_ok=True)

    # ==================================================
    # Chat
    # ==================================================

    def _export_chats(self, base: Path) -> int:

        sessions = self.memory.list_sessions(limit=100000)
        count = 0

        for session in sessions:

            turns = self.memory.read_session(session["id"])

            if not turns:
                continue

            by_date: dict[str, list[dict]] = defaultdict(list)

            for turn in turns:
                by_date[str(turn["timestamp"])[:10]].append(turn)

            for date, day_turns in by_date.items():

                first = day_turns[0]
                path = base / "chat" / f"{date}-{session['id']}.md"

                body = [f"# Chat {date}"]

                for turn in day_turns:

                    body.append(
                        f"\n## {turn['timestamp']} · {turn['turn']}\n"
                        f"\n**Utente:** {turn['question']}\n"
                        f"\n**Hagar:** {turn['answer']}\n"
                    )

                text = (
                    _frontmatter({
                        "session": session["id"],
                        "type": "chat",
                        "created": first["timestamp"],
                        "archived": bool(session["archived"]),
                    })
                    + "\n".join(body)
                )

                self._write(path, text)
                count += 1

        return count

    # ==================================================
    # Skill
    # ==================================================

    def _export_skills(self, base: Path) -> int:

        skills = self.memory.list_skills(limit=100000)
        count = 0

        for skill in skills:

            path = base / "skills" / f"{skill.id}.md"

            text = (
                _frontmatter({
                    "id": skill.id,
                    "title": skill.title,
                    "kind": skill.kind,
                    "status": skill.status,
                    "tags": list(skill.tags),
                    "source_session": skill.source_session,
                    "source_turn": skill.source_turn,
                    "model": skill.model,
                    "created_at": skill.created_at,
                })
                + skill.content.strip()
                + "\n"
            )

            self._write(path, text)
            count += 1

        return count

    # ==================================================
    # Summary
    # ==================================================

    def _export_summaries(self, base: Path) -> int:

        summaries = self.memory.list_summaries(limit=100000)
        count = 0

        for summary in summaries:

            date = str(summary["created_at"])[:10]
            name = (
                f"{date}-{summary['session_id']}"
                f"-{summary['id']}.md"
            )
            path = base / "summaries" / name

            archived = summary.get("archived_transcripts") or []

            text = (
                _frontmatter({
                    "session": summary["session_id"],
                    "project": summary["project"],
                    "created_at": summary["created_at"],
                    "archived_transcripts": archived,
                    "transcript_sha256": summary["transcript_sha256"],
                })
                + str(summary["body"]).strip()
                + "\n"
            )

            self._write(path, text)
            count += 1

        return count

    # ==================================================
    # Progetti
    # ==================================================

    def _export_projects(self, base: Path) -> int:

        if self.projects is None:
            return 0

        count = 0

        for project in self.projects.list_projects(
            include_archived=True
        ):

            folder = base / "projects" / project.id

            index = folder / "index.md"
            self._write(
                index,
                _frontmatter({
                    "id": project.id,
                    "title": project.title,
                    "status": project.status,
                    "created_at": project.created_at,
                    "last_activity": project.last_activity,
                    "summary": project.summary,
                })
                + f"# {project.title}\n",
            )
            count += 1

            for decision in self.projects.list_decisions(
                project.id,
                limit=100000,
            ):

                path = folder / "decisions" / f"{decision.id}.md"

                text = (
                    _frontmatter({
                        "id": decision.id,
                        "project": decision.project,
                        "title": decision.title,
                        "status": decision.status,
                        "created_at": decision.created_at,
                        "reviewed_at": decision.reviewed_at,
                        "auto_saved": decision.auto_saved,
                        "source_session": decision.source_session,
                        "source_turn": decision.source_turn,
                        "alternatives": list(decision.alternatives),
                        "rationale": decision.rationale,
                    })
                    + decision.decision.strip()
                    + "\n"
                )

                self._write(path, text)
                count += 1

        return count
