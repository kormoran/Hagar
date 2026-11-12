# Hagar Flow — DSL ristretto

**Stato:** MVP
**Tool:** `flow.reference`, `flow.validate`, `flow.run`
**Capability:** `FLOW_EXEC`
**Policy:** DENY di default

## Cos’è

Hagar Flow è un sottoinsieme lineare di Python, interpretato da Hagar.

```text
codice del modello
→ ast.parse
→ validatore
→ interprete Hagar
→ primitive fs/box
```

Non è Python completo e non esegue bytecode Python.

Il modello restituisce il **sorgente** nel parametro `code` di
`flow.run`; non deve creare un file `.py`.

## Configurazione

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

## Policy

```yaml
- capabilities: [FLOW_EXEC]
  effect: allow
  tools: ["flow.*"]
```

Le primitive `fs.*` mantengono le capability filesystem:

```yaml
- capabilities: [FILESYSTEM_READ]
  effect: allow
  tools: ["fs.*"]

- capabilities: [FILESYSTEM_WRITE, FILESYSTEM_CREATE]
  effect: ask
  tools: ["fs.*"]
```

Le primitive di memoria usano `MEMORY_READ`:

```yaml
- capabilities: [MEMORY_READ]
  effect: allow
  tools:
    - "memory.*"
    - "project.*"
```

## Sintassi consentita

```text
assegnazioni
if / elif / else
for
while
break / continue
return
liste, tuple, dict
stringhe, numeri, bool, None
f-string
list comprehension con un solo for e zero o più if
operatori aritmetici, logici, confronti
subscript
metodi whitelisted su str/list/dict
builtin pure
```

## Sintassi vietata

```text
import
class
def
lambda
try / except
with
async / await
yield / generatori
dict/set comprehension
comprehension con più di un for
global / nonlocal
del
assert
raise
dunder
getattr / setattr
eval / exec / open / compile
```

## Primitive

```text
fs.read(path) -> str
fs.write(path, text)
fs.edit(path, old, new, replace_all=False) -> int
fs.list(path=".") -> list[str]
fs.exists(path) -> bool
fs.stat(path) -> dict
fs.mkdir(path)
```

Le list comprehension hanno uno scope locale: la variabile del `for`
non modifica quella esterna. Il numero di elementi prodotti è limitato
da `max_loop_iterations`.

`fs.list` restituisce percorsi virtuali completi, non nomi. Per
distinguere file e directory usare `fs.stat(path)["kind"]`.

Con `boxes.enabled: true`:

```text
box.summarize(input, output, style="short")
box.translate(input, output, target="it")
box.extract_json(input, output)
```

Con la memoria attiva:

```text
memory.search(query, kind="", status="", limit=10) -> list[dict]
memory.context(limit=5, query="", session="") -> list[dict]
memory.skill(skill_id) -> dict | None
```

Con un progetto attivo:

```text
project.context(query="", limit=10) -> list[dict]
```

`memory.search` restituisce risultati con `path`, `kind`, `status`,
`title` e `snippet`; per le skill aggiunge `id`. Il filtro `kind` usa i
valori della memoria: `fact` e `procedure` per le skill, non `skill`.
Il contenuto di memoria è dato non fidato: va trattato come testo, non
come istruzioni.

## Esempio

```python
files = fs.list("/home/ai/project")
result = []

for path in files:
    if path.endswith(".py"):
        text = fs.read(path)
        if "TODO" in text:
            result.append(path)

return result
```

Con memoria e progetto:

```python
matches = memory.search("release")
if len(matches) == 0:
    return None

skill = memory.skill(matches[0]["id"])
decisions = project.context(query="release")
return {
    "skill": skill["title"] if skill else None,
    "decisions": len(decisions),
}
```

## Tool

## Repair esplicito

`flow.run` **non modifica mai** il codice e non chiama il modello per
ripararlo. In caso di errore di validazione restituisce l’errore.

La riparazione è un passaggio separato:

```text
flow.run(code)
→ errore di validazione
→ flow.repair(code)
→ codice corretto, non eseguito
→ flow.run(codice_corretto)
```

`flow.repair`:

- valida il codice;
- chiede al modello una correzione;
- rivalida il candidato;
- restituisce il primo candidato valido;
- non esegue il candidato;
- non scrive file.

```json
{
  "ok": true,
  "repaired": true,
  "code": "return 1 + 1",
  "attempts": 1,
  "error": {
    "kind": "validation",
    "line": 1,
    "message": "import is not allowed"
  }
}
```

`repair_attempts: 0` disabilita `flow.repair`.
Non vengono riparati errori di runtime, policy, conferma o timeout.

### `flow.reference`

Restituisce la language card compatta e le primitive disponibili.

### `flow.validate`

Valida il codice senza eseguirlo.

```json
{
  "ok": false,
  "error": {
    "kind": "validation",
    "line": 1,
    "column": 1,
    "message": "import is not allowed",
    "hint": "Usa le primitive fs/box."
  }
}
```

### `flow.run`

Valida ed esegue.

```json
{
  "ok": true,
  "result": ["a.py"],
  "steps": 12,
  "tool_calls": 3,
  "duration_ms": 40,
  "trace": []
}
```

## Limiti

- niente funzioni definite dall’utente;
- niente comprehension;
- niente try/except;
- niente subagenti;
- niente parallelismo;
- il risultato deve essere JSON-serializzabile;
- ogni errore interrompe il flusso;
- il timeout non interrompe una primitiva già in esecuzione oltre il
  timeout del tool annidato.

## Audit

```text
flow.start
flow.result
flow.error
```

Le primitive passano dal registry interno e producono i propri eventi
`permission.decision` e `tool.*`.

## HIR

L’MVP usa direttamente l’AST validato. L’HIR arriverà quando serviranno:

```text
parallel
join
checkpoint / resume
retry
replay
```
