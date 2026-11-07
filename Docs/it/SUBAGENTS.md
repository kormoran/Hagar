# Subagenti — MVP sincrono

**Stato:** MVP implementato  
**Data:** 2026-11-07  
**Tool:** `agent.run`

## 1. Cosa fa

Il modello può delegare un compito a un subagente sincrono:

```text
agent.run(task, context?)
```

Il padre resta in attesa. Il figlio:

- usa lo stesso modello del padre, ma un client LLM separato;
- ha un registry separato;
- vede solo i tool con capability di lettura o calcolo;
- non può usare `filesystem.chdir`;
- non può usare `agent.run`;
- non scrive nella memoria;
- non può chiedere conferme all’utente;
- non ha memoria automatica del padre: riceve solo `task` e `context`.

Il risultato è JSON compatto:

```json
{
  "agent_id": "a-1a2b3c4d",
  "status": "completed",
  "answer": "...",
  "error": null,
  "usage": {
    "input_tokens": 168,
    "output_tokens": 56,
    "cached_input_tokens": 0,
    "reasoning_tokens": 0,
    "total_tokens": 224,
    "calls": 2
  },
  "duration_ms": 1234.5
}
```

## 2. Limiti dell’MVP

- un solo subagente per volta;
- nessun annidamento;
- nessun timeout a parete: vale `max_tool_calls`;
- nessuna GUI dedicata;
- nessuna scrittura di memoria;
- nessuna conferma interattiva;
- nessun budget token/costo configurabile;
- il client LLM è nuovo, ma il modello è lo stesso del padre;
- un errore del modello può diventare una risposta testuale del figlio, non
  necessariamente `status: failed`.

Il manager restituisce `failed` quando la costruzione o l’esecuzione del
figlio solleva un’eccezione. Gli errori interni dell’agente che vengono
restituiti come testo possono quindi apparire come `completed`.

## 3. Componenti isolati

| Componente | Padre | Figlio |
|---|---|---|
| LLM client | `harness.llm` | nuova istanza, stesso modello |
| Tool registry | completo | filtrato read-only |
| Memoria | `MemoryStore` | nessuna scrittura, `memory=None` nell’agent |
| Sandbox | condiviso in lettura | nessun `chdir` |
| Conferme | provider normale | `DenyAllConfirmation` |
| Usage | ledger padre | ledger separato |
| Audit | condiviso | eventi `agent.*` |

Il subagente può usare i tool di memoria in lettura perché sono nel
registry filtrato. Non ha però il contesto automatico del padre: il
padre deve passare il contesto necessario nel campo `context`.

## 4. Tool ammessi

Il registry del figlio include i tool le cui capability sono un
sottoinsieme di:

```text
FILESYSTEM_READ
MEMORY_READ
COMPUTE
```

Sono esclusi esplicitamente:

```text
filesystem.chdir
agent.run
```

Sono esclusi per capability:

- scrittura filesystem;
- creazione, rinomina, copia, cancellazione;
- scrittura memoria;
- rete;
- MCP;
- shell.

## 5. Audit

Eventi registrati dal manager:

```text
agent.spawned
agent.started
agent.finished
agent.failed
```

Campi principali:

```text
agent
parent
task
max_tool_calls
status
usage
duration_ms
error
```

Gli eventi interni del figlio (`turn.start`, `turn.answer`, `tool.call`)
restano nel normale audit Hagar, ma non hanno ancora un campo `agent`.
Questa è una lacuna nota dell’MVP.

## 6. Concorrenza

`SubagentManager` ha un lock e un flag `busy`.

- se un subagente è già in esecuzione, `agent.run` restituisce un errore
  strutturato;
- non ci sono thread multipli;
- il padre rimane bloccato durante l’esecuzione.

Questa scelta evita, per ora, race su audit, memoria, sandbox e provider.

## 7. Test

`tests/test_subagents.py` copre:

- esecuzione con tool read-only;
- esclusione di scrittura e `agent.run`;
- passaggio del contesto;
- rifiuto del secondo subagente mentre il primo è in corso;
- errore di costruzione del provider;
- eventi audit.

Test live eseguito con LM Studio e `gemma-3-27b-it`.

## 8. Prossimi passi

### Fase 2 — Manager

- `agent.spawn`, `agent.status`, `agent.wait`, `agent.cancel`,
  `agent.result`;
- thread e timeout;
- stato nella GUI;
- eventi con `agent_id`.

### Fase 3 — Isolamento

- sandbox separato;
- registry clone completo;
- budget token/tempo;
- conferme delegate;
- profondità e concorrenza.

### Fase 4 — Memoria e persistenza

- contesto automatico read-only;
- scritture mediate dal padre;
- result store;
- eventuale isolamento a processi.
