"""Tool di consultazione della memoria di progetto."""

from __future__ import annotations

import json

from typing import Any
from typing import Callable

from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry
from memory.projects import ProjectStore


class ProjectToolProvider:
    def __init__(
        self,
        projects: ProjectStore,
        project_id_getter: Callable[[], str | None],
    ) -> None:

        self.projects = projects
        self.project_id_getter = project_id_getter

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="memory.project_context",
                description=(
                    "Read project decisions and their rationale. "
                    "Use it when the compact project index is not enough."
                ),
                category="memory",
                capabilities=Capability.MEMORY_READ,
                policy_namespace="projects",
                parameters=[
                    ToolParameter(
                        name="query",
                        param_type="string",
                        description=(
                            "Optional keyword filter."
                        ),
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        name="limit",
                        param_type="integer",
                        description=(
                            "Maximum decisions to return."
                        ),
                        required=False,
                        default=10,
                    ),
                ],
                handler=self.project_context,
            )
        )

    def project_context(
        self,
        query: str = "",
        limit: int = 10,
    ) -> str:

        project_id = self.project_id_getter()

        if not project_id:

            return json.dumps(
                {
                    "error": (
                        "nessun progetto attivo; "
                        "usa /project select"
                    )
                },
                ensure_ascii=False,
            )

        if query.strip():

            decisions = self.projects.search_decisions(
                project_id,
                query,
                limit=limit,
            )

        else:

            decisions = self.projects.list_decisions(
                project_id,
                status="active",
                limit=limit,
            )

        return json.dumps(
            {
                "project": project_id,
                "decisions": [
                    {
                        **item.summary(),
                        "decision": item.decision,
                        "alternatives": list(
                            item.alternatives
                        ),
                        "rationale": item.rationale,
                    }
                    for item in decisions
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
