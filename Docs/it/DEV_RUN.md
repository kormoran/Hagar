# `dev.run` — ricette di sviluppo

**Stato:** implementato nella 0.6.0
**Tool:** `dev.list`, `dev.run`
**Capability:** `DEV_EXEC`
**Policy:** DENY di default
**Backend:** host, dentro la sandbox

## A cosa serve

`dev.run` esegue ricette dichiarate dallo sviluppatore per **test, debug
e build**.

Non è un’API per eseguire codice arbitrario. Il modello può scegliere una
ricetta e i suoi parametri tipizzati, ma non può fornire un comando, un
argv arbitrario o una shell.

```text
modello → dev.run(recipe="test")
        → ricetta fidata
        → subprocess senza shell
```

## File delle ricette

Il file predefinito è:

```text
<config-dir>/recipes.yaml
```

Può essere cambiato con:

```yaml
dev:
  recipes: /percorso/recipes.yaml
```

Regole:

- `recipes.yaml` è configurazione fidata;
- deve stare **fuori** dalla sandbox scrivibile;
- viene letto una sola volta all’avvio;
- non esiste hot reload;
- se cambia durante la sessione, Hagar continua a usare lo snapshot di
  avvio e segnala `recipes_changed: true`; per applicare le modifiche
  bisogna riavviare Hagar.

## Configurazione

```yaml
dev:
  enabled: false
  recipes: recipes.yaml
  copy_workspace: true
  max_output_chars: 100000
```

`enabled: false` non registra i tool. Anche con i tool registrati,
`DEV_EXEC` deve essere concessa esplicitamente in `policy.yaml`.

## Policy

```yaml
- capabilities: [DEV_EXEC]
  effect: allow
  tools: ["dev.*"]
```

La regola predefinita è `deny`.

## Schema

```yaml
version: 1

recipes:
  test:
    description: Esegue pytest
    argv:
      - .venv/Scripts/python.exe
      - -m
      - pytest
      - -q
    cwd: .
    timeout: 120
    env:
      PYTHONUNBUFFERED: "1"

  test-target:
    description: Esegue un test specifico
    argv:
      - .venv/Scripts/python.exe
      - -m
      - pytest
      - -q
      - "{target}"
    parameters:
      target:
        type: choice
        choices:
          - tests/test_agent.py
          - tests/test_filesystem.py
```

Campi:

```text
version             obbligatorio, attualmente 1
recipes             mappa di ricette
description         testo libero
argv                lista non vuota di stringhe
cwd                 directory relativa alla sandbox
timeout             secondi
env                 variabili esplicite
parameters          parametri tipizzati
success_codes       default [0]
stdin_file          file della sandbox
```

## Parametri

Tipi supportati:

```text
string
integer
boolean
choice
path
```

Un parametro `path` viene validato dentro la sandbox. L’interpolazione è
solo un elemento argv completo:

```yaml
argv: ["pytest", "{target}"]
```

Non è supportata l’interpolazione dentro una stringa più grande.

## Cosa è vietato

```text
shell
pipe
redirect
glob
command substitution
variabili nel comando
python -c
bash -c
node -e
```

Sono vietati anche gli eseguibili shell espliciti (`bash`, `sh`, `cmd`,
`powershell`, `pwsh`).

## Esecuzione

Il runner:

- valida ricetta e parametri;
- copia il progetto in una directory temporanea;
- esegue un solo argv con `shell=False`;
- usa un ambiente minimo;
- applica il timeout;
- termina il process group;
- separa stdout e stderr;
- limita l’output;
- registra l’audit.

La copia temporanea evita che `pytest`, compilatori e build lascino
artefatti nel workspace reale o aggirino checkpoint e read-before-write.

## Risultato

```json
{
  "recipe": "test",
  "backend": "host",
  "exit_code": 0,
  "success": true,
  "timed_out": false,
  "duration_ms": 1234,
  "stdout": "...",
  "stderr": "...",
  "truncated": false,
  "artifact_id": null,
  "recipes_changed": false
}
```

Un exit code diverso da zero non è un errore del tool: è un risultato che
il modello può leggere.

## Limiti

- il backend è solo host;
- la sandbox non isola il processo dal filesystem host;
- le ricette sono fidate;
- una ricetta può accedere alla rete;
- non c’è container;
- il container resta congelato per un futuro accesso diretto a
  filesystem/programmi reali, mai dentro la sandbox;
- niente hot reload;
- una ricetta esegue un solo comando.

## Audit

```text
dev.recipes.loaded
dev.run.start
dev.run.result
dev.run.timeout
dev.run.error
dev.run.denied
```

Non vengono registrati gli output completi né i valori delle variabili
d’ambiente.
