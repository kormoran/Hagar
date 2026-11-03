from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolCall:

    tool: str | None

    arguments: dict[str, Any]

    id: str | None = None