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
| `model` | sì | provider, nome, host, max_tokens, api_key_env, native_tools |
| `vault` | sì | percorso del vault Obsidian |
| `filesystem` | sì | `sandbox`: lista di `{alias, path, permissions}` |
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
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system separato, turni alternati |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, ruolo `model` |

La chiave si legge solo dall'ambiente; `model.api_key_env` sovrascrive il
nome predefinito. `model.host` è la base URL di tutti i provider (con un
default per provider), `model.max_tokens` è usato solo da Claude.
`llm/factory.py` costruisce il client e rifiuta provider sconosciuti o
chiavi mancanti. DeepSeek: i modelli correnti sono `deepseek-flash` e
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
fermano la configurazione.

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
con `has_more`; `search` usa un glob ricorsivo con limite di risultati;
`copy_file` richiede `create`; `rename` richiede `rename` sulla sorgente
e `create` sulla destinazione. I percorsi restituiti sono sempre
virtuali (`/home/ai/<alias>/...`). `chdir` richiede `X` sull'alias.

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

Supporta anche risposte `text/event-stream` (streamable HTTP) e invia
la notifica `notifications/initialized` dopo l'handshake. I risultati
dei tool vengono normalizzati a testo: blocchi `text`, altrimenti
`structuredContent` o JSON; un risultato con `isError` diventa un
errore del tool.

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
    redirect_port: 8765       # 0 = porta casuale
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

Flusso authorization code + PKCE, con callback su `127.0.0.1` e apertura
del browser. I metadata vengono scoperti da `.well-known` (RFC 9728 per la
risorsa, RFC 8414 per l'authorization server); se `client_id` manca si usa
la registrazione dinamica. I token sono in un file locale con permessi
ristretti (`0600` dove il sistema li supporta), con refresh automatico e
retry una volta su `401`.

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
`DENY`. Una GUI potrà implementare lo stesso protocollo con un dialog
modale.

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
        tools: ["calculator.*", "statistics.*", "units.*"]
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
  max_skill_chars: 4000
```

Se `vault.path` non esiste o non è scrivibile, la memoria viene
disattivata con un avviso in chat e `memory.disabled` nell'audit; gli
altri componenti continuano a funzionare. Le scritture di memoria sono
soggette alle policy (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.12 Avvio e packaging

Il progetto si installa con `pip install -e .` e dichiara i package in
`pyproject.toml`. L'entry point è `hagar = "hagar:main"`.

```text
hagar --config PATH       file di configurazione
hagar --model NAME        sovrascrive model.name
hagar --no-memory         disattiva la memoria per la sessione
hagar --no-native-tools   usa il protocollo JSON testuale
hagar --version
```

La configurazione si cerca in quest'ordine: `--config`, variabile
`HAGAR_CONFIG`, `./hagar.yaml`. `python -m hagar` funziona dalla
directory del progetto.

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
| `feeder` | `feed.read` | `NETWORK` |

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
- `local_tools` è dichiarato in `pyproject.toml` e installato con il
  progetto.

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
  `.\tools\run_tests.ps1` (Windows) — 628 test superati, 1 skip (symlink
  non disponibili senza Developer Mode). Dettagli e motivazione dello
  shim in README §3.1.
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
- Restano da verificare in CI Linux/macOS: symlink, permessi dei file
  token OAuth e callback loopback.

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
  identifica un mount e l'output virtuale deve restare univoco. Per una
  vista in sola lettura usare un alias su una directory diversa o
  cambiare i permessi dell'alias.

---

# 7. Mappa della documentazione

- `ARCHITECTURE.md` — questo documento: com'è il sistema oggi.
- `ROADMAP.md` — cosa fare, decisioni prese e punti aperti.
- `CHANGELOG.md` — storia delle versioni.
- `README.md` — avvio, configurazione, test.
