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
- deterministic quality on textual tasks;
- vision quality on synthetic images;
- hardware at the time of the test.

## Quality per task

`/models test` also runs a deterministic quality suite:

```text
extraction   extraction of fields into JSON
instruction  compliance with an exact instruction
reasoning    simple numerical calculation
coding       reading of a Python fragment
summary      summary with key points
translation  IT→EN and EN→IT translation
```

Each case is run twice. The score is the average of the
answers, from 0 to 1. It is not a semantic benchmark: it is a compact and
repeatable test to give the broker a better signal than the declared
quality.

Translation combines chrF with the preservation of paths, commands and
required terms. Mandatory terms weigh much more than chrF; an incorrect
technical translation is penalized explicitly. The summary measures the
presence of the key points and compliance with the
length.

The card contains:

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

The corpus is in `benchmarks/corpus/`:

```text
7 texts
2 translation references
10 synthetic images
manifest.yaml with SHA-256
```

The textual suite is `quality_v3`; the vision suite is `vision_v2`.

A `quality_task` in the TaskProfile selects the task to use; if it is
missing, the broker uses the profile name. If the card has no measured
quality, it uses the quality declared in the catalogue.

## Provider discovery

Command:

```text
/models discover lmstudio
/models discover ollama
```

It reads the runtime metadata and normalizes it into `ProviderModelInfo`:

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

`completion` is not automatically mapped to `chat`: a model can
complete text without being conversational. `chat` remains a
capability to be verified.

## Memory and context

`memory_bench` uses synthetic conversations:

```text
simple recall
distractor
contradiction between two memories
persistent instruction
long context
false premise
```

The result feeds the `memory` quality task; the `memory_chat` profile
uses it for the broker. The user's real memories are never used.

## P1 benchmark

```text
tool      → multiple tools, distractors, argument checking
JSON      → schema_valid and field_f1
coding    → unit tests run in a subprocess
production → prompt with tools and memory, real latency
```

The executable coding must be considered a trusted local benchmark: it runs
code generated by the model in a temporary process with a timeout.

## Non-applicable suites

An irrelevant suite is not worth zero:

```json
{
  "vision": {
    "not_applicable": true,
    "reason": "model type does not support vision"
  }
}
```

`verified_capabilities` treats `not_applicable` as a missing capability,
not as a zero score. The live run marks `llm` models this way for
vision.

## Verified capabilities

The card distinguishes:

```text
capabilities           declared by the catalogue
capabilities_verified  measured by the benchmark
```

Capabilities:

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

The broker uses `capabilities_verified` when present. A model that
declares `chat` but refuses the conversation is not selected for a
chat profile; it can however be selected for `coding` or
`tool_calling`.

Example:

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

## Adaptive timeouts

The broker uses the card's p95 latency to estimate the timeout of the
single call:

```text
timeout = clamp(p95 * safety * input_factor * output_factor, floor, ceiling)
```

Configuration:

```yaml
timeouts:
  adaptive: true
  floor_seconds: 30
  ceiling_seconds: 900
  safety_factor: 1.5
  cold_start_seconds: 120
  turn_ceiling_seconds: 1800
```

Slow tools are configured separately:

```yaml
tools:
  timeout: 120
  timeouts:
    document.ocr_pdf: 900
```

The turn does not go below the maximum timeout of the configured tools.

## Answers and reasoning

LM Studio can put the answer text in:

```text
message.content
message.reasoning_content
message.reasoning
message.thinking
```

Hagar uses `content` as the main answer. If it is empty, it uses the
cleaned reasoning as a fallback and records `llm.reasoning_fallback`.
If the model also has tool calls, the reasoning never replaces the
text: the tool call remains the priority.

Some models return chat template wrappers:

```text
<|im_start|>assistant ... <|im_end|>
<start_of_turn>model ... <end_of_turn>
<answer> ... </answer>
<thinking> ... </thinking>
```

Hagar removes these known wrappers, but not generic HTML such as
`<b>...</b>`. Cleaned answers record `llm.text_cleaned`.

## Vision

On request only:

```text
/models test vision
```

It uses a fixed synthetic pool of images:

```text
dominant colour
object count
spatial relation
OCR
bar chart
UI field
OCR with small text
chart with labels
multi-field UI
scene description
```

Each image has an id and a SHA-256 in the run. The score is the average
of the cases. A model without vision capability must not be tested with
this command.

## Run history

Every `/models test` also saves a separate run:

```text
%LOCALAPPDATA%/Hagar/benchmark-runs/<run_id>.json
```

or `HAGAR_BENCHMARK_RUNS`.

Commands:

```text
/models runs
/models runs 5
```

The card contains the latest result; the history keeps the runs for
comparisons over time. The cards are not deleted.

Every run also contains `suite_manifest`, with:

```text
suite version
quality cases and prompts
vision images, id and SHA-256
```

This way a result remains interpretable even when the suites
are extended.

It does not measure yet:

- semantic quality of the answers;
- calibration of the probabilities;
- accuracy on a specific dataset;
- TTFT in streaming;
- concurrent load;
- energy consumption;
- audio;
- human preference.

## Commands

```text
/models list
/models show <provider> <model>
/models test
/models test vision
/models runs [n]
/models hardware
```

`/models test` tests the current LLM model and saves the card.
`/models test vision` runs the vision suite.

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
