from __future__ import annotations

import hashlib
import json
import threading

from typing import Any

from .events import EventSink
from .events import emit
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


class ToolTimeoutError(RuntimeError):
    """Un tool ha superato il timeout configurato."""


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
        event_sink: EventSink | None = None,
        agent_id: str | None = None,
        parent_id: str | None = None,
        default_timeout: float | None = None,
        repeat_limit: int = 3,
        timeout_overrides: dict[str, float] | None = None,
    ) -> None:

        self._tools: dict[
            str,
            ToolDefinition
        ] = {}

        self.evaluator = evaluator
        self.subject = subject
        self.confirmation = confirmation
        self.audit = audit
        self.event_sink = event_sink
        self.agent_id = agent_id
        self.parent_id = parent_id
        self.default_timeout = default_timeout
        self.repeat_limit = int(repeat_limit)
        self.timeout_overrides = {
            str(name): float(value)
            for name, value in (timeout_overrides or {}).items()
        }
        self._repeat_counts: dict[str, int] = {}

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

        if tool.name in self.timeout_overrides:
            tool.timeout = self.timeout_overrides[tool.name]

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

    def begin_turn(self) -> None:
        """Azzera il conteggio delle ripetizioni per un nuovo turno."""

        self._repeat_counts.clear()

    @staticmethod
    def _repeat_key(
        name: str,
        arguments: dict[str, Any],
    ) -> str:

        payload = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(
            f"{name}:{payload}".encode("utf-8")
        ).hexdigest()
        return digest

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

        key = self._repeat_key(name, kwargs)
        count = self._repeat_counts.get(key, 0) + 1
        self._repeat_counts[key] = count

        if self.repeat_limit > 0 and count >= self.repeat_limit:

            self._record(
                "tool.repeat",
                tool=name,
                count=count,
                blocked=True,
            )

            raise RuntimeError(
                f"tool {name} repeated {count} times with the same "
                "arguments in this turn; blocked"
            )

        if self.repeat_limit > 0 and count == 2:

            self._record(
                "tool.repeat",
                tool=name,
                count=count,
                blocked=False,
            )

        timeout = (
            tool.timeout
            if tool.timeout is not None
            else self.default_timeout
        )

        if timeout is not None and float(timeout) > 0:

            return self._execute_with_timeout(
                tool,
                kwargs,
                float(timeout),
            )

        return tool.handler(**kwargs)

    def _execute_with_timeout(
        self,
        tool: ToolDefinition,
        arguments: dict[str, Any],
        timeout: float,
    ) -> Any:

        box: dict[str, Any] = {}
        finished = threading.Event()

        def run() -> None:

            try:
                box["value"] = tool.handler(**arguments)

            except BaseException as exc:  # noqa: BLE001
                box["error"] = exc

            finally:
                finished.set()

        worker = threading.Thread(
            target=run,
            name=f"hagar-tool-{tool.name}",
            daemon=True,
        )
        worker.start()

        if not finished.wait(timeout):

            self._record(
                "tool.timeout",
                tool=tool.name,
                timeout=timeout,
            )

            raise ToolTimeoutError(
                f"tool {tool.name} exceeded timeout of {timeout:g}s"
            )

        if "error" in box:
            raise box["error"]

        return box.get("value")

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

        emit(
            self.event_sink,
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
                            agent_id=self.agent_id,
                            parent_id=self.parent_id,
                        )
                    )
                )

            self._record(
                "permission.confirmation",
                subject=self.subject.name,
                tool=tool.name,
                approved=approved,
            )

            emit(
                self.event_sink,
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

            if self.agent_id:
                fields.setdefault("agent_id", self.agent_id)

            self.audit.record(
                event,
                **fields,
            )
