# HAGAR — Архитектура

Версия: 0.7.0
Последнее обновление: 2026-11-03

---

# 1. Что такое Hagar

Hagar — это harness для LLM, написанный на Python и предназначенный для
устойчивого выполнения языковых моделей.

Цель — не чат с моделью, а **безопасная** операционная среда, в которой
LLM может использовать инструменты, обращаться к постоянной памяти и
взаимодействовать с внешними системами без прямого доступа к реальным
ресурсам хост-машины.

Для этого проект применяет принципы HMI/HCI и когнитивной эргономики
к проектированию среды, в которой работает модель.

## 1.1 Четыре закона HAGAR

**Первый закон — LLM по определению не заслуживает доверия.**
Не потому что она злонамеренна или бесполезна: потому что она вероятностна. Каждое её
утверждение нужно проверять, а каждое её действие — ограничивать.

**Второй закон — инструменты надёжнее LLM.**
Если файловая система говорит, что файл существует, он существует. Если инструмент возвращает
размер, этот размер реален. LLM интерпретирует, инструменты
измеряют.

**Третий закон — состояние должно существовать вне разума LLM.**
ToolRegistry, MCP, FileSystemSandbox и (в перспективе)
PermissionEvaluator выносят знания и контроль за пределы модели,
как в системах, критичных для безопасности.

**Четвёртый закон — каждое действие должно быть объяснимо задним числом.**
Журнал аудита отвечает на правильный вопрос: не «почему LLM сошла с ума?»,
а «какое допущение она сделала?», «какой инструмент она использовала?», «какие данные были
ошибочными?». Расследование инцидентов, как в авиации.

## 1.2 Абсолютные запреты

Модель не должна никогда:

- напрямую обращаться к файловой системе хоста;
- выполнять команды в настоящем shell;
- получать привилегии выше определённых конфигурацией;
- знать фактическую организацию операционной системы.

Все операции проходят исключительно через инструменты, зарегистрированные и
контролируемые harness.

## 1.3 Архитектурные принципы

- разделение модели и операционной системы;
- безопасность по умолчанию;
- плагинная архитектура;
- независимость от провайдера LLM;
- расширяемость через инструменты и протокол MCP.

---

# 2. Архитектура

```text
Пользователь
  │
  ▼
Agent ──────────────── AuditLog (JSON Lines)
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
  │     ├── memory.*        (запланировано)
  │     └── mcp.*
  │
  ├── FileSystemSandbox
  │
  ├── MCPClient
  │
  └── Vault (Obsidian)
```

Поток выполнения:

```text
Пользователь
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
Финальный ответ    turn.answer
```

---

# 3. Компоненты

## 3.1 Конфигурация (`core/config.py`)

Загружает и проверяет файл YAML (`hagar.yaml`) в `AppConfig`.

Разделы:

| раздел | обязателен | содержимое |
|---|---|---|
| `model` | да | provider, имя, host, timeout, max_tokens, api_key_env, native_tools |
| `vault` | да | путь к хранилищу Obsidian |
| `filesystem` | да | `sandbox`: список `{alias, path, permissions}`; `limits`: бюджет записи |
| `permissions` | нет | read, write, shell, network (по умолчанию `true/false/false/false`) |
| `rag` | нет | `top_k` (по умолчанию 8) |
| `mcp_servers` | нет | endpoint, namespace, auth (bearer/header/oauth) |
| `audit` | нет | enabled, path, max_field_chars, max_bytes, max_files, include_outputs |
| `policy` | нет | путь к файлу policy, subject |
| `memory` | нет | enabled, vault_subdir, context_turns, context_skills, max_skill_chars |

Ошибки проверки всегда порождают `ConfigError` с сообщением, которое
указывает поле. Путь аудита, если он относительный, разрешается
относительно файла конфигурации.

## 3.2 Интерфейс LLM и бэкенды (`llm/`)

`LLMClient` имеет два режима:

- **нативный вызов** (по умолчанию): `native_step()` отправляет схемы
  инструментов в формате провайдера и читает вызовы из ответа;
- **текстовый JSON-протокол** (fallback): `request_tool_call()` запрашивает
  JSON с `tool`/`arguments`, с устойчивым парсингом и одной попыткой
  исправления.

Схема параметров строится из `ToolDefinition`:
OpenAI/Ollama используют `tools[].function`, Claude — `tools[].input_schema`,
Gemini — `functionDeclarations`. Канонический диалог использует роли
`user`/`assistant`/`tool`; каждый клиент его переводит (OpenAI `tool_calls`,
Claude блоки `tool_use`/`tool_result`, Gemini `functionCall`/
`functionResponse`). Отказ HTTP 400/404/422 порождает
`NativeToolsUnavailable`: Agent переходит на текстовый протокол, только если он ещё
не выполнил ни одного инструмента.

Имена инструментов нормализуются для API, которые не допускают
точку (`filesystem.read_file` → `filesystem__read_file`) и возвращаются к
внутреннему имени в ответе: policy, аудит и тесты всегда видят исходное
имя.

Текст остаётся fallback для моделей, которые не поддерживают нативные инструменты;
`model.native_tools: false` принудительно включает его (или `--no-native-tools` из CLI).

| провайдер | API | ключ | примечания |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | host по умолчанию `localhost:11434` |
| `lmstudio` | `/v1/chat/completions` (OpenAI) | опционально `LMSTUDIO_API_KEY` | host по умолчанию `localhost:1234/v1` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `openai` / `chatgpt` | `/v1/chat/completions` | `OPENAI_API_KEY` | ChatGPT через API, не по подписке |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | отдельный system, чередующиеся ходы |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, роль `model` |

Ключ читается только из окружения; `model.api_key_env` переопределяет
имя по умолчанию. `model.host` — базовый URL всех провайдеров (со
значением по умолчанию для каждого провайдера), `model.timeout` — тайм-аут HTTP (по умолчанию 120),
`model.max_tokens` используется только Claude.
`llm/factory.py` создаёт клиент и отклоняет неизвестные провайдеры или
отсутствующие ключи. Встроенные провайдеры — это spec в `llm/plugins.py`; внешний
провайдер регистрируется через entry point `hagar.llm` и фабрику
`(config, audit) -> LLMClient` (см. `PLUGINS.md`). LM Studio не
требует ключа, если он не настроен на сервере; OpenAI требует
ключ API, а не подписку ChatGPT.
DeepSeek: текущие модели — `deepseek-flash` и
`deepseek-v4-pro`; `deepseek-chat` больше не принимается.

Текущее состояние: **нативный вызов v1** с автоматическим текстовым fallback
(см. ROADMAP).

## 3.3 Модель инструментов (`core/tool_*.py`)

`ToolDefinition` описывает имя, описание, категорию, параметры,
handler, `origin` (`local` либо `mcp.<namespace>`), объявленные
`capabilities`, состояние включения и `requires_confirmation`
(нижняя граница ASK, применяемая registry).

`ToolCall` — запрос модели (`tool`, `arguments`, `id`);
`ToolResult` — структурированный результат (`tool_name`, `success`, `output`,
`error`).

`ToolRegistry` регистрирует, ищет, включает/отключает и выполняет инструменты;
предоставляет метаданные модели и является единственной точкой выполнения.

## 3.4 Agent (`core/agent.py`)

Многошаговый агентный цикл с двумя режимами:

- **нативный**: один ответ может содержать несколько вызовов; Agent ставит в очередь
  сообщение `assistant` и сообщение `tool` с id для каждого
  результата;
- **текстовый**: по одному вызову за раз, результат отправляется как
  ход `user`.

В обоих:

1. модель решает, нужен ли инструмент;
2. если не нужен, финальный ответ закрывает ход;
3. если нужен, инструмент выполняется, и результат возвращается модели;
4. лимит `max_tool_calls` действует на весь ход. Если модель
   настаивает, ход закрывается с `Agent stopped after N tool calls`
   (защита от циклов).

Если первый нативный шаг завершается ошибкой `NativeToolsUnavailable`, Agent
переходит на текстовый протокол (`llm.native_fallback`); ошибка после того, как
инструмент уже выполнен, закрывает ход с `turn.error`, без
fallback.

Каждый шаг регистрируется в аудите: вопрос, выбор инструмента, аргументы,
результат, длительность и финальный ответ. Сбой аудита не останавливает агента:
сбой сообщается в stderr.

`Agent` получает `Vault`, но пока его не использует.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

Виртуальная файловая система агента. Каждый запрос:

1. разрешается относительно текущего каталога (`resolve_path`);
2. проверяется против разрешённых корней (`effective_permissions`);
3. фильтруется действующими разрешениями, причём более специфичные корни
   переопределяют более внешние;
4. проверяется на symlink и доступное место на диске
   (`FS_Guardian`, legacy-имя).

`DirectoryPermissions` моделирует `read`, `write`, `create`, `rename`,
`delete`, `execute`; `None` означает «наследуется от внешнего корня».
Путь вне корней всегда даёт `PermissionError`.

`FileInfo` / `stat()` возвращают тип, размер в байтах, даты
создания/изменения/доступа (ISO 8601 со смещением локального времени) и
**действующие разрешения песочницы**, а не ACL операционной системы.

**Symlink для песочницы не существуют.** Hagar их не показывает, не
читает, не следует им и не удаляет: `stat`, `list_dir` и `search` их
игнорируют; `read_file`, `read_chunk` и `delete_file` отвечают “not
found”; `chdir` на symlink отвечает “Directory not found”. Битая ссылка
или ссылка наружу неотличима от несуществующего пути.

Виртуальный корень песочницы — `/home/ai`; каждый настроенный каталог
открывается как `/home/ai/<alias>`. `stat`, `list_dir`, `search`,
`read_chunk`, сообщения `write`/`create`/`mkdir`/`delete` и `chdir`
показывают только виртуальные пути: физический путь никогда не появляется
в выводе модели. Ввод `/home/ai/<alias>/...` разрешается
относительно физического каталога алиаса; относительные пути остаются
относительными к текущему каталогу.

`/home/ai` — синтетический каталог: его можно листать и делать stat, но он
не является точкой монтирования, и в него нельзя войти с `chdir`. Записи
`filesystem.sandbox` остаются путями хост-системы, абсолютными или с
`~`, если пользователь так выберет: это может быть любой существующий и
доступный каталог. Hagar не создаёт каталоги и не предполагает отдельный
домашний каталог.

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

Флага `enabled` нет: каждая допустимая запись `filesystem.sandbox`
монтируется. Неверные алиасы или разрешения, отсутствующий путь или дублирующийся путь
останавливают конфигурацию. Физические пути и внутренние имена могут
содержать пробелы; алиас — нет, потому что он должен оставаться одним
виртуальным сегментом.

`R` покрывает чтение, листинг, поиск и `stat`; `W` покрывает запись,
создание, переименование, копирование и удаление; `X` покрывает `chdir`.
Глобальные разрешения `permissions.read`/`write` остаются потолком: алиас
`RWX` не может их превысить.

## 3.6 Инструменты файловой системы (`core/filesystem_tools.py`)

```text
filesystem.read_file
filesystem.write_file
filesystem.edit_file
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

`list_dir` возвращает метаданные `FileInfo`; `read_chunk` читает побайтно
с `has_more`, `next_offset` и полными границами UTF-8; `search` использует
рекурсивный glob с ограничением числа результатов; `copy_file` требует `create`;
`rename` требует `rename` на источнике и `create` в назначении.
Возвращаемые пути всегда виртуальные (`/home/ai/<alias>/...`).
`chdir` требует `X` на алиасе.

`list_dir` возвращает не более 100 записей на страницу (`limit` максимум
500) с `offset`, `next_offset` и `has_more`; если есть другие записи,
`message` говорит `voci: riportate X di Y; per continuare usa offset=Z`.
`search` использует ту же пагинацию: `max_results` — это лимит страницы
(по умолчанию 100, максимум 500), `offset` перебирает результаты. Для больших
деревьев лучше сузить `pattern`/`path`, чем перебирать много
страниц. `read_file` принимает только файлы до `CHUNK_SIZE` (4096 байт);
сверх этого ошибка отсылает к `read_chunk()`, потому что чтение всего файла
превысило бы контекстное окно. `read_chunk` возвращает `next_offset` и
полные границы UTF-8.

`list_dir` и `search` не показывают symlink; `read_file` и `read_chunk`
трактуют их как несуществующие файлы.

`write_file` перезаписывает только существующие файлы; создание идёт через
`create_file`, который требует разрешение `create`. Обойти запрет на
создание, записав новый путь, невозможно.

`read_file`, `read_chunk` и `read_bytes` регистрируют наблюдённую версию
файла. `write_file`, `edit_file`, `delete_file` и `rename` требуют,
чтобы файл был прочитан в той же песочнице и чтобы версия не изменилась
за это время. Версия — это `(st_mtime_ns, st_size)`: кооперативная
защита от слепой перезаписи, а не CAS против гонки TOCTOU.

`edit_file` буквально заменяет `old_string` на `new_string`. По
умолчанию строка должна встречаться ровно один раз; `replace_all` допускает
несколько замен. Запись использует временный файл в той же
директории и `os.replace`, поэтому содержимое никогда не видно
наполовину записанным. Тот же атомарный механизм используют `write_file`, `write_bytes` и
`create_file`.

### Ограничения записи

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = отключено
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` — максимум на отдельную операцию
  `write_file`, `create_file` или `copy_file`;
- `min_free_bytes` — резерв места, который должен остаться после
  операции;
- `session_write_bytes` — суммарный бюджет сессии;
- `ask_over_bytes` поднимает до `ASK` операции выше порога. Preflight
  встроен в `ToolRegistry`: если даже policy говорит `ASK`,
  подтверждение запрашивается одно.

`0` отключает отдельное ограничение. Превышение `max_write_bytes`,
`session_write_bytes` или резерва даёт ошибку, а не подтверждение:
это инварианты, а не вопросы. `ask_over_bytes` — единственный уровень, который
спрашивает пользователя.

`filesystem.stat` возвращает JSON с `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. Несуществующий путь — не ошибка:
`exists: false` с применимыми разрешениями.

## 3.7 MCP (`llm/mcp_client.py`)

Клиент MCP через HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
автоматическое преобразование инструментов в `ToolDefinition` и регистрация с
пространством имён `mcp.<namespace>`.

Также поддерживает ответы `text/event-stream` (streamable HTTP) и отправляет
уведомление `notifications/initialized` после handshake. Использует
`MCP-Protocol-Version` (по умолчанию `2025-06-18`, с fallback) и повторно
использует `Mcp-Session-Id`, когда сервер его возвращает. Ошибки HTTP
включают тело ответа, чтобы сделать 400 диагностируемыми.
Результаты инструментов нормализуются в текст: блоки `text`,
иначе `structuredContent` или JSON; результат с `isError`
становится ошибкой инструмента.

Аутентификация по серверам:

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer          # или "header"
      token_env: MCP_EXAMPLE_TOKEN
      # header: X-API-Key  # только с type: header
```

Токен читается только из окружения и не появляется в аудите. Если он отсутствует,
сервер пропускается с `mcp.failed`, и harness продолжает работу; остальные
серверы остаются доступными.

### Интерактивный OAuth

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # без него — dynamic registration
    # client_secret_env: MCP_CLIENT_SECRET
    scopes: [mcp.read]
    audience: api.atlassian.com  # опционально, для провайдеров 3LO
    redirect_port: 8765       # 0 = случайный порт
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

Поток authorization code + PKCE с callback на
`http://localhost:<port>/oauth/callback` и открытием браузера. Если
scope содержит `offline_access`, добавляется `prompt=consent`.
Метаданные обнаруживаются из `.well-known` (RFC 9728 для
ресурса, RFC 8414 для authorization server); если `client_id` отсутствует,
используется динамическая регистрация. Токены хранятся в локальном файле с
ограниченными правами (`0600` там, где система их поддерживает), с автоматическим
обновлением и однократным повтором при `401`.

Ctrl-C во время ожидания callback закрывает локальный сервер и выходит
с кодом 130, без traceback.

Ограничения: нет device flow, DPoP, mTLS или client assertion; браузер должен
иметь возможность достичь локального callback. Если callback не приходит,
терминал предлагает вставить URL перенаправления.

## 3.8 Vault (`memory/vault.py`)

Доступ к хранилищу Obsidian с путями относительно корня и
защитой от выхода за пределы хранилища. Предоставляет чтение, запись, append,
листинг файлов и `load_all` для рекурсивного чтения. Семантика
памяти находится в `memory/store.py` (§3.11).

## 3.9 Журнал аудита (`core/audit.py`)

Файл JSON Lines append-only. Каждая строка содержит метку времени UTC, `session` и
`event`; события одного вопроса разделяют id `turn`.

```text
harness.start      провайдер, модель, корни, разрешения, инструменты, vault
turn.start         вопрос, лимит инструментов, нативный режим
llm.tool_choice    выбор модели, аргументы, mode=native
llm.native_fallback провайдер без нативных инструментов, переход к тексту
llm.protocol_error несоответствующий ответ (текст целиком, усечённый)
llm.repaired       успешное исправление
llm.repair_failed  неудачное исправление
tool.call          инструмент, аргументы, индекс
tool.result        результат, вывод/ошибка, длительность в ms
turn.answer        финальный ответ, число использованных инструментов
turn.error         фаза и сообщение
turn.stop          достигнут лимит
mcp.loaded         пространство имён и импортированные инструменты
mcp.failed         пространство имён и ошибка
llm.failed         провайдер не может быть создан (например, отсутствует ключ)
harness.stop       чистое завершение (если его нет, процесс был убит)
memory.enabled     корень, подкаталог, ходы контекста
memory.disabled    причина отключения
memory.context     ходы и навыки, внедрённые в промпт
memory.turn        ход, сохранённый в vault
memory.failed      фаза и ошибка
```

Свойства:

- запись best effort: ошибка ввода-вывода не останавливает harness и
  сообщается один раз в stderr;
- настраиваемое усечение (`audit.max_field_chars`, по умолчанию 2000);
- цепочка хешей (`prev`/`hash`), проверяемая через `verify_chain`;
- ротация в `<file>.<timestamp>` сверх `audit.max_bytes` (0 отключает);
- retention: `audit.max_files` (по умолчанию 100) хранит не более N файлов,
  включая активный; самые старые резервные копии удаляются;
- при `audit.include_outputs: false` вывод инструментов регистрируется
  только как размер;
- значения, не являющиеся JSON, приводятся к сериализуемому виду;
- никаких ключей API в журнале;
- журнал содержит также вывод инструментов (то есть содержимое файлов):
  его нужно защищать так же, как workspace.

## 3.10 Разрешения (`core/permissions.py`)

Модель — это матрица субъект × объект:

- **Capability** (`IntFlag`): что может делать операция
  (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`, `FILESYSTEM_CREATE`,
  `FILESYSTEM_DELETE`, `FILESYSTEM_EXEC`, `MEMORY_READ`,
  `MEMORY_WRITE`, `NETWORK`, `MCP_CALL`, `COMPUTE`). Они комбинируются через `|`;
  проверка всегда на вложенность (подмножество).
- **Effect** (`IntEnum`): `ALLOW`, `ASK`, `DENY`. При конфликте
  побеждает большее значение (`DENY > ASK > ALLOW`).
- **Rule**: capability + эффект + необязательные фильтры `tools` (glob),
  `paths` и `namespaces` (префиксы) + `reason`.
- **Subject**: кто запрашивает (агент, пользователь, система), с правилами и
  default (`DENY`, если не указано).
- **Resource**: объект решения (пока это инструмент с его
  capability; в будущем также заметки и пути).
- **Decision**: эффект, причина и применённое правило.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. ресурс должен предоставлять требуемые capability;
2. **системный потолок** (производный от `permissions.read/write/shell`)
   должен их разрешать;
3. для каждой capability применяются правила субъекта: побеждает
   наиболее специфичное (число фильтров, затем длина префикса), при
   равенстве — более строгий эффект; без правил действует default;
4. при нескольких требуемых capability действует AND: побеждает худший эффект.

`ASK` — не решение: это вопрос человеку.
`ConfirmationProvider` его задаёт — `ConsoleConfirmation` спрашивает
`lo faccio? (y/N)` со значением по умолчанию N — а без канала подтверждения действует
`DENY`. GUI может реализовать тот же протокол с модальным диалогом.

В CLI `core/input_broker.py` — единственный владелец консоли:
он распределяет prompt, подтверждения и клавиши `F5`/`F8`, задаёт заголовок
терминала как сигнал внимания и восстанавливает нормальный режим в
конце. На неинтерактивном stdin он возвращается к `input()`.

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

`policy.yaml` читается **до** создания LLM. Если он не
читается или недействителен, harness применяет `DENY` ко всем политикам,
регистрирует это в аудите (`policy.failed`) и сообщает в чате; остальная часть
harness продолжает работать. Отсутствующий субъект также деградирует до
`DENY`.

Проверка выполняется в `ToolRegistry.execute`, единственной точке
выполнения, и порождает события `permission.decision` и
`permission.confirmation`.

Область `paths` сравнивает путь, **записанный моделью**
(нормализованный), а не тот, что разрешён песочницей: абсолютный путь или
`chdir` могут не соответствовать относительному префиксу, и
результат остаётся `DENY` (fail closed).

## 3.11 Память (`memory/store.py`, `memory/tools.py`)

**Бэкенд по умолчанию: SQLite.** `memory/sqlite_store.py` и
`memory/database.py` используют локальную базу данных (`%LOCALAPPDATA%/Hagar/memory.db`
или `HAGAR_MEMORY_DB`) как источник истины для сессий, ходов, навыков и
сводок. SQLite использует WAL, транзакции и `busy_timeout`; резервное копирование —
`VACUUM INTO`. Описанный ниже бэкенд `markdown` остаётся доступным
только для совместимости и больше не является значением по умолчанию.

**Эпизодическая память.** Harness ставит в очередь каждый завершённый ход в заметку
для сессии:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter с `session`, `type: chat`, `created`; тело с
разделом на ход (`## <timestamp> · <turn>`), вопрос и ответ. Выводы
инструментов не сохраняются: они остаются в аудите.

В начале каждого хода Agent внедряет в промпт последние
`memory.context_turns` ходов (0 отключает внедрение), усекая
вопрос и ответ. При `memory.context_skills > 0` он добавляет до N
**подтверждённых навыков**, релевантных вопросу, по лексическому совпадению
заголовка, tags и содержимого; кандидаты и архивные никогда не входят.
Блок помечается как данные, а не инструкции. Ошибка памяти
не останавливает ход: регистрируется `memory.failed`.

**Семантика.** Модель может предложить память с помощью трёх инструментов:

| инструмент | capability | namespace |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

`create_skill` пишет `<vault>/Hagar/skills/<slug>.md` с frontmatter
`id`, `title`, `kind` (`fact`/`procedure`), `status: candidate`, `tags`,
`source_session`, `source_turn`, `model`, `created_at`. Slug
безопасен (только ASCII, без путей); существующий заголовок не
перезаписывается и возвращает `duplicate: true`.

`get_context` возвращает последние ходы или ищет по ключевому слову
в прошлых сессиях; `list_skills` фильтрует по `kind` и `status`.

**Жизненный цикл.** Состояния: `candidate`, `confirmed`, `archived`.
LLM создаёт только кандидатов; переход выполняет человек из CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` показывает по одному кандидату с provenance и
содержимым, затем спрашивает `y/N/a/s/q` (подтвердить, оставить, архивировать, пропустить,
выйти). Подтверждение записывает `reviewed_at`; `archive` обратим с помощью
`confirm`. Каждый переход порождает `memory.status` или `memory.review`
в аудите. Заметки остаются файлами Obsidian: изменение `status` во
frontmatter даёт тот же эффект.

**Конфигурация**:

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

### Память проекта

Память проекта отделена от навыков:

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

У каждого проекта есть `index.md` со статусом, последней активностью, сводкой и
счётчиком активных решений. У каждого решения есть состояние
`candidate`/`active`/`superseded`/`archived`, альтернативы, обоснование,
provenance и `auto_saved`. Решения не перезаписываются: новое
решение может заменить старое.

При `memory.backend: sqlite` проекты и решения используют таблицы
`projects` и `decisions` той же базы данных; legacy-бэкенд Markdown
продолжает использовать Vault.

При запуске Hagar показывает активные проекты и «свободную деятельность»:

```text
/project list
/project new <имя>
/project select <имя>
/project free
/project status
/project archive <имя>
/project unarchive <имя>
```

Неинтерактивные переопределения — `--project <имя>` и `--free`.

В конце сессии:

1. транскрипт перемещается в `archive/chat/`;
2. генерируется сводка моделью, с механическим fallback;
3. сводка сохраняется со ссылкой и хешем транскрипта;
4. если есть проект, LLM предлагает решения `candidate`;
5. пользователь может их просмотреть; при отказе они остаются `candidate` с
   `auto_saved: true`.

Внедряемый контекст использует **индекс** проекта: сводку, заголовки
активных решений и счётчик, а не все тела. Детали
читаются через `memory.project_context(query=..., limit=...)`. Общий блок
ограничен `max_context_chars`; если он обрезан,
аудит регистрирует `memory.context_trimmed`. Это не оценка токенов, а
бюджет в символах, детерминированный.

Когда проект превышает `project_max_active`, Hagar спрашивает, не
архивировать ли его. Архивирование обратимо и ничего не удаляет.

**Просмотр архива.** У архивных транскриптов есть `project`
во frontmatter. Поиск и чтение выполняются по запросу:

```text
/memory archive search <текст>
/memory archive read <session> [offset] [limit]
```

Те же инструменты доступны как `memory.archive_search` и
`memory.archive_read`; поиск возвращает session, turn, timestamp,
проект и snippet, чтение постранично отдаёт ходы. Автоматического внедрения
архива в промпт нет: сводка остаётся индексом, а
транскрипт — источником, к которому обращаются при необходимости.

Если `vault.path` не существует или недоступен для записи, память
отключается с предупреждением в чате и `memory.disabled` в аудите; остальные
компоненты продолжают работать. Записи памяти подчиняются
политикам (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.11.1 Слой сервисов (`core/service.py`)

`HarnessService` — стабильный API над `Harness`: он не читает из
`input()`, не пишет в stdout и не знает о CLI. Предоставляет:

- `ask(question)` с событиями `turn.start`, `turn.answer`, `turn.error`;
- события инструментов и разрешений, переданные из `Agent` и `ToolRegistry`:
  `tool.call`, `tool.result`, `permission.decision`,
  `permission.confirmation`;
- `status()` с моделью, проектом, памятью, аудитом, policy и инструментами;
- `list_projects()`, `current_project()`, `set_project()`,
  `clear_project()`, `create_project()`;
- `finish_session()`.

События — это `ServiceEvent(type, data, ts)`, и их может потреблять
sink (CLI, GUI, тесты). Текущий CLI использует сервис для ходов,
выбора проекта и закрытия сессии.

## 3.11.2 Сервис команд (`core/command_service.py`)

`CommandService` превращает слэш-команды в `CommandResult`:

```text
command, ok, lines, data, error, requires_input
```

Он обрабатывает `/help`, `/tools`, `/status`, `/mcp`, `/audit`, `/project` и
`/memory`, не записывая в stdout. CLI печатает `lines`; GUI будет использовать
`data`. Интерактивная проверка `/memory` остаётся за `MemoryCLI`,
потому что требует человеческого ввода. CLI использует сервис команд для всех
слэш-команд, кроме `/memory review`.

## 3.11.3 Веб-GUI (`core/web.py`)

`hagar web` запускает локальный `ThreadingHTTPServer` с:

- `GET /` — страница чата;
- `GET /static/style.css` и `/static/app.js` (ресурсы в `web/`);
- `GET /api/events` — поток SSE;
- `POST /api/message`, `/api/confirm`, `/api/project`, `/api/stop`,
  `/api/new-chat`, `/api/resume`;
- `GET /api/status`, `/api/projects`, `/api/pending`;
- `GET /api/history`, `/api/history/<session>`;
- `GET /api/tools`, `/api/audit`, `/api/thinking`;
- `GET /api/memories`, `/api/memory?path=...`.

Вкладки GUI: Chat, Chat history, Tool output, Audit, Thinking и
Memories. Боковая панель содержит проект, состояние и токены; история — во
вкладке, выделенной для неё. `SessionLog` хранит события сессии для Tool
output и временной шкалы; Audit читает JSONL; Thinking отдаёт предпочтение
рассуждениям, предоставленным провайдером, а иначе показывает временную шкалу. Memories
читает индекс, исключая чаты, архив и сводки.

Щелчок по прошлому чату вызывает `POST /api/resume`: транскрипт
перезагружается, а сессия аудита/памяти возвращается к тому id, так что
новые ходы продолжают тот же чат. `POST /api/new-chat` вызывает
`MemoryStore.new_session()` и меняет сессию, не затрагивая предыдущие
транскрипты.

Статические ресурсы находятся в `web/` (`index.html`, `style.css`,
`app.js`). `render_index()` вставляет только токен; остальное отдаётся
как есть, с whitelist и через `importlib.resources`.

GUI — это адаптер: он использует `HarnessService`, `CommandService` и
`QueueConfirmationProvider`. Подтверждения ASK блокируют поток хода
на `threading.Event`; сервер остаётся свободным и разблокирует запрос через
`POST /api/confirm`. Тайм-аут считается отказом.

Боковая панель показывает суммарные токены сессии: `UsageLedger` получает
usage от каждого вызова LLM через `usage_sink` и публикует
`usage.updated` через SSE.

**Stop:** `POST /api/stop` вызывает `Agent.cancel()`; агент проверяет
событие между шагами и возбуждает `AgentCancelled`. Ход
прерывается кооперативно и не обрывает уже выполняющийся HTTP-запрос.

**Vision:** `POST /api/message` принимает `images` как data URL
PNG/JPEG/WebP (максимум 4, по 10 MB); тело JSON может достигать
64 MB. `core/images.py` проверяет и конвертирует; `Agent.ask(question,
images=...)` строит мультимодальный content. Адаптеры,
совместимые с OpenAI/LM Studio, используют `image_url`; Claude использует блоки
`image`; Gemini использует `inlineData`. LM Studio не принимает WebP
напрямую: GUI конвертирует его в PNG. Изображение не попадает ни в
память Markdown, ни в аудит.

Безопасность: bind по умолчанию `127.0.0.1`, случайный токен, внедрённый в
страницу, заголовок `X-Hagar-Token` для API и `?token=` для SSE. Он не
многопользовательский и пока не предоставляет изменение Vault.

## 3.11.6 Ввод изображений (`core/images.py`)

`ImageInput` проверяет data URL, MIME и размер; `Agent.ask` использует канонические
части (`text`, `image`), и каждый бэкенд переводит их в свой
формат. Текст остановки и изображений отделён от постоянного
содержимого: память сохраняет только вопрос и ответ.

`vision.open` читает изображение из песочницы, проверяет его по magic number
и возвращает как `ToolResult.images`. Цикл `Agent` прикрепляет
изображение к синтетическому сообщению пользователя перед следующим
вызовом, поэтому модель видит его, не получая base64 в тексте
инструмента. Ограничения: 4 изображения на ход, 10 MB на изображение, PNG/JPEG/WebP.
Ребёнок может использовать `vision.open` в своём workspace только для чтения.

Аудио не реализовано. Канал вложений можно было бы переиспользовать, но
нужны другой контракт провайдера с нативной поддержкой аудио, форматы/декодеры и
явный выбор между ASR и пониманием аудио; это в roadmap без
сроков.

`memory/export.py` экспортирует базу данных SQLite в Markdown:
`Hagar/chat/`, `Hagar/skills/`, `Hagar/summaries/`,
`Hagar/projects/<id>/index.md` и `decisions/`. Запись атомарна
(temp + `os.replace`), и команда отклоняет непустое назначение
без `--force`.

`memory_fts` — таблица FTS5 в той же базе данных, с колонками
`entity`, `entity_id`, `kind`, `project`, `status`, `title`, `body`.
`SqliteMemoryIndex.search` использует `MATCH`, `bm25()` и `snippet()`; если FTS5
недоступен, он возвращается к `LIKE`. `memory/import_markdown.py` импортирует
ту же структуру с upsert и перестраивает индекс FTS.

## 3.11.4 Использование токенов (`core/usage.py`)

`TokenUsage` нормализует input, output, cache и reasoning. Функции
`usage_from_openai`, `usage_from_anthropic`, `usage_from_gemini` и
`usage_from_ollama` читают нативные поля ответов.

`LLMClient._set_usage()` обновляет `last_usage` и вызывает `usage_sink`
клиента. `HarnessService` владеет `UsageLedger`, связывает его с
клиентом и публикует `usage.updated`; GUI использует это в боковой панели, а `/usage`
читает из CLI. Usage провайдера — это
истина; локальная оценка остаётся только fallback.

## 3.11.5 Индекс памяти (`memory/index.py`)

`MemoryIndex` — это индекс SQLite, производный от Markdown Vault:

- таблицы `documents`, `meta` и `documents_fts` (FTS5);
- инкрементальная синхронизация по hash/mtime/size;
- `rebuild()` перестраивает с нуля;
- поиск с фильтрами `project`, `kind`, `status`;
- fallback `LIKE`, если FTS5 недоступен;
- база данных в локальных данных приложения, а не в синхронизируемом Vault.

Инструмент `memory.search` использует индекс; `/memory reindex` и `/memory stats`
предоставляют обслуживание и состояние. С бэкендом SQLite по умолчанию
источником истины является `memory.db`; старый `MemoryIndex` остаётся только для
legacy-бэкенда Markdown.

## 3.11.7 Инструменты решений (`core/decisions.py`)

`DecisionRegistry` выбирает `DecisionProvider`, а `decision.choose`
открывает выбор модели. Встроенные провайдеры:

- `llm`: запрашивает у клиента LLM JSON с `choice` и `probabilities`,
  проверяет метки и нормализует вероятности;
- `linear`: загружает локальную JSON-модель с метками, весами и bias и использует
  softmax для получения вероятностей.

Capability `DECISION` отделена от `COMPUTE`, `NETWORK` и
`FILESYSTEM_*`; подробности и формат модели — в
`DECISIONS.md`. Jev/Kev пока не имеют нативных адаптеров.

## 3.11.8 Hi-Fi (`core/hifi.py`)

`HiFiResolver` выполняет pre-pass перед агентным циклом:

1. запрашивает у модели интерпретации с вероятностями;
2. нормализует и сортирует вероятности;
3. если разрыв между первой и второй превышает `hifi.margin`, заменяет
   запрос выбранной интерпретацией плюс исходный текст;
4. иначе задаёт модели уточняющий вопрос.

Событие `hifi.interpretations` регистрирует вероятности и возможное
уточнение. Невалидный JSON порождает `hifi.failed`, и ход
продолжается без pre-pass.

## 3.11.9 Checkpoint (`core/checkpoints.py`)

`HarnessService.ask` открывает `WorkspaceCheckpoint` на песочнице. Checkpoint
не копирует workspace: он только отмечает файлы, которые собирается
изменить мутация. `delete_file`, `rename` и `copy_file` также регистрируют
назначение. `/undo` восстанавливает последний завершённый checkpoint.

Ограничение: 32 MB снимка, только обычные файлы, только последний ход.
Если checkpoint неполон, undo отклоняется.

## 3.11.10 Runtime-защиты и контекст (`core/tool_registry.py`, `core/context.py`)

`ToolRegistry` применяет:

- `tools.timeout` на отдельный вызов, через демонический worker;
- `tools.repeat_limit` по хешу `tool + аргументы` на ход.

Тайм-аут best effort: уже запущенный Python-handler не убивается. Repeat guard
сбрасывает счётчик при каждом `Agent.ask`.

`OutputSpiller` переносит выводы длиннее 12 000 символов в `ArtifactStore`
и возвращает сводку с `artifact_id`. `ContextCompactor` заменяет более старые
сообщения, когда контекст превышает 24 000 символов, сохраняя последние 8
и системные сообщения.

## 3.11.11 AIsh (`core/aish.py`, `local_tools/aish_tool.py`)

`aish.exec` реализует язык команд, а не host shell. `AishExecutor`
парсит через `shlex`, отвергает перенаправления, операторы, переменные
и command substitution и переводит каждую команду в вызов
`ToolRegistry`. Capability `AISH` запрещена политикой по умолчанию;
чтобы включить её, нужно явное изменение:

```yaml
- capabilities: [AISH]
  effect: allow
  tools: ["aish.*"]
```

Внутренние команды сохраняют правила нижележащих инструментов: включение
`aish.exec` не включает `filesystem.delete_file`.

## 3.11.12 `text.transform` (`local_tools/text_transform_tool.py`)

Инструмент только для чтения с перечислимыми операциями: `grep`, `sort`, `uniq`, `cut`,
`tr`, `wc`, `head`, `tail`, `sed_replace`. Принимает путь песочницы
или inline-текст; применяет лимиты на вход, вывод, pattern и совпадения.

Capability:

```text
FILESYSTEM_READ | COMPUTE
```

Не пишет файлы. AIsh использует его для текстовых команд; сохранение
результата идёт через `filesystem.write_file`/`create_file` с gate
read-before-write.

## 3.11.13 `dev.run` (`core/dev_recipes.py`, `core/dev_runner.py`)

`DevRecipeLoader` читает `recipes.yaml` один раз при запуске и
сохраняет неизменяемый snapshot с хешем. Файл должен находиться вне
записываемой песочницы.

`DevRunner` выполняет рецепт:

- проверяет типизированные параметры и `cwd`;
- копирует проект во временный каталог;
- выполняет один argv с `shell=False`;
- использует минимальное окружение;
- применяет timeout и kill process group;
- разделяет stdout/stderr;
- ограничивает вывод;
- записывает аудит.

Capability `DEV_EXEC` по умолчанию DENY. `dev.run` не принимает произвольные
команды и не использует контейнеры: рецепты доверенные; песочница не
изолирует host-процесс. Контейнер остаётся замороженным для будущего
прямого доступа к реальным файловым системам/программам.

## 3.11.14 Boxed transform (`core/boxes.py`)

Box — это ограниченные LLM-функции с фиксированным промптом, вводом/выводом в файлы
и без памяти, инструментов или автономности.

Инструменты:

```text
box.list
box.run
```

Начальные box:

```text
summarize
translate
extract_json
```

`BoxRunner` читает input из песочницы, применяет chunking где нужно,
вызывает LLM-клиент, проверяет выходной JSON и записывает результат с
gate read-before-write. `BOX_EXEC` по умолчанию DENY.

## 3.11.15 Hagar Flow (`core/flow/`)

`validate()` парсит код через `ast.parse`, отвергает import, классы,
функции, lambda, try, dict/set comprehension, comprehension с более чем
одним `for`, dunder и динамические вызовы, а также проверяет доступные
примитивы. List comprehension с одним `for` и необязательными `if`
поддерживаются.

`FlowRunner` интерпретирует проверенный AST без `eval`/`exec`:

- линейная область видимости;
- бюджет шагов, итераций, tool call и timeout;
- примитивы `fs.*`, `box.*`, `memory.*` и `project.context`, переданные
  из внутреннего registry;
- policy и подтверждения для каждого примитива;
- ошибки с строкой и столбцом.

`FLOW_EXEC` по умолчанию DENY. `flow.run` никогда не исправляет код:
`flow.repair` предлагает валидного кандидата без его выполнения, максимум
`flow.repair_attempts` попыток. Ошибки runtime, policy, подтверждения
и timeout не исправляются. HIR пока отсутствует:
проверенный AST — это IR MVP.

## 3.12 Запуск и упаковка

Проект устанавливается через `pip install -e .` и объявляет пакеты в
`pyproject.toml`. Entry point — `hagar = "hagar:main"`. Текущая версия —
`0.7.0`.

Пример конфигурации — `hagar.example.yaml`; `hagar.yaml` — это локальный
файл, игнорируемый git. Vault по умолчанию в примере —
`./vault`, и его нужно создать до запуска.

```text
hagar --config PATH       файл конфигурации
hagar --model NAME        переопределяет model.name
hagar --project NAME      выбирает активный проект
hagar --free              запускает в свободной деятельности
hagar --no-memory         отключает память для сессии
hagar --no-native-tools   использует текстовый JSON-протокол
hagar --version
```

Конфигурация ищется в таком порядке: `--config`, переменная
`HAGAR_CONFIG`, `./hagar.yaml`. `python -m hagar` работает из
каталога проекта.

CI GitHub Actions запускает набор тестов на Linux, macOS и Windows с
Python 3.11/3.12/3.13, собирает sdist и wheel, запускает `twine check` и
проверяет установку wheel. Workflow `Release` запускается от тега
`v*`, проверяет, что тег соответствует версии пакета, и
создаёт релиз GitHub с артефактами.

Живые тесты исключены из обычного набора и включаются через
`--live`: они проверяют Ollama и удалённые провайдеры (последние только если
ключ API присутствует).

## 3.13 Локальные инструменты (`local_tools/`)

Это не серверы MCP: это локальные провайдеры, которые регистрируют `ToolDefinition`
в registry и живут вне core, в отдельном пакете.

| модуль | инструмент | capability |
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

- `clock.now` возвращает локальное время, дату, часовой пояс, смещение UTC и epoch.
- `calendar.date` преобразует локальную дату, или необязательную дату ISO, в
  пролептический юлианский календарь или в табличный исламский календарь
  (Kuwaiti algorithm). Табличный исламский календарь может отличаться на
  один день от основанных на наблюдении или на Umm al-Qura.
- `think.echo` возвращает ровно полученную строку; он служит для
  вынесения промежуточного шага в цепочках рассуждений.
- `text.diff` возвращает унифицированный diff между двумя текстами, с входом
  максимум 20000 символов, выводом максимум 20000 и `context` 0..10. Он не
  применяет diff.
- `url.parse` разбирает scheme, host, порт, path, query и fragment без
  DNS или сети; ограничивает URL 4096 символами, а параметры — 100. Если
  URL содержит учётные данные, он их скрывает в выводе.
- `clock`, `calendar`, `think`, `text` и `url` не обращаются к файловой системе
  или сети и попадают под правило `COMPUTE` allow.
- Калькулятор использует whitelist AST, а не `eval()`, с ограничениями на
  выражение, число узлов и показатель степени.
- `feed.read` скачивает через `requests` (тайм-аут 15 с, максимум 5 MB), принимает
  только URL http/https и использует `feedparser`; политика `NETWORK` — `ask`.
- SSRF: каждый хост разрешается через `getaddrinfo`, и каждый адрес должен
  быть глобальным; loopback, частные сети, link-local, multicast и
  зарезервированные отклоняются. Перенаправления не автоматические: каждый
  `Location` повторно проверяется, и они прекращаются после 3 переходов. URL с
  учётными данными отклоняется.
- `permissions.network: true` необходимо, чтобы системный потолок
  предоставлял `NETWORK`; `COMPUTE` всегда в потолке, но policy может его запретить.
- `permissions.agents: true` необходимо для `AGENT_SPAWN`; policy
  должна также разрешать `agent.*`.
- `local_tools` объявлен в `pyproject.toml` и устанавливается вместе с
  проектом.

Встроенные инструменты регистрируются в `local_tools/plugins.py` через
тот же контракт `ToolPlugin`, что и внешние плагины. Внешние плагины
обнаруживаются через entry point `hagar.tools` и получают `PluginContext`.
Policy и песочница остаются в registry: плагин не может выдавать
разрешения. Неисправный плагин пропускается и регистрируется в аудите, не
останавливая остальные.

## 3.14 Плагины

`core/plugins.py` определяет:

- `ToolPlugin` + `PluginContext` для инструментов;
- `LLMProvider` для провайдеров LLM;
- обнаружение через `importlib.metadata.entry_points`;
- изоляцию ошибок и аудит `plugin.loaded`/`plugin.error`.

Встроенные провайдеры находятся в `llm/plugins.py` и регистрируются раньше
внешних. Внешний провайдер не может заменить встроенное имя.
Плагины Python доверенные и работают внутри процесса; для недоверенных
расширений границей остаётся MCP или отдельный процесс. Полный контракт
находится в `PLUGINS.md`.

## 3.15 Асинхронные субагенты

`core/subagents.py` реализует:

- `agent.spawn/status/wait/result/cancel` и синхронный `agent.run`;
- обязательный `reason` при spawn, регистрируемый в аудите;
- отдельная capability `AGENT_SPAWN`: ребёнок её не получает и не может
  создавать других агентов;
- строго более ограничительная политика ребёнка; одинаковые или более
  широкие политики отклоняются с `SubagentPolicyError`;
- абсолютный тайм-аут 5 минут, кооперативный, с состоянием `timed_out`;
- `agent_id` во всех событиях аудита родителя, ребёнка и
  registry;
- до двух одновременных субагентов;
- та же локальная модель, но отдельный клиент LLM;
- приватное временное рабочее пространство для каждого ребёнка;
- входные данные, скопированные из рабочего пространства родителя;
- outbox `artifact.put`/`artifact.put_file` и `mailbox.send` для
  ребёнка;
- временное хранилище artifact (максимум 50 MB на artifact, 256 MB на ход)
  и mailbox в памяти (максимум 64 KB на сообщение);
- ограниченное чтение родителем через `artifact.read`, `artifact.list`,
  `mailbox.inbox/read/ack`;
- `artifact.save_to` копирует artifact целиком в доступный для записи путь
  песочницы родителя, не проходя через контекст;
- capability `AGENT_DATA`;
- registry, отфильтрованный до `FILESYSTEM_READ`, `MEMORY_READ`, `COMPUTE` и
  `AGENT_DATA`;
- исключение `filesystem.chdir` и `agent.*`;
- никакой записи в память;
- ASK ребёнка передаются пользователю через `ParentBridgeConfirmation`,
  тайм-аут 180 секунд и DENY по истечении срока; родительская LLM не одобряет;
- отдельный usage;
- аудит `agent.spawned/started/finished/cancelled/failed`;
- в конце хода `artifact.discarded` для неэкспортированного artifact, с
  причиной `unread` или `read_but_not_saved` и метаданными без содержимого;
- очистка рабочих пространств и заданий в конце хода.

`AuditLog.record` сериализуется блокировкой для конкурентных записей.
Пока нет экспорта artifact, бюджета токенов/времени, вложенности или
отдельного GUI. Подробности — в `SUBAGENTS.md`.

---

# 4. Модель безопасности

- Агент не видит реальную файловую систему: только пути, разрешённые внутри
  песочницы.
- Операции проходят только через `ToolRegistry`; никакого shell хоста.
- Разрешения объявлены в конфигурации и в политиках и
  применяются песочницей и `PermissionEvaluator`; вложенные корни
  могут сужать разрешения.
- Ошибки — это данные: отказ возвращается модели как
  результат инструмента, а не скрывается.
- Каждое действие оставляет след в аудите, с сессией и ходом.

---

# 5. Разработка

- Набор тестов: `./tools/run_tests.sh` (Linux/macOS) или
  `.\tools\run_tests.ps1` (Windows). В Windows: 892 пройдено, 2 пропущено
  (symlink недоступны без Developer Mode). В Debian Linux
  (2026-11-12): все тесты зелёные, включая symlink (894 пройдено, 0
  пропущено). Подробности и обоснование shim — в README §3.1.
- Живые тесты: `./tools/run_tests.sh --live` (Linux/macOS) или
  `.\tools\run_tests.ps1 --live` (Windows) — 9 дополнительных тестов (Ollama;
  удалённые провайдеры, если ключи присутствуют).
- Сравнение моделей: `python tools/bench_models.py` (README §3.5).
- Сравнение протоколов: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- Обычный набор тестов не обращается к сети: Ollama и MCP имитируются.

## 5.1 Мультиплатформенность

- Внутренние пути используют `pathlib.Path`; пути, показываемые агенту,
  всегда используют `/` и виртуальный корень `/home/ai`.
- `filesystem.sandbox` содержит пути хост-системы, абсолютные или с
  `~`, если пользователь так выберет: `Path.expanduser()` разрешает home только
  когда путь его использует. Не предполагается, что отдельный домашний каталог существует.
- У каждого монтирования есть явный и уникальный алиас (без учёта регистра);
  физический путь может находиться на любом томе.
- `tools/run_tests.sh` — POSIX runner; `tools/run_tests.ps1` и
  `tools/pytest_shim` нужны только для песочницы Windows с ограниченным
  токеном.
- Единственная оставшаяся явно Windows-ветка — дата создания в
  `stat`: `st_birthtime`, где доступна, иначе `st_ctime` в
  Windows; в Linux `created_at` может быть `None`.
- Внешние API (OAuth, MCP, LLM) используют HTTP и `webbrowser`, а не
  системные команды.
- CI GitHub Actions покрывает Linux, macOS и Windows на Python
  3.11/3.12/3.13; symlink, разрешения токенов OAuth и loopback callback
  ещё предстоит проверить живыми тестами, а не в офлайн-наборе.

---

# 6. Известные ограничения и технический долг

- `PermissionEvaluator` покрывает v1: остаются динамические субъекты,
  подтверждения GUI и capability MCP, назначаемые конфигурацией.
- Нативный вызов зависит от модели: некоторые игнорируют инструменты или
  возвращают несколько вызовов; текстовый fallback покрывает ошибки, но не
  качество выбора.
- Клиент MCP поддерживает bearer/header и OAuth authorization code; он не
  поддерживает device flow, DPoP, mTLS или client assertion.
- Проверка навыков выполняется вручную из CLI; GUI отсутствует.
- Поиск в памяти — по ключевому слову, без индекса и
  embedding.
- Внедряемый контекст использует глобальные последние ходы и до 3 подтверждённых
  навыков по лексическому совпадению, без семантического отбора.
- Память не удаляет чаты или навыки по давности: `archive` —
  единственное удаление из контекста.
- Аудит имеет ротацию и retention (`max_files`), но не компактификацию
  сессий и не внешнюю привязку цепочки.
- `feed.read` проверяет адреса и перенаправления, но остаётся случай DNS
  rebinding: `requests` разрешает имя второй раз в момент
  соединения; нужен закреплённый resolver.
- Калькулятор — не CAS: он обрабатывает только ограниченные числовые
  выражения, не символьные.
- `stat().created_at` равен `None` в Linux, когда отсутствует `st_birthtime`;
  дата создания не выдумывается.
- Два алиаса не могут указывать на один физический путь: алиас
  идентифицирует монтирование, а виртуальный вывод должен оставаться однозначным.

## 6.1 Ответственность пользователя: hard link, mount и TOCTOU

**Hagar не контролирует hard link, mount/junction и гонки TOCTOU
внутри разрешённых каталогов.** Это не дефект Hagar: песочница
основана на путях и не использует handle/file descriptor на всю операцию.

Hard link — это второе имя того же inode, у него нет целевого
пути, и песочница не может знать, существует ли другое имя снаружи. Mount
или junction может открыть другую файловую систему, оставаясь внутри
префикса пути. Гонка TOCTOU может изменить компонент между
проверкой symlink и реальной операцией: Hagar не использует `openat2`,
`O_NOFOLLOW` на каждом компоненте или Windows handle, поэтому не гарантирует
атомарность между проверкой и доступом.

Инструменты файловой системы Hagar не создают hard link. Если hard link или
mount уже существует внутри каталога песочницы, Hagar трактует его как
обычный файл или каталог и может его прочитать, изменить или удалить его
внутреннее имя.

Таким образом, ответственность разделена:

- **Hagar гарантирует**, что разрешённые пути остаются внутри алиаса на
  момент проверки, что symlink невидимы, что разрешения
  `R`/`W`/`X` применяются и что реальные пути не попадают
  в вывод модели.
- **Пользователь гарантирует**, что каталоги, настроенные в
  `filesystem.sandbox`, не содержат hard link, mount или junction к
  содержимому, которое не должно быть доступно, и что никакой недоверенный
  конкурентный процесс не может изменить эти каталоги во время
  выполнения, если ему нужна полная изоляция.

Гонки TOCTOU требуют локального конкурентного участника с доступом на
запись к каталогам песочницы: это не случайность обычного
использования, а злонамеренный сценарий или сценарий скомпрометированной среды.
Для сильной изоляции нужны выделенный том, отдельный пользователь,
mount namespace или контейнер; это не задача resolver путей.

Эти пункты закрыты как **ответственность пользователя**, а не как технический
долг Hagar. Hard link, mount/junction и гонки TOCTOU не
обнаруживаются и не блокируются этой версией.

---

# 7. Карта документации

- `MANUAL.md` — руководство пользователя: команды, конфигурация, policy, значения по умолчанию.
- `ARCHITECTURE.md` — этот документ: какая система сегодня.
- `ROADMAP.md` — что делать, принятые решения и открытые вопросы.
- `PLUGINS.md` — контракты для инструментов и провайдеров LLM-плагинов.
- `DOCUMENT_TOOL.md` — спецификация document tool, схема графа и
  протокол нативного хоста.
- `SUBAGENTS.md` — MVP субагентов и ограничения.
- `CHANGELOG.md` — история версий.
- `README.md` — запуск, конфигурация, тесты.
