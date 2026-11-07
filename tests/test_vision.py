"""Test del tool vision.open e del canale immagini dell'Agent."""

from __future__ import annotations

import base64

from core.agent import Agent
from core.filesystem import DirectoryPermissions
from core.filesystem import FileSystemSandbox
from core.tool_call import ToolCall
from core.tool_registry import ToolRegistry
from local_tools.vision_tool import VisionToolProvider


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ImageLLM:

    def __init__(self):
        self.messages = None
        self.calls = 0

    def request_tool_call(self, messages, registry):
        self.calls += 1

        if self.calls == 1:
            return ToolCall(
                tool="vision.open",
                arguments={"path": "/home/ai/workspace/pixel.png"},
            )

        self.messages = messages
        return ToolCall(tool=None, arguments={})

    def chat(self, messages):
        return "vista"


def make_sandbox(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "pixel.png").write_bytes(PNG_BYTES)
    return root, FileSystemSandbox(
        roots={
            root: DirectoryPermissions(
                read=True,
                write=False,
                create=False,
            )
        },
        current_directory=root,
        aliases={"workspace": root},
    )


def test_vision_open_returns_attachment(tmp_path):
    _, filesystem = make_sandbox(tmp_path)
    provider = VisionToolProvider(filesystem)

    result = provider.open_image(
        "/home/ai/workspace/pixel.png"
    )

    assert result.success is True
    assert len(result.images) == 1
    assert result.images[0].mime_type == "image/png"
    assert "pixel.png" in result.output


def test_agent_attaches_tool_image_to_next_message(tmp_path):
    _, filesystem = make_sandbox(tmp_path)
    registry = ToolRegistry()
    VisionToolProvider(filesystem).register_tools(registry)
    llm = ImageLLM()
    agent = Agent(
        llm=llm,
        tool_registry=registry,
        vault=None,
        max_tool_calls=2,
    )

    assert agent.ask("cosa contiene?") == "vista"

    image_messages = [
        message
        for message in llm.messages
        if (
            message.get("role") == "user"
            and isinstance(message.get("content"), list)
            and any(
                part.get("type") == "image"
                for part in message["content"]
            )
        )
    ]

    assert image_messages
    assert image_messages[0]["content"][0]["type"] == "text"
    assert image_messages[0]["content"][1]["type"] == "image"
    assert image_messages[0]["content"][1]["mime_type"] == "image/png"
