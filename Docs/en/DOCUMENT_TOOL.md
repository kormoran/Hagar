# Document tool — architecture specification

**Status:** accepted  
**Date:** 2026-11-07  
**Scope:** document analysis tool, format plugins, native host  
**MVP:** CSV

## 1. Decision

The document tool separates three levels:

```text
model
  │ document.analyze / structure / semantics / read / close
  ▼
document tool
  │ FormatPlugin
  ▼
format plugin
  ├── Python runtime (in-process)
  └── native runtime (separate host + DLL)
```

The main decision is:

> native format plugins **are not loaded into the Hagar process**.

They are executed by a separate native host, which loads the DLL and talks
with Hagar through a JSON protocol. A crash or a memory corruption of
the DLL kills the host, not Hagar.

The logical `FormatPlugin` contract is unique; only the runtime changes.

## 2. Why this choice

### 2.1 In-process DLL: why not

Loading a DLL with `ctypes` into the Python process means:

- a segmentation fault can terminate Hagar;
- a DLL can corrupt the process memory;
- a Python `try/except` does not catch a native crash;
- a DLL can block the process without a timeout;
- the ABI depends on compiler, C runtime, architecture and operating system;
- Hagar's application sandbox does not confine native code.

For a format such as PDF, EXE or DWG the risk is not acceptable.

### 2.2 Separate host: what it solves

The separate host solves:

- **crash isolation**: the DLL dies with its process;
- **ABI isolation**: Hagar does not link the DLL;
- **timeout**: the host can be terminated;
- **attribution**: one host per native plugin;
- **updating**: the DLL can be replaced without restarting Hagar;
- **testing**: the host can be tested with a stable protocol.

### 2.3 What it does not solve

A separate process **is not a security sandbox**. A malicious DLL
can still:

- read files accessible to the user;
- open network connections;
- consume CPU and memory;
- delete data.

Therefore:

- **trusted** DLLs: separate host for stability;
- **untrusted** DLLs: separate host **plus** an operating system
  sandbox, or no DLL at all.

Hagar must not present the host as a security guarantee against hostile
code.

### 2.4 Why not use LibreOffice or other converters

`libreoffice`, `poppler`, `7zip`, `ffmpeg` or similar are not invoked.
They are complex converters, with broad attack surfaces,
system dependencies and behaviours that are hard to confine.

The document tool can use a Python library or a DLL, but not an
external application that opens and converts the document.

## 3. Goals and non-goals

### Goals

- recognize the format of a file in the sandbox;
- build a navigable graph of structure and semantics;
- extract contents on request, in a bounded way;
- isolate the native parsers;
- keep the graph ephemeral;
- allow formats to be added without modifying the tool;
- not rebuild the document.

### Non-goals

- converting a document into another format;
- recreating the original file;
- keeping the graph as permanent memory;
- executing macros, JavaScript or code contained in the document;
- guaranteeing the recognition of "any" format;
- exposing host paths to the model.

## 4. Model-tool interface

### 4.1 Operations

`path` is a path of the Hagar sandbox, in the form
`/home/ai/<alias>/...`; the model never receives a host path.

```text
document.analyze(path, options?) -> handle + summary
document.structure(handle, node_id?, cursor?, limit?) -> structural nodes
document.semantics(handle, node_id?, cursor?, limit?) -> semantic nodes
document.read(handle, node_id, anchor?, offset?, length?) -> content
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
  "summary": "CSV UTF-8, delimiter ',', 120 rows, 5 columns",
  "counts": {"nodes": 12, "semantic_nodes": 4},
  "warnings": [],
  "truncated": false
}
```

`document.structure` returns only the requested children; not the whole
tree. `document.semantics` returns the semantic nodes associated with a
structural node.

`document.read` is the only way to obtain content:

```json
{
  "node": "n-cell-2-1",
  "anchor": "n-row-2",
  "offset": 0,
  "length": 56,
  "encoding": "utf-8",
  "text": "value",
  "truncated": false
}
```

For binary data:

```json
{
  "node": "n-image-1",
  "encoding": "base64",
  "data_b64": "...",
  "truncated": true
}
```

Rules:

- the `read` offset is relative to the node locator, not to the file;
- `length` is mandatory or limited by a default;
- the response cannot exceed the configured limit;
- `truncated` is explicit;
- no writing, no `save`, no `rebuild`.

### 4.2 Handle

A handle:

- is created by `analyze`;
- is valid only in the current session;
- is bound to `sha256 + size + mtime + plugin + plugin_version +
  schema_version`;
- is invalidated if the file changes;
- dies with `close`, with the closing of the session or with the timeout.

It is not a persistent identifier and it is not a memory.

### 4.3 Limits

Even in development the limits are finite and configurable:

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

The initial values can be very large; "infinite" is not a configuration
value.

## 5. Format plugin

### 5.1 Logical contract

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

`expand` is mandatory for the lazy nodes (`array`, `record`). `read` can
be a default implementation for the uncompressed formats.

### 5.2 DocumentSource

The plugin does not receive an arbitrary host path. It receives:

```text
size
sha256
read_range(offset, length) -> bytes
open_pack(codec, offset, length) -> DocumentSource
```

For the native runtime, the native host receives a **temporary read-only
copy** of the document; the original path is not passed to the
DLL.

### 5.3 Detection

Order:

1. magic number, if it exists;
2. extension;
3. plugin heuristic;
4. minimum confidence.

If magic and extension conflict:

- the magic number wins;
- a warning is added;
- the chosen plugin is the one of the magic.

If no plugin exceeds the threshold:

- `opaque` graph;
- a single node;
- `reason`, `sha256`, extension and size in the properties.

CSV has no magic: it uses the `.csv`/`.tsv` extension plus a heuristic on
text and delimiter.

### 5.4 Registration

The document tool is a Hagar plugin in the `hagar.tools` group.

The format plugins use the group:

```text
hagar.document_formats
```

An entry point returns a descriptor:

```python
@dataclass(frozen=True)
class FormatPluginSpec:
    name: str
    version: str
    runtime: str          # "python" | "native"
    manifest: str | None  # mandatory for native
```

For `runtime: "python"` Hagar imports and uses the plugin in-process. For
`runtime: "native"` Hagar reads the manifest, validates ABI/platform/hash
of the DLL and starts the native host. The DLL is never loaded by the
Hagar process.

### 5.5 Nested containers

A `pack` can contain another document. Rules:

- maximum depth;
- maximum decompressed bytes;
- no unlimited recursion;
- every new space has a `pack_id`;
- a pack that exceeds the limits becomes `opaque`, it does not block the rest.

## 6. Graph

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

### 6.2 Node

```json
{
  "id": "n-...",
  "kind": "structural",
  "type": "section",
  "label": "Page 1",
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

The semantic nodes have an `anchor` towards a structural node. They can
have multiple `anchors` if the content is non-contiguous.

### 6.3 Locator

```json
{"space": "file", "offset": 1234, "length": 56}
```

- `space` is `file` or `pack:<pack_id>`;
- `offset` is 0-based in bytes;
- `length` is mandatory for readable content;
- for a purely structural node without direct content, `length`
  can be `0`;
- for non-contiguous contents `anchors` is used.

A single offset is not enough: without `length` the tool does not know the
boundary of the datum; without `space` an offset inside a pack is ambiguous.

### 6.4 Structural types

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

- `header`: official header of the format;
- `section`: official section or area declared by the format;
- `container`: non-encoded and non-official grouping;
- `pack`: compressed/encoded zone, with `codec` and `logical_root`;
- `array`: homogeneous lazy sequence, with `count`, `element_type`,
  `materialized: false`;
- `record`: simple structure, expanded on request;
- `opaque`: unknown object.

### 6.5 Semantic types

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

Minimum properties:

- `text`: `encoding`, `role`;
- `image`: `mime_type`, `width`, `height`, `codec`;
- `table`: `rows`, `columns`, `header`;
- `machine_code`: `architecture`, `entry_point`;
- `formula`: `language`, `expression`;
- `metadata`: `key`, `value`;
- `binary`: `mime_type`, `codec`.

The format-specific types use a namespace:

```text
pdf.page
xlsx.cell
pe.section
dxf.entity
```

### 6.6 Edges

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

`contains` forms a tree. The other edges can form a graph,
even with cycles.

### 6.7 Lazy array

An array does not materialize all the elements:

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

The model expands:

```text
document.structure(handle, "n-rows", cursor=0, limit=100)
```

The plugin implements `expand` and returns only the requested page.

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

The children have `space: "pack:n-pack-1"`.

## 7. CSV MVP

### 7.1 Detection

- `.csv` or `.tsv` extension;
- textual content;
- consistent delimiter;
- minimum confidence.

If the file is `.csv` but is not textual or does not have a consistent
tabular structure, the result is `opaque` with a warning.

### 7.2 Graph

```text
document
  section "csv"
    array "rows" (lazy)
      record "row 2"
        text "field 1"
        text "field 2"
    semantic table "table"
      semantic column "column A"
      semantic column "column B"
```

The `document` root has locator `{file, 0, size}`.

The `rows` array has `count`, `element_type: record`,
`materialized: false`.

Every `record` is expanded on request. Every cell is a `text` node with
`encoding`, `role: cell` and precise locator.

The semantic table contains:

- delimiter;
- encoding;
- header presence;
- number of columns;
- column names;
- warnings.

### 7.3 CSV read

```text
document.read(handle, "n-cell-2-1")
```

returns the decoded value of the cell, not the whole file.

For a field quoted with newlines, the locator covers the raw bytes; the
decoding and unescaping happen in the plugin.

### 7.4 CSV limits

```text
max_file_bytes
max_rows
max_columns
max_field_bytes
max_nodes
max_read_bytes
```

The plugin builds an index of the row start offsets to
allow lazy expansion without materializing all the rows.

## 8. Native host

### 8.1 Model

```text
Hagar
  └── NativeHost (Hagar process)
        └── one format DLL
```

One host per native plugin. The host is started on first use, performs the
handshake, loads the DLL and stays active as long as the plugin is in use.

### 8.2 Transport

- UTF-8 JSON Lines on stdin/stdout;
- one request or response per line;
- stdout reserved for the protocol;
- logs on stderr;
- a single command in flight per host;
- timeout on the Hagar side;
- kill and restart of the host after a crash.

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

If `protocol` or `abi` do not match, the host is refused.

### 8.4 Commands

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

`path` is a temporary read-only copy, not the original path.

Response:

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

Response:

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

Response:

```json
{
  "id": "4",
  "ok": true,
  "data": "...",
  "encoding": "utf-8",
  "truncated": false
}
```

For binary data `data` is base64 and `encoding` is `base64`.

#### close / shutdown

```json
{"id": "5", "op": "close"}
{"id": "6", "op": "shutdown"}
```

`close` destroys the document state; `shutdown` terminates the host.

### 8.5 Errors

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

Minimum codes:

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

A parsing error must not terminate the host: the document becomes
`opaque` with a warning, if possible.

### 8.6 C ABI

The DLL exposes a versioned C ABI, not the Python API. Conceptual functions:

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

ABI rules:

- C types and buffers with length only;
- no Python or C++ STL types and no exceptions across the boundary;
- explicit buffer ownership;
- `hagar_document_free` to release the response;
- the DLL does not write to stdout;
- mandatory ABI version;
- platform/arch declared in the manifest.

### 8.7 Native plugin manifest

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

A native manifest is registered in the same registry as the format
plugins; the runtime adapter starts the host.

## 9. Security

- the tool resolves the path through the Hagar sandbox;
- the model never receives a host path;
- the file is opened read-only;
- the document is not executed;
- macros, JavaScript and attachments are not executed;
- the containers have depth and decompressed byte limits;
- the native host has a timeout and is terminated if it does not respond;
- the native host is not a security boundary against malicious DLLs;
- for untrusted DLLs an OS sandbox or refusal is required;
- the graph is in memory and is not written to the Vault;
- the audit records format, plugin, hash, size and warnings, not the
  content.

## 10. Discarded alternatives

### In-process DLL

Discarded: a native crash kills Hagar; the ABI is fragile; the application
sandbox does not protect the memory.

### External converters

Discarded: LibreOffice/poppler/7zip have dependencies and attack surfaces
that are too large, and they cannot be confined simply.

### Persistent graph

Discarded: the document is the source of truth; the graph is derived and
large. Persistence introduces invalidation, privacy and storage.

### One tool per format

Discarded: the model would have to know the formats. The single
`document` tool keeps the interface stable.

### Offset without length

Discarded: it does not allow reading a range, handling packs or
non-contiguous contents.

## 11. Tests

### Contract

- CSV analysis;
- structure, semantics, read;
- lazy array and pagination;
- closed/invalidated handle;
- modified file;
- unknown format → opaque;
- corrupted file → opaque with warning;
- limit exceeded;
- path outside the sandbox refused.

### Plugins

- built-in Python plugin;
- external Python plugin;
- native plugin with a fake host;
- wrong ABI handshake;
- host that crashes;
- host that does not respond (timeout);
- invalid graph output;
- `read` beyond the limits.

### CSV

- delimiter `,`, `;`, tab;
- quoting and newlines in the fields;
- BOM and UTF-8;
- header yes/no;
- rows with different columns;
- very large file with lazy array.

## 12. Open points

1. Initial values of the limits.
2. Handling of non-UTF-8 encodings (fallback, warning or error).
3. Exact definition of the `table` type for CSV: optional header,
   duplicate columns, inferred types.
4. Policy for automatic closing of the handles.
5. Native host: OS sandbox for untrusted DLLs.
6. Graph cache: none in the MVP; to be evaluated in the future.
7. Possible support for multiple documents open in the same turn.
8. Later formats: PDF, DOCX, XLSX, PE, DXF.
