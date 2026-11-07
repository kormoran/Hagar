# Plugin di Hagar

Hagar scopre due gruppi di plugin tramite gli entry point Python:

| Gruppo | Contenuto |
|---|---|
| `hagar.tools` | tool aggiuntivi |
| `hagar.llm` | provider LLM aggiuntivi |

I plugin built-in (`local_tools/plugins.py` e `llm/plugins.py`) usano lo
stesso contratto e vengono registrati prima di quelli esterni.

> **Sicurezza:** i plugin Python girano nello stesso processo di Hagar e
> sono considerati *trusted*. Possono usare l'API del processo e non sono
> isolati dal sandbox. Per estensioni non fidate usare MCP o un processo
> separato. Policy, sandbox, conferme e audit restano nell'host: un plugin
> non può concedere permessi.

## Tool plugin

Un plugin di tool è un oggetto `ToolPlugin` con una funzione
`register(registry, context)`:

```python
from core.plugins import ToolPlugin
from core.tool_definition import ToolDefinition
from core.permissions import Capability


def register(registry, context):
    registry.register(
        ToolDefinition(
            name="acme.echo",
            description="Echo the input.",
            category="acme",
            capabilities=Capability.COMPUTE,
            origin="plugin.acme",
            parameters=[],
            handler=lambda text="": text,
        )
    )


PLUGIN = ToolPlugin(
    name="acme",
    version="1.0",
    register=register,
)
```

Entry point nel pacchetto del plugin:

```toml
[project.entry-points."hagar.tools"]
acme = "acme_hagar:PLUGIN"
```

Il campo `origin` dovrebbe identificare il plugin, ad esempio
`plugin.acme`, per rendere leggibile l’audit. Le capability sono
obbligatorie quando il registry ha policy attive.

`PluginContext` espone, se servono:

```text
config
audit
filesystem
memory
project_store
project_state
```

Un plugin guasto viene saltato, registrato come `plugin.error` e non
impedisce l’avvio degli altri. Se registra alcuni tool e poi fallisce,
quei tool restano registrati: il plugin dovrebbe registrare tutto o
niente.

## Provider LLM plugin

Un provider è un oggetto `LLMProvider` con una factory:

```python
from core.plugins import LLMProvider


def factory(config, audit):
    return MyClient(
        model=config.name,
        host=config.host,
        timeout=config.timeout,
        audit=audit,
    )


PROVIDER = LLMProvider(
    name="acme",
    version="1.0",
    factory=factory,
    capabilities=frozenset({"usage", "vision"}),
)
```

Entry point:

```toml
[project.entry-points."hagar.llm"]
acme = "acme_hagar:PROVIDER"
```

Poi in `hagar.yaml`:

```yaml
model:
  provider: acme
  name: acme-vision
```

Capability consigliate:

```text
usage
native_tools
vision
reasoning
streaming
```

Il provider non deve concedere permessi: riceve solo la configurazione e
l’audit. `native_tools` viene applicato dall’host con
`model.native_tools`.

## Scoperta e priorità

- I built-in sono sempre disponibili.
- Un plugin esterno non può sostituire un nome built-in: il duplicato
  viene rifiutato e registrato.
- I provider esterni compaiono in `available_providers()`.
- Gli errori di caricamento sono isolati; l’audit registra
  `plugin.loaded` per i plugin esterni e `plugin.error` per i fallimenti.

## Test

Il contratto è coperto da `tests/test_plugins.py`:

- registrazione di un tool plugin;
- scoperta da entry point;
- isolamento di un plugin guasto;
- caricamento di un provider LLM;
- rifiuto di un nome built-in duplicato.

Per testare un plugin senza installarlo, si può chiamare direttamente:

```python
load_tool_plugins([PLUGIN], registry, context)
load_llm_providers([PROVIDER])
```
