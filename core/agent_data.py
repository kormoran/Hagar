"""Artifact store, mailbox e tool dati per i subagenti.

Gli artifact sono file temporanei gestiti da Hagar, fuori dal Vault.
La mailbox contiene solo metadati e riferimenti; il contenuto grande
resta nello store.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import uuid

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.permissions import Capability
from core.tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from core.tool_registry import ToolRegistry


MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ARTIFACTS = 200
MAX_READ_BYTES = 256 * 1024
MAX_MESSAGE_BYTES = 64 * 1024
MAX_MESSAGES = 100

ALLOWED_KINDS = frozenset({
    "text",
    "json",
    "binary",
    "file",
    "graph",
    "table",
})


class AgentDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    mime_type: str
    size: int
    sha256: str
    owner: str
    created_at: float

    def as_dict(self) -> dict[str, Any]:

        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "mime_type": self.mime_type,
            "size": self.size,
            "sha256": self.sha256,
            "owner": self.owner,
            "created_at": self.created_at,
        }


class ArtifactStore:
    """Store temporaneo, thread-safe, con letture bounded."""

    def __init__(self) -> None:

        self.root = Path(
            tempfile.mkdtemp(prefix="hagar-artifacts-")
        )
        self._lock = threading.Lock()
        self._items: dict[str, ArtifactRef] = {}
        self._paths: dict[str, Path] = {}
        self._reads: dict[str, int] = {}
        self._saved: set[str] = set()
        self._total = 0

    def _put_bytes(
        self,
        data: bytes,
        *,
        kind: str,
        mime_type: str,
        owner: str,
    ) -> ArtifactRef:

        if kind not in ALLOWED_KINDS:

            raise AgentDataError(
                f"unsupported artifact kind: {kind}"
            )

        if len(data) > MAX_ARTIFACT_BYTES:

            raise AgentDataError(
                "artifact exceeds the per-artifact limit"
            )

        with self._lock:

            if len(self._items) >= MAX_ARTIFACTS:

                raise AgentDataError(
                    "too many artifacts"
                )

            if self._total + len(data) > MAX_TOTAL_BYTES:

                raise AgentDataError(
                    "artifact storage quota exceeded"
                )

            artifact_id = (
                "art-" + uuid.uuid4().hex[:16]
            )
            path = self.root / f"{artifact_id}.bin"
            path.write_bytes(data)

            ref = ArtifactRef(
                artifact_id=artifact_id,
                kind=kind,
                mime_type=mime_type,
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                owner=owner,
                created_at=time.time(),
            )
            self._items[artifact_id] = ref
            self._paths[artifact_id] = path
            self._reads[artifact_id] = 0
            self._total += len(data)

            return ref

    def put_text(
        self,
        text: str,
        *,
        kind: str = "text",
        mime_type: str = "text/plain; charset=utf-8",
        owner: str,
    ) -> ArtifactRef:

        if len(text.encode("utf-8")) > MAX_ARTIFACT_BYTES:

            raise AgentDataError(
                "artifact exceeds the per-artifact limit"
            )

        return self._put_bytes(
            text.encode("utf-8"),
            kind=kind,
            mime_type=mime_type,
            owner=owner,
        )

    def put_file(
        self,
        path: Path,
        *,
        kind: str = "file",
        mime_type: str = "application/octet-stream",
        owner: str,
    ) -> ArtifactRef:

        data = path.read_bytes()

        return self._put_bytes(
            data,
            kind=kind,
            mime_type=mime_type,
            owner=owner,
        )

    def get(self, artifact_id: str) -> ArtifactRef:

        with self._lock:
            ref = self._items.get(artifact_id)

        if ref is None:
            raise AgentDataError("artifact not found")

        return ref

    def list(self) -> list[ArtifactRef]:

        with self._lock:
            return list(self._items.values())

    def read(
        self,
        artifact_id: str,
        offset: int = 0,
        length: int = MAX_READ_BYTES,
    ) -> dict[str, Any]:
        ref = self.get(artifact_id)
        offset = max(0, int(offset))
        length = max(1, min(int(length), MAX_READ_BYTES))

        with self._lock:
            path = self._paths[artifact_id]

        data = path.read_bytes()
        chunk = data[offset:offset + length]

        with self._lock:
            self._reads[artifact_id] = (
                self._reads.get(artifact_id, 0) + 1
            )

        result: dict[str, Any] = {
            "artifact_id": artifact_id,
            "kind": ref.kind,
            "mime_type": ref.mime_type,
            "size": ref.size,
            "sha256": ref.sha256,
            "offset": offset,
            "length": len(chunk),
            "truncated": offset + len(chunk) < ref.size,
        }

        if ref.kind in {"text", "json"}:

            result["encoding"] = "utf-8"
            result["text"] = chunk.decode(
                "utf-8",
                errors="replace",
            )

        else:

            import base64

            result["encoding"] = "base64"
            result["data_b64"] = base64.b64encode(
                chunk
            ).decode("ascii")

        return result

    def save_to(
        self,
        artifact_id: str,
        filesystem,
        path: str,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Copia l'artifact completo nel sandbox, senza passare dal contesto."""

        ref = self.get(artifact_id)

        with self._lock:
            source = self._paths[artifact_id]

        data = source.read_bytes()
        target = filesystem.resolve_path(path)
        existed = target.exists()
        filesystem.write_bytes(
            path,
            data,
            overwrite=overwrite,
        )

        with self._lock:
            self._saved.add(artifact_id)

        return {
            "artifact_id": artifact_id,
            "path": filesystem.virtual_path(target),
            "size": ref.size,
            "sha256": ref.sha256,
            "overwritten": existed and overwrite,
        }

    def reset(self) -> None:
        """Svuota lo store mantenendo la directory e l'oggetto."""

        with self._lock:

            for path in self._paths.values():
                path.unlink(missing_ok=True)

            self._items.clear()
            self._paths.clear()
            self._reads.clear()
            self._saved.clear()
            self._total = 0

    def snapshot(self) -> list[dict[str, Any]]:
        """Metadati e stato di consumo, senza contenuto."""

        with self._lock:

            return [
                {
                    **ref.as_dict(),
                    "read_count": self._reads.get(
                        artifact_id,
                        0,
                    ),
                    "saved": artifact_id in self._saved,
                }
                for artifact_id, ref in self._items.items()
            ]

    def cleanup(self) -> None:

        with self._lock:
            self._items.clear()
            self._paths.clear()
            self._total = 0

        import shutil

        shutil.rmtree(self.root, ignore_errors=True)


@dataclass(frozen=True)
class Message:
    message_id: str
    sender: str
    recipient: str
    text: str
    artifacts: tuple[str, ...]
    created_at: float
    acked: bool = False

    def as_dict(self) -> dict[str, Any]:

        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "text": self.text,
            "artifacts": list(self.artifacts),
            "created_at": self.created_at,
            "acked": self.acked,
        }


class Mailbox:
    """Mailbox interna, in memoria, con messaggi per destinatario."""

    def __init__(self) -> None:

        self._lock = threading.Lock()
        self._messages: dict[str, list[Message]] = {}

    def send(
        self,
        *,
        sender: str,
        recipient: str,
        text: str,
        artifacts: list[str] | tuple[str, ...] = (),
    ) -> Message:

        if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:

            raise AgentDataError(
                "message exceeds the text limit"
            )

        with self._lock:

            messages = self._messages.setdefault(
                recipient,
                [],
            )

            if len(messages) >= MAX_MESSAGES:

                raise AgentDataError(
                    "recipient mailbox is full"
                )

            message = Message(
                message_id="msg-" + uuid.uuid4().hex[:12],
                sender=sender,
                recipient=recipient,
                text=text,
                artifacts=tuple(artifacts),
                created_at=time.time(),
            )
            messages.append(message)
            return message

    def inbox(
        self,
        recipient: str,
        cursor: int = 0,
        limit: int = 50,
    ) -> list[Message]:

        with self._lock:
            messages = list(
                self._messages.get(recipient, [])
            )

        cursor = max(0, int(cursor))
        limit = max(1, min(int(limit), 100))
        return messages[cursor:cursor + limit]

    def get(
        self,
        recipient: str,
        message_id: str,
    ) -> Message:

        with self._lock:
            for message in self._messages.get(
                recipient,
                [],
            ):
                if message.message_id == message_id:
                    return message

        raise AgentDataError("message not found")

    def ack(
        self,
        recipient: str,
        message_id: str,
    ) -> bool:
        with self._lock:
            messages = self._messages.get(recipient, [])

            for index, message in enumerate(messages):

                if message.message_id != message_id:
                    continue

                messages[index] = Message(
                    message_id=message.message_id,
                    sender=message.sender,
                    recipient=message.recipient,
                    text=message.text,
                    artifacts=message.artifacts,
                    created_at=message.created_at,
                    acked=True,
                )
                return True

        return False

    def clear(self) -> None:

        with self._lock:
            self._messages.clear()


def _json(value: Any) -> str:

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )


def register_parent_data_tools(
    registry: ToolRegistry,
    store: ArtifactStore,
    mailbox: Mailbox,
    parent_id: str,
    filesystem=None,
) -> None:
    """Tool visibili al padre per leggere artifact e mailbox."""

    registry.register(
        ToolDefinition(
            name="artifact.read",
            description=(
                "Read a bounded chunk of an artifact produced by a "
                "subagent."
            ),
            category="artifact",
            capabilities=Capability.AGENT_DATA,
            parameters=[
                ToolParameter(
                    name="artifact_id",
                    param_type="string",
                    description="Artifact id.",
                ),
                ToolParameter(
                    name="offset",
                    param_type="integer",
                    description="Byte offset.",
                    required=False,
                    default=0,
                ),
                ToolParameter(
                    name="length",
                    param_type="integer",
                    description="Maximum bytes.",
                    required=False,
                    default=MAX_READ_BYTES,
                ),
            ],
            handler=lambda artifact_id, offset=0, length=MAX_READ_BYTES: _json(
                store.read(artifact_id, offset, length)
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="artifact.list",
            description="List artifacts in this session.",
            category="artifact",
            capabilities=Capability.AGENT_DATA,
            parameters=[],
            handler=lambda: _json([
                ref.as_dict()
                for ref in store.list()
            ]),
        )
    )

    if filesystem is not None:

        registry.register(
            ToolDefinition(
                name="artifact.save_to",
                description=(
                    "Copy a whole artifact into a writable path in the "
                    "parent sandbox. The content does not pass through "
                    "the model context."
                ),
                category="artifact",
                capabilities=(
                    Capability.AGENT_DATA
                    | Capability.FILESYSTEM_WRITE
                    | Capability.FILESYSTEM_CREATE
                ),
                parameters=[
                    ToolParameter(
                        name="artifact_id",
                        param_type="string",
                        description="Artifact id.",
                    ),
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Destination path in the parent sandbox."
                        ),
                    ),
                    ToolParameter(
                        name="overwrite",
                        param_type="boolean",
                        description="Overwrite an existing file.",
                        required=False,
                        default=False,
                    ),
                ],
                handler=lambda artifact_id, path, overwrite=False: _json(
                    store.save_to(
                        artifact_id,
                        filesystem,
                        path,
                        overwrite=overwrite,
                    )
                ),
            )
        )

    registry.register(
        ToolDefinition(
            name="mailbox.inbox",
            description=(
                "List messages sent to the parent by subagents."
            ),
            category="mailbox",
            capabilities=Capability.AGENT_DATA,
            parameters=[
                ToolParameter(
                    name="cursor",
                    param_type="integer",
                    description="Start index.",
                    required=False,
                    default=0,
                ),
                ToolParameter(
                    name="limit",
                    param_type="integer",
                    description="Maximum messages.",
                    required=False,
                    default=50,
                ),
            ],
            handler=lambda cursor=0, limit=50: _json([
                message.as_dict()
                for message in mailbox.inbox(
                    parent_id,
                    cursor,
                    limit,
                )
            ]),
        )
    )

    registry.register(
        ToolDefinition(
            name="mailbox.read",
            description="Read one mailbox message.",
            category="mailbox",
            capabilities=Capability.AGENT_DATA,
            parameters=[
                ToolParameter(
                    name="message_id",
                    param_type="string",
                    description="Message id.",
                ),
            ],
            handler=lambda message_id: _json(
                mailbox.get(parent_id, message_id).as_dict()
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="mailbox.ack",
            description="Acknowledge a mailbox message.",
            category="mailbox",
            capabilities=Capability.AGENT_DATA,
            parameters=[
                ToolParameter(
                    name="message_id",
                    param_type="string",
                    description="Message id.",
                ),
            ],
            handler=lambda message_id: _json({
                "message_id": message_id,
                "acked": mailbox.ack(
                    parent_id,
                    message_id,
                ),
            }),
        )
    )


def register_child_data_tools(
    registry: ToolRegistry,
    store: ArtifactStore,
    mailbox: Mailbox,
    agent_id: str,
    parent_id: str,
    filesystem,
) -> None:
    """Outbox e mailbox del figlio, con accesso limitato."""

    registry.register(
        ToolDefinition(
            name="artifact.put",
            description=(
                "Put text into the subagent outbox. "
                "Returns an artifact id."
            ),
            category="artifact",
            capabilities=Capability.AGENT_DATA,
            parameters=[
                ToolParameter(
                    name="text",
                    param_type="string",
                    description="Text or JSON payload.",
                ),
                ToolParameter(
                    name="kind",
                    param_type="string",
                    description="text or json.",
                    required=False,
                    default="text",
                ),
                ToolParameter(
                    name="mime_type",
                    param_type="string",
                    description="MIME type.",
                    required=False,
                    default="text/plain; charset=utf-8",
                ),
            ],
            handler=lambda text, kind="text", mime_type="text/plain; charset=utf-8": _json(
                store.put_text(
                    text,
                    kind=kind,
                    mime_type=mime_type,
                    owner=agent_id,
                ).as_dict()
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="artifact.put_file",
            description=(
                "Copy a file from the subagent workspace into the "
                "outbox. Path must be inside the subagent workspace."
            ),
            category="artifact",
            capabilities=Capability.AGENT_DATA,
            parameters=[
                ToolParameter(
                    name="path",
                    param_type="string",
                    description="Sandbox path inside the subagent workspace.",
                ),
                ToolParameter(
                    name="mime_type",
                    param_type="string",
                    description="MIME type.",
                    required=False,
                    default="application/octet-stream",
                ),
            ],
            handler=lambda path, mime_type="application/octet-stream": _json(
                store.put_file(
                    filesystem.resolve_path(path),
                    kind="file",
                    mime_type=mime_type,
                    owner=agent_id,
                ).as_dict()
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="mailbox.send",
            description=(
                "Send a message and optional artifact references to "
                "the parent."
            ),
            category="mailbox",
            capabilities=Capability.AGENT_DATA,
            parameters=[
                ToolParameter(
                    name="text",
                    param_type="string",
                    description="Message text.",
                ),
                ToolParameter(
                    name="artifacts",
                    param_type="array",
                    description="Artifact ids owned by this subagent.",
                    required=False,
                    default=[],
                ),
            ],
            handler=lambda text, artifacts=None: _child_send(
                store,
                mailbox,
                agent_id,
                parent_id,
                text,
                artifacts or [],
            ),
        )
    )


def _child_send(
    store: ArtifactStore,
    mailbox: Mailbox,
    agent_id: str,
    parent_id: str,
    text: str,
    artifacts: list[str],
) -> str:

    for artifact_id in artifacts:

        ref = store.get(str(artifact_id))

        if ref.owner != agent_id:

            raise AgentDataError(
                "artifact is not owned by this subagent"
            )

    message = mailbox.send(
        sender=agent_id,
        recipient=parent_id,
        text=text,
        artifacts=[str(value) for value in artifacts],
    )

    return _json(message.as_dict())
