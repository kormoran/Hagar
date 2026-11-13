"""Tool Wikidata esposti al modello attraverso il contratto Hagar."""

from __future__ import annotations

import json

from typing import Any

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry

from .client import WikidataClient


def _json(
    payload: Any,
) -> str:

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def _error(
    exc: Exception,
) -> str:

    return _json(
        {
            "success": False,
            "error": str(exc),
        }
    )


class WikidataToolProvider:
    """Registra e implementa i quattro tool del plugin."""

    def __init__(
        self,
        client: WikidataClient,
    ) -> None:

        self.client = client

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="wikidata.search",
                description=(
                    "Search Wikidata items or properties "
                    "by label. Returns IDs, labels, "
                    "descriptions and aliases. Use the "
                    "returned QID/PID with "
                    "wikidata.entity or wikidata.article."
                ),
                category="wikidata",
                capabilities=Capability.NETWORK,
                origin="plugin.wikidata",
                parameters=[
                    ToolParameter(
                        name="query",
                        param_type="string",
                        description=(
                            "Text to search for, in the "
                            "selected language."
                        ),
                    ),
                    ToolParameter(
                        name="language",
                        param_type="string",
                        description=(
                            "Language code for labels and "
                            "search, e.g. it or en. "
                            "Default: it."
                        ),
                        required=False,
                        default=None,
                    ),
                    ToolParameter(
                        name="limit",
                        param_type="integer",
                        description=(
                            "Maximum number of results "
                            "(1-50). Default: 10."
                        ),
                        required=False,
                        default=10,
                    ),
                    ToolParameter(
                        name="entity_type",
                        param_type="string",
                        description=(
                            "item or property. "
                            "Default: item."
                        ),
                        required=False,
                        default="item",
                    ),
                ],
                handler=self.search,
            )
        )

        registry.register(
            ToolDefinition(
                name="wikidata.entity",
                description=(
                    "Fetch one or more Wikidata entities "
                    "by ID (Q..., P..., L...) with labels, "
                    "descriptions, aliases, Wikipedia "
                    "links and a compact summary of "
                    "statements. Referenced entity labels "
                    "can be resolved."
                ),
                category="wikidata",
                capabilities=Capability.NETWORK,
                origin="plugin.wikidata",
                parameters=[
                    ToolParameter(
                        name="ids",
                        param_type="string",
                        description=(
                            "Wikidata IDs separated by "
                            "commas, e.g. Q42,Q5. "
                            "At most 10 IDs."
                        ),
                    ),
                    ToolParameter(
                        name="language",
                        param_type="string",
                        description=(
                            "Language code for labels and "
                            "descriptions. Default: it."
                        ),
                        required=False,
                        default=None,
                    ),
                    ToolParameter(
                        name="include_claims",
                        param_type="boolean",
                        description=(
                            "Include compact statements. "
                            "Default: true."
                        ),
                        required=False,
                        default=True,
                    ),
                    ToolParameter(
                        name="max_claims",
                        param_type="integer",
                        description=(
                            "Maximum statements per entity "
                            "(1-300). Default: 50."
                        ),
                        required=False,
                        default=50,
                    ),
                    ToolParameter(
                        name="resolve_labels",
                        param_type="boolean",
                        description=(
                            "Resolve labels of properties "
                            "and entity-valued statements "
                            "with extra requests. "
                            "Default: true."
                        ),
                        required=False,
                        default=True,
                    ),
                ],
                handler=self.entity,
            )
        )

        registry.register(
            ToolDefinition(
                name="wikidata.article",
                description=(
                    "Read the plain-text extract of a "
                    "Wikipedia article, by Wikidata "
                    "entity ID or by article title. "
                    "Returns up to max_chars characters "
                    "and the article URL."
                ),
                category="wikidata",
                capabilities=Capability.NETWORK,
                origin="plugin.wikidata",
                parameters=[
                    ToolParameter(
                        name="entity_id",
                        param_type="string",
                        description=(
                            "Wikidata entity ID, e.g. Q42. "
                            "Provide this or title, not "
                            "both."
                        ),
                        required=False,
                        default=None,
                    ),
                    ToolParameter(
                        name="title",
                        param_type="string",
                        description=(
                            "Wikipedia article title. "
                            "Provide this or entity_id, "
                            "not both."
                        ),
                        required=False,
                        default=None,
                    ),
                    ToolParameter(
                        name="language",
                        param_type="string",
                        description=(
                            "Wikipedia language code, "
                            "e.g. it or en. Default: it."
                        ),
                        required=False,
                        default=None,
                    ),
                    ToolParameter(
                        name="intro_only",
                        param_type="boolean",
                        description=(
                            "Return only the introduction. "
                            "Default: false."
                        ),
                        required=False,
                        default=False,
                    ),
                    ToolParameter(
                        name="max_chars",
                        param_type="integer",
                        description=(
                            "Maximum characters to return "
                            "(200-20000). Default: 4000."
                        ),
                        required=False,
                        default=4000,
                    ),
                ],
                handler=self.article,
            )
        )

        registry.register(
            ToolDefinition(
                name="wikidata.query",
                description=(
                    "Run a read-only SPARQL SELECT query "
                    "against the Wikidata Query Service. "
                    "Federation via SERVICE is blocked. "
                    "Returns variables and at most "
                    "max_results rows."
                ),
                category="wikidata",
                capabilities=Capability.NETWORK,
                origin="plugin.wikidata",
                parameters=[
                    ToolParameter(
                        name="query",
                        param_type="string",
                        description=(
                            "A SPARQL SELECT query, "
                            "optionally with PREFIX lines."
                        ),
                    ),
                    ToolParameter(
                        name="max_results",
                        param_type="integer",
                        description=(
                            "Maximum rows to return "
                            "(1-500). Default: 100."
                        ),
                        required=False,
                        default=100,
                    ),
                ],
                handler=self.query,
            )
        )

    # ==========================================================
    # Handler
    # ==========================================================

    def search(
        self,
        query: str,
        language: str | None = None,
        limit: int = 10,
        entity_type: str = "item",
    ) -> str:

        try:

            return _json(
                self.client.search(
                    query,
                    language=language,
                    limit=limit,
                    entity_type=entity_type,
                )
            )

        except Exception as exc:  # noqa: BLE001

            return _error(exc)

    def entity(
        self,
        ids: str,
        language: str | None = None,
        include_claims: bool = True,
        max_claims: int = 50,
        resolve_labels: bool = True,
    ) -> str:

        try:

            return _json(
                self.client.entity(
                    ids,
                    language=language,
                    include_claims=include_claims,
                    max_claims=max_claims,
                    resolve_labels=resolve_labels,
                )
            )

        except Exception as exc:  # noqa: BLE001

            return _error(exc)

    def article(
        self,
        entity_id: str | None = None,
        title: str | None = None,
        language: str | None = None,
        intro_only: bool = False,
        max_chars: int = 4000,
    ) -> str:

        try:

            return _json(
                self.client.article(
                    entity_id=entity_id,
                    title=title,
                    language=language,
                    intro_only=intro_only,
                    max_chars=max_chars,
                )
            )

        except Exception as exc:  # noqa: BLE001

            return _error(exc)

    def query(
        self,
        query: str,
        max_results: int = 100,
    ) -> str:

        try:

            return _json(
                self.client.query(
                    query,
                    max_results=max_results,
                )
            )

        except Exception as exc:  # noqa: BLE001

            return _error(exc)
