# HAGAR — Architettura

Versione: 0.5.2
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
  │     ├── LMStudioClient
  │     ├── DeepSeekClient
  │     ├── OpenAIClient
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
| `model` | sì | provider, nome, host, timeout, max_tokens, api_key_env, native_tools |
| `vault` | sì | percorso del vault Obsidian |
| `filesystem` | sì | `sandbox`: lista di `{alias, path, permissions}`; `limits`: budget di scrittura |
| `permissions` | no | read, write, shell, network (default `true/false/false/false`) |
| `rag` | no | `top_k` (default 8) |
| `mcp_servers` | no | endpoint, namespace, auth (bearer/header/oauth) |
| `audit` | no | enabled, path, max_field_chars, max_bytes, max_files, include_outputs |
| `policy` | no | path del file policy, subject |
| `memory` | no | enabled, vault_subdir, context_turns, context_skills, max_skill_chars |

Errori di validazione producono sempre `ConfigError`, con un messaggio che
indica il campo. Il percorso dell'audit, se relativo, viene risolto
rispetto al file di configurazione.

## 3.2 Interfaccia LLM e backend (`llm/`)

`LLMClient` ha due percorsi:

- **calling nativo** (predefinito): `native_step()` invia gli schemi dei
  tool nel formato del provider e legge le chiamate dalla risposta;
- **protocollo JSON testuale** (fallback): `request_tool_call()` chiede un
  JSON con `tool`/`arguments`, con parsing robusto e un tentativo di
  riparazione.

Lo schema dei parametri è costruito da `ToolDefinition`:
OpenAI/Ollama usano `tools[].function`, Claude `tools[].input_schema`,
Gemini `functionDeclarations`. La conversazione canonica usa i ruoli
`user`/`assistant`/`tool`; ogni client la traduce (OpenAI `tool_calls`,
Claude blocchi `tool_use`/`tool_result`, Gemini `functionCall`/
`functionResponse`). Un rifiuto HTTP 400/404/422 produce
`NativeToolsUnavailable`: l'Agent passa al protocollo testuale solo se non
ha ancora eseguito tool.

I nomi dei tool vengono normalizzati per le API che non ammettono il
punto (`filesystem.read_file` → `filesystem__read_file`) e riportati al
nome interno nella risposta: policy, audit e test vedono sempre il nome
originale.

Il testo resta il fallback per modelli che non supportano i tool nativi;
`model.native_tools: false` lo forza (o `--no-native-tools` da CLI).

| provider | API | chiave | note |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | host default `localhost:11434` |
| `lmstudio` | `/v1/chat/completions` (OpenAI) | opzionale `LMSTUDIO_API_KEY` | host default `localhost:1234/v1` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `openai` / `chatgpt` | `/v1/chat/completions` | `OPENAI_API_KEY` | ChatGPT via API, non abbonamento |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system separato, turni alternati |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, ruolo `model` |

La chiave si legge solo dall'ambiente; `model.api_key_env` sovrascrive il
nome predefinito. `model.host` è la base URL di tutti i provider (con un
default per provider), `model.timeout` è il timeout HTTP (default 120),
`model.max_tokens` è usato solo da Claude.
`llm/factory.py` costruisce il client e rifiuta provider sconosciuti o
chiavi mancanti. I provider built-in sono spec in `llm/plugins.py`; un
provider esterno si registra con l'entry point `hagar.llm` e una factory
`(config, audit) -> LLMClient` (vedi `PLUGINS.md`). LM Studio non
richiede chiave salvo configurazione del server; OpenAI richiede una
chiave API, non un abbonamento ChatGPT.
DeepSeek: i modelli correnti sono `deepseek-flash` e
`deepseek-v4-pro`; `deepseek-chat` non è più accettato.

Stato attuale: **calling nativo v1** con fallback testuale automatico
(vedi ROADMAP).

## 3.3 Modello dei tool (`core/tool_*.py`)

`ToolDefinition` descrive nome, descrizione, categoria, parametri,
handler, `origin` (`local` oppure `mcp.<namespace>`), le `capabilities`
dichiarate, lo stato di abilitazione e `requires_confirmation`
(pavimento di ASK applicato dal registry).

`ToolCall` è la richiesta del modello (`tool`, `arguments`, `id`);
`ToolResult` è l'esito strutturato (`tool_name`, `success`, `output`,
`error`).

`ToolRegistry` registra, cerca, abilita/disabilita ed esegue i tool;
espone i metadati al modello ed è l'unico punto di esecuzione.

## 3.4 Agent (`core/agent.py`)

Ciclo agentico multi-step, con due percorsi:

- **nativo**: una risposta può contenere più chiamate; l'Agent riaccoda
  il messaggio `assistant` e un messaggio `tool` con l'id per ogni
  risultato;
- **testuale**: una chiamata per volta, con il risultato inviato come
  turno `user`.

In entrambi:

1. il modello decide se serve un tool;
2. se non serve, la risposta finale chiude il turno;
3. se serve, il tool viene eseguito e il risultato torna al modello;
4. il limite `max_tool_calls` vale per l'intero turno. Se il modello
   insiste, il turno si chiude con `Agent stopped after N tool calls`
   (protezione dai loop).

Se il primo passo nativo fallisce con `NativeToolsUnavailable`, l'Agent
passa al protocollo testuale (`llm.native_fallback`); un errore dopo che
un tool è stato eseguito chiude il turno con `turn.error`, senza
fallback.

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

**I symlink non esistono per la sandbox.** Hagar non li mostra, non li
legge, non li segue e non li cancella: `stat`, `list_dir` e `search` li
ignorano; `read_file`, `read_chunk` e `delete_file` rispondono “not
found”; `chdir` su un symlink risponde “Directory not found”. Un link
rotto o verso l'esterno è indistinguibile da un percorso inesistente.

La radice virtuale del sandbox è `/home/ai`; ogni directory configurata
è esposta come `/home/ai/<alias>`. `stat`, `list_dir`, `search`,
`read_chunk`, i messaggi di `write`/`create`/`mkdir`/`delete` e `chdir`
mostrano solo percorsi virtuali: il percorso fisico non compare mai
nell'output del modello. Un input `/home/ai/<alias>/...` viene risolto
contro la directory fisica dell'alias; i percorsi relativi restano
relativi alla directory corrente.

`/home/ai` è una directory sintetica: si può listare e statare, ma non
è un mount e non è possibile farci `chdir`. Le voci di
`filesystem.sandbox` restano path del sistema ospite, assoluti o con
`~` se l'utente lo sceglie: può essere qualsiasi directory esistente e
raggiungibile. Hagar non crea directory e non presuppone una home
dedicata.

```yaml
filesystem:
  sandbox:
    - alias: documenti
      path: C:\Users\pippo\Documenti
      permissions: RWX
    - alias: ebooks
      path: D:\ebooks
      permissions: R
```

Non esiste un flag `enabled`: ogni voce valida di `filesystem.sandbox`
viene montata. Alias o permessi invalidi, path mancante o path duplicato
fermano la configurazione. I path fisici e i nomi interni possono
contenere spazi; l'alias no, perché deve restare un singolo segmento
virtuale.

`R` copre lettura, elenco, ricerca e `stat`; `W` copre scrittura,
creazione, rinomina, copia e cancellazione; `X` copre `chdir`. I
permessi globali `permissions.read`/`write` restano un tetto: un alias
`RWX` non può superarli.

## 3.6 Tool filesystem (`core/filesystem_tools.py`)

```text
filesystem.read_file
filesystem.write_file
filesystem.create_file
filesystem.delete_file
filesystem.mkdir
filesystem.chdir
filesystem.list_dir
filesystem.read_chunk
filesystem.rename
filesystem.copy_file
filesystem.search
filesystem.free_space
filesystem.stat
```

`list_dir` restituisce metadati `FileInfo`; `read_chunk` legge per byte
con `has_more`, `next_offset` e confini UTF-8 completi; `search` usa un
glob ricorsivo con limite di risultati; `copy_file` richiede `create`;
`rename` richiede `rename` sulla sorgente e `create` sulla destinazione.
I percorsi restituiti sono sempre virtuali (`/home/ai/<alias>/...`).
`chdir` richiede `X` sull'alias.

`list_dir` restituisce al massimo 100 voci per pagina (`limit` massimo
500) con `offset`, `next_offset` e `has_more`; se ci sono altre voci il
`message` dice `voci: riportate X di Y; per continuare usa offset=Z`.
`search` usa la stessa paginazione: `max_results` è il limite di pagina
(default 100, massimo 500), `offset` scorre i risultati. Per alberi
grandi conviene restringere `pattern`/`path` invece di iterare molte
pagine. `read_file` accetta solo file fino a `CHUNK_SIZE` (4096 byte);
oltre, l'errore rimanda a `read_chunk()` perché leggere tutto il file
supererebbe la context window. `read_chunk` restituisce `next_offset` e
confini UTF-8 completi.

`list_dir` e `search` non mostrano i symlink; `read_file` e `read_chunk`
li trattano come file inesistenti.

`write_file` sovrascrive solo file esistenti; la creazione passa da
`create_file`, che richiede il permesso `create`. Non è possibile
aggirare il divieto di creazione scrivendo un percorso nuovo.

### Limiti di scrittura

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = disabilitato
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` è il massimo per singola operazione di
  `write_file`, `create_file` o `copy_file`;
- `min_free_bytes` è la riserva di spazio che deve restare dopo
  l'operazione;
- `session_write_bytes` è il budget cumulativo della sessione;
- `ask_over_bytes` alza a `ASK` le operazioni sopra soglia. Il preflight
  è integrato in `ToolRegistry`: se anche la policy dice `ASK`, la
  conferma è una sola.

`0` disabilita il singolo limite. Superare `max_write_bytes`,
`session_write_bytes` o la riserva produce un errore, non una conferma:
sono invarianti, non domande. `ask_over_bytes` è l'unico livello che
chiede all'utente.

`filesystem.stat` restituisce JSON con `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. Un percorso inesistente non è un errore:
`exists: false` con i permessi applicabili.

## 3.7 MCP (`llm/mcp_client.py`)

Client MCP via HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
conversione automatica dei tool in `ToolDefinition` e registrazione con
namespace `mcp.<namespace>`.

Supporta anche risposte `text/event-stream` (streamable HTTP) e invia
la notifica `notifications/initialized` dopo l'handshake. Usa
`MCP-Protocol-Version` (default `2025-06-18`, con fallback) e riusa
`Mcp-Session-Id` quando il server lo restituisce. Gli errori HTTP
includono il corpo della risposta per rendere diagnosticabili i 400.
I risultati dei tool vengono normalizzati a testo: blocchi `text`,
altrimenti `structuredContent` o JSON; un risultato con `isError`
diventa un errore del tool.

Autenticazione per server:

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer          # oppure "header"
      token_env: MCP_EXAMPLE_TOKEN
      # header: X-API-Key  # solo con type: header
```

Il token si legge solo dall'ambiente e non compare nell'audit. Se manca,
il server viene saltato con `mcp.failed` e il harness continua; gli altri
server restano disponibili.

### OAuth interattivo

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # senza, dynamic registration
    # client_secret_env: MCP_CLIENT_SECRET
    scopes: [mcp.read]
    audience: api.atlassian.com  # opzionale, per provider 3LO
    redirect_port: 8765       # 0 = porta casuale
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

Flusso authorization code + PKCE, con callback su
`http://localhost:<port>/oauth/callback` e apertura del browser. Se lo
scope contiene `offline_access`, viene aggiunto `prompt=consent`.
I metadata vengono scoperti da `.well-known` (RFC 9728 per la
risorsa, RFC 8414 per l'authorization server); se `client_id` manca si
usa la registrazione dinamica. I token sono in un file locale con
permessi ristretti (`0600` dove il sistema li supporta), con refresh
automatico e retry una volta su `401`.

Ctrl-C durante l'attesa del callback chiude il server locale ed esce
con codice 130, senza traceback.

Limiti: niente device flow, DPoP, mTLS o client assertion; il browser deve
poter raggiungere il callback locale. Se il callback non arriva, il
terminale chiede di incollare l'URL di reindirizzamento.

## 3.8 Vault (`memory/vault.py`)

Accesso al vault Obsidian con percorsi relativi alla radice e
protezione dall'uscita dal vault. Offre lettura, scrittura, append,
elenco dei file e `load_all` per la lettura ricorsiva. La semantica
della memoria vive in `memory/store.py` (§3.11).

## 3.9 Audit log (`core/audit.py`)

File JSON Lines append-only. Ogni riga ha timestamp UTC, `session` ed
`event`; gli eventi di una stessa domanda condividono un `turn` id.

```text
harness.start      provider, modello, radici, permessi, tool, vault
turn.start         domanda, limite tool, modalità nativa
llm.tool_choice    scelta del modello, argomenti, mode=native
llm.native_fallback provider senza tool nativi, passaggio al testo
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
memory.enabled     radice, subdir, turni di contesto
memory.disabled    motivo della disattivazione
memory.context     turni e skill iniettati nel prompt
memory.turn        turno salvato nel vault
memory.failed      fase ed errore
```

Proprietà:

- scrittura best effort: un errore di I/O non ferma il harness e viene
  segnalato una sola volta su stderr;
- troncamento configurabile (`audit.max_field_chars`, default 2000);
- catena di hash (`prev`/`hash`) verificabile con `verify_chain`;
- rotazione in `<file>.<timestamp>` oltre `audit.max_bytes` (0 disattiva);
- retention: `audit.max_files` (default 100) tiene al massimo N file,
  incluso quello attivo; i backup più vecchi vengono eliminati;
- con `audit.include_outputs: false` l'output dei tool viene registrato
  solo come dimensione;
- valori non JSON resi serializzabili;
- nessuna chiave API nel log;
- il log contiene anche l'output dei tool (quindi contenuti di file):
  va protetto come il workspace.

## 3.10 Permessi (`core/permissions.py`)

Il modello è una matrice soggetto × oggetto:

- **Capability** (`IntFlag`): cosa un'operazione può fare
  (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`, `FILESYSTEM_CREATE`,
  `FILESYSTEM_DELETE`, `FILESYSTEM_EXEC`, `MEMORY_READ`,
  `MEMORY_WRITE`, `NETWORK`, `MCP_CALL`, `COMPUTE`). Si combinano con `|`;
  la verifica è sempre di sottoinsieme.
- **Effect** (`IntEnum`): `ALLOW`, `ASK`, `DENY`. In caso di conflitto
  vince il valore più alto (`DENY > ASK > ALLOW`).
- **Rule**: capability + effetto + filtri opzionali `tools` (glob),
  `paths` e `namespaces` (prefissi) + `reason`.
- **Subject**: chi chiede (agente, utente, sistema), con regole e
  default (`DENY` se non specificato).
- **Resource**: l'oggetto della decisione (per ora un tool con le sue
  capability; in futuro anche note e percorsi).
- **Decision**: effetto, motivo e regola applicata.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. la risorsa deve offrire le capability richieste;
2. il **tetto di sistema** (derivato da `permissions.read/write/shell`)
   deve concederle;
3. per ogni capability si applicano le regole del soggetto: vince la
   più specifica (numero di filtri, poi lunghezza del prefisso), a
   parità l'effetto più restrittivo; senza regole vale il default;
4. con più capability richieste vale l'AND: l'effetto peggiore vince.

`ASK` non è una decisione: è una domanda a un umano. Il
`ConfirmationProvider` la pone — `ConsoleConfirmation` chiede
`lo faccio? (y/N)` con default N — e senza canale di conferma vale
`DENY`. Una GUI può implementare lo stesso protocollo con un dialog
modale.

In CLI `core/input_broker.py` è l'unico proprietario della console:
distribuisce prompt, conferme e i tasti `F5`/`F8`, imposta il titolo del
terminale come segnale di attenzione e ripristina la modalità normale alla
fine. Su stdin non interattivo ricade su `input()`.

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
      - capabilities: [COMPUTE]
        effect: allow
        tools:
          - "calculator.*"
          - "statistics.*"
          - "units.*"
          - "clock.*"
          - "calendar.*"
          - "think.*"
          - "text.*"
          - "url.*"
      - capabilities: [NETWORK]
        effect: ask
        tools: ["feed.*"]
```

`policy.yaml` viene letto **prima** di costruire il LLM. Se non è
leggibile o non è valido, il harness applica `DENY` a tutte le policy,
lo registra nell'audit (`policy.failed`) e lo segnala in chat; il resto
del harness continua a funzionare. Anche un soggetto assente degrada a
`DENY`.

Il controllo avviene in `ToolRegistry.execute`, unico punto di
esecuzione, e produce gli eventi `permission.decision` e
`permission.confirmation`.

Lo scope `paths` confronta il percorso **scritto dal modello**
(normalizzato), non quello risolto dalla sandbox: un percorso assoluto o
un `chdir` possono non corrispondere a un prefisso relativo, e il
risultato resta `DENY` (fail closed).

## 3.11 Memoria (`memory/store.py`, `memory/tools.py`)

**Backend predefinito: SQLite.** `memory/sqlite_store.py` e
`memory/database.py` usano un database locale (`%LOCALAPPDATA%/Hagar/memory.db`
o `HAGAR_MEMORY_DB`) come fonte di verità per sessioni, turni, skill e
summary. SQLite usa WAL, transazioni e `busy_timeout`; il backup è
`VACUUM INTO`. Il backend `markdown` descritto sotto resta disponibile
solo per compatibilità e non è più il default.

**Episodica.** L'harness accoda ogni turno concluso in una nota per
sessione:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter con `session`, `type: chat`, `created`; corpo con una
sezione per turno (`## <timestamp> · <turn>`), domanda e risposta. Non
vengono salvati gli output dei tool: quelli restano nell'audit.

All'inizio di ogni turno l'Agent inietta nel prompt gli ultimi
`memory.context_turns` turni (0 disattiva l'iniezione), troncando
domanda e risposta. Con `memory.context_skills > 0` aggiunge fino a N
**skill confermate** pertinenti alla domanda, per match lessicale su
titolo, tags e contenuto; le candidate e le archiviate non entrano mai.
Il blocco è etichettato come dati, non istruzioni. Un errore di memoria
non ferma il turno: viene registrato `memory.failed`.

**Semantica.** Il modello può proporre una memoria con tre tool:

| tool | capability | namespace |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

`create_skill` scrive `<vault>/Hagar/skills/<slug>.md` con frontmatter
`id`, `title`, `kind` (`fact`/`procedure`), `status: candidate`, `tags`,
`source_session`, `source_turn`, `model`, `created_at`. Lo slug è
sicuro (solo ASCII, nessun percorso); un titolo già esistente non viene
sovrascritto e restituisce `duplicate: true`.

`get_context` restituisce gli ultimi turni o cerca per parola chiave
nelle sessioni passate; `list_skills` filtra per `kind` e `status`.

**Ciclo di vita.** Gli stati sono `candidate`, `confirmed`, `archived`.
L'LLM crea solo candidate; la transizione è umana, da CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` mostra una candidate alla volta con provenance e
contenuto, poi chiede `y/N/a/s/q` (conferma, lascia, archivia, salta,
esci). La conferma scrive `reviewed_at`; `archive` è reversibile con
`confirm`. Ogni transizione produce `memory.status` o `memory.review`
nell'audit. Le note restano file Obsidian: modificare `status` nel
frontmatter ha lo stesso effetto.

**Configurazione**:

```yaml
memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  context_project_memories: 10
  max_context_chars: 6000
  project_max_active: 200
  summary_max_chars: 4000
  max_skill_chars: 4000
```

### Memoria di progetto

La memoria di progetto è separata dalle skill:

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

Ogni progetto ha un `index.md` con stato, ultima attività, summary e
conteggio delle decisioni attive. Ogni decisione ha stato
`candidate`/`active`/`superseded`/`archived`, alternative, motivazione,
provenance e `auto_saved`. Le decisioni non si riscrivono: una nuova
decisione può sostituirne una vecchia.

Con `memory.backend: sqlite` progetti e decisioni usano le tabelle
`projects` e `decisions` dello stesso database; il backend Markdown
legacy continua a usare il Vault.

All’avvio Hagar mostra i progetti attivi e “attività libera”:

```text
/project list
/project new <nome>
/project select <nome>
/project free
/project status
/project archive <nome>
/project unarchive <nome>
```

Gli override non interattivi sono `--project <nome>` e `--free`.

A fine sessione:

1. il transcript viene spostato in `archive/chat/`;
2. viene generato un summary con il modello, con fallback meccanico;
3. il summary viene salvato con link e hash del transcript;
4. se c’è un progetto, l’LLM propone decisioni `candidate`;
5. l’utente può rivederle; se rifiuta, restano `candidate` con
   `auto_saved: true`.

Il contesto iniettato usa l’**indice** del progetto: summary, titoli
delle decisioni attive e conteggio, non tutti i corpi. I dettagli si
leggono con `memory.project_context(query=..., limit=...)`. Il blocco
complessivo è limitato da `max_context_chars`; se viene tagliato,
l’audit registra `memory.context_trimmed`. Non è una stima di token: è
un budget in caratteri, deterministico.

Quando un progetto supera `project_max_active`, Hagar chiede se
archiviarlo. L’archiviazione è reversibile e non cancella nulla.

**Consultazione archivio.** I transcript archiviati hanno il `project`
nel frontmatter. La ricerca e la lettura sono on demand:

```text
/memory archive search <testo>
/memory archive read <session> [offset] [limit]
```

Gli stessi strumenti sono esposti come `memory.archive_search` e
`memory.archive_read`; la ricerca restituisce session, turn, timestamp,
progetto e snippet, la lettura pagina i turni. Non c’è iniezione
automatica dell’archivio nel prompt: il summary resta l’indice, il
transcript è la fonte da consultare quando serve.

Se `vault.path` non esiste o non è scrivibile, la memoria viene
disattivata con un avviso in chat e `memory.disabled` nell'audit; gli
altri componenti continuano a funzionare. Le scritture di memoria sono
soggette alle policy (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.11.1 Service layer (`core/service.py`)

`HarnessService` è l'API stabile sopra il `Harness`: non legge da
`input()`, non scrive su stdout e non conosce la CLI. Espone:

- `ask(question)` con eventi `turn.start`, `turn.answer`, `turn.error`;
- eventi tool e permessi inoltrati da `Agent` e `ToolRegistry`:
  `tool.call`, `tool.result`, `permission.decision`,
  `permission.confirmation`;
- `status()` con modello, progetto, memoria, audit, policy e tool;
- `list_projects()`, `current_project()`, `set_project()`,
  `clear_project()`, `create_project()`;
- `finish_session()`.

Gli eventi sono `ServiceEvent(type, data, ts)` e possono essere consumati
da un sink (CLI, GUI, test). La CLI attuale usa il service per i turni, la
selezione progetto e la chiusura sessione.

## 3.11.2 Command service (`core/command_service.py`)

`CommandService` trasforma i comandi slash in `CommandResult`:

```text
command, ok, lines, data, error, requires_input
```

Gestisce `/help`, `/tools`, `/status`, `/mcp`, `/audit`, `/project` e
`/memory` senza scrivere su stdout. La CLI stampa `lines`; la GUI userà
`data`. La review interattiva di `/memory` resta affidata a `MemoryCLI`
perché richiede input umano. La CLI usa il command service per tutti i
comandi slash, tranne `/memory review`.

## 3.11.3 Web GUI (`core/web.py`)

`hagar web` avvia un `ThreadingHTTPServer` locale con:

- `GET /` pagina chat;
- `GET /static/style.css` e `/static/app.js` (asset in `web/`);
- `GET /api/events` stream SSE;
- `POST /api/message`, `/api/confirm`, `/api/project`, `/api/stop`,
  `/api/new-chat`, `/api/resume`;
- `GET /api/status`, `/api/projects`, `/api/pending`;
- `GET /api/history`, `/api/history/<session>`;
- `GET /api/tools`, `/api/audit`, `/api/thinking`;
- `GET /api/memories`, `/api/memory?path=...`.

Le tab della GUI sono Chat, Chat history, Tool output, Audit, Thinking e
Memories. La sidebar tiene progetto, stato e token; la cronologia è nella
tab dedicata. `SessionLog` conserva gli eventi della sessione per Tool
output e timeline; Audit legge il JSONL; Thinking privilegia il
reasoning esposto dal provider e altrimenti mostra la timeline. Memories
legge l'indice, escludendo chat, archivio e summary.

Un click su una chat passata chiama `POST /api/resume`: il transcript
viene ricaricato e la sessione di audit/memoria torna a quell'id, così i
nuovi turni continuano la stessa chat. `POST /api/new-chat` chiama
`MemoryStore.new_session()` e cambia la sessione, senza toccare i
transcript precedenti.

Gli asset statici vivono in `web/` (`index.html`, `style.css`,
`app.js`). `render_index()` inietta solo il token; il resto è servito
verbatim con whitelist e `importlib.resources`.

La GUI è un adapter: usa `HarnessService`, `CommandService` e
`QueueConfirmationProvider`. Le conferme ASK bloccano il thread del turno
su un `threading.Event`; il server resta libero e sblocca la richiesta con
`POST /api/confirm`. Un timeout vale come rifiuto.

La sidebar mostra i token cumulati della sessione: `UsageLedger` riceve
l'usage da ogni chiamata LLM tramite `usage_sink` e pubblica
`usage.updated` su SSE.

**Stop:** `POST /api/stop` chiama `Agent.cancel()`; l'agente controlla
l'evento tra un passo e l'altro e solleva `AgentCancelled`. Il turno si
interrompe in modo cooperativo, non abortisce una richiesta HTTP già in
corso.

**Vision:** `POST /api/message` accetta `images` come data URL
PNG/JPEG/WebP (max 4, 10 MB ciascuna); il body JSON può arrivare a
64 MB. `core/images.py` valida e converte; `Agent.ask(question,
images=...)` costruisce content multimodale. Gli adapter
OpenAI-compatibili/LM Studio usano `image_url`; Claude usa blocchi
`image`; Gemini usa `inlineData`. LM Studio non accetta WebP
direttamente: la GUI lo converte in PNG. L'immagine non finisce nella
memoria Markdown né nell'audit.

Sicurezza: bind predefinito `127.0.0.1`, token casuale iniettato nella
pagina, header `X-Hagar-Token` per le API e `?token=` per SSE. Non è
multiutente e non espone ancora la modifica del Vault.

## 3.11.6 Vision input (`core/images.py`)

`ImageInput` valida data URL, MIME e dimensione; `Agent.ask` usa parti
canoniche (`text`, `image`) e ogni backend le traduce nel proprio
formato. Il testo dello stop e delle immagini è separato dal contenuto
persistente: la memoria conserva solo la domanda e la risposta.

`vision.open` legge un'immagine dalla sandbox, la valida con magic number
e la restituisce come `ToolResult.images`. Il ciclo `Agent` allega
l'immagine a un messaggio utente sintetico prima della chiamata
successiva, quindi il modello la vede senza ricevere base64 nel testo del
tool. Limiti: 4 immagini per turno, 10 MB per immagine, PNG/JPEG/WebP.
Il child può usare `vision.open` nel proprio workspace read-only.

L'audio non è implementato. Il canale allegati sarebbe riutilizzabile, ma
servono un contratto provider audio-native diverso, formati/decoder e una
scelta esplicita tra ASR e comprensione audio; è in roadmap senza
timeline.

`memory/export.py` esporta il database SQLite in Markdown:
`Hagar/chat/`, `Hagar/skills/`, `Hagar/summaries/`,
`Hagar/projects/<id>/index.md` e `decisions/`. La scrittura è atomica
(temp + `os.replace`) e il comando rifiuta una destinazione non vuota
senza `--force`.

`memory_fts` è una tabella FTS5 nello stesso database, con colonne
`entity`, `entity_id`, `kind`, `project`, `status`, `title`, `body`.
`SqliteMemoryIndex.search` usa `MATCH`, `bm25()` e `snippet()`; se FTS5
non è disponibile ricade su `LIKE`. `memory/import_markdown.py` importa
la stessa struttura con upsert e ricostruisce l'indice FTS.

## 3.11.4 Token usage (`core/usage.py`)

`TokenUsage` normalizza input, output, cache e reasoning. Funzioni
`usage_from_openai`, `usage_from_anthropic`, `usage_from_gemini` e
`usage_from_ollama` leggono i campi nativi delle risposte.

`LLMClient._set_usage()` aggiorna `last_usage` e chiama il `usage_sink`
del client. `HarnessService` possiede il `UsageLedger`, lo collega al
client e pubblica `usage.updated`; la GUI lo usa nella sidebar e `/usage`
lo legge da CLI. L'usage del provider è la
verità; una stima locale resta solo un fallback.

## 3.11.5 Memory index (`memory/index.py`)

`MemoryIndex` è un indice SQLite derivato dal Vault Markdown:

- tabelle `documents`, `meta` e `documents_fts` (FTS5);
- sync incrementale per hash/mtime/size;
- `rebuild()` ricostruisce da zero;
- ricerca con filtri `project`, `kind`, `status`;
- fallback `LIKE` se FTS5 non è disponibile;
- database nei dati locali dell'app, non nel Vault sincronizzato.

Il tool `memory.search` usa l'indice; `/memory reindex` e `/memory stats`
espongono manutenzione e stato. Con il backend predefinito SQLite la
fonte di verità è `memory.db`; il vecchio `MemoryIndex` resta solo per il
backend Markdown legacy.

## 3.11.7 Decision tools (`core/decisions.py`)

`DecisionRegistry` seleziona un `DecisionProvider` e `decision.choose`
espone la scelta al modello. I provider built-in sono:

- `llm`: chiede al client LLM un JSON con `choice` e `probabilities`,
  valida le label e normalizza le probabilità;
- `linear`: carica un modello JSON locale con label, pesi e bias e usa
  softmax per produrre le probabilità.

La capability `DECISION` è separata da `COMPUTE`, `NETWORK` e
`FILESYSTEM_*`; i dettagli e il formato del modello sono in
`DECISIONS.md`. Jev/Kev non sono ancora adapter nativi.

## 3.11.8 Hi-Fi (`core/hifi.py`)

`HiFiResolver` esegue un pre-pass prima del loop agentico:

1. chiede al modello le interpretazioni con probabilità;
2. normalizza e ordina le probabilità;
3. se il margine tra prima e seconda supera `hifi.margin`, sostituisce
   la richiesta con l'interpretazione scelta più il testo originale;
4. altrimenti chiede al modello una domanda di chiarimento.

L'evento `hifi.interpretations` registra le probabilità e l'eventuale
chiarimento. Un JSON non valido produce `hifi.failed` e il turno
prosegue senza pre-pass.

## 3.12 Avvio e packaging

Il progetto si installa con `pip install -e .` e dichiara i package in
`pyproject.toml`. L'entry point è `hagar = "hagar:main"`. La versione
corrente è `0.5.2`.

La configurazione d'esempio è `hagar.example.yaml`; `hagar.yaml` è un
file locale ignorato da git. Il Vault predefinito dell'esempio è
`./vault` e va creato prima dell'avvio.

```text
hagar --config PATH       file di configurazione
hagar --model NAME        sovrascrive model.name
hagar --project NAME      seleziona un progetto attivo
hagar --free              avvia in attività libera
hagar --no-memory         disattiva la memoria per la sessione
hagar --no-native-tools   usa il protocollo JSON testuale
hagar --version
```

La configurazione si cerca in quest'ordine: `--config`, variabile
`HAGAR_CONFIG`, `./hagar.yaml`. `python -m hagar` funziona dalla
directory del progetto.

La CI GitHub Actions esegue la suite su Linux, macOS e Windows con
Python 3.11/3.12/3.13, costruisce sdist e wheel, esegue `twine check` e
prova l'installazione del wheel. Il workflow `Release` parte da un tag
`v*`, verifica che il tag corrisponda alla versione del pacchetto e
crea la release GitHub con gli artefatti.

I test live sono esclusi dalla suite normale e si abilitano con
`--live`: verificano Ollama e i provider remoti (questi ultimi solo se
la chiave API è presente).

## 3.13 Tool locali (`local_tools/`)

Non sono server MCP: sono provider locali che registrano `ToolDefinition`
nel registry e vivono fuori dal core, in un package separato.

| modulo | tool | capability |
|---|---|---|
| `calculator` | `calculator.evaluate` | `COMPUTE` |
| `statistics` | `statistics.compute` | `COMPUTE` |
| `unit_converter` | `units.convert` | `COMPUTE` |
| `clock` | `clock.now` | `COMPUTE` |
| `calendar` | `calendar.date` | `COMPUTE` |
| `think` | `think.echo` | `COMPUTE` |
| `text` | `text.diff` | `COMPUTE` |
| `url` | `url.parse` | `COMPUTE` |
| `feeder` | `feed.read` | `NETWORK` |

- `clock.now` restituisce ora locale, data, fuso, offset UTC ed epoch.
- `calendar.date` converte la data locale, o una data ISO opzionale, nel
  calendario giuliano prolepticico o in quello islamico tabellare
  (Kuwaiti algorithm). Il calendario islamico tabellare può differire di
  un giorno da quelli basati sull'osservazione o su Umm al-Qura.
- `think.echo` restituisce esattamente la stringa ricevuta; serve a
  esternalizzare un passaggio intermedio nelle catene di ragionamento.
- `text.diff` restituisce un diff unificato tra due testi, con input
  massimo 20000 caratteri, output massimo 20000 e `context` 0..10. Non
  applica il diff.
- `url.parse` scompone scheme, host, porta, path, query e fragment senza
  DNS o rete; limita l'URL a 4096 caratteri e i parametri a 100. Se
  l'URL contiene credenziali, le redige nell'output.
- `clock`, `calendar`, `think`, `text` e `url` non accedono a filesystem
  o rete, e ricadono nella regola `COMPUTE` allow.
- Il calcolatore usa una whitelist AST, non `eval()`, con limiti su
  espressione, numero di nodi ed esponente.
- `feed.read` scarica con `requests` (timeout 15 s, massimo 5 MB), accetta
  solo URL http/https e usa `feedparser`; la policy `NETWORK` è `ask`.
- SSRF: ogni host viene risolto con `getaddrinfo` e ogni indirizzo deve
  essere globale; loopback, reti private, link-local, multicast e
  riservati sono rifiutati. I redirect non sono automatici: ogni
  `Location` viene rivalidata e si fermano dopo 3 salti. Un URL con
  credenziali viene rifiutato.
- `permissions.network: true` è necessario perché il tetto di sistema
  conceda `NETWORK`; `COMPUTE` è sempre nel tetto ma la policy può negarlo.
- `permissions.agents: true` è necessario per `AGENT_SPAWN`; la policy
  deve inoltre consentire `agent.*`.
- `local_tools` è dichiarato in `pyproject.toml` e installato con il
  progetto.

I tool built-in sono registrati da `local_tools/plugins.py` attraverso
lo stesso contratto `ToolPlugin` dei plugin esterni. I plugin esterni si
scoprono con l'entry point `hagar.tools` e ricevono un `PluginContext`.
Policy e sandbox restano nel registry: un plugin non può concedere
permessi. Un plugin guasto viene saltato e registrato in audit, senza
fermare gli altri.

## 3.14 Plugin

`core/plugins.py` definisce:

- `ToolPlugin` + `PluginContext` per i tool;
- `LLMProvider` per i provider LLM;
- scoperta via `importlib.metadata.entry_points`;
- isolamento degli errori e audit `plugin.loaded`/`plugin.error`.

I provider built-in sono in `llm/plugins.py` e vengono registrati prima
degli esterni. Un provider esterno non può sostituire un nome built-in.
I plugin Python sono trusted e girano in-process; per estensioni non
fidate il confine resta MCP o un processo separato. Il contratto completo
è in `PLUGINS.md`.

## 3.15 Subagenti asincroni

`core/subagents.py` implementa:

- `agent.spawn/status/wait/result/cancel` e `agent.run` sincrono;
- `reason` obbligatorio nello spawn, registrato in audit;
- capability `AGENT_SPAWN` separata: il figlio non la riceve e non può
  creare altri agenti;
- policy del figlio strettamente più restrittiva; policy uguali o più
  ampie vengono rifiutate con `SubagentPolicyError`;
- timeout a parete di 5 minuti, cooperativo, con stato `timed_out`;
- `agent_id` in tutti gli eventi audit del padre, del figlio e del
  registry;
- fino a due subagenti concorrenti;
- stesso modello locale ma client LLM separato;
- workspace temporaneo privato per ogni figlio;
- input copiati dal workspace del padre;
- outbox `artifact.put`/`artifact.put_file` e `mailbox.send` per il
  figlio;
- artifact store temporaneo (max 50 MB per artifact, 256 MB per turno)
  e mailbox in memoria (max 64 KB per messaggio);
- lettura bounded del padre con `artifact.read`, `artifact.list`,
  `mailbox.inbox/read/ack`;
- `artifact.save_to` copia l'intero artifact in un path scrivibile del
  sandbox del padre, senza passare dal contesto;
- capability `AGENT_DATA`;
- registry filtrato a `FILESYSTEM_READ`, `MEMORY_READ`, `COMPUTE` e
  `AGENT_DATA`;
- esclusione di `filesystem.chdir` e `agent.*`;
- nessuna scrittura di memoria;
- ASK del figlio inoltrate all'utente dal `ParentBridgeConfirmation`,
  timeout 180 secondi e DENY alla scadenza; il padre LLM non approva;
- usage separato;
- audit `agent.spawned/started/finished/cancelled/failed`;
- a fine turno, `artifact.discarded` per artifact non esportato, con
  motivo `unread` o `read_but_not_saved` e metadati senza contenuto;
- cleanup di workspace e job a fine turno.

`AuditLog.record` è serializzato con lock per le scritture concorrenti.
Non ci sono ancora export di artifact, budget token/tempo, annidamento o
GUI dedicata. I dettagli sono in `SUBAGENTS.md`.

---

# 4. Modello di sicurezza

- L'agente non vede il filesystem reale: solo percorsi risolti dentro la
  sandbox.
- Le operazioni passano solo dal `ToolRegistry`; nessuna shell host.
- I permessi sono dichiarati in configurazione e nelle policy, e sono
  applicati da sandbox e `PermissionEvaluator`; le radici annidate
  possono restringere i permessi.
- Gli errori sono dati: un rifiuto viene restituito al modello come
  risultato del tool, non nascosto.
- Ogni azione lascia una traccia nell'audit, con sessione e turno.

---

# 5. Sviluppo

- Suite: `./tools/run_tests.sh` (Linux/macOS) oppure
  `.\tools\run_tests.ps1` (Windows). Su Windows: 837 superati, 2 skip
  (symlink non disponibili senza Developer Mode). Su Debian Linux
  (2026-11-06): tutti i test verdi, inclusi i symlink (743 superati, 0
  skip). Dettagli e motivazione dello shim in README §3.1.
- Test live: `./tools/run_tests.sh --live` (Linux/macOS) oppure
  `.\tools\run_tests.ps1 --live` (Windows) — 9 test in più (Ollama;
  provider remoti se le chiavi sono presenti).
- Confronto modelli: `python tools/bench_models.py` (README §3.5).
- Confronto protocolli: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- La suite normale non tocca la rete: Ollama e MCP sono simulati.

## 5.1 Multipiattaforma

- I percorsi interni usano `pathlib.Path`; quelli mostrati all'agente
  usano sempre `/` e la radice virtuale `/home/ai`.
- `filesystem.sandbox` contiene path del sistema ospite, assoluti o con
  `~` se l'utente lo sceglie: `Path.expanduser()` risolve la home solo
  quando il path la usa. Non si presuppone che una home dedicata esista.
- Ogni mount ha un alias esplicito e unico (case-insensitive); il
  percorso fisico può stare su qualsiasi volume.
- `tools/run_tests.sh` è il runner POSIX; `tools/run_tests.ps1` e
  `tools/pytest_shim` servono solo alla sandbox Windows con token
  ristretto.
- L'unico ramo esplicitamente Windows rimasto è la data di creazione in
  `stat`: `st_birthtime` dove disponibile, altrimenti `st_ctime` su
  Windows; su Linux `created_at` può essere `None`.
- Le API esterne (OAuth, MCP, LLM) usano HTTP e `webbrowser`, non
  comandi di sistema.
- La CI GitHub Actions copre Linux, macOS e Windows su Python
  3.11/3.12/3.13; symlink, permessi dei token OAuth e callback loopback
  restano da verificare con test live, non nella suite offline.

---

# 6. Limiti noti e debito tecnico

- `PermissionEvaluator` copre la v1: restano i soggetti dinamici, le
  conferme GUI e le capability MCP assegnate dalla configurazione.
- Il calling nativo dipende dal modello: alcuni ignorano i tool o
  restituiscono più chiamate; il fallback testuale copre gli errori, non
  la qualità della scelta.
- Il client MCP supporta bearer/header e OAuth authorization code; non
  gestisce device flow, DPoP, mTLS o client assertion.
- La revisione delle skill è manuale da CLI; manca una GUI.
- La ricerca nella memoria è per parola chiave, senza indice né
  embedding.
- Il contesto iniettato usa turni recenti globali e fino a 3 skill
  confermate per match lessicale, senza selezione semantica.
- La memoria non cancella chat o skill per anzianità: `archive` è
  l'unica rimozione dal contesto.
- L'audit ha rotazione e retention (`max_files`), ma non compattazione
  delle sessioni né un ancoraggio esterno della catena.
- `feed.read` valida gli indirizzi e i redirect, ma resta il caso DNS
  rebinding: `requests` risolve il nome una seconda volta al momento
  della connessione; serve un resolver pinnato.
- Il calcolatore non è un CAS: gestisce solo espressioni numeriche
  limitate, non simboliche.
- `stat().created_at` è `None` su Linux quando manca `st_birthtime`; non
  viene inventata una data di creazione.
- Due alias non possono puntare allo stesso path fisico: l'alias
  identifica un mount e l'output virtuale deve restare univoco.

## 6.1 Responsabilità dell'utente: hard link, mount e TOCTOU

**Hagar non controlla gli hard link, i mount/junction e le race TOCTOU
dentro le directory allowed.** Non è un difetto di Hagar: la sandbox è
path-based e non usa handle/file descriptor per l'intera operazione.

Un hard link è un secondo nome dello stesso inode, non ha un target di
percorso e la sandbox non può sapere se esiste un altro nome fuori. Un
mount o una junction può esporre un altro filesystem pur restando dentro
il prefisso del path. Una race TOCTOU può cambiare un componente tra il
controllo dei symlink e l'operazione reale: Hagar non usa `openat2`,
`O_NOFOLLOW` su ogni componente o handle Windows, quindi non garantisce
atomicità tra check e accesso.

I tool filesystem di Hagar non creano hard link. Se un hard link o un
mount esiste già dentro una directory della sandbox, Hagar lo tratta come
un normale file o directory e può leggerlo, modificarlo o cancellarne il
nome interno.

La responsabilità è quindi divisa:

- **Hagar garantisce** che i percorsi risolti restino dentro l'alias al
  momento del controllo, che i symlink siano invisibili, che i permessi
  `R`/`W`/`X` siano applicati e che i path reali non finiscano
  nell'output del modello.
- **L'utente garantisce** che le directory configurate in
  `filesystem.sandbox` non contengano hard link, mount o junction verso
  contenuti che non devono essere accessibili, e che nessun processo
  concorrente non fidato possa modificare quelle directory durante
  l'esecuzione, se vuole isolamento totale.

Le race TOCTOU richiedono un attore locale concorrente con accesso in
scrittura alle directory della sandbox: non sono un caso accidentale
dell'uso normale, ma uno scenario malevolo o di ambiente compromesso.
Per un isolamento forte servono un volume dedicato, un utente separato,
un mount namespace o un container; non è compito del resolver di path.

I punti sono chiusi come **responsabilità dell'utente**, non come debiti
tecnici di Hagar. Hard link, mount/junction e race TOCTOU non sono
rilevati né bloccati da questa versione.

---

# 7. Mappa della documentazione

- `MANUAL.md` — manuale utente: comandi, configurazione, policy, default.
- `ARCHITECTURE.md` — questo documento: com'è il sistema oggi.
- `ROADMAP.md` — cosa fare, decisioni prese e punti aperti.
- `PLUGINS.md` — contratti per tool e provider LLM plugin.
- `DOCUMENT_TOOL.md` — specifica del document tool, schema del grafo e
  protocollo dell'host nativo.
- `SUBAGENTS.md` — MVP subagenti e limiti.
- `CHANGELOG.md` — storia delle versioni.
- `README.md` — avvio, configurazione, test.
