# Document tool — especificação de arquitetura

**Estado:** accepted
**Data:** 2026-11-07
**Âmbito:** ferramenta de análise de documentos, plugins de formato, host nativo
**MVP:** CSV

## 1. Decisão

A document tool separa três níveis:

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

A decisão principal é:

> os plugins de formato nativos **não são carregados no processo do Hagar**.

São executados por um host nativo separado, que carrega a DLL e fala
com o Hagar através de um protocolo JSON. Um crash ou uma corrupção de
memória da DLL mata o host, não o Hagar.

O contrato lógico `FormatPlugin` é único; muda apenas o runtime.

## 2. Porquê esta escolha

### 2.1 In-process DLL: porquê não

Carregar uma DLL com `ctypes` no processo Python significa:

- um segmentation fault pode terminar o Hagar;
- uma DLL pode corromper a memória do processo;
- uma `try/except` Python não interceta um crash nativo;
- uma DLL pode bloquear o processo sem timeout;
- a ABI depende de compilador, runtime C, arquitetura e sistema operativo;
- a sandbox aplicacional do Hagar não confina o código nativo.

Para um formato como PDF, EXE ou DWG o risco não é aceitável.

### 2.2 Host separado: o que resolve

O host separado resolve:

- **crash isolation**: a DLL morre com o seu processo;
- **ABI isolation**: o Hagar não liga a DLL;
- **timeout**: o host pode ser terminado;
- **atribuição**: um host por plugin nativo;
- **atualização**: a DLL pode ser substituída sem reiniciar o Hagar;
- **testes**: o host pode ser testado com um protocolo estável.

### 2.3 O que não resolve

Um processo separado **não é uma sandbox de segurança**. Uma DLL
maliciosa pode, ainda assim:

- ler ficheiros acessíveis ao utilizador;
- abrir ligações de rede;
- consumir CPU e memória;
- apagar dados.

Portanto:

- DLL **trusted**: host separado por estabilidade;
- DLL **não trusted**: host separado **mais** sandbox do sistema
  operativo, ou nenhuma DLL.

O Hagar não deve apresentar o host como garantia de segurança contra código
hostil.

### 2.4 Porquê não usar LibreOffice ou outros converters

Não são invocados `libreoffice`, `poppler`, `7zip`, `ffmpeg` ou
semelhantes. São converters complexos, com superfícies de ataque amplas,
dependências de sistema e comportamentos difíceis de confinar.

A document tool pode usar uma biblioteca Python ou uma DLL, mas não uma
aplicação externa que abre e converte o documento.

## 3. Objetivos e não-objetivos

### Objetivos

- reconhecer o formato de um ficheiro na sandbox;
- construir um grafo navegável de estrutura e semântica;
- extrair conteúdos a pedido, de forma bounded;
- isolar os parser nativos;
- manter o grafo efémero;
- permitir o acrescento de formatos sem modificar a ferramenta;
- não reconstruir o documento.

### Não-objetivos

- converter um documento noutro formato;
- recriar o ficheiro original;
- conservar o grafo como memória permanente;
- executar macro, JavaScript ou código contido no documento;
- garantir o reconhecimento de "qualquer" formato;
- expor percursos host ao modelo.

## 4. Interface modelo-ferramenta

### 4.1 Operações

`path` é um path da sandbox Hagar, na forma
`/home/ai/<alias>/...`; o modelo nunca recebe um path host.

```text
document.analyze(path, options?) -> handle + summary
document.structure(handle, node_id?, cursor?, limit?) -> nós estruturais
document.semantics(handle, node_id?, cursor?, limit?) -> nós semânticos
document.read(handle, node_id, anchor?, offset?, length?) -> conteúdo
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
  "summary": "CSV UTF-8, delimitador ',', 120 linhas, 5 colunas",
  "counts": {"nodes": 12, "semantic_nodes": 4},
  "warnings": [],
  "truncated": false
}
```

`document.structure` devolve apenas os filhos pedidos; não a árvore
inteira. `document.semantics` devolve os nós semânticos associados a um
nó estrutural.

`document.read` é o único modo de obter conteúdo:

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

Para dados binários:

```json
{
  "node": "n-image-1",
  "encoding": "base64",
  "data_b64": "...",
  "truncated": true
}
```

Regras:

- o offset de `read` é relativo ao locator do nó, não ao ficheiro;
- `length` é obrigatório ou limitado por um default;
- a resposta não pode ultrapassar o limite configurado;
- `truncated` é explícito;
- nenhuma escrita, nenhum `save`, nenhum `rebuild`.

### 4.2 Handle

Um handle:

- é criado por `analyze`;
- é válido apenas na sessão corrente;
- está ligado a `sha256 + size + mtime + plugin + plugin_version +
  schema_version`;
- é invalidado se o ficheiro mudar;
- morre com `close`, com o fecho da sessão ou com o timeout.

Não é um identificador persistente e não é uma memória.

### 4.3 Limites

Também em desenvolvimento os limites são finitos e configuráveis:

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

Os valores iniciais podem ser muito largos; "infinito" não é um
valor de configuração.

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

`expand` é obrigatório para os nós lazy (`array`, `record`). `read` pode
ser uma implementação de default para os formatos não comprimidos.

### 5.2 DocumentSource

O plugin não recebe um path host arbitrário. Recebe:

```text
size
sha256
read_range(offset, length) -> bytes
open_pack(codec, offset, length) -> DocumentSource
```

Para o runtime nativo, o host nativo recebe uma **cópia read-only
temporária** do documento; o path original não é passado à
DLL.

### 5.3 Deteção

Ordem:

1. magic number, se existir;
2. extensão;
3. heurística do plugin;
4. confiança mínima.

Se magic e extensão estiverem em conflito:

- vence o magic number;
- é acrescentado um warning;
- o plugin escolhido é o do magic.

Se nenhum plugin ultrapassar o limiar:

- grafo `opaque`;
- um único nó;
- `reason`, `sha256`, extensão e dimensão nas propriedades.

O CSV não tem magic: usa a extensão `.csv`/`.tsv` mais uma heurística sobre
texto e delimitador.

### 5.4 Registo

A document tool é um plugin Hagar no grupo `hagar.tools`.

Os plugins de formato usam o grupo:

```text
hagar.document_formats
```

Um entry point devolve um descritor:

```python
@dataclass(frozen=True)
class FormatPluginSpec:
    name: str
    version: str
    runtime: str          # "python" | "native"
    manifest: str | None  # obrigatório para native
```

Para `runtime: "python"` o Hagar importa e usa o plugin in-process. Para
`runtime: "native"` o Hagar lê o manifest, valida ABI/platform/hash
da DLL e arranca o host nativo. A DLL nunca é carregada pelo
processo Hagar.

### 5.5 Container aninhados

Um `pack` pode conter outro documento. Regras:

- profundidade máxima;
- bytes descomprimidos máximos;
- nenhuma recursão ilimitada;
- cada novo espaço tem um `pack_id`;
- um pack que ultrapassa os limites torna-se `opaque`, não bloqueia o resto.

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

### 6.2 Nó

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

Os nós semânticos têm um `anchor` para um nó estrutural. Podem
ter `anchors` múltiplos se o conteúdo não for contíguo.

### 6.3 Locator

```json
{"space": "file", "offset": 1234, "length": 56}
```

- `space` é `file` ou `pack:<pack_id>`;
- `offset` é 0-based em bytes;
- `length` é obrigatório para um conteúdo legível;
- para um nó puramente estrutural sem conteúdo direto, `length`
  pode ser `0`;
- para conteúdos não contíguos usa-se `anchors`.

Um único offset não é suficiente: sem `length` a ferramenta não conhece o
limite do dado; sem `space` um offset dentro de um pack é ambíguo.

### 6.4 Tipos estruturais

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

- `header`: header oficial do formato;
- `section`: secção oficial ou área declarada pelo formato;
- `container`: agrupamento não codificado e não oficial;
- `pack`: zona comprimida/codificada, com `codec` e `logical_root`;
- `array`: sequência homogénea lazy, com `count`, `element_type`,
  `materialized: false`;
- `record`: estrutura simples, expandida a pedido;
- `opaque`: objeto desconhecido.

### 6.5 Tipos semânticos

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

Propriedades mínimas:

- `text`: `encoding`, `role`;
- `image`: `mime_type`, `width`, `height`, `codec`;
- `table`: `rows`, `columns`, `header`;
- `machine_code`: `architecture`, `entry_point`;
- `formula`: `language`, `expression`;
- `metadata`: `key`, `value`;
- `binary`: `mime_type`, `codec`.

Os tipos específicos do formato usam um namespace:

```text
pdf.page
xlsx.cell
pe.section
dxf.entity
```

### 6.6 Arestas

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

`contains` forma uma árvore. As outras arestas podem formar um grafo,
também com ciclos.

### 6.7 Array lazy

Um array não materializa todos os elementos:

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

O modelo expande:

```text
document.structure(handle, "n-rows", cursor=0, limit=100)
```

O plugin implementa `expand` e devolve apenas a página pedida.

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

Os filhos têm `space: "pack:n-pack-1"`.

## 7. CSV MVP

### 7.1 Deteção

- extensão `.csv` ou `.tsv`;
- conteúdo textual;
- delimitador coerente;
- confiança mínima.

Se o ficheiro for `.csv` mas não for textual ou não tiver uma estrutura tabular
coerente, o resultado é `opaque` com warning.

### 7.2 Grafo

```text
document
  section "csv"
    array "rows" (lazy)
      record "row 2"
        text "campo 1"
        text "campo 2"
    semantic table "tabela"
      semantic column "coluna A"
      semantic column "coluna B"
```

A raiz `document` tem locator `{file, 0, size}`.

O array `rows` tem `count`, `element_type: record`,
`materialized: false`.

Cada `record` é expandido a pedido. Cada célula é um nó `text` com
`encoding`, `role: cell` e locator preciso.

A tabela semântica contém:

- delimitador;
- encoding;
- presença de header;
- número de colunas;
- nomes das colunas;
- warning.

### 7.3 Read CSV

```text
document.read(handle, "n-cell-2-1")
```

devolve o valor descodificado da célula, não o ficheiro inteiro.

Para um campo entre aspas com newline, o locator cobre os bytes em bruto; a
descodificação e o unescaping ocorrem no plugin.

### 7.4 Limites CSV

```text
max_file_bytes
max_rows
max_columns
max_field_bytes
max_nodes
max_read_bytes
```

O plugin constrói um índice dos offsets de início de linha para
permitir a expansão lazy sem materializar todas as linhas.

## 8. Host nativo

### 8.1 Modelo

```text
Hagar
  └── NativeHost (processo Hagar)
        └── uma DLL de formato
```

Um host por plugin nativo. O host é arrancado no primeiro uso, faz
handshake, carrega a DLL e permanece ativo enquanto o plugin estiver em uso.

### 8.2 Transporte

- JSON Lines UTF-8 em stdin/stdout;
- um pedido ou resposta por linha;
- stdout reservado ao protocolo;
- log em stderr;
- um único comando em voo por host;
- timeout do lado do Hagar;
- kill e reinício do host após um crash.

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

Se `protocol` ou `abi` não corresponderem, o host é recusado.

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

`path` é uma cópia read-only temporária, não o path original.

Resposta:

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

Resposta:

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

Resposta:

```json
{
  "id": "4",
  "ok": true,
  "data": "...",
  "encoding": "utf-8",
  "truncated": false
}
```

Para dados binários `data` é base64 e `encoding` é `base64`.

#### close / shutdown

```json
{"id": "5", "op": "close"}
{"id": "6", "op": "shutdown"}
```

`close` destrói o estado do documento; `shutdown` termina o host.

### 8.5 Erros

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

Um erro de parsing não deve terminar o host: o documento torna-se
`opaque` com warning, se possível.

### 8.6 ABI C

A DLL expõe uma ABI C versionada, não a API Python. Funções concetuais:

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

Regras ABI:

- apenas tipos C e buffer com comprimento;
- nenhum tipo Python, C++ STL ou exceções através da fronteira;
- ownership dos buffer explícita;
- `hagar_document_free` para libertar a resposta;
- a DLL não escreve em stdout;
- versão ABI obrigatória;
- platform/arch declarados no manifest.

### 8.7 Manifest do plugin nativo

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

Um manifest nativo é registado no mesmo registry dos plugins de
formato; o runtime adapter arranca o host.

## 9. Segurança

- a ferramenta resolve o path através da sandbox Hagar;
- o modelo nunca recebe um path host;
- o ficheiro é aberto em só de leitura;
- o documento não é executado;
- macro, JavaScript e anexos não são executados;
- os container têm limites de profundidade e de bytes descomprimidos;
- o host nativo tem timeout e é terminado se não responder;
- o host nativo não é uma fronteira de segurança contra DLL maliciosas;
- para DLL não trusted é necessária uma sandbox de SO ou a recusa;
- o grafo está em memória e não é escrito no Vault;
- a auditoria registra formato, plugin, hash, dimensão e warning, não o
  conteúdo.

## 10. Alternativas descartadas

### DLL in-process

Descartada: um crash nativo mata o Hagar; a ABI é frágil; a sandbox
aplicacional não protege a memória.

### Converter externos

Descartada: LibreOffice/poppler/7zip têm dependências e superfícies de
ataque demasiado grandes, e não são confináveis de forma simples.

### Grafo persistente

Descartada: o documento é a fonte de verdade; o grafo é derivado e
grande. A persistência introduz invalidação, privacidade e storage.

### Uma ferramenta por formato

Descartada: o modelo teria de conhecer os formatos. A ferramenta única
`document` mantém a interface estável.

### Offset sem length

Descartada: não permite ler um intervalo, gerir pack ou
conteúdos não contíguos.

## 11. Testes

### Contrato

- análise CSV;
- estrutura, semântica, read;
- array lazy e paginação;
- handle fechado/invalidado;
- ficheiro modificado;
- formato desconhecido → opaque;
- ficheiro corrompido → opaque com warning;
- limite ultrapassado;
- path fora da sandbox recusado.

### Plugin

- plugin Python built-in;
- plugin Python externo;
- plugin nativo com host falso;
- handshake ABI errado;
- host que crasha;
- host que não responde (timeout);
- output grafo inválido;
- `read` acima dos limites.

### CSV

- delimitador `,`, `;`, tab;
- quoting e newline nos campos;
- BOM e UTF-8;
- header sim/não;
- linhas com colunas diferentes;
- ficheiro muito grande com array lazy.

## 12. Pontos abertos

1. Valores iniciais dos limites.
2. Gestão de encoding não UTF-8 (fallback, warning ou erro).
3. Definição exata do tipo `table` para CSV: header opcional,
   colunas duplicadas, tipos deduzidos.
4. Política de fecho automático dos handle.
5. Host nativo: sandbox de SO para DLL não trusted.
6. Cache dos grafos: nenhuma no MVP; avaliar no futuro.
7. Eventual suporte a vários documentos abertos no mesmo turno.
8. Formatos seguintes: PDF, DOCX, XLSX, PE, DXF.
