"""Tool AIsh: linguaggio di comando sopra i tool Hagar."""

from __future__ import annotations

import json

from core.aish import AishExecutor
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


class AishToolProvider:

    def __init__(
        self,
        registry: ToolRegistry,
        filesystem,
        audit=None,
    ) -> None:

        self.registry = registry
        self.filesystem = filesystem
        self.audit = audit

    def register_tools(self, registry: ToolRegistry) -> None:

        registry.register(
            ToolDefinition(
                name="aish.exec",
                description=(
                    "Execute a small, sandboxed command language. "
                    "This is not a host shell: supported commands are "
                    "pwd, cd, ls, stat, cat, head, tail, wc, grep, "
                    "find, echo, printf, sort, uniq, cut, tr, "
                    "sha256sum, df, date, basename, dirname, true, "
                    "false, mkdir, touch, cp, mv, rm. No redirection, "
                    "no variables, no command substitution, no host "
                    "programs. Every command passes through Hagar tools."
                ),
                category="aish",
                capabilities=Capability.AISH,
                parameters=[
                    ToolParameter(
                        name="script",
                        param_type="string",
                        description="AIsh command or pipeline.",
                    )
                ],
                handler=self.exec,
            )
        )

    def exec(self, script: str) -> str:

        executor = AishExecutor(
            self.registry,
            self.filesystem,
            audit=self.audit,
        )
        result = executor.execute(script)

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
