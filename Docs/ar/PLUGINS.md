# إضافات Hagar

يكتشف Hagar مجموعتين من الإضافات عبر نقاط الدخول (entry point) في Python:

| المجموعة | المحتوى |
|---|---|
| `hagar.tools` | أدوات إضافية |
| `hagar.llm` | مزوّدو LLM إضافيون |

تستخدم الإضافات المدمجة (`local_tools/plugins.py` و`llm/plugins.py`)
العقد نفسه وتُسجَّل قبل الإضافات الخارجية.

> **الأمان:** إضافات Python تعمل في العملية نفسها التي يعمل فيها Hagar و
> تُعدّ *موثوقة* (trusted). ويمكنها استخدام واجهة العملية وهي غير
> معزولة عن صندوق الرمل. وللإضافات غير الموثوقة استخدم MCP أو عملية
> منفصلة. وتبقى السياسة وصندوق الرمل والتأكيدات والتدقيق في المضيف: فلا يمكن لإضافة
> منح أذونات.

## إضافة أداة

إضافة الأداة كائن `ToolPlugin` له دالة
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

نقطة الدخول في حزمة الإضافة:

```toml
[project.entry-points."hagar.tools"]
acme = "acme_hagar:PLUGIN"
```

ويُفضَّل أن يعرّف الحقل `origin` الإضافة، مثل
`plugin.acme`، لجعل التدقيق مقروءًا. والقدرات
إلزامية عندما يكون للسجل سياسات نشطة.

ويعرض `PluginContext`، عند الحاجة:

```text
config
audit
filesystem
memory
project_store
project_state
```

تُتخطى الإضافة المعطوبة، وتُسجَّل كـ `plugin.error`، ولا
تمنع إقلاع الأخريات. وإذا سجّلت بعض الأدوات ثم فشلت،
تبقى تلك الأدوات مسجَّلة: لذا يُفضَّل أن تسجّل الإضافة كل شيء أو
لا شيء.

## إضافة مزوّد LLM

المزوّد كائن `LLMProvider` له مصنع:

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

نقطة الدخول:

```toml
[project.entry-points."hagar.llm"]
acme = "acme_hagar:PROVIDER"
```

ثم في `hagar.yaml`:

```yaml
model:
  provider: acme
  name: acme-vision
```

القدرات الموصى بها:

```text
usage
native_tools
vision
reasoning
streaming
```

يجب ألا يمنح المزوّد أذونات: فهو يتلقى الإعدادات و
التدقيق فقط. ويُطبَّق `native_tools` من المضيف بـ
`model.native_tools`.

## الاكتشاف والأولوية

- الإضافات المدمجة متاحة دائمًا.
- لا يمكن لإضافة خارجية أن تحل محل اسم مدمج: فالاسم المكرر
  يُرفض ويُسجَّل.
- تظهر المزوّدون الخارجيون في `available_providers()`.
- أخطاء التحميل معزولة؛ ويسجّل التدقيق
  `plugin.loaded` للإضافات الخارجية و`plugin.error` للإخفاقات.

## الاختبارات

العقد مغطى بـ `tests/test_plugins.py`:

- تسجيل إضافة أداة؛
- الاكتشاف من entry point؛
- عزل إضافة معطوبة؛
- تحميل مزوّد LLM؛
- رفض اسم مدمج مكرر.

ولاختبار إضافة دون تثبيتها، يمكن الاستدعاء مباشرةً:

```python
load_tool_plugins([PLUGIN], registry, context)
load_llm_providers([PROVIDER])
```
