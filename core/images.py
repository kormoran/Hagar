"""Input immagini per i modelli vision."""

from __future__ import annotations

import base64
import binascii

from dataclasses import dataclass
from typing import Any


ALLOWED_MIME_TYPES = frozenset({
    "image/png",
    "image/jpeg",
    "image/webp",
})

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class ImageInputError(ValueError):
    pass


def detect_mime_type(data: bytes) -> str | None:

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if (
        len(data) >= 12
        and data[:4] == b"RIFF"
        and data[8:12] == b"WEBP"
    ):
        return "image/webp"

    return None


@dataclass(frozen=True)
class ImageInput:
    """Immagine già decodificata e validata."""

    mime_type: str
    data: bytes

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        mime_type: str | None = None,
    ) -> "ImageInput":

        if not isinstance(data, (bytes, bytearray)):

            raise ImageInputError(
                "image data must be bytes"
            )

        data = bytes(data)

        if not data:

            raise ImageInputError("image is empty")

        if len(data) > MAX_IMAGE_BYTES:

            raise ImageInputError(
                "image is too large (max 10 MB)"
            )

        detected = detect_mime_type(data)

        if detected is None:

            raise ImageInputError(
                "unsupported or invalid image data"
            )

        if (
            mime_type is not None
            and mime_type.lower() != detected
        ):

            raise ImageInputError(
                "image MIME type does not match its content"
            )

        return cls(
            mime_type=detected,
            data=data,
        )

    @classmethod
    def from_data_url(
        cls,
        value: Any,
    ) -> "ImageInput":

        if not isinstance(value, str):

            raise ImageInputError(
                "image must be a data URL string"
            )

        if not value.startswith("data:") or ";base64," not in value:

            raise ImageInputError(
                "image must be a base64 data URL"
            )

        header, encoded = value.split(",", 1)
        mime_type = header[
            len("data:"):header.index(";base64")
        ].lower()

        if mime_type not in ALLOWED_MIME_TYPES:

            raise ImageInputError(
                f"unsupported image type: {mime_type}"
            )

        try:
            data = base64.b64decode(
                encoded,
                validate=True,
            )

        except (ValueError, binascii.Error) as exc:

            raise ImageInputError(
                "image is not valid base64"
            ) from exc

        if not data:

            raise ImageInputError("image is empty")

        if len(data) > MAX_IMAGE_BYTES:

            raise ImageInputError(
                "image is too large (max 10 MB)"
            )

        return cls.from_bytes(
            data,
            mime_type=mime_type,
        )

    @property
    def base64_data(self) -> str:

        return base64.b64encode(self.data).decode("ascii")

    @property
    def data_url(self) -> str:

        return (
            f"data:{self.mime_type};base64,"
            f"{self.base64_data}"
        )

    def as_message_part(self) -> dict[str, str]:

        return {
            "type": "image",
            "mime_type": self.mime_type,
            "data": self.base64_data,
        }
