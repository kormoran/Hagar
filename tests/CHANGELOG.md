# Hagar — Changelog della suite di test

Questo file riguarda solo `tests/`. La storia del progetto è in
`Docs/it/CHANGELOG.md`.

## Stato

- 794 test superati, 2 skip su Windows (symlink non disponibili senza
  Developer Mode).
- 796 test superati, 0 skip su Debian Linux (2026-11-06); i due test
  symlink girano davvero. Questo è il primo controllo multipiattaforma
  reale prima della release.
- Esecuzione: `.\tools\run_tests.ps1` (Windows) oppure
  `./tools/run_tests.sh` (Linux/macOS); con `--live` si aggiungono i test
  che chiamano servizi reali (9 test).
- Nessuna rete nella suite normale: Ollama, MCP, feed e provider remoti
  sono simulati.

## Copertura

| area | file |
|---|---|
| configurazione | `test_config.py` |
| packaging e CLI | `test_packaging.py`, `test_hagar.py` |
| sandbox filesystem | `test_filesystem.py`, `test_filesystem_v2.py` |
| tool filesystem | `test_filesystem_tools.py` |
| comandi console | `test_console_commands.py` |
| service layer | `test_service.py`, `test_command_service.py` |
| GUI web e conferme | `test_confirmations.py`, `test_web.py` |
| token usage | `test_usage.py` |
| indice memorie | `test_memory_index.py` |
| vision e stop | `test_images.py`, `test_agent.py`, `test_web.py` |
| cronologia chat | `test_history.py` |
| tab GUI e session log | `test_web.py` |
| memorie e usage | `test_memory_index.py`, `test_command_service.py` |
| plugin tool e LLM | `test_plugins.py`, `test_factory.py` |
| subagenti asincroni | `test_subagents.py`, `test_agent_data.py` |
| tool locali | `test_local_tools.py`, `test_time_tools.py`, `test_text_url_tools.py` |
| registry e definizioni | `test_tool_definition.py`, `test_tool_registry.py` |
| agent e audit | `test_agent.py`, `test_audit.py` |
| memoria e progetti | `test_memory_store.py`, `test_memory_tools.py`, `test_memory_cli.py`, `test_agent_memory.py`, `test_projects.py`, `test_archive.py` |
| calling nativo | `test_native_tools.py`, `test_agent_native.py` |
| backend LLM | `test_ollama_client.py`, `test_llm_backends.py`, `test_openai_compatible.py`, `test_factory.py` |
| MCP | `test_mcp_client.py` |
| permessi e policy | `test_permissions.py`, `test_policy.py`, `test_registry_permissions.py` |
| memoria | `test_memory_store.py`, `test_memory_tools.py`, `test_agent_memory.py` |
| vault | `test_vault.py` |
| cablaggio harness | `test_hagar.py` |
| live (opt-in) | `tests/live/` |

## Storia

### 2026-11-04 — filesystem v2 e local_tools

- test per `list_dir`, `read_chunk`, `rename`, `copy_file`, `search`;
- test per calculator, statistica, unità e feed (incluso RSS finto);
- test SSRF: loopback, reti private, link-local, redirect e credenziali;
- test della radice virtuale `/home/ai`: nessun path fisico in
  `stat`, `list_dir`, `search`, `read_chunk` e messaggi dei tool;
- test alias: root listabile, path indipendenti, lookup
  case-insensitive, permessi per mount, `X` per `chdir`, ricerca tra
  alias, path e nomi con spazi;
- test hardening: UTF-8 nei chunk, `read_file` oltre un chunk, limiti e
  messaggi di `list_dir`/`search`, symlink invisibili;
- capability `COMPUTE`/`NETWORK` e config `permissions.network`;
- 650 test, 2 skip.

### 2026-11-04 — memoria v2 (0.2.0)

- stati `candidate`/`confirmed`/`archived` e `set_skill_status`;
- review CLI `/memory` con conferma/archivio/salta/esci;
- recall delle sole confermate, top 3, etichettato come dati;
- test di store, CLI, Agent e dispatch nel loop;
- 552 test, 1 skip.

### 2026-11-03 — MCP OAuth

- PKCE, discovery, dynamic registration, callback loopback e cache token;
- refresh automatico e retry 401 nel client MCP;
- test del flusso interattivo con authorization server finto, config e
  wiring del harness;
- 522 test, 1 skip.

### 2026-11-03 — audit retention

- backup timestampati e pruning con `max_files` (default 100);
- catena di hash che continua dal backup più recente;
- test di rotazione, retention e riavvio;
- 504 test, 1 skip.

### 2026-11-03 — MCP auth

- `auth` bearer/header per server MCP, token da variabile d'ambiente;
- risoluzione header e isolamento del server se il token manca;
- test di config, header HTTP e harness;
- 496 test, 1 skip.

### 2026-11-03 — DeepSeek live

- modelli aggiornati a `deepseek-flash` / `deepseek-v4-pro`;
- messaggi d'errore con il corpo dell'API e rifiuto delle chiavi
  non-ASCII;
- nomi tool normalizzati per le API senza punto (mappatura reversibile);
- `tools/diagnose_deepseek.py`;
- test live: chat, calling nativo ed end-to-end sul filesystem;
- 479 test, 1 skip; 9 test live.

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
