# HAGAR — دليل المستخدم

الإصدار: **0.3.0**

يصف هذا الدليل السلوك القابل للملاحظة في Hagar: الأوامر،
والخيارات، والإعدادات، والسياسات، وحالات الخطأ. وللاطلاع على المشروع الداخلي
راجع [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

# 1. البدء السريع

المتطلبات: Python 3.11 أو أحدث.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

cp hagar.example.yaml hagar.yaml
mkdir -p vault logs

hagar --config hagar.yaml
```

على Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item hagar.example.yaml hagar.yaml
New-Item -ItemType Directory -Force vault, logs
hagar --config hagar.yaml
```

`hagar.yaml` و`testvault/` و`logs/` ملفات محلية ولا يجب إدراجها في نظام إدارة الإصدارات.

## 1.1 ترتيب الإقلاع

1. يقرأ Hagar الإعدادات.
2. يحمّل `policy.yaml`؛ فإن لم يكن صالحًا، يطبّق `DENY` على كل شيء.
3. يبني عميل LLM.
4. يهيّئ الخزنة والذاكرة، إن كانتا مضبوطتين.
5. يبني بيئة العزل الخاصة بنظام الملفات.
6. يسجّل الأدوات المحلية.
7. يحاول تحميل خوادم MCP؛ وخادم فاشل لا يوقف الآخرين.
8. يعرض اختيار المشروع.
9. يدخل حلقة الدردشة.

---

# 2. أوامر الدردشة

تبدأ الأوامر بـ `/`. والأمر غير المعروف **لا يُرسَل إلى
النموذج**: يرد Hagar بـ `Comando sconosciuto` («أمر غير معروف») ويقترح `/help`.

## 2.1 الأوامر العامة

| الأمر | السلوك |
|---|---|
| `/help` أو `/?` | يسرد الأوامر المتاحة |
| `/tools [categoria]` | يسرد الأدوات والقدرات؛ والفلتر اختياري |
| `/status` | يعرض النموذج، والمشروع، والذاكرة، والتدقيق، وبيئة العزل |
| `/mcp` | يسرد خوادم MCP ونقاط النهاية والأدوات المستوردة |
| `/audit [n]` | يعرض آخر `n` حدثًا؛ الافتراضي 10، والحد الأقصى 50 |
| `exit` | يخرج |
| `quit` | يخرج |
| `Ctrl-D` | يخرج |
| `Ctrl-C` | يقاطع؛ وأثناء OAuth يخرج بالرمز 130 |

`/status` و`/audit` أمران بشريان: لا يمرّان عبر النموذج ولا
يستهلكان نداءات أدوات.

## 2.2 المشروع

| الأمر | السلوك |
|---|---|
| `/project` أو `/project list` أو `/project ls` | يسرد المشاريع النشطة |
| `/project new <nome>` | ينشئ مشروعًا ويختاره |
| `/project select <id>` أو `/project use <id>` | يختار مشروعًا نشطًا |
| `/project free` أو `/project none` | ينتقل إلى النشاط الحر |
| `/project status` أو `/project current` | يعرض المشروع الحالي |
| `/project archive <id>` | يؤرشف مشروعًا |
| `/project unarchive <id>` | يعيد تنشيط مشروع مؤرشف |
| `/project help` | مساعدة |

يستخدم `select` و`archive` **المعرّف** (id) الخاص بالمشروع، لا عنوانه.

في النشاط الحر لا تُقرأ ولا تُكتب ذاكرة المشروع؛ وتبقى الدردشة،
والملخص، والمهارات متاحة.

## 2.3 الذاكرة

| الأمر | السلوك |
|---|---|
| `/memory` أو `/memory help` أو `/memory ?` | مساعدة |
| `/memory list [candidate\|confirmed\|archived]` | يسرد المهارات والأعداد |
| `/memory show <slug>` | يعرض مهارة |
| `/memory review` | مراجعة تفاعلية للمرشحات |
| `/memory confirm <slug>` | يؤكّد مهارة |
| `/memory archive <slug>` | يؤرشف مهارة |
| `/memory archive search <testo>` | يبحث في نصوص المحادثات المؤرشفة |
| `/memory archive read <session> [offset] [limit]` | يقرأ نص محادثة مؤرشفًا |

الكلمتان `search` و`read` محجوزتان: فلا يمكن أرشفة مهارة يحمل
معرّفها (slug) بالضبط `search` أو `read` بهذا الأمر.

لا يوجد أمر للحذف: الأرشفة فقط.

## 2.4 ما ليس أمرًا

الأدوات (`filesystem.*`، `memory.*`، `mcp.*`، `clock.now`، ...) يستدعيها
النموذج عبر السجل (registry). ولا تُكتب يدويًا مثل `/tool`.
والاستثناء الوحيد هو الأوامر الإعلامية `/tools`، و`/status`، و`/mcp`،
و`/audit`، فهي أوامر طرفية وليست أدوات.

---

# 3. سطر الأوامر

```text
hagar [opzioni]
```

| الخيار | الأثر |
|---|---|
| `--config PATH` | يستخدم ملف إعدادات صريحًا |
| `--model NAME` | يتجاوز `model.name` |
| `--project NAME` | يختار مشروعًا نشطًا عند الإقلاع |
| `--free` | يبدأ في النشاط الحر |
| `--no-memory` | يعطّل الذاكرة والمشاريع للجلسة |
| `--no-native-tools` | يفرض بروتوكول JSON النصي |
| `--version` | يطبع الإصدار |

`--project` و`--free` متنافيان.

## 3.1 البحث عن الإعدادات

الترتيب:

1. `--config PATH`
2. المتغيّر `HAGAR_CONFIG`
3. `./hagar.yaml` في المجلد الحالي

المسارات النسبية داخل `hagar.yaml` — التدقيق، والسياسة، والخزنة — تُحلّ
نسبةً إلى مجلد ملف الإعدادات، لا إلى المجلد الذي تُشغّل منه
Hagar.

## 3.2 رموز الخروج

| الرمز | المعنى |
|---|---|
| `0` | خروج طبيعي أو `--version` |
| `1` | خطأ في الإعدادات أو مشروع غير صالح |
| `130` | مقاطعة بـ Ctrl-C |

خطأ MCP لا يغيّر رمز الخروج: يُسجَّل ويستمر
إطار التشغيل.

---

# 4. `hagar.yaml`

مثال أدنى:

```yaml
model:
  provider: ollama
  name: llama3.1:latest

vault:
  path: ./vault

filesystem:
  sandbox:
    - alias: workspace
      path: .
      permissions: RX
```

## 4.1 `model`

| الحقل | الافتراضي | ملاحظات |
|---|---|---|
| `provider` | إلزامي | `ollama`، `deepseek`، `claude`، `gemini` |
| `name` | إلزامي | اسم النموذج لدى المزوّد |
| `host` | افتراضي المزوّد | عنوان URL الأساسي لواجهة API |
| `native_tools` | `true` | إذا كان `false`، يستخدم بروتوكول JSON النصي |
| `max_tokens` | `1024` | يستخدمه Claude فقط |
| `api_key_env` | الاسم القياسي | متغيّر البيئة الخاص بالمفتاح |

المزوّدون والمفاتيح:

| المزوّد | المفتاح القياسي |
|---|---|
| `ollama` | لا يوجد |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `claude` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |

لا تُكتب المفاتيح أبدًا في YAML. وإذا كان مفتاح ما مفقودًا، فلا
يُبنى العميل ويفشل الإقلاع بخطأ صريح.

مع تفعيل الاستدعاء الأصلي، يستخدم Hagar الأدوات المهيكلة
الخاصة بالمزوّد. وإذا رفض المزوّد المخطط (HTTP 400/404/422)، ينتقل عند الخطوة
الأولى إلى بروتوكول JSON النصي لتلك الجلسة. ويغطي الاحتياط
الخطأ التقني، لكنه لا يضمن أن يختار النموذج الأداة اختيارًا جيدًا.

## 4.2 `audit`

```yaml
audit:
  enabled: true
  path: logs/audit.jsonl
  max_field_chars: 2000
  max_bytes: 5000000
  max_files: 100
  include_outputs: true
```

| الحقل | الافتراضي | الأثر |
|---|---|---|
| `enabled` | `true` | يفعّل/يعطّل السجل |
| `path` | `logs/audit.jsonl` | ملف JSON Lines |
| `max_field_chars` | `2000` | يقتطع الحقول |
| `max_bytes` | `5000000` | عتبة التدوير |
| `max_files` | `100` | عدد الملفات المدوّرة التي تُحفظ |
| `include_outputs` | `true` | إذا كان `false`، يحجب مخرجات الأدوات |

يحتوي التدقيق على بيانات حساسة: مخرجات الملفات، والردود، والنصوص. ويجب
حمايته كمساحة العمل. ويعرض `/audit` أحداث الملف الحالي فقط، لا
الملفات المدوّرة.

الأحداث الرئيسية: `harness.start`، `turn.start`، `llm.tool_choice`،
`tool.call`، `tool.result`، `turn.answer`، `permission.decision`،
`permission.confirmation`، `memory.*`، `mcp.loaded`، `mcp.failed`،
`harness.stop`.

## 4.3 `policy`

```yaml
policy:
  path: policy.yaml
  subject: assistant
```

`path` نسبي إلى الإعدادات. وإذا كان الملف غير قابل للقراءة أو غير
صالح:

- تصبح كل السياسات `DENY`؛
- يُسجَّل `policy.failed`؛
- يبقى Hagar مُقلعًا، لكن لا تُنفَّذ أي أداة؛
- تعرض الطرفية `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

هو جذر الذاكرة بصيغة Markdown. ويجب أن يكون موجودًا وقابلًا للكتابة.
وإن كان مفقودًا أو غير قابل للكتابة، تُعطَّل الذاكرة مع تحذير؛
ويستمر بقية إطار التشغيل.

## 4.5 `memory`

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

| الحقل | الافتراضي | الأثر |
|---|---|---|
| `enabled` | `true` | يفعّل الذاكرة |
| `vault_subdir` | `Hagar` | مجلد فرعي داخل الخزنة |
| `context_turns` | `10` | الأدوار الأخيرة المُدرَجة؛ `0` يعطّل |
| `context_skills` | `3` | المهارات المؤكَّدة المُدرَجة |
| `context_project_memories` | `10` | عناوين القرارات النشطة |
| `max_context_chars` | `6000` | ميزانية كتلة الذاكرة |
| `project_max_active` | `200` | عتبة صيانة المشروع |
| `summary_max_chars` | `4000` | الطول الأقصى للملخص |
| `max_skill_chars` | `4000` | الطول الأقصى للمهارة الواحدة |

يجب أن يبقى `vault_subdir` داخل الخزنة: فالمسارات المطلقة، و`..`،
و`I:/...`، ومحركات أقراص Windows الأخرى تُرفض حتى على Linux.

الميزانية بـ **الأحرف**، لا بالرموز (tokens). وعند اقتطاع الكتلة،
يسجّل التدقيق `memory.context_trimmed`.

## 4.6 `filesystem`

```yaml
filesystem:
  sandbox:
    - alias: documenti
      path: C:\Users\pippo\Documenti
      permissions: RWX
  limits:
    max_write_bytes: 0
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

كل مدخلة:

| الحقل | إلزامي | ملاحظات |
|---|---|---|
| `alias` | نعم | مقطع واحد فقط، وفريد دون تمييز بين حالة الأحرف |
| `path` | نعم | مجلد موجود في نظام المضيف |
| `permissions` | لا | الافتراضي `R`؛ والحروف `R`، `W`، `X` |

الأذونات:

| الحرف | يغطي |
|---|---|
| `R` | القراءة، والسرد، والبحث، و`stat` |
| `W` | الكتابة، والإنشاء، وإعادة التسمية، والنسخ، والحذف |
| `X` | `chdir` إلى المجلد |

يرى الوكيل `/home/ai/<alias>/...`. ويسرد `/home/ai` الأسماء المستعارة، لكنه
ليس مجلدًا فعليًا ولا يمكن الدخول إليه بـ `chdir`.

القيود:

- الأسماء المستعارة والمسارات المكررة توقف الإعدادات؛
- المسار المفقود يوقف الإعدادات؛
- يمكن أن تحتوي المسارات الفعلية على مسافات؛ أما الأسماء المستعارة فلا؛
- لا ينشئ Hagar مجلدات بيئة العزل ولا يفترض وجود مجلد منزلي مخصص.

حدود الكتابة:

| الحقل | الأثر |
|---|---|
| `max_write_bytes` | الحد الأقصى لكل عملية واحدة |
| `min_free_bytes` | الحد الأدنى للمساحة الحرة المتبقية |
| `session_write_bytes` | الحد الأقصى التراكمي للجلسة |
| `ask_over_bytes` | فوق هذه العتبة يطلب تأكيدًا |

`0` يعطّل الحد الواحد. والحدود ثوابت (invariants): فتجاوزها
خطأ في الأداة، لا تحذير.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
```

هي **سقف النظام**. الافتراضي: `read=true`، والبقية `false`.

| الحقل | يمنح |
|---|---|
| `read` | قراءة نظام الملفات، وقراءة الذاكرة |
| `write` | الكتابة/الإنشاء/الحذف في نظام الملفات، والكتابة في الذاكرة |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |

`COMPUTE` و`MCP_CALL` موجودان دائمًا في السقف، لكن السياسة يمكن أن تمنعهما.
وإذا لم يمنح السقف قدرة ما، فلا يمكن للسياسة أن تمنحها.

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

القيمة المتوقعة للاسترجاع الوثائقي. ولا تغيّر سياق
الذاكرة في هذا الإصدار.

## 4.9 `mcp_servers`

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer
      token_env: MCP_EXAMPLE_TOKEN
```

الحقول:

| الحقل | ملاحظات |
|---|---|
| `endpoint` | عنوان URL الخاص بالخادم MCP بصيغة HTTP/JSON-RPC |
| `namespace` | بادئة الأدوات المستوردة: `mcp.<namespace>.*` |
| `auth` | اختياري: `bearer` أو `header` أو `oauth` |

Bearer/header:

```yaml
auth:
  type: header
  header: Authorization
  token_env: ATLASSIAN_BASIC
```

تُرسَل القيمة المقروءة من البيئة **كما هي**: فبالنسبة إلى Basic
يجب أن تكون أصلًا `Basic <base64>`، لا الرمز وحده.

OAuth:

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    client_id: ...
    client_secret_env: MCP_CLIENT_SECRET
    scopes: [read:me, offline_access]
    audience: api.atlassian.com
    redirect_port: 8765
    token_cache: .hagar/oauth/example.json
    timeout: 300
```

التدفق هو authorization code + PKCE مع callback محلي
`http://localhost:<port>/oauth/callback`. وإذا كان `client_id` مفقودًا، يُحاوَل
التسجيل الديناميكي. ومع `offline_access` يُضاف
`prompt=consent`. والرموز (tokens) في ملف محلي مقيّد وتُجدَّد
تلقائيًا.

إذا فشل خادم MCP:

- يُسجَّل `mcp.failed`؛
- يُتجاوز الخادم؛
- تستمر الخوادم الأخرى وبقية إطار التشغيل؛
- يعرض `/mcp` صفر أدوات لذلك الفضاء الاسمي.

---

# 5. `policy.yaml`

مثال:

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
        tools: ["filesystem.*"]

      - capabilities: [COMPUTE]
        effect: allow
        tools: ["calculator.*", "statistics.*", "units.*",
                "clock.*", "calendar.*", "think.*", "text.*", "url.*"]

      - capabilities: [MCP_CALL]
        effect: ask
        tools: ["mcp.*"]

      - capabilities: [MEMORY_READ]
        effect: allow
        tools: ["memory.*"]

      - capabilities: [MEMORY_WRITE]
        effect: ask
        tools: ["memory.*"]
```

## 5.1 الآثار

| الأثر | المعنى |
|---|---|
| `allow` | يمكن تنفيذ الأداة |
| `ask` | يلزم تأكيد بشري |
| `deny` | لا تُنفَّذ الأداة |

ترتيب الشدة: `DENY > ASK > ALLOW`. وعند طلب أكثر من قدرة
يسري منطق AND: فيفوز الأثر الأسوأ.

`ASK` دون قناة تأكيد يكافئ `DENY`. والتأكيد من الطرفية
يعرض `lo faccio? (y/N)` والقيمة الافتراضية هي `N`.

## 5.2 القدرات

| الاسم | الاستخدام |
|---|---|
| `FILESYSTEM_READ` | القراءة، والسرد، والبحث، وstat |
| `FILESYSTEM_WRITE` | التعديل |
| `FILESYSTEM_CREATE` | الإنشاء، والنسخ، وإعادة التسمية في الوجهة |
| `FILESYSTEM_DELETE` | الحذف |
| `FILESYSTEM_EXEC` | الدخول/التنفيذ داخل بيئة العزل |
| `MEMORY_READ` | قراءة الذاكرة |
| `MEMORY_WRITE` | كتابة الذاكرة |
| `NETWORK` | الوصول إلى الشبكة |
| `MCP_CALL` | نداء أداة MCP |
| `COMPUTE` | حساب محلي دون شبكة أو نظام ملفات |

## 5.3 القواعد والخصوصية

يمكن للقاعدة أن تفلتر بـ:

- `tools`: نمط glob على الاسم (`filesystem.*`، `mcp.atlassian.*`)؛
- `paths`: بادئات على المسار الذي يكتبه النموذج؛
- `namespaces`: بادئات على الفضاء الاسمي.

تفوز القاعدة الأكثر خصوصية: أولًا عدد الفلاتر، ثم
طول البادئة. وعند التساوي يفوز الأثر الأكثر تقييدًا.
وبدون قواعد يسري `default` الخاص بالفاعل؛ والافتراضي الآمن هو `deny`.

يقارن نطاق `paths` المسار **الذي يكتبه النموذج**، لا المسار
المحلول بعد `chdir`: فالمسار المطلق أو تغيير المجلد قد لا
يتطابق وينتج `DENY` (الفشل إلى الرفض، fail closed).

## 5.4 الأخطاء

إذا كان `policy.yaml` غير صالح، أو كانت قدرة ما مفقودة، أو كان الفاعل
غير موجود:

- يطبّق Hagar `DENY` على كل السياسات؛
- يسجّل `policy.failed`؛
- يعرض تحذيرًا؛
- لا ينفّذ أي أداة.

---

# 6. السلوكيات الافتراضية

| الحالة | السلوك |
|---|---|
| لا يوجد `hagar.yaml` | خطأ في الإعدادات، خروج بالرمز 1 |
| YAML غير صالح | خطأ في الإعدادات، خروج بالرمز 1 |
| سياسة غير صالحة | DENY كامل، إطار التشغيل مُقلع |
| الخزنة غائبة/غير قابلة للكتابة | الذاكرة معطّلة، إطار التشغيل مُقلع |
| `projects` غير قابل للكتابة | المشاريع معطّلة، الذاكرة نشطة |
| لا مشروع نشط | نشاط حر |
| إقلاع غير تفاعلي | نشاط حر، ما لم يُحدَّد `--project`/`--free` |
| `--project` غير موجود | خطأ، خروج بالرمز 1 |
| خادم MCP غير قابل للوصول | `mcp.failed`، يُتجاوز الخادم |
| النموذج/Ollama غير قابل للوصول | خطأ في الدور، ويبقى إطار التشغيل نشطًا |
| مفتاح API مفقود | لا يُبنى العميل، خطأ عند الإقلاع |
| أداة ممنوعة | نتيجة خطأ إلى النموذج، دون تنفيذ |
| أداة في `ASK` دون تأكيد | رفض |
| تجاوز حد الكتابة | خطأ في الأداة، دون كتابة |
| ملف يتجاوز 4096 بايت مع `read_file` | خطأ، استخدم `read_chunk` |
| صفحة تتجاوز الحد | `has_more`/`next_offset` |
| رابط رمزي (symlink) | غير مرئي؛ العملية كمسار غير موجود |
| رابط صلب/mount/junction | لا تُكتشف؛ المسؤولية على المستخدم |
| تسابق TOCTOU | غير مراقَب؛ المسؤولية على المستخدم |
| الذاكرة غائبة أثناء الدور | `memory.failed`، ويستمر الدور |
| نهاية الجلسة مع وجود أدوار | ملخص، وأرشفة، ومراجعة المشروع |
| مراجعة مرفوضة | قرارات مرشحة مع `auto_saved: true` |
| مشروع يتجاوز `project_max_active` | طلب أرشفة |
| Ctrl-C أثناء OAuth | إغلاق الـ callback، خروج 130 |
| أمر `/` غير معروف | رسالة، ولا يُرسَل إلى النموذج |

## 6.1 نهاية الجلسة

عند الخروج، إذا كانت الذاكرة نشطة وهناك أدوار:

1. يُنقل نص المحادثة إلى `archive/chat/`؛
2. يُولَّد ملخص (بواسطة LLM، مع احتياط ميكانيكي)؛
3. يُحفظ الملخص مع رابط وبصمة (hash)؛
4. إن كان هناك مشروع، يقترح النموذج قرارات مرشحة؛
5. يمكن للمستخدم مراجعتها؛ فإن رفض بقيت مرشحة.

وإذا لم تكن هناك أدوار، فلا يُنشأ أي ملخص.

## 6.2 ما لا يفعله Hagar

- لا ينفّذ أوامر صدفة؛
- لا يعطي النموذج مسارات فعلية؛
- لا يضمن عزلًا على مستوى نظام التشغيل: فبيئة العزل مسارية (path-based)؛
- لا يتحكم في الروابط الصلبة أو mounts أو junctions أو TOCTOU؛
- لا يحذف محادثات أو مهارات بسبب القِدَم؛
- لا يشفّر الخزنة؛
- لا يرقّي تلقائيًا مهارة أو قرارًا إلى حقيقة.

---

# 7. الأمان التشغيلي

- النموذج غير موثوق: السياسات والتأكيدات هي أدوات التحكم.
- الخزنة Markdown بنص صريح: قد تحتوي محادثات وقرارات.
- التدقيق قد يحتوي مخرجات ملفات: ويجب حمايته.
- مفاتيح API موجودة في البيئة فقط.
- رموز MCP/OAuth في ذاكرات تخزين مؤقت محلية بأذونات مقيّدة.
- لا تعرض Ollama أو LM Studio على الشبكة بلا ضرورة.
- قد يكشف رابط صلب أو mount داخل مجلد مسموح محتويات
  خارجية: وHagar لا يكتشفها.

---

# 8. استكشاف الأخطاء وإصلاحها

| العَرَض | الفحص |
|---|---|
| `Policy: DENY ALL` | التحقق من صلاحية `policy.yaml` و`policy.path` |
| `Memory: disabled` | هل `vault.path` موجود؟ هل هو قابل للكتابة؟ |
| `Projects: disabled` | هل `vault.path/Hagar/projects` موجود؟ |
| `Failed to load MCP server` | نقطة النهاية، والرمز، و`/mcp` |
| `MCP auth token missing` | المتغيّر المشار إليه في `token_env` |
| `MCP HTTP 401` | بيانات الاعتماد/ترويسة Basic أو OAuth |
| `MCP HTTP 400` | البروتوكول، أو الجلسة، أو معاملات الخادم |
| `read_file` كبير جدًا | استخدم `read_chunk` |
| `PermissionError` | السياسة، وأذونات `R/W/X`، ومسار خارج بيئة العزل |
| أداة غير مسرودة | خادم MCP فاشل أو أداة غير مسجّلة |
| أمر غير معروف | `/help` |

في حال خطأ في الإعدادات، يخرج Hagar بالرمز 1 ويطبع
التفاصيل على stderr. وفي حال خطأ في الدور، يتلقى النموذج
نتيجة الأداة، ويحتفظ التدقيق بالحدث.
