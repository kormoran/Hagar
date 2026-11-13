"""Adapter LLM che usa il modello scelto dal broker."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from core.broker import Broker, BrokerError
from core.models import ModelConfig
from core.timeouts import TimeoutPolicy
from llm.base import LLMClient
from llm.factory import create_llm


class BrokerLLMClient(LLMClient):
    """Delega a un client creato per il modello scelto dal broker.

    Il broker sceglie una volta, alla costruzione del client. La scelta
    non concede capability e non modifica la policy.
    """

    def __init__(
        self,
        broker: Broker,
        config: ModelConfig,
        *,
        profile: str = "coding",
        audit: Any = None,
        llm_factory: Callable[..., LLMClient] | None = None,
        local_only: bool = False,
        timeout_policy: TimeoutPolicy | None = None,
        allow_fallback: bool = True,
    ) -> None:

        self.broker = broker
        self.config = config
        self.profile = profile
        self.audit = audit
        self._factory = llm_factory or create_llm
        self.local_only = local_only
        self.timeout_policy = timeout_policy
        self.allow_fallback = allow_fallback
        self.fallback_reason: str | None = None
        self.selection: Any = None

        try:
            selection = self._select(profile)
        except BrokerError as exc:

            self.fallback_reason = str(exc)
            model_config = config
            self._record(
                "broker.fallback",
                profile=profile,
                provider=config.provider,
                model=config.name,
                error=str(exc),
            )

            if not self.allow_fallback:
                raise

        else:

            self.selection = selection
            model_config = replace(
                config,
                provider=selection.entry.provider,
                name=selection.entry.model,
            )
            self._record(
                "broker.decision",
                profile=profile,
                model_id=selection.entry.id,
                provider=selection.entry.provider,
                model=selection.entry.model,
                score=round(selection.score, 4),
            )

        self._client = self._create_client(
            model_config,
            config,
            audit=audit,
        )

        if self.selection is None:
            self._record(
                "broker.fallback_client",
                profile=profile,
                provider=config.provider,
                model=config.name,
                error=self.fallback_reason,
            )

        self._client.native_tools = config.native_tools

    def switch_profile(self, profile: str) -> Any:
        """Cambia profilo e client in modo atomico.

        Se la selezione o la costruzione del nuovo client falliscono,
        il client precedente resta attivo.
        """

        try:
            selection = self._select(profile)
        except BrokerError as exc:

            self._record(
                "broker.switch_failed",
                profile=profile,
                error=str(exc),
            )
            raise

        model_config = replace(
            self.config,
            provider=selection.entry.provider,
            name=selection.entry.model,
        )

        try:
            client = self._factory(
                model_config,
                audit=self.audit,
            )
        except Exception as exc:

            self._record(
                "broker.switch_failed",
                profile=profile,
                provider=selection.entry.provider,
                model=selection.entry.model,
                error=str(exc),
            )
            raise

        client.native_tools = self.native_tools
        client.usage_sink = self.usage_sink

        self._client = client
        self.profile = profile
        self.selection = selection
        self.fallback_reason = None
        self._record(
            "broker.decision",
            profile=profile,
            model_id=selection.entry.id,
            provider=selection.entry.provider,
            model=selection.entry.model,
            score=round(selection.score, 4),
            action="switch",
        )

        return selection

    def _create_client(
        self,
        model_config: ModelConfig,
        fallback_config: ModelConfig,
        *,
        audit: Any,
    ) -> LLMClient:

        try:
            return self._factory(
                model_config,
                audit=audit,
            )
        except Exception as exc:

            if model_config is fallback_config:
                raise

            self.selection = None
            self.fallback_reason = (
                f"selected model client failed: {exc}"
            )
            self._record(
                "broker.fallback",
                profile=self.profile,
                provider=fallback_config.provider,
                model=fallback_config.name,
                error=self.fallback_reason,
            )

            return self._factory(
                fallback_config,
                audit=audit,
            )

    def _record(self, event: str, **fields: Any) -> None:

        if self.audit is None:
            return

        self.audit.record(event, **fields)

    def _select(self, profile: str) -> Any:

        if not self.local_only:
            return self.broker.select(profile)

        task = self.broker.profiles.get(profile)

        if task is None:
            raise BrokerError(
                f"unknown task profile: {profile}"
            )

        return self.broker.select(
            replace(task, privacy="local_only")
        )

    # --------------------------------------------------
    # Identità e proprietà delegate
    # --------------------------------------------------

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def model(self) -> str:
        return self._client.model

    @property
    def supports_native_tools(self) -> bool:
        return self._client.supports_native_tools

    @property
    def timeout(self) -> Any:
        return getattr(
            self._client,
            "timeout",
            self.config.timeout,
        )

    @timeout.setter
    def timeout(self, value: Any) -> None:
        self.config.timeout = value

        if hasattr(self._client, "timeout"):
            self._client.timeout = value

    @property
    def max_tokens(self) -> Any:
        return getattr(
            self._client,
            "max_tokens",
            self.config.max_tokens,
        )

    @max_tokens.setter
    def max_tokens(self, value: Any) -> None:
        self.config.max_tokens = value

        if hasattr(self._client, "max_tokens"):
            self._client.max_tokens = value

    @property
    def native_tools(self) -> bool:
        return self._client.native_tools

    @native_tools.setter
    def native_tools(self, value: bool) -> None:
        self._client.native_tools = value

    @property
    def last_usage(self) -> Any:
        return self._client.last_usage

    @last_usage.setter
    def last_usage(self, value: Any) -> None:
        self._client.last_usage = value

    @property
    def last_reasoning(self) -> str:
        return self._client.last_reasoning

    @last_reasoning.setter
    def last_reasoning(self, value: str) -> None:
        self._client.last_reasoning = value

    @property
    def usage_sink(self) -> Any:
        return self._client.usage_sink

    @usage_sink.setter
    def usage_sink(self, value: Any) -> None:
        self._client.usage_sink = value

    # --------------------------------------------------
    # Backend API delegata
    # --------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        self._ensure_loaded()
        self._apply_timeout(messages)
        return self._client.chat(messages)

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        self._ensure_loaded()
        self._apply_timeout([
            {"role": "user", "content": prompt}
        ])
        return self._client.generate(
            prompt,
            system_prompt=system_prompt,
        )

    def request_tool_call(
        self,
        messages: list[dict[str, str]],
        registry: Any,
    ) -> Any:
        self._ensure_loaded()
        self._apply_timeout(messages)
        return self._client.request_tool_call(
            messages,
            registry,
        )

    def native_step(
        self,
        messages: list[dict[str, Any]],
        registry: Any,
    ) -> Any:
        self._ensure_loaded()
        self._apply_timeout(messages)
        return self._client.native_step(
            messages,
            registry,
        )

    def _ensure_loaded(self) -> None:

        if (
            not getattr(self.broker, "loaded_only", False)
            or self.selection is None
        ):
            return

        refresh = getattr(self.broker, "refresh", None)

        if callable(refresh):
            refresh()

        state = self.broker.loaded_state(self.selection.entry)

        if state is not False:
            return

        previous = self.selection.entry.id
        self.switch_profile(self.profile)
        self._record(
            "broker.loaded_switch",
            previous=previous,
            model_id=self.selection.entry.id,
        )

    @property
    def turn_timeout(self) -> float | None:
        if (
            self.timeout_policy is None
            or self.selection is None
        ):
            return None

        return self.timeout_policy.turn_timeout(
            self.selection.entry,
        )

    def _apply_timeout(
        self,
        messages: list[dict[str, Any]],
    ) -> None:

        if (
            self.timeout_policy is None
            or self.selection is None
        ):
            return

        timeout = self.timeout_policy.request_timeout(
            self.selection.entry,
            messages,
            self.config.max_tokens,
            self.config.timeout,
        )

        if timeout is None:
            return

        self._client.timeout = timeout
        self._record(
            "llm.timeout",
            seconds=round(timeout, 3),
            model_id=self.selection.entry.id,
        )

    def _native_request(
        self,
        messages: list[dict[str, Any]],
        registry: Any,
    ) -> Any:
        return self._client._native_request(
            messages,
            registry,
        )
