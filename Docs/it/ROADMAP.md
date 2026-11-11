# HAGAR — Roadmap

Versione corrente: 0.6.0 (in preparazione)
Ultimo aggiornamento: 2026-11-09

Le decisioni prese sono indicate come tali; i punti ancora aperti sono
elencati alla fine di ogni area. Le sezioni 1–9 sono lo storico fino
alla 0.6.0; il piano operativo corrente è la sezione 0.

---

# 0. Piano corrente (post-0.6.0)

## 0.1 Ordine delle prossime release

| Release | Obiettivo | Stato |
|---|---|---|
| **0.6.0** | Runtime safety + AIsh | in preparazione |
| **0.7.0** | Broker LLM | prossimo |
| **0.8.0** | Tool SQL read-only | congelato |

L’ordine può cambiare, ma il vincolo è: **niente subagenti senza usage e
limiti; niente broker senza subagenti e model registry.**

## 0.2 0.7.0 — Broker LLM

- schede tecniche JSON e benchmark dei modelli (`/models test`);
- rilevamento hardware CPU/RAM/GPU (`/models hardware`);
- `ModelRegistry` con context window, tool calling, prezzi, latenza e
  località;
- `TaskProfile` con tool richiesti, sensibilità dati, budget e contesto;
- routing a regole/punteggio, non “un LLM sceglie il modello”;
- proposta di `AgentSpec` validata dall’host;
- il broker non concede mai permessi: può solo proporre un sottoinsieme;
- override umano e audit `broker.decision`.

## 0.3 0.8.0 — Tool SQL

- solo lettura nella prima versione;
- SQLite `mode=ro`, `PRAGMA query_only`, una sola istruzione;
- niente `ATTACH`, `PRAGMA` di scrittura o `load_extension`;
- timeout, limite righe/byte e audit della query;
- alias di database configurati, mai path arbitrari;
- capability `DATABASE_READ`;
- scrittura e database di rete solo in una fase successiva, con
  `DATABASE_WRITE` e `NETWORK`.

## 0.4 Punti aperti

- release workflow idempotente se la release esiste già;
- PyPI: rimandato;
- MCP OAuth Atlassian: Basic funziona, il flusso OAuth resta da
  validare;
- test live MCP/OAuth e provider remoti;
- manutenzione delle traduzioni: si rigenerano solo a release, non a
  ogni commit;
- document tool: contratto e protocollo definiti in `DOCUMENT_TOOL.md`;
  MVP CSV ancora da implementare.

## 0.4.1 Versione completa filesystem — congelata

Implementato ora:

- `edit_file` con scrittura atomica;
- checkpoint del turno e `/undo`;
- timeout per tool e repeat guard;
- output spill e compaction del contesto.

L'MVP implementato copre `edit_file`, scrittura atomica,
read-before-overwrite/delete/rename e versione `mtime_ns+size`.
La versione completa è congelata; non entra nella prossima release:

- `edit_file` con patch a più hunk e diff;
- hash del contenuto oltre a `mtime_ns`/`size`;
- scrittura atomica con controllo CAS a livello di filesystem;
- osservazione per singolo agente con isolamento esplicito tra padre e
  subagenti;
- audit `fs.observed`, `fs.guard_denied`, `fs.stale`;
- copertura di rename/delete di directory;
- integrazione GUI e messaggi di recupero guidato.

## 0.4.2 AIsh — implementata nella 0.6.0

`aish.exec` è una shell semantica sopra i tool Hagar, con policy `DENY`
predefinita. Comandi implementati: navigazione, lettura, testo puro,
pipeline e mutazioni di file singoli. Non esegue programmi host,
redirezioni, variabili o command substitution.
`text.transform` fornisce le operazioni testuali bounded usate da AIsh.

## 0.4.3 dev.run — implementato

`dev.list` e `dev.run` eseguono ricette fidate per test, debug e build.
`recipes.yaml` sta fuori dalla sandbox, viene letto all'avvio e non ha
hot reload. `DEV_EXEC` è DENY di default; il backend è solo host.

Il container resta congelato per un futuro accesso diretto a
filesystem/programmi reali, mai dentro la sandbox.

## 0.4.4 Boxed transform — implementate

`box.list` e `box.run` eseguono `summarize`, `translate` e
`extract_json` con prompt fisso, input/output su file e nessuna memoria
o tool. `BOX_EXEC` è DENY di default.

Sono le primitive del futuro DSL.

## 0.4.5 Hagar Flow — MVP

`flow.run` esegue un sottoinsieme lineare di Python con validatore AST e
interprete Hagar, senza `eval`/`exec`. Primitive `fs.*` e `box.*`, limiti
di step e tool call. `FLOW_EXEC` è DENY di default.

HIR, parallelismo e subagenti restano fuori dall’MVP.

## 0.5 Documentazione

`Docs/it` è l’unica fonte mantenuta durante lo sviluppo. Le directory
`Docs/en`, `Docs/es`, `Docs/zh`, `Docs/ru`, `Docs/pt` e `Docs/ar` si
rigenerano solo quando si prepara una release.

---

## 1.0 Stato: v2 implementata (2026-11-04)

Realizzato:

- episodica scritta dall'harness, una nota per sessione;
- iniezione automatica degli ultimi `context_turns` turni;
- tool `memory.create_skill`, `memory.list_skills`, `memory.get_context`;
- provenance (`source_session`, `source_turn`, `model`), stato
  `candidate`, deduplicazione per slug;
- policy `MEMORY_READ`/`MEMORY_WRITE` e namespace `chat` / `skills`;
- vault assente → memoria disattivata con avviso, harness attivo;
- ciclo di vita `candidate` → `confirmed` → `archived` con revisione
  umana da CLI (`/memory review`, `confirm`, `archive`);
- iniezione automatica delle sole skill confermate, top 3 per match
  lessicale;
- retention opzione A: nessuna cancellazione automatica, solo archivio;
- memoria di progetto separata dalle skill: decisioni, alternative,
  motivazioni, stato e provenance;
- selezione progetto all'avvio, `--project`/`--free`, comandi
  `/project`;
- summary di fine sessione con fallback, transcript in `archive/chat/`
  e link/hash nel summary;
- review delle decisioni a fine sessione; se rifiutata, restano
  `candidate` con `auto_saved: true`;
- contesto a indice con budget `max_context_chars` (caratteri, non
  token) e `memory.project_context` per i dettagli;
- `project_max_active` per la richiesta di archiviazione del progetto;
- consultazione archivio con `memory.archive_search`,
  `memory.archive_read`, `/memory archive search|read`, filtro per
  progetto e transcript con `project` nel frontmatter.

Restano: retention delle chat, ricerca semantica, GUI.

## 1.1 Decisioni prese

- **Episodica scritta dall'harness.** I turni di chat vengono registrati
  dal harness di default: è un verbale meccanico, non un giudizio del
  modello. Nessun turno mancante, nessuna memoria inventata.
- **Semantica scritta dal LLM, su richiesta.** Il modello può proporre
  una memoria (skill) solo attraverso un tool dedicato. La proposta è
  esplicita, attribuibile e rivedibile — la Prima Legge vieta di
  trattarla come verità.
- **Solo Vault Obsidian.** Nessuna scrittura sul filesystem reale per la
  memoria (per ora). La `filesystem.sandbox` resta la sandbox operativa.
- **Il Vault non si riscrive.** I tool aggiungono note o sezioni; non
  sovrascrivono note curate dall'utente.
- **Progetti espliciti.** Il progetto si sceglie all'avvio dalla lista
  dei progetti attivi, oppure con `--project`; `--free` e “attività
  libera” non hanno memoria di progetto.
- **Decisioni di progetto.** Sono separate dalle skill: registrano
  decisioni, alternative e motivazioni. Si propongono come `candidate`
  e si rivedono a fine sessione; se la review viene rifiutata restano
  candidate con `auto_saved: true`, non diventano verità automatiche.
- **Niente quote token.** Il contesto è limitato per costruzione:
  indice del progetto, titoli delle decisioni, summary e
  `max_context_chars` in caratteri. Non si misura la context window del
  modello.
- **Archivio, non cancellazione.** Transcript e decisioni archiviate
  restano nel Vault; l'archiviazione di un progetto è reversibile.

## 1.2 Tool previsti

Nomi implementati nel namespace `memory.*`:

| tool | chi lo chiama | cosa fa |
|---|---|---|
| `memory.create_skill` | LLM | crea una memoria semantica **candidata** |
| `memory.list_skills` | LLM | elenca le memorie disponibili |
| `memory.get_context` | LLM | recupera turni di chat passati |

Firme implementate:

```text
memory.create_skill(title, content, kind="procedure", tags=None)
    -> {id, title, kind, status, tags, created_at, source_*, path, duplicate}

memory.list_skills(kind=None, status=None, limit=20)
    -> [{id, title, kind, status, tags, created_at, source_*}]

memory.get_context(limit=5, query=None, session=None)
    -> [{session, turn, timestamp, question, answer}]
```

Comportamenti:

- `create_skill`: slug dal titolo, deduplicazione per slug, limite di
  lunghezza (`max_skill_chars`), frontmatter con `status: candidate`,
  `source_session`, `source_turn`, `model`, `created_at`; se esiste già
  uno slug uguale restituisce l'id esistente invece di duplicare.
- `list_skills`: legge frontmatter e corpo (serve al recall), filtrabile
  per `kind` (`fact` / `procedure`) e `status`.
- `get_context`: senza `session` cerca in tutte le sessioni; con `query`
  cerca per parole chiave nei turni passati; `limit` viene limitato a
  1..50 per non riversare tutto il Vault nel contesto.

## 1.3 Struttura nel Vault

```text
<Vault>/Hagar/
  chat/2026-11-03-<session>.md      # una nota per sessione, turni in append
  skills/<slug>.md                  # una nota per memoria
```

Episodica (una nota per sessione, turni aggiunti in coda):

```markdown
---
session: a1b2c3d4
type: chat
created: 2026-11-03T00:12:44+01:00
---

# Chat 2026-11-03

## 2026-11-03T00:12:44+01:00 · 7f3a

**Utente:** ...
**Hagar:** ...
```

Semantica (una nota per skill):

```markdown
---
id: usa-uv-per-python
title: Usare uv per i progetti Python
kind: procedure
status: candidate
tags: [python, tooling]
source_session: a1b2c3d4
source_turn: 7f3a
model: llama3.1:latest
created_at: 2026-11-03T00:15:02+01:00
---

Passi / contenuto proposto dal modello.
```

## 1.4 Configurazione

```yaml
vault:
  path: <percorso reale>

memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  max_skill_chars: 4000
```

## 1.5 Comportamento dell'harness

- A fine turno: aggiunge domanda e risposta alla nota di sessione (solo
  conversazione, **non** output dei tool: quelli restano nell'audit).
- All'inizio del turno: inietta gli ultimi `context_turns` turni e fino
  a `context_skills` skill **confermate** pertinenti (match lessicale),
  senza aspettare che il modello chiami `get_context`.
- Ogni scrittura o revisione di memoria produce un evento di audit
  (`memory.enabled`, `memory.disabled`, `memory.context`, `memory.turn`,
  `memory.review`, `memory.status`, `memory.failed`); un Vault mancante o
  non scrivibile non ferma il harness.
- La memoria episodica è separata dall'audit: l'audit resta forense e
  contiene anche i dati dei tool.

## 1.6 Punti aperti

- **Retention chat**: quante sessioni conservare, se riassumere le
  vecchie; la 0.2.0 non cancella nulla.
- **Ricerca**: indice (SQLite FTS) o embedding quando i volumi
  cresceranno; oggi è per parola chiave.
- **GUI**: conferma ASK con dialog modale anche per le scritture di
  memoria e per la review.
- **Selezione del contesto**: oggi turni recenti globali, indice del
  progetto e top 3 skill confermate per match lessicale, senza
  rilevanza semantica.
- **Consolidamento decisioni**: il progetto può superare
  `project_max_active`; oggi Hagar propone l'archiviazione, non il
  merge delle decisioni duplicate.

## 1.7 Non obiettivi (per ora)

- scrittura di memorie sul filesystem reale;
- modifica di note esistenti dell'utente;
- embedding / ChromaDB / ricerca semantica (dopo, se i volumi lo
  giustificano);
- scrittura autonoma di memorie fuori dal flusso esplicito.

---

## 2 Obiettivo

Eliminare la fragilità del protocollo JSON testuale: niente più
riparazioni, argomenti validati dallo schema del provider, risultati
strutturati.

## 2.1 Approccio

- Mantenere il protocollo testuale come **fallback** per i modelli che
  non supportano il calling nativo o lo fanno male.
- Aggiungere a `LLMClient` una capacità dichiarata
  (`supports_native_tools`) e un percorso nativo.
- L'`Agent` deve gestire entrambi: `ToolCall` testuale oppure chiamata
  nativa con id; il risultato torna nel formato atteso dal provider.
- Il benchmark misura il miglioramento (riparazioni per turno,
  correttezza degli argomenti).

## 2.2 Trasporto per provider

| provider | richiesta | risultato tool |
|---|---|---|
| `ollama` | `tools` in `/api/chat` | messaggio con ruolo `tool` |
| `deepseek` | `tools` (OpenAI) | ruolo `tool` + `tool_call_id` |
| `claude` | `tools` + blocchi `tool_use` | blocco `tool_result` |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 2.3 Rischi

- I modelli locali piccoli spesso non usano bene il calling nativo: serve
  il fallback automatico.
- Cambia il plumbing dei messaggi: test per provider e per il percorso di
  fallback sono obbligatori.
- Alcuni modelli restituiscono più chiamate nello stesso turno: l'Agent
  le esegue tutte, nel limite del turno.

---

# 3. Priorità 3 — PermissionEvaluator

Stato: v1 implementata

## 3.1 Restano da fare

- `ConfirmationProvider` per la GUI (dialog modale) e per l'esecuzione
  non interattiva (deny di default);
- policy dinamiche per task/ruolo, con sola riduzione a runtime (un
  agente può ridursi i permessi, mai allargarli da solo);
- capability dei tool MCP assegnate dalla configurazione, non
  dichiarate dal server;
- più soggetti in esecuzione contemporanea (più agenti con policy
  diverse);
- oggetti-risorsa per memoria e percorsi, non solo tool.

---

# 5. Priorità 4 — AIsh

Shell dedicata agli LLM, concettualmente simile a Bash ma senza alcun
accesso alla shell reale:

- nessuna esecuzione di comandi host;
- utilizzo esclusivo di tool registrati;
- filesystem simulato e percorsi virtuali (`workspace://`);
- integrazione con tool MCP;
- pipe e comandi virtuali.

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```


# 6. Igiene e robustezza

Fatta (2026-11-03):

- **MCP**: risposte `text/event-stream`, notifica
  `notifications/initialized`, normalizzazione dei risultati a testo
  (blocchi `text`, `structuredContent`, errori `isError`).
- **MCP auth**: bearer o header personalizzato, token solo da ambiente,
  server saltato con `mcp.failed` se il token manca.
- **MCP OAuth**: flusso authorization code + PKCE con browser, discovery
  RFC 9728/8414, dynamic registration, cache token, refresh e retry 401.
- **Audit**: rotazione a `max_bytes`, catena di hash verificabile con
  `verify_chain`, redazione dell'output dei tool con
  `include_outputs: false`.
- **Audit retention**: backup timestampati e `audit.max_files` (default
  100, include il file attivo) con pruning dei più vecchi.
- **URL base**: `model.host` vale per tutti i provider.

Restano:

- device flow / DPoP per MCP OAuth;
- compattazione delle sessioni di audit;
- allineamento continuo della documentazione.

---

# 7. Più avanti

- ricerca semantica sul Vault (indice, poi eventualmente ChromaDB);
- RAG sui documenti;
- gestione attività e scratchpad persistente;
- osservazione del vault (note modificate dall'utente);
- agente personale permanente;
- provider aggiuntivi (OpenAI è quasi gratis: stesso client di DeepSeek
  con un base URL diverso).

---

# 9. Tool locali

Stato al 2026-11-05:

- filesystem v2: `list_dir`, `read_chunk`, `rename`, `copy_file`,
  `search`, oltre ai tool esistenti;
- `local_tools/`: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `feed.read` (provider locali, non server MCP);
- capability `COMPUTE` sempre nel tetto, `NETWORK` controllata da
  `permissions.network` e dalla policy (feed in `ask`);
- limiti di scrittura: `max_write_bytes`, `min_free_bytes`,
  `session_write_bytes` e `ask_over_bytes` con preflight unico;
- `feed.read` con policy SSRF: solo indirizzi globali, redirect
  rivalidati, niente credenziali nell'URL;
- filesystem con radice virtuale `/home/ai`, alias obbligatori e
  permessi per mount (`R`/`W`/`X`);
- runner POSIX `tools/run_tests.sh` accanto a quello Windows.

Punti aperti:

- DNS rebinding: la risoluzione viene validata, ma `requests` risolve
  di nuovo il nome al momento della connessione; serve un resolver
  pinnato o un adapter dedicato per chiudere il caso;
- il calcolatore è volutamente limitato (niente algebra simbolica);
- valutare un limite di dimensione anche per gli altri output dei tool.

Chiuso come responsabilità dell'utente:

- hard link, mount e junction dentro le directory allowed non sono
  controllati da Hagar. Per isolamento totale l'utente deve garantire
  che non ce ne siano; Hagar non li crea e non li rileva;
- race TOCTOU: Hagar non usa `openat2`, `O_NOFOLLOW` su ogni componente o
  handle Windows e non garantisce atomicità tra check e operazione. La
  race richiede un processo locale concorrente con accesso in scrittura;
  è uno scenario malevolo o di ambiente compromesso, non uso normale.
  Per isolamento totale servono volume dedicato, utente separato, mount
  namespace o container.
