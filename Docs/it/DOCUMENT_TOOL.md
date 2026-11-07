# Document tool — specifica di architettura

**Stato:** accepted  
**Data:** 2026-11-07  
**Ambito:** tool di analisi documenti, plugin di formato, host nativo  
**MVP:** CSV

## 1. Decisione

Il document tool separa tre livelli:

```text
modello
  │ document.analyze / structure / semantics / read / close
  ▼
document tool
  │ FormatPlugin
  ▼
plugin di formato
  ├── runtime Python (in-process)
  └── runtime nativo (host separato + DLL)
```

La decisione principale è:

> i plugin di formato nativi **non vengono caricati nel processo di Hagar**.

Vengono eseguiti da un host nativo separato, che carica la DLL e parla
con Hagar attraverso un protocollo JSON. Un crash o una corruzione di
memoria della DLL uccide l’host, non Hagar.

Il contratto logico `FormatPlugin` è unico; cambia solo il runtime.

## 2. Perché questa scelta

### 2.1 In-process DLL: perché no

Caricare una DLL con `ctypes` nel processo Python significa:

- un segmentation fault può terminare Hagar;
- una DLL può corrompere la memoria del processo;
- una `try/except` Python non intercetta un crash nativo;
- una DLL può bloccare il processo senza timeout;
- l’ABI dipende da compilatore, runtime C, architettura e sistema operativo;
- il sandbox applicativo di Hagar non confina il codice nativo.

Per un formato come PDF, EXE o DWG il rischio non è accettabile.

### 2.2 Host separato: cosa risolve

L’host separato risolve:

- **crash isolation**: la DLL muore con il suo processo;
- **ABI isolation**: Hagar non linka la DLL;
- **timeout**: l’host può essere terminato;
- **attribuzione**: un host per plugin nativo;
- **aggiornamento**: la DLL può essere sostituita senza riavviare Hagar;
- **test**: l’host può essere testato con un protocollo stabile.

### 2.3 Cosa non risolve

Un processo separato **non è un sandbox di sicurezza**. Una DLL
malevola può comunque:

- leggere file accessibili all’utente;
- aprire connessioni di rete;
- consumare CPU e memoria;
- cancellare dati.

Quindi:

- DLL **trusted**: host separato per stabilità;
- DLL **non trusted**: host separato **più** sandbox del sistema
  operativo, oppure nessuna DLL.

Hagar non deve presentare l’host come garanzia di sicurezza contro codice
ostile.

### 2.4 Perché non usare LibreOffice o altri converter

Non vengono invocati `libreoffice`, `poppler`, `7zip`, `ffmpeg` o
simili. Sono converter complessi, con superfici di attacco ampie,
dipendenze di sistema e comportamenti difficili da confinare.

Il document tool può usare una libreria Python o una DLL, ma non un
applicativo esterno che apre e converte il documento.

## 3. Obiettivi e non-obiettivi

### Obiettivi

- riconoscere il formato di un file nella sandbox;
- costruire un grafo navigabile di struttura e semantica;
- estrarre contenuti su richiesta, in modo bounded;
- isolare i parser nativi;
- mantenere il grafo effimero;
- permettere l’aggiunta di formati senza modificare il tool;
- non ricostruire il documento.

### Non-obiettivi

- convertire un documento in un altro formato;
- ricreare il file originale;
- conservare il grafo come memoria permanente;
- eseguire macro, JavaScript o codice contenuto nel documento;
- garantire il riconoscimento di “qualunque” formato;
- esporre percorsi host al modello.

## 4. Interfaccia modello-tool

### 4.1 Operazioni

`path` è un path della sandbox Hagar, nella forma
`/home/ai/<alias>/...`; il modello non riceve mai un path host.

```text
document.analyze(path, options?) -> handle + summary
document.structure(handle, node_id?, cursor?, limit?) -> nodi strutturali
document.semantics(handle, node_id?, cursor?, limit?) -> nodi semantici
document.read(handle, node_id, anchor?, offset?, length?) -> contenuto
document.close(handle) -> ok
```

`document.analyze`:

```json
{
  "handle": "doc-7f3a",
  "document_id": "sha256:...",
  "format": "csv",
  "plugin": "csv",
  "plugin_version": "1.0",
  "root": "n-root",
  "summary": "CSV UTF-8, delimitatore ',', 120 righe, 5 colonne",
  "counts": {"nodes": 12, "semantic_nodes": 4},
  "warnings": [],
  "truncated": false
}
```

`document.structure` restituisce solo i figli richiesti; non l’intero
albero. `document.semantics` restituisce i nodi semantici associati a un
nodo strutturale.

`document.read` è l’unico modo per ottenere contenuto:

```json
{
  "node": "n-cell-2-1",
  "anchor": "n-row-2",
  "offset": 0,
  "length": 56,
  "encoding": "utf-8",
  "text": "valore",
  "truncated": false
}
```

Per dati binari:

```json
{
  "node": "n-image-1",
  "encoding": "base64",
  "data_b64": "...",
  "truncated": true
}
```

Regole:

- l’offset di `read` è relativo al locator del nodo, non al file;
- `length` è obbligatorio o limitato da un default;
- la risposta non può superare il limite configurato;
- `truncated` è esplicito;
- nessuna scrittura, nessun `save`, nessun `rebuild`.

### 4.2 Handle

Un handle:

- è creato da `analyze`;
- è valido solo nella sessione corrente;
- è legato a `sha256 + size + mtime + plugin + plugin_version +
  schema_version`;
- viene invalidato se il file cambia;
- muore con `close`, con la chiusura della sessione o con il timeout.

Non è un identificatore persistente e non è una memoria.

### 4.3 Limiti

Anche in sviluppo i limiti sono finiti e configurabili:

```text
max_file_bytes
max_rows
max_columns
max_field_bytes
max_nodes
max_edges
max_semantic_nodes
max_read_bytes
max_open_handles
handle_ttl_seconds
plugin_timeout_seconds
max_decompressed_bytes
max_pack_depth
```

I valori iniziali possono essere molto larghi; “infinito” non è un
valore di configurazione.

## 5. Format plugin

### 5.1 Contratto logico

```python
class FormatPlugin(Protocol):
    name: str
    version: str

    def sniff(
        self,
        head: bytes,
        filename: str,
    ) -> float: ...

    def analyze(
        self,
        source: DocumentSource,
        context: FormatContext,
    ) -> DocumentGraph: ...

    def expand(
        self,
        node_id: str,
        cursor: int,
        limit: int,
    ) -> list[Node]: ...

    def read(
        self,
        node_id: str,
        anchor: int,
        offset: int,
        length: int,
    ) -> bytes: ...
```

`expand` è obbligatorio per i nodi lazy (`array`, `record`). `read` può
essere un’implementazione di default per i formati non compressi.

### 5.2 DocumentSource

Il plugin non riceve un path host arbitrario. Riceve:

```text
size
sha256
read_range(offset, length) -> bytes
open_pack(codec, offset, length) -> DocumentSource
```

Per il runtime nativo, l’host nativo riceve una **copia read-only
temporanea** del documento; il path originale non viene passato alla
DLL.

### 5.3 Rilevamento

Ordine:

1. magic number, se esiste;
2. estensione;
3. euristica del plugin;
4. confidenza minima.

Se magic ed estensione sono in conflitto:

- vince il magic number;
- viene aggiunto un warning;
- il plugin scelto è quello del magic.

Se nessun plugin supera la soglia:

- grafo `opaque`;
- un solo nodo;
- `reason`, `sha256`, estensione e dimensione nelle proprietà.

Il CSV non ha magic: usa estensione `.csv`/`.tsv` più un’euristica su
testo e delimitatore.

### 5.4 Registrazione

Il document tool è un plugin Hagar nel gruppo `hagar.tools`.

I plugin di formato usano il gruppo:

```text
hagar.document_formats
```

Un entry point restituisce un descrittore:

```python
@dataclass(frozen=True)
class FormatPluginSpec:
    name: str
    version: str
    runtime: str          # "python" | "native"
    manifest: str | None  # obbligatorio per native
```

Per `runtime: "python"` Hagar importa e usa il plugin in-process. Per
`runtime: "native"` Hagar legge il manifest, valida ABI/platform/hash
della DLL e avvia l’host nativo. La DLL non viene mai caricata dal
processo Hagar.

### 5.5 Container annidati

Un `pack` può contenere un altro documento. Regole:

- profondità massima;
- byte decompressi massimi;
- nessuna ricorsione illimitata;
- ogni nuovo spazio ha un `pack_id`;
- un pack che supera i limiti diventa `opaque`, non blocca il resto.

## 6. Grafo

### 6.1 Envelope

```json
{
  "schema_version": "1.0",
  "document_id": "sha256:...",
  "format": "csv",
  "plugin": "csv",
  "plugin_version": "1.0",
  "root": "n-root",
  "nodes": [],
  "edges": [],
  "warnings": [],
  "stats": {}
}
```

### 6.2 Nodo

```json
{
  "id": "n-...",
  "kind": "structural",
  "type": "section",
  "label": "Pagina 1",
  "locator": {
    "space": "file",
    "offset": 0,
    "length": 5000
  },
  "properties": {},
  "children": [],
  "materialized": true
}
```

`kind`:

```text
structural
semantic
```

I nodi semantici hanno un `anchor` verso un nodo strutturale. Possono
avere `anchors` multipli se il contenuto è non contiguo.

### 6.3 Locator

```json
{"space": "file", "offset": 1234, "length": 56}
```

- `space` è `file` oppure `pack:<pack_id>`;
- `offset` è 0-based in byte;
- `length` è obbligatorio per un contenuto leggibile;
- per un nodo puramente strutturale senza contenuto diretto, `length`
  può essere `0`;
- per contenuti non contigui si usa `anchors`.

Un solo offset non è sufficiente: senza `length` il tool non conosce il
confine del dato; senza `space` un offset dentro un pack è ambiguo.

### 6.4 Tipi strutturali

```text
document
header
section
container
pack
array
record
opaque
```

- `header`: header ufficiale del formato;
- `section`: sezione ufficiale o area dichiarata dal formato;
- `container`: raggruppamento non codificato e non ufficiale;
- `pack`: zona compressa/codificata, con `codec` e `logical_root`;
- `array`: sequenza omogenea lazy, con `count`, `element_type`,
  `materialized: false`;
- `record`: struttura semplice, espansa su richiesta;
- `opaque`: oggetto sconosciuto.

### 6.5 Tipi semantici

```text
text
image
table
machine_code
formula
metadata
link
annotation
binary
```

Proprietà minime:

- `text`: `encoding`, `role`;
- `image`: `mime_type`, `width`, `height`, `codec`;
- `table`: `rows`, `columns`, `header`;
- `machine_code`: `architecture`, `entry_point`;
- `formula`: `language`, `expression`;
- `metadata`: `key`, `value`;
- `binary`: `mime_type`, `codec`.

I tipi specifici del formato usano un namespace:

```text
pdf.page
xlsx.cell
pe.section
dxf.entity
```

### 6.6 Archi

```text
contains
follows
references
links_to
attached_to
derived_from
same_as
part_of
anchored_to
```

`contains` forma un albero. Gli altri archi possono formare un grafo,
anche con cicli.

### 6.7 Array lazy

Un array non materializza tutti gli elementi:

```json
{
  "id": "n-rows",
  "kind": "structural",
  "type": "array",
  "count": 100000,
  "element_type": "record",
  "materialized": false,
  "locator": {"space": "file", "offset": 0, "length": 0}
}
```

Il modello espande:

```text
document.structure(handle, "n-rows", cursor=0, limit=100)
```

Il plugin implementa `expand` e restituisce solo la pagina richiesta.

### 6.8 Pack

```json
{
  "id": "n-pack-1",
  "kind": "structural",
  "type": "pack",
  "properties": {
    "codec": "zip",
    "compressed": true,
    "logical_root": "n-pack-1-root"
  },
  "locator": {"space": "file", "offset": 100, "length": 2048}
}
```

I figli hanno `space: "pack:n-pack-1"`.

## 7. CSV MVP

### 7.1 Rilevamento

- estensione `.csv` o `.tsv`;
- contenuto testuale;
- delimitatore coerente;
- confidenza minima.

Se il file è `.csv` ma non è testuale o non ha una struttura tabellare
coerente, il risultato è `opaque` con warning.

### 7.2 Grafo

```text
document
  section "csv"
    array "rows" (lazy)
      record "row 2"
        text "campo 1"
        text "campo 2"
    semantic table "tabella"
      semantic column "colonna A"
      semantic column "colonna B"
```

La radice `document` ha locator `{file, 0, size}`.

L’array `rows` ha `count`, `element_type: record`,
`materialized: false`.

Ogni `record` è espanso su richiesta. Ogni cella è un nodo `text` con
`encoding`, `role: cell` e locator preciso.

La tabella semantica contiene:

- delimitatore;
- encoding;
- presenza header;
- numero colonne;
- nomi colonne;
- warning.

### 7.3 Read CSV

```text
document.read(handle, "n-cell-2-1")
```

restituisce il valore decodificato della cella, non l’intero file.

Per un campo quotato con newline, il locator copre i byte grezzi; la
decodifica e l’unescaping avvengono nel plugin.

### 7.4 Limiti CSV

```text
max_file_bytes
max_rows
max_columns
max_field_bytes
max_nodes
max_read_bytes
```

Il plugin costruisce un indice degli offset di inizio riga per
permettere l’espansione lazy senza materializzare tutte le righe.

## 8. Host nativo

### 8.1 Modello

```text
Hagar
  └── NativeHost (processo Hagar)
        └── una DLL di formato
```

Un host per plugin nativo. L’host viene avviato al primo uso, fa
handshake, carica la DLL e resta attivo finché il plugin è in uso.

### 8.2 Trasporto

- JSON Lines UTF-8 su stdin/stdout;
- una richiesta o risposta per riga;
- stdout riservato al protocollo;
- log su stderr;
- un solo comando in volo per host;
- timeout lato Hagar;
- kill e riavvio dell’host dopo un crash.

### 8.3 Handshake

Hagar:

```json
{"id": "1", "op": "hello", "protocol": 1}
```

Host:

```json
{
  "id": "1",
  "ok": true,
  "protocol": 1,
  "plugin": {
    "name": "pdf",
    "version": "1.0",
    "abi": 1,
    "platform": "win-x64"
  },
  "capabilities": ["analyze", "expand", "read"]
}
```

Se `protocol` o `abi` non corrispondono, l’host viene rifiutato.

### 8.4 Comandi

#### analyze

```json
{
  "id": "2",
  "op": "analyze",
  "path": "C:\\...\\temp\\input.bin",
  "options": {},
  "limits": {}
}
```

`path` è una copia read-only temporanea, non il path originale.

Risposta:

```json
{
  "id": "2",
  "ok": true,
  "graph": {},
  "warnings": []
}
```

#### expand

```json
{
  "id": "3",
  "op": "expand",
  "node": "n-rows",
  "cursor": 0,
  "limit": 100
}
```

Risposta:

```json
{
  "id": "3",
  "ok": true,
  "nodes": [],
  "next_cursor": 100
}
```

#### read

```json
{
  "id": "4",
  "op": "read",
  "node": "n-cell-2-1",
  "anchor": 0,
  "offset": 0,
  "length": 4096
}
```

Risposta:

```json
{
  "id": "4",
  "ok": true,
  "data": "...",
  "encoding": "utf-8",
  "truncated": false
}
```

Per dati binari `data` è base64 e `encoding` è `base64`.

#### close / shutdown

```json
{"id": "5", "op": "close"}
{"id": "6", "op": "shutdown"}
```

`close` distrugge lo stato del documento; `shutdown` termina l’host.

### 8.5 Errori

```json
{
  "id": "7",
  "ok": false,
  "error": {
    "code": "parse_error",
    "message": "invalid header",
    "retryable": false,
    "details": {}
  }
}
```

Codici minimi:

```text
invalid_request
unsupported
io_error
parse_error
limit_exceeded
timeout
internal_error
abi_mismatch
```

Un errore di parsing non deve terminare l’host: il documento diventa
`opaque` con warning, se possibile.

### 8.6 ABI C

La DLL espone un’ABI C versionata, non l’API Python. Funzioni concettuali:

```c
typedef struct {
    uint8_t *data;
    size_t len;
} hagar_buffer;

uint32_t hagar_document_abi_version(void);
const char *hagar_document_plugin_info(void);

int hagar_document_probe(
    const char *filename,
    const uint8_t *head,
    size_t head_len,
    double *score
);

int hagar_document_analyze(
    const char *source_path,
    const char *options_json,
    hagar_buffer *output,
    hagar_error *error
);

int hagar_document_expand(
    const char *node_id,
    uint64_t cursor,
    uint32_t limit,
    hagar_buffer *output,
    hagar_error *error
);

int hagar_document_read(
    const char *node_id,
    uint32_t anchor,
    uint64_t offset,
    uint64_t length,
    hagar_buffer *output,
    hagar_error *error
);

void hagar_document_close(void);
void hagar_document_free(hagar_buffer *buffer);
```

Regole ABI:

- solo tipi C e buffer con lunghezza;
- nessun tipo Python, C++ STL o eccezioni attraverso il confine;
- ownership dei buffer esplicita;
- `hagar_document_free` per liberare la risposta;
- la DLL non scrive su stdout;
- versione ABI obbligatoria;
- platform/arch dichiarati nel manifest.

### 8.7 Manifest del plugin nativo

```json
{
  "name": "pdf",
  "version": "1.0",
  "runtime": "native",
  "abi": 1,
  "platform": "win-x64",
  "dll": "pdf_plugin.dll",
  "dll_sha256": "...",
  "capabilities": ["analyze", "expand", "read"]
}
```

Un manifest nativo viene registrato nello stesso registry dei plugin di
formato; il runtime adapter avvia l’host.

## 9. Sicurezza

- il tool risolve il path attraverso il sandbox Hagar;
- il modello non riceve mai un path host;
- il file è aperto in sola lettura;
- il documento non viene eseguito;
- macro, JavaScript e allegati non vengono eseguiti;
- i container hanno limiti di profondità e di byte decompressi;
- l’host nativo ha timeout e viene terminato se non risponde;
- l’host nativo non è un confine di sicurezza contro DLL malevole;
- per DLL non trusted serve un sandbox OS o il rifiuto;
- il grafo è in memoria e non viene scritto nel Vault;
- l’audit registra formato, plugin, hash, dimensione e warning, non il
  contenuto.

## 10. Alternative scartate

### DLL in-process

Scartata: un crash nativo uccide Hagar; l’ABI è fragile; il sandbox
applicativo non protegge la memoria.

### Converter esterni

Scartata: LibreOffice/poppler/7zip hanno dipendenze e superfici di
attacco troppo grandi, e non sono confinabili in modo semplice.

### Grafo persistente

Scartata: il documento è la fonte di verità; il grafo è derivato e
grande. La persistenza introduce invalidazione, privacy e storage.

### Un tool per formato

Scartata: il modello dovrebbe conoscere i formati. Il tool unico
`document` mantiene stabile l’interfaccia.

### Offset senza length

Scartata: non permette di leggere un intervallo, gestire pack o
contenuti non contigui.

## 11. Test

### Contratto

- analisi CSV;
- struttura, semantica, read;
- array lazy e paginazione;
- handle chiuso/invalidato;
- file modificato;
- formato sconosciuto → opaque;
- file corrotto → opaque con warning;
- limite superato;
- path fuori sandbox rifiutato.

### Plugin

- plugin Python built-in;
- plugin Python esterno;
- plugin nativo con host finto;
- handshake ABI errato;
- host che crasha;
- host che non risponde (timeout);
- output grafo invalido;
- `read` oltre i limiti.

### CSV

- delimitatore `,`, `;`, tab;
- quoting e newline nei campi;
- BOM e UTF-8;
- header sì/no;
- righe con colonne diverse;
- file molto grande con array lazy.

## 12. Punti aperti

1. Valori iniziali dei limiti.
2. Gestione encoding non UTF-8 (fallback, warning o errore).
3. Definizione esatta del tipo `table` per CSV: header opzionale,
   colonne duplicate, tipi dedotti.
4. Policy di chiusura automatica degli handle.
5. Host nativo: sandbox OS per DLL non trusted.
6. Cache dei grafi: nessuna nel MVP; valutare in futuro.
7. Eventuale supporto a più documenti aperti nello stesso turno.
8. Formati successivi: PDF, DOCX, XLSX, PE, DXF.
