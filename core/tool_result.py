from __future__ import annotations

from dataclasses import dataclass

from core.images import ImageInput


@dataclass(slots=True)
class ToolResult:
    """
    Risultato strutturato di una chiamata tool.

    ``error`` è ``None`` quando la chiamata è riuscita.
    """

    tool_name: str | None

    success: bool

    output: str = ""

    error: str | None = None

    images: tuple[ImageInput, ...] = ()
