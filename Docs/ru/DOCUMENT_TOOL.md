# Document tool — спецификация архитектуры

**Статус:** accepted
**Дата:** 2026-11-07
**Область:** инструмент анализа документов, плагины форматов, нативный хост
**MVP:** CSV

## 1. Решение

Document tool разделяет три уровня:

```text
модель
  │ document.analyze / structure / semantics / read / close
  ▼
document tool
  │ FormatPlugin
  ▼
плагин формата
  ├── runtime Python (in-process)
  └── нативный runtime (отдельный хост + DLL)
```

Главное решение:

> нативные плагины форматов **не загружаются в процесс Hagar**.

Их выполняет отдельный нативный хост, который загружает DLL и общается
с Hagar через JSON-протокол. Падение или повреждение
памяти DLL убивает хост, а не Hagar.

Логический контракт `FormatPlugin` един; меняется только runtime.

## 2. Почему такой выбор

### 2.1 DLL in-process: почему нет

Загрузка DLL через `ctypes` в процесс Python означает:

- segmentation fault может завершить Hagar;
- DLL может повредить память процесса;
- Python `try/except` не перехватывает нативное падение;
- DLL может заблокировать процесс без тайм-аута;
- ABI зависит от компилятора, среды выполнения C, архитектуры и операционной системы;
- прикладная песочница Hagar не ограничивает нативный код.

Для такого формата, как PDF, EXE или DWG, риск недопустим.

### 2.2 Отдельный хост: что решает

Отдельный хост решает:

- **изоляцию падений**: DLL умирает вместе со своим процессом;
- **изоляцию ABI**: Hagar не линкует DLL;
- **тайм-аут**: хост можно завершить;
- **атрибуцию**: один хост на нативный плагин;
- **обновление**: DLL можно заменить, не перезапуская Hagar;
- **тестирование**: хост можно тестировать по стабильному протоколу.

### 2.3 Что не решает

Отдельный процесс **не является песочницей безопасности**. Злонамеренная DLL
всё равно может:

- читать файлы, доступные пользователю;
- открывать сетевые соединения;
- потреблять CPU и память;
- удалять данные.

Поэтому:

- DLL **trusted**: отдельный хост ради стабильности;
- DLL **не trusted**: отдельный хост **плюс** песочница
  операционной системы, либо никакой DLL.

Hagar не должен представлять хост как гарантию безопасности против враждебного
кода.

### 2.4 Почему не использовать LibreOffice или другие конвертеры

Не вызываются `libreoffice`, `poppler`, `7zip`, `ffmpeg` или
подобные. Это сложные конвертеры с широкой поверхностью атаки,
системными зависимостями и поведением, которое трудно ограничить.

Document tool может использовать библиотеку Python или DLL, но не
внешнее приложение, которое открывает и конвертирует документ.

## 3. Цели и нецели

### Цели

- распознавать формат файла в песочнице;
- строить навигируемый граф структуры и семантики;
- извлекать содержимое по запросу, ограниченными порциями;
- изолировать нативные парсеры;
- сохранять граф эфемерным;
- позволять добавлять форматы без изменения инструмента;
- не восстанавливать документ.

### Нецели

- конвертировать документ в другой формат;
- воссоздавать исходный файл;
- хранить граф как постоянную память;
- выполнять макросы, JavaScript или код, содержащийся в документе;
- гарантировать распознавание «любого» формата;
- раскрывать модели пути хоста.

## 4. Интерфейс модель–инструмент

### 4.1 Операции

`path` — это путь песочницы Hagar в форме
`/home/ai/<alias>/...`; модель никогда не получает путь хоста.

```text
document.analyze(path, options?) -> handle + summary
document.structure(handle, node_id?, cursor?, limit?) -> структурные узлы
document.semantics(handle, node_id?, cursor?, limit?) -> семантические узлы
document.read(handle, node_id, anchor?, offset?, length?) -> содержимое
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
  "summary": "CSV UTF-8, разделитель ',', 120 строк, 5 столбцов",
  "counts": {"nodes": 12, "semantic_nodes": 4},
  "warnings": [],
  "truncated": false
}
```

`document.structure` возвращает только запрошенных потомков, а не всё
дерево. `document.semantics` возвращает семантические узлы, связанные со
структурным узлом.

`document.read` — единственный способ получить содержимое:

```json
{
  "node": "n-cell-2-1",
  "anchor": "n-row-2",
  "offset": 0,
  "length": 56,
  "encoding": "utf-8",
  "text": "значение",
  "truncated": false
}
```

Для бинарных данных:

```json
{
  "node": "n-image-1",
  "encoding": "base64",
  "data_b64": "...",
  "truncated": true
}
```

Правила:

- `offset` в `read` задаётся относительно locator узла, а не файла;
- `length` обязателен или ограничен значением по умолчанию;
- ответ не может превышать настроенный лимит;
- `truncated` указывается явно;
- никакой записи, никакого `save`, никакого `rebuild`.

### 4.2 Handle

Handle:

- создаётся `analyze`;
- действителен только в текущей сессии;
- привязан к `sha256 + size + mtime + plugin + plugin_version +
  schema_version`;
- становится недействительным, если файл изменился;
- умирает с `close`, с закрытием сессии или по тайм-ауту.

Это не постоянный идентификатор и не память.

### 4.3 Лимиты

Даже при разработке лимиты конечны и настраиваемы:

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

Начальные значения могут быть очень большими; «бесконечность» не является
значением конфигурации.

## 5. Плагин формата

### 5.1 Логический контракт

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

`expand` обязателен для lazy-узлов (`array`, `record`). `read` может
быть реализацией по умолчанию для несжатых форматов.

### 5.2 DocumentSource

Плагин не получает произвольный путь хоста. Он получает:

```text
size
sha256
read_range(offset, length) -> bytes
open_pack(codec, offset, length) -> DocumentSource
```

Для нативного runtime нативный хост получает **временную копию
только для чтения** документа; исходный путь не передаётся
DLL.

### 5.3 Обнаружение

Порядок:

1. magic number, если он существует;
2. расширение;
3. эвристика плагина;
4. минимальная уверенность.

Если magic и расширение конфликтуют:

- побеждает magic number;
- добавляется warning;
- выбранный плагин — по magic.

Если ни один плагин не превышает порог:

- граф `opaque`;
- один узел;
- `reason`, `sha256`, расширение и размер в свойствах.

У CSV нет magic: используются расширение `.csv`/`.tsv` плюс эвристика по
тексту и разделителю.

### 5.4 Регистрация

Document tool — это плагин Hagar в группе `hagar.tools`.

Плагины форматов используют группу:

```text
hagar.document_formats
```

Entry point возвращает дескриптор:

```python
@dataclass(frozen=True)
class FormatPluginSpec:
    name: str
    version: str
    runtime: str          # "python" | "native"
    manifest: str | None  # обязателен для native
```

Для `runtime: "python"` Hagar импортирует и использует плагин in-process. Для
`runtime: "native"` Hagar читает manifest, проверяет ABI/platform/hash
DLL и запускает нативный хост. DLL никогда не загружается процессом
Hagar.

### 5.5 Вложенные контейнеры

Один `pack` может содержать другой документ. Правила:

- максимальная глубина;
- максимальное число распакованных байт;
- никакой неограниченной рекурсии;
- у каждого нового пространства есть `pack_id`;
- pack, превышающий лимиты, становится `opaque` и не блокирует остальное.

## 6. Граф

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

### 6.2 Узел

```json
{
  "id": "n-...",
  "kind": "structural",
  "type": "section",
  "label": "Страница 1",
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

Семантические узлы имеют `anchor` на структурный узел. Они могут
иметь несколько `anchors`, если содержимое не является непрерывным.

### 6.3 Locator

```json
{"space": "file", "offset": 1234, "length": 56}
```

- `space` — это `file` либо `pack:<pack_id>`;
- `offset` — 0-based в байтах;
- `length` обязателен для читаемого содержимого;
- для чисто структурного узла без прямого содержимого `length`
  может быть `0`;
- для несмежного содержимого используются `anchors`.

Одного offset недостаточно: без `length` инструмент не знает
границу данных; без `space` offset внутри pack неоднозначен.

### 6.4 Структурные типы

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

- `header`: официальный заголовок формата;
- `section`: официальный раздел или область, объявленная форматом;
- `container`: не кодифицированная и неофициальная группировка;
- `pack`: сжатая/кодированная зона, с `codec` и `logical_root`;
- `array`: однородная lazy-последовательность, с `count`, `element_type`,
  `materialized: false`;
- `record`: простая структура, раскрываемая по запросу;
- `opaque`: неизвестный объект.

### 6.5 Семантические типы

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

Минимальные свойства:

- `text`: `encoding`, `role`;
- `image`: `mime_type`, `width`, `height`, `codec`;
- `table`: `rows`, `columns`, `header`;
- `machine_code`: `architecture`, `entry_point`;
- `formula`: `language`, `expression`;
- `metadata`: `key`, `value`;
- `binary`: `mime_type`, `codec`.

Специфические для формата типы используют namespace:

```text
pdf.page
xlsx.cell
pe.section
dxf.entity
```

### 6.6 Дуги

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

`contains` образует дерево. Остальные дуги могут образовывать граф,
в том числе с циклами.

### 6.7 Lazy-массивы

Массив не материализует все элементы:

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

Модель раскрывает:

```text
document.structure(handle, "n-rows", cursor=0, limit=100)
```

Плагин реализует `expand` и возвращает только запрошенную страницу.

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

У детей `space: "pack:n-pack-1"`.

## 7. CSV MVP

### 7.1 Обнаружение

- расширение `.csv` или `.tsv`;
- текстовое содержимое;
- согласованный разделитель;
- минимальная уверенность.

Если файл имеет расширение `.csv`, но не является текстовым или не имеет согласованной
табличной структуры, результат — `opaque` с warning.

### 7.2 Граф

```text
document
  section "csv"
    array "rows" (lazy)
      record "row 2"
        text "поле 1"
        text "поле 2"
    semantic table "таблица"
      semantic column "столбец A"
      semantic column "столбец B"
```

Корень `document` имеет locator `{file, 0, size}`.

Массив `rows` имеет `count`, `element_type: record`,
`materialized: false`.

Каждый `record` раскрывается по запросу. Каждая ячейка — узел `text` с
`encoding`, `role: cell` и точным locator.

Семантическая таблица содержит:

- разделитель;
- encoding;
- наличие header;
- число столбцов;
- имена столбцов;
- warning.

### 7.3 Чтение CSV

```text
document.read(handle, "n-cell-2-1")
```

возвращает декодированное значение ячейки, а не весь файл.

Для поля в кавычках с newline locator покрывает сырые байты; декодирование
и снятие экранирования выполняются в плагине.

### 7.4 Лимиты CSV

```text
max_file_bytes
max_rows
max_columns
max_field_bytes
max_nodes
max_read_bytes
```

Плагин строит индекс смещений начала строк, чтобы
обеспечить ленивое раскрытие без материализации всех строк.

## 8. Нативный хост

### 8.1 Модель

```text
Hagar
  └── NativeHost (процесс Hagar)
        └── одна DLL формата
```

Один хост на нативный плагин. Хост запускается при первом использовании, выполняет
handshake, загружает DLL и остаётся активным, пока плагин используется.

### 8.2 Транспорт

- JSON Lines UTF-8 через stdin/stdout;
- один запрос или ответ на строку;
- stdout зарезервирован для протокола;
- журналы в stderr;
- только одна команда в работе на хост;
- тайм-аут на стороне Hagar;
- kill и перезапуск хоста после падения.

### 8.3 Handshake

Hagar:

```json
{"id": "1", "op": "hello", "protocol": 1}
```

Хост:

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

Если `protocol` или `abi` не совпадают, хост отклоняется.

### 8.4 Команды

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

`path` — это временная копия только для чтения, а не исходный путь.

Ответ:

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

Ответ:

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

Ответ:

```json
{
  "id": "4",
  "ok": true,
  "data": "...",
  "encoding": "utf-8",
  "truncated": false
}
```

Для бинарных данных `data` имеет кодировку base64, а `encoding` — `base64`.

#### close / shutdown

```json
{"id": "5", "op": "close"}
{"id": "6", "op": "shutdown"}
```

`close` уничтожает состояние документа; `shutdown` завершает хост.

### 8.5 Ошибки

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

Минимальные коды:

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

Ошибка разбора не должна завершать хост: документ становится
`opaque` с warning, если это возможно.

### 8.6 C ABI

DLL предоставляет версионированный C ABI, а не Python API. Концептуальные функции:

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

Правила ABI:

- только типы C и буферы с длиной;
- никаких типов Python, C++ STL или исключений через границу;
- владение буферами явное;
- `hagar_document_free` для освобождения ответа;
- DLL не пишет в stdout;
- версия ABI обязательна;
- platform/arch объявлены в manifest.

### 8.7 Manifest нативного плагина

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

Нативный manifest регистрируется в том же registry, что и плагины
форматов; runtime adapter запускает хост.

## 9. Безопасность

- инструмент разрешает путь через песочницу Hagar;
- модель никогда не получает путь хоста;
- файл открывается только для чтения;
- документ не выполняется;
- макросы, JavaScript и вложения не выполняются;
- у контейнеров есть лимиты глубины и распакованных байт;
- у нативного хоста есть тайм-аут, и он завершается, если не отвечает;
- нативный хост не является границей безопасности против злонамеренных DLL;
- для недоверенных DLL нужна песочница ОС или отказ;
- граф хранится в памяти и не записывается в Vault;
- аудит регистрирует формат, плагин, хеш, размер и warning, но не
  содержимое.

## 10. Отклонённые альтернативы

### DLL in-process

Отклонено: нативное падение убивает Hagar; ABI хрупок; прикладная песочница
не защищает память.

### Внешние конвертеры

Отклонено: у LibreOffice/poppler/7zip слишком большие зависимости и поверхности
атаки, и их непросто ограничить.

### Постоянный граф

Отклонено: документ — источник истины; граф производен и
велик. Персистентность вводит инвалидацию, приватность и хранение.

### Один инструмент на формат

Отклонено: модель должна была бы знать форматы. Единый инструмент
`document` сохраняет интерфейс стабильным.

### Offset без length

Отклонено: не позволяет читать интервал, обрабатывать pack или
несмежное содержимое.

## 11. Тесты

### Контракт

- анализ CSV;
- структура, семантика, read;
- lazy-массивы и пагинация;
- закрытый/недействительный handle;
- изменённый файл;
- неизвестный формат → opaque;
- повреждённый файл → opaque с warning;
- превышенный лимит;
- путь вне песочницы отклонён.

### Плагины

- встроенный плагин Python;
- внешний плагин Python;
- нативный плагин с фиктивным хостом;
- неверный handshake ABI;
- падающий хост;
- хост, который не отвечает (тайм-аут);
- недействительный вывод графа;
- `read` сверх лимитов.

### CSV

- разделитель `,`, `;`, tab;
- quoting и newline в полях;
- BOM и UTF-8;
- header да/нет;
- строки с разным числом столбцов;
- очень большой файл с lazy-массивом.

## 12. Открытые вопросы

1. Начальные значения лимитов.
2. Обработка кодировок, отличных от UTF-8 (fallback, warning или ошибка).
3. Точное определение типа `table` для CSV: необязательный header,
   дублирующиеся столбцы, выведенные типы.
4. Политика автоматического закрытия handle.
5. Нативный хост: песочница ОС для недоверенных DLL.
6. Кэш графов: в MVP его нет; оценить в будущем.
7. Возможная поддержка нескольких открытых документов в одном ходе.
8. Последующие форматы: PDF, DOCX, XLSX, PE, DXF.
