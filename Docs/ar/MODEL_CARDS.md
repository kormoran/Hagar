# البطاقات التقنية للنماذج

**الحالة:** مُنفَّذ
**الأوامر:** `/models list`، `/models show`، `/models test`، `/models hardware`

## الغرض

تغذّي البطاقات وسيط الـ LLM المستقبلي ببيانات مقيسة، لا
بافتراضات. وتُحفظ بطاقة واحدة لكل مزوّد/نموذج بصيغة JSON في:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

أو في `HAGAR_MODEL_CARDS`، أو في `$XDG_STATE_HOME/hagar/models`.

## الصيغة

```json
{
  "card_version": 1,
  "provider": "lmstudio",
  "model": "gemma-3-27b-it",
  "tested_at": "2026-11-08T20:00:00+00:00",
  "last_tested_at": "2026-11-08T20:00:00+00:00",
  "hardware": {
    "platform": "Windows",
    "cpu": {
      "model": "...",
      "physical_cores": 8,
      "logical_cores": 16,
      "mhz_current": 3600,
      "mhz_max": 4200,
      "ghz_current": 3.6,
      "ghz_max": 4.2
    },
    "memory": {
      "total_bytes": 34359738368,
      "total_gib": 32.0,
      "available_bytes": 17179869184,
      "available_gib": 16.0
    },
    "gpus": [
      {
        "name": "NVIDIA ...",
        "vendor": "NVIDIA",
        "vram_bytes": 8589934592,
        "driver": "...",
        "api": "CUDA"
      }
    ]
  },
  "capabilities": {
    "chat": true,
    "structured_json": true,
    "tool_calling": true,
    "native_tools": true
  },
  "benchmarks": {
    "chat": {
      "attempts": 3,
      "successes": 3,
      "duration_ms": {
        "count": 3,
        "min": 500.0,
        "mean": 700.0,
        "p50": 680.0,
        "p95": 800.0,
        "max": 800.0
      },
      "output_tokens_per_second": 42.5,
      "errors": []
    },
    "structured": {
      "attempts": 3,
      "valid_json": 3,
      "valid_choice": 3,
      "duration_ms": {},
      "errors": []
    },
    "tool_call": {
      "attempts": 2,
      "successes": 2,
      "duration_ms": {},
      "errors": []
    }
  }
}
```

`last_tested_at` موجود دائمًا ويُحدَّث عند كل `/models test`.

## ما تقيسه

- زمن استجابة المحادثة: الحد الأدنى والمتوسط وp50 وp95 والحد الأقصى؛
- رموز الإخراج في الثانية؛
- صحة JSON؛
- اختيار صالح ضمن مجموعة التسميات؛
- استدعاء الأدوات بأداة قياس مرجعية؛
- الجودة الحتمية على مهام نصية؛
- جودة الرؤية على صور تخليقية؛
- العتاد في لحظة الاختبار.

## الجودة حسب المهمة

يشغّل `/models test` أيضًا مجموعة جودة حتمية:

```text
extraction   استخراج حقول في JSON
instruction  الالتزام بتعليمة دقيقة
reasoning    حساب عددي بسيط
coding       قراءة مقتطف Python
summary      تلخيص بنقاط رئيسية
translation  ترجمة IT→EN وEN→IT
```

تُنفَّذ كل حالة مرتين. والدرجة هي متوسط الردود، من 0 إلى 1. وهي ليست
معيار قياس دلاليًا: بل اختبار مضغوط وقابل للتكرار ليعطي الوسيط إشارة
أفضل من الجودة المعلَنة.

تجمع الترجمة بين chrF والحفاظ على المسارات والأوامر والمصطلحات
المطلوبة. والمصطلحات الإلزامية تزن أكثر بكثير من chrF؛ والترجمة التقنية
الخاطئة تُعاقَب صراحةً. ويقيس التلخيص حضور النقاط الرئيسية والالتزام
بالطول.

وتحتوي البطاقة:

```json
{
  "quality": {
    "suite_version": 3,
    "overall": 0.75,
    "tasks": {
      "extraction": {"attempts": 2, "mean": 0.83},
      "instruction": {"attempts": 2, "mean": 1.0},
      "reasoning": {"attempts": 2, "mean": 1.0},
      "coding": {"attempts": 2, "mean": 0.5},
      "summary": {"attempts": 2, "cases": 2, "mean": 0.8},
      "translation": {"attempts": 2, "cases": 2, "mean": 0.7}
    }
  }
}
```

المدوّنة في `benchmarks/corpus/`:

```text
7 نصوص
2 مراجع ترجمة
10 صور تخليقية
manifest.yaml مع SHA-256
```

المجموعة النصية هي `quality_v3`؛ ومجموعة الرؤية هي `vision_v2`.

يحدّد `quality_task` في TaskProfile المهمة المستخدمة؛ وإن غاب، استخدم
الوسيط اسم الملف التعريفي. وإن لم تكن للبطاقة جودة مقيسة، استخدم
الجودة المعلَنة في الكتالوج.

## اكتشاف المزوّد

الأمر:

```text
/models discover lmstudio
/models discover ollama
```

يقرأ بيانات وقت التشغيل ويوحّدها في `ProviderModelInfo`:

```text
provider
model
model_type
context_window
quantization
state
capabilities
hagar_capabilities
```

Mapping:

```text
LM Studio tool_use     → tool_calling
LM Studio type vlm     → vision
Ollama tools           → tool_calling
Ollama thinking        → reasoning
Ollama vision          → vision
Ollama completion      → text_generation
```

لا يُربَط `completion` تلقائيًا بـ `chat`: فالنموذج قد يكمل نصًا دون أن
يكون حواريًا. وتبقى `chat` قدرة تحتاج إلى تحقّق.

## الذاكرة والسياق

يستخدم `memory_bench` محادثات تخليقية:

```text
استرجاع بسيط
distractor
تناقض بين ذكريين
تعليمة مستمرة
سياق طويل
مقدمة زائفة
```

تغذّي النتيجة مهمة الجودة `memory`؛ ويستخدمها الملف التعريفي
`memory_chat` في الوسيط. ولا تُستخدم أبدًا ذكريات المستخدم الحقيقية.

## معايير P1

```text
tool      → عدة أدوات، distractor، فحص الوسائط
JSON      → schema_valid وfield_f1
coding    → unit test تُنفَّذ في عملية فرعية
production → prompt مع الأدوات والذاكرة، وزمن استجابة حقيقي
```

يُعدّ الـ coding القابل للتنفيذ معيار قياس محليًا موثوقًا: فهو ينفّذ
شيفرة يولّدها النموذج في عملية مؤقتة وبمهلة.

## المجموعات غير القابلة للتطبيق

المجموعة غير ذات الصلة لا تُحتسب صفرًا:

```json
{
  "vision": {
    "not_applicable": true,
    "reason": "model type does not support vision"
  }
}
```

يعامل `verified_capabilities` قيمة `not_applicable` كغياب قدرة، لا
كدرجة صفر. وهكذا تُوسم نماذج `llm` في التشغيل الحي بالنسبة إلى الرؤية.

## القدرات المتحقَّق منها

تفرّق البطاقة بين:

```text
capabilities           معلَنة من الكتالوج
capabilities_verified  مقيسة من معيار القياس
```

القدرات:

```text
chat
coding
structured_json
tool_calling
native_tools
vision
ocr
reasoning
```

يستخدم الوسيط `capabilities_verified` عند وجودها. والنموذج الذي يعلن
`chat` ثم يرفض المحادثة لا يُختار لملف تعريفي خاص بالمحادثة؛ لكنه قد
يُختار لـ `coding` أو `tool_calling`.

مثال:

```json
{
  "capabilities": {
    "chat": false,
    "coding": true,
    "structured_json": true,
    "tool_calling": true,
    "native_tools": true,
    "vision": false,
    "ocr": false,
    "reasoning": true
  }
}
```

## المهلات التكيفية

يستخدم الوسيط زمن استجابة p95 من البطاقة لتقدير مهلة النداء الواحد:

```text
timeout = clamp(p95 * safety * input_factor * output_factor, floor, ceiling)
```

الإعدادات:

```yaml
timeouts:
  adaptive: true
  floor_seconds: 30
  ceiling_seconds: 900
  safety_factor: 1.5
  cold_start_seconds: 120
  turn_ceiling_seconds: 1800
```

وتُعدّ الأدوات البطيئة على حدة:

```yaml
tools:
  timeout: 120
  timeouts:
    document.ocr_pdf: 900
```

ولا ينزل الدور تحت أقصى مهلة للأدوات المعدَّة.

## الردود والـ reasoning

قد يضع LM Studio نص الرد في:

```text
message.content
message.reasoning_content
message.reasoning
message.thinking
```

يستخدم Hagar الحقل `content` ردًا رئيسيًا. وإن كان فارغًا، استخدم
الـ reasoning المنقّى كبديل وسجّل `llm.reasoning_fallback`. وإن كان
للنموذج أيضًا استدعاء أدوات، فلا يحلّ الـ reasoning محل النص أبدًا:
ويبقى استدعاء الأداة ذا أولوية.

بعض النماذج تُرجع أغلفة (wrapper) من قوالب المحادثة:

```text
<|im_start|>assistant ... <|im_end|>
<start_of_turn>model ... <end_of_turn>
<answer> ... </answer>
<thinking> ... </thinking>
```

يزيل Hagar هذه الأغلفة المعروفة، لكن لا يزيل HTML العام مثل
`<b>...</b>`. والردود المنقّاة تسجّل `llm.text_cleaned`.

## الرؤية (Vision)

عند الطلب فقط:

```text
/models test vision
```

يستخدم مجموعة صور تخليقية ثابتة:

```text
اللون السائد
عدّ العناصر
علاقة مكانية
OCR
مخطط أعمدة
حقل واجهة
OCR بنص صغير
مخطط بتسميات
واجهة متعددة الحقول
وصف مشهد
```

لكل صورة معرِّف وSHA-256 في التشغيل. والدرجة هي متوسط الحالات. ولا
ينبغي اختبار نموذج بلا قدرة رؤية بهذا الأمر.

## سجل التشغيلات

يحفظ كل `/models test` أيضًا تشغيلًا منفصلًا:

```text
%LOCALAPPDATA%/Hagar/benchmark-runs/<run_id>.json
```

أو `HAGAR_BENCHMARK_RUNS`.

الأوامر:

```text
/models runs
/models runs 5
```

تحتوي البطاقة آخر نتيجة؛ ويحفظ السجل التشغيلات للمقارنة عبر الزمن. ولا
تُحذف البطاقات.

ويحتوي كل تشغيل أيضًا `suite_manifest`، وفيه:

```text
إصدار المجموعة
حالات الجودة والـ prompt
صور الرؤية، والمعرِّف، وSHA-256
```

وبذلك تبقى النتيجة قابلة للتفسير حتى عندما تُوسَّع المجموعات.

ولا تقيس بعد:

- الجودة الدلالية للردود؛
- معايرة الاحتمالات؛
- الدقة على مجموعة بيانات محددة؛
- TTFT في البث؛
- الحمل المتزامن؛
- استهلاك الطاقة؛
- الصوت؛
- التفضيل البشري.

## الأوامر

```text
/models list
/models show <provider> <model>
/models test
/models test vision
/models runs [n]
/models hardware
```

يختبر `/models test` نموذج الـ LLM الحالي ويحفظ البطاقة.
ويشغّل `/models test vision` مجموعة الرؤية.

## العتاد

`detect_hardware()` يعمل بأفضل جهد وهو متعدد المنصات:

- Windows: registry، و`GlobalMemoryStatusEx`، و`wmic`، و`nvidia-smi`؛
- Linux: `/proc/cpuinfo`، و`/proc/meminfo`، و`/sys/class/drm`، و`nvidia-smi`؛
- macOS: `sysctl`، و`system_profiler`.

الحقول غير القابلة للاكتشاف تبقى `null`، لا صفرًا. وغياب بيانات
لا يعني أن العتاد غير موجود.

## الاستخدام المستقبلي في الوسيط

سيستخدم الوسيط البطاقة للترشيح والترتيب:

```text
القدرات المطلوبة
العتاد المتاح
RAM/VRAM كافية
زمن الاستجابة p50/p95
التكلفة
الموقع
آخر اختبار
```

لا تُحذف البطاقة القديمة: بل تُوسم كمنتهية الصلاحية أو
تُعاد اختبارها.
