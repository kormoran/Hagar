# memory/tools.py

from __future__ import annotations

import json

from typing import Any

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry

from memory.store import MemoryStore


def _limit(
    value: Any,
    default: int,
    maximum: int,
) -> int:

    if value is None or isinstance(value, bool):
        number = default

    else:

        try:
            number = int(value)

        except (TypeError, ValueError):
            number = default

    return max(1, min(number, maximum))


def _optional(
    value: Any,
) -> str | None:

    if not isinstance(value, str):
        return None

    value = value.strip()

    return value or None


class MemoryToolProvider:
    """Espone la memoria dell'agente come tool."""

    def __init__(
        self,
        store: MemoryStore,
    ) -> None:

        self.store = store

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="memory.create_skill",
                description=(
                    "Save a durable memory (a 'skill') in the "
                    "vault. Use it only when the user asks to "
                    "remember something or when a reusable "
                    "procedure or fact is clearly worth keeping. "
                    "The memory is stored as a candidate and can "
                    "be reviewed later."
                ),
                category="memory",
                capabilities=Capability.MEMORY_WRITE,
                policy_namespace="skills",
                parameters=[
                    ToolParameter(
                        name="title",
                        param_type="string",
                        description=(
                            "Short, specific title."
                        ),
                    ),
                    ToolParameter(
                        name="content",
                        param_type="string",
                        description=(
                            "The memory itself: steps for a "
                            "procedure, or a fact with context."
                        ),
                    ),
                    ToolParameter(
                        name="kind",
                        param_type="string",
                        description=(
                            "'procedure' (default) or 'fact'."
                        ),
                        required=False,
                        default="procedure",
                    ),
                    ToolParameter(
                        name="tags",
                        param_type="array",
                        description=(
                            "Optional list of tags."
                        ),
                        required=False,
                        default=None,
                    ),
                ],
                handler=self.create_skill,
            )
        )

        registry.register(
            ToolDefinition(
                name="memory.list_skills",
                description=(
                    "List the memories saved in the vault, "
                    "optionally filtered by kind or status. "
                    "Returns id, title, kind, status, tags and "
                    "provenance for each memory."
                ),
                category="memory",
                capabilities=Capability.MEMORY_READ,
                policy_namespace="skills",
                parameters=[
                    ToolParameter(
                        name="kind",
                        param_type="string",
                        description=(
                            "Filter: 'fact' or 'procedure'."
                        ),
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        name="status",
                        param_type="string",
                        description=(
                            "Filter: 'candidate', 'confirmed' "
                            "or 'archived'."
                        ),
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        name="limit",
                        param_type="integer",
                        description=(
                            "Maximum number of memories "
                            "(default 20)."
                        ),
                        required=False,
                        default=20,
                    ),
                ],
                handler=self.list_skills,
            )
        )

        registry.register(
            ToolDefinition(
                name="memory.get_context",
                description=(
                    "Retrieve previous chat turns. Without a "
                    "query it returns the most recent turns; with "
                    "a query it searches past conversations for "
                    "matching turns."
                ),
                category="memory",
                capabilities=Capability.MEMORY_READ,
                policy_namespace="chat",
                parameters=[
                    ToolParameter(
                        name="limit",
                        param_type="integer",
                        description=(
                            "Maximum number of turns "
                            "(default 5)."
                        ),
                        required=False,
                        default=5,
                    ),
                    ToolParameter(
                        name="query",
                        param_type="string",
                        description=(
                            "Optional keyword to search for."
                        ),
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        name="session",
                        param_type="string",
                        description=(
                            "Optional session id to restrict "
                            "the search."
                        ),
                        required=False,
                        default="",
                    ),
                ],
                handler=self.get_context,
            )
        )

    # ==================================================
    # Handlers
    # ==================================================

    def create_skill(
        self,
        title: str,
        content: str,
        kind: str = "procedure",
        tags: Any = None,
    ) -> str:

        skill, duplicate = self.store.create_skill(
            title,
            content,
            kind=kind,
            tags=tags,
        )

        payload = skill.summary()

        payload["path"] = skill.path.as_posix()
        payload["duplicate"] = duplicate

        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )

    def list_skills(
        self,
        kind: str = "",
        status: str = "",
        limit: Any = 20,
    ) -> str:

        skills = self.store.list_skills(
            kind=_optional(kind),
            status=_optional(status),
            limit=_limit(limit, 20, 100),
        )

        return json.dumps(
            [skill.summary() for skill in skills],
            ensure_ascii=False,
            indent=2,
        )

    def get_context(
        self,
        limit: Any = 5,
        query: str = "",
        session: str = "",
    ) -> str:

        limit = _limit(limit, 5, 50)

        query_text = _optional(query)
        session_id = _optional(session)

        if query_text:

            turns = self.store.search_turns(
                query_text,
                limit=limit,
                session=session_id,
            )

        else:

            turns = self.store.recent_turns(
                limit=limit,
                session=session_id,
            )

        return json.dumps(
            [turn.as_dict() for turn in turns],
            ensure_ascii=False,
            indent=2,
        )
