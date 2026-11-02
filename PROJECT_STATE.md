# PROJECT_STATE.md

# HAGAR
## Harness Agentico Generale per AI Residenti

---

# 1. Visione del progetto

Hagar è un harness per LLM sviluppato in Python e progettato per l'esecuzione locale.

L'obiettivo non è semplicemente fornire una chat con un modello linguistico, ma creare un ambiente operativo sicuro nel quale un LLM possa utilizzare strumenti, consultare una memoria persistente e interagire con sistemi esterni senza accedere direttamente alle risorse reali della macchina host.

Hagar si basa su cinque principi fondamentali:

- separazione tra modello e sistema operativo;
- sicurezza per impostazione predefinita;
- architettura a plugin;
- indipendenza dal provider LLM;
- estendibilità tramite tool e protocollo MCP.

---

# 2. Obiettivi architetturali

Il modello non deve mai:

- accedere direttamente al filesystem host;
- eseguire comandi sulla shell reale;
- ottenere privilegi superiori a quelli definiti dalla configurazione;
- conoscere l'organizzazione effettiva del sistema operativo.

Tutte le operazioni passano esclusivamente attraverso tool registrati e controllati dall'harness.

---

# 3. Architettura attuale

```text
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

```text
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

Completato.

Funzionalità:

- caricamento configurazione YAML;
- validazione parametri;
- gestione configurazione del modello;
- gestione configurazione MCP;
- gestione configurazione workspace.

---

## OllamaClient

Completato.

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
```

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