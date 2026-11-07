"""Test degli input immagine e della conversione vision."""

from __future__ import annotations

import pytest

from core.agent import Agent
from core.images import ImageInput
from core.images import ImageInputError
from core.tool_call import ToolCall
from core.tool_registry import ToolRegistry
from llm.openai_compatible import OpenAICompatibleClient


PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ImageLLM:
    def __init__(self):
        self.messages = None

    def request_tool_call(self, messages, registry):
        self.messages = messages
        return ToolCall(tool=None, arguments={})

    def chat(self, messages):
        return "vista"


def test_data_url_is_validated():
    image = ImageInput.from_data_url(PNG_DATA_URL)

    assert image.mime_type == "image/png"
    assert image.data
    assert image.as_message_part()["type"] == "image"


def test_invalid_mime_is_rejected():
    with pytest.raises(ImageInputError, match="unsupported"):
        ImageInput.from_data_url(
            "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="
        )


def test_invalid_base64_is_rejected():
    with pytest.raises(ImageInputError, match="base64"):
        ImageInput.from_data_url(
            "data:image/png;base64,not-base64!"
        )


def test_agent_builds_multimodal_content():
    llm = ImageLLM()
    agent = Agent(llm, ToolRegistry(), vault=None)

    assert agent.ask(
        "cosa vedi?",
        images=[ImageInput.from_data_url(PNG_DATA_URL)],
    ) == "vista"

    content = llm.messages[0]["content"]

    assert content[0] == {"type": "text", "text": "cosa vedi?"}
    assert content[1]["type"] == "image"
    assert content[1]["mime_type"] == "image/png"


def test_openai_converts_image_to_image_url():
    client = OpenAICompatibleClient(
        model="vision-model",
        api_key="sk",
    )

    converted = client._openai_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "guarda"},
                    ImageInput.from_data_url(
                        PNG_DATA_URL
                    ).as_message_part(),
                ],
            }
        ]
    )

    parts = converted[0]["content"]

    assert parts[0] == {"type": "text", "text": "guarda"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_lmstudio_rejects_webp_with_clear_error():
    from llm.lmstudio_client import LMStudioClient

    with pytest.raises(RuntimeError, match="WebP"):

        LMStudioClient._content(
            [
                {
                    "type": "image",
                    "mime_type": "image/webp",
                    "data": "UklGRg==",
                }
            ]
        )
