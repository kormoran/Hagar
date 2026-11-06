<p align="center">
  <img src="../HAGAR.jpg">
</p>

[Italiano](../it/README.md) · [English](../en/README.md) · [Español](../es/README.md) · [中文](../zh/README.md) · [Русский](../ru/README.md) · [Português](../pt/README.md)

# H.A.G.A.R.

Harness Agentico Generale per AI Resiliente (General Resilient Agentic Harness for AIs)

# 0. Come tutto cominciò: la sicurezza 

Ho creato HAGAR perché nessun altro harness per IA isolava i miei file per impostazione predefinita. Che fosse DeepSeek, Claude Code, AutoGen o altro, se lasciati liberi, finiscono tutti per esporre il tuo file system agli LLM. Sei TU a dover imporre dei limiti e devi farlo bene, se no sono cavoli tuoi. Nessuno di questi strumenti garantisce che i tuoi dati non vengano letti per scopi imprecisati, per errore o per entrambi i motivi. E se non è l'harness stesso a farlo, potrebbe essere quel plugin tanto figo, quell'utilissima skill o qualsiasi altra aggiunta che hai appena installato...

**HAGAR ribalta questo approccio: sei TU a stabilire cosa gli LLM possono vedere, scrivere o cercare, e dove.** Nessun LLM può leggere o scrivere nulla al di fuori delle directory che hai esplicitamente indicato come leggibili o scrivibili nel file di configurazione. Se una directory non c'è nella sezione `[filesystem]` della configurazione, non esiste: per gli LLM, è come se non ci fosse.

Durante lo sviluppo di HAGAR, mi è sorto un altro interrogativo: perché un LLM dovrebbe avere bisogno di interagire con il sistema operativo? Nel mondo dell'intelligenza artificiale, il vero collo di bottiglia prestazionale sono le chiamate al modello, che possono richiedere secondi (a volte MOLTI secondi). L'accesso diretto al sistema operativo permette di risparmiare solo qualche millisecondo: vale la pena correre il rischio? La mia risposta è no.

Per questo motivo, **HAGAR fa il possibile per isolare l'LLM dal sistema operativo.** Ogni interazione con file, memorie o la macchina stessa avviene tramite strumenti specifici (basati su protocollo MCP o integrati direttamente in HAGAR). L'IA non sa su che sistema operativo sta girando, e non dovrebbe mai saperlo: se ci fosse un modo per cui un'IA possa capire il sistema operativo dove gira nonostante l'isolamento di HAGAR, lo considererò una falla di sicurezza e provvederò a correggerla (o, quantomeno, a documentare il problema per informare gli utenti).

|Harness	|Vede FS host	|Vede il SO		|Isolamento	  |
|-----------|---------------|---------------|-------------|
|Claude Code|Parziale		|Sì 	 		|Permessi	  |
|Codex CLI	|Parziale		|Sì 	 		|Sandbox	  |
|OpenHands	|No				|Sì 	 		|Docker		  |
|E2B		|No				|Sì				|VM/Container |
|`HAGAR`	|`No`			|`No`			|`FS virtuale`|

**Gli altri harness cercano di dare agli LLM un computer: HAGAR dice agli LLM che il computer non esiste.** 
Le IA dovrebbero concentrarsi sulla gestione della conoscenza più che sui dettagli tecnici (anche se sono molto brave in entrambi). Più un framework può automatizzare, minore è il ragionamento (e il numero di token) richiesto. Così anche i modelli più piccoli possono esprimere il loro pieno potenziale.

Oppure, detto in altro modo: per un LLM, HAGAR è la realtà.

# 1. Visione del progetto

HAGAR è un harness per LLM, sviluppato in Python, progettato per l'esecuzione sicura di modelli linguistici.

L'obiettivo non è fornire solo un'interfaccia di chat per un LLM, ma creare un ambiente operativo ***sicuro e protetto*** in cui l'LLM possa utilizzare strumenti, consultare una memoria persistente e interagire con sistemi esterni — il tutto senza avere accesso diretto alle risorse reali della macchina ospite — prevenendo o almeno mitigando gli errori più comuni.

Per questo ho adottato principi e metodologie provenienti sia dalla sicurezza informatica (principio del minimo privilegio, triade CIA) sia dall'ambito HMI/HCI (interazione/interfaccia uomo-macchina, tipica dei macchinari industriali) e dall'ergonomia cognitiva, applicandoli alla progettazione dell'ambiente in cui opera l'LLM: come si fa con il lavoro degli uomini, lo scopo ulteriore di HAGAR è creare un ambiente per LLM dove fare bene è facile, e sbagliare è difficile.

Sulla base di quanto esposto e al fine di stabilire una regola di condotta generale per ogni futuro sviluppo di questo software, enuncio qui **le Quattro Leggi di HAGAR**:

## 1.1 Prima Legge di HAGAR
**Un LLM è, per definizione, inaffidabile.** Ciò non significa che sia malevolo o inutile, ma che il suo funzionamento è di natura probabilistica. Di conseguenza, ogni sua affermazione deve essere verificata e ogni sua azione deve essere soggetta a vincoli.

## 1.2 Seconda Legge di HAGAR
**Gli strumenti sono più affidabili dell'LLM.** Se il file system indica che un file esiste, allora esiste davvero. Se uno strumento restituisce la dimensione di un file, tale dimensione è reale. L'LLM interpreta, ma gli strumenti misurano. 

## 1.3 Terza Legge di HAGAR
**Lo stato deve esistere al di fuori della "mente" dell'LLM.** Implementando componenti come `ToolRegistry`, `MCP`, `FilesystemSandbox`, `Memory` e `PermissionEvaluator`, trasferiamo la conoscenza e il controllo all'esterno del modello stesso. Ciò è in linea con le pratiche standard per i sistemi in cui la sicurezza è un requisito critico.

## 1.4 Quarta Legge di HAGAR
**Ogni azione deve essere spiegabile a posteriori.** Per questo motivo HAGAR implementa un *log di audit*: quando qualcosa va storto — e prima o poi succederà — la domanda non deve essere "Perché l'LLM è impazzito?", ma "Che presupposti ha adottato?", "Quale strumento ha usato?", "Quale dato era errato?". In altre parole, deve essere possibile condurre un'analisi degli incidenti, esattamente come in aviazione. HAGAR riconosce questa necessità e darà sempre gli strumenti per farla.

## 1.5 Architettura Software

Dal punto di vista strutturale, HAGAR si fonda su cinque principi fondamentali:

- separazione tra il modello e il sistema operativo;
- sicurezza per impostazione predefinita (*security by default*);
- architettura a plugin;
- indipendenza da qualsiasi specifico fornitore di LLM;
- estensibilità tramite strumenti (*tools*) e l'MCP (Model Context Protocol).

---

# 2. Divieti Assoluti

Al modello è fatto assoluto divieto di:

- accedere direttamente al file system dell'host;
- eseguire comandi in una vera shell dell'OS;
- ottenere privilegi superiori a quelli definiti in configurazione;
- conoscere il reale sistema operativo.

Tutte le operazioni devono avvenire solo attraverso strumenti registrati e controllati dall'harness.

---

# 3. Sviluppo

## 3.0 Installazione e CLI

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

`pip install -e .` dichiara i pacchetti `core`, `llm` e `memory` e
installa il comando `hagar`:

```powershell
hagar --config hagar.yaml
hagar --model qwen3:8b
hagar --no-memory
hagar --no-native-tools
hagar --version
```

La configurazione viene cercata nell'ordine seguente: parametro `--config`,
variabile d'ambiente `HAGAR_CONFIG` e infine file `./hagar.yaml`.
È inoltre possibile utilizzare `python -m hagar` lavorando direttamente sul codice sorgente.

## 3.1 Layout

```
hagar.py            Script di lancio dell'harness
hagar.yaml          Script di configurazione predefinito
policy.yaml			Configurazione dei permessi per i tool (integrati ed MCP)
core/               config, agent, audit log, registry, sandbox e tools
llm/                LLM backends (Ollama, DeepSeek, Claude, Gemini), client MCP
memory/             accesso al vault
tests/              suite pytest
tools/              helper di sviluppo (test runner, sandbox shim, model benchmark)
local_tools/		Tool per le AI integrati in HAGAR - non MCP, ma disponibili direttamente
```

## 3.2 LLM backends

`model.provider` seleziona il backend. Gli schemi degli strumenti (tool), la conversione dei messaggi e i percorsi nativi o di fallback sono gestiti in `llm/base.py`; pertanto, cambiare provider non richiede modifiche all'infrastruttura di esecuzione (harness).

Il native tool calling è l'impostazione predefinita per tutti e quattro i backend. Se un modello rifiuta tale modalità (restituendo un errore HTTP 400, 404 o 422), l'agente passa al protocollo su JSON testuale per l'intera sessione; si può forzare l'uso del protocollo testuale impostando `model.native_tools: false` o passando l'argomento `--no-native-tools`.

| provider   | trasporto                    | chiave API             |
|------------|------------------------------|------------------------|
| `ollama`   | nativo `/api/chat`           | nessuna                |
| `deepseek` | REST compatibile con OpenAI  | `DEEPSEEK_API_KEY`     |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

I nomi dei modelli attualmente supportati per DeepSeek sono `deepseek-flash` (predefinito) e `deepseek-v4-pro`; il vecchio `deepseek-chat` non è più accettato. Il live test usa `deepseek-flash`, a meno che non venga sovrascritto dalla variabile `HAGAR_LIVE_DEEPSEEK_MODEL`. Lo script `tools/diagnose_deepseek.py` consente di verificare il DNS, il formato della chiave e l'endpoint, senza mostrare la chiave stessa.

Le chiavi vengono lette solo da variabili d'ambiente e mai dal file YAML. Se il nome predefinito della variabile non è adatto alle proprie esigenze, si può specificarne un altro con `model.api_key_env`. Il parametro `model.host` indica l'URL di base del provider (con un valore predefinito specifico per ciascuno; ad esempio, Ollama usa `http://localhost:11434`), mentre `model.max_tokens` si applica solo a Claude (con un valore predefinito di 1024). 

```yaml
model:
provider: gemini
name: gemini-2.0-flash
```

Ogni backend normalizza il dialogo secondo il proprio formato: Claude riceve i messaggi di sistema nel campo dedicato `system` e i turni alternati, mentre Gemini riceve `systemInstruction` e il ruolo `model`. Il protocollo condiviso tra l'agente e il client utilizza esclusivamente i ruoli `user` e `assistant`.

## 3.3 Log di audit

Ogni sessione aggiunge voci in formato JSON Lines al percorso specificato in `audit.path` (valore predefinito: `logs/audit.jsonl`, risolto relativamente al file di configurazione):

```yaml
audit:
enabled: true
path: logs/audit.jsonl
max_field_chars: 2000
```

Eventi registrati: `harness.start`, `turn.start`, `llm.tool_choice`, `llm.protocol_error`, `llm.repaired`, `llm.repair_failed`, `tool.call`, `tool.result`, `turn.answer`, `turn.error`, `turn.stop`, `mcp.loaded`, `mcp.failed`, `llm.failed`, `harness.stop`. L'assenza di un evento `harness.stop` nell'ultima sessione indica che il processo è stato terminato forzatamente o è andato in crash.

Ogni record include un timestamp UTC, l'ID della sessione e, ove pertinente, un ID del turno condiviso da tutti gli eventi relativi a una singola richiesta. Il troncamento dei dati è regolato dal parametro `audit.max_field_chars`; le chiavi API non vengono mai scritte nel log.

Il log è concepito per essere consultato in seguito a un incidente, non per essere letto dal modello. Poiché può contenere il contenuto di file letti tramite gli strumenti di accesso al file system, deve essere trattato con la stessa cautela riservata all'area di lavoro (workspace) stessa.

## 3.4 Autorizzazioni e `policy.yaml`

Ogni chiamata a uno strumento viene autorizzata prima della sua esecuzione. Uno strumento dichiara le proprie
**capability** (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`,
`FILESYSTEM_CREATE`, `FILESYSTEM_DELETE`, `MEMORY_READ`,
`MEMORY_WRITE`, `MCP_CALL`, ...); un **soggetto** (l'agente) definisce
regole che associano tali funzionalità a `allow` (consenti), `ask` (chiedi) o `deny` (nega),
eventualmente circoscritte in base al nome dello strumento, al prefisso del percorso o allo spazio dei nomi.

```yaml
version: 1
subjects:
assistant:
default: deny
rules:
- capabilities: [FILESYSTEM_READ]
effect: allow
tools: ["filesystem.*"]
- capabilities: [FILESYSTEM_WRITE, FILESYSTEM_CREATE]
effect: ask
paths: ["note"]
```

L'opzione `ask` genera una richiesta nella console del tipo `lo faccio? (y/N)` (con valore predefinito `N`); il protocollo `ConfirmationProvider` permette inoltre di implementare una finestra di dialogo modale in un'interfaccia grafica (GUI). 
Il file delle policy viene letto prima della creazione dell'LLM: se risulta mancante o
non valido, ogni policy viene impostata su `DENY`, l'errore viene registrato nel log di controllo (`policy.failed`) e visualizzato nella chat, mentre l'harness continua a funzionare.

## 3.5 Memoria

Il sistema mantiene una memoria episodica della conversazione all'interno del vault di Obsidian
(`<vault>/Hagar/chat/`) e inserisce gli ultimi `memory.context_turns` in ogni prompt. Il modello può salvare memorie persistenti tramite
`memory.create_skill` (archiviate come `candidate` con indicazione della provenienza),
elencarle con `memory.list_skills` e consultare i passaggi precedenti
tramite `memory.get_context`.

```yaml
memory:
enabled: true
vault_subdir: Hagar
context_turns: 10
max_skill_chars: 4000
```

Se il vault è assente o non accessibile in scrittura, la funzionalità di memoria viene disabilitata
con la generazione di un avviso, mentre il sistema continua a funzionare. Le scritture in memoria passano attraverso il motore delle policy (`MEMORY_READ`/`MEMORY_WRITE`; per impostazione predefinita, le operazioni di scrittura richiedono una conferma). Si veda ARCHITECTURE §3.11 per la struttura del vault.
---

# 4. Documentazione

HAGAR ha una documentazione in più lingue. Al momento le lingue supportate
sono: italiano, inglese, spagnolo, portoghese, cinese, russo. Ogni lingua ha la sua subdirectory dedicata in Docs.

- [MANUAL.md](MANUAL.md) — formato della configurazione, comandi da console, 
  opzioni da linea di comando, presupposti di base. 
- [ARCHITECTURE.md](ARCHITECTURE.md) — L'architettura software di questa 
  versione dell'harness: componenti, modello di sicurezza, limiti noti.
- [ROADMAP.md](ROADMAP.md) — Funzioni progettate da implementare, decisioni già prese
  e questioni ancora aperte.
- [CHANGELOG.md](CHANGELOG.md) — cronologia delle modifiche.
