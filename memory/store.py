# memory/store.py

from __future__ import annotations

import hashlib
import re
import unicodedata

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from memory.vault import Vault


class MemoryError(RuntimeError):
    pass


FRONTMATTER = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z",
    re.DOTALL,
)

TURN_HEADING = re.compile(
    r"(?m)^##\s+"
)

TURN_BODY = re.compile(
    r"\*\*Utente:\*\*\s*(.*?)\s*\*\*Hagar:\*\*\s*(.*)",
    re.DOTALL,
)

SLUG_CHARS = re.compile(
    r"[^a-z0-9]+"
)


def _iso_timestamp(
    when: datetime | None = None,
) -> str:

    moment = when or datetime.now().astimezone()

    if moment.tzinfo is None:
        moment = moment.astimezone()

    return moment.isoformat(timespec="seconds")


def _split_frontmatter(
    text: str,
) -> tuple[dict[str, Any], str]:

    match = FRONTMATTER.match(text)

    if match is None:
        return {}, text

    try:

        meta = yaml.safe_load(match.group(1)) or {}

    except yaml.YAMLError:

        return {}, text

    if not isinstance(meta, dict):
        return {}, text

    return meta, match.group(2)


def _frontmatter(
    data: dict[str, Any],
) -> str:

    body = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )

    return f"---\n{body}---\n"


def slugify(
    title: str,
) -> str:
    """Slug stabile, solo ASCII minuscolo e trattini."""

    normalized = unicodedata.normalize(
        "NFKD",
        title,
    )

    ascii_text = normalized.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    slug = SLUG_CHARS.sub(
        "-",
        ascii_text.lower(),
    ).strip("-")

    if not slug:

        digest = hashlib.sha1(
            title.encode("utf-8")
        ).hexdigest()[:8]

        slug = f"skill-{digest}"

    return slug[:80].strip("-")


def _clip(
    text: str,
    limit: int,
) -> str:

    if len(text) <= limit:
        return text

    return text[:limit] + "…"


def _normalize_tags(
    value: Any,
) -> tuple[str, ...]:

    if value is None:
        return ()

    if isinstance(value, str):
        items = value.split(",")

    elif isinstance(value, (list, tuple, set)):
        items = list(value)

    else:

        raise MemoryError(
            "tags must be a list of strings or a "
            "comma-separated string"
        )

    cleaned = [
        item.strip()
        for item in items
        if isinstance(item, str) and item.strip()
    ]

    return tuple(dict.fromkeys(cleaned))


def _parse_turns(
    text: str,
    fallback_session: str,
) -> list[Turn]:

    meta, body = _split_frontmatter(text)

    session = str(meta.get("session", fallback_session))

    parts = TURN_HEADING.split(body)

    turns: list[Turn] = []

    for part in parts[1:]:

        header, _, rest = part.partition("\n")

        stamp, separator, turn_id = header.partition("·")

        body_match = TURN_BODY.search(rest)

        if body_match is None:
            continue

        turns.append(
            Turn(
                session=session,
                turn_id=turn_id.strip(),
                timestamp=stamp.strip(),
                question=body_match.group(1).strip(),
                answer=body_match.group(2).strip(),
            )
        )

    return turns


@dataclass(frozen=True, slots=True)
class Turn:

    session: str
    turn_id: str
    timestamp: str
    question: str
    answer: str

    def as_dict(self) -> dict[str, str]:

        return {
            "session": self.session,
            "turn": self.turn_id,
            "timestamp": self.timestamp,
            "question": self.question,
            "answer": self.answer,
        }


@dataclass(frozen=True, slots=True)
class Skill:

    id: str
    title: str
    kind: str
    status: str
    tags: tuple[str, ...]
    created_at: str
    source_session: str | None
    source_turn: str | None
    model: str | None
    path: Path

    def summary(self) -> dict[str, Any]:

        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "status": self.status,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "source_session": self.source_session,
            "source_turn": self.source_turn,
        }


class MemoryStore:
    """
    Memoria dell'agente su un vault Obsidian.

    Episodica: una nota per sessione, con i turni accodati (solo domanda
    e risposta, mai output dei tool). Semantica: una nota per skill, con
    frontmatter di provenance e stato ``candidate``.
    """

    KINDS = frozenset({"fact", "procedure"})

    STATUSES = frozenset({
        "candidate",
        "confirmed",
        "archived",
    })

    def __init__(
        self,
        vault: Vault,
        *,
        session_id: str,
        subdir: str = "Hagar",
        context_turns: int = 10,
        max_skill_chars: int = 4000,
        model: str | None = None,
    ) -> None:

        if not session_id:

            raise MemoryError(
                "session_id is required"
            )

        self.vault = vault
        self.session_id = session_id
        self.base = self._validate_subdir(subdir)
        self.context_turns = int(context_turns)
        self.max_skill_chars = int(max_skill_chars)
        self.model = model
        self.current_turn: str | None = None

    @staticmethod
    def _validate_subdir(
        subdir: str,
    ) -> Path:

        if not isinstance(subdir, str) or not subdir.strip():

            raise MemoryError(
                "vault_subdir must be a non-empty string"
            )

        path = Path(subdir)

        if path.is_absolute() or ".." in path.parts:

            raise MemoryError(
                "vault_subdir must stay inside the vault"
            )

        return path

    # ==================================================
    # Stato del turno
    # ==================================================

    def ensure(self) -> None:
        """
        Verifica il vault e crea le cartelle della memoria.

        Serve a scoprire subito un vault assente o non scrivibile,
        invece di fallire a ogni turno.
        """

        if not self.vault.exists():

            raise MemoryError(
                f"Vault not found: {self.vault.root}"
            )

        self.vault.ensure_dir(self.chat_dir)
        self.vault.ensure_dir(self.skills_dir)

    def begin_turn(
        self,
        turn_id: str,
    ) -> None:

        self.current_turn = turn_id

    def end_turn(self) -> None:

        self.current_turn = None

    # ==================================================
    # Memoria episodica
    # ==================================================

    @property
    def chat_dir(self) -> Path:

        return self.base / "chat"

    def append_turn(
        self,
        turn_id: str,
        question: str,
        answer: str,
        when: datetime | None = None,
    ) -> Turn:

        if not isinstance(question, str) or not isinstance(
            answer,
            str,
        ):

            raise MemoryError(
                "question and answer must be strings"
            )

        timestamp = _iso_timestamp(when)

        date = timestamp[:10]

        relative = (
            self.chat_dir
            / f"{date}-{self.session_id}.md"
        )

        if not self.vault.file_exists(relative):

            header = _frontmatter(
                {
                    "session": self.session_id,
                    "type": "chat",
                    "created": timestamp,
                }
            )

            self.vault.write(
                relative,
                header + f"\n# Chat {date}\n",
            )

        self.vault.append(
            relative,
            (
                f"\n## {timestamp} · {turn_id}\n\n"
                f"**Utente:** {question}\n\n"
                f"**Hagar:** {answer}\n"
            ),
        )

        return Turn(
            session=self.session_id,
            turn_id=turn_id,
            timestamp=timestamp,
            question=question,
            answer=answer,
        )

    def _all_turns(self) -> list[Turn]:

        turns: list[Turn] = []

        for path in self.vault.list_files(
            self.chat_dir,
            "*.md",
        ):

            try:

                text = path.read_text(encoding="utf-8")

            except OSError:
                continue

            turns.extend(
                _parse_turns(text, path.stem)
            )

        turns.sort(key=lambda turn: turn.timestamp)

        return turns

    def recent_turns(
        self,
        limit: int | None = None,
        session: str | None = None,
    ) -> list[Turn]:
        """Ultimi turni in ordine cronologico (i più vecchi prima)."""

        limit = (
            self.context_turns
            if limit is None
            else int(limit)
        )

        if limit <= 0:
            return []

        turns = self._all_turns()

        if session is not None:

            turns = [
                turn
                for turn in turns
                if turn.session == session
            ]

        return turns[-limit:]

    def search_turns(
        self,
        query: str,
        limit: int = 10,
        session: str | None = None,
    ) -> list[Turn]:
        """Turni che contengono la query, dal più recente."""

        needle = query.strip().lower()

        if not needle:
            return []

        turns = self._all_turns()

        if session is not None:

            turns = [
                turn
                for turn in turns
                if turn.session == session
            ]

        matches = [
            turn
            for turn in turns
            if (
                needle in turn.question.lower()
                or needle in turn.answer.lower()
            )
        ]

        matches.sort(
            key=lambda turn: turn.timestamp,
            reverse=True,
        )

        return matches[: max(1, int(limit))]

    def context_text(
        self,
    ) -> tuple[str | None, int]:
        """
        Contesto pronto per il prompt: ultimi turni, dal più vecchio.
        """

        turns = self.recent_turns(
            self.context_turns
        )

        if not turns:
            return None, 0

        lines = [
            "Contesto delle conversazioni precedenti "
            "(dalla più vecchia):"
        ]

        for turn in turns:

            lines.append(
                f"[{turn.timestamp}] Utente: "
                f"{_clip(turn.question, 500)}"
            )

            lines.append(
                f"Hagar: {_clip(turn.answer, 1000)}"
            )

        return "\n".join(lines), len(turns)

    # ==================================================
    # Memoria semantica
    # ==================================================

    @property
    def skills_dir(self) -> Path:

        return self.base / "skills"

    def create_skill(
        self,
        title: str,
        content: str,
        kind: str = "procedure",
        tags: Any = None,
        when: datetime | None = None,
    ) -> tuple[Skill, bool]:
        """
        Crea una skill candidata.

        Restituisce ``(skill, duplicate)``. Se lo slug esiste già non
        sovrascrive nulla: restituisce la skill esistente.
        """

        if not isinstance(title, str) or not title.strip():

            raise MemoryError(
                "title must be a non-empty string"
            )

        if not isinstance(content, str) or not content.strip():

            raise MemoryError(
                "content must be a non-empty string"
            )

        if len(content) > self.max_skill_chars:

            raise MemoryError(
                "content exceeds max_skill_chars "
                f"({self.max_skill_chars})"
            )

        if not isinstance(kind, str) or kind.lower() not in self.KINDS:

            raise MemoryError(
                "kind must be 'fact' or 'procedure'"
            )

        kind = kind.lower()

        slug = slugify(title)

        relative = self.skills_dir / f"{slug}.md"

        if self.vault.file_exists(relative):

            existing = self.get_skill(slug)

            if existing is not None:
                return existing, True

        timestamp = _iso_timestamp(when)

        tags_tuple = _normalize_tags(tags)

        self.vault.write(
            relative,
            _frontmatter(
                {
                    "id": slug,
                    "title": title.strip(),
                    "kind": kind,
                    "status": "candidate",
                    "tags": list(tags_tuple),
                    "source_session": self.session_id,
                    "source_turn": self.current_turn,
                    "model": self.model,
                    "created_at": timestamp,
                }
            )
            + "\n"
            + content.strip()
            + "\n",
        )

        return (
            Skill(
                id=slug,
                title=title.strip(),
                kind=kind,
                status="candidate",
                tags=tags_tuple,
                created_at=timestamp,
                source_session=self.session_id,
                source_turn=self.current_turn,
                model=self.model,
                path=relative,
            ),
            False,
        )

    def get_skill(
        self,
        skill_id: str,
    ) -> Skill | None:

        relative = self.skills_dir / f"{skill_id}.md"

        if not self.vault.file_exists(relative):
            return None

        try:

            text = self.vault.read(relative)

        except OSError:
            return None

        return self._skill_from_text(
            relative,
            text,
        )

    def list_skills(
        self,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Skill]:

        if kind is not None and kind not in self.KINDS:

            raise MemoryError(
                "kind must be 'fact' or 'procedure'"
            )

        if status is not None and status not in self.STATUSES:

            raise MemoryError(
                "status must be candidate, confirmed or archived"
            )

        skills: list[Skill] = []

        for path in self.vault.list_files(
            self.skills_dir,
            "*.md",
        ):

            try:

                text = path.read_text(encoding="utf-8")

            except OSError:
                continue

            try:

                relative = path.relative_to(
                    self.vault.root.resolve()
                )

            except ValueError:

                relative = path

            skill = self._skill_from_text(
                relative,
                text,
            )

            if skill is None:
                continue

            if kind is not None and skill.kind != kind:
                continue

            if status is not None and skill.status != status:
                continue

            skills.append(skill)

        skills.sort(
            key=lambda skill: skill.created_at,
            reverse=True,
        )

        return skills[: max(1, int(limit))]

    def _skill_from_text(
        self,
        path: Path,
        text: str,
    ) -> Skill | None:

        meta, _ = _split_frontmatter(text)

        if not meta:
            return None

        tags_value = meta.get("tags") or []

        if not isinstance(tags_value, list):
            tags_value = []

        return Skill(
            id=str(meta.get("id") or path.stem),
            title=str(meta.get("title") or path.stem),
            kind=str(meta.get("kind", "procedure")),
            status=str(meta.get("status", "candidate")),
            tags=tuple(
                str(tag)
                for tag in tags_value
            ),
            created_at=str(meta.get("created_at", "")),
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
            model=(
                str(meta["model"])
                if meta.get("model")
                else None
            ),
            path=path,
        )
