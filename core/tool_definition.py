from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from typing import Callable


@dataclass(slots=True)
class ToolParameter:
    """
    Definizione di un singolo parametro di un tool.
    """

    name: str

    param_type: str

    description: str

    required: bool = True

    default: Any = None


@dataclass(slots=True)
class ToolDefinition:
    """
    Metadati che descrivono un tool esposto all'agente.

    ``origin`` distingue i tool locali da quelli remoti (es. ``mcp.github``)
    e serve per l'audit log: la Quarta Legge di HAGAR richiede che ogni azione
    sia riconducibile alla sua sorgente.
    """

    name: str

    description: str

    category: str

    handler: Callable[..., Any]

    parameters: list[ToolParameter] = field(
        default_factory=list
    )

    origin: str = "local"

    enabled: bool = True

    requires_confirmation: bool = False
