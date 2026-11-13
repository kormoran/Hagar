# Hagar benchmark live — LM Studio

Avvio: `2026-11-13T05:27:34+00:00`
Aggiornato: `2026-11-13T06:51:39+00:00`
Host: `http://localhost:1234/v1`

Completato: `2026-11-13T06:51:39+00:00`

## Note

- Le prime schede completate prima del resume usano i tentativi originali (3 chat, 2 tool, 2 qualità); i modelli successivi usano 1 tentativo per completare la rassegna.
- `deepseek-coder-6.7b-instruct`, `starcoder2-7b` e `llama-3.2-8x3b-gated-moe-horror-reasoning...` sono stati fermati dopo oltre 30–40 minuti senza risposta e sono registrati come failure.
- I due modelli `text-embedding-*` sono esclusi: non sono agenti chat.
- I punteggi sono indicativi: una sola esecuzione per la maggior parte dei modelli.

## Politica

```text
llm/vlm: benchmark testo + qualità
vlm: anche benchmark vision
embeddings: esclusi
un modello alla volta
errori registrati, si continua
ripetizioni: 3 chat/2 tool/2 qualità per le prime schede, 1 per le successive
```

## Riepilogo

| Modello | Tipo | Testo | Qualità | Vision | Errori |
|---|---|---|---|---|---|
| `text-embedding-nomic-embed-code` | embeddings | n/d | n/d | n/d | 1 |
| `text-embedding-nomic-embed-text-v1.5` | embeddings | n/d | n/d | n/d | 1 |
| `bullerwins/meta-llama-3.1-8b-instruct` | llm | ok | 0.8348 | n/d | 0 |
| `codestral-22b-v0.1` | llm | ok | 0.8721 | n/d | 0 |
| `deepseek-coder-6.7b-instruct` | llm | fail | n/d | n/d | 1 |
| `deepseek-r1-distill-qwen-7b` | llm | ok | 0.3497 | n/d | 0 |
| `essentialai/rnj-1` | llm | ok | 0.4474 | n/d | 0 |
| `falcon3-mamba-7b-instruct` | llm | ok | 0.7084 | n/d | 0 |
| `granite-3.2-8b-instruct` | llm | ok | 0.7185 | n/d | 0 |
| `llama-3.2-3b-instruct-abliterated` | llm | ok | 0.7697 | n/d | 0 |
| `llama-3.2-8x3b-gated-moe-horror-reasoning-dark-champion-uncensored-18.4b-imat` | llm | fail | n/d | n/d | 1 |
| `llama-3.2-8x3b-moe-dark-champion-instruct-uncensored-abliterated-18.4b` | llm | ok | 0.6502 | n/d | 0 |
| `llama3.1-8b` | llm | ok | 0.7861 | n/d | 0 |
| `lmstudio-community/meta-llama-3.1-8b-instruct` | llm | ok | 0.0534 | n/d | 0 |
| `mamba-codestral-7b-v0.1` | llm | ok | 0.5268 | n/d | 0 |
| `microsoft/phi-4-reasoning-plus` | llm | ok | 0.0000 | n/d | 0 |
| `nvidia-nemotron-3-nano-4b` | llm | ok | 0.3523 | n/d | 0 |
| `qwen2.5-coder-14b-instruct` | llm | ok | 0.8526 | n/d | 0 |
| `qwen2.5-coder-32b-instruct` | llm | ok | 0.6952 | n/d | 0 |
| `qwen2.5-coder-7b-instruct` | llm | ok | 0.8452 | n/d | 0 |
| `qwen3-32b` | llm | ok | 0.3000 | n/d | 0 |
| `qwen3-coder-next` | llm | ok | 0.9295 | n/d | 0 |
| `qwen3.5-35b-a3b` | llm | ok | 0.2182 | n/d | 0 |
| `recursivesi/flint` | llm | ok | 0.3976 | n/d | 0 |
| `starcoder2-7b` | llm | fail | n/d | n/d | 1 |
| `baidu.unlimited-ocr` | vlm | ok | 0.0430 | 0.0000 | 0 |
| `gemma-3-27b-it` | vlm | ok | 0.8567 | 0.9667 | 0 |
| `google/gemma-4-12b-qat` | vlm | ok | 0.2260 | 0.1000 | 0 |
| `google/gemma-4-26b-a4b-qat` | vlm | ok | 0.1719 | 0.1000 | 0 |

## Dettaglio

### `text-embedding-nomic-embed-code`

- tipo: `embeddings`
- quantizzazione: `Q4_K_S`
- contesto max: `32768`
- errori:
  - `embedding model: non chat`

### `text-embedding-nomic-embed-text-v1.5`

- tipo: `embeddings`
- quantizzazione: `Q4_K_M`
- contesto max: `2048`
- errori:
  - `embedding model: non chat`

### `bullerwins/meta-llama-3.1-8b-instruct`

- tipo: `llm`
- quantizzazione: `Q4_K_S`
- contesto max: `131072`
- testo: chat 3/3, p50 2378.64 ms, JSON 3/3, tool 2/2
- qualità: 0.8348
  - summary: 0.5150
  - translation: 0.4939
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 1.0000

### `codestral-22b-v0.1`

- tipo: `llm`
- quantizzazione: `Q2_K`
- contesto max: `32768`
- testo: chat 3/3, p50 12284.62 ms, JSON 3/3, tool 2/2
- qualità: 0.8721
  - summary: 0.6300
  - translation: 0.6028
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 1.0000

### `deepseek-coder-6.7b-instruct`

- tipo: `llm`
- quantizzazione: `Q4_K_S`
- contesto max: `16384`
- testo: fallito
- errori:
  - `saltato: bloccato nella run precedente`

### `deepseek-r1-distill-qwen-7b`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `131072`
- testo: chat 3/3, p50 64364.45 ms, JSON 2/3, tool 1/2
- qualità: 0.3497
  - summary: 0.7600
  - translation: 0.6716
  - extraction: 0.6667
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000

### `essentialai/rnj-1`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `32768`
- testo: chat 3/3, p50 2533.62 ms, JSON 3/3, tool 2/2
- qualità: 0.4474
  - summary: 0.6600
  - translation: 0.5243
  - extraction: 0.0000
  - instruction: 1.0000
  - reasoning: 0.0000
  - coding: 0.5000

### `falcon3-mamba-7b-instruct`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `1048576`
- testo: chat 3/3, p50 2652.05 ms, JSON 3/3, tool 2/2
- qualità: 0.7084
  - summary: 0.4450
  - translation: 0.4720
  - extraction: 0.8333
  - instruction: 1.0000
  - reasoning: 0.5000
  - coding: 1.0000

### `granite-3.2-8b-instruct`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `131072`
- testo: chat 3/3, p50 2605.88 ms, JSON 3/3, tool 2/2
- qualità: 0.7185
  - summary: 0.7450
  - translation: 0.5660
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 0.0000
  - coding: 1.0000

### `llama-3.2-3b-instruct-abliterated`

- tipo: `llm`
- quantizzazione: `Q4_K_S`
- contesto max: `131072`
- testo: chat 3/3, p50 2365.06 ms, JSON 3/3, tool 2/2
- qualità: 0.7697
  - summary: 0.5200
  - translation: 0.5981
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 0.5000

### `llama-3.2-8x3b-gated-moe-horror-reasoning-dark-champion-uncensored-18.4b-imat`

- tipo: `llm`
- quantizzazione: `Q3_K_S`
- contesto max: `131072`
- testo: fallito
- errori:
  - `saltato: bloccato nella run precedente`

### `llama-3.2-8x3b-moe-dark-champion-instruct-uncensored-abliterated-18.4b`

- tipo: `llm`
- quantizzazione: `Q3_K_S`
- contesto max: `131072`
- testo: chat 1/1, p50 59509.44 ms, JSON 1/1, tool 1/1
- qualità: 0.6502
  - summary: 0.3800
  - translation: 0.5211
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 0.0000

### `llama3.1-8b`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `131072`
- testo: chat 1/1, p50 38631.22 ms, JSON 1/1, tool 1/1
- qualità: 0.7861
  - summary: 0.4000
  - translation: 0.3165
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 1.0000

### `lmstudio-community/meta-llama-3.1-8b-instruct`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `131072`
- testo: chat 1/1, p50 39462.39 ms, JSON 1/1, tool 1/1
- qualità: 0.0534
  - summary: 0.2000
  - translation: 0.1206
  - extraction: 0.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000

### `mamba-codestral-7b-v0.1`

- tipo: `llm`
- quantizzazione: `Q3_K_M`
- contesto max: `1048576`
- testo: chat 1/1, p50 25810.3 ms, JSON 1/1, tool 1/1
- qualità: 0.5268
  - summary: 0.5700
  - translation: 0.5906
  - extraction: 1.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 1.0000

### `microsoft/phi-4-reasoning-plus`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `32768`
- testo: chat 1/1, p50 65889.94 ms, JSON 0/1, tool 0/1
- qualità: 0.0000
  - summary: 0.0000
  - translation: 0.0000
  - extraction: 0.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000

### `nvidia-nemotron-3-nano-4b`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `1048576`
- testo: chat 1/1, p50 31667.35 ms, JSON 0/1, tool 0/1
- qualità: 0.3523
  - summary: 0.5700
  - translation: 0.5438
  - extraction: 0.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 1.0000

### `qwen2.5-coder-14b-instruct`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `131072`
- testo: chat 1/1, p50 66156.84 ms, JSON 1/1, tool 1/1
- qualità: 0.8526
  - summary: 0.5800
  - translation: 0.5354
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 1.0000

### `qwen2.5-coder-32b-instruct`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `131072`
- testo: chat 1/1, p50 141268.63 ms, JSON 1/1, tool 1/1
- qualità: 0.6952
  - summary: 0.6400
  - translation: 0.5314
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 0.0000
  - coding: 1.0000

### `qwen2.5-coder-7b-instruct`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `32768`
- testo: chat 1/1, p50 40381.28 ms, JSON 1/1, tool 1/1
- qualità: 0.8452
  - summary: 0.5800
  - translation: 0.4912
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 1.0000

### `qwen3-32b`

- tipo: `llm`
- quantizzazione: `Q3_K_L`
- contesto max: `32768`
- testo: chat 1/1, p50 207736.78 ms, JSON 0/1, tool 1/1
- qualità: 0.3000
  - summary: 0.8000
  - translation: 0.0000
  - extraction: 1.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000

### `qwen3-coder-next`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `262144`
- testo: chat 0/1, p50 302100.55 ms, JSON 0/1, tool 1/1
- qualità: 0.9295
  - summary: 0.8500
  - translation: 0.7272
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 1.0000

### `qwen3.5-35b-a3b`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `262144`
- testo: chat 1/1, p50 167335.0 ms, JSON 0/1, tool 1/1
- qualità: 0.2182
  - summary: 0.9000
  - translation: 0.4094
  - extraction: 0.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000

### `recursivesi/flint`

- tipo: `llm`
- quantizzazione: `Q4_K_M`
- contesto max: `262144`
- testo: chat 1/1, p50 173928.83 ms, JSON 0/1, tool 1/1
- qualità: 0.3976
  - summary: 0.8200
  - translation: 0.5656
  - extraction: 1.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000

### `starcoder2-7b`

- tipo: `llm`
- quantizzazione: `Q4_K_S`
- contesto max: `16384`
- testo: fallito
- errori:
  - `saltato: bloccato nella run precedente`

### `baidu.unlimited-ocr`

- tipo: `vlm`
- quantizzazione: `Q4_K_M`
- contesto max: `32768`
- testo: chat 1/1, p50 42087.63 ms, JSON 0/1, tool 0/1
- qualità: 0.0430
  - summary: 0.2500
  - translation: 0.0082
  - extraction: 0.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000
- vision: 0.0000
  - vision_color: 0.0000
  - vision_count: 0.0000
  - vision_spatial: 0.0000
  - vision_ocr: 0.0000
  - vision_chart: 0.0000
  - vision_ui: 0.0000
  - vision_ocr_small: 0.0000
  - vision_chart_months: 0.0000
  - vision_ui_multi: 0.0000
  - vision_scene_description: 0.0000

### `gemma-3-27b-it`

- tipo: `vlm`
- quantizzazione: `Q3_K_L`
- contesto max: `131072`
- testo: chat 1/1, p50 112861.47 ms, JSON 1/1, tool 1/1
- qualità: 0.8567
  - summary: 0.4800
  - translation: 0.6603
  - extraction: 1.0000
  - instruction: 1.0000
  - reasoning: 1.0000
  - coding: 1.0000
- vision: 0.9667
  - vision_color: 1.0000
  - vision_count: 1.0000
  - vision_spatial: 1.0000
  - vision_ocr: 1.0000
  - vision_chart: 1.0000
  - vision_ui: 1.0000
  - vision_ocr_small: 1.0000
  - vision_chart_months: 1.0000
  - vision_ui_multi: 1.0000
  - vision_scene_description: 0.6667

### `google/gemma-4-12b-qat`

- tipo: `vlm`
- quantizzazione: `Q4_0`
- contesto max: `262144`
- testo: chat 1/1, p50 89840.47 ms, JSON 0/1, tool 1/1
- qualità: 0.2260
  - summary: 0.8000
  - translation: 0.5559
  - extraction: 0.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000
- vision: 0.1000
  - vision_color: 0.0000
  - vision_count: 0.0000
  - vision_spatial: 0.0000
  - vision_ocr: 0.0000
  - vision_chart: 0.0000
  - vision_ui: 0.0000
  - vision_ocr_small: 0.0000
  - vision_chart_months: 0.0000
  - vision_ui_multi: 0.0000
  - vision_scene_description: 1.0000

### `google/gemma-4-26b-a4b-qat`

- tipo: `vlm`
- quantizzazione: `Q4_0`
- contesto max: `262144`
- testo: chat 1/1, p50 122361.31 ms, JSON 0/1, tool 1/1
- qualità: 0.1719
  - summary: 0.9000
  - translation: 0.1315
  - extraction: 0.0000
  - instruction: 0.0000
  - reasoning: 0.0000
  - coding: 0.0000
- vision: 0.1000
  - vision_color: 0.0000
  - vision_count: 0.0000
  - vision_spatial: 0.0000
  - vision_ocr: 0.0000
  - vision_chart: 0.0000
  - vision_ui: 0.0000
  - vision_ocr_small: 0.0000
  - vision_chart_months: 0.0000
  - vision_ui_multi: 0.0000
  - vision_scene_description: 1.0000

## File

```text
schede: benchmarks/live-cards/
run:    benchmarks/live-runs/
```

