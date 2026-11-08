# HAGAR — المعمارية

الإصدار: 0.5.2
آخر تحديث: 2026-11-03

---

# 1. ما هو Hagar

Hagar هو harness لنماذج LLM مكتوب بلغة Python، مصمَّم للتشغيل
المرن لنماذج اللغة.

الهدف ليس محادثة مع نموذج، بل بيئة تشغيل
**آمنة** يستطيع فيها الـ LLM استخدام الأدوات، والرجوع إلى ذاكرة
دائمة، والتفاعل مع أنظمة خارجية دون الوصول المباشر
إلى الموارد الحقيقية للجهاز المضيف.

ولتحقيق ذلك يطبّق المشروع مبادئ HMI/HCI وبيئة العمل الإدراكية
(Cognitive Ergonomics) على تصميم البيئة التي يعمل فيها النموذج.

## 1.1 قوانين HAGAR الأربعة

**القانون الأول — الـ LLM غير موثوق بحكم التعريف.**
ليس لأنه سيئ أو عديم الفائدة: بل لأنه احتمالي. فكل
تصريحاته يجب التحقق منها وكل أفعاله يجب تقييدها.

**القانون الثاني — الأدوات أكثر موثوقية من الـ LLM.**
إذا قال نظام الملفات إن ملفًا موجود، فهو موجود. وإذا أعادت الأداة
حجمًا، فذلك الحجم حقيقي. الـ LLM يفسّر، والأدوات
تقيس.

**القانون الثالث — يجب أن توجد الحالة خارج عقل الـ LLM.**
ToolRegistry وMCP وFileSystemSandbox و(في المنظور)
PermissionEvaluator تنقل المعرفة والتحكم إلى خارج النموذج،
كما في الأنظمة الحرجة للسلامة.

**القانون الرابع — يجب أن يكون كل فعل قابلًا للتفسير بعده.**
يجيب سجل التدقيق عن السؤال الصحيح: لا "لماذا جُنّ الـ LLM؟"
بل "أي افتراض تبنّاه؟"، و"أي أداة استخدم؟"، و"أي بيانات كانت
خاطئة؟". تحقيق في الحوادث، كما في الطيران.

## 1.2 المحظورات المطلقة

يجب ألا يفعل النموذج أبدًا:

- الوصول المباشر إلى نظام ملفات المضيف؛
- تنفيذ أوامر على shell الحقيقية؛
- الحصول على امتيازات أعلى من تلك المحددة في الإعدادات؛
- معرفة التنظيم الفعلي لنظام التشغيل.

تمر جميع العمليات حصريًا عبر أدوات مسجّلة و
مراقَبة من قِبل الـ harness.

## 1.3 المبادئ المعمارية

- الفصل بين النموذج ونظام التشغيل؛
- الأمان افتراضيًا؛
- الهندسة القائمة على الإضافات (plugin)؛
- الاستقلال عن مزوّد الـ LLM؛
- القابلية للتوسّع عبر الأدوات وبروتوكول MCP.

---

# 2. المعمارية

```text
المستخدم
  │
  ▼
الوكيل (Agent) ──────────────── AuditLog (JSON Lines)
  │
  ├── LLMClient (llm/base.py)
  │     ├── OllamaClient
  │     ├── LMStudioClient
  │     ├── DeepSeekClient
  │     ├── OpenAIClient
  │     ├── ClaudeClient
  │     └── GeminiClient
  │
  ├── ToolRegistry
  │     ├── filesystem.*
  │     ├── memory.*        (مخطط)
  │     └── mcp.*
  │
  ├── FileSystemSandbox
  │
  ├── MCPClient
  │
  └── Vault (Obsidian)
```

تدفق التنفيذ:

```text
المستخدم
  ↓
الوكيل (Agent)          turn.start
  ↓
LLMClient               llm.tool_choice
  ↓
ToolCall
  ↓
ToolRegistry            tool.call
  ↓
ToolResult              tool.result
  ↓
LLMClient
  ↓
الرد النهائي            turn.answer
```

---

# 3. المكوّنات

## 3.1 الإعدادات (`core/config.py`)

يحمل ملف YAML (`hagar.yaml`) ويتحقق من صحته إلى `AppConfig`.

الأقسام:

| section | إلزامي | المحتوى |
|---|---|---|
| `model` | نعم | provider وname وhost وtimeout وmax_tokens وapi_key_env وnative_tools |
| `vault` | نعم | مسار vault الخاص بـ Obsidian |
| `filesystem` | نعم | `sandbox`: قائمة `{alias, path, permissions}`؛ `limits`: ميزانية الكتابة |
| `permissions` | لا | read وwrite وshell وnetwork (الافتراضي `true/false/false/false`) |
| `rag` | لا | `top_k` (الافتراضي 8) |
| `mcp_servers` | لا | endpoint وnamespace وauth (bearer/header/oauth) |
| `audit` | لا | enabled وpath وmax_field_chars وmax_bytes وmax_files وinclude_outputs |
| `policy` | لا | مسار ملف policy وsubject |
| `memory` | لا | enabled وvault_subdir وcontext_turns وcontext_skills وmax_skill_chars |

تُنتج أخطاء التحقق دائمًا `ConfigError`، برسالة
تشير إلى الحقل. ويُحل مسار التدقيق، إن كان نسبيًا،
بالنسبة إلى ملف الإعدادات.

## 3.2 واجهة الـ LLM والواجهات الخلفية (`llm/`)

لدى `LLMClient` مساران:

- **الاستدعاء الأصلي** (الافتراضي): يرسل `native_step()` مخططات
  الأدوات بصيغة المزوّد ويقرأ الاستدعاءات من الرد؛
- **بروتوكول JSON النصي** (تراجع): يطلب `request_tool_call()`
  JSON يحتوي `tool`/`arguments`، مع تحليل قوي ومحاولة
  إصلاح واحدة.

يُبنى مخطط المعاملات من `ToolDefinition`:
OpenAI/Ollama يستخدمان `tools[].function`، وClaude يستخدم `tools[].input_schema`،
وGemini يستخدم `functionDeclarations`. ويستخدم الحوار القانوني الأدوار
`user`/`assistant`/`tool`؛ ويترجمه كل عميل (OpenAI `tool_calls`،
وClaude كتل `tool_use`/`tool_result`، وGemini `functionCall`/
`functionResponse`). ويولّد رفض HTTP 400/404/422
`NativeToolsUnavailable`: فينتقل الوكيل إلى البروتوكول النصي فقط إذا لم
يكن قد نفّذ أداة بعد.

تُطبَّع أسماء الأدوات من أجل الـ APIs التي لا تقبل
النقطة (`filesystem.read_file` → `filesystem__read_file`) وتُعاد إلى
الاسم الداخلي في الرد: فالسياسة والتدقيق والاختبارات ترى دائمًا الاسم
الأصلي.

يبقى النص مسار التراجع للنماذج التي لا تدعم الأدوات الأصلية؛
ويفرضه `model.native_tools: false` (أو `--no-native-tools` من الـ CLI).

| provider | API | المفتاح | ملاحظات |
|---|---|---|---|
| `ollama` | `/api/chat`، `/api/generate` | — | المضيف الافتراضي `localhost:11434` |
| `lmstudio` | `/v1/chat/completions` (OpenAI) | اختياري `LMSTUDIO_API_KEY` | المضيف الافتراضي `localhost:1234/v1` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system مضمّن |
| `openai` / `chatgpt` | `/v1/chat/completions` | `OPENAI_API_KEY` | ChatGPT عبر API، ليس بالاشتراك |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system منفصل، وأدوار متبادلة |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`، والدور `model` |

يُقرأ المفتاح من البيئة فقط؛ و`model.api_key_env` يتجاوز
الاسم الافتراضي. و`model.host` هو عنوان URL الأساسي لجميع المزوّدين (بقيمة
افتراضية لكل مزوّد)، و`model.timeout` هو مهلة HTTP (الافتراضي 120)،
و`model.max_tokens` يستخدمه Claude فقط.
ويبني `llm/factory.py` العميل ويرفض المزوّدين المجهولين أو
المفاتيح الغائبة. والمزوّدون المدمجون عبارة عن spec في `llm/plugins.py`؛
ويسجّل المزوّد الخارجي نفسه عبر entry point بالاسم `hagar.llm` ومصنع
`(config, audit) -> LLMClient` (راجع `PLUGINS.md`). ولا يتطلب LM Studio
مفتاحًا إلا بإعداد الخادم؛ أما OpenAI فيتطلب
مفتاح API، لا اشتراك ChatGPT.
DeepSeek: النماذج الحالية هي `deepseek-flash` و
`deepseek-v4-pro`؛ ولم يعد `deepseek-chat` مقبولًا.

الحالة الحالية: **الاستدعاء الأصلي v1** مع تراجع نصي تلقائي
(راجع ROADMAP).

## 3.3 نموذج الأدوات (`core/tool_*.py`)

يصف `ToolDefinition` الاسم والوصف والفئة والمعاملات
والمعالج، و`origin` (`local` أو `mcp.<namespace>`)، و`capabilities`
المعلنة، وحالة التمكين و`requires_confirmation`
(الحد الأدنى من ASK الذي يطبّقه السجل).

`ToolCall` هو طلب النموذج (`tool` و`arguments` و`id`)؛
و`ToolResult` هو النتيجة المهيكلة (`tool_name` و`success` و`output`
و`error`).

يسجّل `ToolRegistry` الأدوات ويبحث عنها ويمكّنها/يعطّلها وينفّذها؛
ويعرض البيانات الوصفية للنموذج وهو نقطة التنفيذ الوحيدة.

## 3.4 الوكيل (`core/agent.py`)

دورة وكيلية متعددة الخطوات، بمسارين:

- **أصلي**: قد يحتوي الرد على استدعاءات متعددة؛ فيعيد الوكيل إدراج
  رسالة `assistant` ورسالة `tool` مع المعرّف لكل
  نتيجة؛
- **نصي**: استدعاء واحد في كل مرة، وتُرسل النتيجة كدور
  `user`.

في الحالتين:

1. يقرر النموذج ما إذا كانت هناك حاجة إلى أداة؛
2. إذا لم تكن هناك حاجة، يغلق الرد النهائي الدور؛
3. إذا كانت هناك حاجة، تُنفَّذ الأداة وتعود النتيجة إلى النموذج؛
4. الحد `max_tool_calls` يسري على الدور بأكمله. وإذا أصرّ النموذج،
   يُغلق الدور بـ `Agent stopped after N tool calls`
   (حماية من الحلقات).

إذا فشلت الخطوة الأصلية الأولى بـ `NativeToolsUnavailable`، ينتقل الوكيل
إلى البروتوكول النصي (`llm.native_fallback`)؛ وخطأ بعد تنفيذ
أداة يغلق الدور بـ `turn.error`، دون
تراجع.

تُسجَّل كل خطوة في التدقيق: السؤال، واختيار الأداة، والمعاملات،
والنتيجة، والمدة، والرد النهائي. وسجل تدقيق معطوب لا يوقف الوكيل: بل
يُبلَّغ عن العطل على stderr.

يتلقى `Agent` الـ `Vault` لكنه لا يستخدمه بعد.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

نظام الملفات الافتراضي للوكيل. يُعالَج كل طلب كما يلي:

1. يُحل مقابل المجلد الحالي (`resolve_path`)؛
2. يُتحقق منه مقابل الجذور الممنوحة (`effective_permissions`)؛
3. يُرشَّح بالأذونات الفعلية، مع الجذور الأكثر خصوصية التي
   تتجاوز الجذور الخارجية؛
4. يُفحص مقابل الروابط الرمزية والمساحة المتاحة على القرص
   (`FS_Guardian`، وهو اسم قديم).

يمثّل `DirectoryPermissions` الأذونات `read` و`write` و`create` و`rename`
و`delete` و`execute`؛ و`None` يعني "يرث من الجذر الخارجي".
والمسار خارج الجذور دائمًا `PermissionError`.

يعيد `FileInfo` / `stat()` النوع والحجم بالبايت وتواريخ
الإنشاء/التعديل/الوصول (ISO 8601 مع إزاحة محلية) و**الأذونات الفعلية
لصندوق الرمل**، لا ACL نظام التشغيل.

**الروابط الرمزية غير موجودة بالنسبة لصندوق الرمل.** فلا يعرضها Hagar ولا
يقرأها ولا يتبعها ولا يحذفها: `stat` و`list_dir` و`search`
تتجاهلها؛ و`read_file` و`read_chunk` و`delete_file` ترد
بـ “not found”؛ و`chdir` على رابط رمزي يرد بـ “Directory not found”. والرابط
المعطوب أو المتجه إلى الخارج لا يمكن تمييزه عن مسار غير موجود.

الجذر الافتراضي لصندوق الرمل هو `/home/ai`؛ وكل مجلد مُعدّ
يُعرَض كـ `/home/ai/<alias>`. و`stat` و`list_dir` و`search`
و`read_chunk` ورسائل `write`/`create`/`mkdir`/`delete` و`chdir`
تعرض مسارات افتراضية فقط: فالمسار الفيزيائي لا يظهر أبدًا
في مخرجات النموذج. ويُحل الإدخال `/home/ai/<alias>/...`
مقابل المجلد الفيزيائي للاسم المستعار؛ أما المسارات النسبية فتبقى
نسبية إلى المجلد الحالي.

`/home/ai` مجلد اصطناعي: يمكن سرده وطلب stat له، لكنه
ليس mount ولا يمكن تنفيذ `chdir` إليه. وتبقى إدخالات
`filesystem.sandbox` مسارات للنظام المضيف، مطلقة أو بـ
`~` إن اختار المستخدم ذلك: فقد تكون أي مجلد موجود و
قابل للوصول. ولا ينشئ Hagar مجلدات ولا يفترض وجود مجلد منزل
مخصص.

```yaml
filesystem:
  sandbox:
    - alias: documenti
      path: C:\Users\pippo\Documenti
      permissions: RWX
    - alias: ebooks
      path: D:\ebooks
      permissions: R
```

لا يوجد علم `enabled`: بل يُركَّب كل إدخال صالح في `filesystem.sandbox`.
والأسماء المستعارة أو الأذونات غير الصالحة، أو المسار المفقود أو المكرر،
توقف الإعدادات. ويمكن أن تحتوي المسارات الفيزيائية والأسماء الداخلية
على مسافات؛ أما الاسم المستعار فلا، لأنه يجب أن يبقى مقطعًا افتراضيًا
واحدًا.

يغطي `R` القراءة والسرد والبحث و`stat`؛ ويغطي `W` الكتابة
والإنشاء وإعادة التسمية والنسخ والحذف؛ ويغطي `X` `chdir`. وتبقى
الأذونات العامة `permissions.read`/`write` سقفًا: فلا يستطيع اسم مستعار
`RWX` تجاوزها.

## 3.6 أدوات نظام الملفات (`core/filesystem_tools.py`)

```text
filesystem.read_file
filesystem.write_file
filesystem.create_file
filesystem.delete_file
filesystem.mkdir
filesystem.chdir
filesystem.list_dir
filesystem.read_chunk
filesystem.rename
filesystem.copy_file
filesystem.search
filesystem.free_space
filesystem.stat
```

يعيد `list_dir` بيانات `FileInfo` الوصفية؛ ويقرأ `read_chunk` بالبايت
مع `has_more` و`next_offset` وحدود UTF-8 كاملة؛ ويستخدم `search`
نمط glob تكراريًا بحد للنتائج؛ ويتطلب `copy_file` `create`؛
ويتطلب `rename` `rename` على المصدر و`create` على الوجهة.
والمسارات المعادة افتراضية دائمًا (`/home/ai/<alias>/...`).
ويتطلب `chdir` `X` على الاسم المستعار.

يعيد `list_dir` 100 إدخال كحد أقصى في الصفحة (`limit` بحد أقصى
500) مع `offset` و`next_offset` و`has_more`؛ وإذا وُجدت إدخالات أخرى فإن
`message` يقول `voci: riportate X di Y; per continuare usa offset=Z`.
ويستخدم `search` الترقيم الصفحي نفسه: `max_results` هو حد الصفحة
(الافتراضي 100، والحد الأقصى 500)، و`offset` يتنقل بين النتائج. وللأشجار
الكبيرة يُفضَّل تضييق `pattern`/`path` بدلًا من تكرار صفحات
كثيرة. ويقبل `read_file` فقط ملفات حتى `CHUNK_SIZE` (4096 بايت)؛
وما فوق ذلك يوجّهه الخطأ إلى `read_chunk()` لأن قراءة الملف بأكمله
ستتجاوز نافذة السياق. ويعيد `read_chunk` `next_offset` و
حدود UTF-8 كاملة.

لا يعرض `list_dir` و`search` الروابط الرمزية؛ ويعاملهما `read_file` و`read_chunk`
كملفات غير موجودة.

يستبدل `write_file` الملفات الموجودة فقط؛ أما الإنشاء فيمر عبر
`create_file`، الذي يتطلب إذن `create`. ولا يمكن
الالتفاف على حظر الإنشاء بكتابة مسار جديد.

### حدود الكتابة

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = معطَّل
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` هو الحد الأقصى لكل عملية من
  `write_file` أو `create_file` أو `copy_file`؛
- `min_free_bytes` هو احتياطي المساحة الذي يجب أن يبقى بعد
  العملية؛
- `session_write_bytes` هو الميزانية التراكمية للجلسة؛
- `ask_over_bytes` يرفع العمليات فوق العتبة إلى `ASK`. والفحص المسبق
  مدمج في `ToolRegistry`: فحتى إذا قالت السياسة `ASK`، يكون
  التأكيد واحدًا فقط.

يعطّل `0` الحد الفردي. وتجاوز `max_write_bytes`
أو `session_write_bytes` أو الاحتياطي ينتج خطأ، لا تأكيدًا:
فهي ثوابت، لا أسئلة. و`ask_over_bytes` هو المستوى الوحيد الذي
يسأل المستخدم.

يعيد `filesystem.stat` JSON يحتوي `path` و`exists` و`kind`
(`file`/`directory`/`other`) و`size_bytes` و`created_at` و`modified_at`
و`accessed_at` و`permissions`. والمسار غير الموجود ليس خطأ:
بل `exists: false` مع الأذونات المطبقة.

## 3.7 MCP (`llm/mcp_client.py`)

عميل MCP عبر HTTP/JSON-RPC: `initialize` و`tools/list` و`tools/call`،
مع تحويل تلقائي للأدوات إلى `ToolDefinition` وتسجيلها بفضاء الأسماء
`mcp.<namespace>`.

يدعم أيضًا ردود `text/event-stream` (streamable HTTP) ويرسل
إشعار `notifications/initialized` بعد المصافحة. ويستخدم
`MCP-Protocol-Version` (الافتراضي `2025-06-18`، مع تراجع) ويعيد استخدام
`Mcp-Session-Id` عندما يعيده الخادم. وتتضمن أخطاء HTTP
جسم الرد لجعل أخطاء 400 قابلة للتشخيص.
وتُطبَّع نتائج الأدوات إلى نص: كتل `text`،
أو `structuredContent` أو JSON؛ والنتيجة التي تحمل `isError`
تصبح خطأ في الأداة.

المصادقة لكل خادم:

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer          # أو "header"
      token_env: MCP_EXAMPLE_TOKEN
      # header: X-API-Key  # فقط مع type: header
```

يُقرأ الرمز من البيئة فقط ولا يظهر في التدقيق. وإذا غاب،
يُتخطى الخادم بـ `mcp.failed` ويستمر الـ harness؛ وتبقى الخوادم الأخرى
متاحة.

### OAuth التفاعلي

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # بدونه، تسجيل ديناميكي
    # client_secret_env: MCP_CLIENT_SECRET
    scopes: [mcp.read]
    audience: api.atlassian.com  # اختياري، لمزوّدي 3LO
    redirect_port: 8765       # 0 = منفذ عشوائي
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

تدفق authorization code + PKCE، مع استدعاء عودة على
`http://localhost:<port>/oauth/callback` وفتح المتصفح. وإذا كان
النطاق يحتوي `offline_access`، يُضاف `prompt=consent`.
وتُكتشَف البيانات الوصفية من `.well-known` (RFC 9728 للمورد،
وRFC 8414 لخادم التفويض)؛ وإذا غاب `client_id` يُستخدم
التسجيل الديناميكي. والرموز في ملف محلي بأذونات
مقيَّدة (`0600` حيث يدعم النظام ذلك)، مع تجديد
تلقائي وإعادة محاولة واحدة عند `401`.

ويؤدي Ctrl-C أثناء انتظار استدعاء العودة إلى إغلاق الخادم المحلي والخروج
بالرمز 130، دون traceback.

الحدود: لا device flow ولا DPoP ولا mTLS ولا client assertion؛ ويجب أن
يستطيع المتصفح الوصول إلى استدعاء العودة المحلي. وإذا لم يصل استدعاء العودة،
تطلب الطرفية لصق عنوان URL لإعادة التوجيه.

## 3.8 الـ Vault (`memory/vault.py`)

وصول إلى vault الخاص بـ Obsidian بمسارات نسبية إلى الجذر و
حماية من الخروج من الـ vault. ويتيح القراءة والكتابة والإلحاق
وسرد الملفات و`load_all` للقراءة التكرارية. أما دلالات
الذاكرة فتعيش في `memory/store.py` (§3.11).

## 3.9 سجل التدقيق (`core/audit.py`)

ملف JSON Lines للإلحاق فقط. كل سطر يحمل طابعًا زمنيًا UTC و`session` و
`event`؛ وتشترك أحداث الطلب نفسه في معرّف `turn`.

```text
harness.start      المزوّد، والنموذج، والجذور، والأذونات، والأدوات، والvault
turn.start         السؤال، وحد الأدوات، والوضع الأصلي
llm.tool_choice    اختيار النموذج، والمعاملات، mode=native
llm.native_fallback مزوّد بلا أدوات أصلية، والانتقال إلى النص
llm.protocol_error رد غير مطابق (النص الكامل، مقتطعًا)
llm.repaired       إصلاح ناجح
llm.repair_failed  إصلاح فاشل
tool.call          الأداة، والمعاملات، والفهرس
tool.result        النتيجة، والمخرج/الخطأ، والمدة بالمللي ثانية
turn.answer        الرد النهائي، وعدد الأدوات المستخدمة
turn.error         المرحلة والرسالة
turn.stop          بلوغ الحد
mcp.loaded         فضاء الأسماء والأدوات المستوردة
mcp.failed         فضاء الأسماء والخطأ
llm.failed         مزوّد غير قابل للبناء (مثل مفتاح غائب)
harness.stop       خروج سليم (وإن غاب، فقد قُتلت العملية)
memory.enabled     الجذر، والمجلد الفرعي، وأدوار السياق
memory.disabled    سبب التعطيل
memory.context     الأدوار والمهارات المحقونة في الـ prompt
memory.turn        الدور المحفوظ في الvault
memory.failed      المرحلة والخطأ
```

الخصائص:

- الكتابة بأفضل جهد: خطأ الإدخال/الإخراج لا يوقف الـ harness ويُبلَّغ عنه
  مرة واحدة فقط على stderr؛
- اقتطاع قابل للإعداد (`audit.max_field_chars`، الافتراضي 2000)؛
- سلسلة بصمات (`prev`/`hash`) قابلة للتحقق بـ `verify_chain`؛
- تدوير إلى `<file>.<timestamp>` عند تجاوز `audit.max_bytes` (و0 يعطّل)؛
- الاحتفاظ: `audit.max_files` (الافتراضي 100) يحتفظ بحد أقصى N ملفًا،
  بما فيها الملف النشط؛ وتُحذف النسخ الأقدم؛
- مع `audit.include_outputs: false` تُسجَّل مخرجات الأدوات
  بالحجم فقط؛
- القيم غير الـ JSON تُجعل قابلة للتسلسل؛
- لا مفاتيح API في السجل؛
- يحتوي السجل أيضًا على مخرجات الأدوات (أي محتويات ملفات):
  ويجب حمايته كمساحة العمل.

## 3.10 الأذونات (`core/permissions.py`)

النموذج مصفوفة ذات × كائن:

- **Capability** (`IntFlag`): ما يمكن للعملية فعله
  (`FILESYSTEM_READ`، `FILESYSTEM_WRITE`، `FILESYSTEM_CREATE`،
  `FILESYSTEM_DELETE`، `FILESYSTEM_EXEC`، `MEMORY_READ`،
  `MEMORY_WRITE`، `NETWORK`، `MCP_CALL`، `COMPUTE`). وتُدمَج بـ `|`؛
  والتحقق دائمًا من كونها مجموعة جزئية.
- **Effect** (`IntEnum`): `ALLOW` و`ASK` و`DENY`. وعند التعارض
  تفوز القيمة الأعلى (`DENY > ASK > ALLOW`).
- **Rule**: قدرة + تأثير + مرشحات اختيارية `tools` (glob)
  و`paths` و`namespaces` (بادئات) + `reason`.
- **Subject**: من يطلب (الوكيل، المستخدم، النظام)، مع قواعد و
  افتراضي (`DENY` إن لم يُحدد).
- **Resource**: موضوع القرار (حاليًا أداة بقدراتها؛
  وفي المستقبل أيضًا الملاحظات والمسارات).
- **Decision**: التأثير والسبب والقاعدة المطبقة.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. يجب أن يوفر المورد القدرات المطلوبة؛
2. يجب أن يمنحها **سقف النظام** (المشتق من `permissions.read/write/shell`)؛
3. لكل قدرة تُطبَّق قواعد الذات: فيفوز الأكثر
   خصوصية (عدد المرشحات، ثم طول البادئة)، وعند التعادل
   التأثير الأكثر تقييدًا؛ ودون قواعد يسري الافتراضي؛
4. مع تعدد القدرات المطلوبة يسري منطق AND: فيفوز التأثير الأسوأ.

`ASK` ليس قرارًا: بل سؤال موجَّه إلى إنسان. ويطرحه
`ConfirmationProvider` — فيطلب `ConsoleConfirmation`
`lo faccio? (y/N)` بالافتراضي N — ودون قناة تأكيد يسري
`DENY`. ويمكن لواجهة رسومية تطبيق البروتوكول نفسه بحوار
نمطي.

في الـ CLI يكون `core/input_broker.py` المالك الوحيد للطرفية:
فيتولى توزيع الطلبات والتأكيدات والمفتاحين `F5`/`F8`، ويضع عنوان
الطرفية كإشارة انتباه ويعيد الوضع الطبيعي في
النهاية. وعلى stdin غير التفاعلي يرتد إلى `input()`.

```yaml
version: 1
subjects:
  assistant:
    default: deny
    rules:
      - capabilities: [FILESYSTEM_READ]
        effect: allow
        tools: ["filesystem.*"]
      - capabilities: [FILESYSTEM_WRITE, FILESYSTEM_CREATE]
        effect: ask
        paths: ["note"]
      - capabilities: [COMPUTE]
        effect: allow
        tools:
          - "calculator.*"
          - "statistics.*"
          - "units.*"
          - "clock.*"
          - "calendar.*"
          - "think.*"
          - "text.*"
          - "url.*"
      - capabilities: [NETWORK]
        effect: ask
        tools: ["feed.*"]
```

يُقرأ `policy.yaml` **قبل** بناء الـ LLM. وإذا لم يكن
قابلًا للقراءة أو غير صالح، يطبّق الـ harness `DENY` على جميع السياسات،
ويسجّله في التدقيق (`policy.failed`) ويبلّغ عنه في المحادثة؛ ويستمر
بقية الـ harness في العمل. وحتى الذات الغائبة تتدهور إلى
`DENY`.

ويحدث التحقق في `ToolRegistry.execute`، نقطة التنفيذ الوحيدة، وينتج
الحدثين `permission.decision` و`permission.confirmation`.

ويقارن نطاق `paths` المسار **الذي يكتبه النموذج**
(بعد التطبيع)، لا المسار الذي يحله صندوق الرمل: فقد لا يطابق المسار المطلق
أو `chdir` بادئة نسبية، وتبقى
النتيجة `DENY` (fail closed).

## 3.11 الذاكرة (`memory/store.py`، `memory/tools.py`)

**الواجهة الخلفية الافتراضية: SQLite.** يستخدم `memory/sqlite_store.py`
و`memory/database.py` قاعدة بيانات محلية (`%LOCALAPPDATA%/Hagar/memory.db`
أو `HAGAR_MEMORY_DB`) كمصدر حقيقة للجلسات والأدوار والمهارات و
الملخصات. ويستخدم SQLite وضع WAL والمعاملات و`busy_timeout`؛ والنسخ الاحتياطي هو
`VACUUM INTO`. أما الواجهة الخلفية `markdown` الموصوفة أدناه فتبقى متاحة
للتوافق فقط ولم تعد الافتراضية.

**الذاكرة العرضية.** يدرج الـ harness كل دور منتهٍ في ملاحظة لكل
جلسة:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter يحتوي `session` و`type: chat` و`created`؛ والجسم يحتوي قسمًا
لكل دور (`## <timestamp> · <turn>`)، والسؤال والرد. ولا
تُحفظ مخرجات الأدوات: فتبقى في التدقيق.

وفي بداية كل دور يحقن الوكيل في الـ prompt آخر
`memory.context_turns` دورًا (و0 يعطّل الحقن)، مع اقتطاع
السؤال والرد. ومع `memory.context_skills > 0` يضيف حتى N
**مهارة مؤكدة** ذات صلة بالسؤال، عبر مطابقة معجمية على
العنوان والوسوم والمحتوى؛ ولا تدخل المرشحة والمؤرشفة أبدًا.
ويُوسم هذا المقطع كبيانات، لا كتعليمات. وخطأ الذاكرة
لا يوقف الدور: بل يُسجَّل `memory.failed`.

**الدلالة.** يمكن للنموذج اقتراح ذكرى بثلاث أدوات:

| الأداة | القدرة | فضاء الأسماء |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

يكتب `create_skill` الملف `<vault>/Hagar/skills/<slug>.md` مع frontmatter
يحتوي `id` و`title` و`kind` (`fact`/`procedure`) و`status: candidate` و`tags`
و`source_session` و`source_turn` و`model` و`created_at`. والـ slug
آمن (ASCII فقط، بلا مسار)؛ والعنوان الموجود مسبقًا لا يُستبدل
ويعيد `duplicate: true`.

ويعيد `get_context` الأدوار الأخيرة أو يبحث بكلمة مفتاحية
في الجلسات السابقة؛ ويرشّح `list_skills` حسب `kind` و`status`.

**دورة الحياة.** الحالات هي `candidate` و`confirmed` و`archived`.
ولا ينشئ الـ LLM إلا مرشحين؛ أما الانتقال فيقوم به الإنسان، من الـ CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

يعرض `/memory review` مرشحًا واحدًا في كل مرة مع المصدر و
المحتوى، ثم يسأل `y/N/a/s/q` (تأكيد، إبقاء، أرشفة، تخطٍّ،
خروج). ويكتب التأكيد `reviewed_at`؛ و`archive` قابل للعكس بـ
`confirm`. وكل انتقال ينتج `memory.status` أو `memory.review`
في التدقيق. وتبقى الملاحظات ملفات Obsidian: فتعديل `status` في
الـ frontmatter له الأثر نفسه.

**الإعدادات**:

```yaml
memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  context_project_memories: 10
  max_context_chars: 6000
  project_max_active: 200
  summary_max_chars: 4000
  max_skill_chars: 4000
```

### ذاكرة المشروع

ذاكرة المشروع منفصلة عن المهارات:

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

لكل مشروع `index.md` يحتوي الحالة وآخر نشاط والملخص و
عدد القرارات النشطة. ولكل قرار حالة
`candidate`/`active`/`superseded`/`archived`، وبدائل، وتبرير،
ومصدر، و`auto_saved`. ولا تُعاد كتابة القرارات: فالقرار الجديد
قد يحل محل قرار قديم.

مع `memory.backend: sqlite` تستخدم المشاريع والقرارات الجدولين
`projects` و`decisions` في قاعدة البيانات نفسها؛ أما الواجهة الخلفية Markdown
القديمة فتواصل استخدام الـ Vault.

عند الإقلاع يعرض Hagar المشاريع النشطة و"النشاط الحر":

```text
/project list
/project new <nome>
/project select <nome>
/project free
/project status
/project archive <nome>
/project unarchive <nome>
```

التجاوزات غير التفاعلية هي `--project <nome>` و`--free`.

في نهاية الجلسة:

1. يُنقل النص إلى `archive/chat/`؛
2. يُولَّد ملخص بالنموذج، مع تراجع ميكانيكي؛
3. يُحفظ الملخص مع رابط وبصمة للنص؛
4. إذا وُجد مشروع، يقترح الـ LLM قرارات `candidate`؛
5. يمكن للمستخدم مراجعتها؛ وإذا رفض تبقى `candidate` مع
   `auto_saved: true`.

يستخدم السياق المحقون **فهرس** المشروع: الملخص وعناوين
القرارات النشطة وعددها، لا جميع الأجسام. وتُقرأ التفاصيل
بـ `memory.project_context(query=..., limit=...)`. والكتلة
الإجمالية محدودة بـ `max_context_chars`؛ وإذا اقتُطعت،
يسجّل التدقيق `memory.context_trimmed`. وليست تقديرًا للرموز: بل
ميزانية بالحروف، حتمية.

وعندما يتجاوز مشروع `project_max_active`، يسأل Hagar هل
يؤرشفه. والأرشفة قابلة للعكس ولا تحذف شيئًا.

**استشارة الأرشيف.** النصوص المؤرشفة تحمل `project`
في الـ frontmatter. والبحث والقراءة عند الطلب:

```text
/memory archive search <testo>
/memory archive read <session> [offset] [limit]
```

وتُعرَض الأدوات نفسها كـ `memory.archive_search` و
`memory.archive_read`؛ فالبحث يعيد session وturn وtimestamp
والمشروع ومقتطفًا، والقراءة ترقّم الأدوار صفحيًا. ولا يوجد حقن
تلقائي للأرشيف في الـ prompt: فيبقى الملخص هو الفهرس، و
النص هو المصدر الذي يُرجَع إليه عند الحاجة.

إذا لم يكن `vault.path` موجودًا أو غير قابل للكتابة، تُعطَّل الذاكرة
مع تحذير في المحادثة و`memory.disabled` في التدقيق؛ وتواصل
المكوّنات الأخرى العمل. وتخضع كتابات الذاكرة
للسياسات (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.11.1 طبقة الخدمة (`core/service.py`)

`HarnessService` هو الـ API المستقر فوق `Harness`: لا يقرأ من
`input()` ولا يكتب على stdout ولا يعرف الـ CLI. ويعرض:

- `ask(question)` مع الأحداث `turn.start` و`turn.answer` و`turn.error`؛
- أحداث الأدوات والأذونات التي تمرّرها `Agent` و`ToolRegistry`:
  `tool.call` و`tool.result` و`permission.decision`
  و`permission.confirmation`؛
- `status()` مع النموذج والمشروع والذاكرة والتدقيق والسياسة والأدوات؛
- `list_projects()` و`current_project()` و`set_project()`
  و`clear_project()` و`create_project()`؛
- `finish_session()`.

الأحداث هي `ServiceEvent(type, data, ts)` ويمكن استهلاكها
من sink (الـ CLI أو الواجهة الرسومية أو الاختبارات). ويستخدم الـ CLI الحالي الخدمة للأدوار و
اختيار المشروع وإغلاق الجلسة.

## 3.11.2 خدمة الأوامر (`core/command_service.py`)

يحوّل `CommandService` أوامر الشرطة المائلة إلى `CommandResult`:

```text
command, ok, lines, data, error, requires_input
```

ويتولى `/help` و`/tools` و`/status` و`/mcp` و`/audit` و`/project` و
`/memory` دون الكتابة على stdout. ويطبع الـ CLI الحقل `lines`؛ وستستخدم الواجهة الرسومية
الحقل `data`. وتبقى المراجعة التفاعلية لـ `/memory` مسندة إلى `MemoryCLI`
لأنها تتطلب إدخالًا بشريًا. ويستخدم الـ CLI خدمة الأوامر لجميع
أوامر الشرطة المائلة، عدا `/memory review`.

## 3.11.3 واجهة الويب الرسومية (`core/web.py`)

يشغّل `hagar web` خادم `ThreadingHTTPServer` محليًا مع:

- `GET /` صفحة المحادثة؛
- `GET /static/style.css` و`/static/app.js` (الأصول في `web/`)؛
- `GET /api/events` بث SSE؛
- `POST /api/message` و`/api/confirm` و`/api/project` و`/api/stop`
  و`/api/new-chat` و`/api/resume`؛
- `GET /api/status` و`/api/projects` و`/api/pending`؛
- `GET /api/history` و`/api/history/<session>`؛
- `GET /api/tools` و`/api/audit` و`/api/thinking`؛
- `GET /api/memories` و`/api/memory?path=...`.

تبويبات الواجهة الرسومية هي Chat وChat history وTool output وAudit وThinking و
Memories. ويحتفظ الشريط الجانبي بالمشروع والحالة والرموز؛ والسجل في
التبويب المخصص. ويحفظ `SessionLog` أحداث الجلسة من أجل Tool
output والخط الزمني؛ ويقرأ Audit ملف JSONL؛ ويفضّل Thinking
الاستدلال الذي يكشفه المزوّد، وإلا فيعرض الخط الزمني. ويقرأ Memories
الفهرس، مستبعدًا المحادثة والأرشيف والملخص.

ونقرة على محادثة سابقة تستدعي `POST /api/resume`: فيُعاد تحميل النص
وتعود جلسة التدقيق/الذاكرة إلى ذلك المعرّف، وبذلك تواصل
الأدوار الجديدة المحادثة نفسها. ويستدعي `POST /api/new-chat`
`MemoryStore.new_session()` ويغيّر الجلسة، دون المساس
بالنصوص السابقة.

تعيش الأصول الثابتة في `web/` (`index.html` و`style.css` و
`app.js`). و`render_index()` يحقن الرمز فقط؛ والبقية تُقدَّم
حرفيًا مع قائمة سماح و`importlib.resources`.

الواجهة الرسومية محوّل (adapter): تستخدم `HarnessService` و`CommandService` و
`QueueConfirmationProvider`. وتُجمّد تأكيدات ASK خيط الدور
على `threading.Event`؛ ويبقى الخادم حرًا ويحرّر الطلب بـ
`POST /api/confirm`. والمهلة تعادل الرفض.

ويعرض الشريط الجانبي الرموز المتراكمة للجلسة: يتلقى `UsageLedger`
الاستهلاك من كل استدعاء LLM عبر `usage_sink` وينشر
`usage.updated` على SSE.

**الإيقاف:** يستدعي `POST /api/stop` الدالة `Agent.cancel()`؛ ويتحقق الوكيل
من الحدث بين خطوة وأخرى ويرفع `AgentCancelled`. وبذلك يُقاطَع الدور
على نحو تعاوني، ولا يُجهض طلب HTTP جارٍ بالفعل.

**الرؤية (Vision):** يقبل `POST /api/message` حقل `images` كـ data URL
PNG/JPEG/WebP (بحد أقصى 4، و10 MB لكل واحدة)؛ ويمكن أن يصل جسم JSON إلى
64 MB. ويتحقق `core/images.py` ويحوّل؛ ويبني `Agent.ask(question,
images=...)` محتوى متعدد الوسائط. وتستخدم محوّلات
OpenAI المتوافقة/LM Studio الحقل `image_url`؛ ويستخدم Claude كتل
`image`؛ ويستخدم Gemini `inlineData`. ولا يقبل LM Studio WebP
مباشرة: فتحوّله الواجهة الرسومية إلى PNG. ولا تدخل الصورة في
ذاكرة Markdown ولا في التدقيق.

الأمان: الربط الافتراضي `127.0.0.1`، ورمز عشوائي محقون في
الصفحة، وترويسة `X-Hagar-Token` للـ APIs و`?token=` لـ SSE. وهي ليست
متعددة المستخدمين ولا تعرض بعد تعديل الـ Vault.

## 3.11.6 إدخال الرؤية (`core/images.py`)

يتحقق `ImageInput` من data URL وMIME والحجم؛ ويستخدم `Agent.ask` أجزاء
قانونية (`text` و`image`) ويترجمها كل backend إلى صيغته
الخاصة. ونص الإيقاف والصور منفصل عن المحتوى
المحفوظ: فالذاكرة تحفظ السؤال والرد فقط.

يقرأ `vision.open` صورة من صندوق الرمل، ويتحقق منها بـ magic number
ويعيدها كـ `ToolResult.images`. وتُرفِق دورة `Agent`
الصورة برسالة مستخدم اصطناعية قبل الاستدعاء
التالي، فيراها النموذج دون تلقّي base64 في نص
الأداة. الحدود: 4 صور لكل دور، و10 MB لكل صورة، وPNG/JPEG/WebP.
ويمكن للابن استخدام `vision.open` في مساحة عمله للقراءة فقط.

الصوت غير مُنفَّذ. فقناة المرفقات قابلة لإعادة الاستخدام، لكن
يلزم عقد مزوّد صوتي أصلي مختلف، وصيغ/مفككات ترميز، واختيار
صريح بين ASR وفهم الصوت؛ وهو في خريطة الطريق دون موعد زمني.

يصدّر `memory/export.py` قاعدة بيانات SQLite إلى Markdown:
`Hagar/chat/` و`Hagar/skills/` و`Hagar/summaries/`
و`Hagar/projects/<id>/index.md` و`decisions/`. والكتابة ذرّية
(temp + `os.replace`) ويرفض الأمر وجهة غير فارغة
دون `--force`.

`memory_fts` جدول FTS5 في قاعدة البيانات نفسها، بأعمدة
`entity` و`entity_id` و`kind` و`project` و`status` و`title` و`body`.
ويستخدم `SqliteMemoryIndex.search` الدالة `MATCH` و`bm25()` و`snippet()`؛ وإذا لم يكن FTS5
متاحًا يرتد إلى `LIKE`. ويستورد `memory/import_markdown.py`
البنية نفسها بـ upsert ويعيد بناء فهرس FTS.

## 3.11.4 استهلاك الرموز (`core/usage.py`)

يُطبّع `TokenUsage` الإدخال والإخراج والتخزين المؤقت والاستدلال. والدوال
`usage_from_openai` و`usage_from_anthropic` و`usage_from_gemini` و
`usage_from_ollama` تقرأ الحقول الأصلية للردود.

يحدّث `LLMClient._set_usage()` الحقل `last_usage` ويستدعي `usage_sink`
الخاص بالعميل. ويملك `HarnessService` الكائن `UsageLedger`، ويصله
بالعميل وينشر `usage.updated`؛ وتستخدمه الواجهة الرسومية في الشريط الجانبي ويقرأه `/usage`
من الـ CLI. واستهلاك المزوّد هو
الحقيقة؛ ويبقى التقدير المحلي تراجعًا فقط.

## 3.11.5 فهرس الذاكرة (`memory/index.py`)

`MemoryIndex` فهرس SQLite مشتق من Vault Markdown:

- الجداول `documents` و`meta` و`documents_fts` (FTS5)؛
- مزامنة تزايدية بالبصمة/mtime/size؛
- `rebuild()` يعيد البناء من الصفر؛
- بحث بمرشحات `project` و`kind` و`status`؛
- تراجع `LIKE` إذا لم يكن FTS5 متاحًا؛
- قاعدة البيانات في البيانات المحلية للتطبيق، لا في الـ Vault المتزامن.

وتستخدم أداة `memory.search` الفهرس؛ ويعرض `/memory reindex` و`/memory stats`
الصيانة والحالة. ومع الواجهة الخلفية الافتراضية SQLite يكون
مصدر الحقيقة هو `memory.db`؛ ولا يبقى `MemoryIndex` القديم إلا للواجهة الخلفية
Markdown القديمة.

## 3.11.7 أدوات القرار (`core/decisions.py`)

يختار `DecisionRegistry` مزوّد `DecisionProvider` وتكشف `decision.choose`
الاختيار للنموذج. والمزوّدون المدمجون هم:

- `llm`: يطلب من عميل الـ LLM JSON يحتوي `choice` و`probabilities`،
  ويتحقق من التسميات ويطبّع الاحتمالات؛
- `linear`: يحمّل نموذج JSON محليًا يحتوي التسميات والأوزان والانحياز ويستخدم
  softmax لإنتاج الاحتمالات.

والقدرة `DECISION` منفصلة عن `COMPUTE` و`NETWORK` و
`FILESYSTEM_*`؛ والتفاصيل وصيغة النموذج في
`DECISIONS.md`. و`Jev`/`Kev` ليسا بعد محوّلين أصليين.

## 3.12 الإقلاع والتغليف

يُثبَّت المشروع بـ `pip install -e .` ويعلن الحزم في
`pyproject.toml`. ونقطة الدخول هي `hagar = "hagar:main"`. والإصدار
الحالي هو `0.5.2`.

ملف الإعدادات النموذجي هو `hagar.example.yaml`؛ و`hagar.yaml` ملف
محلي يتجاهله git. والـ Vault الافتراضي في المثال هو
`./vault` ويجب إنشاؤه قبل الإقلاع.

```text
hagar --config PATH       ملف الإعدادات
hagar --model NAME        يتجاوز model.name
hagar --project NAME      يحدد مشروعًا نشطًا
hagar --free              يبدأ في النشاط الحر
hagar --no-memory         يعطّل الذاكرة للجلسة
hagar --no-native-tools   يستخدم بروتوكول JSON النصي
hagar --version
```

يُبحث عن الإعدادات بهذا الترتيب: `--config`، ثم المتغير
`HAGAR_CONFIG`، ثم `./hagar.yaml`. ويعمل `python -m hagar` من
مجلد المشروع.

تشغّل CI الخاصة بـ GitHub Actions المجموعة على Linux وmacOS وWindows مع
Python 3.11/3.12/3.13، وتبني sdist وwheel، وتنفّذ `twine check`،
وتختبر تثبيت الـ wheel. ويبدأ سير العمل `Release` من وسم
`v*`، ويتحقق من مطابقة الوسم لإصدار الحزمة و
ينشئ إصدار GitHub مع المخرجات.

والاختبارات الحية مستبعدة من المجموعة العادية وتُفعَّل بـ
`--live`: فتتحقق من Ollama والمزوّدين عن بُعد (والأخيرون فقط إذا
كان مفتاح API موجودًا).

## 3.13 الأدوات المحلية (`local_tools/`)

ليست خوادم MCP: بل مزوّدون محليون يسجّلون `ToolDefinition`
في السجل ويعيشون خارج الـ core، في حزمة منفصلة.

| الوحدة | الأداة | القدرة |
|---|---|---|
| `calculator` | `calculator.evaluate` | `COMPUTE` |
| `statistics` | `statistics.compute` | `COMPUTE` |
| `unit_converter` | `units.convert` | `COMPUTE` |
| `clock` | `clock.now` | `COMPUTE` |
| `calendar` | `calendar.date` | `COMPUTE` |
| `think` | `think.echo` | `COMPUTE` |
| `text` | `text.diff` | `COMPUTE` |
| `url` | `url.parse` | `COMPUTE` |
| `feeder` | `feed.read` | `NETWORK` |

- يعيد `clock.now` الوقت المحلي والتاريخ والمنطقة الزمنية وإزاحة UTC وepoch.
- يحوّل `calendar.date` التاريخ المحلي، أو تاريخ ISO اختياريًا، إلى
  التقويم اليولياني المديد أو التقويم الإسلامي الجدولي
  (Kuwaiti algorithm). وقد يختلف التقويم الإسلامي الجدولي بيوم واحد
  عن التقاويم القائمة على الرصد أو على أم القرى.
- يعيد `think.echo` السلسلة المستلمة بالضبط؛ ويُستخدم
  لإخراج خطوة وسيطة إلى الخارج في سلاسل الاستدلال.
- يعيد `text.diff` فرقًا موحّدًا بين نصين، بحد أقصى للإدخال
  20000 حرف، وحد أقصى للمخرجات 20000، و`context` من 0 إلى 10. ولا
  يطبّق الفرق.
- يفكّك `url.parse` scheme وhost والمنفذ وpath وquery وfragment دون
  DNS أو شبكة؛ ويحدّ عنوان URL بـ 4096 حرفًا والمعاملات بـ 100. وإذا
  احتوى URL على بيانات اعتماد، فإنه يحجبها في المخرجات.
- `clock` و`calendar` و`think` و`text` و`url` لا تصل إلى نظام الملفات
  أو الشبكة، وتندرج في قاعدة `COMPUTE` allow.
- تستخدم الآلة الحاسبة قائمة AST مسموحة، لا `eval()`، بحدود على
  التعبير وعدد العقد والأس.
- ينزّل `feed.read` بـ `requests` (مهلة 15 ثانية، وبحد أقصى 5 MB)، ويقبل
  عناوين URL من نوع http/https فقط ويستخدم `feedparser`؛ وسياسة `NETWORK` هي `ask`.
- SSRF: يُحل كل مضيف بـ `getaddrinfo` ويجب أن يكون كل عنوان
  عامًّا؛ فالعناوين المحلية (loopback) والشبكات الخاصة وlink-local وmulticast و
  المحجوزة تُرفض. وإعادة التوجيه غير تلقائية: فكل
  `Location` يُعاد التحقق منه وتُوقف بعد 3 قفزات. وعنوان URL يحمل
  بيانات اعتماد يُرفض.
- `permissions.network: true` ضروري كي يمنح سقف النظام
  `NETWORK`؛ و`COMPUTE` في السقف دائمًا لكن يمكن للسياسة حجبها.
- `permissions.agents: true` ضروري لـ `AGENT_SPAWN`؛ ويجب على السياسة
  أيضًا السماح بـ `agent.*`.
- `local_tools` معلنة في `pyproject.toml` وتُثبَّت مع
  المشروع.

وتُسجَّل الأدوات المدمجة من `local_tools/plugins.py` عبر
العقد `ToolPlugin` نفسه الخاص بالإضافات الخارجية. وتُكتشَف الإضافات الخارجية
عبر entry point بالاسم `hagar.tools` وتتلقى `PluginContext`.
وتبقى السياسة وصندوق الرمل في السجل: فلا يمكن لإضافة أن تمنح
أذونات. والإضافة المعطوبة تُتخطى وتُسجَّل في التدقيق، دون
إيقاف الأخريات.

## 3.14 الإضافات (Plugin)

يعرّف `core/plugins.py`:

- `ToolPlugin` + `PluginContext` للأدوات؛
- `LLMProvider` لمزوّدي الـ LLM؛
- الاكتشاف عبر `importlib.metadata.entry_points`؛
- عزل الأخطاء والتدقيق `plugin.loaded`/`plugin.error`.

المزوّدون المدمجون في `llm/plugins.py` ويُسجَّلون قبل
الخارجيين. ولا يمكن لمزوّد خارجي أن يحل محل اسم مدمج.
وإضافات Python موثوقة وتعمل داخل العملية (in-process)؛ وللإضافات غير
الموثوقة يبقى الحد MCP أو عملية منفصلة. والعقد الكامل
في `PLUGINS.md`.

## 3.15 الوكلاء الفرعيون غير المتزامنين

ينفّذ `core/subagents.py`:

- `agent.spawn/status/wait/result/cancel` و`agent.run` المتزامن؛
- `reason` إلزامي في spawn، ومسجَّل في التدقيق؛
- القدرة `AGENT_SPAWN` منفصلة: فلا يتلقاها الابن ولا يستطيع
  إنشاء وكلاء آخرين؛
- سياسة الابن أكثر تقييدًا بصرامة؛ فالسياسات المماثلة أو الأوسع
  تُرفض بـ `SubagentPolicyError`؛
- مهلة زمنية فعلية مدتها 5 دقائق، تعاونية، بحالة `timed_out`؛
- `agent_id` في جميع أحداث التدقيق للأب والابن و
  السجل؛
- حتى وكيلين فرعيين متزامنين؛
- النموذج المحلي نفسه لكن عميل LLM منفصل؛
- مساحة عمل مؤقتة خاصة لكل ابن؛
- مدخلات منسوخة من مساحة عمل الأب؛
- صندوق صادر عبر `artifact.put`/`artifact.put_file` و`mailbox.send` للابن؛
- مخزن artifact مؤقت (بحد أقصى 50 MB لكل artifact، و256 MB لكل دور)
  وmailbox في الذاكرة (بحد أقصى 64 KB لكل رسالة)؛
- قراءة محدودة من الأب عبر `artifact.read` و`artifact.list`
  و`mailbox.inbox/read/ack`؛
- `artifact.save_to` ينسخ الـ artifact بأكمله إلى مسار قابل للكتابة في
  صندوق رمل الأب، دون المرور بالسياق؛
- القدرة `AGENT_DATA`؛
- سجل مرشَّح إلى `FILESYSTEM_READ` و`MEMORY_READ` و`COMPUTE` و
  `AGENT_DATA`؛
- استبعاد `filesystem.chdir` و`agent.*`؛
- لا كتابة في الذاكرة؛
- تأكيدات ASK الخاصة بالابن تُمرَّر إلى المستخدم عبر `ParentBridgeConfirmation`،
  بمهلة 180 ثانية وDENY عند انتهائها؛ ولا يوافق الـ LLM الأب؛
- استهلاك منفصل؛
- أحداث تدقيق `agent.spawned/started/finished/cancelled/failed`؛
- في نهاية الدور، `artifact.discarded` لكل artifact غير مُصدَّر، مع
  سبب `unread` أو `read_but_not_saved` وبيانات وصفية بلا محتوى؛
- تنظيف مساحة العمل والمهمة في نهاية الدور.

`AuditLog.record` متسلسل بقفل للكتابات المتزامنة.
ولا توجد بعد تصديرات artifact، ولا ميزانيات رموز/وقت، ولا تداخل، ولا
واجهة رسومية مخصصة. والتفاصيل في `SUBAGENTS.md`.

---

# 4. نموذج الأمان

- لا يرى الوكيل نظام الملفات الحقيقي: بل مسارات محلولة داخل
  صندوق الرمل فقط.
- تمر العمليات فقط عبر `ToolRegistry`؛ ولا shell مضيف.
- تُعلَن الأذونات في الإعدادات وفي السياسات، وتُطبَّق
  من صندوق الرمل و`PermissionEvaluator`؛ ويمكن للجذور المتداخلة
  أن تقيّد الأذونات.
- الأخطاء بيانات: فالرفض يُعاد إلى النموذج كـ
  نتيجة أداة، لا يُخفى.
- كل فعل يترك أثرًا في التدقيق، مع الجلسة والدور.

---

# 5. التطوير

- المجموعة: `./tools/run_tests.sh` (Linux/macOS) أو
  `.\tools\run_tests.ps1` (Windows). على Windows: 832 ناجحًا، و2 متجاوز
  (الروابط الرمزية غير متاحة دون Developer Mode). وعلى Debian Linux
  (2026-11-06): جميع الاختبارات خضراء، بما فيها الروابط الرمزية (743 ناجحًا، و0
  متجاوز). والتفاصيل ومبرر الـ shim في README §3.1.
- الاختبارات الحية: `./tools/run_tests.sh --live` (Linux/macOS) أو
  `.\tools\run_tests.ps1 --live` (Windows) — 9 اختبارات إضافية (Ollama؛
  والمزوّدون عن بُعد إذا كانت المفاتيح موجودة).
- مقارنة النماذج: `python tools/bench_models.py` (README §3.5).
- مقارنة البروتوكولات: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- المجموعة العادية لا تلمس الشبكة: فـ Ollama وMCP محاكيان.

## 5.1 تعدّد المنصات

- تستخدم المسارات الداخلية `pathlib.Path`؛ أما المعروضة للوكيل
  فتستخدم دائمًا `/` والجذر الافتراضي `/home/ai`.
- يحتوي `filesystem.sandbox` على مسارات للنظام المضيف، مطلقة أو بـ
  `~` إن اختار المستخدم ذلك: و`Path.expanduser()` يحل مجلد المنزل فقط
  عندما يستخدمه المسار. ولا يُفترض وجود مجلد منزل مخصص.
- لكل mount اسم مستعار صريح وفريد (بغض النظر عن حالة الأحرف)؛ ويمكن أن يكون
  المسار الفيزيائي على أي وحدة تخزين.
- `tools/run_tests.sh` هو مشغّل POSIX؛ و`tools/run_tests.ps1` و
  `tools/pytest_shim` يخدمان فقط صندوق رمل Windows ذا الرمز
  المقيَّد.
- الفرع الوحيد الصريح الخاص بـ Windows المتبقي هو تاريخ الإنشاء في
  `stat`: `st_birthtime` حيث يكون متاحًا، وإلا `st_ctime` على
  Windows؛ وعلى Linux قد يكون `created_at` هو `None`.
- تستخدم الـ APIs الخارجية (OAuth وMCP وLLM) بروتوكول HTTP و`webbrowser`، لا
  أوامر نظام.
- تغطي CI الخاصة بـ GitHub Actions Linux وmacOS وWindows على Python
  3.11/3.12/3.13؛ وتبقى الروابط الرمزية وأذونات رموز OAuth واستدعاءات العودة المحلية
  بحاجة إلى تحقق باختبارات حية، لا في المجموعة دون اتصال.

---

# 6. الحدود المعروفة والدين التقني

- يغطي `PermissionEvaluator` الإصدار v1: وتبقى الذوات الديناميكية و
  تأكيدات الواجهة الرسومية وقدرات MCP الممنوحة من الإعدادات.
- يعتمد الاستدعاء الأصلي على النموذج: فبعضها يتجاهل الأدوات أو
  يعيد استدعاءات متعددة؛ ويغطي التراجع النصي الأخطاء، لا
  جودة الاختيار.
- يدعم عميل MCP المصادقة bearer/header وOAuth authorization code؛ ولا
  يدعم device flow ولا DPoP ولا mTLS ولا client assertion.
- مراجعة المهارات يدوية من الـ CLI؛ وتغيب واجهة رسومية.
- البحث في الذاكرة بالكلمة المفتاحية، دون فهرس أو
  embedding.
- يستخدم السياق المحقون أدوارًا حديثة عامة وحتى 3 مهارات
  مؤكدة عبر المطابقة المعجمية، دون اختيار دلالي.
- لا تحذف الذاكرة محادثات أو مهارات بحسب القِدَم: فـ `archive` هو
  الإزالة الوحيدة من السياق.
- للتدقيق تدوير واحتفاظ (`max_files`)، لكن بلا ضغط
  للجلسات ولا تثبيت خارجي للسلسلة.
- يتحقق `feed.read` من العناوين وإعادة التوجيه، لكن تبقى حالة DNS
  rebinding: فـ `requests` يحل الاسم مرة ثانية عند
  الاتصال؛ ويلزم resolver مثبَّت.
- الآلة الحاسبة ليست CAS: فهي تتناول تعبيرات عددية
  محدودة فقط، لا رمزية.
- `stat().created_at` هو `None` على Linux عند غياب `st_birthtime`؛ ولا
  يُختلَق تاريخ إنشاء.
- لا يمكن لاسمين مستعارين أن يشيرا إلى المسار الفيزيائي نفسه: فالاسم المستعار
  يعرّف mount ويجب أن يبقى المخرج الافتراضي فريدًا.

## 6.1 مسؤولية المستخدم: الروابط الصلبة وmount وTOCTOU

**لا يتحقق Hagar من الروابط الصلبة ولا mount/junction ولا سباقات TOCTOU
داخل المجلدات المسموح بها.** وليس هذا عيبًا في Hagar: فصندوق الرمل
قائم على المسار ولا يستخدم مقابض (handle) أو واصفات ملفات للعملية بأكملها.

الرابط الصلب اسم ثانٍ للـ inode نفسه، وليس له هدف مسار
ولا يستطيع صندوق الرمل معرفة ما إذا كان هناك اسم آخر في الخارج. أما
mount أو junction فيمكنه عرض نظام ملفات آخر مع بقائه داخل
بادئة المسار. ويمكن لسباق TOCTOU أن يغيّر مكوّنًا بين فحص
الروابط الرمزية والعملية الفعلية: فلا يستخدم Hagar `openat2`،
ولا `O_NOFOLLOW` على كل مكوّن، ولا مقابض Windows، وبالتالي لا يضمن
الذرّية بين الفحص والوصول.

لا تنشئ أدوات نظام الملفات في Hagar روابط صلبة. وإذا وُجد رابط صلب أو
mount مسبقًا داخل مجلد من صندوق الرمل، يعامله Hagar
كملف أو مجلد عادي ويمكنه قراءته أو تعديله أو حذف اسمه
الداخلي.

وبالتالي تتوزع المسؤولية:

- **Hagar يضمن** أن تبقى المسارات المحلولة داخل الاسم المستعار في
  لحظة الفحص، وأن الروابط الرمزية غير مرئية، وأن الأذونات
  `R`/`W`/`X` مطبقة، وأن المسارات الحقيقية لا تظهر
  في مخرجات النموذج.
- **المستخدم يضمن** أن المجلدات المُعدّة في
  `filesystem.sandbox` لا تحتوي روابط صلبة أو mount أو junction نحو
  محتويات لا يجب أن تكون متاحة، وألا تستطيع أي عملية
  متزامنة غير موثوقة تعديل تلك المجلدات أثناء
  التنفيذ، إن أراد عزلًا تامًّا.

تتطلب سباقات TOCTOU فاعلًا محليًا متزامنًا لديه وصول
للكتابة إلى مجلدات صندوق الرمل: فهي ليست حالة عرضية
في الاستخدام العادي، بل سيناريو خبيث أو بيئة مخترقة.
وللعزل القوي يلزم مجلد تخزين مخصص، أو مستخدم منفصل، أو
mount namespace، أو حاوية (container)؛ وليس هذا من مهام
محلّل المسارات.

وهذه النقاط مغلقة بوصفها **مسؤولية المستخدم**، لا ديونًا
تقنية في Hagar. فالروابط الصلبة وmount/junction وسباقات TOCTOU غير
مكتشفة ولا محجوبة في هذا الإصدار.

---

# 7. خريطة التوثيق

- `MANUAL.md` — دليل المستخدم: الأوامر والإعدادات والسياسات والافتراضيات.
- `ARCHITECTURE.md` — هذا المستند: كيف هو النظام اليوم.
- `ROADMAP.md` — ما ينبغي فعله، والقرارات المتخذة، والنقاط المفتوحة.
- `PLUGINS.md` — عقود الأدوات ومزوّدي LLM من نوع plugin.
- `DOCUMENT_TOOL.md` — مواصفة أداة المستندات، ومخطط الرسم البياني، و
  بروتوكول المضيف الأصلي.
- `SUBAGENTS.md` — الوكلاء الفرعيون MVP والحدود.
- `CHANGELOG.md` — تاريخ الإصدارات.
- `README.md` — الإقلاع والإعدادات والاختبارات.
