# البطاقات التقنية للنماذج

**الحالة:** مُنفَّذ
**الأوامر:** `/models list`، `/models show`، `/models test`، `/models hardware`

## الغرض

تغذّي البطاقات وسيط الـ LLM المستقبلي ببيانات مقيسة، لا
بافتراضات. وتُحفظ بطاقة لكل مزوّد/نموذج كـ JSON في:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

أو `HAGAR_MODEL_CARDS`، أو `$XDG_STATE_HOME/hagar/models`.

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

`last_tested_at` موجود دائمًا ويُحدَّث مع كل `/models test`.

## ما تقيسه

- زمن استجابة المحادثة: الحد الأدنى والمتوسط وp50 وp95 والحد الأقصى؛
- رموز الإخراج في الثانية؛
- صحة JSON؛
- اختيار صالح داخل مجموعة التسميات؛
- استدعاء الأدوات بأداة قياس؛
- العتاد في لحظة الاختبار.

ولا تقيس بعد:

- الجودة الدلالية للردود؛
- معايرة الاحتمالات؛
- الدقة على مجموعة بيانات محددة؛
- TTFT في البث؛
- الحمل المتزامن؛
- استهلاك الطاقة.

## الأوامر

```text
/models list
/models show <provider> <model>
/models test
/models hardware
```

يختبر `/models test` نموذج الـ LLM الحالي ويحفظ البطاقة.

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
تُعاد اختبارًا.
