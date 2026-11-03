# HAGAR — Roadmap

Versione corrente: 0.2.0 (in sviluppo)
Ultimo aggiornamento: 2026-11-03

Le decisioni prese sono indicate come tali; i punti ancora aperti sono
elencati alla fine di ogni area.

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

## 2.0 Stato: v1 implementata (2026-11-03)

Realizzato:

- episodica scritta dall'harness, una nota per sessione;
- iniezione automatica degli ultimi `context_turns` turni;
- tool `memory.create_skill`, `memory.list_skills`, `memory.get_context`;
- provenance (`source_session`, `source_turn`, `model`), stato
  `candidate`, deduplicazione per slug;
- policy `MEMORY_READ`/`MEMORY_WRITE` e namespace `chat` / `skills`;
- vault assente → memoria disattivata con avviso, harness attivo.

Restano: revisione delle skill, retention, ricerca semantica, GUI.

## 2.1 Decisioni prese

- **Episodica scritta dall'harness.** I turni di chat vengono registrati
  dal harness di default: è un verbale meccanico, non un giudizio del
  modello. Nessun turno mancante, nessuna memoria inventata.
- **Semantica scritta dal LLM, su richiesta.** Il modello può proporre
  una memoria (skill) solo attraverso un tool dedicato. La proposta è
  esplicita, attribuibile e rivedibile — la Prima Legge vieta di
  trattarla come verità.
- **Solo Vault Obsidian.** Nessuna scrittura sul filesystem reale per la
  memoria (per ora). Il `filesystem.allowed` resta la sandbox operativa.
- **Il Vault non si riscrive.** I tool aggiungono note o sezioni; non
  sovrascrivono note curate dall'utente.

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
- `list_skills`: legge solo il frontmatter, non i corpi; filtrabile per
  `kind` (`fact` / `procedure`) e `status`.
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
  max_skill_chars: 4000
```

## 2.5 Comportamento dell'harness

- A fine turno: aggiunge domanda e risposta alla nota di sessione (solo
  conversazione, **non** output dei tool: quelli restano nell'audit).
- All'inizio del turno: inietta gli ultimi `context_turns` turni nel
  prompt, senza aspettare che il modello chiami `get_context`.
- Ogni scrittura di memoria produce un evento di audit
  (`memory.enabled`, `memory.disabled`, `memory.context`, `memory.turn`,
  `memory.failed`); un Vault mancante o non scrivibile non ferma il
  harness.
- La memoria episodica è separata dall'audit: l'audit resta forense e
  contiene anche i dati dei tool.

## 2.6 Punti aperti

- **Retention**: quante sessioni conservare, se riassumere le vecchie.
- **Revisione**: chi promuove una skill da `candidate` a `confirmed`
  (utente via comando, o un passo di consolidamento).
- **Ricerca**: indice (SQLite FTS) o embedding quando i volumi
  cresceranno; oggi è per parola chiave.
- **GUI**: conferma ASK con dialog modale anche per le scritture di
  memoria.
- **Selezione del contesto**: oggi vengono iniettati gli ultimi turni
  globali, senza rilevanza semantica.

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

1. Memoria v1: fatta; restano revisione, retention e ricerca.
2. PermissionEvaluator: v1 fatta; restano conferme GUI e policy
   dinamiche.
3. Igiene: fatta (packaging, test live, MCP, audit, base URL, legacy);
   restano autenticazione MCP e retention dell'audit.
4. Calling nativo: v1 fatta; resta la misura col benchmark.
