# Hagar 的插件

Hagar 通过 Python entry point 发现两组插件：

| 组 | 内容 |
|---|---|
| `hagar.tools` | 额外的工具 |
| `hagar.llm` | 额外的 LLM provider |

内置插件（`local_tools/plugins.py` 和 `llm/plugins.py`）使用同一
契约，并在外部插件之前注册。

> **安全：** Python 插件在 Hagar 的同一进程中运行，
> 被视为*受信*。它们可以使用进程 API，并且不受
> sandbox 隔离。对于不受信的扩展，请使用 MCP 或单独的
> 进程。策略、sandbox、确认和审计都留在 host 中：插件
> 不能授予权限。

## 工具插件

工具插件是一个 `ToolPlugin` 对象，带一个
`register(registry, context)` 函数：

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

插件包中的 entry point：

```toml
[project.entry-points."hagar.tools"]
acme = "acme_hagar:PLUGIN"
```

`origin` 字段应标识该插件，例如
`plugin.acme`，以便审计可读。当 registry 启用策略时，
capability 是必填的。

`PluginContext` 在需要时暴露：

```text
config
audit
filesystem
memory
project_store
project_state
```

故障的插件会被跳过、记录为 `plugin.error`，且不会
阻止其他插件启动。如果它注册了一些工具之后失败，
那些工具仍保持注册：插件应当全注册或全不注册。

## LLM provider 插件

provider 是一个 `LLMProvider` 对象，带一个工厂函数：

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

Entry point：

```toml
[project.entry-points."hagar.llm"]
acme = "acme_hagar:PROVIDER"
```

然后在 `hagar.yaml` 中：

```yaml
model:
  provider: acme
  name: acme-vision
```

推荐的 capability：

```text
usage
native_tools
vision
reasoning
streaming
```

provider 不得授予权限：它只接收配置和
审计。`native_tools` 由 host 通过
`model.native_tools` 应用。

## 发现与优先级

- 内置插件始终可用。
- 外部插件不能替换内置名称：重复项
  会被拒绝并记录。
- 外部 provider 出现在 `available_providers()` 中。
- 加载错误被隔离；审计为外部插件记录
  `plugin.loaded`，为失败记录 `plugin.error`。

## 测试

该契约由 `tests/test_plugins.py` 覆盖：

- 注册一个工具插件；
- 从 entry point 发现；
- 故障插件的隔离；
- 加载一个 LLM provider；
- 拒绝重复的内置名称。

要在不安装插件的情况下测试它，可以直接调用：

```python
load_tool_plugins([PLUGIN], registry, context)
load_llm_providers([PROVIDER])
```
