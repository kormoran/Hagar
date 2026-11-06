# HAGAR — المعمارية

الإصدار: 0.2.0 (قيد التطوير)
آخر تحديث: 2026-11-03

---

# 1. ما هو Hagar

Hagar هو إطار تشغيل للنماذج اللغوية الكبيرة مكتوب بلغة Python، ومصمَّم للتنفيذ
المرن (resilient) للنماذج اللغوية.

الهدف ليس محادثة مع نموذج، بل بيئة تشغيلية
**آمنة** يستطيع فيها النموذج استخدام الأدوات، والرجوع إلى ذاكرة
دائمة، والتفاعل مع أنظمة خارجية دون وصول مباشر
إلى الموارد الفعلية للجهاز المضيف.

ولهذا الغرض يطبّق المشروع مبادئ HMI/HCI والإرغونوميا المعرفية
على تصميم البيئة التي يعمل فيها النموذج.

## 1.1 قوانين HAGAR الأربعة

**القانون الأول — النموذج غير موثوق بحكم التعريف.**
لا لأنه سيئ أو عديم الفائدة: بل لأنه احتمالي. فكل تصريح له
يجب التحقق منه، وكل فعل له يجب أن يُقيَّد.

**القانون الثاني — الأدوات أكثر موثوقية من النموذج.**
فإذا قال نظام الملفات إن ملفًا موجود، فهو موجود. وإذا أعادت الأداة
حجمًا، فذلك الحجم حقيقي. النموذج يفسّر، والأدوات
تقيس.

**القانون الثالث — يجب أن توجد الحالة خارج ذهن النموذج.**
فـ ToolRegistry وMCP وFileSystemSandbox و(في المنظور)
PermissionEvaluator تنقل المعرفة والتحكم إلى خارج النموذج،
كما في الأنظمة الحرجة للسلامة.

**القانون الرابع — يجب أن يكون كل فعل قابلًا للتفسير لاحقًا.**
يجيب سجل التدقيق عن السؤال الصحيح: لا «لماذا فقد النموذج صوابه؟»
بل «أي افتراض تبنّاه؟»، «أي أداة استخدم؟»، «أي بيانات كانت
خاطئة؟». تحقيق في الحوادث، كما في الطيران.

## 1.2 المحظورات المطلقة

يجب ألّا يفعل النموذج أبدًا ما يلي:

- الوصول المباشر إلى نظام ملفات المضيف؛
- تنفيذ أوامر على الصدفة الحقيقية؛
- الحصول على امتيازات أعلى من تلك المحددة في الإعدادات؛
- معرفة التنظيم الفعلي لنظام التشغيل.

تمر جميع العمليات حصريًا عبر أدوات مسجّلة و
خاضعة لرقابة إطار التشغيل.

## 1.3 المبادئ المعمارية

- الفصل بين النموذج ونظام التشغيل؛
- الأمان افتراضيًا؛
- معمارية قائمة على الإضافات (plugins)؛
- الاستقلال عن مزوّد LLM؛
- القابلية للتوسّع عبر الأدوات وبروتوكول MCP.

---

# 2. المعمارية

```text
المستخدم
  │
  ▼
Agent ──────────────── AuditLog (JSON Lines)
  │
  ├── LLMClient (llm/base.py)
  │     ├── OllamaClient
  │     ├── DeepSeekClient
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
Agent              turn.start
  ↓
LLMClient          llm.tool_choice
  ↓
ToolCall
  ↓
ToolRegistry       tool.call
  ↓
ToolResult         tool.result
  ↓
LLMClient
  ↓
الرد النهائي       turn.answer
```

---

# 3. المكوّنات

## 3.1 الإعدادات (`core/config.py`)

يحمّل ملف YAML (`hagar.yaml`) ويتحقق من صلاحيته إلى `AppConfig`.

الأقسام:

| القسم | إلزامي | المحتوى |
|---|---|---|
| `model` | نعم | المزوّد، والاسم، وhost، وmax_tokens، وapi_key_env، وnative_tools |
| `vault` | نعم | مسار خزنة Obsidian |
| `filesystem` | نعم | `sandbox`: قائمة `{alias, path, permissions}`؛ و`limits`: ميزانية الكتابة |
| `permissions` | لا | read، وwrite، وshell، وnetwork (الافتراضي `true/false/false/false`) |
| `rag` | لا | `top_k` (الافتراضي 8) |
| `mcp_servers` | لا | endpoint، وnamespace، وauth (bearer/header/oauth) |
| `audit` | لا | enabled، وpath، وmax_field_chars، وmax_bytes، وmax_files، وinclude_outputs |
| `policy` | لا | مسار ملف السياسة، وsubject |
| `memory` | لا | enabled، وvault_subdir، وcontext_turns، وcontext_skills، وmax_skill_chars |

تُنتج أخطاء التحقق دائمًا `ConfigError`، مع رسالة
تشير إلى الحقل. ويُحلّ مسار التدقيق، إن كان نسبيًا،
نسبةً إلى ملف الإعدادات.

## 3.2 واجهة LLM والواجهات الخلفية (`llm/`)

لـ `LLMClient` مساران:

- **الاستدعاء الأصلي** (افتراضي): `native_step()` يرسل مخططات
  الأدوات بتنسيق المزوّد ويقرأ النداءات من الرد؛
- **بروتوكول JSON النصي** (احتياط): `request_tool_call()` يطلب
  JSON يحوي `tool`/`arguments`، مع تحليل متين ومحاولة
  إصلاح واحدة.

يُبنى مخطط المعاملات من `ToolDefinition`:
OpenAI/Ollama يستخدمان `tools[].function`، وClaude `tools[].input_schema`،
وGemini `functionDeclarations`. ويستخدم الحوار المعياري الأدوار
`user`/`assistant`/`tool`؛ وكل عميل يترجمه (OpenAI `tool_calls`،
وClaude كتل `tool_use`/`tool_result`، وGemini `functionCall`/
`functionResponse`). ورفض HTTP 400/404/422 يُنتج
`NativeToolsUnavailable`: فينتقل الـ Agent إلى البروتوكول النصي فقط إذا لم يكن قد
نفّذ أدوات بعد.

تُطبَّع أسماء الأدوات للـ APIs التي لا تسمح
بالنقطة (`filesystem.read_file` ← `filesystem__read_file`) وتُعاد إلى
الاسم الداخلي في الرد: فترى السياسة والتدقيق والاختبارات دائمًا الاسم
الأصلي.

ويبقى النص هو الاحتياط للنماذج التي لا تدعم الأدوات الأصلية؛
ويفرضه `model.native_tools: false` (أو `--no-native-tools` من CLI).

| المزوّد | API | المفتاح | ملاحظات |
|---|---|---|---|
| `ollama` | `/api/chat`، `/api/generate` | — | host الافتراضي `localhost:11434` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system مضمَّن |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system منفصل، وأدوار متبادلة |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`، والدور `model` |

يُقرأ المفتاح من البيئة فقط؛ و`model.api_key_env` يتجاوز
الاسم الافتراضي. و`model.host` هو عنوان URL الأساسي لجميع المزوّدين (مع
افتراضي لكل مزوّد)، و`model.max_tokens` يستخدمه Claude فقط.
و`llm/factory.py` يبني العميل ويرفض المزوّدين المجهولين أو
المفاتيح المفقودة. DeepSeek: النماذج الحالية هي `deepseek-flash` و
`deepseek-v4-pro`؛ ولم يعد `deepseek-chat` مقبولًا.

الحالة الحالية: **الاستدعاء الأصلي v1** مع احتياط نصي تلقائي
(راجع ROADMAP).

## 3.3 نموذج الأدوات (`core/tool_*.py`)

يصف `ToolDefinition` الاسم والوصف والفئة والمعاملات و
الhandler و`origin` (`local` أو `mcp.<namespace>`) و`capabilities`
المعلنة وحالة التفعيل و`requires_confirmation`
(أرضية ASK التي يطبّقها السجل).

و`ToolCall` هو طلب النموذج (`tool`، و`arguments`، و`id`)؛
و`ToolResult` هو النتيجة المهيكلة (`tool_name`، و`success`، و`output`،
و`error`).

و`ToolRegistry` يسجّل الأدوات ويبحث عنها ويفعّلها/يعطّلها وينفّذها؛
ويعرض البيانات الوصفية على النموذج، وهو نقطة التنفيذ الوحيدة.

## 3.4 الوكيل (`core/agent.py`)

حلقة وكيلية متعددة الخطوات، بمسارين:

- **أصلي**: قد يحوي الرد عدة نداءات؛ فيعيد الـ Agent إدراج
  رسالة `assistant` ورسالة `tool` بمعرّف لكل
  نتيجة؛
- **نصي**: نداء واحد في كل مرة، والنتيجة تُرسَل كدور
  `user`.

في كلا المسارين:

1. يقرر النموذج ما إذا كانت هناك حاجة إلى أداة؛
2. إن لم تكن هناك حاجة، أغلق الرد النهائي الدور؛
3. إن كانت هناك حاجة، تُنفَّذ الأداة وتعود النتيجة إلى النموذج؛
4. الحد `max_tool_calls` صالح للدور كله. وإذا أصرّ النموذج،
   أُغلق الدور بـ `Agent stopped after N tool calls`
   (حماية من الحلقات).

وإذا فشلت الخطوة الأصلية الأولى بـ `NativeToolsUnavailable`، انتقل الـ Agent
إلى البروتوكول النصي (`llm.native_fallback`)؛ وخطأ بعد أن
نُفِّذت أداة يُغلق الدور بـ `turn.error`، دون
احتياط.

تُسجَّل كل خطوة في التدقيق: السؤال، واختيار الأداة، والمعاملات،
والنتيجة، والمدة، والرد النهائي. والتدقيق المعطوب لا يوقف الوكيل: بل
يُبلَّغ عن العطل على stderr.

ويتلقى الـ `Agent` الخزنة `Vault` لكنه لا يستخدمها بعد.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

نظام الملفات الافتراضي للوكيل. وكل طلب:

1. يُحلّ نسبةً إلى المجلد الحالي (`resolve_path`)؛
2. يُتحقَّق منه مقابل الجذور الممنوحة (`effective_permissions`)؛
3. يُفلتر بالأذونات الفعلية، والجذور الأكثر خصوصية
   تتجاوز الأكثر خارجية؛
4. يُفحص مقابل الروابط الرمزية والمساحة الحرة على القرص
   (`FS_Guardian`، وهو اسم قديم).

و`DirectoryPermissions` ينمذج `read`، و`write`، و`create`، و`rename`،
و`delete`، و`execute`؛ و`None` تعني «يرث من الجذر الخارجي».
والمسار خارج الجذور يكون دائمًا `PermissionError`.

و`FileInfo` / `stat()` يعيدان النوع، والحجم بالبايت، وتواريخ
الإنشاء/التعديل/الوصول (ISO 8601 مع إزاحة محلية)، والأذونات
**الفعلية لبيئة العزل**، لا ACL الخاصة بنظام التشغيل.

**الروابط الرمزية (symlinks) غير موجودة بالنسبة إلى بيئة العزل.** فلا يعرضها Hagar، ولا
يقرأها، ولا يتبعها، ولا يحذفها: و`stat` و`list_dir` و`search`
تتجاهلها؛ و`read_file` و`read_chunk` و`delete_file` ترد “not
found”؛ و`chdir` على رابط رمزي يرد “Directory not found”. والرابط
المكسور أو المتجه إلى الخارج لا يمكن تمييزه عن مسار غير موجود.

جذر بيئة العزل الافتراضي هو `/home/ai`؛ وكل مجلد مضبوط
يُعرض كـ `/home/ai/<alias>`. و`stat` و`list_dir` و`search`
و`read_chunk` ورسائل `write`/`create`/`mkdir`/`delete` و`chdir`
تُظهر مسارات افتراضية فقط: فلا يظهر المسار الفعلي أبدًا
في مخرجات النموذج. والمدخلات `/home/ai/<alias>/...` تُحلّ
نسبةً إلى المجلد الفعلي للاسم المستعار؛ وتبقى المسارات النسبية
نسبية إلى المجلد الحالي.

و`/home/ai` مجلد اصطناعي: يمكن سرده وقياسه (stat)، لكنه
ليس mount ولا يمكن تنفيذ `chdir` إليه. ومدخلات
`filesystem.sandbox` تبقى مسارات لنظام المضيف، مطلقة أو ذات
`~` إن اختار المستخدم ذلك: فقد تكون أي مجلد موجود و
قابل للوصول. ولا ينشئ Hagar مجلدات ولا يفترض وجود مجلد منزلي
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

لا يوجد علم (flag) `enabled`: فكل مدخلة صالحة في `filesystem.sandbox`
تُركَّب (mount). والأسماء المستعارة أو الأذونات غير الصالحة، والمسار المفقود أو المكرر
توقف الإعدادات. ويمكن أن تحتوي المسارات الفعلية والأسماء الداخلية
على مسافات؛ أما الاسم المستعار فلا، لأنه يجب أن يبقى مقطعًا
افتراضيًا واحدًا.

و`R` يغطي القراءة والسرد والبحث و`stat`؛ و`W` يغطي الكتابة
والإنشاء وإعادة التسمية والنسخ والحذف؛ و`X` يغطي `chdir`. وتبقى
الأذونات العامة `permissions.read`/`write` سقفًا: فلا يمكن لاسم مستعار
`RWX` أن يتجاوزها.

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
glob تكراريًا بحد للنتائج؛ ويتطلب `copy_file` إذن `create`؛
ويتطلب `rename` إذن `rename` على المصدر و`create` على الوجهة.
والمسارات المعادة افتراضية دائمًا (`/home/ai/<alias>/...`).
و`chdir` يتطلب `X` على الاسم المستعار.

ويعيد `list_dir` 100 مدخلة كحد أقصى في الصفحة (`limit` بحد أقصى
500) مع `offset` و`next_offset` و`has_more`؛ وإن كانت هناك مدخلات أخرى،
فإن `message` يقول `voci: riportate X di Y; per continuare usa offset=Z`.
ويستخدم `search` الترقيم نفسه: `max_results` هو حد الصفحة
(الافتراضي 100، وبحد أقصى 500)، و`offset` يتنقل في النتائج. وللأشجار
الكبيرة يُفضَّل تضييق `pattern`/`path` بدلًا من تكرار صفحات
كثيرة. و`read_file` يقبل الملفات حتى `CHUNK_SIZE` (4096 بايت) فقط؛
وما زاد، يحيل الخطأ إلى `read_chunk()` لأن قراءة الملف كله
ستتجاوز نافذة السياق. ويعيد `read_chunk` `next_offset` و
حدود UTF-8 كاملة.

ولا يعرض `list_dir` و`search` الروابط الرمزية؛ ويعاملها `read_file` و`read_chunk`
كملفات غير موجودة.

يكتب `write_file` فوق الملفات الموجودة فقط؛ وتمرّ عملية الإنشاء عبر
`create_file`، الذي يتطلب إذن `create`. ولا يمكن
الالتفاف على حظر الإنشاء بكتابة مسار جديد.

### حدود الكتابة

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = معطّل
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` هو الحد الأقصى لكل عملية من
  `write_file`، أو `create_file`، أو `copy_file`؛
- `min_free_bytes` هو احتياطي المساحة الذي يجب أن يبقى بعد
  العملية؛
- `session_write_bytes` هو الميزانية التراكمية للجلسة؛
- `ask_over_bytes` يرفع إلى `ASK` العمليات التي تتجاوز العتبة. والفحص المسبق
  مدمج في `ToolRegistry`: فإذا قالت السياسة أيضًا `ASK`، كان
  التأكيد واحدًا فقط.

و`0` يعطّل الحد الواحد. وتجاوز `max_write_bytes`،
أو `session_write_bytes`، أو الاحتياطي يُنتج خطأً، لا تأكيدًا:
فهي ثوابت، لا أسئلة. و`ask_over_bytes` هو المستوى الوحيد الذي
يسأل المستخدم.

و`filesystem.stat` يعيد JSON يحوي `path`، و`exists`، و`kind`
(`file`/`directory`/`other`)، و`size_bytes`، و`created_at`، و`modified_at`،
و`accessed_at`، و`permissions`. والمسار غير الموجود ليس خطأً:
`exists: false` مع الأذونات المنطبقة.

## 3.7 MCP (`llm/mcp_client.py`)

عميل MCP عبر HTTP/JSON-RPC: `initialize`، و`tools/list`، و`tools/call`،
والتحويل التلقائي للأدوات إلى `ToolDefinition` والتسجيل بـ
الفضاء الاسمي `mcp.<namespace>`.

ويدعم أيضًا ردود `text/event-stream` (HTTP القابل للبث) ويرسل
إشعار `notifications/initialized` بعد المصافحة (handshake). ويستخدم
`MCP-Protocol-Version` (الافتراضي `2025-06-18`، مع احتياط) ويعيد استخدام
`Mcp-Session-Id` عندما يعيده الخادم. وتتضمن أخطاء HTTP
جسم الرد لجعل أخطاء 400 قابلة للتشخيص.
وتُطبَّع نتائج الأدوات إلى نص: كتل `text`،
أو `structuredContent` وإلا JSON؛ والنتيجة التي تحمل `isError`
تصبح خطأً في الأداة.

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

يُقرأ الرمز من البيئة فقط ولا يظهر في التدقيق. وإذا كان مفقودًا،
يُتجاوز الخادم مع `mcp.failed` ويستمر إطار التشغيل؛ وتبقى الخوادم الأخرى
متاحة.

### OAuth تفاعلي

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

تدفق authorization code + PKCE، مع callback على
`http://localhost:<port>/oauth/callback` وفتح المتصفح. وإذا حوى
النطاق `offline_access`، يُضاف `prompt=consent`.
وتُكتشَف البيانات الوصفية من `.well-known` (RFC 9728 للمورد،
وRFC 8414 لخادم التفويض)؛ وإذا كان `client_id` مفقودًا
يُستخدم التسجيل الديناميكي. والرموز في ملف محلي
بأذونات مقيّدة (`0600` حيث يدعمها النظام)، مع تجديد
تلقائي وإعادة محاولة مرة واحدة عند `401`.

وCtrl-C أثناء انتظار الـ callback يغلق الخادم المحلي ويخرج
بالرمز 130، دون traceback.

القيود: لا device flow، ولا DPoP، ولا mTLS، ولا client assertion؛ ويجب أن يستطيع المتصفح
الوصول إلى الـ callback المحلي. وإذا لم يصل الـ callback، فإن
الطرفية تطلب لصق عنوان URL الخاص بإعادة التوجيه.

## 3.8 الخزنة (`memory/vault.py`)

الوصول إلى خزنة Obsidian بمسارات نسبية إلى الجذر و
حماية من الخروج من الخزنة. ويتيح القراءة، والكتابة، والإضافة (append)،
وسرد الملفات، و`load_all` للقراءة التكرارية. ودلالات
الذاكرة تعيش في `memory/store.py` (§3.11).

## 3.9 سجل التدقيق (`core/audit.py`)

ملف JSON Lines للإضافة فقط. وكل سطر فيه طابع زمني بتوقيت UTC، و`session`، و
`event`؛ وأحداث السؤال الواحد تتشارك معرّف `turn`.

```text
harness.start      المزوّد، والنموذج، والجذور، والأذونات، والأدوات، والخزنة
turn.start         السؤال، وحد الأدوات، والنمط الأصلي
llm.tool_choice    اختيار النموذج، والمعاملات، وmode=native
llm.native_fallback مزوّد بلا أدوات أصلية، والانتقال إلى النص
llm.protocol_error رد غير مطابق (النص الكامل، مقتطعًا)
llm.repaired       إصلاح ناجح
llm.repair_failed  إصلاح فاشل
tool.call          الأداة، والمعاملات، والفهرس
tool.result        النتيجة، والمخرجات/الخطأ، والكمون بالمللي ثانية
turn.answer        الرد النهائي، وعدد الأدوات المستخدمة
turn.error         المرحلة والرسالة
turn.stop          بلوغ الحد
mcp.loaded         الفضاء الاسمي والأدوات المستوردة
mcp.failed         الفضاء الاسمي والخطأ
llm.failed         مزوّد لا يمكن بناؤه (مثل مفتاح مفقود)
harness.stop       خروج نظيف (إن غاب، فقد قُتلت العملية)
memory.enabled     الجذر، والمجلد الفرعي، وأدوار السياق
memory.disabled    سبب التعطيل
memory.context     الأدوار والمهارات المُدرَجة في الموجّه
memory.turn        دور محفوظ في الخزنة
memory.failed      المرحلة والخطأ
```

الخصائص:

- كتابة بأفضل جهد: خطأ الإدخال/الإخراج لا يوقف إطار التشغيل ويُبلَّغ عنه
  مرة واحدة فقط على stderr؛
- اقتطاع قابل للضبط (`audit.max_field_chars`، الافتراضي 2000)؛
- سلسلة بصمات (`prev`/`hash`) قابلة للتحقق عبر `verify_chain`؛
- التدوير إلى `<file>.<timestamp>` بعد تجاوز `audit.max_bytes` (و0 يعطّل)؛
- الاحتفاظ: `audit.max_files` (الافتراضي 100) يحتفظ بـ N ملف كحد أقصى،
  بما فيها الملف النشط؛ وتُحذف النسخ الاحتياطية الأقدم؛
- مع `audit.include_outputs: false` تُسجَّل مخرجات الأدوات
  بالحجم فقط؛
- القيم غير JSON تُجعل قابلة للتسلسل؛
- لا مفاتيح API في السجل؛
- يحتوي السجل أيضًا مخرجات الأدوات (أي محتويات ملفات):
  فيجب حمايته كمساحة العمل.

## 3.10 الأذونات (`core/permissions.py`)

النموذج مصفوفة فاعل × كائن:

- **Capability** (`IntFlag`): ما يمكن للعملية أن تفعله
  (`FILESYSTEM_READ`، و`FILESYSTEM_WRITE`، و`FILESYSTEM_CREATE`،
  و`FILESYSTEM_DELETE`، و`FILESYSTEM_EXEC`، و`MEMORY_READ`،
  و`MEMORY_WRITE`، و`NETWORK`، و`MCP_CALL`، و`COMPUTE`). وتُدمج بـ `|`؛
  والتحقق دائمًا بالمجموعة الجزئية.
- **Effect** (`IntEnum`): `ALLOW`، و`ASK`، و`DENY`. وعند التعارض
  يفوز القيمة الأعلى (`DENY > ASK > ALLOW`).
- **Rule**: القدرة + الأثر + الفلاتر الاختيارية `tools` (glob)،
  و`paths`، و`namespaces` (بادئات) + `reason`.
- **Subject**: من يطلب (الوكيل، أو المستخدم، أو النظام)، مع قواعد
  وافتراضي (`DENY` إن لم يُحدَّد).
- **Resource**: كائن القرار (حاليًا أداة بقدراتها؛
  وفي المستقبل أيضًا الملاحظات والمسارات).
- **Decision**: الأثر، والسبب، والقاعدة المطبقة.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. يجب أن يوفّر المورد القدرات المطلوبة؛
2. يجب أن يمنحها **سقف النظام** (المشتق من `permissions.read/write/shell`)؛
3. لكل قدرة تُطبَّق قواعد الفاعل: فيفوز
   الأكثر خصوصية (عدد الفلاتر، ثم طول البادئة)، وعند
   التساوي الأثر الأكثر تقييدًا؛ وبدون قواعد يسري الافتراضي؛
4. عند طلب أكثر من قدرة يسري منطق AND: فيفوز الأثر الأسوأ.

و`ASK` ليس قرارًا: بل سؤال لإنسان. ويطرحه
`ConfirmationProvider` — فـ `ConsoleConfirmation` يطلب
`lo faccio? (y/N)` والافتراضي N — وبدون قناة تأكيد يسري
`DENY`. ويمكن لواجهة GUI أن تنفّذ البروتوكول نفسه بنافذة حوار
نمطية.

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

ويُقرأ `policy.yaml` **قبل** بناء LLM. وإذا لم يكن
قابلًا للقراءة أو لم يكن صالحًا، يطبّق إطار التشغيل `DENY` على كل السياسات،
ويسجّله في التدقيق (`policy.failed`) ويبلّغ عنه في الدردشة؛ ويستمر بقية
إطار التشغيل في العمل. وحتى غياب الفاعل يُخفَّض إلى
`DENY`.

ويحدث الفحص في `ToolRegistry.execute`، نقطة التنفيذ الوحيدة، ويُنتج الحدثين
`permission.decision` و`permission.confirmation`.

ويقارن نطاق `paths` المسار **الذي يكتبه النموذج**
(المطبَّع)، لا المسار المحلول بواسطة بيئة العزل: فالمسار المطلق أو
`chdir` قد لا يطابق بادئة نسبية، وتبقى
النتيجة `DENY` (الفشل إلى الرفض، fail closed).

## 3.11 الذاكرة (`memory/store.py`، `memory/tools.py`)

**الحدثية.** يضيف إطار التشغيل كل دور منتهٍ إلى ملاحظة لكل
جلسة:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter يحوي `session`، و`type: chat`، و`created`؛ والجسم فيه
قسم لكل دور (`## <timestamp> · <turn>`)، والسؤال والجواب. ولا
تُحفظ مخرجات الأدوات: فتلك تبقى في التدقيق.

وفي بداية كل دور يُدرج الـ Agent في الموجّه آخر
`memory.context_turns` دورًا (و0 يعطّل الإدراج)، مع اقتطاع
السؤال والجواب. ومع `memory.context_skills > 0` يضيف حتى N
**مهارة مؤكَّدة** ذات صلة بالسؤال، بالمطابقة المعجمية على
العنوان والوسوم والمحتوى؛ والمرشحات والمؤرشفة لا تدخل أبدًا.
وتُوسم الكتلة كبيانات، لا كتعليمات. وخطأ الذاكرة
لا يوقف الدور: بل يُسجَّل `memory.failed`.

**الدلالية.** يمكن للنموذج أن يقترح ذاكرة بثلاث أدوات:

| الأداة | القدرة | الفضاء الاسمي |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

يكتب `create_skill` الملف `<vault>/Hagar/skills/<slug>.md` مع frontmatter
يحوي `id`، و`title`، و`kind` (`fact`/`procedure`)، و`status: candidate`، و`tags`،
و`source_session`، و`source_turn`، و`model`، و`created_at`. والـ slug
آمن (ASCII فقط، وبلا مسار)؛ والعنوان الموجود أصلًا لا
يُكتب فوقه، ويعيد `duplicate: true`.

ويعيد `get_context` الأدوار الأخيرة أو يبحث بالكلمة المفتاحية
في الجلسات السابقة؛ ويفلتر `list_skills` بحسب `kind` و`status`.

**دورة الحياة.** الحالات هي `candidate`، و`confirmed`، و`archived`.
والنموذج ينشئ مرشحات فقط؛ والانتقال بشري، من CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

ويعرض `/memory review` مرشحًا واحدًا في كل مرة مع بيان المصدر و
المحتوى، ثم يطلب `y/N/a/s/q` (تأكيد، وترك، وأرشفة، وتجاوز،
وخروج). والتأكيد يكتب `reviewed_at`؛ و`archive` قابل للعكس بـ
`confirm`. وكل انتقال يُنتج `memory.status` أو `memory.review`
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

لكل مشروع `index.md` يحوي الحالة، وآخر نشاط، والملخص، و
عدد القرارات النشطة. ولكل قرار حالة
`candidate`/`active`/`superseded`/`archived`، والبدائل، والمبرر،
وبيان المصدر، و`auto_saved`. ولا تُعاد كتابة القرارات: فقد يحل
قرار جديد محل قرار قديم.

وعند الإقلاع يعرض Hagar المشاريع النشطة و«النشاط الحر»:

```text
/project list
/project new <nome>
/project select <nome>
/project free
/project status
/project archive <nome>
/project unarchive <nome>
```

والتجاوزات غير التفاعلية هي `--project <nome>` و`--free`.

وفي نهاية الجلسة:

1. يُنقل نص المحادثة إلى `archive/chat/`؛
2. يُولَّد ملخص بالنموذج، مع احتياط ميكانيكي؛
3. يُحفظ الملخص مع رابط وبصمة (hash) لنص المحادثة؛
4. إن كان هناك مشروع، يقترح النموذج قرارات `candidate`؛
5. يمكن للمستخدم مراجعتها؛ فإن رفض بقيت `candidate` مع
   `auto_saved: true`.

ويستخدم السياق المُدرَج **فهرس** المشروع: الملخص، وعناوين
القرارات النشطة وعددها، لا كل الأجسام. وتُقرأ التفاصيل
بـ `memory.project_context(query=..., limit=...)`. والكتلة
الإجمالية محدودة بـ `max_context_chars`؛ وإذا قُطعت،
سجّل التدقيق `memory.context_trimmed`. وليس تقديرًا للرموز: بل
ميزانية بالأحرف، حتمية.

وعندما يتجاوز مشروع `project_max_active`، يسأل Hagar هل
يؤرشفه. والأرشفة قابلة للعكس ولا تحذف شيئًا.

**تصفّح الأرشيف.** نصوص المحادثات المؤرشفة تحمل `project`
في الـ frontmatter. والبحث والقراءة عند الطلب:

```text
/memory archive search <testo>
/memory archive read <session> [offset] [limit]
```

وتُعرض الأدوات نفسها كـ `memory.archive_search` و
`memory.archive_read`؛ فالبحث يعيد session، وturn، وtimestamp،
والمشروع، ومقتطفًا، والقراءة تُرقّم الأدوار صفحاتٍ. ولا يوجد إدراج
تلقائي للأرشيف في الموجّه: فيبقى الملخص هو الفهرس، ونص المحادثة هو
المصدر الذي يُرجَع إليه عند الحاجة.

وإذا لم يكن `vault.path` موجودًا أو لم يكن قابلًا للكتابة، تُعطَّل الذاكرة
مع تحذير في الدردشة و`memory.disabled` في التدقيق؛ وتستمر
المكوّنات الأخرى في العمل. وكتابات الذاكرة
خاضعة للسياسات (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.12 الإقلاع والتغليف

يُثبَّت المشروع بـ `pip install -e .` ويعلن الحزم في
`pyproject.toml`. ونقطة الدخول هي `hagar = "hagar:main"`. والإصدار
الحالي هو `0.3.0`.

والإعدادات النموذجية هي `hagar.example.yaml`؛ و`hagar.yaml` ملف
محلي متجاهَل من git. والخزنة الافتراضية في المثال هي
`./vault` ويجب إنشاؤها قبل الإقلاع.

```text
hagar --config PATH       ملف الإعدادات
hagar --model NAME        يتجاوز model.name
hagar --project NAME      يختار مشروعًا نشطًا
hagar --free              يبدأ في النشاط الحر
hagar --no-memory         يعطّل الذاكرة للجلسة
hagar --no-native-tools   يستخدم بروتوكول JSON النصي
hagar --version
```

ويُبحث عن الإعدادات بهذا الترتيب: `--config`، والمتغيّر
`HAGAR_CONFIG`، و`./hagar.yaml`. و`python -m hagar` يعمل من
مجلد المشروع.

وتشغّل CI عبر GitHub Actions المجموعة على Linux وmacOS وWindows مع
Python 3.11/3.12/3.13، وتبني sdist وwheel، وتنفّذ `twine check` و
تختبر تثبيت الـ wheel. ويبدأ سير العمل `Release` من وسم
`v*`، ويتحقق من أن الوسم يطابق إصدار الحزمة، و
ينشئ إصدار GitHub بالمخرجات.

والاختبارات المباشرة مستثناة من المجموعة العادية وتُفعَّل بـ
`--live`: فتشمل Ollama والمزوّدين البعيدين (والأخيرون فقط إذا
كان مفتاح API موجودًا).

## 3.13 الأدوات المحلية (`local_tools/`)

ليست خوادم MCP: بل مزوّدون محليون يسجّلون `ToolDefinition`
في السجل، ويعيشون خارج الـ core، في حزمة منفصلة.

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

- `clock.now` يعيد الوقت المحلي، والتاريخ، والمنطقة الزمنية، وإزاحة UTC، وepoch.
- يحوّل `calendar.date` التاريخ المحلي، أو تاريخ ISO اختياريًا، إلى
  التقويم اليولياني المُسقَط (proleptic) أو إلى التقويم الإسلامي الجدولي
  (خوارزمية الكويت). وقد يختلف التقويم الإسلامي الجدولي بيوم واحد
  عن التقاويم القائمة على الرصد أو على أم القرى.
- يعيد `think.echo` السلسلة المستلمة بالضبط؛ ويُستخدم لإخراج
  خطوة وسيطة إلى الخارج في سلاسل الاستدلال.
- يعيد `text.diff` diff موحّدًا بين نصين، بحد أقصى 20000 حرف للمدخل،
  و20000 للمخرج، و`context` من 0 إلى 10. ولا
  يطبّق الـ diff.
- يفكّك `url.parse` scheme، وhost، والمنفذ، والمسار، والاستعلام (query)، والجزء (fragment) دون
  DNS أو شبكة؛ ويحدّ الـ URL بـ 4096 حرفًا والمعاملات بـ 100. وإذا
  حوى الـ URL بيانات اعتماد، حجبها في المخرج.
- و`clock` و`calendar` و`think` و`text` و`url` لا تصل إلى نظام الملفات
  أو الشبكة، وتندرج في قاعدة `COMPUTE` allow.
- تستخدم الحاسبة قائمة بيضاء AST، لا `eval()`، مع حدود على
  التعبير، وعدد العقد، والأس.
- ينزّل `feed.read` بـ `requests` (timeout 15 ث، وبحد أقصى 5 MB)، ويقبل
  عناوين http/https فقط، ويستخدم `feedparser`؛ وسياسة `NETWORK` هي `ask`.
- SSRF: يُحلّ كل host بـ `getaddrinfo` ويجب أن يكون كل عنوان
  عالميًا؛ وتُرفض loopback، والشبكات الخاصة، وlink-local، وmulticast، و
  المحجوزة. والتحويلات (redirects) ليست تلقائية: يُعاد التحقق من كل
  `Location` وتتوقف بعد 3 قفزات. ويُرفض URL يحوي
  بيانات اعتماد.
- `permissions.network: true` لازم كي يمنح سقف النظام
  `NETWORK`؛ و`COMPUTE` دائمًا في السقف لكن السياسة يمكن أن تمنعه.
- `local_tools` معلن في `pyproject.toml` ويُثبَّت مع
  المشروع.

---

# 4. نموذج الأمان

- لا يرى الوكيل نظام الملفات الفعلي: بل مسارات محلولة داخل
  بيئة العزل فقط.
- تمر العمليات عبر `ToolRegistry` فقط؛ ولا صدفة مضيف.
- الأذونات معلنة في الإعدادات وفي السياسات، وتُطبَّق
  بواسطة بيئة العزل و`PermissionEvaluator`؛ ويمكن للجذور المتداخلة
  أن تقيّد الأذونات.
- الأخطاء بيانات: فالرفض يُعاد إلى النموذج كنتيجة
  للأداة، لا يُخفى.
- كل فعل يترك أثرًا في التدقيق، مع الجلسة والدور.

---

# 5. التطوير

- المجموعة: `./tools/run_tests.sh` (Linux/macOS) أو
  `.\tools\run_tests.ps1` (Windows). على Windows: 691 ناجحًا، و2 متجاوَز
  (الروابط الرمزية غير متاحة دون Developer Mode). وعلى Debian Linux
  (2026-11-06): جميع الاختبارات ناجحة، بما في ذلك الروابط الرمزية (693 ناجحًا، و0
  متجاوَز). والتفاصيل ومبرر الـ shim في README §3.1.
- الاختبارات المباشرة: `./tools/run_tests.sh --live` (Linux/macOS) أو
  `.\tools\run_tests.ps1 --live` (Windows) — 9 اختبارات إضافية (Ollama؛
  والمزوّدون البعيدون إن كانت المفاتيح موجودة).
- مقارنة النماذج: `python tools/bench_models.py` (README §3.5).
- مقارنة البروتوكولات: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- المجموعة العادية لا تلمس الشبكة: فـ Ollama وMCP محاكيان.

## 5.1 تعدد المنصات

- تستخدم المسارات الداخلية `pathlib.Path`؛ والمسارات المعروضة على الوكيل
  تستخدم دائمًا `/` والجذر الافتراضي `/home/ai`.
- يحوي `filesystem.sandbox` مسارات لنظام المضيف، مطلقة أو ذات
  `~` إن اختار المستخدم ذلك: و`Path.expanduser()` يحل الـ home فقط
  عندما يستخدمها المسار. ولا يُفترض وجود مجلد منزلي مخصص.
- لكل mount اسم مستعار صريح وفريد (دون تمييز بين حالة الأحرف)؛ و
  المسار الفعلي يمكن أن يكون على أي حجم (volume).
- `tools/run_tests.sh` هو مُشغّل POSIX؛ و`tools/run_tests.ps1` و
  `tools/pytest_shim` يخدمان فقط بيئة عزل Windows ذات الرمز
  المقيّد.
- الفرع الوحيد الصريح الخاص بـ Windows المتبقي هو تاريخ الإنشاء في
  `stat`: `st_birthtime` حيث يكون متاحًا، وإلا `st_ctime` على
  Windows؛ وعلى Linux قد يكون `created_at` هو `None`.
- تستخدم الـ APIs الخارجية (OAuth، وMCP، وLLM) بروتوكول HTTP و`webbrowser`، لا
  أوامر نظام.
- تغطي CI عبر GitHub Actions Linux وmacOS وWindows على Python
  3.11/3.12/3.13؛ وتبقى الروابط الرمزية، وأذونات رموز OAuth، والـ callback على loopback
  بحاجة إلى تحقق باختبارات مباشرة، لا في المجموعة غير المتصلة.

---

# 6. القيود المعروفة والدين التقني

- يغطي `PermissionEvaluator` الإصدار الأول: وتبقى الفاعلون الديناميكيون،
  وتأكيدات GUI، وقدرات MCP المعيَّنة من الإعدادات.
- يعتمد الاستدعاء الأصلي على النموذج: فبعضها يتجاهل الأدوات أو
  يعيد عدة نداءات؛ والاحتياط النصي يغطي الأخطاء، لا
  جودة الاختيار.
- يدعم عميل MCP المصادقة bearer/header وOAuth authorization code؛ ولا
  يدير device flow، ولا DPoP، ولا mTLS، ولا client assertion.
- مراجعة المهارات يدوية من CLI؛ وواجهة GUI مفقودة.
- البحث في الذاكرة بالكلمة المفتاحية، دون فهرس أو
  embedding.
- يستخدم السياق المُدرَج أدوارًا حديثة عالميًا وحتى 3 مهارات
  مؤكَّدة بالمطابقة المعجمية، دون اختيار دلالي.
- لا تحذف الذاكرة محادثات أو مهارات بسبب القِدَم: و`archive` هو
  الإزالة الوحيدة من السياق.
- للتدقيق تدوير واحتفاظ (`max_files`)، لكن لا ضغط (compaction)
  للجلسات ولا تثبيت (anchoring) خارجي لسلسلة البصمات.
- يتحقق `feed.read` من العناوين والتحويلات، لكن تبقى حالة DNS
  rebinding: فـ `requests` يحل الاسم مرة ثانية لحظة
  الاتصال؛ ويلزم resolver مثبَّت.
- الحاسبة ليست CAS (نظام جبر حاسوبي): فهي تدير تعبيرات عددية
  محدودة فقط، لا رمزية.
- `stat().created_at` هو `None` على Linux عند غياب `st_birthtime`؛ ولا
  يُختلق تاريخ إنشاء.
- لا يمكن لاسمين مستعارين أن يشيرا إلى المسار الفعلي نفسه: فالاسم المستعار
  يعرّف mount، ويجب أن يبقى المخرج الافتراضي فريدًا.

## 6.1 مسؤولية المستخدم: الروابط الصلبة، وmounts، وTOCTOU

**لا يتحكم Hagar في الروابط الصلبة (hard links)، ولا mounts/junctions، ولا تسابقات TOCTOU
داخل المجلدات المسموحة.** وليس هذا عيبًا في Hagar: فبيئة العزل
مسارية (path-based) ولا تستخدم مقابض (handles)/واصفات ملفات للعملية كلها.

والرابط الصلب اسم ثانٍ لنفس الـ inode، وليس له هدف مساري،
ولا تستطيع بيئة العزل أن تعرف هل يوجد اسم آخر في الخارج. وقد يعرض mount أو junction
نظام ملفات آخر مع بقائه داخل
بادئة المسار. وقد يغيّر تسابق TOCTOU مكوّنًا بين
فحص الروابط الرمزية والعملية الفعلية: فـ Hagar لا يستخدم `openat2`، ولا
`O_NOFOLLOW` على كل مكوّن، ولا مقابض Windows، ولذلك لا يضمن
الذرّية بين الفحص والوصول.

ولا تنشئ أدوات نظام الملفات في Hagar روابط صلبة. وإذا كان رابط صلب أو
mount موجودًا أصلًا داخل مجلد من بيئة العزل، يعامله Hagar
كملف أو مجلد عادي، ويمكنه قراءته أو تعديله أو حذف اسمه الداخلي.

ولذلك تتوزع المسؤولية:

- **يضمن Hagar** أن تبقى المسارات المحلولة داخل الاسم المستعار
  لحظة الفحص، وأن تكون الروابط الرمزية غير مرئية، وأن تُطبَّق الأذونات
  `R`/`W`/`X`، وألّا تنتهي المسارات الفعلية
  في مخرجات النموذج.
- **يضمن المستخدم** ألّا تحتوي المجلدات المضبوطة في
  `filesystem.sandbox` على روابط صلبة أو mounts أو junctions نحو
  محتويات لا يجب الوصول إليها، وألّا يستطيع أي عملية
  متزامنة غير موثوقة تعديل تلك المجلدات أثناء
  التنفيذ، إن أراد عزلًا كاملًا.

وتستلزم تسابقات TOCTOU فاعلًا محليًا متزامنًا له وصول
كتابة إلى مجلدات بيئة العزل: فهي ليست حالة عرضية
من الاستخدام الطبيعي، بل سيناريو خبيث أو بيئة مخترقة.
وللعزل القوي يلزم حجم (volume) مخصص، ومستخدم منفصل،
وmount namespace أو حاوية؛ وليس ذلك من مهام
محلّل المسارات.

والنقاط مغلقة بوصفها **مسؤولية على المستخدم**، لا ديونًا
تقنية في Hagar. فالروابط الصلبة، وmounts/junctions، وتسابقات TOCTOU غير
مكتشفة ولا محجوبة في هذا الإصدار.

---

# 7. خريطة التوثيق

- `MANUAL.md` — دليل المستخدم: الأوامر، والإعدادات، والسياسة، والافتراضيات.
- `ARCHITECTURE.md` — هذا المستند: كيف النظام اليوم.
- `ROADMAP.md` — ما يجب فعله، والقرارات المتخذة، والنقاط المفتوحة.
- `CHANGELOG.md` — تاريخ الإصدارات.
- `README.md` — الإقلاع، والإعدادات، والاختبارات.
