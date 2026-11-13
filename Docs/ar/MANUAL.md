# HAGAR — دليل المستخدم

الإصدار: **0.7.0**

يصف هذا الدليل السلوك الملاحَظ لـ Hagar: الأوامر،
والخيارات، والإعدادات، والسياسات، وحالات الخطأ. وبالنسبة للتصميم الداخلي
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

الملفات `hagar.yaml` و`testvault/` و`logs/` محلية ولا ينبغي إدراجها في نظام إدارة الإصدارات.

## 1.1 ترتيب الإقلاع

1. يقرأ Hagar الإعدادات.
2. يحمّل `policy.yaml`؛ وإن لم يكن صالحًا، يطبّق `DENY` على كل شيء.
3. يبني عميل الـ LLM.
4. يهيّئ الـ Vault والذاكرة، إن كانا مُعدَّين.
5. يبني صندوق الرمل (sandbox) لنظام الملفات.
6. يسجّل الأدوات المحلية.
7. يحاول تحميل خوادم MCP؛ وفشل خادم واحد لا يوقف الآخرين.
8. يعرض اختيار المشروع.
9. يدخل حلقة المحادثة.

---

# 2. أوامر المحادثة

تبدأ الأوامر بـ `/`. الأمر غير المعروف **لا يُرسَل إلى
النموذج**: يرد Hagar بـ `Comando sconosciuto` ويقترح `/help`.

## 2.1 الأوامر العامة

| الأمر | السلوك |
|---|---|
| `/help` أو `/?` | يسرد الأوامر المتاحة |
| `/tools [categoria]` | يسرد الأدوات والقدرات؛ التصفية اختيارية |
| `/status` | يعرض النموذج والمشروع والذاكرة والتدقيق وصندوق الرمل |
| `/usage` | يعرض الرموز المستهلكة في الجلسة |
| `/models ...` | بطاقات ومعايير قياس وعتاد خاص بالوسيط (broker) |
| `/models hardware` | يكتشف المعالج والذاكرة العشوائية ووحدة معالجة الرسوميات في الجهاز |
| `/undo` | يلغي تعديلات الدور الأخير |
| `/mcp` | يسرد خوادم MCP ونقاط النهاية والأدوات المستوردة |
| `/audit [n]` | يعرض آخر `n` حدثًا؛ الافتراضي 10 والحد الأقصى 50 |
| `exit` | يخرج |
| `quit` | يخرج |
| `Ctrl-D` | يخرج |
| `Ctrl-C` | يقاطع؛ وأثناء OAuth يخرج بالرمز 130 |

الأمران `/status` و`/audit` موجَّهان للإنسان: لا يمرّان عبر النموذج ولا
يستهلكان استدعاءات أدوات.

## 2.2 المشروع

| الأمر | السلوك |
|---|---|
| `/project` أو `/project list` أو `/project ls` | يسرد المشاريع النشطة |
| `/project new <nome>` | ينشئ مشروعًا ويحدده |
| `/project select <id>` أو `/project use <id>` | يحدد مشروعًا نشطًا |
| `/project free` أو `/project none` | ينتقل إلى النشاط الحر |
| `/project status` أو `/project current` | يعرض المشروع الحالي |
| `/project archive <id>` | يؤرشف مشروعًا |
| `/project unarchive <id>` | يعيد تنشيط مشروع مؤرشف |
| `/project help` | مساعدة |

يستخدم `select` و`archive` **معرّف** المشروع، لا عنوانه.

في النشاط الحر لا تُقرأ ولا تُكتب ذاكرة المشروع؛ أما المحادثة
والملخص والمهارات فتبقى متاحة.

## 2.3 الذاكرة

| الأمر | السلوك |
|---|---|
| `/memory` أو `/memory help` أو `/memory ?` | مساعدة |
| `/memory list [candidate\|confirmed\|archived]` | يسرد المهارات والأعداد |
| `/memory show <slug>` | يعرض مهارة |
| `/memory search <testo>` | يبحث في ذكريات SQLite |
| `/memory sessions` | يسرد المحادثات المسجَّلة |
| `/memory chat <session>` | يعرض أدوار محادثة |
| `/memory reindex` | يحسّن/يعيد بناء فهارس SQLite |
| `/memory stats` | حالة قاعدة البيانات وأعدادها |
| `/memory backup <path>` | نسخة متسقة من قاعدة البيانات |
| `/memory export <path> [--force]` | يصدّر المحادثات والمهارات والملخصات والمشاريع إلى Markdown |
| `/memory import <path> [--force]` | يستورد بنية Markdown إلى قاعدة البيانات |
| `/memory review` | مراجعة تفاعلية للمهارات المرشحة |
| `/memory confirm <slug>` | يؤكد مهارة |
| `/memory archive <slug>` | يؤرشف مهارة |
| `/memory archive search <testo>` | يبحث في النصوص المؤرشفة |
| `/memory archive read <session> [offset] [limit]` | يقرأ نصًا مؤرشفًا |

الكلمتان `search` و`read` محجوزتان: فلا يمكن أرشفة مهارة اسمها
بالضبط `search` أو `read` بهذا الأمر.

لا يوجد أمر حذف: فالأرشفة فقط.

الواجهة الخلفية الافتراضية هي SQLite (`memory.backend: sqlite`). وتقع قاعدة
البيانات في البيانات المحلية للتطبيق، لا في الـ Vault:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

أو `HAGAR_MEMORY_DB`. وتبقى الواجهة الخلفية `markdown` للتوافق
فقط. ولم يعد الـ Vault يُحدَّث من الواجهة الخلفية SQLite.

## 2.4 ما ليس أمرًا

الأدوات (`filesystem.*`، `memory.*`، `mcp.*`، `clock.now`، ...) يستدعيها
النموذج عبر السجل (registry). ولا تُكتَب كـ `/tool`.
والاستثناء الوحيد هو الأوامر المعلوماتية `/tools` و`/status` و`/models` و`/mcp`
و`/audit`، وهي أوامر طرفية وليست أدوات.

---

# 3. سطر الأوامر

```text
hagar [opzioni]
hagar web [opzioni]
```

| الخيار | التأثير |
|---|---|
| `--config PATH` | يستخدم ملف إعدادات صريحًا |
| `--model NAME` | يتجاوز `model.name` |
| `--project NAME` | يحدد مشروعًا نشطًا عند الإقلاع |
| `--free` | يبدأ في النشاط الحر |
| `--no-memory` | يعطّل الذاكرة والمشاريع للجلسة |
| `--no-native-tools` | يفرض بروتوكول JSON النصي |
| `--hifi` | يفعّل مرحلة ما قبل التفسير والتوضيح |
| `--host HOST` | مضيف واجهة الويب (الافتراضي `127.0.0.1`) |
| `--port PORT` | منفذ واجهة الويب (الافتراضي `8765`) |
| `--version` | يطبع الإصدار |

الخياران `--project` و`--free` متعارضان.

## 3.0 واجهة الويب

```bash
hagar web
hagar --config hagar.yaml web --port 8765
```

يفتح واجهة محلية على `http://127.0.0.1:8765/`.

- الخادم مصمَّم لمستخدم محلي واحد: الافتراضي `127.0.0.1`.
- يتلقى المتصفح رمزًا عشوائيًا في الصفحة؛ وتطلبه الـ API
  في ترويسة `X-Hagar-Token`.
- تعرض المحادثة الأدوار واستدعاءات الأدوات والنتائج وتأكيدات ASK.
- في الأعلى توجد تبويبات **Chat** و**Chat history** و**Tool output**
  و**Audit** و**Thinking**.
- يسرد **Chat history** المحادثات السابقة، سطرًا لكل محادثة؛ ونقرة واحدة
  تستأنف المحادثة: فيُعاد تحميل النص من قاعدة البيانات وتُضاف الأدوار
  الجديدة إلى الجلسة نفسها.
- يفتح زر **+ Nuova chat** جلسة جديدة ويصفّر
  السياق؛ وتبقى المحادثة السابقة في السجل.
- **Memories** متصفح للقراءة فقط للملاحظات المفهرسة
  (المهارات والمشاريع والقرارات)؛ ويتيح البحث وفتح النص.
- يعرض **Tool output** استدعاءات الأدوات ونتائج الجلسة.
- يعرض **Audit** أحداث السجل؛ وإذا كان التدقيق معطَّلًا فالتبويب
  معطَّل ويعرض `audit off`.
- يعرض **Thinking** الاستدلال الذي يكشفه المزوّد، إن وُجد؛ وإلا
  فيعرض الخط الزمني لأحداث الوكيل.
- تعرض **Memories** ذكريات قاعدة البيانات ومهاراتها للقراءة فقط، مع البحث.
- يوقف زر **Stop** الدور على نحو تعاوني.
- يرفق زر **Immagine** ملفات PNG/JPEG/WebP (بحد أقصى 4، و10 MB لكل منها)
  للنماذج البصرية. ويُحوَّل WebP إلى PNG في الواجهة لأن LM
  Studio لا يقبله مباشرة. ولا تُحفظ الصور
  في الذاكرة ولا في التدقيق: فيصل إلى النموذج data URL، لا
  مسار المضيف.
- يعرض الشريط الجانبي في الأسفل الرموز المتراكمة للجلسة: الإدخال
  والإخراج والإجمالي.
- يمكن للنموذج تحميل صور من صندوق الرمل عبر `vision.open`؛
  فتُرفَق الصورة بالدور، ولا تُعاد كـ base64 في
  السياق.
- تأكيدات ASK نمطية: يبقى الدور في انتظار ويستمر الخادم
  في الاستجابة. والمهلة تعادل الرفض. وتعرض طلبات
  الوكلاء الفرعيين `agent_id` و`parent_id`؛ ولا يستطيع الـ LLM الأب
  الموافقة عليها. ومهلة الوكيل الفرعي 180 ثانية.
- في الـ CLI يملك خيط واحد فقط الإدخال. وعندما يكون تأكيد نشطًا،
  يطلب عنوان الطرفية الانتباه وتُقبل `F5` =
  allow، و`F8` = deny، إضافة إلى `y/N`. وإذا لم تدعم الطرفية مفاتيح
  الوظائف، فتبقى `y/N` والواجهة الرسومية.
- يؤدي Ctrl-C في الـ CLI إلى استعادة الوضع الطبيعي للطرفية قبل
  الخروج.
- الواجهة ليست بعد متعددة المستخدمين ولا تتيح تعديلات مباشرة على الذاكرة.
- يغلق Ctrl-C الخادم ويحاول إنهاء الجلسة.

لا تستخدم `--host 0.0.0.0` على شبكة غير موثوقة: فالواجهة تعرض أدوات
الـ harness لكل من يستطيع الوصول إلى المنفذ.

## 3.1 البحث عن الإعدادات

الترتيب:

1. `--config PATH`
2. المتغير `HAGAR_CONFIG`
3. `./hagar.yaml` في المجلد الحالي

تُحل المسارات النسبية داخل `hagar.yaml` — التدقيق والسياسة والـ Vault — بالنسبة إلى
مجلد ملف الإعدادات، لا بالنسبة إلى المجلد الذي تشغّل منه Hagar.

## 3.2 رموز الخروج

| الرمز | المعنى |
|---|---|
| `0` | خروج طبيعي أو `--version` |
| `1` | خطأ في الإعدادات أو مشروع غير صالح |
| `130` | مقاطعة بـ Ctrl-C |

خطأ MCP لا يغيّر رمز الخروج: بل يُسجَّل ويستمر
الـ harness.

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
| `provider` | إلزامي | `ollama`، `lmstudio`، `deepseek`، `openai` (`chatgpt`)، `claude`، `gemini` |
| `name` | إلزامي | اسم النموذج لدى المزوّد |
| `host` | افتراضي المزوّد | عنوان URL الأساسي للـ API |
| `native_tools` | `true` | إذا كان `false`، يستخدم بروتوكول JSON النصي |
| `max_tokens` | `1024` | يستخدمه Claude فقط |
| `timeout` | `120` | مهلة HTTP بالثواني لكل استدعاء |
| `api_key_env` | الاسم القياسي | متغير البيئة الخاص بالمفتاح |

المزوّدون والمفاتيح:

| المزوّد | المفتاح القياسي | الافتراضي |
|---|---|---|
| `ollama` | لا شيء | `http://localhost:11434` |
| `lmstudio` | لا شيء، اختياري `LMSTUDIO_API_KEY` | `http://localhost:1234/v1` |
| `deepseek` | `DEEPSEEK_API_KEY` | API DeepSeek |
| `openai` / `chatgpt` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `claude` | `ANTHROPIC_API_KEY` | API Anthropic |
| `gemini` | `GEMINI_API_KEY` | API Gemini |

لا ينبغي أبدًا كتابة المفاتيح في YAML. وإذا غاب مفتاح، فلا يُبنى العميل
ويفشل الإقلاع بخطأ صريح. ولا يتطلب LM Studio
مفتاحًا، إلا إذا كان الخادم المحلي مُعدًّا لطلبه.
و`chatgpt` اسم بديل لـ `openai`: فاشتراك ChatGPT لا
يمنح الوصول إلى الـ API، بل تحتاج إلى مفتاح OpenAI ورصيد API.

مع LM Studio يعتمد استدعاء الأدوات الأصلي على النموذج وقالبه.
وإذا قبل النموذج الطلب لكنه ردّ بنص بدلًا من
إصدار `tool_calls`، فلا يستطيع Hagar تنفيذ الأداة: استخدم
`model.native_tools: false` أو نموذجًا قادرًا على استخدام الأدوات.

مع تفعيل الاستدعاء الأصلي، يستخدم Hagar الأدوات المهيكلة التي يوفرها
المزوّد. وإذا رفض المزوّد المخطط (HTTP 400/404/422)، ينتقل عند الخطوة الأولى
إلى بروتوكول JSON النصي لتلك الجلسة. ويغطي هذا التراجع
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

| الحقل | الافتراضي | التأثير |
|---|---|---|
| `enabled` | `true` | يفعّل/يعطّل السجل |
| `path` | `logs/audit.jsonl` | ملف JSON Lines |
| `max_field_chars` | `2000` | يقتطع الحقول |
| `max_bytes` | `5000000` | عتبة التدوير |
| `max_files` | `100` | عدد الملفات المدوَّرة المحتفظ بها |
| `include_outputs` | `true` | إذا كان `false`، يحجب مخرجات الأدوات |

يحتوي التدقيق على بيانات حساسة: مخرجات ملفات وردود ونصوص. ويجب
حمايته كمساحة العمل. ويعرض `/audit` أحداث الملف
الحالي فقط، لا المدوَّرة.

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

- تصبح جميع السياسات `DENY`؛
- يُسجَّل `policy.failed`؛
- يبقى Hagar مشغَّلًا لكن لا تُنفَّذ أي أداة؛
- تعرض الطرفية `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

مع الواجهة الخلفية SQLite لا يُستخدم إلا من الواجهة الخلفية Markdown القديمة ومن
المشاريع القديمة. ومع `memory.backend: sqlite` قد لا يكون موجودًا أصلًا.

## 4.5 `memory`

```yaml
memory:
  enabled: true
  backend: sqlite
  database: ./hagar-memory.db
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  context_project_memories: 10
  max_context_chars: 6000
  project_max_active: 200
  summary_max_chars: 4000
  max_skill_chars: 4000
```

| الحقل | الافتراضي | التأثير |
|---|---|---|
| `enabled` | `true` | يفعّل الذاكرة |
| `backend` | `sqlite` | `sqlite` أو `markdown` القديمة |
| `database` | بيانات محلية | مسار صريح لقاعدة بيانات SQLite |
| `vault_subdir` | `Hagar` | مجلد فرعي في الـ Vault القديم |
| `context_turns` | `10` | الأدوار الحديثة المحقونة؛ `0` يعطّل |
| `context_skills` | `3` | المهارات المؤكدة المحقونة |
| `context_project_memories` | `10` | عناوين القرارات النشطة |
| `max_context_chars` | `6000` | ميزانية كتلة الذاكرة |
| `project_max_active` | `200` | عتبة صيانة المشروع |
| `summary_max_chars` | `4000` | الطول الأقصى للملخص |
| `max_skill_chars` | `4000` | الطول الأقصى لمهارة واحدة |

يجب أن يبقى `vault_subdir` داخل الـ Vault: فالمسارات المطلقة و`..`
و`I:/...` وأحرف محركات Windows الأخرى تُرفض حتى على Linux.

مع `backend: sqlite` قاعدة البيانات الافتراضية هي:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

أو `HAGAR_MEMORY_DB`. ويستخدم SQLite وضع WAL والمعاملات و`VACUUM INTO`
للنسخ الاحتياطي؛ ولا يُحدَّث الـ Vault.

الميزانية **بالحروف** لا بالرموز. وعندما تُقتطع الكتلة،
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

كل إدخال:

| الحقل | إلزامي | ملاحظات |
|---|---|---|
| `alias` | نعم | مقطع واحد فقط، فريد بغض النظر عن حالة الأحرف |
| `path` | نعم | مجلد موجود في النظام المضيف |
| `permissions` | لا | الافتراضي `R`؛ الحروف `R` و`W` و`X` |

الأذونات:

| الحرف | يغطي |
|---|---|
| `R` | القراءة والسرد والبحث و`stat` |
| `W` | الكتابة والإنشاء وإعادة التسمية والنسخ والحذف |
| `X` | `chdir` داخل المجلد |

يرى الوكيل `/home/ai/<alias>/...`. ويسرد `/home/ai` الأسماء المستعارة لكنه
ليس مجلدًا فيزيائيًا ولا يمكن الدخول إليه بـ `chdir`.

القيود:

- الأسماء المستعارة والمسارات المكررة توقف الإعدادات؛
- المسار المفقود يوقف الإعدادات؛
- يمكن أن تحتوي المسارات الفيزيائية على مسافات؛ أما الأسماء المستعارة فلا؛
- لا ينشئ Hagar مجلدات صندوق الرمل ولا يفترض وجود مجلد منزل مخصص.

حدود الكتابة:

| الحقل | التأثير |
|---|---|
| `max_write_bytes` | الحد الأقصى لكل عملية واحدة |
| `min_free_bytes` | الحد الأدنى للمساحة الحرة المتبقية |
| `session_write_bytes` | الحد الأقصى التراكمي للجلسة |
| `ask_over_bytes` | يطلب تأكيدًا عند تجاوز هذه العتبة |

`0` يعطّل الحد الفردي. والحدود ثوابت: فتجاوزها خطأ في الأداة،
لا تحذير.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
  agents: false
```

هي **سقف النظام**. الافتراضي: `read=true`، والبقية `false`.

| الحقل | يمنح |
|---|---|
| `read` | filesystem read، memory read |
| `write` | filesystem write/create/delete، memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |
| `agents` | `AGENT_SPAWN` و`AGENT_DATA`، لـ `agent.*`/`artifact.*`/`mailbox.*` |

`COMPUTE` و`MCP_CALL` في السقف دائمًا، لكن يمكن للسياسة حجبهما.
وإذا لم يمنح السقف قدرة ما، فلا يمكن للسياسة منحها.
و`agents: true` لا يكفي وحده: يجب أن تحتوي السياسة على قاعدة
`AGENT_SPAWN` لـ `agent.*`.

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

القيمة المتوقعة للاسترجاع الوثائقي. ولا تعدّل سياق
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
| `endpoint` | عنوان URL HTTP/JSON-RPC لخادم MCP |
| `namespace` | بادئة الأدوات المستوردة: `mcp.<namespace>.*` |
| `auth` | اختياري: `bearer` أو `header` أو `oauth` |

Bearer/header:

```yaml
auth:
  type: header
  header: Authorization
  token_env: ATLASSIAN_BASIC
```

القيمة المقروءة من البيئة تُرسَل **كما هي**: فبالنسبة إلى Basic
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

التدفق هو authorization code + PKCE مع استدعاء عودة محلي
`http://localhost:<port>/oauth/callback`. وإذا غاب `client_id` يُحاوَل
التسجيل الديناميكي. ومع `offline_access` يُضاف
`prompt=consent`. والرموز في ملف محلي مقيَّد وتُجدَّد
تلقائيًا.

إذا فشل خادم MCP:

- يُسجَّل `mcp.failed`؛
- يُتخطى الخادم؛
- تستمر الخوادم الأخرى وبقية الـ harness؛
- يعرض `/mcp` صفر أدوات لذلك الفضاء الاسمي.

## 4.10 `hifi`

```yaml
hifi:
  enabled: true
  margin: 0.20
  interpretations: 3
```

`margin` هو الحد الأدنى للمسافة، بالنقاط المئوية، بين التفسير الأول
والثاني. وتحت هذه العتبة يطلب Hagar توضيحًا.
و`interpretations` هو عدد التفسيرات المطلوبة من النموذج.
ويضيف هذا الوضع استدعاء LLM واحدًا لكل دور.

## 4.11 `tools`

```yaml
tools:
  timeout: 120
  repeat_limit: 3
```

`timeout` هو الحد بالثواني لاستدعاء أداة واحد؛ و`0` يعطّله.
ويمنع `repeat_limit` الاستدعاء المطابق الثالث في الدور نفسه؛
و`0` يعطّل المنع. ومهلة معالج Python قيد التنفيذ
هي بذل أقصى للجهد (best effort): فقد ينتهي العامل بعد الحد.

## 4.12 `dev`

```yaml
dev:
  enabled: false
  recipes: recipes.yaml
  copy_workspace: true
  max_output_chars: 100000
```

يفعّل `dev.list` و`dev.run`، وهما ينفذان وصفات موثوقة للاختبار
والتنقيح والبناء. ويجب أن يكون `recipes.yaml` خارج صندوق الرمل،
ويُقرأ عند الإقلاع فقط. وتلزم أيضًا قدرة `DEV_EXEC` في السياسة.
التفاصيل في `DEV_RUN.md`.

## 4.13 `boxes`

```yaml
boxes:
  enabled: false
  max_input_chars: 200000
  max_output_chars: 20000
  chunk_chars: 8000
  max_calls: 20
```

يفعّل `box.list` و`box.run`، وهما تحويلات LLM محدودة النطاق
(bounded) على ملفات صندوق الرمل. وليس لها ذاكرة ولا أدوات ولا
موجّه حر. وتلزم `BOX_EXEC` في السياسة. التفاصيل في `BOXES.md`.

## 4.14 `flow`

```yaml
flow:
  enabled: false
  max_source_chars: 20000
  max_steps: 10000
  max_tool_calls: 50
  max_loop_iterations: 1000
  timeout: 120
  max_output_chars: 20000
  repair_attempts: 2
```

يفعّل `flow.reference` و`flow.validate` و`flow.run`، وهو DSL خطي
`Hagar Flow`. وليس Python كاملًا: فلا import ولا class ولا def ولا lambda
ولا try ولا dict/set comprehension ولا وصول إلى كائنات Python؛
ويُسمح بـ list comprehension مع `for` واحد فقط. وتلزم `FLOW_EXEC` في
السياسة؛ وتستخدم العناصر الأولية `fs.*` قدرات نظام الملفات.

`repair_attempts` هو الحد الأقصى لمحاولات `flow.repair`؛
و`0` يعطّل الإصلاح. ولا يصلح `flow.run` الكود تلقائيًا أبدًا:
بل يعيد الخطأ ويقرر المستدعي ما إذا كان سيستخدم `flow.repair`.
ومع تفعيل الذاكرة تتاح `memory.search` و`memory.context`
و`memory.skill`؛ ومع مشروع نشط `project.context`.
التفاصيل في `FLOW.md`.

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

## 5.1 التأثيرات

| التأثير | المعنى |
|---|---|
| `allow` | يمكن تنفيذ الأداة |
| `ask` | يلزم تأكيد بشري |
| `deny` | لا تُنفَّذ الأداة |

ترتيب الشدة: `DENY > ASK > ALLOW`. ومع تعدد القدرات المطلوبة
يسري منطق AND: فيفوز التأثير الأسوأ.

`ASK` دون قناة تأكيد يعادل `DENY`. والتأكيد من الطرفية
يعرض `lo faccio? (y/N)` والافتراضي `N`.

## 5.2 القدرات

| الاسم | الاستخدام |
|---|---|
| `FILESYSTEM_READ` | القراءة والسرد والبحث وstat |
| `FILESYSTEM_WRITE` | التعديل |
| `FILESYSTEM_CREATE` | الإنشاء والنسخ وإعادة التسمية عند الوجهة |
| `FILESYSTEM_DELETE` | الحذف |
| `FILESYSTEM_EXEC` | الدخول/التنفيذ في صندوق الرمل |
| `MEMORY_READ` | قراءة الذاكرة |
| `MEMORY_WRITE` | كتابة الذاكرة |
| `NETWORK` | الوصول إلى الشبكة |
| `MCP_CALL` | استدعاء أداة MCP |
| `COMPUTE` | حساب محلي دون شبكة أو نظام ملفات |
| `AISH` | تنفيذ لغة AIsh |
| `DEV_EXEC` | تنفيذ وصفات dev.run |
| `BOX_EXEC` | تنفيذ boxed transform |
| `FLOW_EXEC` | تنفيذ DSL الخاص بـ Hagar Flow |

## 5.3 القواعد والخصوصية

يمكن للقاعدة التصفية بـ:

- `tools`: نمط glob على الاسم (`filesystem.*`، `mcp.atlassian.*`)؛
- `paths`: بادئات على المسار الذي يكتبه النموذج؛
- `namespaces`: بادئات على فضاء الأسماء.

تفوز القاعدة الأكثر خصوصية: أولًا عدد المرشحات، ثم
طول البادئة. وعند التعادل يفوز التأثير الأكثر تقييدًا.
ودون قواعد يسري `default` الخاص بالذات؛ والافتراضي الآمن `deny`.

تُحجب `AISH` بالقاعدة الافتراضية `aish.*`. ولتفعيل AIsh
يجب على المستخدم تغيير تلك القاعدة إلى `allow`؛ وتبقى الأوامر الداخلية
خاضعة لقواعد الأدوات الخاصة بها.

يقارن نطاق `paths` المسار **الذي يكتبه النموذج**، لا المسار
المحلول بعد `chdir`: فقد لا يطابق المسار المطلق أو تغيير المجلد
ويولّد `DENY` (fail closed).

## 5.4 الأخطاء

إذا كان `policy.yaml` غير صالح، أو غابت قدرة، أو لم تكن الذات
موجودة:

- يطبّق Hagar `DENY` على جميع السياسات؛
- يسجّل `policy.failed`؛
- يعرض تحذيرًا؛
- لا ينفّذ أي أداة.

---

# 6. السلوكيات الافتراضية

| الحالة | السلوك |
|---|---|
| لا يوجد `hagar.yaml` | خطأ في الإعدادات، خروج 1 |
| YAML غير صالح | خطأ في الإعدادات، خروج 1 |
| سياسة غير صالحة | DENY شامل، والـ harness مشغَّل |
| الذاكرة معطَّلة | تحقق من `memory.database` وأذونات المجلد |
| `Projects: disabled` | تحقق من قاعدة بيانات SQLite أو `vault.path` في الواجهة الخلفية القديمة |
| لا مشروع نشط | نشاط حر |
| إقلاع غير تفاعلي | نشاط حر، إلا مع `--project`/`--free` |
| `--project` غير موجود | خطأ، خروج 1 |
| خادم MCP غير قابل للوصول | `mcp.failed`، ويتخطى الخادم |
| النموذج/Ollama غير قابل للوصول | خطأ في الدور، ويبقى الـ harness نشطًا |
| مفتاح API غائب | لا يُبنى العميل، خطأ عند الإقلاع |
| أداة مرفوضة | نتيجة خطأ إلى النموذج، دون تنفيذ |
| أداة في `ASK` دون تأكيد | رفض |
| تجاوز حد الكتابة | خطأ في الأداة، دون كتابة |
| ملف يتجاوز 4096 بايت مع `read_file` | خطأ، استخدم `read_chunk` |
| `write_file`/`edit_file`/`delete_file`/`rename` على ملف لم يُقرأ | خطأ: اقرأ الملف أولًا |
| ملف تغيّر بعد القراءة | خطأ: أعد قراءته قبل تعديله |
| `edit_file` مع `old_string` غامض | خطأ: استخدم `replace_all` أو سلسلة أكثر تحديدًا |
| `edit_file` مع `old_string` غائب | خطأ، دون تعديل |
| صفحة تتجاوز الحد | `has_more`/`next_offset` |
| Symlink | غير مرئي؛ العملية كمسار غير موجود |
| Hard link/mount/junction | غير مكتشفة؛ مسؤولية المستخدم |
| Race TOCTOU | غير مراقَبة؛ مسؤولية المستخدم |
| ذاكرة غائبة أثناء الدور | `memory.failed`، ويستمر الدور |
| نهاية الجلسة مع أدوار | ملخص، وأرشفة، ومراجعة المشروع |
| مراجعة مرفوضة | قرارات مرشحة مع `auto_saved: true` |
| مشروع يتجاوز `project_max_active` | طلب أرشفة |
| Ctrl-C أثناء OAuth | إغلاق استدعاء العودة، خروج 130 |
| أمر `/` غير معروف | رسالة، ولا يُرسَل إلى النموذج |

## 6.1 نهاية الجلسة

عند الخروج، إذا كانت الذاكرة نشطة ووُجدت أدوار:

1. يُنقل النص إلى `archive/chat/`؛
2. يُولَّد ملخص (LLM، مع تراجع ميكانيكي)؛
3. يُحفظ الملخص مع رابط وبصمة (hash)؛
4. إذا وُجد مشروع، يقترح الـ LLM قرارات مرشحة؛
5. يمكن للمستخدم مراجعتها؛ وإذا رفض تبقى مرشحة.

إذا لم تكن هناك أدوار فلا يُنشأ أي ملخص.

## 6.2 ما لا يفعله Hagar

- لا ينفّذ أوامر shell؛
- لا يعطي النموذج مسارات فيزيائية؛
- لا يضمن عزلًا على مستوى نظام التشغيل: فصندوق الرمل قائم على المسارات؛
- لا يراقب hard link أو mount أو junction أو TOCTOU؛
- لا يحذف المحادثات أو المهارات بحسب القِدَم؛
- لا يشفّر الـ Vault؛
- لا يرفع تلقائيًا مهارة أو قرارًا إلى مرتبة الحقيقة.

---

# 7. الأمان التشغيلي

- النموذج غير موثوق: فالسياسات والتأكيدات هي الضوابط.
- تحتوي قاعدة بيانات SQLite على المحادثات والقرارات: ويجب حمايتها.
- قد يحتوي التدقيق على مخرجات ملفات: ويجب حمايته.
- مفاتيح API في البيئة فقط.
- رموز MCP/OAuth في ذاكرات تخزين مؤقت محلية بأذونات مقيَّدة.
- لا تعرّض Ollama أو LM Studio على الشبكة دون ضرورة.
- قد يعرّض hard link أو mount داخل مجلد مسموح
  محتويات خارجية: ولا يكتشفها Hagar.

---

# 8. استكشاف الأخطاء وإصلاحها

| العَرَض | الفحص |
|---|---|
| `Policy: DENY ALL` | تحقق من صحة `policy.yaml` و`policy.path` |
| `Memory: disabled` | تحقق من `memory.database` والأذونات |
| `Projects: disabled` | تحقق من قاعدة بيانات SQLite |
| `Failed to load MCP server` | نقطة النهاية، والرمز، و`/mcp` |
| `MCP auth token missing` | المتغير المشار إليه في `token_env` |
| `MCP HTTP 401` | بيانات الاعتماد/ترويسة Basic أو OAuth |
| `MCP HTTP 400` | البروتوكول أو الجلسة أو معاملات الخادم |
| `read_file` كبير جدًا | استخدم `read_chunk` |
| `PermissionError` | السياسة، وأذونات `R/W/X`، ومسار خارج صندوق الرمل |
| أداة غير مسرودة | خادم MCP فاشل أو أداة غير مسجَّلة |
| أمر غير معروف | `/help` |

في حالة خطأ إعدادات، يخرج Hagar بالرمز 1 ويطبع
التفاصيل على stderr. وفي حالة خطأ دور، يتلقى النموذج
نتيجة الأداة ويحفظ التدقيق الحدث.
