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

## Tool

## Repair loop

`flow.run` ripara solo gli errori di **validazione**:

```text
massimo repair_attempts tentativi
un errore per tentativo
stesso modello configurato in Hagar
```

Non ripara:

```text
errori di runtime
policy o conferma negata
timeout
errori di primitive
```

Il risultato include `repair_attempts`. Gli eventi audit sono:

```text
flow.repair.start
flow.repair.attempt
flow.repair.result
flow.repair.gave_up
flow.repair.error
```

`repair_attempts: 0` disabilita la riparazione.

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
