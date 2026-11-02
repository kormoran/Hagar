from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ToolResult:

    tool_name: str

    success: bool

    output: str

    error: str | None = None