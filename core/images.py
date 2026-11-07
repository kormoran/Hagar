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


@dataclass(frozen=True)
class ImageInput:
    """Immagine già decodificata e validata."""

    mime_type: str
    data: bytes

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

        return cls(
            mime_type=mime_type,
            data=data,
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
