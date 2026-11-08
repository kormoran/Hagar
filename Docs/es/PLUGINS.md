# Plugin de Hagar

Hagar descubre dos grupos de plugins mediante los entry point de Python:

| Grupo | Contenido |
|---|---|
| `hagar.tools` | tool adicionales |
| `hagar.llm` | proveedores LLM adicionales |

Los plugins built-in (`local_tools/plugins.py` y `llm/plugins.py`) usan el
mismo contrato y se registran antes que los externos.

> **Seguridad:** los plugins Python se ejecutan en el mismo proceso de Hagar y
> se consideran *trusted*. Pueden usar la API del proceso y no están
> aislados de la sandbox. Para extensiones no fiables usar MCP o un proceso
> separado. Policy, sandbox, confirmaciones y auditoría permanecen en el host: un plugin
> no puede conceder permisos.

## Tool plugin

Un plugin de tool es un objeto `ToolPlugin` con una función
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

Entry point en el paquete del plugin:

```toml
[project.entry-points."hagar.tools"]
acme = "acme_hagar:PLUGIN"
```

El campo `origin` debería identificar el plugin, por ejemplo
`plugin.acme`, para hacer legible la auditoría. Las capability son
obligatorias cuando el registry tiene policy activas.

`PluginContext` expone, si hacen falta:

```text
config
audit
filesystem
memory
project_store
project_state
```

Un plugin defectuoso se omite, se registra como `plugin.error` y no
impide el inicio de los demás. Si registra algunos tool y después falla,
esos tool siguen registrados: el plugin debería registrar todo o
nada.

## Proveedor LLM plugin

Un proveedor es un objeto `LLMProvider` con una factory:

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

Luego en `hagar.yaml`:

```yaml
model:
  provider: acme
  name: acme-vision
```

Capability recomendadas:

```text
usage
native_tools
vision
reasoning
streaming
```

El proveedor no debe conceder permisos: recibe solo la configuración y
la auditoría. `native_tools` lo aplica el host con
`model.native_tools`.

## Descubrimiento y prioridad

- Los built-in están siempre disponibles.
- Un plugin externo no puede sustituir un nombre built-in: el duplicado
  se rechaza y se registra.
- Los proveedores externos aparecen en `available_providers()`.
- Los errores de carga están aislados; la auditoría registra
  `plugin.loaded` para los plugins externos y `plugin.error` para los fallos.

## Test

El contrato está cubierto por `tests/test_plugins.py`:

- registro de un tool plugin;
- descubrimiento desde entry point;
- aislamiento de un plugin defectuoso;
- carga de un proveedor LLM;
- rechazo de un nombre built-in duplicado.

Para probar un plugin sin instalarlo, se puede llamar directamente:

```python
load_tool_plugins([PLUGIN], registry, context)
load_llm_providers([PROVIDER])
```
