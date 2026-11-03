# HAGAR — Architettura

Versione: 0.2.0 (in sviluppo)
Ultimo aggiornamento: 2026-11-03

---

# 1. Cos'è Hagar

Hagar è un harness per LLM scritto in Python, progettato per l'esecuzione
resiliente di modelli linguistici.

L'obiettivo non è una chat con un modello, ma un ambiente operativo
**sicuro** nel quale un LLM possa usare strumenti, consultare una memoria
persistente e interagire con sistemi esterni senza accedere direttamente
alle risorse reali della macchina host.

A questo scopo il progetto applica principi di HMI/HCI e Cognitive
Ergonomics alla progettazione dell'ambiente in cui il modello opera.

## 1.1 Le Quattro Leggi di HAGAR

**Prima legge — L'LLM non è attendibile per definizione.**
Non perché cattivo o inutile: perché è probabilistico. Ogni sua
affermazione va verificata e ogni sua azione va limitata.

**Seconda legge — I tool sono più affidabili dell'LLM.**
Se il filesystem dice che un file esiste, esiste. Se il tool restituisce
una dimensione, quella dimensione è reale. L'LLM interpreta, i tool
misurano.

**Terza legge — Lo stato deve esistere fuori dalla mente dell'LLM.**
ToolRegistry, MCP, FileSystemSandbox e (in prospettiva)
PermissionEvaluator spostano conoscenza e controllo fuori dal modello,
come nei sistemi safety-critical.

**Quarta legge — Ogni azione deve poter essere spiegata dopo.**
L'audit log risponde alla domanda giusta: non "perché l'LLM è impazzito?"
ma "quale assunzione ha fatto?", "quale tool ha usato?", "quale dato era
sbagliato?". Investigazione incidenti, come in aviazione.

## 1.2 Divieti assoluti

Il modello non deve mai:

- accedere direttamente al filesystem host;
- eseguire comandi sulla shell reale;
- ottenere privilegi superiori a quelli definiti dalla configurazione;
- conoscere l'organizzazione effettiva del sistema operativo.

Tutte le operazioni passano esclusivamente attraverso tool registrati e
controllati dall'harness.

## 1.3 Principi architetturali

- separazione tra modello e sistema operativo;
- sicurezza per impostazione predefinita;
- architettura a plugin;
- indipendenza dal provider LLM;
- estendibilità tramite tool e protocollo MCP.

---

# 2. Architettura

```text
Utente
  │
  ▼
Agent ──────────────── AuditLog (JSON Lines)
  │
  ├── LLMClient (llm/base.py)
  │     ├── OllamaClient
  │     ├── DeepSeekClient
  │     ├── ClaudeClient
  │     └── GeminiClient
  │
  ├── ToolRegistry
  │     ├── filesystem.*
  │     ├── memory.*        (pianificato)
  │     └── mcp.*
  │
  ├── FileSystemSandbox
  │
  ├── MCPClient
  │
  └── Vault (Obsidian)
```

Flusso di esecuzione:

```text
Utente
  ↓
Agent              turn.start
  ↓
LLMClient          llm.tool_choice
  ↓
ToolCall
  ↓
ToolRegistry       tool.call
  ↓
ToolResult         tool.result
  ↓
LLMClient
  ↓
Risposta finale    turn.answer
```

---

# 3. Componenti

## 3.1 Config (`core/config.py`)

Carica e valida un file YAML (`hagar.yaml`) in un `AppConfig`.

Sezioni:

| sezione | obbligatoria | contenuto |
|---|---|---|
| `model` | sì | provider, nome, host, max_tokens, api_key_env |
| `vault` | sì | percorso del vault Obsidian |
| `filesystem` | sì | radici della sandbox (`allowed`) |
| `permissions` | no | read, write, shell (default `true/false/false`) |
| `rag` | no | `top_k` (default 8) |
| `mcp_servers` | no | lista di `endpoint` + `namespace` |
| `audit` | no | enabled, path, max_field_chars |

Errori di validazione producono sempre `ConfigError`, con un messaggio che
indica il campo. Il percorso dell'audit, se relativo, viene risolto
rispetto al file di configurazione.

## 3.2 Interfaccia LLM e backend (`llm/`)

`llm/base.py` definisce `LLMClient`: un backend concreto implementa solo
`chat()`. Sono condivisi:

- il prompt di selezione dei tool;
- il rendering dei metadati dei tool;
- il parsing robusto del JSON (JSON puro, blocco markdown, primo oggetto
  JSON nel testo);
- l'alias `parameters` → `arguments` (alcuni modelli usano la chiave
  sbagliata);
- la riparazione: se la risposta non è JSON valido, un solo tentativo
  guidato, poi errore esplicito con entrambe le risposte.

La conversazione interna usa solo i ruoli `user` e `assistant`; ogni
client traduce nel proprio formato. I risultati dei tool sono turni
`user`, non `system`, perché i backend remoti non accettano messaggi di
sistema in mezzo al dialogo.

| provider | API | chiave | note |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | host default `localhost:11434` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system separato, turni alternati |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, ruolo `model` |

La chiave si legge solo dall'ambiente; `model.api_key_env` sovrascrive il
nome predefinito. `model.host` è usato solo da Ollama, `model.max_tokens`
solo da Claude. `llm/factory.py` costruisce il client e rifiuta provider
sconosciuti o chiavi mancanti.

Stato attuale del protocollo: **JSON testuale**, non function calling
nativo (vedi ROADMAP).

## 3.3 Modello dei tool (`core/tool_*.py`)

`ToolDefinition` descrive nome, descrizione, categoria, parametri,
handler, `origin` (`local` oppure `mcp.<namespace>`), stato di
abilitazione e `requires_confirmation` (campo presente ma non ancora
applicato dall'Agent).

`ToolCall` è la richiesta del modello (`tool`, `arguments`);
`ToolResult` è l'esito strutturato (`tool_name`, `success`, `output`,
`error`).

`ToolRegistry` registra, cerca, abilita/disabilita ed esegue i tool;
espone i metadati al modello ed è l'unico punto di esecuzione.

## 3.4 Agent (`core/agent.py`)

Ciclo agentico multi-step:

1. chiede al modello se serve un tool;
2. se non serve, genera la risposta finale e chiude il turno;
3. se serve, esegue il tool e rimanda il risultato al modello;
4. il modello può chiedere al massimo `max_tool_calls` esecuzioni; dopo
   l'ultima ha comunque una richiesta finale. Se insiste, il turno si
   chiude con `Agent stopped after N tool calls` (protezione dai loop).

Ogni passo è registrato nell'audit: domanda, scelta del tool, argomenti,
esito, durata e risposta finale. Un audit rotto non ferma l'agente: il
guasto viene segnalato su stderr.

L'`Agent` riceve il `Vault` ma non lo usa ancora.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

Filesystem virtuale dell'agente. Ogni richiesta viene:

1. risolta contro la directory corrente (`resolve_path`);
2. verificata contro le radici concesse (`effective_permissions`);
3. filtrata dai permessi effettivi, con le radici più specifiche che
   sovrascrivono quelle più esterne;
4. controllata contro i symlink e lo spazio disco disponibile
   (`FS_Guardian`, nome legacy).

`DirectoryPermissions` modella `read`, `write`, `create`, `rename`,
`delete`, `execute`; `None` significa "eredita dalla radice esterna".
Un percorso fuori dalle radici è sempre `PermissionError`.

`FileInfo` / `stat()` restituiscono tipo, dimensione in byte, date di
creazione/modifica/accesso (ISO 8601 con offset locale) e i permessi
**effettivi della sandbox**, non le ACL del sistema operativo.

## 3.6 Tool filesystem (`core/filesystem_tools.py`)

```text
filesystem.read_file
filesystem.write_file
filesystem.create_file
filesystem.delete_file
filesystem.mkdir
filesystem.chdir
filesystem.free_space
filesystem.stat
```

`write_file` sovrascrive solo file esistenti; la creazione passa da
`create_file`, che richiede il permesso `create`. Non è possibile
aggirare il divieto di creazione scrivendo un percorso nuovo.

`filesystem.stat` restituisce JSON con `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. Un percorso inesistente non è un errore:
`exists: false` con i permessi applicabili.

## 3.7 MCP (`llm/mcp_client.py`)

Client MCP via HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
conversione automatica dei tool in `ToolDefinition` e registrazione con
namespace `mcp.<namespace>`.

Limiti noti: nessun supporto SSE, nessuna notifica
`notifications/initialized`, risultati normalizzati solo parzialmente.

## 3.8 Vault (`memory/vault.py`)

Accesso minimale al vault Obsidian: elenco ricorsivo dei file Markdown e
lettura del testo. L'integrazione con la memoria dell'agente è
pianificata (vedi ROADMAP).

## 3.9 Audit log (`core/audit.py`)

File JSON Lines append-only. Ogni riga ha timestamp UTC, `session` ed
`event`; gli eventi di una stessa domanda condividono un `turn` id.

```text
harness.start      provider, modello, radici, permessi, tool, vault
turn.start         domanda, limite tool
llm.tool_choice    scelta del modello, con argomenti
llm.protocol_error risposta non conforme (testo integrale, troncato)
llm.repaired       riparazione riuscita
llm.repair_failed  riparazione fallita
tool.call          tool, argomenti, indice
tool.result        esito, output/errore, durata in ms
turn.answer        risposta finale, numero di tool usati
turn.error         fase e messaggio
turn.stop          limite raggiunto
mcp.loaded         namespace e tool importati
mcp.failed         namespace ed errore
llm.failed         provider non costruibile (es. chiave mancante)
harness.stop       uscita pulita (se manca, il processo è stato ucciso)
```

Proprietà:

- scrittura best effort: un errore di I/O non ferma il harness e viene
  segnalato una sola volta su stderr;
- troncamento configurabile (`audit.max_field_chars`, default 2000);
- valori non JSON resi serializzabili;
- nessuna chiave API nel log;
- il log contiene anche l'output dei tool (quindi contenuti di file):
  va protetto come il workspace.

---

# 4. Modello di sicurezza

- L'agente non vede il filesystem reale: solo percorsi risolti dentro la
  sandbox.
- Le operazioni passano solo dal `ToolRegistry`; nessuna shell host.
- I permessi sono dichiarati in configurazione e applicati dalla sandbox;
  le radici annidate possono restringere o allargare i permessi.
- Gli errori sono dati: un rifiuto viene restituito al modello come
  risultato del tool, non nascosto.
- Ogni azione lascia una traccia nell'audit, con sessione e turno.

---

# 5. Sviluppo

- Suite: `.\tools\run_tests.ps1` — 259 test, 1 skip (symlink non
  disponibili senza Developer Mode). Dettagli e motivazione dello shim in
  README §3.1.
- Confronto modelli: `python tools/bench_models.py` (README §3.5).
- La suite non tocca la rete: Ollama e MCP sono simulati.

---

# 6. Limiti noti e debito tecnico

- `PermissionEvaluator` non esiste: `FS_Guardian` è locale alla sandbox e
  `requires_confirmation` non è applicato.
- Il protocollo dei tool è JSON testuale: robusto grazie alla
  riparazione, ma fragile con modelli piccoli.
- Il client MCP non gestisce SSE, `notifications/initialized` né
  normalizza del tutto i risultati.
- Gli URL base dei provider remoti sono fissi (`model.host` è solo per
  Ollama).
- `Agent` non usa il `Vault`; non esiste ancora memoria.
- `core/permissions.py` e `tools/filesystem.py` sono implementazioni
  legacy non usate.
- `chdir` espone il percorso assoluto della sandbox; da valutare percorsi
  virtuali (vedi AIsh in ROADMAP).
- L'audit non ha rotazione né integrità crittografica.

---

# 7. Mappa della documentazione

- `ARCHITECTURE.md` — questo documento: com'è il sistema oggi.
- `ROADMAP.md` — cosa fare, decisioni prese e punti aperti.
- `CHANGELOG.md` — storia delle versioni.
- `README.md` — avvio, configurazione, test.
