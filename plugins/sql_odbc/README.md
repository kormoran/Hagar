# hagar-sql-odbc

Plugin SQL per Hagar, **solo ODBC**, con lettura e scrittura DML su
database su file dentro la sandbox.

Documentazione completa: [Docs/it/SQL.md](../../Docs/it/SQL.md).

## Tool

| Tool | Capability | Funzione |
|---|---|---|
| `sql.odbc.drivers` | `DATABASE_READ` | Driver ODBC installati e alias. |
| `sql.odbc.schema` | `FILESYSTEM_READ | DATABASE_READ` | Tabelle, colonne, chiavi e indici via catalogo ODBC. |
| `sql.odbc.query` | `FILESYSTEM_READ | DATABASE_READ` | Una istruzione `SELECT`/`WITH`/`EXPLAIN` read-only. |
| `sql.odbc.execute` | `FILESYSTEM_READ | FILESYSTEM_WRITE | DATABASE_READ | DATABASE_WRITE` | Una istruzione DML, con conferma. |

`sql.odbc.execute` accetta solo `INSERT`, `UPDATE`, `DELETE`, `MERGE`
e `REPLACE`. DDL, `SELECT`, più istruzioni, `ATTACH`, `PRAGMA` e token
pericolosi sono rifiutati. La conferma umana è obbligatoria
(`requires_confirmation=True`), oltre alla policy.

## Installazione

Dalla radice di Hagar:

```powershell
python -m pip install -e plugins/sql_odbc
```

Il plugin dipende da `pyodbc`. Il driver ODBC del formato specifico
(Access, Firebird, DuckDB, SQLite ODBC, dBase) va installato a livello
di sistema operativo.

Verifica:

```powershell
python -c "from importlib.metadata import entry_points; print([e.name for e in entry_points(group='hagar.tools')])"
# deve contenere 'sql-odbc'
```

## Abilitazione

In `hagar.yaml`:

```yaml
permissions:
  read: true
  write: true          # serve a sql.odbc.execute
  database_read: true
  database_write: true # implica DATABASE_READ nel tetto
```

Il mount della sandbox che contiene il database deve avere `W` (write)
oltre a `R`.

In `policy.yaml`:

```yaml
      - capabilities: [FILESYSTEM_READ, DATABASE_READ]
        effect: ask
        tools:
          - "sql.odbc.drivers"
          - "sql.odbc.schema"
          - "sql.odbc.query"

      - capabilities: [FILESYSTEM_READ, FILESYSTEM_WRITE, DATABASE_READ, DATABASE_WRITE]
        effect: ask
        tools: ["sql.odbc.execute"]
```

`sql.odbc.execute` chiede comunque conferma anche se la policy è
`allow`.

## Sicurezza

- Solo file nella sandbox: il percorso è risolto da
  `FileSystemSandbox` e verificato in lettura/scrittura.
- Il database delle memorie di Hagar e i sidecar `-wal`, `-shm`,
  `-journal` sono sempre esclusi.
- Solo ODBC: SQLite nativo resta nel built-in `sql.file.query`; qui
  serve un driver ODBC (ad esempio `sqlite-odbc`).
- Connessione di scrittura con `readonly=False`, `autocommit=False`,
  commit esplicito e rollback in caso di errore.
- Una sola istruzione per chiamata; timeout, righe e dimensione SQL
  limitati.
- Nessun percorso host viene restituito al modello.

## Esempio

```json
{
  "path": "/home/ai/workspace/legacy.accdb",
  "driver": "access",
  "sql": "UPDATE Clienti SET Citta = 'Roma' WHERE ID = 42",
  "timeout_seconds": 30
}
```

Risposta:

```json
{
  "success": true,
  "adapter": "odbc",
  "driver": "Microsoft Access Driver (*.mdb, *.accdb)",
  "row_count": 1,
  "committed": true
}
```

## Limiti

- Niente DDL (`CREATE`, `ALTER`, `DROP`, `TRUNCATE`).
- Niente transazioni multi-istruzione: ogni chiamata è atomica.
- Il driver ODBC deve supportare connessioni read-only/scrittura e le
  funzioni di catalogo usate da `schema`; se non le supporta, il
  risultato contiene `warnings`.
- `row_count` può essere `-1` se il driver non lo riporta.

## Test

```powershell
python -m pytest tests/test_sql_odbc_plugin.py -q
```

I test usano un driver ODBC simulato; non serve un driver reale.
