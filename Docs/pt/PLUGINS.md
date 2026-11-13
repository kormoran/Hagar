# Plugins do Hagar

O Hagar descobre dois grupos de plugins através dos entry point Python:

| Grupo | Conteúdo |
|---|---|
| `hagar.tools` | tool adicionais |
| `hagar.llm` | providers LLM adicionais |

Os plugins built-in (`local_tools/plugins.py` e `llm/plugins.py`) usam o
mesmo contrato e são registados antes dos externos.

> **Segurança:** os plugins Python correm no mesmo processo do Hagar e
> são considerados *trusted*. Podem usar a API do processo e não estão
> isolados da sandbox. Para extensões não fidedignas, usar MCP ou um
> processo separado. Policy, sandbox, confirmações e audit permanecem no
> host: um plugin não pode conceder permissões.

## Plugin de tool

Um plugin de tool é um objeto `ToolPlugin` com uma função
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

Entry point no pacote do plugin:

```toml
[project.entry-points."hagar.tools"]
acme = "acme_hagar:PLUGIN"
```

O campo `origin` deve identificar o plugin, por exemplo `plugin.acme`,
para tornar o audit legível. As capability são obrigatórias quando o
registry tem policy ativas.

`PluginContext` expõe, se forem necessários:

```text
config
audit
filesystem
memory
project_store
project_state
```

Um plugin com falha é ignorado, registado como `plugin.error` e não
impede o arranque dos outros. Se registar alguns tool e depois falhar,
esses tool permanecem registados: o plugin deve registar tudo ou nada.

## Provider LLM plugin

Um provider é um objeto `LLMProvider` com uma factory:

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

Depois, em `hagar.yaml`:

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

O provider não deve conceder permissões: recebe apenas a configuração e o
audit. `native_tools` é aplicado pelo host com `model.native_tools`.

## Descoberta e prioridade

- Os built-in estão sempre disponíveis.
- Um plugin externo não pode substituir um nome built-in: o duplicado
  é recusado e registado.
- Os providers externos aparecem em `available_providers()`.
- Os erros de carregamento são isolados; o audit regista
  `plugin.loaded` para os plugins externos e `plugin.error` para as
  falhas.

## Testes

O contrato é coberto por `tests/test_plugins.py`:

- registo de um plugin de tool;
- descoberta a partir do entry point;
- isolamento de um plugin com falha;
- carregamento de um provider LLM;
- recusa de um nome built-in duplicado.

Para testar um plugin sem o instalar, pode chamar-se diretamente:

```python
load_tool_plugins([PLUGIN], registry, context)
load_llm_providers([PROVIDER])
```
