# Hagar benchmark — retest mirato

Aggiornato: `2026-11-14T01:25:58+00:00`
Host: `http://localhost:1234/v1`

## Confronto

| Modello | Qualità vecchia | Qualità nuova | Chat | Capability | Errori |
|---|---|---|---|---|---|
| `lmstudio-community/meta-llama-3.1-8b-instruct` | 0.0534 | 0.0947 | 1/1 | chat, structured_json, tool_calling, native_tools | 0 |
| `microsoft/phi-4-reasoning-plus` | 0.0000 | 0.0000 | 1/1 | chat, tool_calling, native_tools | 5 |
| `qwen3.5-35b-a3b` | 0.2182 | 0.2356 | 1/1 | chat, tool_calling, native_tools | 1 |

## Dettaglio

### `lmstudio-community/meta-llama-3.1-8b-instruct`

- qualità precedente: `0.0534`
- qualità nuova: `0.0947`
  - summary: `0.3800`
  - translation: `0.1879`
  - extraction: `0.0000`
  - instruction: `0.0000`
  - reasoning: `0.0000`
  - coding: `0.0000`
- chat: `1/1`, p50 `38127.13 ms`

### `microsoft/phi-4-reasoning-plus`

- qualità precedente: `0.0000`
- qualità nuova: `0.0000`
  - summary: `0.0000`
  - translation: `0.0000`
  - extraction: `0.0000`
  - instruction: `0.0000`
  - reasoning: `0.0000`
  - coding: `0.0000`
- chat: `1/1`, p50 `67316.31 ms`
- errori:
  - `structured: Extra data: line 1 column 54 (char 53)`
  - `summary: HTTPConnectionPool(host='localhost', port=1234): Read timed out. (read timeout=600)`
  - `summary: HTTPConnectionPool(host='localhost', port=1234): Read timed out. (read timeout=600)`
  - `translation: HTTPConnectionPool(host='localhost', port=1234): Read timed out. (read timeout=600)`
  - `translation: HTTPConnectionPool(host='localhost', port=1234): Read timed out. (read timeout=600)`

### `qwen3.5-35b-a3b`

- qualità precedente: `0.2182`
- qualità nuova: `0.2356`
  - summary: `0.9000`
  - translation: `0.5139`
  - extraction: `0.0000`
  - instruction: `0.0000`
  - reasoning: `0.0000`
  - coding: `0.0000`
- chat: `1/1`, p50 `65541.01 ms`
- errori:
  - `structured: Extra data: line 1 column 54 (char 53)`

