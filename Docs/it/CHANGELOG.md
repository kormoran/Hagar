# HAGAR — Changelog

Il formato è libero ma stabile: versioni in ordine decrescente, con
riferimento al commit quando utile.

---

# Non rilasciato

## Nuovi backend LLM

- Nuovo backend `lmstudio` per il server OpenAI-compatibile locale di
  LM Studio, default `http://localhost:1234/v1`, senza chiave salvo
  configurazione del server.
- Nuovo backend `openai` (alias `chatgpt`) per l'API OpenAI Chat
  Completions, chiave `OPENAI_API_KEY`, base URL configurabile.
- I due backend condividono il client OpenAI-compatibile, con native
  tool calling e fallback JSON testuale su HTTP 400/404/422.
- `model.timeout` configurabile (default 120 s) e passato a tutti i
  backend; utile per modelli locali grandi.
- `hagar.example.yaml` e la documentazione italiana aggiornati.

## Service layer

- Nuovo `core/service.py` con `HarnessService`: turni, stato, progetto,
  fine sessione ed eventi strutturati (`ServiceEvent`).
- `hagar.py` usa il service per `ask`, selezione progetto e chiusura
  sessione; la CLI resta un adapter.
- Eventi `tool.call`, `tool.result`, `permission.decision` e
  `permission.confirmation` inoltrati da `Agent` e `ToolRegistry` al
  sink del service; l'output dei tool è troncato negli eventi.
- Nuovo `CommandService` per `/help`, `/tools`, `/status`, `/mcp`,
  `/audit`, `/project` e `/memory`, con `CommandResult` strutturato.
- La CLI usa il command service per i comandi slash; `/memory review`
  resta interattiva.
- Nuovo `QueueConfirmationProvider`: conferme ASK da GUI con coda,
  timeout e rifiuto esplicito.
- Nuova GUI web locale (`hagar web`): chat, eventi SSE, stato, progetti,
  tool call e modale di conferma; token locale e bind `127.0.0.1`.
- Le disconnessioni SSE del browser non producono più traceback su
  Windows (`ConnectionAbortedError`/WinError 10053).
- Ctrl-C chiude subito `hagar web`: niente `shutdown()` dal thread di
  `serve_forever`, niente join dei thread SSE e summary saltato allo
  spegnimento.
- Nuovo `core/usage.py`: parsing usage OpenAI/DeepSeek/LM Studio,
  Claude, Gemini e Ollama, con `UsageLedger` per sessione.
- La GUI mostra input, output e totale token nella sidebar, aggiornati
  via evento `usage.updated`.
- HTML, CSS e JavaScript della GUI separati in `web/` e serviti come
  asset statici; `core/web.py` inietta solo il token.
- Nuovo `memory/index.py`: indice SQLite/FTS5 incrementale e
  ricostruibile delle memorie Markdown, con fallback lessicale.
- Nuovo tool `memory.search`; comandi `/memory search`, `reindex`,
  `stats`.
- Stop cooperativo del turno (`Agent.cancel`, `POST /api/stop`) con
  pulsante nella GUI ed evento `turn.cancelled`.
- Input immagini vision (`core/images.py`) con validazione data URL,
  MIME e limite 10 MB; adapter OpenAI/LM Studio, Claude e Gemini.
- Upload immagini nella GUI con anteprima e rimozione; WebP convertito
  in PNG prima dell'invio. Nessuna immagine salvata in memoria o audit.
- Body JSON della GUI fino a 64 MB, per accettare immagini ad alta
  risoluzione in base64.
- Cronologia chat nella tab dedicata: elenco di `chat/` e
  `archive/chat/`; un click riprende la stessa sessione e i nuovi turni
  continuano il transcript.
- Pulsante **+ Nuova chat** con `MemoryStore.new_session()` e reset del
  contesto; i transcript precedenti restano nel Vault.
- Tab GUI: Chat, Chat history, Tool output, Audit, Thinking, Memories.
- `SessionLog` in memoria per tool call/risultati e timeline;
  `/api/tools`, `/api/audit`, `/api/thinking`.
- Browser memorie in sola lettura: `/api/memories`, `/api/memory`.
- `/usage` in CLI per i token cumulati della sessione; stesso ledger
  usato dalla GUI.
- Tool e provider LLM sono plugin: built-in in `local_tools/plugins.py`
  e `llm/plugins.py`, esterni via entry point `hagar.tools`/`hagar.llm`.
- Errori dei plugin isolati e registrati in audit; policy e sandbox
  restano nell'host.
- Documentata la progettazione del document tool in `DOCUMENT_TOOL.md`:
  grafo struttura/semantica, CSV MVP, contratto `FormatPlugin`, ABI C e
  protocollo JSON dell'host nativo.
- Audit disattivato: tab disabilitata con etichetta `audit off`.
- Thinking mostra il reasoning esposto dal provider, altrimenti la
  timeline degli eventi.
- Base per la futura GUI, senza `input()` o `print()` nel service.

# 0.3.0 — 2026-11-05

## Memoria di progetto, summary e archivio

- Nuova memoria di progetto separata dalle skill:
  `Hagar/projects/<id>/index.md` e `decisions/<data>-<slug>.md`, con
  stato `candidate`/`active`/`superseded`/`archived`, alternative,
  motivazione, provenance e `auto_saved`.
- All'avvio Hagar mostra i progetti attivi e “attività libera”; comandi
  `/project list|new|select|free|status` e override `--project`/`--free`.
- A fine sessione il transcript viene spostato in `archive/chat/` e
  sostituito da un summary con link e hash; fallback meccanico se il
  modello non è disponibile.
- Le decisioni di progetto vengono proposte come `candidate` e riviste
  a fine sessione; se l'utente rifiuta, restano candidate con
  `auto_saved: true`.
- Contesto a indice: summary e titoli delle decisioni attive, non i
  corpi; dettagli con `memory.project_context`. Budget
  `max_context_chars` (caratteri, non token) e audit
  `memory.context_trimmed`.
- `project_max_active` fa scattare la richiesta di archiviazione del
  progetto; l'archiviazione è reversibile e non cancella nulla.
- Se la directory `projects` non è scrivibile, la memoria resta attiva
  e i progetti vengono disabilitati con `project.disabled`.
- Consultazione archivio: `memory.archive_search` e
  `memory.archive_read`, comandi `/memory archive search|read`, con
  filtro per progetto e transcript che conserva `project` nel
  frontmatter. L'archivio non viene mai iniettato automaticamente.

## Comandi console e manuale

- Nuovi comandi di chat: `/help`, `/tools [categoria]`, `/status`, `/mcp`,
  `/audit [n]`.
- `/tools` raggruppa i tool per categoria e mostra le capability.
- `/status` riporta modello, calling, progetto, memoria, audit e
  filesystem.
- `/mcp` elenca server configurati, endpoint e tool importati.
- `/audit` legge gli ultimi eventi del log corrente, senza esporre i
  campi non selezionati.
- I comandi `/` sconosciuti non vengono inviati al modello.
- Nuovo `Docs/it/MANUAL.md` con comandi, CLI, `hagar.yaml`,
  `policy.yaml`, default e comportamenti in caso di errore.

## MCP, OAuth e uscita pulita

- Client MCP aggiornato a `MCP-Protocol-Version` `2025-06-18` con
  fallback, riuso di `Mcp-Session-Id` e corpo HTTP negli errori.
- OAuth: `audience` opzionale, `prompt=consent` con `offline_access`,
  callback `http://localhost:<port>/oauth/callback`, scope nella
  dynamic registration.
- Ctrl-C durante OAuth o un turno chiude il callback locale ed esce con
  codice 130, senza traceback.

## Strumenti locali e filesystem v2

- Nuova directory `local_tools/` per i provider locali: calcolo, statistica,
  conversione unità, ora/data e feed. Non sono server MCP: registrano
  `ToolDefinition` nel registry.
- Tool aggiunti: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `clock.now`, `calendar.date`, `think.echo`,
  `text.diff`, `url.parse`, `feed.read`.
- Filesystem: `list_dir`, `read_chunk`, `rename`, `copy_file`, `search`.
- Nuove capability `COMPUTE` (calcoli locali, sempre nel tetto) e
  `NETWORK` (abilitata da `permissions.network: true`); `feed.read`
  richiede `NETWORK`.
- `permissions.network` in configurazione; policy: `COMPUTE` allow per
  calculator/statistics/units, `NETWORK` ask per feed.
- `feedparser` tra le dipendenze; il feed viene scaricato con
  `requests`, timeout e limite di 5 MB, e solo da URL http/https.
- SSRF: risoluzione DNS obbligatoria, solo indirizzi globali
  (niente loopback, reti private, link-local, multicast o riservati),
  redirect manuali rivalidati (massimo 3) e rifiuto degli URL con
  credenziali.
- Ripristinato il permesso `rename` della sandbox, perso durante
  l'estensione; `filesystem.rename` richiede `rename` sulla sorgente e
  `create` sulla destinazione.
- Rinomina `MCP_tools/` → `local_tools/`: sono provider locali, non
  server MCP; package, import, test e documentazione aggiornati.
- Filesystem con radice virtuale `/home/ai`: `stat`, `list_dir`,
  `search`, `read_chunk` e i messaggi dei tool non espongono più il
  percorso fisico; gli input `/home/ai/...` sono accettati.
- `read_chunk` allinea i confini ai caratteri UTF-8 e restituisce
  `next_offset`; non spezza più caratteri multibyte.
- `read_file` rifiuta file oltre 4096 byte e rimanda a `read_chunk()`
  per evitare di caricare tutto il file nella context window.
- `list_dir` restituisce al massimo 100 voci per pagina e `search` 100
  risultati (massimo 500); entrambi supportano `offset`, `next_offset`,
  `has_more` e il messaggio
  `voci: riportate X di Y; per continuare usa offset=Z`. Per alberi
  grandi conviene restringere pattern/path invece di iterare pagine.
- Nuovi limiti di scrittura `filesystem.limits`:
  `max_write_bytes` per operazione, `min_free_bytes` come riserva,
  `session_write_bytes` cumulativo e `ask_over_bytes` per la conferma.
  I primi tre sono invarianti; `ask_over_bytes` passa dal preflight di
  `ToolRegistry` e chiede una sola volta, anche se la policy è `ASK`.
- I symlink non esistono per la sandbox: non sono mostrati, letti,
  seguiti o cancellati; `chdir` su un link risponde
  “Directory not found”. Decisione di progetto: restano invisibili
  anche se il filesystem ospite li supporta.
- Hard link, mount e junction dentro le directory allowed non sono
  controllati né rilevati da Hagar. Non è un difetto: un hard link è un
  secondo nome dello stesso inode e un mount può esporre un altro
  filesystem restando dentro il prefisso. I tool filesystem non creano
  hard link. Per isolamento totale l'utente deve garantire che nelle
  directory della sandbox non ce ne siano. Responsabilità dell'utente,
  punto chiuso.
- TOCTOU: questa versione non usa `openat2`, `O_NOFOLLOW` su ogni
  componente o handle Windows, quindi non garantisce atomicità tra check
  e operazione. La race richiede un processo locale concorrente con
  accesso in scrittura: scenario malevolo o ambiente compromesso, non
  uso normale. Chiuso come responsabilità dell'utente; per isolamento
  totale servono volume dedicato, utente separato, mount namespace o
  container.
- `filesystem.allowed` sostituito da `filesystem.sandbox`: ogni voce ha
  `alias`, `path` e permessi `R`/`W`/`X`. L'agente vede
  `/home/ai/<alias>/...`; niente `hdN`, niente volumi o directory
  intermedie sintetiche. `/home/ai` elenca gli alias ma non è un mount.
- Permessi per alias: `R` lettura/elenco/ricerca/stat, `W`
  scrittura/creazione/rinomina/copia/cancellazione, `X` `chdir`; i
  permessi globali restano un tetto.
- Alias obbligatorio, singolo segmento, unico case-insensitive, senza
  nomi riservati Windows; le voci della sandbox restano path del sistema
  ospite e Hagar non crea directory. I path fisici e i nomi interni
  possono contenere spazi; l'alias no.
- Runner POSIX `tools/run_tests.sh`; `run_tests.ps1` e lo shim restano
  specifici della sandbox Windows. Aggiornati i comandi di benchmark.
- Fix multipiattaforma dalla CI: `vault_subdir` rifiuta anche i path con
  drive Windows (`I:/...`) su POSIX; il rifiuto dei symlink non viene più
  inghiottito da `except OSError`, quindi il percorso non viene risolto
  fuori dalla sandbox.
- 782 test superati, 2 skip su Windows; 784 superati, 0 skip su Debian
  Linux (2026-11-06), inclusi i test symlink.

## Rilascio e multipiattaforma

- Versione `0.3.0` in `pyproject.toml` e `hagar.py`.
- CI GitHub Actions su Linux, macOS e Windows con Python 3.11, 3.12 e
  3.13; build del pacchetto, `twine check` e smoke test del wheel.
- Action aggiornate a `checkout@v7`, `setup-python@v7` e
  `upload-artifact@v7`, tutte su Node 24; rimosso il warning di
  deprecazione di Node 20.
- Workflow di release su tag `v*`: build sdist/wheel, verifica che il tag
  corrisponda alla versione e creazione della release GitHub.
- `hagar.example.yaml` portabile; `hagar.yaml` locale e `testvault/` sono
  ignorati da git.
- `MANIFEST.in`, `SECURITY.md`, `CONTRIBUTING.md` e `RELEASING.md` per il
  primo rilascio pubblico.

# 0.2.0 — 2026-11-04

Prima release con memoria revisionabile, calling nativo, MCP auth/OAuth,
retention dell'audit e packaging installabile.

## Memoria v2

- Ciclo di vita `candidate` → `confirmed` → `archived`: l'LLM propone,
  l'utente promuove da CLI.
- Comandi `/memory list`, `/memory show`, `/memory review`,
  `/memory confirm`, `/memory archive`.
- Iniezione automatica delle sole skill confermate, fino a
  `memory.context_skills` (default 3), per match lessicale; le candidate
  e le archiviate restano fuori.
- `reviewed_at` nel frontmatter; eventi audit `memory.review` e
  `memory.status`.
- Retention opzione A: nessuna cancellazione automatica; `archive` è
  reversibile con `confirm`.
- `memory.context_skills` in configurazione; 552 test superati, 1 skip.

## MCP OAuth interattivo

- Flusso authorization code + PKCE con callback su `127.0.0.1` e
  apertura del browser; fallback manuale incollando l'URL.
- Discovery RFC 9728 (protected resource) e RFC 8414 (authorization
  server), con registrazione dinamica del client se `client_id` manca.
- Cache token locale con permessi `0600`, refresh automatico e retry una
  volta su `401`.
- Config `auth.type: oauth` con `authorization_server`, `client_id`,
  `client_secret_env`, `scopes`, `redirect_port`, `token_cache`,
  `timeout`.
- Limiti: niente device flow, DPoP, mTLS o client assertion.
- 522 test superati, 1 skip.

## Audit retention

- Rotazione in `<file>.<timestamp>` oltre `audit.max_bytes`.
- `audit.max_files` (default 100) limita il numero di file audit,
  incluso quello attivo; i backup più vecchi vengono eliminati.
- La catena di hash continua dal backup più recente se il file attivo
  manca.
- 504 test superati, 1 skip.

## MCP auth

- `mcp_servers[].auth`: `type: bearer` oppure `type: header`, con
  `token_env` e, per l'header, il nome dell'header.
- Il token si legge solo dall'ambiente: non va nel YAML, nell'audit o
  nei log.
- Token mancante o non-ASCII: il server viene saltato con `mcp.failed` e
  il harness continua con gli altri.
- 496 test superati, 1 skip.

## Benchmark nativo vs testo

- `tools/bench_native.py`: 9 task filesystem sullo stesso registry,
  confronto tra `native_step()` e `request_tool_call()`, con accuratezza,
  latenza e riparazioni.
- Prime misure: `llama3.1` 4/5 vs 5/5, `qwen3:8b` 4/5 vs 5/5,
  `hermes3:8b` 4/5 vs 3/5, `deepseek-flash` 8/9 vs 9/9 (subset Ollama,
  suite completa DeepSeek).
- Nessun vincitore universale: il default resta nativo, con opt-out per
  modello tramite `model.native_tools` o `--no-native-tools`.

## DeepSeek (live)

- Modelli aggiornati: `deepseek-flash` (default) e `deepseek-v4-pro`;
  `deepseek-chat` non è più valido.
- Messaggi d'errore con il corpo della risposta API; chiavi non-ASCII
  rifiutate con `ConfigError`.
- Nomi dei tool normalizzati per le API che non ammettono il punto
  (`filesystem.read_file` → `filesystem__read_file`), con ritorno al
  nome interno.
- `tools/diagnose_deepseek.py` per rete, forma della chiave ed endpoint,
  senza stampare la chiave.
- Test live: chat, calling nativo ed end-to-end sul filesystem.
- 479 test superati, 1 skip; 9 test live con `--live`.

## Calling nativo (v1)

- `LLMClient.native_step()` e `LLMReply`: calling nativo per Ollama,
  DeepSeek, Claude e Gemini; schema dei parametri da `ToolDefinition`.
- Messaggi canonici `assistant` con `tool_calls` e `tool` con
  `tool_call_id`; ogni backend li traduce (`tool_calls`, `tool_use`/
  `tool_result`, `functionCall`/`functionResponse`).
- L'Agent esegue più chiamate per turno, nel limite `max_tool_calls`.
- Fallback automatico al protocollo testuale su HTTP 400/404/422 al primo
  passo, con evento `llm.native_fallback`; `model.native_tools: false` e
  `--no-native-tools` lo forzano.
- Audit: `turn.start` con `native`, `llm.tool_choice` con `mode=native`.
- 476 test superati, 1 skip; 7 test live con `--live`.

## Igiene (v1)

- **Packaging**: `pyproject.toml` completo (metadati, dipendenze,
  setuptools), entry point `hagar`, versione unica (`hagar.__version__`);
  `pip install -e .` verificato.
- **CLI**: `--config`, `--model`, `--no-memory`, `--version`;
  configurazione cercata in `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml`.
- **Test live**: marker `live`, esclusi dalla suite normale, `--live`
  per Ollama e provider remoti (skippati senza chiave).
- **MCP**: risposte `text/event-stream`, notifica
  `notifications/initialized`, normalizzazione dei risultati a testo.
- **Audit**: catena di hash (`prev`/`hash`, `verify_chain`), rotazione a
  `max_bytes`, redazione dell'output dei tool con `include_outputs`.
- **URL base**: `model.host` usato da tutti i provider.
- **Legacy**: rimossi `tools/filesystem.py` e `llm/tool_result.py`.
- 442 test superati, 1 skip; 6 test live con `--live`.

## Memoria (v1)

- `memory/store.py`: memoria episodica (una nota per sessione in
  `<vault>/Hagar/chat/`) e semantica
  (`<vault>/Hagar/skills/<slug>.md`);
- iniezione automatica degli ultimi `memory.context_turns` turni nel
  prompt, con troncamento; un errore di memoria non fa fallire il turno;
- tool `memory.create_skill` (provenance e stato `candidate`),
  `memory.list_skills`, `memory.get_context` (ricerca per parola chiave);
- capability `MEMORY_READ`/`MEMORY_WRITE`, namespace `chat`/`skills` per
  le policy;
- configurazione `memory.*` e disattivazione con avviso se il vault
  manca;
- eventi audit `memory.enabled`, `memory.disabled`, `memory.context`,
  `memory.turn`, `memory.failed`;

## Permessi (PermissionEvaluator v1)

- nuovo `core/permissions.py`: `Capability` (IntFlag), `Effect`
  (`ALLOW` / `ASK` / `DENY`, con deny-overrides), `Rule` con scope per
  tool, path e namespace, `Subject`, `Resource`, `Decision` ed
  evaluator puro;
- `policy.yaml` separato, letto prima di costruire il LLM: in caso di
  errore tutte le policy diventano `DENY`, con evento `policy.failed` e
  warning in chat;
- tetto di sistema derivato da `permissions.read/write/shell`;
- `ASK` con conferma da console (`lo faccio? (y/N)`, default N) e
  `ConfirmationProvider` per le future GUI;
- `ToolRegistry.execute` applica la policy e registra
  `permission.decision` e `permission.confirmation`;
- `ToolDefinition.capabilities` per tutti i tool (filesystem e MCP);
- `requires_confirmation` ora applicato come pavimento di ASK;
- rimosso lo stub incompleto `PolicyRule` da `core/models.py`;

## Filesystem v2, strumenti matematici e feed

### Filesystem

- `filesystem.list_dir`: elenco non ricorsivo del contenuto di una directory.
- `filesystem.list_dir` restituisce metadati completi tramite `FileInfo` per ogni elemento trovato.
- `filesystem.read_chunk`: lettura incrementale di file di grandi dimensioni tramite offset e lunghezza.
- `filesystem.read_chunk` opera a livello di byte e restituisce `has_more` per consentire all'agente di continuare la lettura.
- `filesystem.rename`: rinomina o sposta file all'interno della sandbox.
- `filesystem.copy_file`: copia file con verifica dei permessi e dello spazio disponibile.
- `filesystem.search`: ricerca ricorsiva tramite pattern glob (`*.py`, `*.md`, ecc.).
- `filesystem.search` restituisce:
  - numero totale di risultati trovati;
  - numero di risultati restituiti;
  - indicazione di troncamento (`truncated`);
  - elenco dei risultati come `FileInfo`.
- Migliorata l'esplorazione autonoma della sandbox: l'agente può ora enumerare directory, cercare file e leggere documenti molto grandi senza saturare la context window.

### Calculator

- Nuova classe `local_tools/calculator.py`.
- Parsing tramite AST sicuro, senza utilizzo di `eval()`.
- Supporto a:
  - `+`
  - `-`
  - `*`
  - `/`
  - `//`
  - `%`
  - `**`
  - parentesi.
- Costanti matematiche:
  - `pi`
  - `e`
- Funzioni supportate:
  - `sqrt`
  - `abs`
  - `sin`
  - `cos`
  - `tan`
  - `asin`
  - `acos`
  - `atan`
  - `log`
  - `log10`
  - `exp`
  - `floor`
  - `ceil`
  - `round`
- Nuovo tool MCP:

  `calculator.evaluate`
  
Tutte le operazioni vengono validate tramite whitelist di nodi AST, operatori e funzioni consentite.

### Statistica

Nuova classe local_tools/statistics.py.

Nuovo tool MCP:

`statistics.compute`

La classe è `Stats_calc`; il tool esposto al modello è
`statistics.compute`. Operazioni supportate:

- mean
- median
- stdev
- variance
- min
- max
- sum
- count

Risultati strutturati con:

- esito dell'operazione;
- tipo di statistica richiesta;
- numero di campioni elaborati;
- risultato o errore.

### Conversione unità

Nuova classe `local_tools/unit_converter.py`.

Nuovo tool MCP:

`units.convert`

Supporto alle categorie:

Lunghezza

- mm
- cm
- m
- km

Massa

- mg
- g
- kg
- t

Tempo

- ms
- s
- min
- hour
- day

Temperatura

- c
- f
- k

Angolo

- deg
- rad

Dimensione dati

- b
- kb
- mb
- gb
- tb

Sistema di alias e normalizzazione delle unità:

meters → m
kilometers → km
hours → hour
celsius → c
fahrenheit → f
degrees → deg
ecc.

Conversioni dedicate per:

temperatura (con offset);
angoli (gradi/radianti).

Conversioni lineari per tutte le altre categorie.

### Feed RSS e Atom

Nuova classe `local_tools/feeder.py`.

Nuovo tool MCP:

`feed.read`

Supporto trasparente a feed RSS e Atom tramite un'unica API.

Parametro max_items con limite di sicurezza per evitare output eccessivi.

Estrazione strutturata di:

- titolo;
- link;
- data di pubblicazione;
- autore;
- sommario.

Pulizia automatica dell'HTML presente nei feed e restituzione dei metadati del feed:

- titolo;
- descrizione;
- link;
- tipo (rss, atom, ecc.).

Restituzione del numero totale di elementi disponibili, numero di elementi restituiti e indicazione di troncamento.

### Note

Questa iterazione amplia in modo significativo le capacità operative dell'agente. Oltre al filesystem sandboxato, Hagar dispone ora di strumenti affidabili per:

esplorare e ricercare contenuti;
leggere file molto grandi in modo incrementale;
eseguire calcoli matematici deterministici;
effettuare analisi statistiche;
convertire unità di misura appartenenti a domini differenti;
consumare fonti informative strutturate tramite feed RSS e Atom.

L'obiettivo resta privilegiare strumenti deterministici, strutturati e facilmente utilizzabili dai modelli tramite tool calling nativo.


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
