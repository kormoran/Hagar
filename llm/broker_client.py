"""Adapter LLM che usa il modello scelto dal broker."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from core.broker import Broker, BrokerError
from core.models import ModelConfig
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
    ) -> None:

        self.broker = broker
        self.config = config
        self.profile = profile
        self.audit = audit
        self._factory = llm_factory or create_llm
        self.fallback_reason: str | None = None
        self.selection: Any = None

        try:
            selection = broker.select(profile)
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
        return self._client.chat(messages)

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        return self._client.generate(
            prompt,
            system_prompt=system_prompt,
        )

    def request_tool_call(
        self,
        messages: list[dict[str, str]],
        registry: Any,
    ) -> Any:
        return self._client.request_tool_call(
            messages,
            registry,
        )

    def native_step(
        self,
        messages: list[dict[str, Any]],
        registry: Any,
    ) -> Any:
        return self._client.native_step(
            messages,
            registry,
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
