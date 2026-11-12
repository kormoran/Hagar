# Tarjetas de modelo

**Estado:** implementado
**Comandos:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Propósito

Las tarjetas alimentan el futuro broker LLM con datos medidos, no con
suposiciones. Se guarda una tarjeta por proveedor/modelo como JSON en:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

o bien en `HAGAR_MODEL_CARDS`, o en `$XDG_STATE_HOME/hagar/models`.

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

`last_tested_at` siempre está presente y se actualiza en cada `/models test`.

## Qué mide

- latencia de chat: min, media, p50, p95, max;
- tokens de salida por segundo;
- validez del JSON;
- elección válida dentro del conjunto de etiquetas;
- tool calling con un tool de benchmark;
- hardware en el momento de la prueba.

Todavía no mide:

- calidad semántica de las respuestas;
- calibración de las probabilidades;
- exactitud sobre un dataset específico;
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

`/models test` prueba el modelo LLM actual y guarda la tarjeta.

## Hardware

`detect_hardware()` es best-effort y multiplataforma:

- Windows: registry, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

Los campos que no se pueden detectar quedan en `null`, no en cero. La
ausencia de un dato no significa que el hardware no exista.

## Uso futuro en el broker

El broker usará la tarjeta para filtrar y ordenar:

```text
capabilities solicitadas
hardware disponible
RAM/VRAM suficientes
latencia p50/p95
costo
localidad
última prueba
```

Una tarjeta antigua no debe borrarse: debe marcarse como caducada o
volverse a probar.
