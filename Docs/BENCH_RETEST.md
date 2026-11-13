# Hagar benchmark — retest mirato

Aggiornato: `2026-11-13T20:10:41+00:00`
Host: `http://localhost:1234/v1`

## Confronto

| Modello | Qualità vecchia | Qualità nuova | Chat | Capability | Errori |
|---|---|---|---|---|---|
| `lmstudio-community/meta-llama-3.1-8b-instruct` | 0.0534 | 0.1216 | 1/1 | chat, structured_json, tool_calling, native_tools | 0 |
| `microsoft/phi-4-reasoning-plus` | 0.0000 | 0.2934 | 1/1 | chat, native_tools | 4 |
| `qwen3.5-35b-a3b` | 0.2182 | 0.2171 | 1/1 | chat, tool_calling, native_tools | 2 |

Nota: gli errori includono timeout, modello scaricato da LM Studio e JSON non valido. I punteggi nuovi non sono quindi tutti confrontabili.

## Dettaglio

### `lmstudio-community/meta-llama-3.1-8b-instruct`

- qualità precedente: `0.0534`
- qualità nuova: `0.1216`
  - summary: `0.4800`
  - translation: `0.2496`
  - extraction: `0.0000`
  - instruction: `0.0000`
  - reasoning: `0.0000`
  - coding: `0.0000`
- chat: `1/1`, p50 `41491.88 ms`

### `microsoft/phi-4-reasoning-plus`

- qualità precedente: `0.0000`
- qualità nuova: `0.2934`
  - summary: `0.3500`
  - translation: `0.4106`
  - extraction: `0.0000`
  - instruction: `1.0000`
  - reasoning: `0.0000`
  - coding: `0.0000`
- chat: `1/1`, p50 `64191.92 ms`
- errori:
  - summary technical: model unloaded
  - translation EN→IT: read timeout 600s
  - structured: extra data after JSON
  - tool_call: model unloaded

### `qwen3.5-35b-a3b`

- qualità precedente: `0.2182`
- qualità nuova: `0.2171`
  - summary: `0.9000`
  - translation: `0.4029`
  - extraction: `0.0000`
  - instruction: `0.0000`
  - reasoning: `0.0000`
  - coding: `0.0000`
- chat: `1/1`, p50 `168118.11 ms`
- errori:
  - translation EN→IT: read timeout 600s
  - structured: extra data after JSON

