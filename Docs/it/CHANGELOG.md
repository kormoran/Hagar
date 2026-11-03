# HAGAR — Changelog

Il formato è libero ma stabile: versioni in ordine decrescente, con
riferimento al commit quando utile.

---

# Non rilasciato

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
