# Document tool — 架构规范

**状态：** accepted
**日期：** 2026-11-07
**范围：** 文档分析工具、格式插件、原生宿主
**MVP：** CSV

## 1. 决定

document tool 把三个层次分开：

```text
模型
  │ document.analyze / structure / semantics / read / close
  ▼
document tool
  │ FormatPlugin
  ▼
格式插件
  ├── Python runtime（进程内）
  └── 原生 runtime（独立宿主 + DLL）
```

主要决定是：

> 原生格式插件**不会被加载进 Hagar 的进程**。

它们由一个独立的原生宿主执行，该宿主加载 DLL 并通过 JSON
协议与 Hagar 通信。DLL 的崩溃或内存损坏会杀死该宿主，
而不是 Hagar。

逻辑契约 `FormatPlugin` 只有一份；变化的只是 runtime。

## 2. 为什么这样选择

### 2.1 进程内 DLL：为什么不行

用 `ctypes` 把 DLL 载入 Python 进程意味着：

- 一次 segmentation fault 可能终止 Hagar；
- DLL 可能破坏进程内存；
- Python 的 `try/except` 无法捕获原生崩溃；
- DLL 可能在没有超时的情况下阻塞进程；
- ABI 取决于编译器、C runtime、架构和操作系统；
- Hagar 的应用级 sandbox 无法限制原生代码。

对于 PDF、EXE 或 DWG 这样的格式，这一风险不可接受。

### 2.2 独立宿主：解决了什么

独立宿主解决：

- **崩溃隔离**：DLL 随其进程一起死亡；
- **ABI 隔离**：Hagar 不链接该 DLL；
- **超时**：宿主可以被终止；
- **归属**：每个原生插件一个宿主；
- **更新**：替换 DLL 无需重启 Hagar；
- **测试**：可以用稳定的协议测试宿主。

### 2.3 没有解决什么

独立进程**不是安全 sandbox**。恶意 DLL 仍可以：

- 读取用户可访问的文件；
- 打开网络连接；
- 消耗 CPU 和内存；
- 删除数据。

因此：

- **受信** DLL：为稳定性使用独立宿主；
- **不受信** DLL：独立宿主**加上**操作系统 sandbox，
  或者根本不用 DLL。

Hagar 不得把该宿主宣传为抵御恶意代码的安全保证。

### 2.4 为什么不用 LibreOffice 或其他转换器

不会调用 `libreoffice`、`poppler`、`7zip`、`ffmpeg` 或
类似工具。它们是复杂的转换器，攻击面大、
依赖系统环境，且行为难以限制。

document tool 可以使用 Python 库或 DLL，但不能使用打开并转换文档的
外部应用。

## 3. 目标与非目标

### 目标

- 识别 sandbox 中文件的格式；
- 构建可导航的结构与语义图；
- 按需、有界地提取内容；
- 隔离原生 parser；
- 保持图是临时的；
- 允许在不修改工具的情况下添加格式；
- 不重建文档。

### 非目标

- 把文档转换为另一种格式；
- 重建原始文件；
- 把图保存为永久记忆；
- 执行宏、JavaScript 或文档中包含的代码；
- 保证能识别"任何"格式；
- 向模型暴露宿主路径。

## 4. 模型-工具接口

### 4.1 操作

`path` 是 Hagar sandbox 的路径，形式为
`/home/ai/<alias>/...`；模型永远不会收到宿主路径。

```text
document.analyze(path, options?) -> handle + summary
document.structure(handle, node_id?, cursor?, limit?) -> 结构节点
document.semantics(handle, node_id?, cursor?, limit?) -> 语义节点
document.read(handle, node_id, anchor?, offset?, length?) -> 内容
document.close(handle) -> ok
```

`document.analyze`：

```json
{
  "handle": "doc-7f3a",
  "document_id": "sha256:...",
  "format": "csv",
  "plugin": "csv",
  "plugin_version": "1.0",
  "root": "n-root",
  "summary": "CSV UTF-8，分隔符 ','，120 行，5 列",
  "counts": {"nodes": 12, "semantic_nodes": 4},
  "warnings": [],
  "truncated": false
}
```

`document.structure` 只返回所请求的子节点；不返回整个
树。`document.semantics` 返回与某个
结构节点关联的语义节点。

`document.read` 是获取内容的唯一方式：

```json
{
  "node": "n-cell-2-1",
  "anchor": "n-row-2",
  "offset": 0,
  "length": 56,
  "encoding": "utf-8",
  "text": "值",
  "truncated": false
}
```

对于二进制数据：

```json
{
  "node": "n-image-1",
  "encoding": "base64",
  "data_b64": "...",
  "truncated": true
}
```

规则：

- `read` 的 offset 相对于节点的 locator，而不是文件；
- `length` 为必填，或由默认值限制；
- 响应不得超过配置的限制；
- `truncated` 是显式的；
- 不写入、没有 `save`、没有 `rebuild`。

### 4.2 Handle

一个 handle：

- 由 `analyze` 创建；
- 只在当前会话中有效；
- 绑定到 `sha256 + size + mtime + plugin + plugin_version +
  schema_version`；
- 如果文件发生变化则失效；
- 随 `close`、会话关闭或超时而消失。

它不是持久标识符，也不是记忆。

### 4.3 限制

即使在开发中，限制也是有限且可配置的：

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

初始值可以非常宽松；"无穷"不是配置值。

## 5. 格式插件

### 5.1 逻辑契约

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

`expand` 对惰性节点（`array`、`record`）是必填的。对于非压缩格式，
`read` 可以是默认实现。

### 5.2 DocumentSource

插件不会收到任意的宿主路径。它收到：

```text
size
sha256
read_range(offset, length) -> bytes
open_pack(codec, offset, length) -> DocumentSource
```

对于原生 runtime，原生宿主收到文档的**临时只读
副本**；原始路径不会传给
DLL。

### 5.3 检测

顺序：

1. magic number（如果存在）；
2. 扩展名；
3. 插件的启发式；
4. 最低置信度。

如果 magic 与扩展名冲突：

- magic number 胜出；
- 添加一条 warning；
- 选择的插件是 magic 对应的那个。

如果没有插件超过阈值：

- 图为 `opaque`；
- 只有一个节点；
- 属性中包含 `reason`、`sha256`、扩展名和大小。

CSV 没有 magic：它使用 `.csv`/`.tsv` 扩展名，加上对文本和
分隔符的启发式。

### 5.4 注册

document tool 是 `hagar.tools` 组中的一个 Hagar 插件。

格式插件使用以下组：

```text
hagar.document_formats
```

一个 entry point 返回一个描述符：

```python
@dataclass(frozen=True)
class FormatPluginSpec:
    name: str
    version: str
    runtime: str          # "python" | "native"
    manifest: str | None  # native 必填
```

对于 `runtime: "python"`，Hagar 在进程内导入并使用该插件。对于
`runtime: "native"`，Hagar 读取 manifest，校验 ABI/平台/DLL
hash，并启动原生宿主。DLL 永远不会被
Hagar 进程加载。

### 5.5 嵌套容器

一个 `pack` 可以包含另一个文档。规则：

- 最大深度；
- 最大解压字节数；
- 不允许无限递归；
- 每个新空间都有一个 `pack_id`；
- 超过限制的 pack 变为 `opaque`，不会阻塞其余部分。

## 6. 图

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

### 6.2 节点

```json
{
  "id": "n-...",
  "kind": "structural",
  "type": "section",
  "label": "第 1 页",
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

`kind`：

```text
structural
semantic
```

语义节点有一个指向结构节点的 `anchor`。如果内容不连续，它们可以
有多个 `anchors`。

### 6.3 Locator

```json
{"space": "file", "offset": 1234, "length": 56}
```

- `space` 是 `file` 或 `pack:<pack_id>`；
- `offset` 以字节为单位，从 0 开始；
- 对于可读内容，`length` 是必填的；
- 对于没有直接内容的纯结构节点，`length`
  可以为 `0`；
- 对于不连续内容，使用 `anchors`。

仅有 offset 不够：没有 `length`，工具不知道
数据的边界；没有 `space`，pack 内的 offset 是歧义的。

### 6.4 结构类型

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

- `header`：格式的正式 header；
- `section`：格式声明的正式小节或区域；
- `container`：未编码且非正式的分组；
- `pack`：压缩/编码区域，带 `codec` 和 `logical_root`；
- `array`：同质的惰性序列，带 `count`、`element_type`、
  `materialized: false`；
- `record`：简单结构，按需展开；
- `opaque`：未知对象。

### 6.5 语义类型

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

最小属性：

- `text`：`encoding`、`role`；
- `image`：`mime_type`、`width`、`height`、`codec`；
- `table`：`rows`、`columns`、`header`；
- `machine_code`：`architecture`、`entry_point`；
- `formula`：`language`、`expression`；
- `metadata`：`key`、`value`；
- `binary`：`mime_type`、`codec`。

格式特定的类型使用命名空间：

```text
pdf.page
xlsx.cell
pe.section
dxf.entity
```

### 6.6 边

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

`contains` 构成一棵树。其他边可以形成图，
甚至带环。

### 6.7 惰性数组

一个数组不会具体化所有元素：

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

模型进行展开：

```text
document.structure(handle, "n-rows", cursor=0, limit=100)
```

插件实现 `expand`，只返回所请求的页。

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

子节点具有 `space: "pack:n-pack-1"`。

## 7. CSV MVP

### 7.1 检测

- `.csv` 或 `.tsv` 扩展名；
- 文本内容；
- 一致的分隔符；
- 最低置信度。

如果文件是 `.csv` 但不是文本，或没有一致的表格结构，
结果为 `opaque`，并带 warning。

### 7.2 图

```text
document
  section "csv"
    array "rows" (lazy)
      record "row 2"
        text "字段 1"
        text "字段 2"
    semantic table "表"
      semantic column "列 A"
      semantic column "列 B"
```

根 `document` 的 locator 为 `{file, 0, size}`。

`rows` 数组带 `count`、`element_type: record`、
`materialized: false`。

每个 `record` 按需展开。每个单元格是一个 `text` 节点，带
`encoding`、`role: cell` 和精确的 locator。

语义表包含：

- 分隔符；
- encoding；
- 是否有 header；
- 列数；
- 列名；
- warning。

### 7.3 读取 CSV

```text
document.read(handle, "n-cell-2-1")
```

返回该单元格解码后的值，而不是整个文件。

对于带换行的引号字段，locator 覆盖原始字节；解码和
反转义在插件中进行。

### 7.4 CSV 限制

```text
max_file_bytes
max_rows
max_columns
max_field_bytes
max_nodes
max_read_bytes
```

插件构建行起始 offset 的索引，
以便在不具体化所有行的情况下进行惰性展开。

## 8. 原生宿主

### 8.1 模型

```text
Hagar
  └── NativeHost（Hagar 进程）
        └── 一个格式 DLL
```

每个原生插件一个宿主。宿主在首次使用时启动，进行
握手、加载 DLL，并在插件使用期间保持活动。

### 8.2 传输

- stdin/stdout 上的 UTF-8 JSON Lines；
- 每行一个请求或响应；
- stdout 专用于协议；
- 日志写入 stderr；
- 每个宿主同时只有一个在途命令；
- Hagar 侧超时；
- 崩溃后杀死并重启宿主。

### 8.3 握手

Hagar：

```json
{"id": "1", "op": "hello", "protocol": 1}
```

宿主：

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

如果 `protocol` 或 `abi` 不匹配，宿主会被拒绝。

### 8.4 命令

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

`path` 是临时的只读副本，不是原始路径。

响应：

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

响应：

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

响应：

```json
{
  "id": "4",
  "ok": true,
  "data": "...",
  "encoding": "utf-8",
  "truncated": false
}
```

对于二进制数据，`data` 是 base64，`encoding` 是 `base64`。

#### close / shutdown

```json
{"id": "5", "op": "close"}
{"id": "6", "op": "shutdown"}
```

`close` 销毁文档状态；`shutdown` 终止宿主。

### 8.5 错误

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

最小代码集：

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

解析错误不得终止宿主：在可能的情况下，文档会变为
`opaque` 并带 warning。

### 8.6 C ABI

DLL 暴露的是带版本的 C ABI，而不是 Python API。概念性函数：

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

ABI 规则：

- 只使用 C 类型和带长度的 buffer；
- 边界上不传递 Python 类型、C++ STL 或异常；
- buffer 的所有权明确；
- 用 `hagar_document_free` 释放响应；
- DLL 不写 stdout；
- ABI 版本必填；
- 平台/架构在 manifest 中声明。

### 8.7 原生插件的 manifest

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

原生 manifest 注册在与格式插件相同的 registry 中；
runtime adapter 负责启动宿主。

## 9. 安全

- 该工具通过 Hagar sandbox 解析路径；
- 模型永远不会收到宿主路径；
- 文件以只读方式打开；
- 文档不会被执行；
- 宏、JavaScript 和附件不会被执行；
- 容器有深度和解压字节限制；
- 原生宿主有超时，若不应答则被终止；
- 原生宿主不是抵御恶意 DLL 的安全边界；
- 对于不受信的 DLL，需要操作系统 sandbox 或直接拒绝；
- 图在内存中，不会写入 Vault；
- 审计记录格式、插件、hash、大小和 warning，而不记录
  内容。

## 10. 被放弃的替代方案

### 进程内 DLL

已放弃：原生崩溃会杀死 Hagar；ABI 脆弱；应用级 sandbox
不保护内存。

### 外部转换器

已放弃：LibreOffice/poppler/7zip 的依赖和攻击面过大，
且无法简单限制。

### 持久化图

已放弃：文档是事实来源；图是派生的且
庞大。持久化会引入失效、隐私和存储问题。

### 每种格式一个工具

已放弃：模型将不得不了解各种格式。单一工具
`document` 保持接口稳定。

### 只有 offset 没有 length

已放弃：无法读取区间、处理 pack 或
不连续内容。

## 11. 测试

### 契约

- CSV 分析；
- 结构、语义、read；
- 惰性数组与分页；
- 已关闭/失效的 handle；
- 文件被修改；
- 未知格式 → opaque；
- 损坏文件 → opaque 并带 warning；
- 超过限制；
- sandbox 之外的路径被拒绝。

### 插件

- 内置 Python 插件；
- 外部 Python 插件；
- 带假宿主的原生插件；
- ABI 握手错误；
- 崩溃的宿主；
- 不应答的宿主（超时）；
- 无效的图输出；
- 超出限制的 `read`。

### CSV

- 分隔符 `,`、`;`、tab；
- 字段中的引号和换行；
- BOM 与 UTF-8；
- 有/无 header；
- 列数不一致的行；
- 用惰性数组处理非常大的文件。

## 12. 开放问题

1. 限制的初始值。
2. 非 UTF-8 编码的处理（回退、warning 或错误）。
3. CSV 的 `table` 类型的精确定义：可选 header、
   重复列、推断类型。
4. handle 自动关闭的策略。
5. 原生宿主：不受信 DLL 的操作系统 sandbox。
6. 图的缓存：MVP 中没有；将来再评估。
7. 是否支持在同一轮次中打开多个文档。
8. 后续格式：PDF、DOCX、XLSX、PE、DXF。
