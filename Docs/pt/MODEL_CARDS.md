# Fichas técnicas dos modelos

**Estado:** implementado
**Comandos:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Objetivo

As fichas alimentam o futuro broker LLM com dados medidos, não com
suposições. Uma ficha por provider/modelo é guardada como JSON em:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

ou `HAGAR_MODEL_CARDS`, ou `$XDG_STATE_HOME/hagar/models`.

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

`last_tested_at` está sempre presente e é atualizado a cada `/models test`.

## O que mede

- latência de chat: min, média, p50, p95, max;
- tokens de output por segundo;
- validade do JSON;
- escolha válida no conjunto de labels;
- tool calling com uma tool de benchmark;
- hardware no momento do teste.

Ainda não mede:

- qualidade semântica das respostas;
- calibração das probabilidades;
- acurácia num dataset específico;
- TTFT em streaming;
- carga concorrente;
- consumo energético.

## Comandos

```text
/models list
/models show <provider> <model>
/models test
/models hardware
```

`/models test` testa o modelo LLM atual e guarda a ficha.

## Hardware

`detect_hardware()` é best-effort e multiplataforma:

- Windows: registry, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

Os campos não detetáveis permanecem `null`, não zero. A ausência de um dado não
significa que o hardware não exista.

## Uso futuro no broker

O broker usará a ficha para filtrar e ordenar:

```text
capabilities requeridas
hardware disponível
RAM/VRAM suficientes
latência p50/p95
custo
localidade
último teste
```

Uma ficha antiga não deve ser apagada: deve ser marcada como expirada ou
testada novamente.
