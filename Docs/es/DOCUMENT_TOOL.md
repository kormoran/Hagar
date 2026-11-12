# Document tool — especificación de arquitectura

**Estado:** accepted  
**Fecha:** 2026-11-07  
**Ámbito:** tool de análisis de documentos, plugin de formato, host nativo  
**MVP:** CSV

## 1. Decisión

El document tool separa tres niveles:

```text
modelo
  │ document.analyze / structure / semantics / read / close
  ▼
document tool
  │ FormatPlugin
  ▼
plugin de formato
  ├── runtime Python (in-process)
  └── runtime nativo (host separado + DLL)
```

La decisión principal es:

> los plugins de formato nativos **no se cargan en el proceso de Hagar**.

Los ejecuta un host nativo separado, que carga la DLL y habla
con Hagar mediante un protocolo JSON. Un crash o una corrupción de
memoria de la DLL mata al host, no a Hagar.

El contrato lógico `FormatPlugin` es único; solo cambia el runtime.

## 2. Por qué esta elección

### 2.1 DLL in-process: por qué no

Cargar una DLL con `ctypes` en el proceso Python significa:

- un segmentation fault puede terminar Hagar;
- una DLL puede corromper la memoria del proceso;
- un `try/except` Python no intercepta un crash nativo;
- una DLL puede bloquear el proceso sin timeout;
- la ABI depende de compilador, runtime C, arquitectura y sistema operativo;
- la sandbox de la aplicación de Hagar no confina el código nativo.

Para un formato como PDF, EXE o DWG el riesgo no es aceptable.

### 2.2 Host separado: qué resuelve

El host separado resuelve:

- **crash isolation**: la DLL muere con su proceso;
- **ABI isolation**: Hagar no enlaza la DLL;
- **timeout**: el host puede terminarse;
- **atribución**: un host por plugin nativo;
- **actualización**: la DLL puede sustituirse sin reiniciar Hagar;
- **test**: el host puede probarse con un protocolo estable.

### 2.3 Qué no resuelve

Un proceso separado **no es una sandbox de seguridad**. Una DLL
maliciosa puede de todos modos:

- leer archivos accesibles al usuario;
- abrir conexiones de red;
- consumir CPU y memoria;
- borrar datos.

Por tanto:

- DLL **trusted**: host separado por estabilidad;
- DLL **no trusted**: host separado **más** sandbox del sistema
  operativo, o ninguna DLL.

Hagar no debe presentar el host como garantía de seguridad contra código
hostil.

### 2.4 Por qué no usar LibreOffice u otros converter

No se invocan `libreoffice`, `poppler`, `7zip`, `ffmpeg` o
similares. Son converter complejos, con superficies de ataque amplias,
dependencias de sistema y comportamientos difíciles de confinar.

El document tool puede usar una librería Python o una DLL, pero no una
aplicación externa que abra y convierta el documento.

## 3. Objetivos y no-objetivos

### Objetivos

- reconocer el formato de un archivo en la sandbox;
- construir un grafo navegable de estructura y semántica;
- extraer contenidos bajo petición, de forma bounded;
- aislar los parser nativos;
- mantener el grafo efímero;
- permitir añadir formatos sin modificar el tool;
- no reconstruir el documento.

### No-objetivos

- convertir un documento a otro formato;
- recrear el archivo original;
- conservar el grafo como memoria permanente;
- ejecutar macro, JavaScript o código contenido en el documento;
- garantizar el reconocimiento de "cualquier" formato;
- exponer rutas de host al modelo.

## 4. Interfaz modelo-tool

### 4.1 Operaciones

`path` es un path de la sandbox Hagar, en la forma
`/home/ai/<alias>/...`; el modelo nunca recibe un path de host.

```text
document.analyze(path, options?) -> handle + summary
document.structure(handle, node_id?, cursor?, limit?) -> nodos estructurales
document.semantics(handle, node_id?, cursor?, limit?) -> nodos semánticos
document.read(handle, node_id, anchor?, offset?, length?) -> contenido
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
  "summary": "CSV UTF-8, delimitador ',', 120 filas, 5 columnas",
  "counts": {"nodes": 12, "semantic_nodes": 4},
  "warnings": [],
  "truncated": false
}
```

`document.structure` devuelve solo los hijos solicitados; no el árbol
entero. `document.semantics` devuelve los nodos semánticos asociados a un
nodo estructural.

`document.read` es el único modo de obtener contenido:

```json
{
  "node": "n-cell-2-1",
  "anchor": "n-row-2",
  "offset": 0,
  "length": 56,
  "encoding": "utf-8",
  "text": "valor",
  "truncated": false
}
```

Para datos binarios:

```json
{
  "node": "n-image-1",
  "encoding": "base64",
  "data_b64": "...",
  "truncated": true
}
```

Reglas:

- el offset de `read` es relativo al locator del nodo, no al archivo;
- `length` es obligatorio o limitado por un default;
- la respuesta no puede superar el límite configurado;
- `truncated` es explícito;
- ninguna escritura, ningún `save`, ningún `rebuild`.

### 4.2 Handle

Un handle:

- lo crea `analyze`;
- es válido solo en la sesión actual;
- está ligado a `sha256 + size + mtime + plugin + plugin_version +
  schema_version`;
- se invalida si el archivo cambia;
- muere con `close`, con el cierre de la sesión o con el timeout.

No es un identificador persistente y no es una memoria.

### 4.3 Límites

También en desarrollo los límites son finitos y configurables:

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

Los valores iniciales pueden ser muy amplios; "infinito" no es un
valor de configuración.

## 5. Format plugin

### 5.1 Contrato lógico

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

`expand` es obligatorio para los nodos lazy (`array`, `record`). `read` puede
ser una implementación por defecto para los formatos no comprimidos.

### 5.2 DocumentSource

El plugin no recibe un path de host arbitrario. Recibe:

```text
size
sha256
read_range(offset, length) -> bytes
open_pack(codec, offset, length) -> DocumentSource
```

Para el runtime nativo, el host nativo recibe una **copia de solo lectura
temporal** del documento; el path original no se pasa a la
DLL.

### 5.3 Detección

Orden:

1. magic number, si existe;
2. extensión;
3. heurística del plugin;
4. confianza mínima.

Si magic y extensión están en conflicto:

- vence el magic number;
- se añade un warning;
- el plugin elegido es el del magic.

Si ningún plugin supera el umbral:

- grafo `opaque`;
- un solo nodo;
- `reason`, `sha256`, extensión y dimensión en las propiedades.

El CSV no tiene magic: usa extensión `.csv`/`.tsv` más una heurística sobre
texto y delimitador.

### 5.4 Registro

El document tool es un plugin Hagar en el grupo `hagar.tools`.

Los plugins de formato usan el grupo:

```text
hagar.document_formats
```

Un entry point devuelve un descriptor:

```python
@dataclass(frozen=True)
class FormatPluginSpec:
    name: str
    version: str
    runtime: str          # "python" | "native"
    manifest: str | None  # obligatorio para native
```

Para `runtime: "python"` Hagar importa y usa el plugin in-process. Para
`runtime: "native"` Hagar lee el manifest, valida ABI/platform/hash
de la DLL e inicia el host nativo. Hagar nunca carga la DLL en su
propio proceso.

### 5.5 Contenedores anidados

Un `pack` puede contener otro documento. Reglas:

- profundidad máxima;
- bytes descomprimidos máximos;
- ninguna recursión ilimitada;
- cada nuevo espacio tiene un `pack_id`;
- un pack que supera los límites se vuelve `opaque`, no bloquea el resto.

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
  "label": "Página 1",
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

Los nodos semánticos tienen un `anchor` hacia un nodo estructural. Pueden
tener `anchors` múltiples si el contenido no es contiguo.

### 6.3 Locator

```json
{"space": "file", "offset": 1234, "length": 56}
```

- `space` es `file` o bien `pack:<pack_id>`;
- `offset` es 0-based en bytes;
- `length` es obligatorio para un contenido legible;
- para un nodo puramente estructural sin contenido directo, `length`
  puede ser `0`;
- para contenidos no contiguos se usa `anchors`.

Un solo offset no es suficiente: sin `length` el tool no conoce el
límite del dato; sin `space` un offset dentro de un pack es ambiguo.

### 6.4 Tipos estructurales

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

- `header`: header oficial del formato;
- `section`: sección oficial o área declarada por el formato;
- `container`: agrupación no codificada y no oficial;
- `pack`: zona comprimida/codificada, con `codec` y `logical_root`;
- `array`: secuencia homogénea lazy, con `count`, `element_type`,
  `materialized: false`;
- `record`: estructura simple, expandida bajo petición;
- `opaque`: objeto desconocido.

### 6.5 Tipos semánticos

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

Propiedades mínimas:

- `text`: `encoding`, `role`;
- `image`: `mime_type`, `width`, `height`, `codec`;
- `table`: `rows`, `columns`, `header`;
- `machine_code`: `architecture`, `entry_point`;
- `formula`: `language`, `expression`;
- `metadata`: `key`, `value`;
- `binary`: `mime_type`, `codec`.

Los tipos específicos del formato usan un namespace:

```text
pdf.page
xlsx.cell
pe.section
dxf.entity
```

### 6.6 Arcos

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

`contains` forma un árbol. Los demás arcos pueden formar un grafo,
incluso con ciclos.

### 6.7 Array lazy

Un array no materializa todos los elementos:

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

El modelo expande:

```text
document.structure(handle, "n-rows", cursor=0, limit=100)
```

El plugin implementa `expand` y devuelve solo la página solicitada.

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

Los hijos tienen `space: "pack:n-pack-1"`.

## 7. CSV MVP

### 7.1 Detección

- extensión `.csv` o `.tsv`;
- contenido textual;
- delimitador coherente;
- confianza mínima.

Si el archivo es `.csv` pero no es textual o no tiene una estructura tabular
coherente, el resultado es `opaque` con warning.

### 7.2 Grafo

```text
document
  section "csv"
    array "rows" (lazy)
      record "row 2"
        text "campo 1"
        text "campo 2"
    semantic table "tabla"
      semantic column "columna A"
      semantic column "columna B"
```

La raíz `document` tiene locator `{file, 0, size}`.

El array `rows` tiene `count`, `element_type: record`,
`materialized: false`.

Cada `record` se expande bajo petición. Cada celda es un nodo `text` con
`encoding`, `role: cell` y locator preciso.

La tabla semántica contiene:

- delimitador;
- encoding;
- presencia de header;
- número de columnas;
- nombres de columnas;
- warning.

### 7.3 Read CSV

```text
document.read(handle, "n-cell-2-1")
```

devuelve el valor decodificado de la celda, no el archivo entero.

Para un campo entrecomillado con newline, el locator cubre los bytes crudos; la
decodificación y el unescaping se realizan en el plugin.

### 7.4 Límites CSV

```text
max_file_bytes
max_rows
max_columns
max_field_bytes
max_nodes
max_read_bytes
```

El plugin construye un índice de los offsets de inicio de línea para
permitir la expansión lazy sin materializar todas las filas.

## 8. Host nativo

### 8.1 Modelo

```text
Hagar
  └── NativeHost (proceso Hagar)
        └── una DLL de formato
```

Un host por plugin nativo. El host se inicia en el primer uso, hace
handshake, carga la DLL y permanece activo mientras el plugin está en uso.

### 8.2 Transporte

- JSON Lines UTF-8 sobre stdin/stdout;
- una petición o respuesta por línea;
- stdout reservado al protocolo;
- log en stderr;
- un solo comando en vuelo por host;
- timeout del lado de Hagar;
- kill y reinicio del host tras un crash.

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

Si `protocol` o `abi` no corresponden, el host se rechaza.

### 8.4 Comandos

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

`path` es una copia de solo lectura temporal, no el path original.

Respuesta:

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

Respuesta:

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

Respuesta:

```json
{
  "id": "4",
  "ok": true,
  "data": "...",
  "encoding": "utf-8",
  "truncated": false
}
```

Para datos binarios `data` es base64 y `encoding` es `base64`.

#### close / shutdown

```json
{"id": "5", "op": "close"}
{"id": "6", "op": "shutdown"}
```

`close` destruye el estado del documento; `shutdown` termina el host.

### 8.5 Errores

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

Códigos mínimos:

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

Un error de parsing no debe terminar el host: el documento se vuelve
`opaque` con warning, si es posible.

### 8.6 ABI C

La DLL expone una ABI C versionada, no la API Python. Funciones conceptuales:

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

Reglas ABI:

- solo tipos C y buffer con longitud;
- ningún tipo Python, C++ STL o excepción a través del límite;
- ownership de los buffer explícito;
- `hagar_document_free` para liberar la respuesta;
- la DLL no escribe en stdout;
- versión ABI obligatoria;
- platform/arch declarados en el manifest.

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

Un manifest nativo se registra en el mismo registry de los plugins de
formato; el runtime adapter inicia el host.

## 9. Seguridad

- el tool resuelve el path a través de la sandbox Hagar;
- el modelo nunca recibe un path de host;
- el archivo se abre en solo lectura;
- el documento no se ejecuta;
- macro, JavaScript y adjuntos no se ejecutan;
- los contenedores tienen límites de profundidad y de bytes descomprimidos;
- el host nativo tiene timeout y se termina si no responde;
- el host nativo no es un límite de seguridad contra DLL maliciosas;
- para DLL no trusted hace falta una sandbox de SO o el rechazo;
- el grafo está en memoria y no se escribe en el Vault;
- la auditoría registra formato, plugin, hash, dimensión y warning, no el
  contenido.

## 10. Alternativas descartadas

### DLL in-process

Descartada: un crash nativo mata Hagar; la ABI es frágil; la sandbox
de la aplicación no protege la memoria.

### Converter externos

Descartada: LibreOffice/poppler/7zip tienen dependencias y superficies de
ataque demasiado grandes, y no son confinables de forma simple.

### Grafo persistente

Descartada: el documento es la fuente de verdad; el grafo es derivado y
grande. La persistencia introduce invalidación, privacidad y storage.

### Un tool por formato

Descartada: el modelo debería conocer los formatos. El tool único
`document` mantiene estable la interfaz.

### Offset sin length

Descartada: no permite leer un intervalo, gestionar pack o
contenidos no contiguos.

## 11. Test

### Contrato

- análisis CSV;
- estructura, semántica, read;
- array lazy y paginación;
- handle cerrado/invalidado;
- archivo modificado;
- formato desconocido → opaque;
- archivo corrupto → opaque con warning;
- límite superado;
- path fuera de la sandbox rechazado.

### Plugin

- plugin Python built-in;
- plugin Python externo;
- plugin nativo con host falso;
- handshake ABI erróneo;
- host que crashea;
- host que no responde (timeout);
- output grafo inválido;
- `read` más allá de los límites.

### CSV

- delimitador `,`, `;`, tab;
- quoting y newline en los campos;
- BOM y UTF-8;
- header sí/no;
- filas con columnas distintas;
- archivo muy grande con array lazy.

## 12. Puntos abiertos

1. Valores iniciales de los límites.
2. Gestión de encoding no UTF-8 (fallback, warning o error).
3. Definición exacta del tipo `table` para CSV: header opcional,
   columnas duplicadas, tipos deducidos.
4. Policy de cierre automático de los handle.
5. Host nativo: sandbox de SO para DLL no trusted.
6. Cache de los grafos: ninguna en el MVP; evaluar en el futuro.
7. Eventual soporte a varios documentos abiertos en el mismo turno.
8. Formatos posteriores: PDF, DOCX, XLSX, PE, DXF.
