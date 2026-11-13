# Plugin SQL ODBC

**Ambito:** plugin esterno `plugins/sql_odbc` per leggere e scrivere
database su file tramite ODBC, dentro la sandbox.

Il tool built-in [sql.file.*](SQL.md) copre la lettura, con SQLite
nativo e ODBC. Questo plugin aggiunge la scrittura DML e usa **solo
ODBC**: non apre SQLite nativo.

## 1. Tool

| Tool | Capability | Funzione |
|---|---|---|
| `sql.odbc.drivers` | `DATABASE_READ` | Driver ODBC installati e alias. |
| `sql.odbc.schema` | `FILESYSTEM_READ | DATABASE_READ` | Tabelle, colonne, chiavi e indici via catalogo ODBC. |
| `sql.odbc.query` | `FILESYSTEM_READ | DATABASE_READ` | Una istruzione `SELECT`, `WITH` o `EXPLAIN` read-only. |
| `sql.odbc.execute` | `FILESYSTEM_READ | FILESYSTEM_WRITE | DATABASE_READ | DATABASE_WRITE` | Una istruzione DML, con conferma obbligatoria. |

### 1.1 `sql.odbc.execute`

Accetta una sola istruzione tra:

- `INSERT`
- `UPDATE`
- `DELETE`
- `MERGE`
- `REPLACE`

Rifiuta:

- `SELECT` e `WITH` (usare `sql.odbc.query`);
- DDL: `CREATE`, `ALTER`, `DROP`, `TRUNCATE`;
- più istruzioni separate da `;`;
- `ATTACH`, `DETACH`, `PRAGMA`, `LOAD`, `COPY`, `CALL`, `EXEC`;
- token pericolosi come `OPENROWSET`, `xp_cmdshell`, `pg_read_file`,
  `DBMS_*`.

La connessione è `readonly=False`, `autocommit=False`; il tool esegue
`commit` e, in caso di errore, `rollback`. `row_count` può essere
`-1` se il driver non lo riporta.

`requires_confirmation=True` è un pavimento di `ASK`: la conferma
umana è richiesta anche se la policy dice `allow`. La policy deve
comunque concedere `DATABASE_WRITE` e `FILESYSTEM_WRITE`.

## 2. Perché solo ODBC

La scrittura è confinata a un plugin esterno per non allargare il
tool built-in read-only. Il plugin è ODBC-only per un confine chiaro:

- SQLite nativo resta nel built-in `sql.file.query`, in sola lettura;
- per scrivere un file SQLite serve un driver SQLite ODBC e
  `driver="sqlite-odbc"`;
- Access, Firebird, DuckDB e dBase usano i rispettivi driver ODBC;
- nessun protocollo wire viene implementato dal plugin.

## 3. Installazione

Prerequisito: Hagar installato nell'ambiente.

```powershell
python -m pip install -e plugins/sql_odbc
```

Il plugin dipende da `pyodbc`; il driver ODBC del formato specifico va
installato a livello di sistema operativo. Hagar non installa driver.

Verifica:

```powershell
python -c "from importlib.metadata import entry_points; print([e.name for e in entry_points(group='hagar.tools')])"
```

Deve contenere `sql-odbc`.

Per rimuovere il plugin:

```powershell
python -m pip uninstall hagar-sql-odbc
```

## 4. Abilitazione

In `hagar.yaml`:

```yaml
permissions:
  read: true
  write: true
  database_read: true
  database_write: true
```

`write: true` serve a `FILESYSTEM_WRITE`; il mount della sandbox che
contiene il database deve avere `W`:

```yaml
filesystem:
  sandbox:
    - alias: workspace
      path: .
      permissions: RWX
```

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

Senza `database_write: true` la policy non può concedere
`DATABASE_WRITE` e `sql.odbc.execute` viene negato prima
dell'esecuzione.

## 5. Sicurezza

- **Solo sandbox**: il percorso viene risolto con
  `FileSystemSandbox.resolve_path`; per `execute` sono richiesti sia
  `read` sia `write` effettivi.
- **DB memorie protetto**: il database SQLite delle memorie di Hagar e
  i sidecar `-wal`, `-shm`, `-journal` sono sempre esclusi, anche se
  montati nella sandbox.
- **Solo file**: directory e file mancanti sono rifiutati.
- **Una istruzione**: niente batch o transazioni multi-istruzione.
- **Conferma umana** obbligatoria su `execute`.
- **Nessun percorso host** restituito al modello.
- **Timeout, lunghezza SQL e righe** limitati; gli errori del driver
  vengono ripuliti dai percorsi host.

Il confine più forte resta il driver e l'utente del database. Per file
condivisi usare una copia del database o un driver configurato per
l'accesso minimo.

## 6. Esempi

Lettura:

```json
{
  "path": "/home/ai/workspace/legacy.accdb",
  "driver": "access",
  "sql": "SELECT * FROM Clienti"
}
```

Schema:

```json
{
  "path": "/home/ai/workspace/legacy.accdb",
  "driver": "access",
  "table": "Clienti"
}
```

Scrittura:

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

## 7. Limiti

- Niente DDL.
- Niente transazioni multi-istruzione: una chiamata, una istruzione,
  commit o rollback.
- Il driver deve supportare connessioni in scrittura e, per `schema`,
  le funzioni di catalogo ODBC. Se il catalogo non è disponibile, il
  risultato contiene `warnings`.
- `row_count` può essere `-1`.
- Il plugin non crea file di database: il file deve esistere nella
  sandbox.
- Non ci sono parametri bind: i valori vanno scritti nell'istruzione.
  Per DML con dati non fidati è una limitazione da considerare.

## 8. Test

```powershell
python -m pytest tests/test_sql_odbc_plugin.py -q
```

I test usano un driver ODBC simulato e non richiedono un driver reale.
