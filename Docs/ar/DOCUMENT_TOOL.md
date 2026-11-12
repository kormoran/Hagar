# أداة المستندات — مواصفة المعمارية

**الحالة:** accepted  
**التاريخ:** 2026-11-07  
**النطاق:** أداة تحليل المستندات، وإضافات الصيغ، والمضيف الأصلي  
**MVP:** CSV

## 1. القرار

تفصل أداة المستندات ثلاثة مستويات:

```text
النموذج
  │ document.analyze / structure / semantics / read / close
  ▼
أداة المستندات
  │ FormatPlugin
  ▼
إضافة الصيغة
  ├── runtime Python (in-process)
  └── runtime أصلي (مضيف منفصل + DLL)
```

والقرار الأساسي هو:

> إضافات الصيغ الأصلية **لا تُحمَّل في عملية Hagar**.

بل يشغّلها مضيف أصلي منفصل، يحمّل الـ DLL ويتحدث
مع Hagar عبر بروتوكول JSON. فانهيار أو فساد في
ذاكرة الـ DLL يقتل المضيف، لا Hagar.

والعقد المنطقي `FormatPlugin` واحد؛ ولا يتغير إلا الـ runtime.

## 2. لماذا هذا الاختيار

### 2.1 DLL داخل العملية: لماذا لا

تحميل DLL بـ `ctypes` في عملية Python يعني:

- أن خطأ segfault قد يُنهي Hagar؛
- أن الـ DLL قد تفسد ذاكرة العملية؛
- أن `try/except` في Python لا يعترض انهيارًا أصليًا؛
- أن الـ DLL قد تجمّد العملية بلا مهلة؛
- أن الـ ABI تعتمد على المترجم وruntime C والمعمارية ونظام التشغيل؛
- أن صندوق رمل Hagar التطبيقي لا يحصر الشيفرة الأصلية.

ولصيغة مثل PDF أو EXE أو DWG، المخاطرة غير مقبولة.

### 2.2 المضيف المنفصل: ما يحله

يحل المضيف المنفصل:

- **عزل الانهيار** (crash isolation): تموت الـ DLL مع عمليتها؛
- **عزل الـ ABI**: لا يربط Hagar الـ DLL؛
- **المهلة**: يمكن إنهاء المضيف؛
- **النسبة**: مضيف واحد لكل إضافة أصلية؛
- **التحديث**: يمكن استبدال الـ DLL دون إعادة تشغيل Hagar؛
- **الاختبار**: يمكن اختبار المضيف ببروتوكول مستقر.

### 2.3 ما لا يحله

العملية المنفصلة **ليست صندوق رمل أمنيًا**. فالـ DLL
الخبيثة يمكنها مع ذلك:

- قراءة ملفات يمكن للمستخدم الوصول إليها؛
- فتح اتصالات شبكية؛
- استهلاك المعالج والذاكرة؛
- حذف بيانات.

لذلك:

- الـ DLL **الموثوقة**: مضيف منفصل من أجل الاستقرار؛
- الـ DLL **غير الموثوقة**: مضيف منفصل **إضافة إلى** صندوق رمل على مستوى
  نظام التشغيل، أو لا DLL أصلًا.

ويجب ألا يقدّم Hagar المضيف كضمان أمني ضد شيفرة
معادية.

### 2.4 لماذا لا نستخدم LibreOffice أو محوّلات أخرى

لا تُستدعى `libreoffice` ولا `poppler` ولا `7zip` ولا `ffmpeg` ولا
ما شابهها. فهي محوّلات معقدة، بأسطح هجوم واسعة،
وتبعيات نظامية وسلوكيات يصعب حصرها.

ويمكن لأداة المستندات استخدام مكتبة Python أو DLL، لكن لا
تطبيقًا خارجيًا يفتح المستند ويحوّله.

## 3. الأهداف وما ليس ضمن الأهداف

### الأهداف

- التعرّف على صيغة ملف في صندوق الرمل؛
- بناء رسم بياني قابل للتنقل للبنية والدلالة؛
- استخراج المحتويات عند الطلب، على نحو محدود (bounded)؛
- عزل المحلّلات الأصلية؛
- إبقاء الرسم البياني مؤقتًا؛
- إتاحة إضافة صيغ دون تعديل الأداة؛
- عدم إعادة بناء المستند.

### ما ليس ضمن الأهداف

- تحويل مستند إلى صيغة أخرى؛
- إعادة إنشاء الملف الأصلي؛
- حفظ الرسم البياني كذاكرة دائمة؛
- تنفيذ ماكرو أو JavaScript أو شيفرة محتواة في المستند؛
- ضمان التعرّف على "أي" صيغة؛
- كشف مسارات المضيف للنموذج.

## 4. واجهة النموذج-الأداة

### 4.1 العمليات

`path` مسار في صندوق رمل Hagar، بالشكل
`/home/ai/<alias>/...`؛ ولا يتلقى النموذج مسار مضيف أبدًا.

```text
document.analyze(path, options?) -> handle + summary
document.structure(handle, node_id?, cursor?, limit?) -> عقد بنيوية
document.semantics(handle, node_id?, cursor?, limit?) -> عقد دلالية
document.read(handle, node_id, anchor?, offset?, length?) -> محتوى
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
  "summary": "CSV UTF-8, المحدّد ',', 120 سطرًا, 5 أعمدة",
  "counts": {"nodes": 12, "semantic_nodes": 4},
  "warnings": [],
  "truncated": false
}
```

يعيد `document.structure` الأبناء المطلوبين فقط؛ لا الشجرة
كلها. ويعيد `document.semantics` العقد الدلالية المرتبطة بعقدة
بنيوية.

و`document.read` هو الطريق الوحيد للحصول على المحتوى:

```json
{
  "node": "n-cell-2-1",
  "anchor": "n-row-2",
  "offset": 0,
  "length": 56,
  "encoding": "utf-8",
  "text": "قيمة",
  "truncated": false
}
```

وللبيانات الثنائية:

```json
{
  "node": "n-image-1",
  "encoding": "base64",
  "data_b64": "...",
  "truncated": true
}
```

القواعد:

- إزاحة `read` نسبية إلى locator العقدة، لا إلى الملف؛
- `length` إلزامي أو محدود بقيمة افتراضية؛
- لا يمكن للرد أن يتجاوز الحد المُعدّ؛
- `truncated` صريح؛
- لا كتابة ولا `save` ولا `rebuild`.

### 4.2 الـ handle

الـ handle:

- يُنشأ بـ `analyze`؛
- صالح في الجلسة الحالية فقط؛
- مرتبط بـ `sha256 + size + mtime + plugin + plugin_version +
  schema_version`؛
- يُبطَل إذا تغيّر الملف؛
- يموت مع `close` أو مع إغلاق الجلسة أو مع المهلة.

وهو ليس معرّفًا دائمًا وليس ذاكرة.

### 4.3 الحدود

حتى في التطوير تكون الحدود منتهية وقابلة للإعداد:

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

ويمكن أن تكون القيم الأولية واسعة جدًا؛ أما "لا نهائي" فليس
قيمة إعداد.

## 5. إضافة الصيغة

### 5.1 العقد المنطقي

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

`expand` إلزامي للعقد الكسولة (`array` و`record`). ويمكن أن يكون `read`
تطبيقًا افتراضيًا للصيغ غير المضغوطة.

### 5.2 DocumentSource

لا تتلقى الإضافة مسار مضيف عشوائيًا. بل تتلقى:

```text
size
sha256
read_range(offset, length) -> bytes
open_pack(codec, offset, length) -> DocumentSource
```

وللـ runtime الأصلي، يتلقى المضيف الأصلي **نسخة للقراءة فقط
ومؤقتة** من المستند؛ ولا يُمرَّر المسار الأصلي إلى
الـ DLL.

### 5.3 الاكتشاف

الترتيب:

1. magic number، إن وُجد؛
2. الامتداد؛
3. استدلال الإضافة (heuristic)؛
4. حد أدنى للثقة.

وإذا تعارض الـ magic والامتداد:

- يفوز magic number؛
- يُضاف تحذير؛
- والإضافة المختارة هي إضافة الـ magic.

وإذا لم تتجاوز أي إضافة العتبة:

- رسم `opaque`؛
- عقدة واحدة؛
- `reason` و`sha256` والامتداد والحجم في الخصائص.

ولا magic للـ CSV: بل يُستخدم الامتداد `.csv`/`.tsv` إضافة إلى استدلال على
النص والمحدّد (delimiter).

### 5.4 التسجيل

أداة المستندات إضافة Hagar في المجموعة `hagar.tools`.

وتستخدم إضافات الصيغ المجموعة:

```text
hagar.document_formats
```

ويعيد entry point واصفًا:

```python
@dataclass(frozen=True)
class FormatPluginSpec:
    name: str
    version: str
    runtime: str          # "python" | "native"
    manifest: str | None  # إلزامي للـ native
```

ومع `runtime: "python"` يستورد Hagar الإضافة ويستخدمها داخل العملية. ومع
`runtime: "native"` يقرأ Hagar الـ manifest، ويتحقق من ABI/platform/hash
الخاصة بالـ DLL ويشغّل المضيف الأصلي. ولا تُحمَّل الـ DLL أبدًا من
عملية Hagar.

### 5.5 الحاويات المتداخلة

قد يحتوي `pack` على مستند آخر. القواعد:

- عمق أقصى؛
- بايتات مفكوكة بحد أقصى؛
- لا تكرار غير محدود؛
- لكل فضاء جديد `pack_id`؛
- الـ pack الذي يتجاوز الحدود يصبح `opaque`، ولا يوقف الباقي.

## 6. الرسم البياني

### 6.1 الـ Envelope

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

### 6.2 العقدة

```json
{
  "id": "n-...",
  "kind": "structural",
  "type": "section",
  "label": "الصفحة 1",
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

والعقد الدلالية لها `anchor` نحو عقدة بنيوية. وقد يكون لها
`anchors` متعددة إذا كان المحتوى غير متجاور.

### 6.3 الـ Locator

```json
{"space": "file", "offset": 1234, "length": 56}
```

- `space` هو `file` أو `pack:<pack_id>`؛
- `offset` يبدأ من 0 بالبايت؛
- `length` إلزامي لمحتوى قابل للقراءة؛
- ولعقدة بنيوية بحتة بلا محتوى مباشر، يمكن أن يكون `length`
  هو `0`؛
- وللمحتويات غير المتجاورة تُستخدم `anchors`.

إزاحة واحدة لا تكفي: فبدون `length` لا تعرف الأداة
حدود البيانات؛ وبدون `space` تكون الإزاحة داخل pack ملتبسة.

### 6.4 الأنواع البنيوية

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

- `header`: ترويسة رسمية للصيغة؛
- `section`: قسم رسمي أو منطقة معلنة من الصيغة؛
- `container`: تجميع غير مشفّر وغير رسمي؛
- `pack`: منطقة مضغوطة/مشفّرة، مع `codec` و`logical_root`؛
- `array`: تسلسل متجانس كسول، مع `count` و`element_type`
  و`materialized: false`؛
- `record`: بنية بسيطة، تُوسَّع عند الطلب؛
- `opaque`: كائن مجهول.

### 6.5 الأنواع الدلالية

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

الخصائص الدنيا:

- `text`: `encoding`، `role`؛
- `image`: `mime_type`، `width`، `height`، `codec`؛
- `table`: `rows`، `columns`، `header`؛
- `machine_code`: `architecture`، `entry_point`؛
- `formula`: `language`، `expression`؛
- `metadata`: `key`، `value`؛
- `binary`: `mime_type`، `codec`.

والأنواع الخاصة بالصيغة تستخدم فضاء أسماء:

```text
pdf.page
xlsx.cell
pe.section
dxf.entity
```

### 6.6 الحواف (Edges)

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

يشكّل `contains` شجرة. أما الحواف الأخرى فقد تشكّل رسمًا بيانيًا،
حتى مع حلقات.

### 6.7 المصفوفات الكسولة

المصفوفة لا تجسّد جميع العناصر:

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

ويوسّعها النموذج:

```text
document.structure(handle, "n-rows", cursor=0, limit=100)
```

وتنفّذ الإضافة `expand` وتعيد الصفحة المطلوبة فقط.

### 6.8 الـ Pack

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

وللأبناء `space: "pack:n-pack-1"`.

## 7. MVP الخاص بـ CSV

### 7.1 الاكتشاف

- امتداد `.csv` أو `.tsv`؛
- محتوى نصي؛
- محدّد متسق؛
- حد أدنى للثقة.

وإذا كان الملف `.csv` لكنه غير نصي أو بلا بنية جدولية
متسقة، فالنتيجة `opaque` مع تحذير.

### 7.2 الرسم البياني

```text
document
  section "csv"
    array "rows" (lazy)
      record "row 2"
        text "الحقل 1"
        text "الحقل 2"
    semantic table "جدول"
      semantic column "العمود A"
      semantic column "العمود B"
```

جذر `document` له locator `{file, 0, size}`.

وللمصفوفة `rows` الحقلان `count` و`element_type: record`
و`materialized: false`.

ويُوسَّع كل `record` عند الطلب. وكل خلية عقدة `text` لها
`encoding` و`role: cell` وlocator دقيق.

ويحتوي الجدول الدلالي:

- المحدّد؛
- الترميز؛
- وجود الترويسة؛
- عدد الأعمدة؛
- أسماء الأعمدة؛
- التحذيرات.

### 7.3 قراءة CSV

```text
document.read(handle, "n-cell-2-1")
```

يعيد قيمة الخلية المفكوكة، لا الملف كله.

ولحقل بين علامات اقتباس يحتوي سطرًا جديدًا، يغطي الـ locator البايتات الخام؛ ويحدث
فك الترميز وإزالة الهروب في الإضافة.

### 7.4 حدود CSV

```text
max_file_bytes
max_rows
max_columns
max_field_bytes
max_nodes
max_read_bytes
```

تبني الإضافة فهرسًا لإزاحات بداية الأسطر لتمكين
التوسيع الكسول دون تجسيد جميع الأسطر.

## 8. المضيف الأصلي

### 8.1 النموذج

```text
Hagar
  └── NativeHost (عملية Hagar)
        └── DLL واحدة للصيغة
```

مضيف واحد لكل إضافة أصلية. ويُشغَّل المضيف عند أول استخدام، ويجري
مصافحة، ويحمّل الـ DLL ويبقى نشطًا ما دامت الإضافة قيد الاستخدام.

### 8.2 النقل

- JSON Lines بترميز UTF-8 على stdin/stdout؛
- طلب أو رد واحد لكل سطر؛
- stdout محجوز للبروتوكول؛
- السجلات على stderr؛
- أمر واحد قيد التنفيذ لكل مضيف؛
- مهلة من جهة Hagar؛
- kill وإعادة تشغيل المضيف بعد انهيار.

### 8.3 المصافحة

Hagar:

```json
{"id": "1", "op": "hello", "protocol": 1}
```

المضيف:

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

وإذا لم يتطابق `protocol` أو `abi`، يُرفض المضيف.

### 8.4 الأوامر

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

`path` نسخة مؤقتة للقراءة فقط، لا المسار الأصلي.

الرد:

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

الرد:

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

الرد:

```json
{
  "id": "4",
  "ok": true,
  "data": "...",
  "encoding": "utf-8",
  "truncated": false
}
```

وللبيانات الثنائية يكون `data` بـ base64 و`encoding` هو `base64`.

#### close / shutdown

```json
{"id": "5", "op": "close"}
{"id": "6", "op": "shutdown"}
```

`close` يدمّر حالة المستند؛ و`shutdown` يُنهي المضيف.

### 8.5 الأخطاء

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

الرموز الدنيا:

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

ويجب ألا يُنهي خطأ التحليل المضيف: بل يصبح المستند
`opaque` مع تحذير، إن أمكن.

### 8.6 ABI بلغة C

تعرض الـ DLL ABI بلغة C ذات إصدار، لا واجهة Python. والدوال المفاهيمية:

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

قواعد الـ ABI:

- أنواع C فقط ومخازن بطول محدد؛
- لا أنواع Python ولا C++ STL ولا استثناءات عبر الحدود؛
- ملكية المخازن صريحة؛
- `hagar_document_free` لتحرير الرد؛
- الـ DLL لا تكتب على stdout؛
- إصدار ABI إلزامي؛
- المنصة/المعمارية معلنة في الـ manifest.

### 8.7 Manifest الإضافة الأصلية

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

ويُسجَّل الـ manifest الأصلي في السجل نفسه الخاص بإضافات
الصيغ؛ ويشغّل محوّل الـ runtime المضيف.

## 9. الأمان

- تحل الأداة المسار عبر صندوق رمل Hagar؛
- لا يتلقى النموذج مسار مضيف أبدًا؛
- يُفتح الملف للقراءة فقط؛
- لا يُنفَّذ المستند؛
- لا تُنفَّذ الماكروات ولا JavaScript ولا المرفقات؛
- للحاويات حدود على العمق وعلى البايتات المفكوكة؛
- للمضيف الأصلي مهلة ويُنهى إذا لم يستجب؛
- المضيف الأصلي ليس حدًّا أمنيًا ضد الـ DLL الخبيثة؛
- وللـ DLL غير الموثوقة يلزم صندوق رمل على مستوى نظام التشغيل أو الرفض؛
- الرسم البياني في الذاكرة ولا يُكتب في الـ Vault؛
- يسجّل التدقيق الصيغة والإضافة والبصمة والحجم والتحذيرات، لا
  المحتوى.

## 10. بدائل مستبعدة

### DLL داخل العملية

مستبعد: انهيار أصلي يقتل Hagar؛ والـ ABI هش؛ وصندوق الرمل
التطبيقي لا يحمي الذاكرة.

### محوّلات خارجية

مستبعد: LibreOffice/poppler/7zip لها تبعيات وأسطح هجوم
كبيرة جدًا، ولا يمكن حصرها ببساطة.

### رسم بياني دائم

مستبعد: المستند هو مصدر الحقيقة؛ والرسم البياني مشتق و
كبير. والاستمرارية تُدخل الإبطال والخصوصية والتخزين.

### أداة لكل صيغة

مستبعد: سيتعيّن على النموذج معرفة الصيغ. والأداة الواحدة
`document` تبقي الواجهة مستقرة.

### إزاحة بلا length

مستبعد: لا تتيح قراءة نطاق، ولا إدارة pack أو
محتويات غير متجاورة.

## 11. الاختبارات

### العقد

- تحليل CSV؛
- البنية والدلالة والقراءة؛
- المصفوفات الكسولة والترقيم الصفحي؛
- handle مغلق/مُبطَل؛
- ملف معدَّل؛
- صيغة مجهولة → opaque؛
- ملف تالف → opaque مع تحذير؛
- تجاوز الحد؛
- مسار خارج صندوق الرمل مرفوض.

### الإضافات

- إضافة Python مدمجة؛
- إضافة Python خارجية؛
- إضافة أصلية بمضيف وهمي؛
- مصافحة ABI خاطئة؛
- مضيف ينهار؛
- مضيف لا يستجيب (مهلة)؛
- مخرج رسم بياني غير صالح؛
- `read` يتجاوز الحدود.

### CSV

- المحدّد `,` و`;` وtab؛
- الاقتباس والسطر الجديد داخل الحقول؛
- BOM وUTF-8؛
- ترويسة نعم/لا؛
- أسطر بأعمدة مختلفة؛
- ملف كبير جدًا بمصفوفة كسولة.

## 12. نقاط مفتوحة

1. القيم الأولية للحدود.
2. إدارة الترميزات غير UTF-8 (تراجع، أو تحذير، أو خطأ).
3. التعريف الدقيق للنوع `table` في CSV: ترويسة اختيارية،
   وأعمدة مكررة، وأنواع مستنتجة.
4. سياسة الإغلاق التلقائي للـ handles.
5. المضيف الأصلي: صندوق رمل نظامي للـ DLL غير الموثوقة.
6. تخزين مؤقت للرسوم البيانية: لا شيء في الـ MVP؛ يُقيَّم في المستقبل.
7. دعم محتمل لمستندات متعددة مفتوحة في الدور نفسه.
8. صيغ لاحقة: PDF وDOCX وXLSX وPE وDXF.
