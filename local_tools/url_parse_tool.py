from __future__ import annotations

import json

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry

from local_tools.url_parse import UrlParser


class UrlParseToolProvider:

    def __init__(
        self,
        url_parser: UrlParser,
    ) -> None:

        self.url_parser = url_parser

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="url.parse",
                description=(
                    "Parse a URL into scheme, host, port, path, "
                    "query and fragment. It does not perform DNS "
                    "lookups or network requests."
                ),
                category="url",
                capabilities=Capability.COMPUTE,
                parameters=[
                    ToolParameter(
                        name="url",
                        param_type="string",
                        description="URL or relative reference.",
                    ),
                ],
                handler=self.parse,
            )
        )

    def parse(
        self,
        url: str,
    ) -> str:

        return json.dumps(
            self.url_parser.parse(url),
            ensure_ascii=False,
            indent=2,
        )
