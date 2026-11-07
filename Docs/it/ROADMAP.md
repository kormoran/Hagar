# HAGAR — Roadmap

Versione corrente: 0.3.0 pubblicata
Ultimo aggiornamento: 2026-11-07

Le decisioni prese sono indicate come tali; i punti ancora aperti sono
elencati alla fine di ogni area. Le sezioni 1–9 sono lo storico fino
alla 0.3.0; il piano operativo corrente è la sezione 0.

---

# 0. Piano corrente (post-0.3.0)

## 0.1 Stato

Pubblicato:

- release GitHub `v0.3.0`;
- CI Linux/macOS/Windows con Python 3.11, 3.12 e 3.13;
- action aggiornate a Node 24;
- documentazione italiana più traduzioni in inglese, spagnolo, cinese,
  russo, portoghese e arabo;
- backend `lmstudio`, `openai`/`chatgpt` e `model.timeout`.

Completato dopo la release, non ancora rilasciato:

- `HarnessService`: turni, stato, progetti, eventi e fine sessione senza
  `input()`/`stdout`;
- `CommandService`: `/help`, `/tools`, `/status`, `/mcp`, `/audit`,
  `/project`, `/memory` con `CommandResult` strutturato;
- event bridge `Agent`/`ToolRegistry` → `tool.call`, `tool.result`,
  `permission.*`;
- GUI web locale `hagar web` con SSE, chat, progetti, stato e conferme
  ASK modali;
- `QueueConfirmationProvider` con timeout e risoluzione da GUI;
- `core/usage.py`: parsing token per OpenAI/LM Studio/DeepSeek, Claude,
  Gemini e Ollama; `UsageLedger` per sessione;
- sidebar GUI con token input/output/totale aggiornati via
  `usage.updated`;
- `MemoryIndex`: indice SQLite/FTS5 incrementale e ricostruibile;
- memoria SQLite come fonte primaria: sessioni, turni, skill e summary;
- comandi `/memory sessions`, `/memory chat`, `/memory backup`;
- tool `memory.search`, `/memory search`, `/memory reindex`,
  `/memory stats`;
- asset GUI separati in `web/index.html`, `web/style.css`, `web/app.js`.

## 0.2 Ordine delle prossime release

| Release | Obiettivo | Stato |
|---|---|---|
| **0.4.0** | Indice SQLite delle memorie | implementato |
| **0.4.x** | GUI: stop turno, cronologia, vision | prossimo |
| **0.5.0** | Subagenti | pianificato |
| **0.6.0** | Broker LLM | pianificato |
| **0.7.0** | Tool SQL read-only | pianificato |

L’ordine può cambiare, ma il vincolo è: **niente subagenti senza usage e
limiti; niente broker senza subagenti e model registry.**

## 0.3 0.4.0 — Indice SQLite delle memorie

Stato: implementato; resta la verifica sul Vault reale e l’eventuale
misura delle prestazioni.

- posizione: dati locali dell’app, non dentro il Vault sincronizzato;
- schema: note, skill, decisioni, sessioni, tag, FTS5;
- sync incrementale per path/hash/mtime;
- `rebuild()` atomico, indice cancellabile e ricostruibile;
- fallback alla ricerca lessicale se FTS5 non è disponibile;
- tool `memory.search` con filtri progetto/kind/status;
- `/memory reindex` e `/memory stats`;
- nessun path reale esposto al modello.

Criterio di uscita: cancellare il DB non perde memoria; ricostruirlo
restituisce gli stessi risultati.

## 0.4 0.4.x — GUI

- pulsante **Stop** del turno — implementato;
- vision: upload immagine nel composer, con adapter per provider —
  implementato (OpenAI/LM Studio, Claude, Gemini);
- cronologia chat visibile dopo un refresh — implementata come elenco
  delle chat passate con ricarica dal Vault, ripresa della sessione e
  **+ Nuova chat**;
- tab Chat, Chat history, Tool output, Audit, Thinking e Memories —
  implementate; Audit si disabilita se il log è spento, Thinking usa il
  reasoning se disponibile e altrimenti la timeline;
- browser memorie in sola lettura — implementato;
- comando `/usage` lato CLI — implementato;
- tool e provider LLM come plugin con entry point — implementato;
  audit sink rimandato.

La vision non deve entrare nella memoria come base64: solo hash e
descrizione.

## 0.5 0.5.0 — Subagenti

- [x] MVP sincrono: `AgentSpec`, `agent.run`, tool read-only, memoria
  read-only, conferme negate, audit `agent.*`, usage separato;
- [x] `agent.spawn/status/wait/result/cancel` con thread e fino a due
  subagenti concorrenti;
- [x] registry e workspace privato per figlio, input copiati e cleanup;
- [x] audit serializzato con lock;
- [x] `reason` obbligatorio e capability `AGENT_SPAWN` separata;
- [x] artifact store, mailbox e outbox `artifact.put`/`mailbox.send`,
  con capability `AGENT_DATA` e cleanup;
- [x] audit `artifact.discarded` per artifact non esportati;
- [ ] persistenza/orphan retention (solo se necessaria);
- [x] progetti e decisioni nello stesso database SQLite;
- [ ] export Markdown opzionale dal database;
- [x] timeout a parete di 5 minuti per subagente;
- [x] policy del figlio strettamente più restrittiva del padre;
- [x] `agent_id` negli eventi di padre, figli e registry;
- [x] ASK dei figli inoltrate all'utente con timeout 180 secondi e DENY;
- [ ] budget token/costo;
- [ ] `parent_id` su ogni evento interno del figlio;
- [ ] `audio.open`/`AudioInput`: il canale allegati è condiviso con le
  immagini, ma servono provider audio-nativi, formati e semantica ASR
  diversi; nessuna timeline;
- [ ] conferme ASK via console quando il prompt è bloccato (la GUI è
  già supportata).

## 0.6 0.6.0 — Broker LLM

- `ModelRegistry` con context window, tool calling, prezzi, latenza e
  località;
- `TaskProfile` con tool richiesti, sensibilità dati, budget e contesto;
- routing a regole/punteggio, non “un LLM sceglie il modello”;
- proposta di `AgentSpec` validata dall’host;
- il broker non concede mai permessi: può solo proporre un sottoinsieme;
- override umano e audit `broker.decision`.

## 0.7 0.7.0 — Tool SQL

- solo lettura nella prima versione;
- SQLite `mode=ro`, `PRAGMA query_only`, una sola istruzione;
- niente `ATTACH`, `PRAGMA` di scrittura o `load_extension`;
- timeout, limite righe/byte e audit della query;
- alias di database configurati, mai path arbitrari;
- capability `DATABASE_READ`;
- scrittura e database di rete solo in una fase successiva, con
  `DATABASE_WRITE` e `NETWORK`.

## 0.8 Punti aperti

- release workflow idempotente se la release esiste già;
- PyPI: rimandato, non blocca la 0.4;
- MCP OAuth Atlassian: Basic funziona, il flusso OAuth resta da
  validare;
- test live MCP/OAuth e provider remoti;
- manutenzione delle traduzioni: si rigenerano solo a release, non a
  ogni commit;
- concorrenza e scritture atomiche del Vault: da valutare prima di
  subagenti con memoria condivisa;
- document tool: contratto e protocollo definiti in `DOCUMENT_TOOL.md`;
  MVP CSV ancora da implementare.

## 0.9 Documentazione

`Docs/it` è l’unica fonte mantenuta durante lo sviluppo. Le directory
`Docs/en`, `Docs/es`, `Docs/zh`, `Docs/ru`, `Docs/pt` e `Docs/ar` si
rigenerano solo quando si prepara una release.

---

# 1. Direzione

Hagar è passato da "idea" a "sistema funzionante" (v0.1) e poi a un
harness con audit, backend multipli e suite di test (v0.2 in corso). Il
prossimo salto non è aggiungere tool: è dare al sistema una **memoria** e
un modo di chiamare i tool meno fragile del JSON testuale.

Ordine deciso:

1. memoria su Vault;
2. calling nativo per i provider che lo supportano;
3. PermissionEvaluator — **v1 fatta** (policy.yaml, ASK, audit);
4. igiene (audit, MCP, packaging, test live).

---

# 2. Priorità 1 — Memoria su Vault

## 2.0 Stato: v2 implementata (2026-11-04)

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

## 2.1 Decisioni prese

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

## 2.2 Tool previsti

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

## 2.3 Struttura nel Vault

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

## 2.4 Configurazione

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

## 2.5 Comportamento dell'harness

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

## 2.6 Punti aperti

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

## 2.7 Non obiettivi (per ora)

- scrittura di memorie sul filesystem reale;
- modifica di note esistenti dell'utente;
- embedding / ChromaDB / ricerca semantica (dopo, se i volumi lo
  giustificano);
- scrittura autonoma di memorie fuori dal flusso esplicito.

---

# 3. Priorità 2 — Calling nativo (v1, fatta)

**Stato:** implementato il 2026-11-03. `native_step()` per i quattro
provider, schema dei parametri da `ToolDefinition`, messaggi canonici
`tool`, più chiamate per turno, fallback automatico su HTTP 400/404/422
e `--no-native-tools`. Verificato live su Ollama e DeepSeek; Claude e
Gemini restano da provare. Misurato con `tools/bench_native.py`: nessun
protocollo vince su tutti i modelli (nativo più veloce, testo a volte più
preciso). Resta da affinare per i modelli locali che ignorano i tool.

## 3.1 Obiettivo

Eliminare la fragilità del protocollo JSON testuale: niente più
riparazioni, argomenti validati dallo schema del provider, risultati
strutturati.

## 3.2 Approccio

- Mantenere il protocollo testuale come **fallback** per i modelli che
  non supportano il calling nativo o lo fanno male.
- Aggiungere a `LLMClient` una capacità dichiarata
  (`supports_native_tools`) e un percorso nativo.
- L'`Agent` deve gestire entrambi: `ToolCall` testuale oppure chiamata
  nativa con id; il risultato torna nel formato atteso dal provider.
- Il benchmark misura il miglioramento (riparazioni per turno,
  correttezza degli argomenti).

## 3.3 Trasporto per provider

| provider | richiesta | risultato tool |
|---|---|---|
| `ollama` | `tools` in `/api/chat` | messaggio con ruolo `tool` |
| `deepseek` | `tools` (OpenAI) | ruolo `tool` + `tool_call_id` |
| `claude` | `tools` + blocchi `tool_use` | blocco `tool_result` |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 3.4 Rischi

- I modelli locali piccoli spesso non usano bene il calling nativo: serve
  il fallback automatico.
- Cambia il plumbing dei messaggi: test per provider e per il percorso di
  fallback sono obbligatori.
- Alcuni modelli restituiscono più chiamate nello stesso turno: l'Agent
  le esegue tutte, nel limite del turno.

---

# 4. Priorità 3 — PermissionEvaluator

## 4.1 Stato: v1 implementata

Realizzato:

- `Capability`, `Effect`, `Rule`, `Subject`, `Resource`, `Decision` e
  `PermissionEvaluator` in `core/permissions.py`;
- `policy.yaml` letto **prima** del LLM, con fallback a `DENY` totale e
  warning su audit e chat;
- tetto di sistema derivato da `permissions.read/write/shell`;
- scope per `tools` (glob), `paths` e `namespaces` (prefissi);
- `ASK` con `ConsoleConfirmation` (`lo faccio? (y/N)`, default N);
- applicazione in `ToolRegistry.execute` e audit di
  `permission.decision` / `permission.confirmation`;
- `ToolDefinition.capabilities` per tutti i tool (filesystem e MCP);
- `requires_confirmation` applicato come pavimento di ASK;
- 347 test raccolti, 1 skip.

## 4.2 Restano da fare

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

I percorsi virtuali risolverebbero anche l'esposizione dei percorsi
assoluti della sandbox.

---

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
- **Test live**: marker `live`, esclusi di default, `--live` per Ollama
  e provider remoti (questi ultimi skippati senza chiave).
- **Packaging**: metadati completi, entry point `hagar`, `--config`,
  `--model`, `--no-memory`, `--version`, versione unica.
- **URL base**: `model.host` vale per tutti i provider.
- **Legacy**: rimossi `tools/filesystem.py` e `llm/tool_result.py`.

Restano:

- device flow / DPoP per MCP OAuth;
- compattazione delle sessioni di audit;
- conferme GUI per `ASK`;
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

# 8. Ordine di lavoro

1. Memoria v2: fatta (ciclo di vita, review CLI, iniezione confermate);
   restano retention chat, ricerca semantica e GUI.
2. PermissionEvaluator: v1 fatta; restano conferme GUI e policy
   dinamiche.
3. Igiene: fatta (packaging, test live, MCP auth/OAuth, audit con
   retention, base URL, legacy).
4. Calling nativo: v1 fatta; resta la misura col benchmark.
5. Release 0.3.0: preparata per GitHub, con CI multipiattaforma e
   workflow di release.

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
