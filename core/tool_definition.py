from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from typing import Callable


@dataclass(slots=True)
class ToolParameter:
    """
    Definition of a single tool parameter.
    """

    name: str

    param_type: str

    description: str

    required: bool = True

    default: Any = None


@dataclass(slots=True)
class ToolDefinition:
    """
    Metadata describing a tool exposed to the agent.
    """

    name: str
    
    origin: str

    description: str

    category: str

    handler: Callable[..., Any]

    parameters: list[ToolParameter] = field(
        default_factory=list
    )

    enabled: bool = True

    requires_confirmation: bool = False