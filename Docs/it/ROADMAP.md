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
3. PermissionEvaluator;
4. igiene (audit, MCP, packaging, test live).

---

# 2. Priorità 1 — Memoria su Vault

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

Nomi provvisori; vedi "punti aperti" per la convenzione.

| tool | chi lo chiama | cosa fa |
|---|---|---|
| `memory.create_skill` | LLM | crea una memoria semantica **candidata** |
| `memory.list_skills` | LLM | elenca le memorie disponibili |
| `memory.get_context` | LLM | recupera turni di chat passati |

Firme proposte:

```text
memory.create_skill(title, content, kind="procedure", tags=[])
    -> {id, path, status, duplicate?}

memory.list_skills(kind=None, status=None, limit=20)
    -> [{id, title, kind, status, updated_at}]

memory.get_context(limit=10, session=None, query=None)
    -> [{turn, timestamp, question, answer}]
```

Comportamenti:

- `create_skill`: slug dal titolo, deduplicazione per slug, limite di
  lunghezza (`max_skill_chars`), frontmatter con `status: candidate`,
  `source_session`, `source_turn`, `model`, `created_at`; se esiste già
  uno slug uguale restituisce l'id esistente invece di duplicare.
- `list_skills`: legge solo il frontmatter, non i corpi; filtrabile per
  `kind` (`fact` / `procedure`) e `status`.
- `get_context`: senza `session` usa quella corrente; con `query` cerca
  per parole chiave nelle sessioni passate; `limit` obbligatorio per non
  riversare tutto il Vault nel contesto.

## 2.3 Struttura nel Vault

```text
<Vault>/Hagar/
  chat/2026-11-03-<session>.md      # una nota per sessione, turni in append
  skills/<slug>.md                  # una nota per memoria
```

Episodica (una nota per sessione, `turni` aggiunti in coda):

```markdown
---
session: a1b2c3d4
date: 2026-11-03
model: llama3.1:latest
turns: 12
---

## 2026-11-03T00:12:44+01:00 — turno 7f3a

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
  (`memory.write`, `memory.failed`); un Vault mancante o non scrivibile
  non ferma il harness.
- La memoria episodica è separata dall'audit: l'audit resta forense e
  contiene anche i dati dei tool.

## 2.6 Punti aperti

- **Nomi**: `memory.create_skill` / `memory.list_skills` /
  `memory.get_context` (coerenti con `filesystem.*`) oppure i nomi
  proposti in origine `skill_maker` / `skill_dir` / `get_context`.
- **Percorso del Vault**: `D:/Vault` non esiste su questa macchina; serve
  il percorso reale prima di implementare.
- **Iniezione automatica**: confermata l'idea, da decidere se sempre o
  solo quando il Vault è raggiungibile.
- **`kind`**: `fact` / `procedure` (proposta) oppure solo "skill".
- **Retention**: quante sessioni conservare, se riassumere le vecchie.
- **Revisione**: chi promuove una skill da `candidate` a `confirmed`
  (utente via comando, o un passo di consolidamento).

## 2.7 Non obiettivi (per ora)

- scrittura di memorie sul filesystem reale;
- modifica di note esistenti dell'utente;
- embedding / ChromaDB / ricerca semantica (dopo, se i volumi lo
  giustificano);
- scrittura autonoma di memorie fuori dal flusso esplicito.

---

# 3. Priorità 2 — Calling nativo

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
- Alcuni provider accettano una sola chiamata per turno: l'Agent deve
  continuare a eseguire un tool alla volta.

---

# 4. Priorità 3 — PermissionEvaluator

## 4.1 Obiettivo

Un unico punto di decisione per i permessi, che assorba `FS_Guardian` e
copra anche i tool di memoria.

## 4.2 Contenuto

- policy per tool e per radice (non solo un flag globale `write`);
- applicazione di `requires_confirmation`, oggi presente in
  `ToolDefinition` ma non usata: o si implementa, o si rimuove;
- conferma esplicita per operazioni distruttive (`delete_file`,
  sovrascritture) e limite per turno;
- audit della decisione (permesso concesso/negato, motivo);
- test unitari della matrice tool × radice × permesso.

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

- **MCP**: supporto SSE, notifica `notifications/initialized`,
  normalizzazione dei risultati in `ToolResult`, timeout e
  autenticazione.
- **Audit**: rotazione per dimensione, catena di hash per l'integrità,
  opzione di redazione dell'output dei tool, retention.
- **Test live**: marker `live` per Ollama e provider remoti, skippati di
  default, così la suite resta veloce ma verificabile.
- **Packaging**: entry point `hagar`, `--config` e `--model` da riga di
  comando, versione unica.
- **URL base**: collegare `model.host` come base URL anche ai provider
  remoti (proxy o endpoint self-hosted).
- **Legacy**: rimuovere o integrare `core/permissions.py` e
  `tools/filesystem.py`.
- **Documentazione**: mantenere ARCHITECTURE / ROADMAP / CHANGELOG
  allineati a ogni cambio di comportamento.

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

1. Memoria v0: episodica + tool semantici + audit delle memorie.
2. Calling nativo con fallback, misurato con il benchmark.
3. PermissionEvaluator e conferme.
4. Igiene: audit, MCP, packaging, test live.
