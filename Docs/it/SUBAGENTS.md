# Subagenti — fase asincrona

**Stato:** implementato
**Data:** 2026-11-07  
**Tool:** `agent.spawn`, `agent.status`, `agent.wait`, `agent.result`,
`agent.cancel`, `agent.run` (compatibilità sincrona), `artifact.*`,
`mailbox.*`

## 1. Cosa fanno

Il modello può avviare fino a due subagenti concorrenti:

```text
agent.spawn(task, reason, context?, inputs?) -> agent_id
agent.status(agent_id) -> stato
agent.wait(agent_id, timeout?) -> risultato
agent.result(agent_id) -> risultato
agent.cancel(agent_id) -> ok
```

`spawn` ritorna subito. Il padre può continuare a lavorare e raccogliere
i risultati quando servono. `agent.run` resta come scorciatoia
`spawn + wait` per compatibilità.

`reason` è obbligatorio: viene registrato in audit ed è la motivazione
per cui il padre delega il lavoro. Il tool richiede la capability
`AGENT_SPAWN`; il figlio non la riceve, quindi non può crearne altri.
`permissions.agents: true` è il tetto di sistema necessario.

Ogni figlio:

- usa lo stesso modello locale del padre, ma un client LLM separato;
- ha un registry separato;
- vede solo i tool con capability `FILESYSTEM_READ`,
  `MEMORY_READ` e `COMPUTE`, più `AGENT_DATA`;
- non può usare `agent.*` né `filesystem.chdir`;
- legge solo il proprio workspace;
- non scrive nella memoria;
- non può chiedere conferme all’utente.

## 2. Workspace privato

Per ogni figlio viene creato un workspace temporaneo:

```text
<hagar-temp>/hagar-subagent-<id>/
```

Il figlio lo vede come:

```text
/home/ai/workspace
```

Il workspace è in sola lettura. Prima dell’avvio, il manager copia gli
input indicati dal padre:

```text
agent.spawn(
    task="analizza il CSV",
    reason="i file sono indipendenti e vanno analizzati in parallelo",
    inputs=["/home/ai/workspace/report.csv"]
)
```

Regole:

- gli input devono essere file nel sandbox del padre;
- il padre deve avere il permesso di lettura;
- il nome del file viene preservato;
- due input con lo stesso nome sono un errore;
- il figlio non vede il path host;
- il workspace viene eliminato alla fine del turno.

Il padre scrive solo nel proprio workspace. Il workspace del figlio è
fuori dalle radici del padre, quindi non è raggiungibile dai suoi tool.

## 2.1 Outbox, artifact e mailbox

Il figlio non scrive nel workspace. Per produrre dati usa l'outbox:

```text
artifact.put(text, kind?, mime_type?)       -> artifact_id
artifact.put_file(path, mime_type?)          -> artifact_id
mailbox.send(text, artifacts?)               -> message
```

`artifact.put_file` legge un file dal workspace read-only del figlio e
lo copia nello store gestito da Hagar.

Il padre legge con:

```text
artifact.list()
artifact.read(artifact_id, offset?, length?)
artifact.save_to(artifact_id, path, overwrite?)
mailbox.inbox(cursor?, limit?)
mailbox.read(message_id)
mailbox.ack(message_id)
```

`artifact.save_to` copia l'intero artifact in un path scrivibile del
sandbox del padre senza far passare il contenuto dal contesto. È
l'operazione da usare per artifact più grandi della finestra del modello:
il modello legge solo i chunk che gli servono e salva il file completo
con `save_to`.

`save_to` richiede `AGENT_DATA`, `FILESYSTEM_WRITE` e
`FILESYSTEM_CREATE`; la policy lo tratta come una scrittura e può
chiedere conferma. Non accetta path host arbitrari.

Limiti iniziali:

| Elemento | Limite |
|---|---|
| artifact singolo | 50 MB |
| totale artifact per turno | 256 MB |
| artifact per turno | 200 |
| lettura per chiamata | 256 KB |
| testo di un messaggio | 64 KB |
| messaggi per mailbox | 100 |

Gli artifact sono file temporanei fuori dal Vault, con hash SHA-256 e
metadati. La mailbox contiene solo testo e riferimenti `artifact_id`.
Alla fine del turno store e mailbox vengono svuotati.

## 3. Limiti dell’implementazione

- massimo **2** subagenti attivi (configurabile nel manager come
  `max_concurrent`);
- solo modelli locali;
- nessun annidamento: il registry del figlio esclude `agent.*`;
- nessun budget token/tempo oltre a `max_tool_calls`;
- nessun timeout a parete sul singolo turno del figlio;
- nessuna GUI dedicata;
- nessuna scrittura di memoria;
- conferme negate;
- artifact e mailbox sono effimeri: spariscono a fine turno;
- gli eventi interni del figlio (`turn.*`, `tool.*`) non hanno ancora
  un campo `agent` nell’audit.

Alla fine del turno del padre:

1. `finish_turn()` attende i figli per un timeout;
2. annulla quelli ancora attivi;
3. elimina i workspace;
4. dimentica i job.

## 4. Componenti isolati

| Componente | Padre | Figlio |
|---|---|---|
| LLM client | `harness.llm` | nuova istanza, stesso modello |
| Tool registry | completo | filtrato read-only |
| Filesystem | workspace padre | workspace privato in sola lettura |
| Memoria | `MemoryStore` | `memory=None`, nessuna scrittura |
| Artifact/mailbox | lettura | outbox del figlio |
| Conferme | provider normale | `DenyAllConfirmation` |
| Usage | ledger padre | ledger separato |
| Audit | condiviso, con lock | eventi `agent.*` |

Il figlio non ha il contesto automatico del padre: il padre deve passare
`context`.

## 5. Tool ammessi

Il padre deve avere le capability `AGENT_SPAWN` e `COMPUTE`; il figlio
non riceve `AGENT_SPAWN` e non può quindi creare altri agenti.

Il registry del figlio include i tool le cui capability sono un
sottoinsieme di:

```text
FILESYSTEM_READ
MEMORY_READ
COMPUTE
AGENT_DATA
```

Il figlio riceve `artifact.put`, `artifact.put_file` e `mailbox.send`.
Non riceve `artifact.read`, `artifact.list`, `mailbox.inbox`,
`mailbox.read` o `mailbox.ack`: quelli sono del padre.

Sono esclusi esplicitamente:

```text
filesystem.chdir
agent.*
```

Sono esclusi per capability:

- scrittura filesystem;
- creazione, rinomina, copia, cancellazione;
- scrittura memoria;
- rete;
- MCP;
- shell.

## 6. Audit

Eventi registrati dal manager:

```text
agent.spawned
agent.started
agent.finished
agent.cancelled
agent.failed
```

Campi principali:

```text
agent
parent
task
inputs
max_tool_calls
status
usage
duration_ms
error
```

`AuditLog.record` è protetto da lock, così le scritture concorrenti non
interlacciano la catena hash.

## 7. Concorrenza

- thread separati per i figli;
- limite `max_concurrent = 2`;
- lock sul dizionario dei job;
- nessuna condizione di race sul filesystem: workspace separati;
- nessuna condivisione di `MemoryStore`, sandbox o client LLM;
- provider locale con richieste concorrenti;
- `agent.wait` blocca solo il chiamante, non gli altri figli.

## 8. Test

`tests/test_subagents.py` copre:

- esecuzione con tool read-only;
- esclusione di scrittura e `agent.*`;
- passaggio del contesto;
- copia degli input nel workspace privato;
- rifiuto oltre `max_concurrent`;
- due subagenti concorrenti;
- errore di costruzione del provider;
- eventi audit.

Test live eseguito con LM Studio e `gemma-3-27b-it`: due subagenti
concorrenti completati, ciascuno con usage separato.

## 9. Prossimi passi

- export esplicito degli artifact dal workspace del figlio;
- budget token/tempo e timeout a parete;
- annidamento controllato, se richiesto;
- `agent_id` su tutti gli eventi interni;
- conferme delegate al padre o alla GUI;
- modello scelto dal broker, non dal manager.
