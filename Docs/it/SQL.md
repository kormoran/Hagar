# Tool SQL locale

**Ambito:** accesso in sola lettura a database SQL su file, dentro la
sandbox. SQLite è nativo; gli altri formati richiedono un driver ODBC
installato dall'host.

Il tool è built-in (`local_tools/sql_file*`) e usa le capability
`DATABASE_READ` e `FILESYSTEM_READ`. Non è un plugin esterno: è
disponibile appena Hagar parte, ma resta negato finché il tetto di
sistema e la policy non lo consentono.

Per la scrittura DML via ODBC vedi il plugin
[SQL_ODBC.md](SQL_ODBC.md).

## 1. Tool

| Tool | Capability | Funzione |
|---|---|---|
| `sql.file.drivers` | `DATABASE_READ` | Elenca SQLite nativo, driver ODBC installati, alias e estensioni riconosciute. |
| `sql.file.schema` | `FILESYSTEM_READ | DATABASE_READ` | Elenca tabelle/viste oppure ispeziona colonne, chiave primaria, foreign key e indici. |
| `sql.file.query` | `FILESYSTEM_READ | DATABASE_READ` | Esegue una sola istruzione `SELECT`, `WITH` o `EXPLAIN` e restituisce righe e colonne. |

### 1.1 `sql.file.drivers`

Non tocca alcun database. Restituisce:

- `native`: gli adattatori sempre disponibili (`sqlite`);
- `odbc_available`: se `pyodbc` è importabile;
- `odbc_drivers`: i driver ODBC installati;
- `aliases`: stato degli alias `access`, `sqlite-odbc`, `firebird`,
  `duckdb`, `dbase`;
- `extensions`: associazione estensione → adattatore per `driver=auto`.

Se `pyodbc` manca, il tool risponde comunque con `success: true`,
`odbc_available: false` e un campo `error` che spiega come installarlo.

### 1.2 `sql.file.schema`

Parametri:

- `path` (string): percorso del database nella sandbox;
- `driver` (string, opzionale): `auto` (default), `sqlite`,
  `sqlite-odbc`, `access`, `firebird`, `duckdb`, `dbase`, oppure il
  nome esatto di un driver ODBC installato;
- `table` (string, opzionale): tabella o vista da ispezionare; se
  omesso elenca tabelle e viste;
- `schema` (string, opzionale): schema/catalogo ODBC;
- `max_tables` (integer, opzionale): 1..500, default 200;
- `timeout_seconds` (integer, opzionale): 1..120, default 30.

Senza `table` restituisce `tables`, `count` e `truncated`. Con `table`
restituisce `columns`, `primary_key`, `foreign_keys`, `indexes` e
`found`. Per ODBC usa le funzioni di catalogo del driver
(`SQLTables`, `SQLColumns`, `SQLPrimaryKeys`, `SQLForeignKeys`); se un
driver non le espone, il risultato contiene `warnings` invece di
fallire.

### 1.3 `sql.file.query`

Parametri:

- `path` (string): percorso del database nella sandbox;
- `sql` (string): una sola istruzione `SELECT`, `WITH` o `EXPLAIN`;
- `driver` (string, opzionale): come sopra;
- `max_rows` (integer, opzionale): 1..1000, default 100;
- `timeout_seconds` (integer, opzionale): 1..120, default 30.

Restituisce `columns`, `rows`, `row_count`, `truncated`,
`duration_ms`, `read_only`, `adapter`, `driver` (per ODBC) e `path`
(virtuale). I valori sono convertiti in JSON: `Decimal` e date
diventano stringhe, i blob diventano base64 con flag `truncated`, le
stringhe lunghe sono troncate.

## 2. Formati e driver

| Estensione / alias | Adattatore | Note |
|---|---|---|
| `.db`, `.sqlite`, `.sqlite3` | SQLite nativo | Sempre disponibile, nessuna dipendenza. |
| `.accdb`, `.mdb`, `access` | ODBC Access | Richiede il driver Microsoft Access. |
| `.fdb`, `firebird` | ODBC Firebird | Richiede il driver Firebird/InterBase. |
| `.duckdb`, `duckdb` | ODBC DuckDB | Richiede il driver DuckDB ODBC. |
| `.dbf`, `dbase` | ODBC dBase | Richiede il driver dBase. |
| `sqlite-odbc` | ODBC SQLite | Richiede un driver SQLite ODBC. |
| nome esatto | ODBC generico | Usa `DRIVER={nome};DBQ={path};`. |

Con `driver=auto` l'estensione decide. Se l'estensione non è
riconosciuta, il tool restituisce un errore che elenca le estensioni e
gli alias supportati. Se il driver richiesto non è installato, il tool
restituisce un errore con l'elenco dei driver disponibili: non prova a
installarne nessuno.

### 2.1 Installare il supporto ODBC

`pyodbc` è una dipendenza opzionale:

```powershell
python -m pip install -e ".[database]"
```

Il driver ODBC specifico (Access, Firebird, DuckDB, SQLite ODBC, …)
va installato a livello di sistema operativo. Hagar non lo installa e
non lo configura.

## 3. Sicurezza

- **Solo sandbox**: il percorso viene risolto con
  `FileSystemSandbox.resolve_path` e verificato con `FS_Guardian`.
  Un percorso fuori dalle radici concesse viene rifiutato; nessun
  percorso host viene restituito al modello.
- **Solo file**: directory, dispositivi e file mancanti sono rifiutati.
- **DB memorie protetto**: il percorso del database SQLite delle
  memorie di Hagar e i suoi sidecar `-wal`, `-shm` e `-journal` sono
  sempre esclusi, anche se montati nella sandbox. Il confronto usa
  path normalizzati e, quando possibile, `st_dev`/`st_ino` per
  intercettare gli hard link.
- **Sola lettura SQLite**: connessione `mode=ro`, `PRAGMA
  query_only=ON`, authorizer che consente solo `SELECT`/`READ` e
  blocca `ATTACH`, `DETACH`, `PRAGMA`, `load_extension`, `readfile`,
  `writefile`.
- **Sola lettura ODBC**: `pyodbc.connect(..., readonly=True)`,
  `autocommit=False`, `connection.timeout`, una sola istruzione.
- **Validazione SQL**: solo `SELECT`, `WITH`, `EXPLAIN`; niente
  `SELECT ... INTO`, niente `EXPLAIN ANALYZE`, niente più istruzioni;
  `WITH` non può contenere DML/DDL; una lista di token pericolosi
  (`OPENROWSET`, `xp_cmdshell`, `pg_read_file`, `DBMS_*`, …) viene
  rifiutata.
- **Limiti**: `max_rows` (1000), `timeout_seconds` (120), lunghezza
  SQL (20.000 caratteri), dimensione cella e blob, numero di tabelle.
- Il tool non espone parametri bind: i valori vanno scritti nella
  query. Per le query parametriche serve una versione successiva.
- **Nessun permesso concesso dal tool**: policy, conferma, audit e
  repeat limit restano nell'host.

Il limite più importante resta l'utente del database. Per ODBC e per
database condivisi usare un utente in sola lettura e un driver
configurato per aprire il file in sola lettura. La validazione SQL e
`readonly=True` sono difese in profondità, non sostituti dei permessi
del database.

## 4. Configurazione

In `hagar.yaml`:

```yaml
permissions:
  database_read: true
```

`database_write` non serve al tool built-in, che è solo lettura; sarà
usato dal plugin ODBC con scrittura.

In `policy.yaml`:

```yaml
      - capabilities: [FILESYSTEM_READ, DATABASE_READ]
        effect: ask
        tools: ["sql.file.*"]
```

`ask` richiede conferma per ogni chiamata. Se il tetto non concede
`DATABASE_READ`, la policy non può concederla e il tool viene negato
prima dell'esecuzione.

## 5. Esempi

Elenco dei driver:

```json
{}
```

Schema di un file SQLite:

```json
{
  "path": "/home/ai/workspace/app.db",
  "driver": "auto"
}
```

Colonne di una tabella:

```json
{
  "path": "/home/ai/workspace/app.db",
  "table": "orders"
}
```

Query:

```json
{
  "path": "/home/ai/workspace/app.db",
  "sql": "SELECT id, total FROM orders ORDER BY id DESC",
  "max_rows": 50
}
```

File Access:

```json
{
  "path": "/home/ai/workspace/legacy.accdb",
  "driver": "access",
  "sql": "SELECT TOP 10 * FROM Clienti"
}
```

## 6. Test

I test sono offline e usano SQLite reale e un modulo ODBC simulato:

```powershell
python -m pytest tests/test_sql_file.py -q
```

Coprono registrazione e capability, schema, query, limiti, rifiuto di
scritture/PRAGMA/ATTACH, timeout, path fuori sandbox, blocco del DB
memorie, driver ODBC mancante e connessione ODBC read-only.
