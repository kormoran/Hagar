# Hagar benchmark — retest mirato

Aggiornato: `2026-11-13T18:57:47+00:00`
Host: `http://localhost:1234/v1`

## Confronto

| Modello | Qualità vecchia | Qualità nuova | Chat | Capability | Errori |
|---|---|---|---|---|---|
| `lmstudio-community/meta-llama-3.1-8b-instruct` | 0.0534 | 0.1216 | 1/1 | chat, structured_json, tool_calling, native_tools | 0 |
| `microsoft/phi-4-reasoning-plus` | 0.0000 | n/d | fail | n/d | 0 |

In corso: `microsoft/phi-4-reasoning-plus`

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
- qualità nuova: non disponibile
- chat: fallita

