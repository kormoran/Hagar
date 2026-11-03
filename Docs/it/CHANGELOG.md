# HAGAR — Changelog

Il formato è libero ma stabile: versioni in ordine decrescente, con
riferimento al commit quando utile.

---

# Non rilasciato

## MCP auth

- `mcp_servers[].auth`: `type: bearer` oppure `type: header`, con
  `token_env` e, per l'header, il nome dell'header.
- Il token si legge solo dall'ambiente: non va nel YAML, nell'audit o
  nei log.
- Token mancante o non-ASCII: il server viene saltato con `mcp.failed` e
  il harness continua con gli altri.
- 496 test superati, 1 skip.

## Benchmark nativo vs testo

- `tools/bench_native.py`: 9 task filesystem sullo stesso registry,
  confronto tra `native_step()` e `request_tool_call()`, con accuratezza,
  latenza e riparazioni.
- Prime misure: `llama3.1` 4/5 vs 5/5, `qwen3:8b` 4/5 vs 5/5,
  `hermes3:8b` 4/5 vs 3/5, `deepseek-flash` 8/9 vs 9/9 (subset Ollama,
  suite completa DeepSeek).
- Nessun vincitore universale: il default resta nativo, con opt-out per
  modello tramite `model.native_tools` o `--no-native-tools`.

## DeepSeek (live)

- Modelli aggiornati: `deepseek-flash` (default) e `deepseek-v4-pro`;
  `deepseek-chat` non è più valido.
- Messaggi d'errore con il corpo della risposta API; chiavi non-ASCII
  rifiutate con `ConfigError`.
- Nomi dei tool normalizzati per le API che non ammettono il punto
  (`filesystem.read_file` → `filesystem__read_file`), con ritorno al
  nome interno.
- `tools/diagnose_deepseek.py` per rete, forma della chiave ed endpoint,
  senza stampare la chiave.
- Test live: chat, calling nativo ed end-to-end sul filesystem.
- 479 test superati, 1 skip; 9 test live con `--live`.

## Calling nativo (v1)

- `LLMClient.native_step()` e `LLMReply`: calling nativo per Ollama,
  DeepSeek, Claude e Gemini; schema dei parametri da `ToolDefinition`.
- Messaggi canonici `assistant` con `tool_calls` e `tool` con
  `tool_call_id`; ogni backend li traduce (`tool_calls`, `tool_use`/
  `tool_result`, `functionCall`/`functionResponse`).
- L'Agent esegue più chiamate per turno, nel limite `max_tool_calls`.
- Fallback automatico al protocollo testuale su HTTP 400/404/422 al primo
  passo, con evento `llm.native_fallback`; `model.native_tools: false` e
  `--no-native-tools` lo forzano.
- Audit: `turn.start` con `native`, `llm.tool_choice` con `mode=native`.
- 476 test superati, 1 skip; 7 test live con `--live`.

## Igiene (v1)

- **Packaging**: `pyproject.toml` completo (metadati, dipendenze,
  setuptools), entry point `hagar`, versione unica (`hagar.__version__`);
  `pip install -e .` verificato.
- **CLI**: `--config`, `--model`, `--no-memory`, `--version`;
  configurazione cercata in `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml`.
- **Test live**: marker `live`, esclusi dalla suite normale, `--live`
  per Ollama e provider remoti (skippati senza chiave).
- **MCP**: risposte `text/event-stream`, notifica
  `notifications/initialized`, normalizzazione dei risultati a testo.
- **Audit**: catena di hash (`prev`/`hash`, `verify_chain`), rotazione a
  `max_bytes`, redazione dell'output dei tool con `include_outputs`.
- **URL base**: `model.host` usato da tutti i provider.
- **Legacy**: rimossi `tools/filesystem.py` e `llm/tool_result.py`.
- 442 test superati, 1 skip; 6 test live con `--live`.

## Memoria (v1)

- `memory/store.py`: memoria episodica (una nota per sessione in
  `<vault>/Hagar/chat/`) e semantica
  (`<vault>/Hagar/skills/<slug>.md`);
- iniezione automatica degli ultimi `memory.context_turns` turni nel
  prompt, con troncamento; un errore di memoria non fa fallire il turno;
- tool `memory.create_skill` (provenance e stato `candidate`),
  `memory.list_skills`, `memory.get_context` (ricerca per parola chiave);
- capability `MEMORY_READ`/`MEMORY_WRITE`, namespace `chat`/`skills` per
  le policy;
- configurazione `memory.*` e disattivazione con avviso se il vault
  manca;
- eventi audit `memory.enabled`, `memory.disabled`, `memory.context`,
  `memory.turn`, `memory.failed`;

## Permessi (PermissionEvaluator v1)

- nuovo `core/permissions.py`: `Capability` (IntFlag), `Effect`
  (`ALLOW` / `ASK` / `DENY`, con deny-overrides), `Rule` con scope per
  tool, path e namespace, `Subject`, `Resource`, `Decision` ed
  evaluator puro;
- `policy.yaml` separato, letto prima di costruire il LLM: in caso di
  errore tutte le policy diventano `DENY`, con evento `policy.failed` e
  warning in chat;
- tetto di sistema derivato da `permissions.read/write/shell`;
- `ASK` con conferma da console (`lo faccio? (y/N)`, default N) e
  `ConfirmationProvider` per le future GUI;
- `ToolRegistry.execute` applica la policy e registra
  `permission.decision` e `permission.confirmation`;
- `ToolDefinition.capabilities` per tutti i tool (filesystem e MCP);
- `requires_confirmation` ora applicato come pavimento di ASK;
- rimosso lo stub incompleto `PolicyRule` da `core/models.py`;

## Documentazione

- `PROJECT_STATE.md` diviso in `ARCHITECTURE.md` (com'è il sistema),
  `ROADMAP.md` (cosa fare e decisioni prese) e questo `CHANGELOG.md`.
- Roadmap aggiornata con le decisioni del 2026-11-03: memoria su Vault,
  calling nativo dei tool, `PermissionEvaluator`.

---

# 0.2.0 — 2026-11-03 (in sviluppo)

Commit: `137c985` — *Debug, suite di test, audit log e backend multipli*

## Aggiunto

- **Audit log** (`core/audit.py`): JSON Lines append-only con timestamp
  UTC, `session` e `turn` id. Eventi per sessione, turno, scelta del
  tool, protocollo, esecuzione, errori, MCP e provider. Scrittura best
  effort, troncamento configurabile, nessuna chiave API nel log.
- **Backend multipli** (`llm/base.py`, `llm/factory.py`,
  `deepseek_client.py`, `claude_client.py`, `gemini_client.py`):
  `LLMClient` condivide selezione dei tool, parsing e riparazione del
  JSON; ogni backend implementa solo il trasporto e la conversione dei
  ruoli.
- **`filesystem.stat`**: tipo, dimensione in byte, date ISO 8601 e
  permessi effettivi della sandbox, in una sola misura.
- **Suite di test**: 259 test, 1 skip, senza rete (Ollama e MCP
  simulati), con `tools/run_tests.ps1` e shim per la sandbox Windows.
- **`tools/bench_models.py`**: confronto riproducibile dei modelli
  Ollama su lettura, metadati, creazione e chat.

## Cambiato

- `model.provider` seleziona davvero il backend (prima era ignorato e si
  usava sempre Ollama). Chiavi API dall'ambiente, mai dal YAML.
- Modello predefinito: `llama3.1:latest` al posto di `qwen3:8b`.
- I risultati dei tool sono turni `user` e non `system`, per compatibilità
  con i backend remoti.
- Errori di configurazione: uscita pulita (`SystemExit 1`) con messaggio
  su stderr e evento `llm.failed` nell'audit.

## Corretto

- `core/filesystem.py` era troncato a metà di `mkdir`: mancavano
  `read_file`, `write_file`, `create_file`, `delete_file`,
  `free_space`. Ogni tool del filesystem falliva con `AttributeError`.
- `ToolDefinition.origin` era obbligatorio ma nessun provider lo passava:
  la registrazione di qualunque tool falliva con `TypeError`.
- `ToolResult` usava `tool` mentre l'`Agent` usava `tool_name`.
- `llm/ollama_client.py` usava `re` senza importarlo e definiva due volte
  `_tool_call_from_json`.
- `hagar.py` leggeva campi inesistenti di `AppConfig`: `main()` non
  partiva.
- `ConfigLoader` non validava YAML vuoto, radici non-mapping, permessi
  non booleani, `allowed` non lista.
- `write_file` poteva creare file nuovi aggirando il permesso `create`.
- Il parsing accetta l'alias `parameters`; una risposta in prosa produce
  un solo tentativo di riparazione, poi errore esplicito.

## Note

Confronto modelli Ollama (4 attività, sandbox temporanea, max 4 tool per
turno):

| modello | read | stat | create | chat | riparazioni |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | loop, 4 tool | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | tool errato | file errato | contenuto errato | ok 6.4 s | 3 |

---

# 0.1.0 — 2026-11-02

Commit: `03b35bf` — *versione 0.1 alpha*

Prima versione realmente funzionante: Hagar non è più un'interfaccia
verso Ollama, è un agente operativo.

## Aggiunto

- caricamento e validazione della configurazione YAML;
- `OllamaClient` con `generate`, `chat`, `request_tool_call`;
- `ToolRegistry`, `ToolDefinition`, `ToolCall`, `ToolResult`;
- `Agent` con ciclo multi-step, gestione errori e limite ai tool;
- `FileSystemSandbox` con radici, permessi ereditabili, protezione dai
  symlink e controllo dello spazio disco;
- tool filesystem: lettura, scrittura, creazione, cancellazione,
  creazione directory, cambio directory, spazio libero;
- client MCP via HTTP con discovery automatica dei tool e namespace;
- `Vault` iniziale per i file Markdown.

## Note

La v0.1 è la prima versione in grado di dialogare con un LLM locale,
esporre strumenti, far scegliere al modello quali usare, operare su un
filesystem sandboxato e concatenare più operazioni in autonomia.
