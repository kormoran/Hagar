# PROJECT_STATE.md

# 0. HAGAR

## 0.1 Harness Agentico Generale per AI Resilienti

---

# 1. Visione del progetto

Hagar è un harness per LLM sviluppato in Python e progettato per l'esecuzione resiliente di LLM.

L'obiettivo non è semplicemente fornire una chat con un modello linguistico, ma creare un ambiente operativo ***sicuro*** nel quale un LLM possa utilizzare strumenti, consultare una memoria persistente e interagire con sistemi esterni senza accedere direttamente alle risorse reali della macchina host, e in cui si possano evitare o almeno mitigare gli errori più comuni.

A questo scopo vengono adottati principi e metodologie proprie della HMI/HCI (progettazione di interfacce utente dei macchinari industriale) e della Cognitive Ergonomics, applicandoli alla progettazione di un ambiente in cui l'LLM dovrà operare. Come prima iterazione del progetto, si definiscono qui **Le Quattro Leggi di HAGAR**:

## 1.1 Prima legge di HAGAR
**L'LLM non è attendibile per definizione.** Non perché cattivo o inutile: perché è probabilistico. Quindi ogni sua affermazione va verificata e ogni sua azione va limitata.

## 1.2 Seconda legge di HAGAR
**I tool sono più affidabili dell'LLM.** Se il filesystem dice che un file esiste, esiste. Se il tool restituisce una dimensione, quella dimensione è reale. L'LLM interpreta, ma i tool misurano.

## 1.3 Terza legge di HAGAR
**Lo stato deve esistere fuori dalla mente dell'LLM.** Introducendo ToolRegistry, MCP, FilesystemSandbox e (prossimamente) PermissionEvaluator spostiamo conoscenza e controllo fuori dal modello. È esattamente ciò che si fa nei sistemi safety-critical.

## 1.4 Quarta legge di HAGAR
**Ogni azione deve poter essere spiegata dopo.** L'audit log è fondamentale: quando qualcosa andrà storto, e prima o poi succederà, la domanda non sarà: "Perché l'LLM è impazzito?" ma: "Quale assunzione ha fatto?" "Quale tool ha usato?" "Quale dato era sbagliato?" In altre parole: investigazione incidenti. Come in aviazione.

## 1.5 Architettura software

Strutturalmente, HAGAR si basa su cinque principi fondamentali:

- separazione tra modello e sistema operativo;
- sicurezza per impostazione predefinita;
- architettura a plugin;
- indipendenza dal provider LLM;
- estendibilità tramite tool e protocollo MCP.

---

# 2. Divieti assoluti

Il modello non deve mai:

- accedere direttamente al filesystem host;
- eseguire comandi sulla shell reale;
- ottenere privilegi superiori a quelli definiti dalla configurazione;
- conoscere l'organizzazione effettiva del sistema operativo.

Tutte le operazioni passano esclusivamente attraverso tool registrati e controllati dall'harness.

---

# 3. Architettura attuale

```
Utente
  │
  ▼
Agent
  │
  ├── OllamaClient
  │
  ├── ToolRegistry
  │     ├── filesystem.*
  │     └── mcp.*
  │
  ├── FileSystemSandbox
  │
  ├── MCPClient
  │
  └── Vault
```

Flusso di esecuzione:

```
Utente
  ↓
LLM
  ↓
ToolCall
  ↓
ToolRegistry
  ↓
ToolResult
  ↓
LLM
  ↓
Risposta finale
```

---

# 4. Componenti implementati

## Config

Funzionalità:

- caricamento configurazione YAML;
- validazione parametri;
- gestione configurazione del modello;
- gestione configurazione MCP;
- gestione configurazione workspace.

---

## OllamaClient

Funzionalità:

- generate();
- chat();
- request_tool_call();
- parsing robusto del JSON;
- supporto multi-step agent.

Il client è progettato per essere sostituito in futuro da altri backend senza modificare l'Agent.

---

## ToolRegistry

Completato.

Funzionalità:

- registrazione tool;
- ricerca tool;
- esecuzione tool;
- abilitazione/disabilitazione;
- esportazione metadati verso il modello.

---

## ToolDefinition

Completato.

Ogni tool possiede:

- nome;
- descrizione;
- categoria;
- parametri;
- handler;
- flag di abilitazione.

---

## ToolCall

Completato.

Rappresenta una richiesta di esecuzione strumento generata dal modello.

---

## ToolResult

Completato.

Rappresenta il risultato strutturato di una chiamata tool.

---

## Agent

Completato.

Funzionalità:

- orchestrazione completa LLM ↔ Tool;
- gestione errori;
- supporto multi-step;
- limite configurabile alle chiamate tool;
- generazione della risposta finale.

---

## FileSystemSandbox

Completato.

Funzionalità:

- sandbox del filesystem;
- percorsi relativi sicuri;
- controllo dei limiti della sandbox;
- supporto a permessi ereditabili;
- protezione dai symlink;
- gestione directory corrente;
- controllo spazio disponibile.

L'LLM non vede mai il filesystem reale.

---

## FileSystem Tools

Completato.

Tool esposti:

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

`filesystem.stat` restituisce in un'unica misura tipo (`file`,
`directory`, `other`), dimensione in byte, date di creazione, modifica e
accesso (ISO 8601 con offset locale) e permessi **effettivi della
sandbox** — non le ACL del sistema operativo, che l'agente non deve
conoscere. Un percorso inesistente non è un errore: restituisce
`exists: false` con i permessi che la sandbox applicherebbe.

Un solo tool invece di tre (dimensione, date, permessi): i metadati si
leggono insieme, e tre tool separati costerebbero tre round-trip con il
modello per la stessa informazione. Se l'uso reale mostrerà il bisogno
di misure separate, si dividono.

---

## MCP Client

Completato.

Funzionalità:

- protocollo MCP via HTTP;
- inizializzazione;
- discovery automatica dei tool;
- registrazione automatica nel ToolRegistry;
- namespace separati.

Esempi:

```text
mcp.github.create_issue

mcp.obsidian.search

mcp.erp.customer_lookup
```

---

## Vault

Implementazione iniziale presente.

L'integrazione avanzata con memoria semantica è rimandata alla v0.2 e successive.

---

# 5. Stato della Versione 0.1

## Milestone raggiunta

✅ Configurazione caricata

✅ Connessione a Ollama

✅ Agent operativo

✅ Tool Registry

✅ Tool Calling JSON

✅ Parsing robusto delle risposte del modello

✅ Supporto multi-step

✅ FileSystem Sandbox

✅ Tool del filesystem

✅ Integrazione MCP

✅ Utilizzo unificato di tool locali e remoti

---

# 6. Celebrazione della Versione 0.1

🎉 HAGAR VERSIONE 0.1 COMPLETATA 🎉

Questa è la prima versione realmente funzionante del progetto.

Per la prima volta Hagar è in grado di:

- dialogare con un LLM locale;
- esporre strumenti al modello;
- consentire al modello di scegliere autonomamente i tool;
- utilizzare tool locali;
- utilizzare tool MCP remoti;
- operare su un filesystem sandboxato;
- concatenare più operazioni in modo autonomo.

Non è più una semplice interfaccia verso Ollama.

È diventato un agente operativo.

La v0.1 rappresenta il passaggio da "idea progettuale" a "sistema funzionante".

---

# 7. Roadmap Versione 0.2

## Priorità 1 - Backend multipli per LLM

Obiettivo:

rendere il provider del modello completamente sostituibile.

Provider previsti:

- Ollama
- Gemini
- DeepSeek
- OpenAI
- Claude
- backend futuri

Nuova architettura:

```text
Agent
  │
  ▼
LLM Interface
  ├── OllamaClient
  ├── GeminiClient
  ├── DeepSeekClient
  └── ...
```

---

## Priorità 2 - AIsh

Obiettivo:

creare una shell dedicata agli LLM.

AIsh sarà concettualmente simile a Bash ma non avrà alcun accesso alla shell reale del sistema.

Caratteristiche:

- nessuna esecuzione di comandi host;
- utilizzo esclusivo di tool registrati;
- integrazione con filesystem simulato;
- integrazione con tool MCP;
- supporto pipe e comandi virtuali;
- ambiente completamente sicuro e controllabile.

Esempio:

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```

Tutti i comandi verranno tradotti in chiamate ai tool dell'harness.

---

## Priorità 3 - Memoria conversazionale

Obiettivo:

permettere a Hagar di ricordare il contesto tra richieste successive.

Funzionalità previste:

- cronologia conversazioni;
- memoria operativa;
- recupero del contesto rilevante;
- persistenza nel vault Obsidian.

---

# 8. Obiettivi successivi

Dopo il completamento della v0.2:

- PermissionEvaluator centralizzato;
- memoria semantica;
- ChromaDB;
- RAG;
- gestione attività;
- scratchpad persistente;
- osservazione del vault;
- agente personale permanente.

---

# 9. Stato attuale

Hagar è ufficialmente in fase:

```text
Versione 0.1
STABILE
PRONTA PER TEST REALI
```

La priorità immediata non è aggiungere funzionalità.

La priorità immediata è usare il sistema, romperlo, analizzarlo e capire quali problemi emergono durante l'utilizzo reale.

Da questo momento l'esperienza pratica avrà più valore di qualunque speculazione architetturale.

---

# 10. Debug e suite di test (post-v0.1)

## 10.1 Difetti corretti

- `core/filesystem.py` era troncato a metà di `mkdir`: mancavano
  `read_file`, `write_file`, `create_file`, `delete_file` e `free_space`,
  quindi ogni tool del filesystem falliva con `AttributeError`.
- `ToolDefinition.origin` era obbligatorio ma nessun provider lo passava:
  la registrazione di qualunque tool falliva con `TypeError`. Ora ha un
  valore predefinito (`local`) e i tool MCP dichiarano `mcp.<namespace>`.
- `core/tool_result.py` esponeva `tool` mentre `Agent` usava `tool_name`
  (con `error` obbligatorio): ogni esecuzione tool falliva. Il duplicato
  divergente `llm/tool_result.py` è ora un semplice alias.
- `llm/ollama_client.py` usava `re` senza importarlo (NameError sul parsing
  markdown) e definiva `_tool_call_from_json` due volte.
- `hagar.py` leggeva `cfg.workspace_path`, `cfg.vault_path` e `cfg.data`,
  campi inesistenti: `main()` non partiva. Ora usa i campi reali di
  `AppConfig`, espone `build_harness()` (testabile) e gestisce EOF/Ctrl-C.
- `ConfigLoader` non validava il documento: YAML vuoto, radice non-mapping,
  permessi non booleani e `allowed` non lista producevano eccezioni
  diverse da `ConfigError`.
- `write_file` poteva creare file nuovi aggirando il permesso `create`.
  Ora richiede un file esistente; la creazione passa da `create_file`.
- Le etichette dei risultati tool riportano nome ed esito: riducono le
  risposte incoerenti del modello e facilitano l'analisi a posteriori.

## 10.2 Robustezza verso il modello reale

Provato con `qwen3:8b` via Ollama: il modello a volte risponde in prosa
invece che in JSON e usa `"parameters"` invece di `"arguments"`.

Il client ora accetta l'alias `parameters` e, se la risposta non è JSON,
esegue **un solo** tentativo di riparazione prima di sollevare un errore
esplicito che riporta entrambe le risposte. La prosa non viene mai
considerata una risposta valida: la Prima Legge vieta di fidarsi.

## 10.3 Suite di test

`tests/` copre configurazione, sandbox, tool filesystem, registry, agent,
client Ollama, client MCP, vault e cablaggio del harness. I test non
toccano la rete: Ollama e MCP sono simulati.

```
259 test superati, 1 skip (symlink non disponibili senza Developer Mode)
```

Esecuzione:

```
.\tools\run_tests.ps1
```

Il runner serve perché Python 3.13+ applica il mode `0o700` di
`tempfile.mkdtemp()`: dentro la sandbox Windows il token ristretto non
accede a quelle cartelle e ogni `tmp_path` fallirebbe. Lo shim in
`tools/pytest_shim` riporta il mode a `0o777`; su Windows i bit POSIX non
hanno significato e il confinamento resta garantito da token e jail.

## 10.4 Limiti noti

- `PermissionEvaluator` non esiste: `FS_Guardian` è ancora locale alla
  sandbox;
- `core/permissions.py` e `tools/filesystem.py` sono implementazioni
  legacy non usate e vanno rimosse o integrate;
- il client MCP non gestisce risposte SSE né la notifica
  `notifications/initialized`;
- `Agent` riceve il `Vault` ma non lo usa ancora.

---

# 11. v0.2: audit log e backend multipli

## 11.1 Audit log (Quarta Legge)

Ogni sessione scrive un file JSON Lines append-only (`audit.path`,
default `logs/audit.jsonl`, risolto rispetto al file di configurazione).
Ogni riga porta timestamp UTC, `session` ed `event`; tutti gli eventi di
una stessa domanda condividono un `turn` id.

```text
harness.start      provider, modello, radici, permessi, tool, vault
turn.start         domanda, limite tool
llm.tool_choice    cosa ha scelto il modello, con argomenti
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
- valori non JSON (Path, oggetti arbitrari) resi serializzabili;
- nessuna chiave API nel log;
- il log contiene anche il contenuto dei file letti dai tool: va
  protetto come il workspace.

Esempio reale con `qwen3:8b`: una risposta in prosa ha prodotto
`llm.protocol_error`, poi `llm.repaired` e infine `turn.answer`. Il log
mostra dal vivo l'assunzione sbagliata del modello e la correzione,
senza doverla riprodurre.

## 11.2 Backend multipli

`llm/base.py` definisce `LLMClient`: un backend concreto implementa solo
`chat()`; rendering dei tool, prompt di selezione, parsing robusto del
JSON e riparazione sono condivisi. La conversazione interna usa soltanto
i ruoli `user` e `assistant`, e ogni client la traduce nel proprio
formato.

| provider | API | chiave | note |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | host default `localhost:11434` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system separato, turni alternati |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, ruolo `model` |

La chiave si legge sempre dall'ambiente; `model.api_key_env` sovrascrive
il nome predefinito. `model.host` resta solo per Ollama e
`model.max_tokens` solo per Claude (default 1024).

`model.provider` era già presente nella configurazione ma veniva
ignorato (si usava sempre Ollama): ora seleziona davvero il backend.

Il risultato dei tool viene registrato come turno `user` e non `system`:
i backend remoti non accettano messaggi di sistema in mezzo al dialogo,
e il modello lo legge come input dell'ambiente.

## 11.3 Test

La suite copre anche audit log, factory dei provider e i tre backend
con trasporto HTTP simulato (payload, header, conversione dei ruoli,
errori). Restano fuori i test live contro i provider remoti, che
richiedono chiavi reali.

## 11.4 Prossimi passi

- **Vault come sistema di memoria** (deciso, da fare): il vault Obsidian
  diventerà il supporto delle memorie dell'agente. Serviranno tool per
  leggere e scrivere note e una ricerca sul contenuto; oggi `Agent`
  riceve il `Vault` ma non lo usa.
- `PermissionEvaluator` centralizzato, che assorba `FS_Guardian`.
- Tool di elenco directory e di rinomina, se l'uso reale li richiederà.
- Test live dei provider remoti, quando ci saranno chiavi dedicate.

## 11.5 Scelta del modello (Ollama)

Confronto su quattro attività (lettura, metadati, creazione, chat senza
tool) con `python tools/bench_models.py`, sandbox temporanea e limite di
4 tool per turno:

| modello | read | stat | create | chat | riparazioni |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | **loop**, 4 tool | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | **tool errato** | **file errato** | **contenuto errato** | ok 6.4 s | 3 |

`llama3.1:latest` è il default (`hagar.yaml`): sceglie il tool giusto con
gli argomenti giusti, è il più veloce e ha una sola riparazione — la
chat, dove risponde in prosa invece di restituire `{"tool": null}`.

Osservazioni:

- `qwen3:8b` resta usabile ma è più lento e usa `stat` prima di
  `read_file`; con lui la riparazione JSON scatta più spesso.
- `hermes3:8b` non converge quando il risultato del tool contiene già la
  risposta: ripete lo stesso tool fino al limite. Il `turn.stop`
  nell'audit rende il caso visibile.
- `gemma:latest` sbaglia tool, nome file e contenuto (ha creato `Ciao!`
  invece di `ciao` e ha provato `mkdir` su un file).

La riparazione del protocollo è ciò che rende accettabili anche i modelli
che rispondono in prosa: senza, ogni scarto diventerebbe un turno
fallito. Il limite di 4 tool evita che un modello in loop consumi dieci
round-trip.

Il confronto è riproducibile con:

```
python tools/bench_models.py
python tools/bench_models.py llama3.1:latest
```