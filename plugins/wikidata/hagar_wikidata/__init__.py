"""Plugin Hagar per interrogare Wikidata e leggere Wikipedia.

L'entry point è dichiarato in ``pyproject.toml``::

    [project.entry-points."hagar.tools"]
    wikidata = "hagar_wikidata:PLUGIN"

Il plugin non concede permessi: dichiara ``NETWORK`` e lascia a policy,
conferme e sandbox dell'host la decisione finale.
"""

from __future__ import annotations

from core.plugins import (
    PluginContext,
    ToolPlugin,
)

from .client import WikidataClient
from .tools import WikidataToolProvider


VERSION = "1.0.0"


def register(
    registry,
    context: PluginContext,
) -> None:
    """Registra i tool Wikidata nel registry dell'host.

    La configurazione del plugin è volutamente minima: lingua,
    timeout e user agent si leggono dall'ambiente nel client. Il
    context resta disponibile per future estensioni.
    """

    del context

    WikidataToolProvider(
        WikidataClient()
    ).register_tools(registry)


PLUGIN = ToolPlugin(
    name="wikidata",
    version=VERSION,
    register=register,
)


__all__ = [
    "PLUGIN",
    "VERSION",
    "WikidataClient",
    "WikidataToolProvider",
    "register",
]
