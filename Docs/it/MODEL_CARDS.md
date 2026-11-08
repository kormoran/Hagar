# Schede tecniche dei modelli

**Stato:** implementato
**Comandi:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Scopo

Le schede alimentano il futuro broker LLM con dati misurati, non con
supposizioni. Una scheda per provider/modello viene salvata come JSON in:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

oppure `HAGAR_MODEL_CARDS`, o `$XDG_STATE_HOME/hagar/models`.

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

`last_tested_at` è sempre presente e viene aggiornato a ogni `/models test`.

## Cosa misura

- latenza chat: min, media, p50, p95, max;
- token di output al secondo;
- validità JSON;
- scelta valida nell'insieme delle label;
- tool calling con un tool di benchmark;
- hardware al momento della prova.

Non misura ancora:

- qualità semantica delle risposte;
- calibrazione delle probabilità;
- accuratezza su un dataset specifico;
- TTFT in streaming;
- carico concorrente;
- consumo energetico.

## Comandi

```text
/models list
/models show <provider> <model>
/models test
/models hardware
```

`/models test` prova il modello LLM corrente e salva la scheda.

## Hardware

`detect_hardware()` è best-effort e multipiattaforma:

- Windows: registry, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

I campi non rilevabili restano `null`, non zero. L'assenza di un dato non
significa che l'hardware non esista.

## Uso futuro nel broker

Il broker userà la scheda per filtrare e ordinare:

```text
capabilities richieste
hardware disponibile
RAM/VRAM sufficienti
latenza p50/p95
costo
località
ultima prova
```

Una scheda vecchia non va cancellata: va marcata come scaduta o
ritestata.
