# HAGAR — سجل التغييرات

الصيغة حرة لكنها ثابتة: الإصدارات بترتيب تنازلي، مع
إشارة إلى الـ commit عند الحاجة.

---

# 0.5.2 — 2026-11-08

## ملخص

إصدار توطيد: ذاكرة SQLite، والوكلاء الفرعيون، والرؤية، وأدوات
القرار، وبطاقات النماذج، واستيراد/تصدير Markdown، وinput broker في الـ CLI.

## تغييرات كاسرة (Breaking change)

- الذاكرة الافتراضية لم تعد Vault Markdown: بل تستخدم
  `%LOCALAPPDATA%/Hagar/memory.db` أو `HAGAR_MEMORY_DB`؛
- لا يُستورَد الـ Vault تلقائيًا؛
- تبقى الواجهة الخلفية `markdown` متاحة كنسخة قديمة فقط؛
- `memory.database` و`decisions.*` أقسام إعدادات جديدة.

## واجهات LLM خلفية جديدة

- واجهة خلفية جديدة `lmstudio` لخادم LM Studio المحلي المتوافق مع
  OpenAI، والافتراضي `http://localhost:1234/v1`، بلا مفتاح إلا
  بإعداد الخادم.
- واجهة خلفية جديدة `openai` (الاسم البديل `chatgpt`) لـ API OpenAI Chat
  Completions، والمفتاح `OPENAI_API_KEY`، وعنوان URL أساسي قابل للإعداد.
- تتشارك الواجهتان العميل المتوافق مع OpenAI، مع استدعاء
  أدوات أصلي وتراجع JSON نصي عند HTTP 400/404/422.
- `model.timeout` قابل للإعداد (الافتراضي 120 ثانية) ويُمرَّر إلى جميع
  الواجهات الخلفية؛ وهو مفيد للنماذج المحلية الكبيرة.
- تحديث `hagar.example.yaml` والتوثيق الإيطالي.

## طبقة الخدمة

- `core/service.py` جديد مع `HarnessService`: الأدوار والحالة والمشروع
  ونهاية الجلسة والأحداث المهيكلة (`ServiceEvent`).
- يستخدم `hagar.py` الخدمة في `ask` واختيار المشروع وإغلاق
  الجلسة؛ ويبقى الـ CLI محوّلًا (adapter).
- الأحداث `tool.call` و`tool.result` و`permission.decision` و
  `permission.confirmation` تمرّرها `Agent` و`ToolRegistry` إلى
  sink الخاص بالخدمة؛ وتُقتطع مخرجات الأدوات في الأحداث.
- `CommandService` جديد لـ `/help` و`/tools` و`/status` و`/mcp`
  و`/audit` و`/project` و`/memory`، مع `CommandResult` مهيكل.
- يستخدم الـ CLI خدمة الأوامر لأوامر الشرطة المائلة؛ وتبقى `/memory review`
  تفاعلية.
- `QueueConfirmationProvider` جديد: تأكيدات ASK من الواجهة الرسومية بطابور
  ومهلة ورفض صريح.
- واجهة ويب محلية جديدة (`hagar web`): المحادثة، وأحداث SSE، والحالة، والمشاريع،
  واستدعاءات الأدوات، وحوار التأكيد؛ ورمز محلي وربط `127.0.0.1`.
- لم تعد انقطاعات SSE من المتصفح تنتج traceback على
  Windows (`ConnectionAbortedError`/WinError 10053).
- يُغلق Ctrl-C أمر `hagar web` فورًا: لا `shutdown()` من خيط
  `serve_forever`، ولا join لخيوط SSE، ويُتخطى الملخص عند
  الإطفاء.
- `core/usage.py` جديد: تحليل الاستهلاك لـ OpenAI/DeepSeek/LM Studio
  وClaude وGemini وOllama، مع `UsageLedger` لكل جلسة.
- تعرض الواجهة الرسومية الإدخال والإخراج وإجمالي الرموز في الشريط الجانبي، محدَّثة
  عبر الحدث `usage.updated`.
- HTML وCSS وJavaScript الخاصة بالواجهة منفصلة في `web/` وتُقدَّم
  كأصول ثابتة؛ و`core/web.py` يحقن الرمز فقط.
- `memory/index.py` جديد: فهرس SQLite/FTS5 تزايدي و
  قابل لإعادة البناء للذكريات Markdown، مع تراجع معجمي.
- الأداة الجديدة `memory.search`؛ والأوامر `/memory search` و`reindex`
  و`stats`.
- إيقاف تعاوني للدور (`Agent.cancel` و`POST /api/stop`) مع
  زر في الواجهة الرسومية وحدث `turn.cancelled`.
- إدخال صور الرؤية (`core/images.py`) مع التحقق من data URL
  وMIME والحد 10 MB؛ ومحوّلات OpenAI/LM Studio وClaude وGemini.
- رفع الصور في الواجهة الرسومية مع معاينة وإزالة؛ ويُحوَّل WebP
  إلى PNG قبل الإرسال. ولا تُحفظ أي صورة في الذاكرة أو التدقيق.
- جسم JSON للواجهة الرسومية حتى 64 MB، لقبول صور عالية
  الدقة بـ base64.
- سجل المحادثات في التبويب المخصص: قائمة `chat/` و
  `archive/chat/`؛ ونقرة تستأنف الجلسة نفسها وتواصل الأدوار الجديدة
  النص نفسه.
- زر **+ Nuova chat** مع `MemoryStore.new_session()` وتصفير
  السياق؛ وتبقى النصوص السابقة في الـ Vault.
- تبويبات الواجهة الرسومية: Chat وChat history وTool output وAudit وThinking وMemories.
- `SessionLog` في الذاكرة لاستدعاءات/نتائج الأدوات والخط الزمني؛
  و`/api/tools` و`/api/audit` و`/api/thinking`.
- متصفح ذكريات للقراءة فقط: `/api/memories` و`/api/memory`.
- `/usage` في الـ CLI للرموز المتراكمة للجلسة؛ والسجل نفسه
  تستخدمه الواجهة الرسومية.
- الأدوات ومزوّدو الـ LLM إضافات (plugin): مدمجة في `local_tools/plugins.py`
  و`llm/plugins.py`، وخارجية عبر entry point `hagar.tools`/`hagar.llm`.
- أخطاء الإضافات معزولة ومسجَّلة في التدقيق؛ وتبقى السياسة وصندوق الرمل
  في المضيف.
- موثَّق تصميم أداة المستندات في `DOCUMENT_TOOL.md`:
  رسم البنية/الدلالة، وMVP الخاص بـ CSV، وعقد `FormatPlugin`، وABI بلغة C، و
  بروتوكول JSON للمضيف الأصلي.
- وكلاء فرعيون غير متزامنون: `agent.spawn/status/wait/result/cancel`، وحتى
  ابنين متزامنين، وعميل LLM منفصل، ومساحة عمل خاصة بمدخلات
  منسوخة، وسجل للقراءة فقط، وذاكرة بلا كتابات، وتأكيدات مرفوضة،
  واستهلاك وتدقيق مخصصان؛ وتنظيف في نهاية الدور.
- `reason` إلزامي في spawn والقدرة `AGENT_SPAWN` منفصلة:
  فلا يستطيع الابن إنشاء آخرين؛ و`permissions.agents` يتحكم في
  سقف النظام.
- سياسة الوكيل الفرعي أكثر تقييدًا بصرامة من سياسة الأب؛ والسياسات
  المماثلة أو غير الأكثر تقييدًا تُرفض.
- مهلة فعلية مدتها 5 دقائق لكل وكيل فرعي، تعاونية، بحالة
  `timed_out`؛ و`agent_id` في جميع أحداث التدقيق.
- تأكيدات ASK الخاصة بالوكلاء الفرعيين تُمرَّر إلى المستخدم عبر `ParentBridgeConfirmation`،
  بمهلة 180 ثانية وDENY عند انتهائها؛ ولا يوافق الـ LLM الأب.
- `vision.open` يحمّل PNG/JPEG/WebP من صندوق الرمل ويرفقها بالدور؛
  و`ToolResult.images` ودورة الوكيل تديران القناة متعددة الوسائط
  دون base64 في النص. والصوت في خريطة الطريق.
- ذاكرة SQLite كمصدر أساسي: `memory/sqlite_store.py` و
  `memory/database.py`، وWAL والنسخ الاحتياطي؛ والأوامر `/memory sessions`
  و`/memory chat` و`/memory backup`. والمشاريع والقرارات في قاعدة
  البيانات نفسها؛ والواجهة الخلفية Markdown قديمة فقط.
- تصدير Markdown لقاعدة البيانات بـ `/memory export <path> [--force]`:
  المحادثات والمهارات والملخصات والمشاريع والقرارات، بكتابة ذرّية.
- استيراد Markdown بـ `/memory import <path> [--force]`؛ وFTS5 في
  قاعدة البيانات الأساسية مع `bm25`/`snippet` وتراجع `LIKE`.
- الـ CLI مع `ConsoleInputBroker`: قارئ طرفية واحد، وعنوان
  انتباه، وتأكيدات ASK بـ `F5` allow / `F8` deny؛ وتراجع `y/N`.
  ويحفظ الـ broker الطرفية ويعيدها، حتى مع Ctrl-C.
- فئة أدوات جديدة `decision.*` مع `decision.choose`: مزوّد LLM
  محلي/عن بُعد ومصنّف خطي محلي، واحتمالات مُتحقَّق منها،
  وتدقيق `decision.result`، والقدرة `DECISION`.
- بطاقات تقنية للنماذج ومعايير قياس: `/models list|show|test|hardware`،
  وزمن الاستجابة، وJSON، واستدعاء الأدوات، وتاريخ آخر تجربة، واكتشاف
  CPU/RAM/GPU دون تبعيات إلزامية.
- مخزن artifact مؤقت وmailbox داخلية: `artifact.put` و
  `artifact.put_file` و`mailbox.send` للابن؛ و`artifact.read` و
  `artifact.list` و`mailbox.inbox/read/ack` للأب. والقدرة
  `AGENT_DATA`، وحصص وتنظيف في نهاية الدور.
- `artifact.save_to` ينسخ الـ artifact بأكمله إلى مسار قابل للكتابة في
  صندوق رمل الأب؛ ويتطلب `AGENT_DATA` و`FILESYSTEM_WRITE` و
  `FILESYSTEM_CREATE`، مع تأكيد محتمل من السياسة.
- تدقيق `artifact.discarded` في نهاية الدور لكل artifact غير مُصدَّر،
  بسبب `unread` أو `read_but_not_saved`؛ وتبقى الاستمرارية
  مؤجَّلة.
- التدقيق معطَّل: تبويب معطَّل مع التسمية `audit off`.
- يعرض Thinking الاستدلال الذي يكشفه المزوّد، وإلا
  الخط الزمني للأحداث.
- أساس للواجهة الرسومية المستقبلية، دون `input()` أو `print()` في الخدمة.

# 0.3.0 — 2026-11-05

## ذاكرة المشروع والملخص والأرشيف

- ذاكرة مشروع جديدة منفصلة عن المهارات:
  `Hagar/projects/<id>/index.md` و`decisions/<data>-<slug>.md`، مع
  الحالة `candidate`/`active`/`superseded`/`archived`، والبدائل،
  والتبرير، والمصدر، و`auto_saved`.
- عند الإقلاع يعرض Hagar المشاريع النشطة و"النشاط الحر"؛ والأوامر
  `/project list|new|select|free|status` والتجاوزين `--project`/`--free`.
- في نهاية الجلسة يُنقل النص إلى `archive/chat/` و
  يُستبدل بملخص مع رابط وبصمة؛ وتراجع ميكانيكي إذا لم يكن
  النموذج متاحًا.
- تُقترَح قرارات المشروع كـ `candidate` وتُراجَع
  في نهاية الجلسة؛ وإذا رفض المستخدم تبقى مرشحة مع
  `auto_saved: true`.
- سياق بالفهرس: الملخص وعناوين القرارات النشطة، لا
  الأجسام؛ والتفاصيل بـ `memory.project_context`. والميزانية
  `max_context_chars` (بالحروف، لا بالرموز) والتدقيق
  `memory.context_trimmed`.
- `project_max_active` يفعّل طلب أرشفة
  المشروع؛ والأرشفة قابلة للعكس ولا تحذف شيئًا.
- إذا لم يكن المجلد `projects` قابلًا للكتابة، تبقى الذاكرة نشطة
  وتُعطَّل المشاريع بـ `project.disabled`.
- استشارة الأرشيف: `memory.archive_search` و
  `memory.archive_read`، والأوامر `/memory archive search|read`، مع
  ترشيح حسب المشروع ونصوص تحتفظ بـ `project` في
  الـ frontmatter. ولا يُحقن الأرشيف تلقائيًا أبدًا.

## أوامر الطرفية والدليل

- أوامر محادثة جديدة: `/help` و`/tools [categoria]` و`/status` و`/mcp`
  و`/audit [n]`.
- يجمع `/tools` الأدوات حسب الفئة ويعرض القدرات.
- يعرض `/status` النموذج والاستدعاء والمشروع والذاكرة والتدقيق و
  نظام الملفات.
- يسرد `/mcp` الخوادم المُعدّة ونقاط النهاية والأدوات المستوردة.
- يقرأ `/audit` آخر أحداث السجل الحالي، دون كشف
  الحقول غير المحددة.
- لا تُرسَل أوامر `/` غير المعروفة إلى النموذج.
- `Docs/it/MANUAL.md` جديد مع الأوامر والـ CLI و`hagar.yaml`
  و`policy.yaml` والافتراضيات والسلوكيات في حالة الخطأ.

## MCP وOAuth والخروج السليم

- تحديث عميل MCP إلى `MCP-Protocol-Version` `2025-06-18` مع
  تراجع، وإعادة استخدام `Mcp-Session-Id`، وجسم HTTP في الأخطاء.
- OAuth: `audience` اختياري، و`prompt=consent` مع `offline_access`،
  واستدعاء عودة `http://localhost:<port>/oauth/callback`، والنطاقات في
  التسجيل الديناميكي.
- Ctrl-C أثناء OAuth أو دور يغلق استدعاء العودة المحلي ويخرج
  بالرمز 130، دون traceback.

## الأدوات المحلية ونظام الملفات v2

- مجلد جديد `local_tools/` للمزوّدين المحليين: الحساب والإحصاء
  وتحويل الوحدات والوقت/التاريخ والخلاصات. وليست خوادم MCP: بل تسجّل
  `ToolDefinition` في السجل.
- أدوات مضافة: `calculator.evaluate` و`statistics.compute`
  و`units.convert` و`clock.now` و`calendar.date` و`think.echo`
  و`text.diff` و`url.parse` و`feed.read`.
- نظام الملفات: `list_dir` و`read_chunk` و`rename` و`copy_file` و`search`.
- القدرات الجديدة `COMPUTE` (حسابات محلية، في السقف دائمًا) و
  `NETWORK` (تُفعّلها `permissions.network: true`)؛ ويتطلب `feed.read`
  `NETWORK`.
- `permissions.network` في الإعدادات؛ والسياسة: `COMPUTE` allow لـ
  calculator/statistics/units، و`NETWORK` ask لـ feed.
- `feedparser` بين التبعيات؛ وتُنزَّل الخلاصة بـ
  `requests`، بمهلة وحد 5 MB، ومن عناوين http/https فقط.
- SSRF: تحليل DNS إلزامي، وعناوين عامة فقط
  (لا loopback ولا شبكات خاصة ولا link-local ولا multicast ولا محجوزة)،
  وإعادة توجيه يدوية يُعاد التحقق منها (بحد أقصى 3) ورفض عناوين URL التي تحمل
  بيانات اعتماد.
- أُعيد إذن `rename` في صندوق الرمل، الذي فُقد أثناء
  التوسيع؛ ويتطلب `filesystem.rename` `rename` على المصدر و
  `create` على الوجهة.
- إعادة تسمية `MCP_tools/` → `local_tools/`: فهي مزوّدون محليون، لا
  خوادم MCP؛ وتحديث الحزمة والاستيرادات والاختبارات والتوثيق.
- نظام ملفات بجذر افتراضي `/home/ai`: لم يعد `stat` و`list_dir`
  و`search` و`read_chunk` ورسائل الأدوات تكشف
  المسار الفيزيائي؛ وتُقبل المدخلات `/home/ai/...`.
- يوائم `read_chunk` الحدود مع حروف UTF-8 ويعيد
  `next_offset`؛ ولم يعد يكسر الحروف متعددة البايتات.
- يرفض `read_file` الملفات التي تتجاوز 4096 بايت ويوجّه إلى `read_chunk()`
  لتجنّب تحميل الملف كله في context window.
- يعيد `list_dir` 100 إدخال كحد أقصى في الصفحة و`search` 100
  نتيجة (بحد أقصى 500)؛ وكلاهما يدعم `offset` و`next_offset`
  و`has_more` والرسالة
  `voci: riportate X di Y; per continuare usa offset=Z`. وللأشجار
  الكبيرة يُفضَّل تضييق pattern/path بدلًا من تكرار الصفحات.
- حدود كتابة جديدة `filesystem.limits`:
  `max_write_bytes` لكل عملية، و`min_free_bytes` كاحتياطي،
  و`session_write_bytes` تراكمي، و`ask_over_bytes` للتأكيد.
  والثلاثة الأولى ثوابت؛ و`ask_over_bytes` يمر عبر الفحص المسبق في
  `ToolRegistry` ويسأل مرة واحدة فقط، حتى إذا كانت السياسة `ASK`.
- الروابط الرمزية غير موجودة بالنسبة لصندوق الرمل: فلا تُعرض ولا تُقرأ
  ولا تُتبع ولا تُحذف؛ و`chdir` على رابط يرد
  “Directory not found”. وقرار المشروع: تبقى غير مرئية
  حتى لو دعمها نظام الملفات المضيف.
- الروابط الصلبة وmount وjunction داخل المجلدات المسموح بها لا
  يراقبها Hagar ولا يكتشفها. وليس هذا عيبًا: فالرابط الصلب
  اسم ثانٍ للـ inode نفسه وقد يعرض mount نظام ملفات آخر
  وهو داخل البادئة. وأدوات نظام الملفات لا تنشئ
  روابط صلبة. ولعزل تام يجب على المستخدم ضمان عدم وجودها في
  مجلدات صندوق الرمل. مسؤولية المستخدم،
  والحالة مغلقة.
- TOCTOU: لا يستخدم هذا الإصدار `openat2` ولا `O_NOFOLLOW` على كل
  مكوّن ولا مقابض Windows، وبالتالي لا يضمن الذرّية بين الفحص
  والعملية. فالسباق يتطلب عملية محلية متزامنة بوصول
  للكتابة: سيناريو خبيث أو بيئة مخترقة، لا
  استخدام عادي. مغلق كمسؤولية المستخدم؛ ولعزل
  تام يلزم مجلد تخزين مخصص، أو مستخدم منفصل، أو mount namespace، أو
  حاوية.
- استُبدل `filesystem.allowed` بـ `filesystem.sandbox`: فكل إدخال له
  `alias` و`path` وأذونات `R`/`W`/`X`. ويرى الوكيل
  `/home/ai/<alias>/...`؛ لا `hdN` ولا وحدات تخزين ولا مجلدات
  وسيطة اصطناعية. ويسرد `/home/ai` الأسماء المستعارة لكنه ليس mount.
- أذونات لكل اسم مستعار: `R` قراءة/سرد/بحث/stat، و`W`
  كتابة/إنشاء/إعادة تسمية/نسخ/حذف، و`X` `chdir`؛ وتبقى
  الأذونات العامة سقفًا.
- الاسم المستعار إلزامي، ومقطع واحد، وفريد بغض النظر عن حالة الأحرف، وبلا
  أسماء Windows المحجوزة؛ وتبقى إدخالات صندوق الرمل مسارات للنظام
  المضيف ولا ينشئ Hagar مجلدات. ويمكن أن تحتوي المسارات الفيزيائية والأسماء الداخلية
  على مسافات؛ أما الاسم المستعار فلا.
- مشغّل POSIX `tools/run_tests.sh`؛ ويبقى `run_tests.ps1` والـ shim
  خاصين بصندوق رمل Windows. وتحديث أوامر القياس.
- إصلاح متعدد المنصات من CI: يرفض `vault_subdir` أيضًا المسارات التي تحمل
  محرك Windows (`I:/...`) على POSIX؛ ولم يعد رفض الروابط الرمزية
  يُبتلع بـ `except OSError`، وبذلك لا يُحل المسار
  خارج صندوق الرمل.
- 832 اختبارًا ناجحًا، و2 متجاوز على Windows؛ و834 ناجحًا، و0 متجاوز على Debian
  Linux (2026-11-06)، بما فيها اختبارات symlink.

## الإصدار وتعدّد المنصات

- الإصدار `0.3.0` في `pyproject.toml` و`hagar.py`.
- CI الخاصة بـ GitHub Actions على Linux وmacOS وWindows مع Python 3.11 و3.12 و
  3.13؛ وبناء الحزمة، و`twine check`، واختبار سريع (smoke test) للـ wheel.
- تحديث الـ actions إلى `checkout@v7` و`setup-python@v7` و
  `upload-artifact@v7`، جميعها على Node 24؛ وإزالة تحذير
  إهمال Node 20.
- سير عمل الإصدار على وسم `v*`: بناء sdist/wheel، والتحقق من أن الوسم
  يطابق الإصدار، وإنشاء إصدار GitHub.
- `hagar.example.yaml` قابل للنقل؛ و`hagar.yaml` المحلي و`testvault/`
  يتجاهلهما git.
- `MANIFEST.in` و`SECURITY.md` و`CONTRIBUTING.md` و`RELEASING.md` من أجل
  الإصدار العام الأول.

# 0.2.0 — 2026-11-04

أول إصدار بذاكرة قابلة للمراجعة، واستدعاء أصلي، وMCP auth/OAuth،
واحتفاظ بالتدقيق، وتغليف قابل للتثبيت.

## الذاكرة v2

- دورة الحياة `candidate` → `confirmed` → `archived`: يقترح الـ LLM،
  ويرقّي المستخدم من الـ CLI.
- الأوامر `/memory list` و`/memory show` و`/memory review`
  و`/memory confirm` و`/memory archive`.
- حقن تلقائي للمهارات المؤكدة فقط، وحتى
  `memory.context_skills` (الافتراضي 3)، بالمطابقة المعجمية؛ وتبقى المرشحة
  والمؤرشفة خارجًا.
- `reviewed_at` في الـ frontmatter؛ وأحداث التدقيق `memory.review` و
  `memory.status`.
- الاحتفاظ بالخيار A: لا حذف تلقائي؛ و`archive` قابل للعكس بـ
  `confirm`.
- `memory.context_skills` في الإعدادات؛ و552 اختبارًا ناجحًا، و1 متجاوز.

## MCP OAuth التفاعلي

- تدفق authorization code + PKCE مع استدعاء عودة على `127.0.0.1` و
  فتح المتصفح؛ وتراجع يدوي بلصق عنوان URL.
- اكتشاف RFC 9728 (المورد المحمي) وRFC 8414 (خادم التفويض)،
  مع تسجيل ديناميكي للعميل إذا غاب `client_id`.
- ذاكرة رموز محلية بأذونات `0600`، وتجديد تلقائي وإعادة محاولة واحدة
  عند `401`.
- إعداد `auth.type: oauth` مع `authorization_server` و`client_id`
  و`client_secret_env` و`scopes` و`redirect_port` و`token_cache`
  و`timeout`.
- الحدود: لا device flow ولا DPoP ولا mTLS ولا client assertion.
- 522 اختبارًا ناجحًا، و1 متجاوز.

## الاحتفاظ بالتدقيق

- تدوير إلى `<file>.<timestamp>` عند تجاوز `audit.max_bytes`.
- `audit.max_files` (الافتراضي 100) يحدّ عدد ملفات التدقيق،
  بما فيها الملف النشط؛ وتُحذف النسخ الأقدم.
- تستمر سلسلة البصمات من أحدث نسخة احتياطية إذا غاب الملف
  النشط.
- 504 اختبارات ناجحة، و1 متجاوز.

## MCP auth

- `mcp_servers[].auth`: `type: bearer` أو `type: header`، مع
  `token_env`، وللترويسة اسم الترويسة.
- يُقرأ الرمز من البيئة فقط: فلا يدخل YAML ولا التدقيق ولا
  السجلات.
- رمز غائب أو غير ASCII: يُتخطى الخادم بـ `mcp.failed` و
  يستمر الـ harness مع الآخرين.
- 496 اختبارًا ناجحًا، و1 متجاوز.

## قياس الأصلي مقابل النصي

- `tools/bench_native.py`: 9 مهام لنظام الملفات على السجل نفسه،
  ومقارنة بين `native_step()` و`request_tool_call()`، مع الدقة
  وزمن الاستجابة والإصلاحات.
- أول القياسات: `llama3.1` 4/5 مقابل 5/5، و`qwen3:8b` 4/5 مقابل 5/5،
  و`hermes3:8b` 4/5 مقابل 3/5، و`deepseek-flash` 8/9 مقابل 9/9 (مجموعة فرعية من Ollama،
  والمجموعة الكاملة على DeepSeek).
- لا فائز شامل: فيبقى الافتراضي أصليًا، مع إمكانية الإلغاء لكل
  نموذج عبر `model.native_tools` أو `--no-native-tools`.

## DeepSeek (حي)

- نماذج محدَّثة: `deepseek-flash` (الافتراضي) و`deepseek-v4-pro`؛
  ولم يعد `deepseek-chat` صالحًا.
- رسائل خطأ بجسم رد الـ API؛ والمفاتيح غير الـ ASCII
  تُرفض بـ `ConfigError`.
- أسماء الأدوات مطبَّعة من أجل الـ APIs التي لا تقبل النقطة
  (`filesystem.read_file` → `filesystem__read_file`)، مع العودة إلى
  الاسم الداخلي.
- `tools/diagnose_deepseek.py` للشبكة وشكل المفتاح ونقطة النهاية،
  دون طباعة المفتاح.
- اختبارات حية: المحادثة، والاستدعاء الأصلي، واختبار شامل على نظام الملفات.
- 479 اختبارًا ناجحًا، و1 متجاوز؛ و9 اختبارات حية مع `--live`.

## الاستدعاء الأصلي (v1)

- `LLMClient.native_step()` و`LLMReply`: استدعاء أصلي لـ Ollama
  وDeepSeek وClaude وGemini؛ ومخطط المعاملات من `ToolDefinition`.
- رسائل قانونية `assistant` مع `tool_calls` و`tool` مع
  `tool_call_id`؛ ويترجمها كل backend (`tool_calls`، و`tool_use`/
  `tool_result`، و`functionCall`/`functionResponse`).
- ينفّذ الوكيل استدعاءات متعددة لكل دور، في حدود `max_tool_calls`.
- تراجع تلقائي إلى البروتوكول النصي عند HTTP 400/404/422 في الخطوة الأولى،
  مع الحدث `llm.native_fallback`؛ ويفرضه `model.native_tools: false` و
  `--no-native-tools`.
- التدقيق: `turn.start` مع `native`، و`llm.tool_choice` مع `mode=native`.
- 476 اختبارًا ناجحًا، و1 متجاوز؛ و7 اختبارات حية مع `--live`.

## النظافة (v1)

- **التغليف**: `pyproject.toml` كامل (بيانات وصفية وتبعيات و
  setuptools)، ونقطة الدخول `hagar`، وإصدار واحد (`hagar.__version__`)؛
  وتم التحقق من `pip install -e .`.
- **الـ CLI**: `--config` و`--model` و`--no-memory` و`--version`؛
  ويُبحث عن الإعدادات في `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml`.
- **الاختبارات الحية**: وسم `live`، مستبعدة من المجموعة العادية، و`--live`
  لـ Ollama والمزوّدين عن بُعد (يُتجاوزون دون مفتاح).
- **MCP**: ردود `text/event-stream`، وإشعار
  `notifications/initialized`، وتطبيع النتائج إلى نص.
- **التدقيق**: سلسلة بصمات (`prev`/`hash`، و`verify_chain`)، وتدوير عند
  `max_bytes`، وحجب مخرجات الأدوات بـ `include_outputs`.
- **عنوان URL الأساسي**: `model.host` يستخدمه جميع المزوّدين.
- **القديم**: أُزيل `tools/filesystem.py` و`llm/tool_result.py`.
- 442 اختبارًا ناجحًا، و1 متجاوز؛ و6 اختبارات حية مع `--live`.

## الذاكرة (v1)

- `memory/store.py`: ذاكرة عرضية (ملاحظة واحدة لكل جلسة في
  `<vault>/Hagar/chat/`) ودلالية
  (`<vault>/Hagar/skills/<slug>.md`)؛
- حقن تلقائي لآخر `memory.context_turns` دورًا في
  الـ prompt، مع اقتطاع؛ وخطأ الذاكرة لا يُفشل الدور؛
- الأدوات `memory.create_skill` (المصدر والحالة `candidate`)،
  و`memory.list_skills`، و`memory.get_context` (البحث بالكلمة المفتاحية)؛
- القدرتان `MEMORY_READ`/`MEMORY_WRITE`، وفضاءا الأسماء `chat`/`skills` من أجل
  السياسات؛
- إعداد `memory.*` والتعطيل مع تحذير إذا غاب الـ vault؛
- أحداث التدقيق `memory.enabled` و`memory.disabled` و`memory.context`
  و`memory.turn` و`memory.failed`؛

## الأذونات (PermissionEvaluator v1)

- `core/permissions.py` جديد: `Capability` (IntFlag)، و`Effect`
  (`ALLOW` / `ASK` / `DENY`، مع deny-overrides)، و`Rule` بنطاق لكل
  tool وpath وnamespace، و`Subject`، و`Resource`، و`Decision`، و
  evaluator نقي؛
- `policy.yaml` منفصل، يُقرأ قبل بناء الـ LLM: وفي حالة
  خطأ تصبح جميع السياسات `DENY`، مع الحدث `policy.failed` و
  تحذير في المحادثة؛
- سقف نظام مشتق من `permissions.read/write/shell`؛
- `ASK` مع تأكيد من الطرفية (`lo faccio? (y/N)`، الافتراضي N) و
  `ConfirmationProvider` للواجهات الرسومية المستقبلية؛
- يطبّق `ToolRegistry.execute` السياسة ويسجّل
  `permission.decision` و`permission.confirmation`؛
- `ToolDefinition.capabilities` لجميع الأدوات (نظام الملفات وMCP)؛
- `requires_confirmation` مطبَّق الآن كحد أدنى من ASK؛
- أُزيل الـ stub الناقص `PolicyRule` من `core/models.py`؛

## نظام الملفات v2 والأدوات الرياضية والخلاصات

### نظام الملفات

- `filesystem.list_dir`: سرد غير تكراري لمحتوى مجلد.
- `filesystem.list_dir` يعيد بيانات كاملة عبر `FileInfo` لكل عنصر موجود.
- `filesystem.read_chunk`: قراءة تزايدية للملفات الكبيرة عبر offset وlength.
- `filesystem.read_chunk` يعمل على مستوى البايت ويعيد `has_more` ليتيح للوكيل مواصلة القراءة.
- `filesystem.rename`: إعادة تسمية أو نقل ملف داخل صندوق الرمل.
- `filesystem.copy_file`: نسخ ملف مع التحقق من الأذونات والمساحة المتاحة.
- `filesystem.search`: بحث تكراري بنمط glob (`*.py`، `*.md`، إلخ).
- `filesystem.search` يعيد:
  - العدد الإجمالي للنتائج الموجودة؛
  - عدد النتائج المعادة؛
  - إشارة الاقتطاع (`truncated`)؛
  - قائمة النتائج كـ `FileInfo`.
- تحسين الاستكشاف المستقل لصندوق الرمل: يستطيع الوكيل الآن تعداد المجلدات والبحث عن الملفات وقراءة مستندات كبيرة جدًا دون إشباع context window.

### Calculator

- الفئة الجديدة `local_tools/calculator.py`.
- تحليل عبر AST آمن، دون استخدام `eval()`.
- دعم:
  - `+`
  - `-`
  - `*`
  - `/`
  - `//`
  - `%`
  - `**`
  - الأقواس.
- الثوابت الرياضية:
  - `pi`
  - `e`
- الدوال المدعومة:
  - `sqrt`
  - `abs`
  - `sin`
  - `cos`
  - `tan`
  - `asin`
  - `acos`
  - `atan`
  - `log`
  - `log10`
  - `exp`
  - `floor`
  - `ceil`
  - `round`
- أداة MCP جديدة:

  `calculator.evaluate`

تُتحقق جميع العمليات عبر قائمة مسموحة من عقد AST والمعاملات والدوال.

### الإحصاء

الفئة الجديدة local_tools/statistics.py.

أداة MCP جديدة:

`statistics.compute`

الفئة هي `Stats_calc`؛ والأداة المعروضة للنموذج هي
`statistics.compute`. العمليات المدعومة:

- mean
- median
- stdev
- variance
- min
- max
- sum
- count

نتائج مهيكلة مع:

- نتيجة العملية؛
- نوع الإحصاء المطلوب؛
- عدد العينات المعالجة؛
- النتيجة أو الخطأ.

### تحويل الوحدات

الفئة الجديدة `local_tools/unit_converter.py`.

أداة MCP جديدة:

`units.convert`

دعم الفئات:

الطول

- mm
- cm
- m
- km

الكتلة

- mg
- g
- kg
- t

الزمن

- ms
- s
- min
- hour
- day

درجة الحرارة

- c
- f
- k

الزاوية

- deg
- rad

حجم البيانات

- b
- kb
- mb
- gb
- tb

نظام الأسماء البديلة وتطبيع الوحدات:

meters → m
kilometers → km
hours → hour
celsius → c
fahrenheit → f
degrees → deg
إلخ.

تحويلات مخصصة من أجل:

درجة الحرارة (مع إزاحة)؛
الزوايا (درجات/راديان).

تحويلات خطية لجميع الفئات الأخرى.

### خلاصات RSS وAtom

الفئة الجديدة `local_tools/feeder.py`.

أداة MCP جديدة:

`feed.read`

دعم شفاف لخلاصات RSS وAtom عبر API واحدة.

المعامل max_items بحد أمان لتجنّب مخرجات مفرطة.

استخراج مهيكل لـ:

- العنوان؛
- الرابط؛
- تاريخ النشر؛
- المؤلف؛
- الملخص.

تنظيف تلقائي للـ HTML الموجود في الخلاصات وإعادة البيانات الوصفية للخلاصة:

- العنوان؛
- الوصف؛
- الرابط؛
- النوع (rss أو atom أو إلخ).

إعادة العدد الإجمالي للعناصر المتاحة، وعدد العناصر المعادة، وإشارة الاقتطاع.

### ملاحظات

توسّع هذه التكرار قدرات الوكيل التشغيلية توسعًا كبيرًا. فإضافة إلى نظام الملفات المعزول، أصبح لدى Hagar الآن أدوات موثوقة من أجل:

استكشاف المحتويات والبحث فيها؛
قراءة ملفات كبيرة جدًا على نحو تزايدي؛
إجراء حسابات رياضية حتمية؛
إجراء تحليلات إحصائية؛
تحويل وحدات قياس تنتمي إلى مجالات مختلفة؛
استهلاك مصادر معلومات مهيكلة عبر خلاصات RSS وAtom.

ويبقى الهدف إيثار أدوات حتمية ومهيكلة وسهلة الاستخدام من النماذج عبر الاستدعاء الأصلي للأدوات.


## التوثيق

- `PROJECT_STATE.md` مقسوم إلى `ARCHITECTURE.md` (كيف هو النظام)،
  و`ROADMAP.md` (ما ينبغي فعله والقرارات المتخذة)، وهذا `CHANGELOG.md`.
- تحديث خارطة الطريق بقرارات 2026-11-03: الذاكرة على الـ Vault، و
  الاستدعاء الأصلي للأدوات، و`PermissionEvaluator`.

---

# 0.2.0 — 2026-11-03 (قيد التطوير)

Commit: `137c985` — *Debug, suite di test, audit log e backend multipli*

## مضاف

- **سجل التدقيق** (`core/audit.py`): JSON Lines للإلحاق فقط بطوابع زمنية
  UTC، ومعرّفات `session` و`turn`. وأحداث لكل جلسة ودور واختيار
  للأداة وبروتوكول وتنفيذ وأخطاء وMCP ومزوّد. وكتابة بأفضل
  جهد، واقتطاع قابل للإعداد، ولا مفاتيح API في السجل.
- **واجهات خلفية متعددة** (`llm/base.py`، `llm/factory.py`،
  `deepseek_client.py`، `claude_client.py`، `gemini_client.py`):
  يتشارك `LLMClient` اختيار الأدوات وتحليل JSON وإصلاحه؛
  ويكتفي كل backend بتنفيذ النقل وتحويل
  الأدوار.
- **`filesystem.stat`**: النوع والحجم بالبايت وتواريخ ISO 8601 و
  الأذونات الفعلية لصندوق الرمل، في قياس واحد.
- **مجموعة الاختبارات**: 259 اختبارًا، و1 متجاوز، بلا شبكة (Ollama وMCP
  محاكيان)، مع `tools/run_tests.ps1` وshim لصندوق رمل Windows.
- **`tools/bench_models.py`**: مقارنة قابلة للتكرار لنماذج
  Ollama في القراءة والبيانات الوصفية والإنشاء والمحادثة.

## متغيّر

- `model.provider` يختار الـ backend فعلًا (كان يُتجاهل سابقًا وكان
  يُستخدم Ollama دائمًا). ومفاتيح API من البيئة، لا من YAML أبدًا.
- النموذج الافتراضي: `llama3.1:latest` بدلًا من `qwen3:8b`.
- نتائج الأدوات أدوار `user` لا `system`، للتوافق
  مع الواجهات الخلفية عن بُعد.
- أخطاء الإعدادات: خروج سليم (`SystemExit 1`) برسالة
  على stderr وحدث `llm.failed` في التدقيق.

## مصحَّح

- كان `core/filesystem.py` مقطوعًا في منتصف `mkdir`: فقد غاب
  `read_file` و`write_file` و`create_file` و`delete_file`
  و`free_space`. وكانت كل أداة من أدوات نظام الملفات تفشل بـ `AttributeError`.
- كان `ToolDefinition.origin` إلزاميًا لكن لا مزوّد يمرّره:
  فكان تسجيل أي أداة يفشل بـ `TypeError`.
- كان `ToolResult` يستخدم `tool` بينما يستخدم `Agent` الحقل `tool_name`.
- كان `llm/ollama_client.py` يستخدم `re` دون استيراده ويعرّف مرتين
  `_tool_call_from_json`.
- كان `hagar.py` يقرأ حقولًا غير موجودة في `AppConfig`: فكانت `main()`
  لا تبدأ.
- لم يكن `ConfigLoader` يتحقق من YAML الفارغ، والجذور غير الـ mapping، والأذونات
  غير المنطقية، و`allowed` غير القائمة.
- كان `write_file` يستطيع إنشاء ملفات جديدة بالالتفاف على إذن `create`.
- يقبل التحليل الاسم البديل `parameters`؛ والرد النثري ينتج
  محاولة إصلاح واحدة، ثم خطأ صريحًا.

## ملاحظات

مقارنة نماذج Ollama (4 مهام، وصندوق رمل مؤقت، وبحد أقصى 4 أدوات لكل
دور):

| modello | read | stat | create | chat | الإصلاحات |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | حلقة، 4 أدوات | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | أداة خاطئة | ملف خاطئ | محتوى خاطئ | ok 6.4 s | 3 |

---

# 0.1.0 — 2026-11-02

Commit: `03b35bf` — *versione 0.1 alpha*

أول إصدار يعمل فعلًا: لم يعد Hagar واجهة
إلى Ollama، بل وكيلًا تشغيليًا.

## مضاف

- تحميل إعدادات YAML والتحقق من صحتها؛
- `OllamaClient` مع `generate` و`chat` و`request_tool_call`؛
- `ToolRegistry` و`ToolDefinition` و`ToolCall` و`ToolResult`؛
- `Agent` بدورة متعددة الخطوات وإدارة للأخطاء وحد للأدوات؛
- `FileSystemSandbox` بجذور وأذونات قابلة للتوريث وحماية من
  الروابط الرمزية ومراقبة لمساحة القرص؛
- أدوات نظام الملفات: القراءة والكتابة والإنشاء والحذف،
  وإنشاء المجلدات، وتغيير المجلد، والمساحة الحرة؛
- عميل MCP عبر HTTP مع اكتشاف تلقائي للأدوات وفضاء الأسماء؛
- `Vault` أولي لملفات Markdown.

## ملاحظات

v0.1 هو أول إصدار قادر على التحاور مع LLM محلي،
وعرض أدوات، وجعل النموذج يختار ما يستخدمه، والعمل على
نظام ملفات معزول، وربط عدة عمليات باستقلالية.
