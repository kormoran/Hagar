"""Tool dev.list e dev.run per ricette dichiarate dall'utente."""

from __future__ import annotations

import hashlib
import json

from core.dev_recipes import RecipeBook
from core.dev_runner import DevExecutionError, DevRunner
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


class DevToolProvider:

    def __init__(
        self,
        runner: DevRunner,
        book: RecipeBook,
        audit=None,
    ) -> None:

        self.runner = runner
        self.book = book
        self.audit = audit
        self._changed_notified = False

    def register_tools(self, registry: ToolRegistry) -> None:

        registry.register(
            ToolDefinition(
                name="dev.list",
                description=(
                    "List the developer recipes loaded at Hagar startup. "
                    "Recipes are trusted user configuration for tests, "
                    "debug and build; they are not a general execution API."
                ),
                category="dev",
                capabilities=Capability.DEV_EXEC,
                parameters=[],
                handler=self.list_recipes,
            )
        )

        registry.register(
            ToolDefinition(
                name="dev.run",
                description=(
                    "Run one declared developer recipe (test/debug/build). "
                    "The model cannot provide a command or arbitrary argv; "
                    "it chooses a recipe and typed parameters only."
                ),
                category="dev",
                capabilities=Capability.DEV_EXEC,
                parameters=[
                    ToolParameter(
                        "recipe",
                        "string",
                        "Recipe name from dev.list.",
                    ),
                    ToolParameter(
                        "parameters",
                        "object",
                        "Typed recipe parameters.",
                        required=False,
                        default=None,
                    ),
                ],
                handler=self.run_recipe,
            )
        )

    def list_recipes(self) -> str:

        return json.dumps(
            {
                "recipes": self.runner.list_recipes(),
                "recipes_changed": self._recipes_changed(),
            },
            ensure_ascii=False,
            indent=2,
        )

    def run_recipe(
        self,
        recipe: str,
        parameters: dict | None = None,
    ) -> str:

        try:
            result = self.runner.run(
                recipe,
                parameters,
            )
        except DevExecutionError:
            raise

        payload = result.as_dict()
        payload["recipes_changed"] = self._recipes_changed()

        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )

    def _recipes_changed(self) -> bool:

        try:
            data = self.book.path.read_bytes()
        except OSError:
            changed = True
        else:
            changed = hashlib.sha256(data).hexdigest() != self.book.sha256

        if changed and not self._changed_notified:
            self._changed_notified = True
            if self.audit is not None:
                self.audit.record(
                    "dev.recipes.changed",
                    path=str(self.book.path),
                )

        return changed
