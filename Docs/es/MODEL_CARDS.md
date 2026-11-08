# Fichas técnicas de los modelos

**Estado:** implementado
**Comandos:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Propósito

Las fichas alimentan el futuro broker LLM con datos medidos, no con
suposiciones. Una ficha por proveedor/modelo se guarda como JSON en:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

o bien `HAGAR_MODEL_CARDS`, o `$XDG_STATE_HOME/hagar/models`.

## Formato

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

`last_tested_at` está siempre presente y se actualiza en cada `/models test`.

## Qué mide

- latencia de chat: min, media, p50, p95, max;
- tokens de output por segundo;
- validez JSON;
- elección válida en el conjunto de las label;
- tool calling con un tool de benchmark;
- hardware en el momento de la prueba.

Aún no mide:

- calidad semántica de las respuestas;
- calibración de las probabilidades;
- precisión sobre un dataset específico;
- TTFT en streaming;
- carga concurrente;
- consumo energético.

## Comandos

```text
/models list
/models show <provider> <model>
/models test
/models hardware
```

`/models test` prueba el modelo LLM actual y guarda la ficha.

## Hardware

`detect_hardware()` es best-effort y multiplataforma:

- Windows: registry, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

Los campos no detectables quedan `null`, no cero. La ausencia de un dato no
significa que el hardware no exista.

## Uso futuro en el broker

El broker usará la ficha para filtrar y ordenar:

```text
capabilities solicitadas
hardware disponible
RAM/VRAM suficientes
latencia p50/p95
coste
localidad
última prueba
```

Una ficha antigua no debe borrarse: debe marcarse como caducada o
volverse a probar.
