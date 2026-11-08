# Плагины Hagar

Hagar обнаруживает две группы плагинов через entry points Python:

| Группа | Содержимое |
|---|---|
| `hagar.tools` | дополнительные инструменты |
| `hagar.llm` | дополнительные провайдеры LLM |

Встроенные плагины (`local_tools/plugins.py` и `llm/plugins.py`) используют
тот же контракт и регистрируются раньше внешних.

> **Безопасность:** плагины Python работают в том же процессе, что и Hagar,
> и считаются *доверенными*. Они могут использовать API процесса и не
> изолированы песочницей. Для недоверенных расширений используйте MCP или
> отдельный процесс. Политика, песочница, подтверждения и аудит остаются
> на стороне хоста: плагин не может выдавать разрешения.

## Плагины-инструменты

Плагин-инструмент — это объект `ToolPlugin` с функцией
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

Entry point в пакете плагина:

```toml
[project.entry-points."hagar.tools"]
acme = "acme_hagar:PLUGIN"
```

Поле `origin` должно идентифицировать плагин, например `plugin.acme`,
чтобы аудит был читаемым. Возможности (capability) обязательны, когда в
реестре активны политики.

`PluginContext` предоставляет, если нужно:

```text
config
audit
filesystem
memory
project_store
project_state
```

Неисправный плагин пропускается, регистрируется как `plugin.error` и не
мешает запуску остальных. Если он регистрирует несколько инструментов, а
затем падает, эти инструменты остаются зарегистрированными: плагин должен
регистрировать всё или ничего.

## Плагины-провайдеры LLM

Провайдер — это объект `LLMProvider` с фабрикой:

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

Затем в `hagar.yaml`:

```yaml
model:
  provider: acme
  name: acme-vision
```

Рекомендуемые возможности:

```text
usage
native_tools
vision
reasoning
streaming
```

Провайдер не должен выдавать разрешения: он получает только конфигурацию и
аудит. `native_tools` применяется хостом через `model.native_tools`.

## Обнаружение и приоритет

- Встроенные плагины доступны всегда.
- Внешний плагин не может заменить встроенное имя: дубликат
  отклоняется и регистрируется.
- Внешние провайдеры появляются в `available_providers()`.
- Ошибки загрузки изолированы; аудит регистрирует `plugin.loaded` для
  внешних плагинов и `plugin.error` для сбоев.

## Тесты

Контракт покрыт в `tests/test_plugins.py`:

- регистрация плагина-инструмента;
- обнаружение через entry point;
- изоляция неисправного плагина;
- загрузка провайдера LLM;
- отклонение дублирующегося встроенного имени.

Чтобы протестировать плагин без установки, можно вызвать напрямую:

```python
load_tool_plugins([PLUGIN], registry, context)
load_llm_providers([PROVIDER])
```
