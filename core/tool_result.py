from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolResult:

    tool: str | None

    success: bool
    
    output: str
    
    error: str
    
    