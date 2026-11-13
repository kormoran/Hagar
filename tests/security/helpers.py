"""Helper comuni per i test di sicurezza L0/L1."""

from __future__ import annotations

import json
import secrets

from pathlib import Path
from typing import Any

import yaml

from core.config import ConfigLoader
from hagar import build_harness
from llm.base import LLMClient


class ScriptedLLM(LLMClient):
    """Modello finto che esegue una sequenza di risposte.

    Non rappresenta un modello reale: simula un modello completamente
    compromesso che esegue esattamente le tool call dello script.
    """

    provider = "scripted"
    supports_native_tools = False

    def __init__(
        self,
        script: list[str],
    ) -> None:

        super().__init__("scripted")
        self.script = list(script)
        self.index = 0
        self.transcript: list[str] = []

    def chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        self.transcript.append(
            json.dumps(
                messages,
                ensure_ascii=False,
                default=str,
            )
        )

        if self.index < len(self.script):

            item = self.script[self.index]
            self.index += 1
            return item

        #
        # Dopo l'ultima istruzione, se il modello deve dare la risposta
        # finale, riecheggia l'ultimo risultato di tool. Serve a rendere
        # visibile un'eventuale fuga del canary nel test.
        #

        for message in reversed(messages):

            content = str(
                message.get("content", "")
            )

            if content.startswith(
                (
                    "Tool result",
                    "Tool execution failed",
                )
            ):
                return content

        return "Fine."


def tool_call(
    name: str,
    **arguments: Any,
) -> str:

    return json.dumps(
        {
            "tool": name,
            "arguments": arguments,
        },
        ensure_ascii=False,
    )


def finish() -> str:

    return json.dumps(
        {
            "tool": None,
            "arguments": {},
        }
    )


def script(
    calls: list[str],
    final: str | None = None,
) -> list[str]:

    values = [*calls, finish()]

    if final is not None:
        values.append(final)

    return values


def make_policy(
    tmp_path: Path,
    default: str = "allow",
) -> Path:

    path = tmp_path / "policy.yaml"
    path.write_text(
        "version: 1\n"
        "subjects:\n"
        "  assistant:\n"
        f"    default: {default}\n",
        encoding="utf-8",
    )

    return path


def make_config(
    tmp_path: Path,
    *,
    policy_default: str = "allow",
    database_read: bool = False,
) -> tuple[Path, Path]:

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)

    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)

    policy = make_policy(
        tmp_path,
        default=policy_default,
    )

    data = {
        "model": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "name": "qwen3:8b",
        },
        "audit": {
            "enabled": True,
            "path": str(tmp_path / "logs" / "audit.jsonl"),
        },
        "policy": {
            "path": str(policy),
            "subject": "assistant",
        },
        "vault": {"path": str(vault)},
        "memory": {"enabled": False},
        "filesystem": {
            "sandbox": [
                {
                    "alias": "workspace",
                    "path": str(workspace),
                    "permissions": "RWX",
                }
            ],
        },
        "permissions": {
            "read": True,
            "write": True,
            "shell": False,
            "network": False,
            "database_read": database_read,
        },
        "hifi": {
            "enabled": False,
            "margin": 0.2,
            "interpretations": 3,
        },
        "tools": {
            "timeout": 120,
            "repeat_limit": 3,
        },
    }

    path = tmp_path / "hagar.yaml"
    path.write_text(
        yaml.safe_dump(data),
        encoding="utf-8",
    )

    return path, workspace


def make_harness(
    tmp_path: Path,
    responses: list[str],
    *,
    policy_default: str = "allow",
    database_read: bool = False,
):

    config_path, workspace = make_config(
        tmp_path,
        policy_default=policy_default,
        database_read=database_read,
    )

    config = ConfigLoader.load(config_path)
    harness = build_harness(config)
    llm = ScriptedLLM(responses)

    harness.llm = llm
    harness.agent.llm = llm

    return harness, llm, workspace


def make_canary(
    tmp_path: Path,
) -> tuple[Path, str]:

    outside = tmp_path / "outside"
    outside.mkdir()
    path = outside / "secret.txt"
    token = secrets.token_hex(16)
    path.write_text(
        "CANARY=" + token,
        encoding="utf-8",
    )

    return path, token


def audit_text(
    harness: Any,
) -> str:

    from core.audit import read_entries

    path = getattr(harness.audit, "path", None)

    if path is None:
        return ""

    return json.dumps(
        read_entries(path),
        ensure_ascii=False,
        default=str,
    )
