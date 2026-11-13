# HAGAR — Manuale utente

Versione: **0.7.0**

Questo manuale descrive il comportamento osservabile di Hagar: comandi,
opzioni, configurazione, policy e casi di errore. Per il progetto interno
vedi [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

# 1. Avvio rapido

Requisiti: Python 3.11 o superiore.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

cp hagar.example.yaml hagar.yaml
mkdir -p vault logs

hagar --config hagar.yaml
```

Su Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item hagar.example.yaml hagar.yaml
New-Item -ItemType Directory -Force vault, logs
hagar --config hagar.yaml
```

`hagar.yaml`, `testvault/` e `logs/` sono locali e non vanno versionati.

## 1.1 Ordine di avvio

1. Hagar legge la configurazione.
2. Carica `policy.yaml`; se non è valido, applica `DENY` a tutto.
3. Costruisce il client LLM.
4. Inizializza il Vault e la memoria, se configurati.
5. Costruisce la sandbox filesystem.
6. Registra i tool locali.
7. Tenta di caricare i server MCP; un server fallito non ferma gli altri.
8. Mostra la scelta del progetto.
9. Entra nel loop di chat.

---

# 2. Comandi di chat

I comandi iniziano con `/`. Un comando sconosciuto **non viene inviato al
modello**: Hagar risponde `Comando sconosciuto` e suggerisce `/help`.

## 2.1 Comandi globali

| Comando | Comportamento |
|---|---|
| `/help` o `/?` | elenca i comandi disponibili |
| `/tools [categoria]` | elenca i tool e le capability; il filtro è opzionale |
| `/status` | mostra modello, progetto, memoria, audit e sandbox |
| `/usage` | mostra i token consumati nella sessione |
| `/models ...` | schede, benchmark, storico e hardware per il broker |
| `/models test` | benchmark testo e qualità del modello corrente |
| `/models test vision` | benchmark vision su immagini sintetiche |
| `/models runs [n]` | ultimi run di benchmark salvati |
| `/models discover [provider]` | capacità dichiarate da LM Studio o Ollama |
| `/models hardware` | rileva CPU, RAM e GPU della macchina |
| `/undo` | annulla le modifiche dell'ultimo turno |
| `/mcp` | elenca server MCP, endpoint e tool importati |
| `/audit [n]` | mostra gli ultimi `n` eventi; default 10, massimo 50 |
| `exit` | esce |
| `quit` | esce |
| `Ctrl-D` | esce |
| `Ctrl-C` | interrompe; durante OAuth esce con codice 130 |

`/status` e `/audit` sono comandi umani: non passano dal modello e non
consumano tool call.

## 2.2 Progetto

| Comando | Comportamento |
|---|---|
| `/project` o `/project list` o `/project ls` | elenca i progetti attivi |
| `/project new <nome>` | crea un progetto e lo seleziona |
| `/project select <id>` o `/project use <id>` | seleziona un progetto attivo |
| `/project free` o `/project none` | passa ad attività libera |
| `/project status` o `/project current` | mostra il progetto corrente |
| `/project archive <id>` | archivia un progetto |
| `/project unarchive <id>` | riattiva un progetto archiviato |
| `/project help` | aiuto |

`select` e `archive` usano l’**id** del progetto, non il titolo.

In attività libera non viene letta né scritta memoria di progetto; chat,
summary e skill restano disponibili.

## 2.3 Memoria

| Comando | Comportamento |
|---|---|
| `/memory` o `/memory help` o `/memory ?` | aiuto |
| `/memory list [candidate\|confirmed\|archived]` | elenca le skill e i conteggi |
| `/memory show <slug>` | mostra una skill |
| `/memory search <testo>` | cerca nelle memorie SQLite |
| `/memory sessions` | elenca le chat registrate |
| `/memory chat <session>` | mostra i turni di una chat |
| `/memory reindex` | ottimizza/ricostruisce gli indici SQLite |
| `/memory stats` | stato e conteggi del database |
| `/memory backup <path>` | copia consistente del database |
| `/memory export <path> [--force]` | esporta chat, skill, summary e progetti in Markdown |
| `/memory import <path> [--force]` | importa una struttura Markdown nel database |
| `/memory review` | revisione interattiva delle candidate |
| `/memory confirm <slug>` | conferma una skill |
| `/memory archive <slug>` | archivia una skill |
| `/memory archive search <testo>` | cerca nei transcript archiviati |
| `/memory archive read <session> [offset] [limit]` | legge un transcript archiviato |

Le parole `search` e `read` sono riservate: uno slug di skill chiamato
esattamente `search` o `read` non è archiviabile con questo comando.

Non esiste un comando di cancellazione: si archivia soltanto.

Il backend predefinito è SQLite (`memory.backend: sqlite`). Il database
sta nei dati locali dell'app, non nel Vault:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

oppure `HAGAR_MEMORY_DB`. Il backend `markdown` resta solo per
compatibilità. Il Vault non è più aggiornato dal backend SQLite.

## 2.4 Cosa non è un comando

I tool (`filesystem.*`, `memory.*`, `mcp.*`, `clock.now`, ...) sono
chiamati dal modello tramite il registry. Non si digitano come `/tool`.
L’unica eccezione sono i comandi informativi `/tools`, `/status`, `/models`, `/mcp`,
`/audit`, che sono console e non tool.

---

# 3. Linea di comando

```text
hagar [opzioni]
hagar web [opzioni]
```

| Opzione | Effetto |
|---|---|
| `--config PATH` | usa un file di configurazione esplicito |
| `--model NAME` | sovrascrive `model.name` |
| `--project NAME` | seleziona un progetto attivo all’avvio |
| `--free` | avvia in attività libera |
| `--no-memory` | disattiva memoria e progetti per la sessione |
| `--no-native-tools` | forza il protocollo JSON testuale |
| `--hifi` | attiva il pre-pass di interpretazione e chiarimento |
| `--host HOST` | host della GUI web (default `127.0.0.1`) |
| `--port PORT` | porta della GUI web (default `8765`) |
| `--version` | stampa la versione |

`--project` e `--free` sono mutuamente esclusivi.

## 3.0 GUI web

```bash
hagar web
hagar --config hagar.yaml web --port 8765
```

Apre una GUI locale su `http://127.0.0.1:8765/`.

- Il server è pensato per un solo utente locale: default `127.0.0.1`.
- Il browser riceve un token casuale nella pagina; le API lo richiedono
  nell’header `X-Hagar-Token`.
- La chat mostra turni, tool call, risultati e conferme ASK.
- In alto ci sono le tab **Chat**, **Chat history**, **Tool output**,
  **Audit** e **Thinking**.
- **Chat history** elenca le chat passate, una riga per chat; un click
  riprende la chat: il transcript viene ricaricato dal database e i nuovi
  turni si aggiungono alla stessa sessione.
- Il pulsante **+ Nuova chat** apre una nuova sessione e azzera il
  contesto; la chat precedente resta nella cronologia.
- **Memories** è un browser in sola lettura delle note indicizzate
  (skill, progetti, decisioni); permette ricerca e apertura del testo.
- **Tool output** mostra i tool call e i risultati della sessione.
- **Audit** mostra gli eventi del log; se l'audit è disattivato la tab è
  disabilitata e mostra `audit off`.
- **Thinking** mostra il reasoning esposto dal provider, se presente; in
  alternativa la timeline degli eventi dell'agente.
- **Memories** mostra memorie e skill del database in sola lettura, con ricerca.
- I pulsanti **Pannello** e **Sandbox** aprono le pagine amministrative;
  entrambe hanno **Torna alla chat**. Dettagli in
  [WEB_UI.md](WEB_UI.md).
- **Pannello** elenca i tool con toggle allow/deny runtime, i provider e
  i modelli selezionabili, e i valori di configurazione modificabili
  (Hi-Fi, timeout, limiti). **Ritorna a configurazione hagar.yaml**
  ricarica i valori, riabilita i tool e azzera gli override RWX.
- **Sandbox** mostra l’albero della sandbox con checkbox R/W/X per
  elemento, il path reale dell’elemento selezionato e la creazione di
  nuove directory. Non esiste una funzione di cancellazione.
- Le mutazioni amministrative sono rifiutate mentre un turno è in
  corso; allow/deny non scavalca policy, conferme o tetto di sistema.
- Il pulsante **Stop** interrompe il turno in modo cooperativo.
- Il pulsante **Immagine** allega PNG/JPEG/WebP (max 4, 10 MB ciascuna)
  per i modelli vision. WebP viene convertito in PNG nella GUI perché LM
  Studio non lo accetta direttamente. Le immagini non vengono salvate
  nella memoria né nell'audit: al modello arriva il data URL, non il
  path host.
- La sidebar in basso mostra i token cumulati della sessione: input,
  output e totale.
- Il modello può caricare immagini dalla sandbox con `vision.open`;
  l'immagine viene allegata al turno, non restituita come base64 nel
  contesto.
- Le conferme ASK sono modali: il turno resta in attesa e il server
  continua a rispondere. Un timeout equivale a rifiuto. Le richieste dei
  subagenti mostrano `agent_id` e `parent_id`; il padre LLM non può
  approvarle. Il timeout del subagente è 180 secondi.
- In CLI un solo thread possiede l'input. Quando è attiva una conferma,
  il titolo del terminale chiede attenzione e sono accettati `F5` =
  allow, `F8` = deny, oltre a `y/N`. Se il terminale non supporta i tasti
  funzione, restano `y/N` e la GUI.
- Ctrl-C in CLI ripristina la modalità normale del terminale prima di
  uscire.
- La GUI non è ancora multiutente e non espone modifiche dirette alla memoria.
- Ctrl-C chiude il server e tenta la fine sessione.

Non usare `--host 0.0.0.0` su una rete non fidata: la GUI espone i tool
del harness a chiunque possa raggiungere la porta.

## 3.1 Ricerca della configurazione

Ordine:

1. `--config PATH`
2. variabile `HAGAR_CONFIG`
3. `./hagar.yaml` nella directory corrente

I percorsi relativi dentro `hagar.yaml` — audit, policy, Vault — sono
risolti rispetto alla directory del file di configurazione, non alla
directory da cui lanci Hagar.

## 3.2 Codici di uscita

| Codice | Significato |
|---|---|
| `0` | uscita normale o `--version` |
| `1` | errore di configurazione o progetto non valido |
| `130` | interruzione con Ctrl-C |

Un errore MCP non cambia il codice di uscita: viene registrato e il
harness continua.

---

# 4. `hagar.yaml`

Esempio minimo:

```yaml
model:
  provider: ollama
  name: llama3.1:latest

vault:
  path: ./vault

filesystem:
  sandbox:
    - alias: workspace
      path: .
      permissions: RX
```

## 4.1 `model`

| Campo | Default | Note |
|---|---|---|
| `provider` | obbligatorio | `ollama`, `lmstudio`, `deepseek`, `openai` (`chatgpt`), `claude`, `gemini` |
| `name` | obbligatorio | nome del modello presso il provider |
| `host` | default provider | base URL dell’API |
| `native_tools` | `true` | se `false`, usa il protocollo JSON testuale |
| `max_tokens` | `1024` | usato solo da Claude |
| `timeout` | `120` | timeout HTTP in secondi per ogni chiamata |
| `api_key_env` | nome standard | variabile d’ambiente della chiave |

Provider e chiavi:

| Provider | Chiave standard | Default |
|---|---|---|
| `ollama` | nessuna | `http://localhost:11434` |
| `lmstudio` | nessuna, opzionale `LMSTUDIO_API_KEY` | `http://localhost:1234/v1` |
| `deepseek` | `DEEPSEEK_API_KEY` | API DeepSeek |
| `openai` / `chatgpt` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `claude` | `ANTHROPIC_API_KEY` | API Anthropic |
| `gemini` | `GEMINI_API_KEY` | API Gemini |

Le chiavi non vanno mai scritte nel YAML. Se una chiave manca, il client
non viene costruito e l’avvio fallisce con un errore esplicito. LM Studio
non richiede chiave, salvo che il server locale sia configurato per
richiederla. `chatgpt` è un alias di `openai`: l’abbonamento ChatGPT non
dà accesso all’API, servono una chiave OpenAI e credito API.

Con LM Studio il tool calling nativo dipende dal modello e dal suo
template. Se il modello accetta la richiesta ma risponde in testo invece
di emettere `tool_calls`, Hagar non può eseguire il tool: usare
`model.native_tools: false` o un modello tool-capable.

Con il calling nativo attivo, Hagar usa gli strumenti strutturati del
provider. Se il provider rifiuta lo schema (HTTP 400/404/422), al primo
passo passa al protocollo JSON testuale per quella sessione. Il fallback
copre l’errore tecnico, non garantisce che il modello scelga bene il tool.

## 4.2 `audit`

```yaml
audit:
  enabled: true
  path: logs/audit.jsonl
  max_field_chars: 2000
  max_bytes: 5000000
  max_files: 100
  include_outputs: true
```

| Campo | Default | Effetto |
|---|---|---|
| `enabled` | `true` | attiva/disattiva il log |
| `path` | `logs/audit.jsonl` | file JSON Lines |
| `max_field_chars` | `2000` | tronca i campi |
| `max_bytes` | `5000000` | soglia di rotazione |
| `max_files` | `100` | file ruotati da conservare |
| `include_outputs` | `true` | se `false`, redige l’output dei tool |

L’audit contiene dati sensibili: output di file, risposte e testi. Va
protetto come il workspace. `/audit` mostra solo gli eventi del file
corrente, non quelli ruotati.

Eventi principali: `harness.start`, `turn.start`, `llm.tool_choice`,
`tool.call`, `tool.result`, `turn.answer`, `permission.decision`,
`permission.confirmation`, `memory.*`, `mcp.loaded`, `mcp.failed`,
`harness.stop`.

## 4.3 `policy`

```yaml
policy:
  path: policy.yaml
  subject: assistant
```

`path` è relativo alla configurazione. Se il file non è leggibile o non è
valido:

- tutte le policy diventano `DENY`;
- viene registrato `policy.failed`;
- Hagar resta avviato ma nessun tool viene eseguito;
- la console mostra `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

Con il backend SQLite è usato solo dal backend Markdown legacy e dai
progetti legacy. Con `memory.backend: sqlite` può anche non esistere.

## 4.5 `memory`

```yaml
memory:
  enabled: true
  backend: sqlite
  database: ./hagar-memory.db
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  context_project_memories: 10
  max_context_chars: 6000
  project_max_active: 200
  summary_max_chars: 4000
  max_skill_chars: 4000
```

| Campo | Default | Effetto |
|---|---|---|
| `enabled` | `true` | attiva la memoria |
| `backend` | `sqlite` | `sqlite` o `markdown` legacy |
| `database` | dati locali | path esplicito del database SQLite |
| `vault_subdir` | `Hagar` | sottodirectory del Vault legacy |
| `context_turns` | `10` | turni recenti iniettati; `0` disattiva |
| `context_skills` | `3` | skill confermate iniettate |
| `context_project_memories` | `10` | titoli di decisioni attive |
| `max_context_chars` | `6000` | budget del blocco memoria |
| `project_max_active` | `200` | soglia di manutenzione progetto |
| `summary_max_chars` | `4000` | lunghezza massima del summary |
| `max_skill_chars` | `4000` | lunghezza massima di una skill |

`vault_subdir` deve restare dentro il Vault: path assoluti, `..`,
`I:/...` e altri drive Windows vengono rifiutati anche su Linux.

Con `backend: sqlite` il database predefinito è:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

o `HAGAR_MEMORY_DB`. SQLite usa WAL, transazioni e `VACUUM INTO` per il
backup; il Vault non viene aggiornato.

Il budget è in **caratteri**, non in token. Quando il blocco viene
tagliato, l’audit registra `memory.context_trimmed`.

## 4.6 `filesystem`

```yaml
filesystem:
  sandbox:
    - alias: documenti
      path: C:\Users\pippo\Documenti
      permissions: RWX
  limits:
    max_write_bytes: 0
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

Ogni voce:

| Campo | Obbligatorio | Note |
|---|---|---|
| `alias` | sì | un solo segmento, unico case-insensitive |
| `path` | sì | directory esistente del sistema ospite |
| `permissions` | no | default `R`; lettere `R`, `W`, `X` |

Permessi:

| Lettera | Copre |
|---|---|
| `R` | leggere, listare, cercare, `stat` |
| `W` | scrivere, creare, rinominare, copiare, cancellare |
| `X` | `chdir` nella directory |

L’agente vede `/home/ai/<alias>/...`. `/home/ai` elenca gli alias ma non
è una directory fisica e non è possibile entrarci con `chdir`.

Vincoli:

- alias e path duplicati fermano la configurazione;
- un path mancante ferma la configurazione;
- i path fisici possono contenere spazi; gli alias no;
- Hagar non crea directory della sandbox e non assume una home dedicata.

Limiti di scrittura:

| Campo | Effetto |
|---|---|
| `max_write_bytes` | massimo per singola operazione |
| `min_free_bytes` | spazio libero minimo residuo |
| `session_write_bytes` | massimo cumulativo per sessione |
| `ask_over_bytes` | oltre questa soglia chiede conferma |

`0` disabilita il singolo limite. I limiti sono invarianti: un
superamento è un errore del tool, non un avviso.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
  agents: false
  database_read: false
  database_write: false
```

Sono il **tetto di sistema**. Default: `read=true`, gli altri `false`.

| Campo | Concede |
|---|---|
| `read` | filesystem read, memory read |
| `write` | filesystem write/create/delete, memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |
| `agents` | `AGENT_SPAWN` e `AGENT_DATA`, per `agent.*`/`artifact.*`/`mailbox.*` |
| `database_read` | `DATABASE_READ`, per query SQL in lettura |
| `database_write` | `DATABASE_WRITE` (e `DATABASE_READ`), per modifiche SQL |

`database_write` implica `DATABASE_READ` nel tetto, perché un tool di
scrittura deve poter leggere lo schema prima di modificarlo.

`COMPUTE` e `MCP_CALL` sono sempre nel tetto, ma la policy può negarli.
Se il tetto non concede una capability, la policy non può concederla.
`agents: true` non basta da solo: la policy deve avere una regola
`AGENT_SPAWN` per `agent.*`.

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

Valore previsto per il recupero documentale. Non modifica il contesto
della memoria in questa versione.

## 4.9 `mcp_servers`

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer
      token_env: MCP_EXAMPLE_TOKEN
```

Campi:

| Campo | Note |
|---|---|
| `endpoint` | URL HTTP/JSON-RPC del server MCP |
| `namespace` | prefisso dei tool importati: `mcp.<namespace>.*` |
| `auth` | opzionale: `bearer`, `header` o `oauth` |

Bearer/header:

```yaml
auth:
  type: header
  header: Authorization
  token_env: ATLASSIAN_BASIC
```

Il valore letto dall’ambiente viene inviato **così com’è**: per Basic
deve già essere `Basic <base64>`, non solo il token.

OAuth:

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    client_id: ...
    client_secret_env: MCP_CLIENT_SECRET
    scopes: [read:me, offline_access]
    audience: api.atlassian.com
    redirect_port: 8765
    token_cache: .hagar/oauth/example.json
    timeout: 300
```

Il flusso è authorization code + PKCE con callback locale
`http://localhost:<port>/oauth/callback`. Se `client_id` manca si tenta
la dynamic registration. Con `offline_access` viene aggiunto
`prompt=consent`. I token sono in un file locale ristretto e vengono
rinnovati automaticamente.

Se un server MCP fallisce:

- viene registrato `mcp.failed`;
- il server viene saltato;
- gli altri server e il resto del harness continuano;
- `/mcp` mostra zero tool per quel namespace.

## 4.10 `hifi`

```yaml
hifi:
  enabled: true
  margin: 0.20
  interpretations: 3
```

`margin` è la distanza minima, in punti percentuali, tra la prima e la
seconda interpretazione. Sotto quella soglia Hagar chiede chiarimento.
`interpretations` è il numero di interpretazioni richieste al modello.
La modalità aggiunge una chiamata LLM per ogni turno.

## 4.11 `tools`

```yaml
tools:
  timeout: 120
  repeat_limit: 3
  compact: true
  timeouts:
    document.ocr_pdf: 900
```

`timeout` è il limite in secondi per una singola tool call; `0` lo
disabilita. `repeat_limit` blocca la terza chiamata identica nello stesso
turno; `0` disabilita il blocco. `compact` usa descrizioni brevi e
omette le descrizioni dei parametri dallo schema nativo: riduce il
prompt per i modelli piccoli. Le descrizioni complete restano nei
`ToolDefinition`. `timeouts` imposta eccezioni per singolo tool.

Il timeout di un handler Python già in
esecuzione è best effort: il worker può terminare dopo il limite.

## 4.12 `dev`

```yaml
dev:
  enabled: false
  recipes: recipes.yaml
  copy_workspace: true
  max_output_chars: 100000
```

Abilita `dev.list` e `dev.run`, che eseguono ricette fidate per test,
debug e build. `recipes.yaml` deve stare fuori dalla sandbox e viene
letto solo all’avvio. Serve anche la capability `DEV_EXEC` in policy.
Dettagli in `DEV_RUN.md`.

## 4.13 `boxes`

```yaml
boxes:
  enabled: false
  max_input_chars: 200000
  max_output_chars: 20000
  chunk_chars: 8000
  max_calls: 20
```

Abilita `box.list` e `box.run`, trasformazioni LLM bounded su file della
sandbox. Non hanno memoria, tool o prompt libero. Serve `BOX_EXEC` in
policy. Dettagli in `BOXES.md`.

## 4.14 `flow`

```yaml
flow:
  enabled: false
  max_source_chars: 20000
  max_steps: 10000
  max_tool_calls: 50
  max_loop_iterations: 1000
  timeout: 120
  max_output_chars: 20000
  repair_attempts: 2
```

Abilita `flow.reference`, `flow.validate` e `flow.run`, il DSL lineare
`Hagar Flow`. Non è Python completo: niente import, class, def, lambda,
try, dict/set comprehension o accesso a oggetti Python; sono ammesse
list comprehension con un solo `for`. Serve `FLOW_EXEC` in policy; le
primitive `fs.*` usano le capability filesystem.

`repair_attempts` è il numero massimo di tentativi di `flow.repair`;
`0` disabilita la riparazione. `flow.run` non ripara mai il codice da
solo: restituisce l’errore e il chiamante decide se usare `flow.repair`.
Con la memoria attiva sono disponibili `memory.search`, `memory.context`
e `memory.skill`; con un progetto attivo `project.context`.
Dettagli in `FLOW.md`.

---

# 5. `policy.yaml`

Esempio:

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
        tools: ["filesystem.*"]

      - capabilities: [COMPUTE]
        effect: allow
        tools: ["calculator.*", "statistics.*", "units.*",
                "clock.*", "calendar.*", "think.*", "text.*", "url.*"]

      - capabilities: [MCP_CALL]
        effect: ask
        tools: ["mcp.*"]

      - capabilities: [MEMORY_READ]
        effect: allow
        tools: ["memory.*"]

      - capabilities: [MEMORY_WRITE]
        effect: ask
        tools: ["memory.*"]
```

## 5.1 Effetti

| Effetto | Significato |
|---|---|
| `allow` | il tool può essere eseguito |
| `ask` | serve una conferma umana |
| `deny` | il tool non viene eseguito |

Ordine di gravità: `DENY > ASK > ALLOW`. Con più capability richieste
vale l’AND: vince l’effetto peggiore.

`ASK` senza canale di conferma equivale a `DENY`. La conferma da console
mostra `lo faccio? (y/N)` e il default è `N`.

## 5.2 Capability

| Nome | Uso |
|---|---|
| `FILESYSTEM_READ` | lettura, elenco, ricerca, stat |
| `FILESYSTEM_WRITE` | modifica |
| `FILESYSTEM_CREATE` | creazione, copia, rename in destinazione |
| `FILESYSTEM_DELETE` | cancellazione |
| `FILESYSTEM_EXEC` | ingresso/esecuzione nella sandbox |
| `MEMORY_READ` | lettura memoria |
| `MEMORY_WRITE` | scrittura memoria |
| `NETWORK` | accesso di rete |
| `MCP_CALL` | chiamata a tool MCP |
| `COMPUTE` | calcolo locale senza rete/filesystem |
| `AISH` | esecuzione del linguaggio AIsh |
| `DEV_EXEC` | esecuzione di ricette dev.run |
| `BOX_EXEC` | esecuzione di boxed transform |
| `FLOW_EXEC` | esecuzione del DSL Hagar Flow |
| `DATABASE_READ` | lettura di database SQL |
| `DATABASE_WRITE` | modifica di database SQL |

## 5.3 Regole e specificità

Una regola può filtrare con:

- `tools`: glob sul nome (`filesystem.*`, `mcp.atlassian.*`);
- `paths`: prefissi sul path scritto dal modello;
- `namespaces`: prefissi sul namespace.

Vince la regola più specifica: prima il numero di filtri, poi la
lunghezza del prefisso. A parità vince l’effetto più restrittivo.
Senza regole vale `default` del soggetto; il default sicuro è `deny`.

`AISH` è negata dalla regola predefinita `aish.*`. Per abilitare AIsh
l’utente deve cambiare quella regola in `allow`; i comandi interni
restano soggetti alle regole dei rispettivi tool.

Lo scope `paths` confronta il path **scritto dal modello**, non quello
risolto dopo `chdir`: un path assoluto o un cambio di directory può non
corrispondere e produce `DENY` (fail closed).

## 5.4 Errori

Se `policy.yaml` è invalido, manca una capability o il soggetto non
esiste:

- Hagar applica `DENY` a tutte le policy;
- registra `policy.failed`;
- mostra un avviso;
- non esegue nessun tool.

---

# 6. Comportamenti predefiniti

| Situazione | Comportamento |
|---|---|
| Nessun `hagar.yaml` | errore di configurazione, uscita 1 |
| YAML invalido | errore di configurazione, uscita 1 |
| Policy invalida | DENY totale, harness avviato |
| Memoria disattivata | controlla `memory.database` e i permessi della directory |
| `Projects: disabled` | controlla il database SQLite o `vault.path` nel backend legacy |
| Nessun progetto attivo | attività libera |
| Avvio non interattivo | attività libera, salvo `--project`/`--free` |
| `--project` inesistente | errore, uscita 1 |
| Server MCP irraggiungibile | `mcp.failed`, server saltato |
| Modello/Ollama irraggiungibile | errore del turno, harness resta attivo |
| Chiave API assente | client non costruito, errore all’avvio |
| Tool negato | risultato di errore al modello, nessuna esecuzione |
| Tool in `ASK` senza conferma | rifiuto |
| Limite di scrittura superato | errore del tool, nessuna scrittura |
| File oltre 4096 byte con `read_file` | errore, usare `read_chunk` |
| `write_file`/`edit_file`/`delete_file`/`rename` su file non letto | errore: leggere prima il file |
| File cambiato dopo la lettura | errore: rileggere prima di modificarlo |
| `edit_file` con `old_string` ambiguo | errore: usare `replace_all` o una stringa più specifica |
| `edit_file` con `old_string` assente | errore, nessuna modifica |
| Pagina oltre il limite | `has_more`/`next_offset` |
| Symlink | invisibile; operazione come path inesistente |
| Hard link/mount/junction | non rilevati; responsabilità utente |
| Race TOCTOU | non controllata; responsabilità utente |
| Memoria assente durante il turno | `memory.failed`, il turno continua |
| Fine sessione con turni | summary, archivio, review progetto |
| Review rifiutata | decisioni candidate con `auto_saved: true` |
| Progetto oltre `project_max_active` | richiesta di archiviazione |
| Ctrl-C durante OAuth | callback chiuso, uscita 130 |
| Comando `/` sconosciuto | messaggio, non inviato al modello |

## 6.1 Fine sessione

All’uscita, se la memoria è attiva e ci sono turni:

1. il transcript viene spostato in `archive/chat/`;
2. viene generato un summary (LLM, con fallback meccanico);
3. il summary viene salvato con link e hash;
4. se c’è un progetto, l’LLM propone decisioni candidate;
5. l’utente può rivederle; se rifiuta restano candidate.

Se non ci sono turni non viene creato nessun summary.

## 6.2 Cosa Hagar non fa

- non esegue comandi di shell;
- non dà al modello path fisici;
- non garantisce isolamento OS: la sandbox è path-based;
- non controlla hard link, mount, junction o TOCTOU;
- non cancella chat o skill per anzianità;
- non cifra il Vault;
- non promuove automaticamente una skill o una decisione a verità.

---

# 7. Sicurezza operativa

- Il modello è non fidato: policy e conferme sono i controlli.
- Il database SQLite contiene conversazioni e decisioni: va protetto.
- L’audit può contenere output di file: va protetto.
- Le chiavi API stanno solo nell’ambiente.
- I token MCP/OAuth stanno in cache locali con permessi ristretti.
- Non esporre Ollama o LM Studio sulla rete senza necessità.
- Un hard link o un mount dentro una directory allowed può esporre
  contenuti esterni: Hagar non li rileva.

---

# 8. Troubleshooting

| Sintomo | Controllo |
|---|---|
| `Policy: DENY ALL` | validare `policy.yaml` e `policy.path` |
| `Memory: disabled` | controlla `memory.database` e i permessi |
| `Projects: disabled` | controlla il database SQLite |
| `Failed to load MCP server` | endpoint, token, `/mcp` |
| `MCP auth token missing` | variabile indicata da `token_env` |
| `MCP HTTP 401` | credenziali/header Basic o OAuth |
| `MCP HTTP 400` | protocollo, sessione o parametri del server |
| `read_file` troppo grande | usare `read_chunk` |
| `PermissionError` | policy, permessi `R/W/X`, path fuori sandbox |
| Tool non elencato | server MCP fallito o tool non registrato |
| Comando non riconosciuto | `/help` |

Per un errore di configurazione, Hagar esce con codice 1 e stampa il
dettaglio su stderr. Per un errore di turno, il modello riceve il
risultato del tool e l’audit conserva l’evento.
