# Hagar — Changelog della suite di test

Questo file riguarda solo `tests/`. La storia del progetto è in
`Docs/it/CHANGELOG.md` e `Docs/en/CHANGELOG.md`.

## Stato

- 476 test superati, 1 skip (symlink non disponibili senza Developer
  Mode).
- Esecuzione: `.\tools\run_tests.ps1`; con `--live` si aggiungono i test
  che chiamano servizi reali (7 test).
- Nessuna rete nella suite normale: Ollama, MCP e i provider remoti sono
  simulati.

## Copertura

| area | file |
|---|---|
| configurazione | `test_config.py` |
| packaging e CLI | `test_packaging.py`, `test_hagar.py` |
| sandbox filesystem | `test_filesystem.py` |
| tool filesystem | `test_filesystem_tools.py` |
| registry e definizioni | `test_tool_definition.py`, `test_tool_registry.py` |
| agent e audit | `test_agent.py`, `test_audit.py` |
| calling nativo | `test_native_tools.py`, `test_agent_native.py` |
| backend LLM | `test_ollama_client.py`, `test_llm_backends.py`, `test_factory.py` |
| MCP | `test_mcp_client.py` |
| permessi e policy | `test_permissions.py`, `test_policy.py`, `test_registry_permissions.py` |
| memoria | `test_memory_store.py`, `test_memory_tools.py`, `test_agent_memory.py` |
| vault | `test_vault.py` |
| cablaggio harness | `test_hagar.py` |
| live (opt-in) | `tests/live/` |

## Storia

### 2026-11-03 — calling nativo

- `native_step()` per i quattro provider, con schema dei parametri e
  messaggi canonici `tool`;
- più chiamate per turno e fallback automatico al protocollo testuale;
- `test_native_tools.py` (payload/parsing) e `test_agent_native.py`
  (ciclo, limite, fallback);
- 476 test, 1 skip; 7 test live.

### 2026-11-03 — igiene

- packaging e CLI (`hagar`, `--config`, `--model`, `--no-memory`);
- test live esclusi di default (`--live`);
- MCP con SSE, notifica `initialized` e risultati normalizzati;
- audit con catena di hash, rotazione e redazione;
- base URL per tutti i provider, legacy rimosso;
- 442 test, 1 skip.

### 2026-11-03 — memoria

- store episodico e semantico, tool `memory.*` e iniezione del contesto;
- integrazione con l'Agent, policy per namespace e fallback senza vault;
- 407 test, 1 skip.

### 2026-11-03 — permessi

- evaluator, policy loader e integrazione nel registry;
- conferma ASK rifiutata e accettata, audit delle decisioni.

### 2026-11-03 — debug e suite

- prima suite completa (config, sandbox, tool, agent, LLM, MCP, vault);
- 259 test, runner `tools/run_tests.ps1` con shim per la sandbox Windows.
