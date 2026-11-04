from __future__ import annotations

from typing import Any

from .permissions import (
    ConfirmationProvider,
    ConfirmationRequest,
    Effect,
    PermissionDenied,
    PermissionEvaluator,
    RequestScope,
    Resource,
    Subject,
    capability_names,
)
from .tool_definition import ToolDefinition


class ToolRegistry:
    """
    Registry of all tools available to the agent.

    Responsibilities:
        - register tool definitions
        - list available tools
        - execute tools
        - enable/disable tools
        - provide metadata to the LLM

    Quando è configurato un ``PermissionEvaluator``, ogni esecuzione
    passa da un controllo di policy. Senza evaluator il registry è in
    modalità non confinata, usata solo dai test e dal codice legacy: il
    harness ne configura sempre uno.
    """

    def __init__(
        self,
        evaluator: PermissionEvaluator | None = None,
        subject: Subject | None = None,
        confirmation: ConfirmationProvider | None = None,
        audit: Any = None,
    ) -> None:

        self._tools: dict[
            str,
            ToolDefinition
        ] = {}

        self.evaluator = evaluator
        self.subject = subject
        self.confirmation = confirmation
        self.audit = audit

    # ==================================================
    # Registration
    # ==================================================

    def register(
        self,
        tool: ToolDefinition,
    ) -> None:

        if tool.name in self._tools:

            raise RuntimeError(
                f"tool already registered: "
                f"{tool.name}"
            )

        #
        # Con le policy attive un tool senza capability sarebbe
        # automaticamente libero: lo rifiutiamo alla registrazione.
        #

        if (
            self.evaluator is not None
            and not tool.capabilities
        ):

            raise ValueError(
                f"tool {tool.name} must declare "
                f"capabilities when permissions are enabled"
            )

        self._tools[tool.name] = tool

    def unregister(
        self,
        name: str,
    ) -> None:

        self._tools.pop(
            name,
            None,
        )

    # ==================================================
    # Lookup
    # ==================================================

    def exists(
        self,
        name: str,
    ) -> bool:

        return name in self._tools

    def get(
        self,
        name: str,
    ) -> ToolDefinition:

        tool = self._tools.get(name)

        if tool is None:

            raise RuntimeError(
                f"unknown tool: {name}"
            )

        return tool

    def tool_names(
        self,
    ) -> list[str]:

        return sorted(
            self._tools.keys()
        )

    # ==================================================
    # Enable / Disable
    # ==================================================

    def enable(
        self,
        name: str,
    ) -> None:

        self.get(name).enabled = True

    def disable(
        self,
        name: str,
    ) -> None:

        self.get(name).enabled = False

    def is_enabled(
        self,
        name: str,
    ) -> bool:

        return self.get(name).enabled

    # ==================================================
    # Metadata
    # ==================================================

    def list_definitions(
        self,
    ) -> list[ToolDefinition]:

        return [
            tool
            for tool in self._tools.values()
            if tool.enabled
        ]

    def list_tools(
        self,
    ) -> list[dict[str, Any]]:

        result = []

        for tool in self._tools.values():

            if not tool.enabled:
                continue

            result.append(
                {
                    "name": tool.name,
                    "description": (
                        tool.description
                    ),
                    "category": (
                        tool.category
                    ),
                    "requires_confirmation": (
                        tool.requires_confirmation
                    ),
                }
            )

        return result

    def tools_by_category(
        self,
        category: str,
    ) -> list[ToolDefinition]:

        return [
            tool
            for tool in self._tools.values()
            if (
                tool.category == category
                and tool.enabled
            )
        ]

    # ==================================================
    # Execution
    # ==================================================

    def execute(
        self,
        name: str,
        **kwargs,
    ) -> Any:

        tool = self.get(name)

        if not tool.enabled:

            raise RuntimeError(
                f"tool disabled: {name}"
            )

        self._authorize(tool, kwargs)

        return tool.handler(
            **kwargs
        )

    # ==================================================
    # Permissions
    # ==================================================

    def _authorize(
        self,
        tool: ToolDefinition,
        arguments: dict[str, Any],
    ) -> None:

        if self.evaluator is None:
            return

        if self.subject is None:

            raise PermissionDenied(
                "No subject configured for permission evaluation"
            )

        resource = Resource.from_tool(tool)

        scope = RequestScope.from_call(
            tool.name,
            arguments,
        )

        if (
            scope.namespace is None
            and tool.policy_namespace
        ):

            scope = RequestScope(
                tool=scope.tool,
                path=scope.path,
                namespace=tool.policy_namespace,
            )

        decision = self.evaluator.evaluate(
            self.subject,
            resource,
            scope,
        )

        effect = decision.effect
        reason = decision.reason

        #
        # Il flag sul tool è un pavimento di ASK: non può mai
        # trasformare un DENY in esecuzione.
        #

        if (
            tool.requires_confirmation
            and effect < Effect.ASK
        ):

            effect = Effect.ASK
            reason = reason or "requires confirmation"

        #
        # Preflight: può alzare un ALLOW ad ASK, ma non può mai
        # trasformare un DENY in esecuzione. Se il preflight fallisce,
        # si nega (fail closed).
        #

        if effect is not Effect.DENY and tool.preflight is not None:

            try:

                preflight_reason = tool.preflight(
                    dict(arguments)
                )

            except Exception as ex:

                effect = Effect.DENY
                reason = f"preflight failed: {ex}"

            else:

                if preflight_reason:

                    if effect is Effect.ALLOW:
                        effect = Effect.ASK

                    reason = (
                        preflight_reason
                        if not reason
                        else f"{reason}; {preflight_reason}"
                    )

        self._record(
            "permission.decision",
            subject=self.subject.name,
            tool=tool.name,
            capabilities=capability_names(
                resource.capabilities
            ),
            path=scope.path,
            namespace=scope.namespace,
            effect=effect.name,
            reason=reason,
            rule=(
                decision.rule.reason
                if decision.rule is not None
                else None
            ),
        )

        if effect is Effect.DENY:

            raise PermissionDenied(
                f"Permission denied for "
                f"{tool.name}: {reason}",
                decision,
            )

        if effect is Effect.ASK:

            approved = False

            if self.confirmation is not None:

                approved = bool(
                    self.confirmation.confirm(
                        ConfirmationRequest(
                            subject=self.subject.name,
                            tool=tool.name,
                            capabilities=(
                                resource.capabilities
                            ),
                            arguments=dict(arguments),
                            reason=reason,
                        )
                    )
                )

            self._record(
                "permission.confirmation",
                subject=self.subject.name,
                tool=tool.name,
                approved=approved,
            )

            if not approved:

                raise PermissionDenied(
                    f"Permission denied by user "
                    f"for {tool.name}",
                    decision,
                )

    def _record(
        self,
        event: str,
        **fields: Any,
    ) -> None:

        if self.audit is not None:

            self.audit.record(
                event,
                **fields,
            )
