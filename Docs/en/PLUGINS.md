# Hagar plugins

Hagar discovers two groups of plugins through the Python entry points:

| Group | Content |
|---|---|
| `hagar.tools` | additional tools |
| `hagar.llm` | additional LLM providers |

The built-in plugins (`local_tools/plugins.py` and `llm/plugins.py`) use the
same contract and are registered before the external ones.

> **Security:** Python plugins run in the same process as Hagar and
> are considered *trusted*. They can use the process API and are not
> isolated from the sandbox. For untrusted extensions use MCP or a
> separate process. Policy, sandbox, confirmations and audit remain in the host: a plugin
> cannot grant permissions.

## Tool plugins

A tool plugin is a `ToolPlugin` object with a
`register(registry, context)` function:

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

Entry point in the plugin package:

```toml
[project.entry-points."hagar.tools"]
acme = "acme_hagar:PLUGIN"
```

The `origin` field should identify the plugin, for example
`plugin.acme`, to make the audit readable. The capabilities are
mandatory when the registry has active policies.

`PluginContext` exposes, if needed:

```text
config
audit
filesystem
memory
project_store
project_state
```

A broken plugin is skipped, recorded as `plugin.error` and does not
prevent the others from starting. If it registers some tools and then fails,
those tools remain registered: the plugin should register everything or
nothing.

## LLM provider plugins

A provider is an `LLMProvider` object with a factory:

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

Then in `hagar.yaml`:

```yaml
model:
  provider: acme
  name: acme-vision
```

Recommended capabilities:

```text
usage
native_tools
vision
reasoning
streaming
```

The provider must not grant permissions: it receives only the configuration and
the audit. `native_tools` is applied by the host with
`model.native_tools`.

## Discovery and priority

- The built-ins are always available.
- An external plugin cannot replace a built-in name: the duplicate
  is refused and recorded.
- The external providers appear in `available_providers()`.
- Loading errors are isolated; the audit records
  `plugin.loaded` for the external plugins and `plugin.error` for the failures.

## Tests

The contract is covered by `tests/test_plugins.py`:

- registration of a tool plugin;
- discovery from an entry point;
- isolation of a broken plugin;
- loading of an LLM provider;
- refusal of a duplicate built-in name.

To test a plugin without installing it, you can call directly:

```python
load_tool_plugins([PLUGIN], registry, context)
load_llm_providers([PROVIDER])
```
