"""Consolidamento e retention delle memorie.

Il consolidamento è una proposta, non un'operazione automatica: Hagar
trova le skill simili e l'utente decide quali unire. Le fonti non
vengono cancellate, solo archiviate dopo il merge.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Any
from typing import Iterable

from memory.store import MemoryError, Skill


STOPWORDS = frozenset({
    "il", "lo", "la", "i", "gli", "le", "un", "una", "uno",
    "di", "da", "in", "con", "su", "per", "tra", "fra", "e",
    "ed", "o", "a", "al", "alla", "ai", "alle", "del", "della",
    "dei", "delle", "che", "chi", "cosa", "come", "quando",
    "dove", "perche", "perché", "non", "piu", "più", "mi", "ti",
    "si", "ci", "vi", "ho", "hai", "ha", "sono", "è", "sei",
    "sia", "questo", "questa", "quello", "quella", "the", "an",
    "and", "or", "of", "to", "on", "for", "with", "is", "are",
    "what", "how", "why", "do", "does", "you", "it", "this",
    "that", "my", "your",
})


@dataclass(frozen=True, slots=True)
class DuplicateGroup:

    target: Skill
    duplicates: tuple[Skill, ...]
    score: float


def _terms(text: str) -> set[str]:

    words = re.findall(r"[a-z0-9àèéìòù]+", text.lower())

    return {
        word
        for word in words
        if len(word) >= 2 and word not in STOPWORDS
    }


def similarity(left: Skill | str, right: Skill | str) -> float:

    left_text = (
        f"{left.title}\n{left.content}"
        if isinstance(left, Skill)
        else str(left)
    )
    right_text = (
        f"{right.title}\n{right.content}"
        if isinstance(right, Skill)
        else str(right)
    )

    left_terms = _terms(left_text)
    right_terms = _terms(right_text)

    if not left_terms or not right_terms:
        return 0.0

    return len(left_terms & right_terms) / len(
        left_terms | right_terms
    )


def _rank(skill: Skill) -> tuple[int, str, int]:

    return (
        1 if skill.status == "confirmed" else 0,
        skill.created_at,
        len(skill.content),
    )


def find_duplicate_skills(
    store: Any,
    *,
    threshold: float = 0.70,
    limit: int = 500,
) -> list[DuplicateGroup]:
    """Raggruppa skill non archiviate con contenuto simile.

    La soglia è la similarità di Jaccard sui termini di titolo e
    contenuto. Il target è la skill confermata più vecchia; in assenza
    di confermate, la candidata più vecchia.
    """

    if not 0.0 < float(threshold) <= 1.0:
        raise MemoryError("threshold must be between 0 and 1")

    skills = [
        skill
        for skill in store.list_skills(
            status=None,
            limit=max(1, int(limit)),
        )
        if skill.status != "archived"
    ]

    groups: list[list[Skill]] = []

    for skill in skills:

        placed = False

        for group in groups:

            reference = group[0]

            if (
                reference.kind != skill.kind
                or similarity(reference, skill) < threshold
            ):
                continue

            group.append(skill)
            placed = True
            break

        if not placed:
            groups.append([skill])

    result = []

    for group in groups:

        if len(group) < 2:
            continue

        group.sort(key=_rank, reverse=True)
        target = group[0]
        duplicates = tuple(group[1:])
        score = min(
            similarity(target, item)
            for item in duplicates
        )
        result.append(
            DuplicateGroup(
                target=target,
                duplicates=duplicates,
                score=score,
            )
        )

    result.sort(key=lambda item: item.score, reverse=True)
    return result


def merge_skills(
    store: Any,
    target_id: str,
    source_ids: Iterable[str],
) -> Skill:
    """Unisce le fonti nella target e archivia le fonti.

    Non cancella contenuto: se il testo di una fonte non è già presente
    nella target, viene accodato in una sezione con la provenienza.
    """

    target = store.get_skill(target_id)

    if target is None:
        raise MemoryError(f"skill not found: {target_id}")

    if target.status == "archived":
        raise MemoryError(
            "cannot merge into an archived skill"
        )

    sources = []
    seen = {target.id}
    normalized_content = target.content.strip().lower()

    for source_id in source_ids:

        if source_id in seen:
            continue

        source = store.get_skill(source_id)

        if source is None:
            raise MemoryError(f"skill not found: {source_id}")

        if source.id == target.id:
            continue

        if source.status == "archived":
            raise MemoryError(
                f"skill is archived: {source_id}"
            )

        if (
            source.status == "confirmed"
            and target.status != "confirmed"
        ):
            raise MemoryError(
                "cannot merge a confirmed skill into a "
                "non-confirmed target"
            )

        seen.add(source.id)
        sources.append(source)

    if not sources:
        raise MemoryError("no source skills to merge")

    parts = [target.content.strip()]
    tags = list(target.tags)

    for source in sources:

        body = source.content.strip()

        if body.lower() not in normalized_content:

            parts.append(
                f"## Consolidato da {source.id}\n\n{body}"
            )
            normalized_content += "\n" + body.lower()

        for tag in source.tags:
            if tag not in tags:
                tags.append(tag)

    merged = store.update_skill(
        target.id,
        content="\n\n".join(parts),
        tags=tags,
    )

    for source in sources:
        store.set_skill_status(source.id, "archived")

    return merged


def retention_candidates(
    store: Any,
    max_active: int,
) -> list[Skill]:
    """Skill confermate oltre il limite, dalla più vecchia."""

    limit = int(max_active)

    if limit <= 0:
        return []

    confirmed = store.list_skills(
        status="confirmed",
        limit=10000,
    )
    confirmed.sort(key=lambda item: item.created_at)

    return confirmed[: max(0, len(confirmed) - limit)]


def apply_skill_retention(
    store: Any,
    max_active: int,
) -> list[Skill]:
    """Archivia le confermate più vecchie oltre il limite."""

    candidates = retention_candidates(store, max_active)

    for skill in candidates:
        store.set_skill_status(skill.id, "archived")

    return candidates
