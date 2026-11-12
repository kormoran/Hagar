# Model technical cards

**Status:** implemented
**Commands:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Purpose

The cards feed the future LLM broker with measured data, not with
assumptions. One card per provider/model is saved as JSON in:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

or `HAGAR_MODEL_CARDS`, or `$XDG_STATE_HOME/hagar/models`.

## Format

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

`last_tested_at` is always present and is updated on every `/models test`.

## What it measures

- chat latency: min, mean, p50, p95, max;
- output tokens per second;
- JSON validity;
- valid choice within the label set;
- tool calling with a benchmark tool;
- hardware at the time of the test.

It does not measure yet:

- semantic quality of the answers;
- calibration of the probabilities;
- accuracy on a specific dataset;
- TTFT in streaming;
- concurrent load;
- energy consumption.

## Commands

```text
/models list
/models show <provider> <model>
/models test
/models hardware
```

`/models test` tests the current LLM model and saves the card.

## Hardware

`detect_hardware()` is best-effort and cross-platform:

- Windows: registry, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

Fields that cannot be detected remain `null`, not zero. The absence of a
data point does not mean that the hardware does not exist.

## Future use in the broker

The broker will use the card to filter and sort:

```text
required capabilities
available hardware
sufficient RAM/VRAM
p50/p95 latency
cost
locality
last test
```

An old card must not be deleted: it must be marked as expired or
tested again.
