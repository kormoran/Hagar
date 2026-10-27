# Project_state.md

## 1. Hagar the Harness

Il programma Hagar.py è un harness in Python per LLM che girano in locale (sulla stessa macchina del programma).

Le sue caratteristiche fondamentali:

- Struttura a plugin;
- Usa Ollama come provider;
- Mette a disposizione dei tool MCP al LLM;
- Non scrive nessun file sul filesystem reale ma usa Obsidian come sistema di memoria persistente;
- Il LLM non vede mai il filesystem locale del computer reale e non vi accede mai direttamente, ma solo tramite un filesystem virtuale emulato dall'harness, con un sistema di permessi simulato e un elenco di directory accessibili impostate nel file di configurazione;
- Tutte le operazioni sul filesystem passano attraverso tool controllati e validati dall'harness;
- Il modello deve essere sostituibile senza modifiche alla logica applicativa.

---

## 2. Struttura su disco del progetto

```text
Hagar/
│
├── Hagar.py
├── Hagar.yaml
│
├── core/
│   ├── agent.py
│   ├── config.py
│   ├── permissions.py
│   ├── tool_registry.py
│   └── models.py
│
├── llm/
│   └── ollama_client.py
│
├── memory/
│   ├── vault.py
│   ├── embeddings.py
│   └── vectorstore.py
│
├── tools/
│   ├── filesystem.py
│   ├── vault_search.py
│   └── git_tools.py
│
├── data/
│   └── chroma/
│
└── vault/
```

---

## 3. Principi architetturali

### Sicurezza

Il LLM non deve mai:

- conoscere i percorsi reali della macchina host;
- accedere direttamente al filesystem;
- eseguire comandi arbitrari;
- ottenere privilegi superiori a quelli stabiliti dalla configurazione.

Tutte le operazioni avvengono tramite tool registrati nell'harness.

### Namespace virtuali

Il filesystem presentato al modello utilizza percorsi virtuali:

```text
vault://
workspace://smac/
workspace://archiver/
workspace://docs/
```

L'harness traduce tali percorsi nei corrispondenti percorsi reali solo dopo aver verificato i permessi.

### Memoria

Obsidian rappresenta la memoria persistente del sistema.

Le note del vault costituiscono:

- memoria a lungo termine;
- documentazione;
- knowledge base;
- archivio delle decisioni progettuali.

---

## 4. Roadmap

### Fase 1 - Fondamenta operative

Obiettivo: ottenere un harness funzionante.

Attività:

- caricamento della configurazione YAML;
- connessione a Ollama;
- registry dei tool;
- sistema di permessi;
- filesystem virtuale minimale;
- lettura file autorizzati;
- scansione del vault Obsidian;
- interfaccia a riga di comando.

Risultato atteso:

Hagar è in grado di dialogare con il modello e recuperare informazioni da file e note autorizzate.

---

### Fase 2 - Integrazione RAG con Obsidian

Obiettivo: usare il vault come memoria semantica.

Attività:

- chunking automatico dei documenti;
- generazione degli embedding;
- memorizzazione in ChromaDB;
- ricerca semantica;
- recupero automatico del contesto rilevante.

Flusso:

```text
Domanda
    ↓
Embedding
    ↓
Ricerca vettoriale
    ↓
Recupero chunk rilevanti
    ↓
Prompt finale
    ↓
LLM
```

Risultato atteso:

Hagar può rispondere sulla base delle informazioni presenti nel vault senza dover caricare l'intero archivio nel prompt.

---

### Fase 3 - Tool Calling e MCP

Obiettivo: consentire al modello di utilizzare strumenti esterni.

Attività:

- protocollo di chiamata tool in JSON;
- esecuzione controllata dei tool;
- gestione errori;
- logging;
- integrazione MCP;
- plugin caricabili dinamicamente.

Esempio:

```json
{
  "tool": "read_file",
  "arguments":
  {
    "path": "workspace://smac/renderqueue.hpp"
  }
}
```

Risultato atteso:

Il modello può esplorare autonomamente la knowledge base e le directory autorizzate.

---

### Fase 4 - Assistente personale persistente

Obiettivo: trasformare Hagar in un vero agente locale.

Attività:

- memoria operativa persistente;
- scratchpad permanente;
- lista attività;
- gestione progetti;
- collegamenti automatici fra note;
- osservazione del vault in tempo reale;
- indicizzazione incrementale.

File previsti:

```text
vault://agent/context.md
vault://agent/todo.md
vault://agent/scratchpad.md
vault://agent/decisions.md
```

Risultato atteso:

Hagar mantiene il contesto nel tempo e può supportare attività progettuali continuative.

---

## 5. Possibili estensioni future

Funzionalità non necessarie per la prima versione ma compatibili con l'architettura:

- supporto a provider multipli oltre Ollama;
- accesso controllato a repository Git;
- indicizzazione del codice sorgente;
- memoria gerarchica a più livelli;
- supporto multiutente;
- interfaccia web;
- integrazione con sistemi di ticketing;
- pianificatore di attività automatiche;
- supporto a più vault Obsidian.

---

## 6. Quindi, ora

Le prossime attività concrete sono:

1. Creare la struttura delle directory del progetto.
2. Implementare il caricamento della configurazione YAML.
3. Implementare il PermissionManager.
4. Implementare il filesystem virtuale minimale.
5. Implementare il registry dei tool.
6. Implementare il client Ollama.
7. Collegare tutti i componenti in Hagar.py.
8. Realizzare una prima CLI interattiva.
9. Verificare che il modello possa:
   - ricevere una domanda;
   - leggere una nota del vault;
   - leggere un file autorizzato;
   - rispettare i vincoli di accesso.
10. Solo dopo questa validazione iniziare il lavoro sugli embedding e sulla memoria vettoriale.

### Definizione di "Versione 0.1"

La Versione 0.1 è completata quando:

- Hagar si avvia correttamente;
- comunica con Ollama;
- carica la configurazione;
- accede al vault Obsidian;
- espone almeno due tool funzionanti;
- applica correttamente il sistema di permessi;
- risponde a domande reali usando informazioni recuperate dal vault.