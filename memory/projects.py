"""Memoria di progetto: progetti e decision log su Vault.

La memoria di progetto è distinta dalle skill: registra decisioni,
alternative e motivazioni di un progetto specifico. Le decisioni non si
riscrivono: una nuova decisione può sostituirne una vecchia.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from memory.store import (
    MemoryError,
    _frontmatter,
    _iso_timestamp,
    _split_frontmatter,
    slugify,
)
from memory.vault import Vault


PROJECT_STATUSES = frozenset({"active", "archived"})
DECISION_STATUSES = frozenset(
    {"candidate", "active", "superseded", "archived"}
)


class ProjectError(MemoryError):
    pass


@dataclass(frozen=True, slots=True)
class Project:

    id: str
    title: str
    status: str
    created_at: str
    last_activity: str
    summary: str
    path: Path
    active_decisions: int = 0


@dataclass(frozen=True, slots=True)
class Decision:

    id: str
    project: str
    title: str
    decision: str
    alternatives: tuple[str, ...]
    rationale: str
    status: str
    created_at: str
    reviewed_at: str | None
    auto_saved: bool
    source_session: str | None
    source_turn: str | None
    path: Path

    def summary(self) -> dict[str, Any]:

        return {
            "id": self.id,
            "project": self.project,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "auto_saved": self.auto_saved,
            "source_session": self.source_session,
            "source_turn": self.source_turn,
        }


class ProjectStore:
    """Registry dei progetti e decision log."""

    def __init__(
        self,
        vault: Vault,
        subdir: str = "Hagar",
    ) -> None:

        self.vault = vault
        self.base = Path(subdir) / "projects"

    # ==================================================
    # Progetti
    # ==================================================

    def ensure(self) -> None:

        self.vault.ensure_dir(self.base)

    def _project_dir(
        self,
        project_id: str,
    ) -> Path:

        return self.base / project_id

    def _index_path(
        self,
        project_id: str,
    ) -> Path:

        return self._project_dir(project_id) / "index.md"

    def list_projects(
        self,
        include_archived: bool = False,
    ) -> list[Project]:

        projects: list[Project] = []

        for index in self.vault.list_files(
            self.base,
            "*/index.md",
        ):

            project = self._read_project(index)

            if project is None:
                continue

            if (
                not include_archived
                and project.status != "active"
            ):
                continue

            projects.append(project)

        projects.sort(
            key=lambda item: item.last_activity,
            reverse=True,
        )

        return projects

    def get_project(
        self,
        project_id: str,
    ) -> Project | None:

        return self._read_project(
            self._index_path(project_id)
        )

    def create_project(
        self,
        name: str,
        when: datetime | None = None,
    ) -> Project:

        if not isinstance(name, str) or not name.strip():

            raise ProjectError(
                "project name must be a non-empty string"
            )

        project_id = slugify(name.strip())

        if not project_id:

            raise ProjectError("invalid project name")

        index = self._index_path(project_id)

        if self.vault.file_exists(index):

            raise ProjectError(
                f"project already exists: {project_id}"
            )

        moment = _iso_timestamp(when)

        self.vault.write(
            index,
            _frontmatter(
                {
                    "id": project_id,
                    "title": name.strip(),
                    "status": "active",
                    "created_at": moment,
                    "last_activity": moment,
                    "summary": "",
                }
            )
            + f"\n# {name.strip()}\n",
        )

        project = self.get_project(project_id)

        if project is None:

            raise ProjectError(
                f"project not readable after creation: {project_id}"
            )

        return project

    def set_project_status(
        self,
        project_id: str,
        status: str,
        when: datetime | None = None,
    ) -> Project:

        if status not in PROJECT_STATUSES:

            raise ProjectError(
                "project status must be active or archived"
            )

        project = self.get_project(project_id)

        if project is None:

            raise ProjectError(
                f"project not found: {project_id}"
            )

        self._write_project(
            project,
            status=status,
            last_activity=_iso_timestamp(when),
        )

        updated = self.get_project(project_id)

        if updated is None:

            raise ProjectError(
                f"project not readable after update: {project_id}"
            )

        return updated

    def set_project_summary(
        self,
        project_id: str,
        summary: str,
        when: datetime | None = None,
    ) -> Project:

        project = self.get_project(project_id)

        if project is None:

            raise ProjectError(
                f"project not found: {project_id}"
            )

        self._write_project(
            project,
            summary=summary.strip(),
            last_activity=_iso_timestamp(when),
        )

        updated = self.get_project(project_id)

        if updated is None:

            raise ProjectError(
                f"project not readable after summary: {project_id}"
            )

        return updated

    def _read_project(
        self,
        index: Path,
    ) -> Project | None:

        try:

            relative = index.relative_to(
                self.vault.root.resolve()
            )

        except ValueError:

            relative = index

        if not self.vault.file_exists(relative):
            return None

        try:

            text = self.vault.read(relative)

        except OSError:
            return None

        meta, _ = _split_frontmatter(text)

        if not meta:
            return None

        project_id = str(meta.get("id") or index.parent.name)

        decisions = self.list_decisions(
            project_id,
            status="active",
            limit=100000,
        )

        return Project(
            id=project_id,
            title=str(meta.get("title") or project_id),
            status=str(meta.get("status", "active")),
            created_at=str(meta.get("created_at", "")),
            last_activity=str(
                meta.get("last_activity", "")
            ),
            summary=str(meta.get("summary", "")),
            path=relative,
            active_decisions=len(decisions),
        )

    def _write_project(
        self,
        project: Project,
        **changes: Any,
    ) -> None:

        meta = {
            "id": project.id,
            "title": project.title,
            "status": project.status,
            "created_at": project.created_at,
            "last_activity": project.last_activity,
            "summary": project.summary,
        }

        meta.update(changes)

        _, body = _split_frontmatter(
            self.vault.read(project.path)
        )

        self.vault.write(
            project.path,
            _frontmatter(meta) + "\n" + body.strip() + "\n",
        )

    # ==================================================
    # Decisioni
    # ==================================================

    def _decisions_dir(
        self,
        project_id: str,
    ) -> Path:

        return self._project_dir(project_id) / "decisions"

    def create_decision(
        self,
        project_id: str,
        title: str,
        decision: str,
        alternatives: Any = None,
        rationale: str = "",
        status: str = "candidate",
        auto_saved: bool = False,
        session: str | None = None,
        turn: str | None = None,
        when: datetime | None = None,
    ) -> Decision:

        if status not in DECISION_STATUSES:

            raise ProjectError(
                "invalid decision status"
            )

        if not isinstance(title, str) or not title.strip():

            raise ProjectError(
                "decision title must be non-empty"
            )

        if not isinstance(decision, str) or not decision.strip():

            raise ProjectError(
                "decision text must be non-empty"
            )

        project = self.get_project(project_id)

        if project is None:

            raise ProjectError(
                f"project not found: {project_id}"
            )

        moment = _iso_timestamp(when)
        decision_id = (
            f"{moment[:10]}-{slugify(title)}"
        )
        relative = (
            self._decisions_dir(project_id)
            / f"{decision_id}.md"
        )

        suffix = 2

        while self.vault.file_exists(relative):

            relative = (
                self._decisions_dir(project_id)
                / f"{decision_id}-{suffix}.md"
            )
            suffix += 1

        alternatives_tuple = tuple(
            str(item).strip()
            for item in (
                [alternatives]
                if isinstance(alternatives, str)
                else (alternatives or [])
            )
            if str(item).strip()
        )

        self.vault.write(
            relative,
            _frontmatter(
                {
                    "id": relative.stem,
                    "project": project_id,
                    "title": title.strip(),
                    "status": status,
                    "created_at": moment,
                    "reviewed_at": (
                        moment
                        if status in {"active", "archived"}
                        else None
                    ),
                    "auto_saved": bool(auto_saved),
                    "source_session": session,
                    "source_turn": turn,
                    "alternatives": list(
                        alternatives_tuple
                    ),
                    "rationale": rationale.strip(),
                }
            )
            + "\n"
            + decision.strip()
            + "\n",
        )

        self._write_project(
            project,
            last_activity=moment,
        )

        loaded = self._read_decision(relative)

        if loaded is None:

            raise ProjectError(
                f"decision not readable: {relative}"
            )

        return loaded

    def get_decision(
        self,
        project_id: str,
        decision_id: str,
    ) -> Decision | None:

        relative = (
            self._decisions_dir(project_id)
            / f"{decision_id}.md"
        )

        return self._read_decision(relative)

    def list_decisions(
        self,
        project_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Decision]:

        decisions: list[Decision] = []

        for path in self.vault.list_files(
            self._decisions_dir(project_id),
            "*.md",
        ):

            item = self._read_decision(path)

            if item is None:
                continue

            if status is not None and item.status != status:
                continue

            decisions.append(item)

        decisions.sort(
            key=lambda item: item.created_at,
            reverse=True,
        )

        return decisions[: max(1, int(limit))]

    def review_queue(
        self,
        project_id: str,
        limit: int = 1000,
    ) -> list[Decision]:

        decisions = self.list_decisions(
            project_id,
            status="candidate",
            limit=limit,
        )
        decisions.sort(key=lambda item: item.created_at)
        return decisions

    def set_decision_status(
        self,
        project_id: str,
        decision_id: str,
        status: str,
        when: datetime | None = None,
    ) -> Decision:

        if status not in DECISION_STATUSES:

            raise ProjectError(
                "invalid decision status"
            )

        decision = self.get_decision(
            project_id,
            decision_id,
        )

        if decision is None:

            raise ProjectError(
                f"decision not found: {decision_id}"
            )

        moment = _iso_timestamp(when)

        meta, body = _split_frontmatter(
            self.vault.read(decision.path)
        )
        meta["status"] = status
        meta["updated_at"] = moment

        if status in {"active", "archived"}:
            meta["reviewed_at"] = moment

        self.vault.write(
            decision.path,
            _frontmatter(meta)
            + "\n"
            + body.strip()
            + "\n",
        )

        updated = self.get_decision(
            project_id,
            decision_id,
        )

        if updated is None:

            raise ProjectError(
                f"decision not readable: {decision_id}"
            )

        return updated

    def mark_auto_saved(
        self,
        project_id: str,
        decision_ids: list[str],
    ) -> None:

        for decision_id in decision_ids:

            decision = self.get_decision(
                project_id,
                decision_id,
            )

            if decision is None:
                continue

            meta, body = _split_frontmatter(
                self.vault.read(decision.path)
            )
            meta["auto_saved"] = True
            self.vault.write(
                decision.path,
                _frontmatter(meta)
                + "\n"
                + body.strip()
                + "\n",
            )

    def _read_decision(
        self,
        path: Path,
    ) -> Decision | None:

        try:

            relative = path.relative_to(
                self.vault.root.resolve()
            )

        except ValueError:

            relative = path

        if not self.vault.file_exists(relative):
            return None

        try:

            text = self.vault.read(relative)

        except OSError:
            return None

        meta, body = _split_frontmatter(text)

        if not meta:
            return None

        alternatives = meta.get("alternatives") or []

        if not isinstance(alternatives, list):
            alternatives = []

        return Decision(
            id=str(meta.get("id") or path.stem),
            project=str(meta.get("project", "")),
            title=str(meta.get("title") or path.stem),
            decision=body.strip(),
            alternatives=tuple(
                str(item) for item in alternatives
            ),
            rationale=str(meta.get("rationale", "")),
            status=str(meta.get("status", "candidate")),
            created_at=str(meta.get("created_at", "")),
            reviewed_at=(
                str(meta["reviewed_at"])
                if meta.get("reviewed_at")
                else None
            ),
            auto_saved=bool(meta.get("auto_saved", False)),
            source_session=(
                str(meta["source_session"])
                if meta.get("source_session")
                else None
            ),
            source_turn=(
                str(meta["source_turn"])
                if meta.get("source_turn")
                else None
            ),
            path=relative,
        )

    # ==================================================
    # Contesto e ricerca
    # ==================================================

    def search_decisions(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[Decision]:

        needle = query.strip().lower()

        if not needle:
            return []

        matches = [
            item
            for item in self.list_decisions(
                project_id,
                limit=100000,
            )
            if (
                needle in item.title.lower()
                or needle in item.decision.lower()
                or needle in item.rationale.lower()
                or any(
                    needle in alt.lower()
                    for alt in item.alternatives
                )
            )
        ]

        return matches[: max(1, int(limit))]

    def context_index(
        self,
        project_id: str,
        max_decisions: int = 10,
        max_chars: int = 6000,
    ) -> tuple[str, int]:

        project = self.get_project(project_id)

        if project is None:
            return "", 0

        active = (
            self.list_decisions(
                project_id,
                status="active",
                limit=max_decisions,
            )
            if max_decisions > 0
            else []
        )

        lines = [
            f"Progetto: {project.title} [{project.id}]",
            f"Ultima attività: {project.last_activity}",
        ]

        if project.summary:
            lines.append(
                f"Sintesi: {project.summary.strip()}"
            )

        if active:
            lines.append(
                "Decisioni attive recenti:"
            )
            for item in active:
                lines.append(
                    f"- {item.title} ({item.created_at[:10]}, "
                    f"{item.id})"
                )

        lines.append(
            f"Decisioni attive totali: "
            f"{project.active_decisions}"
        )
        lines.append(
            "Dettagli: memory.project_context(query=...)"
        )

        text = "\n".join(lines)

        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"

        return text, len(active)
