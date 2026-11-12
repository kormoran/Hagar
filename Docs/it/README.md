<p align="center">
  <img src="../HAGAR.jpg">
</p>

[Italiano](../it/README.md) · [English](../en/README.md) · [Español](../es/README.md) · [中文](../zh/README.md) · [Русский](../ru/README.md) · [Português](../pt/README.md) · [العربية](../ar/README.md)

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

`pip install -e .` dichiara i pacchetti `core`, `llm`, `memory` e
`local_tools` e installa il comando `hagar`:

```powershell
hagar --config hagar.yaml
hagar --model qwen3:8b
hagar --no-memory
hagar --no-native-tools
hagar --version

# GUI web locale
hagar web
hagar --config hagar.yaml web --port 8765
```

La GUI web usa `http://127.0.0.1:8765/`, un token casuale per le API,
conferme ASK modali, stop del turno, upload immagini, tab per chat,
cronologia, tool output, audit, thinking e memorie, e token cumulati
della sessione nella sidebar. Per i dettagli vedi `MANUAL.md` §3.0.

La configurazione viene cercata nell'ordine seguente: parametro `--config`,
variabile d'ambiente `HAGAR_CONFIG` e infine file `./hagar.yaml`.
È inoltre possibile utilizzare `python -m hagar` lavorando direttamente sul codice sorgente.

## 3.1 Layout

```
hagar.py            Script di lancio dell'harness
hagar.yaml          Script di configurazione predefinito
policy.yaml			Configurazione dei permessi per i tool (integrati ed MCP)
core/               config, agent, audit log, registry, sandbox, service e web server
llm/                LLM backends (Ollama, LM Studio, DeepSeek, OpenAI, Claude, Gemini), client MCP
memory/             memoria SQLite (sqlite_store.py) e backend markdown legacy
web/                HTML, CSS e JavaScript della GUI locale
tests/              suite pytest
tools/              helper di sviluppo (test runner, sandbox shim, model benchmark)
local_tools/        tool integrati; i built-in passano da local_tools/plugins.py
core/plugins.py     contratti e scoperta dei plugin (hagar.tools, hagar.llm)
core/subagents.py   manager del subagente MVP sincrono e read-only
llm/plugins.py      provider LLM built-in registrati come plugin
```

## 3.2 LLM backends

`model.provider` seleziona il backend. Gli schemi degli strumenti (tool), la conversione dei messaggi e i percorsi nativi o di fallback sono gestiti in `llm/base.py`; pertanto, cambiare provider non richiede modifiche all'infrastruttura di esecuzione (harness).

Il native tool calling è l'impostazione predefinita per tutti i backend. Se un modello rifiuta tale modalità (restituendo un errore HTTP 400, 404 o 422), l'agente passa al protocollo su JSON testuale per l'intera sessione; si può forzare l'uso del protocollo testuale impostando `model.native_tools: false` o passando l'argomento `--no-native-tools`.

| provider   | trasporto                    | chiave API             |
|------------|------------------------------|------------------------|
| `ollama`   | nativo `/api/chat`           | nessuna                |
| `lmstudio` | OpenAI-compatibile locale    | nessuna (opzionale)    |
| `deepseek` | REST compatibile con OpenAI  | `DEEPSEEK_API_KEY`     |
| `openai`   | OpenAI Chat Completions      | `OPENAI_API_KEY`       |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

`chatgpt` è un alias di `openai`. L'abbonamento ChatGPT non dà accesso all'API: servono una chiave OpenAI e credito API. LM Studio deve avere il server locale attivo e un modello caricato; l'endpoint predefinito è `http://localhost:1234/v1`. Se il server LM Studio richiede una chiave, si può impostare `LMSTUDIO_API_KEY` o `model.api_key_env`; altrimenti non serve.

Con LM Studio il tool calling nativo dipende dal modello e dal suo template: alcuni modelli accettano la richiesta ma rispondono in testo invece di emettere `tool_calls`. In quel caso usare `model.native_tools: false` (protocollo JSON testuale) o un modello tool-capable.

I nomi dei modelli attualmente supportati per DeepSeek sono `deepseek-flash` (predefinito) e `deepseek-v4-pro`; il vecchio `deepseek-chat` non è più accettato. Il live test usa `deepseek-flash`, a meno che non venga sovrascritto dalla variabile `HAGAR_LIVE_DEEPSEEK_MODEL`. Lo script `tools/diagnose_deepseek.py` consente di verificare il DNS, il formato della chiave e l'endpoint, senza mostrare la chiave stessa.

Le chiavi vengono lette solo da variabili d'ambiente e mai dal file YAML. Se il nome predefinito della variabile non è adatto alle proprie esigenze, si può specificarne un altro con `model.api_key_env`. Il parametro `model.host` indica l'URL di base del provider (con un valore predefinito specifico per ciascuno; ad esempio, Ollama usa `http://localhost:11434` e LM Studio `http://localhost:1234/v1`), `model.timeout` è il timeout HTTP in secondi (default 120) e `model.max_tokens` si applica solo a Claude (con un valore predefinito di 1024).

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

La memoria è un database SQLite locale e rappresenta la fonte di verità:
sessioni, turni, skill e summary. Il modello può salvare memorie con
`memory.create_skill`, elencarle con `memory.list_skills` e consultare i
passaggi precedenti con `memory.get_context`.

```yaml
memory:
  enabled: true
  backend: sqlite
  context_turns: 10
  max_skill_chars: 4000
```

Il database predefinito è `%LOCALAPPDATA%/Hagar/memory.db` (oppure
`HAGAR_MEMORY_DB`). Il backend `markdown` resta solo per compatibilità.
Le scritture passano dal motore delle policy. I comandi `/memory` di CLI
permettono di ispezionare chat, skill e statistiche.

## 3.6 Decision tool

`decision.choose` pone una domanda a scelta fissa e restituisce label,
probabilità e provider. Supporta un LLM decisore (locale o remoto) e un
classificatore lineare locale. Dettagli in [DECISIONS.md](DECISIONS.md).

## 3.7 Schede e benchmark dei modelli

`/models test` misura latenza, JSON strutturato e tool calling e salva
una scheda JSON con hardware e data dell'ultima prova. Dettagli in
[MODEL_CARDS.md](MODEL_CARDS.md).

## 3.8 Modalità Hi-Fi

Con `--hifi` Hagar chiede al modello tre interpretazioni della richiesta
e, se le due più probabili sono troppo vicine, chiede un chiarimento
invece di rispondere. Dettagli in [HIFI.md](HIFI.md).

## 3.9 Checkpoint, timeout e contesto

Hagar salva un checkpoint dei file modificati nel turno, limita le
chiamate ai tool, spilla gli output grandi e pota il contesto vecchio.
Dettagli in [RUNTIME_GUARDS.md](RUNTIME_GUARDS.md).

## 3.10 AIsh

`aish.exec` è una shell semantica ristretta: i comandi vengono tradotti
in tool Hagar, non eseguiti come programmi. È **DENY di default** e va
abilitata esplicitamente in `policy.yaml`. Dettagli in [AISH.md](AISH.md).
Le trasformazioni testuali usano [text.transform](TEXT_TRANSFORM.md).

## 3.11 Ricette di sviluppo

`dev.run` esegue ricette fidate per test, debug e build, senza shell e
senza comandi arbitrari. È **DENY di default** e richiede `DEV_EXEC`.
Dettagli in [DEV_RUN.md](DEV_RUN.md).

## 3.12 Boxed transform

`box.run` esegue trasformazioni LLM bounded (`summarize`, `translate`,
`extract_json`) senza memoria, tool o prompt libero. È **DENY di default**
e richiede `BOX_EXEC`. Dettagli in [BOXES.md](BOXES.md).

## 3.13 Hagar Flow

`flow.run` esegue un sottoinsieme lineare di Python validato e
interpretato da Hagar, senza import, funzioni, try o accesso a oggetti
Python. È **DENY di default** e richiede `FLOW_EXEC`. Dettagli in
[FLOW.md](FLOW.md).

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
- [PLUGINS.md](PLUGINS.md) — contratti per tool e provider LLM plugin.
- [HIFI.md](HIFI.md) — pre-pass di interpretazione e chiarimento.
- [RUNTIME_GUARDS.md](RUNTIME_GUARDS.md) — checkpoint, timeout, spill e compaction.
- [AISH.md](AISH.md) — shell semantica ristretta e policy DENY.
- [TEXT_TRANSFORM.md](TEXT_TRANSFORM.md) — trasformazioni testuali bounded.
- [DEV_RUN.md](DEV_RUN.md) — ricette per test, debug e build.
- [BOXES.md](BOXES.md) — trasformazioni LLM bounded.
- [FLOW.md](FLOW.md) — DSL ristretto e interprete.
- [DECISIONS.md](DECISIONS.md) — tool decisionali e provider.
- [MODEL_CARDS.md](MODEL_CARDS.md) — schede, benchmark e hardware.
- [BROKER.md](BROKER.md) — catalogo modelli e futuro broker LLM.
- [DOCUMENT_TOOL.md](DOCUMENT_TOOL.md) — specifica del document tool,
  grafo semantico, plugin di formato e host nativo.
- [SUBAGENTS.md](SUBAGENTS.md) — MVP subagenti, isolamento e limiti.
- [CHANGELOG.md](CHANGELOG.md) — cronologia delle modifiche.
