# HAGAR — 变更日志

格式自由但保持稳定：版本按降序排列，在有用时
引用 commit。

---

# 0.5.2 — 2026-11-08

## 概要

整合版本：SQLite 记忆、子智能体、vision、决策
工具、模型卡片、Markdown 导入/导出和 CLI input broker。

## 破坏性变更

- 默认记忆不再是 Vault Markdown：它使用
  `%LOCALAPPDATA%/Hagar/memory.db` 或 `HAGAR_MEMORY_DB`；
- Vault 不会被自动导入；
- `markdown` 后端仅作为遗留保留；
- `memory.database` 和 `decisions.*` 是新的配置段。

## 新的 LLM 后端

- 面向 LM Studio 本地 OpenAI 兼容服务器的新 `lmstudio` 后端，
  默认 `http://localhost:1234/v1`，除非服务器
  配置要求，否则无需密钥。
- 面向 OpenAI Chat Completions API 的新 `openai` 后端（别名 `chatgpt`），
  密钥 `OPENAI_API_KEY`，base URL 可配置。
- 这两个后端共享 OpenAI 兼容客户端，带原生
  tool calling，并在 HTTP 400/404/422 上回退到文本 JSON。
- `model.timeout` 可配置（默认 120 秒），并传递给所有
  后端；对大型本地模型很有用。
- 更新了 `hagar.example.yaml` 和意大利语文档。

## 服务层

- 新增 `core/service.py`，含 `HarnessService`：轮次、状态、项目、
  会话结束和结构化事件（`ServiceEvent`）。
- `hagar.py` 使用该服务处理 `ask`、项目选择和会话
  关闭；CLI 仍是一个 adapter。
- `tool.call`、`tool.result`、`permission.decision` 和
  `permission.confirmation` 事件由 `Agent` 和 `ToolRegistry` 转发到
  服务的 sink；事件中的工具输出会被截断。
- 新增 `CommandService`，用于 `/help`、`/tools`、`/status`、`/mcp`、
  `/audit`、`/project` 和 `/memory`，带结构化的 `CommandResult`。
- CLI 对斜杠命令使用该命令服务；`/memory review`
  仍为交互式。
- 新增 `QueueConfirmationProvider`：来自 GUI 的 ASK 确认，带队列、
  超时和显式拒绝。
- 新增本地 web GUI（`hagar web`）：聊天、SSE 事件、状态、项目、
  tool call 和确认模态框；本地 token 和 `127.0.0.1` 绑定。
- 浏览器的 SSE 断开在 Windows 上不再产生 traceback
  （`ConnectionAbortedError`/WinError 10053）。
- Ctrl-C 会立即关闭 `hagar web`：不再从 `serve_forever` 的线程调用
  `shutdown()`，不再 join SSE 线程，关闭时跳过
  summary。
- 新增 `core/usage.py`：解析 OpenAI/DeepSeek/LM Studio、
  Claude、Gemini 和 Ollama 的 usage，带按会话的 `UsageLedger`。
- GUI 在侧边栏显示 input、output 和总计 token，通过
  `usage.updated` 事件更新。
- GUI 的 HTML、CSS 和 JavaScript 分离到 `web/` 中，并作为
  静态资源提供；`core/web.py` 只注入 token。
- 新增 `memory/index.py`：Markdown 记忆的可增量重建
  SQLite/FTS5 索引，带词法回退。
- 新增工具 `memory.search`；命令 `/memory search`、`reindex`、
  `stats`。
- 轮次的协作式停止（`Agent.cancel`、`POST /api/stop`），带
  GUI 按钮和 `turn.cancelled` 事件。
- vision 图片输入（`core/images.py`），带 data URL、MIME 和 10 MB
  限制校验；OpenAI/LM Studio、Claude 和 Gemini adapter。
- 在 GUI 中上传图片，可预览和移除；WebP 在发送
  前转换为 PNG。任何图片都不会保存到记忆或审计。
- GUI 的 JSON body 最大 64 MB，以便接受高分辨率
  base64 图片。
- 专门的标签页中的聊天历史：列出 `chat/` 和
  `archive/chat/`；点击即恢复同一会话，新轮次
  继续该 transcript。
- **+ Nuova chat** 按钮，使用 `MemoryStore.new_session()` 并重置
  上下文；先前的 transcript 仍留在 Vault 中。
- GUI 标签页：Chat、Chat history、Tool output、Audit、Thinking、Memories。
- 内存中的 `SessionLog`，用于 tool call/结果和 timeline；
  `/api/tools`、`/api/audit`、`/api/thinking`。
- 只读记忆浏览器：`/api/memories`、`/api/memory`。
- CLI 中的 `/usage` 用于会话累计 token；与 GUI 使用同一个
  ledger。
- 工具和 LLM provider 都是插件：内置在 `local_tools/plugins.py`
  和 `llm/plugins.py`，外部通过 entry point `hagar.tools`/`hagar.llm`。
- 插件错误被隔离并记录到审计；策略和 sandbox
  留在 host 中。
- 在 `DOCUMENT_TOOL.md` 中记录了 document tool 的设计：
  结构/语义图、CSV MVP、`FormatPlugin` 契约、C ABI 和
  原生宿主的 JSON 协议。
- 异步子智能体：`agent.spawn/status/wait/result/cancel`，最多
  两个并发 child、独立 LLM 客户端、带复制输入的私有 workspace、
  只读 registry、不写入记忆、拒绝确认、
  专用 usage 和审计；轮次结束时清理。
- spawn 时强制的 `reason` 和独立的 `AGENT_SPAWN` capability：
  child 不能创建其他 child；`permissions.agents` 控制系统
  上限。
- 子智能体策略严格严于父级；相同或不再受限的策略
  会被拒绝。
- 每个子智能体 5 分钟墙钟超时，协作式，状态
  `timed_out`；所有审计事件中都有 `agent_id`。
- 子智能体的 ASK 通过 `ParentBridgeConfirmation` 转发给用户，
  超时 180 秒，到期即 DENY；父级 LLM 不批准。
- `vision.open` 从 sandbox 加载 PNG/JPEG/WebP 并附加到轮次；
  `ToolResult.images` 和 Agent 循环处理多模态通道，
  文本中不含 base64。音频在路线图中。
- SQLite 记忆作为主要来源：`memory/sqlite_store.py`、
  `memory/database.py`、WAL 和备份；命令 `/memory sessions`、
  `/memory chat` 和 `/memory backup`。项目和决策在同一个
  数据库中；Markdown 后端仅为遗留。
- 用 `/memory export <path> [--force]` 从数据库导出 Markdown：
  chat、skill、summary、项目和决策，原子写入。
- 用 `/memory import <path> [--force]` 导入 Markdown；主数据库中的
  FTS5，带 `bm25`/`snippet` 和 `LIKE` 回退。
- CLI 带 `ConsoleInputBroker`：单一控制台读取器、注意
  标题，以及 `F5` allow / `F8` deny 的 ASK 确认；`y/N` 回退。
  该 broker 会保存并恢复终端，包括在 Ctrl-C 时。
- 新增工具类 `decision.*`，含 `decision.choose`：本地/远程 LLM
  provider 和本地线性分类器，概率经过校验，
  审计 `decision.result` 和 capability `DECISION`。
- 模型技术卡片与基准测试：`/models list|show|test|hardware`，
  延迟、JSON、tool calling、最近一次测试日期和
  CPU/RAM/GPU 检测，无强制依赖。
- 临时 artifact store 和内部 mailbox：child 使用 `artifact.put`、
  `artifact.put_file`、`mailbox.send`；父级使用 `artifact.read`、
  `artifact.list`、`mailbox.inbox/read/ack`。capability
  `AGENT_DATA`、配额和轮次结束时清理。
- `artifact.save_to` 把整个 artifact 复制到父级
  sandbox 中可写的路径；需要 `AGENT_DATA`、`FILESYSTEM_WRITE` 和
  `FILESYSTEM_CREATE`，并可能需要策略确认。
- 轮次结束时对未导出的 artifact 记录 `artifact.discarded` 审计，
  原因为 `unread` 或 `read_but_not_saved`；持久化仍
  推迟。
- 审计被停用：该标签页禁用，并显示 `audit off`。
- Thinking 显示 provider 暴露的 reasoning，否则显示
  事件 timeline。
- 为将来的 GUI 打下基础，服务中不使用 `input()` 或 `print()`。

# 0.3.0 — 2026-11-05

## 项目记忆、summary 和归档

- 新增与 skill 分开的项目记忆：
  `Hagar/projects/<id>/index.md` 和 `decisions/<data>-<slug>.md`，带
  状态 `candidate`/`active`/`superseded`/`archived`、备选方案、
  理由、来源和 `auto_saved`。
- 启动时 Hagar 显示活动项目和"自由活动"；命令
  `/project list|new|select|free|status` 和覆盖项 `--project`/`--free`。
- 在会话结束时，transcript 被移动到 `archive/chat/`，
  并替换为一个带链接和 hash 的 summary；如果
  模型不可用，则机械式回退。
- 项目决策作为 `candidate` 提出，并在会话结束时
  审查；如果用户拒绝，它们保持 candidate，并带
  `auto_saved: true`。
- 索引式上下文：summary 和活动决策的标题，而不是
  正文；细节用 `memory.project_context`。预算
  `max_context_chars`（字符，而不是 token）和审计
  `memory.context_trimmed`。
- `project_max_active` 触发项目归档请求；
  归档是可逆的，不会删除任何东西。
- 如果 `projects` 目录不可写，记忆保持活动，
  项目被停用并记录 `project.disabled`。
- 查阅归档：`memory.archive_search` 和
  `memory.archive_read`，命令 `/memory archive search|read`，带
  按项目过滤，transcript 在
  frontmatter 中保留 `project`。归档永远不会被自动注入。

## 控制台命令与手册

- 新的聊天命令：`/help`、`/tools [类别]`、`/status`、`/mcp`、
  `/audit [n]`。
- `/tools` 按类别分组工具并显示 capability。
- `/status` 报告模型、calling、项目、记忆、审计和
  filesystem。
- `/mcp` 列出已配置的服务器、端点和导入的工具。
- `/audit` 读取当前日志的最近事件，不暴露
  未选中的字段。
- 未知的 `/` 命令不会发送给模型。
- 新增 `Docs/it/MANUAL.md`，含命令、CLI、`hagar.yaml`、
  `policy.yaml`、默认值和错误情形下的行为。

## MCP、OAuth 与干净退出

- MCP 客户端更新到 `MCP-Protocol-Version` `2025-06-18`，带
  回退、复用 `Mcp-Session-Id` 以及错误中的 HTTP body。
- OAuth：可选的 `audience`、使用 `offline_access` 时的 `prompt=consent`、
  回调 `http://localhost:<port>/oauth/callback`、在
  dynamic registration 中的 scope。
- OAuth 或轮次期间按 Ctrl-C 会关闭本地回调，并以
  代码 130 退出，不打印 traceback。

## 本地工具与 filesystem v2

- 新增 `local_tools/` 目录用于本地 provider：计算、统计、
  单位转换、时间/日期和 feed。它们不是 MCP 服务器：它们向 registry 注册
  `ToolDefinition`。
- 新增工具：`calculator.evaluate`、`statistics.compute`、
  `units.convert`、`clock.now`、`calendar.date`、`think.echo`、
  `text.diff`、`url.parse`、`feed.read`。
- Filesystem：`list_dir`、`read_chunk`、`rename`、`copy_file`、`search`。
- 新 capability `COMPUTE`（本地计算，始终在上限中）和
  `NETWORK`（由 `permissions.network: true` 启用）；`feed.read`
  需要 `NETWORK`。
- 配置中的 `permissions.network`；策略：calculator/statistics/units 的 `COMPUTE` 为 allow，
  feed 的 `NETWORK` 为 ask。
- `feedparser` 在依赖中；feed 用
  `requests` 下载，带超时和 5 MB 限制，且只从 http/https URL 下载。
- SSRF：强制 DNS 解析，只允许全局地址
  （不允许 loopback、私有网络、link-local、multicast 或保留地址），
  重定向手动重新校验（最多 3 次），并拒绝带
  凭据的 URL。
- 恢复了 sandbox 的 `rename` 权限，它在
  扩展期间丢失；`filesystem.rename` 需要对源有 `rename`，对
  目标有 `create`。
- 重命名 `MCP_tools/` → `local_tools/`：它们是本地 provider，而不是
  MCP 服务器；已更新包、导入、测试和文档。
- 带虚拟根 `/home/ai` 的 filesystem：`stat`、`list_dir`、
  `search`、`read_chunk` 和工具消息不再暴露
  物理路径；接受 `/home/ai/...` 输入。
- `read_chunk` 把边界对齐到 UTF-8 字符，并返回
  `next_offset`；不再切断多字节字符。
- `read_file` 拒绝超过 4096 字节的文件，并指向 `read_chunk()`，
  以避免把整个文件载入上下文窗口。
- `list_dir` 每页最多返回 100 个条目，`search` 最多 100 个
  结果（最多 500）；两者都支持 `offset`、`next_offset`、
  `has_more` 以及消息
  `voci: riportate X di Y; per continuare usa offset=Z`。对于大型
  目录树，最好收紧 pattern/path，而不是遍历很多页。
- 新的写入限制 `filesystem.limits`：
  `max_write_bytes` 按操作、`min_free_bytes` 作为储备、
  `session_write_bytes` 累计、`ask_over_bytes` 用于确认。
  前三项是不变式；`ask_over_bytes` 经过 `ToolRegistry` 的预检，
  只询问一次，即使策略是 `ASK`。
- 对 sandbox 而言 symlink 不存在：它们不会被显示、读取、
  跟随或删除；对链接执行 `chdir` 会回答
  "Directory not found"。项目决定：即使宿主文件系统支持它们，
  它们也保持不可见。
- 允许目录内的硬链接、mount 和 junction 不会被 Hagar
  检查或检测。这不是缺陷：硬链接是同一 inode 的
  第二个名字，mount 可以在前缀内部暴露另一个
  文件系统。文件系统工具不会创建
  硬链接。要实现完全隔离，用户必须保证 sandbox
  目录中没有这类对象。用户责任，
  该点关闭。
- TOCTOU：本版本不使用 `openat2`、对每个组成部分的 `O_NOFOLLOW`
  或 Windows handle，因此不保证检查与
  操作之间的原子性。该竞态需要带写访问权限的本地并发进程：
  恶意场景或被攻陷的环境，而不是
  正常使用。作为用户责任关闭；要实现完全隔离，
  需要专用卷、独立用户、mount namespace 或
  容器。
- `filesystem.allowed` 被 `filesystem.sandbox` 取代：每个条目都有
  `alias`、`path` 和 `R`/`W`/`X` 权限。agent 看到
  `/home/ai/<alias>/...`；没有 `hdN`，没有合成的卷或中间
  目录。`/home/ai` 列出 alias，但不是 mount。
- 按 alias 的权限：`R` 读取/列出/搜索/stat，`W`
  写入/创建/重命名/复制/删除，`X` `chdir`；全局
  权限仍是上限。
- alias 必填、单个路径段、不区分大小写唯一、不使用 Windows
  保留名称；sandbox 条目仍是宿主系统的路径，Hagar 不会创建目录。
  物理路径和内部名称
  可以包含空格；alias 不可以。
- POSIX runner `tools/run_tests.sh`；`run_tests.ps1` 和 shim 仍是
  Windows sandbox 专用。更新了基准测试命令。
- CI 提供的跨平台修复：`vault_subdir` 在 POSIX 上也会拒绝带
  Windows 驱动器（`I:/...`）的路径；symlink 的拒绝不再
  被 `except OSError` 吞掉，因此路径不会被解析到
  sandbox 之外。
- Windows 上 832 个测试通过，2 个跳过；Debian Linux 上 834 通过，0 跳过
  （2026-11-06），包括 symlink 测试。

## 发布与跨平台

- `pyproject.toml` 和 `hagar.py` 中的版本 `0.3.0`。
- 覆盖 Linux、macOS 和 Windows 上 Python 3.11、3.12 和
  3.13 的 GitHub Actions CI；包构建、`twine check` 和 wheel 冒烟测试。
- action 更新到 `checkout@v7`、`setup-python@v7` 和
  `upload-artifact@v7`，全部基于 Node 24；移除了 Node 20 的
  弃用警告。
- 基于 `v*` 标签的 release workflow：构建 sdist/wheel、校验标签
  与版本一致，并创建 GitHub release。
- `hagar.example.yaml` 可移植；本地 `hagar.yaml` 和 `testvault/` 被
  git 忽略。
- `MANIFEST.in`、`SECURITY.md`、`CONTRIBUTING.md` 和 `RELEASING.md` 用于
  首次公开发布。

# 0.2.0 — 2026-11-04

首个带可审查记忆、原生 calling、MCP auth/OAuth、
审计保留和可安装打包的版本。

## 记忆 v2

- 生命周期 `candidate` → `confirmed` → `archived`：LLM 提议，
  用户从 CLI 提升。
- 命令 `/memory list`、`/memory show`、`/memory review`、
  `/memory confirm`、`/memory archive`。
- 只自动注入已确认的 skill，最多
  `memory.context_skills`（默认 3）个，按词法匹配；candidate
  和已归档的不会进入。
- frontmatter 中的 `reviewed_at`；审计事件 `memory.review` 和
  `memory.status`。
- 保留策略选项 A：不自动删除；`archive` 可用
  `confirm` 逆转。
- 配置中的 `memory.context_skills`；552 个测试通过，1 个跳过。

## 交互式 MCP OAuth

- authorization code + PKCE 流程，回调在 `127.0.0.1`，并
  打开浏览器；可粘贴 URL 手动回退。
- RFC 9728（受保护资源）和 RFC 8414（authorization
  server）发现，如果缺少 `client_id` 则动态注册客户端。
- 权限 `0600` 的本地 token 缓存、自动刷新，以及在
  `401` 时重试一次。
- 配置 `auth.type: oauth`，含 `authorization_server`、`client_id`、
  `client_secret_env`、`scopes`、`redirect_port`、`token_cache`、
  `timeout`。
- 限制：没有 device flow、DPoP、mTLS 或 client assertion。
- 522 个测试通过，1 个跳过。

## 审计保留

- 超过 `audit.max_bytes` 时轮转到 `<file>.<timestamp>`。
- `audit.max_files`（默认 100）限制审计文件数量，
  包括活动文件；较旧的备份会被删除。
- 如果活动文件缺失，hash 链从最近的备份
  继续。
- 504 个测试通过，1 个跳过。

## MCP auth

- `mcp_servers[].auth`：`type: bearer` 或 `type: header`，带
  `token_env`，对 header 类型还有 header 名称。
- token 只从环境变量读取：不写入 YAML、审计或
  日志。
- token 缺失或非 ASCII：服务器以 `mcp.failed` 被跳过，
  harness 继续使用其他服务器。
- 496 个测试通过，1 个跳过。

## 原生与文本基准测试

- `tools/bench_native.py`：在同一 registry 上的 9 个 filesystem 任务，
  比较 `native_step()` 与 `request_tool_call()`，含准确率、
  延迟和修复次数。
- 初步测量：`llama3.1` 4/5 vs 5/5、`qwen3:8b` 4/5 vs 5/5、
  `hermes3:8b` 4/5 vs 3/5、`deepseek-flash` 8/9 vs 9/9（Ollama 子集，
  DeepSeek 完整套件）。
- 没有普遍胜出者：默认仍是原生，可按
  模型通过 `model.native_tools` 或 `--no-native-tools` 选择退出。

## DeepSeek（live）

- 更新的模型：`deepseek-flash`（默认）和 `deepseek-v4-pro`；
  `deepseek-chat` 不再有效。
- 错误消息包含 API 响应体；非 ASCII 密钥
  以 `ConfigError` 被拒绝。
- 对不允许句点的 API，工具名会被规范化
  （`filesystem.read_file` → `filesystem__read_file`），并还原为
  内部名称。
- `tools/diagnose_deepseek.py` 用于检查网络、密钥形态和端点，
  而不打印密钥。
- live 测试：聊天、原生 calling 和文件系统端到端。
- 479 个测试通过，1 个跳过；`--live` 下 9 个 live 测试。

## 原生 calling（v1）

- `LLMClient.native_step()` 和 `LLMReply`：Ollama、
  DeepSeek、Claude 和 Gemini 的原生 calling；参数 schema 来自 `ToolDefinition`。
- 规范的 `assistant` 消息带 `tool_calls`，`tool` 消息带
  `tool_call_id`；每个后端都会翻译它们（`tool_calls`、`tool_use`/
  `tool_result`、`functionCall`/`functionResponse`）。
- Agent 在 `max_tool_calls` 限制内每轮执行多次调用。
- 第一步遇到 HTTP 400/404/422 时自动回退到文本协议，
  并产生 `llm.native_fallback` 事件；`model.native_tools: false` 和
  `--no-native-tools` 可强制使用它。
- 审计：`turn.start` 带 `native`，`llm.tool_choice` 带 `mode=native`。
- 476 个测试通过，1 个跳过；`--live` 下 7 个 live 测试。

## 卫生（v1）

- **打包**：完整的 `pyproject.toml`（元数据、依赖、
  setuptools）、entry point `hagar`、单一版本号（`hagar.__version__`）；
  `pip install -e .` 已验证。
- **CLI**：`--config`、`--model`、`--no-memory`、`--version`；
  配置按 `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml` 查找。
- **live 测试**：marker `live`，从常规套件排除，`--live`
  用于 Ollama 和远程 provider（无密钥时跳过）。
- **MCP**：`text/event-stream` 响应、`notifications/initialized`
  通知、把结果规范化为文本。
- **审计**：hash 链（`prev`/`hash`、`verify_chain`）、按
  `max_bytes` 轮转、用 `include_outputs` 对工具输出做遮蔽。
- **base URL**：所有 provider 都使用 `model.host`。
- **遗留**：移除了 `tools/filesystem.py` 和 `llm/tool_result.py`。
- 442 个测试通过，1 个跳过；`--live` 下 6 个 live 测试。

## 记忆（v1）

- `memory/store.py`：情景记忆（每个会话一个笔记，位于
  `<vault>/Hagar/chat/`）和语义记忆
  （`<vault>/Hagar/skills/<slug>.md`）；
- 自动把最近 `memory.context_turns` 个轮次注入
  prompt，并做截断；记忆错误不会使轮次失败；
- 工具 `memory.create_skill`（来源信息和 `candidate` 状态）、
  `memory.list_skills`、`memory.get_context`（按关键词搜索）；
- capability `MEMORY_READ`/`MEMORY_WRITE`、面向策略的命名空间 `chat`/`skills`；
- `memory.*` 配置，以及 vault 缺失时带警告的
  停用；
- 审计事件 `memory.enabled`、`memory.disabled`、`memory.context`、
  `memory.turn`、`memory.failed`；

## 权限（PermissionEvaluator v1）

- 新增 `core/permissions.py`：`Capability`（IntFlag）、`Effect`
  （`ALLOW` / `ASK` / `DENY`，带 deny-overrides）、`Rule`，作用域按
  tool、path 和 namespace，`Subject`、`Resource`、`Decision` 和
  纯 evaluator；
- 独立的 `policy.yaml`，在构建 LLM 之前读取：出错时
  所有策略变为 `DENY`，带 `policy.failed` 事件和
  聊天中的警告；
- 由 `permissions.read/write/shell` 导出的系统上限；
- `ASK`，带控制台确认（`lo faccio? (y/N)`，默认 N）和
  面向未来 GUI 的 `ConfirmationProvider`；
- `ToolRegistry.execute` 应用策略并记录
  `permission.decision` 和 `permission.confirmation`；
- 所有工具（filesystem 和 MCP）的 `ToolDefinition.capabilities`；
- `requires_confirmation` 现在作为 ASK 底线应用；
- 从 `core/models.py` 移除了不完整的 `PolicyRule` stub；

## Filesystem v2、数学工具与 feed

### Filesystem

- `filesystem.list_dir`：非递归地列出一个目录的内容。
- `filesystem.list_dir` 通过 `FileInfo` 为每个找到的元素返回完整元数据。
- `filesystem.read_chunk`：通过 offset 和长度增量读取大文件。
- `filesystem.read_chunk` 在字节层面工作，并返回 `has_more`，让 agent 可以继续读取。
- `filesystem.rename`：在 sandbox 内重命名或移动文件。
- `filesystem.copy_file`：复制文件，并检查权限和可用空间。
- `filesystem.search`：通过 glob 模式递归搜索（`*.py`、`*.md` 等）。
- `filesystem.search` 返回：
  - 找到的结果总数；
  - 返回的结果数量；
  - 截断指示（`truncated`）；
  - 作为 `FileInfo` 的结果列表。
- 改进了对 sandbox 的自主探索：agent 现在可以枚举目录、搜索文件并读取非常大的文档，而不会占满上下文窗口。

### Calculator

- 新增 `local_tools/calculator.py` 类。
- 通过安全的 AST 解析，不使用 `eval()`。
- 支持：
  - `+`
  - `-`
  - `*`
  - `/`
  - `//`
  - `%`
  - `**`
  - 括号。
- 数学常量：
  - `pi`
  - `e`
- 支持的函数：
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
- 新增 MCP 工具：

  `calculator.evaluate`

所有操作都通过 AST 节点、运算符和允许函数的白名单校验。

### 统计

新增 local_tools/statistics.py 类。

新增 MCP 工具：

`statistics.compute`

类名是 `Stats_calc`；暴露给模型的工具是
`statistics.compute`。支持的操作：

- mean
- median
- stdev
- variance
- min
- max
- sum
- count

结构化结果包含：

- 操作结果；
- 所请求的统计类型；
- 处理的样本数；
- 结果或错误。

### 单位转换

新增 `local_tools/unit_converter.py` 类。

新增 MCP 工具：

`units.convert`

支持的类别：

长度

- mm
- cm
- m
- km

质量

- mg
- g
- kg
- t

时间

- ms
- s
- min
- hour
- day

温度

- c
- f
- k

角度

- deg
- rad

数据大小

- b
- kb
- mb
- gb
- tb

单位别名与规范化系统：

meters → m
kilometers → km
hours → hour
celsius → c
fahrenheit → f
degrees → deg
等等。

专用转换用于：

温度（带偏移）；
角度（度/弧度）。

其他所有类别使用线性转换。

### RSS 与 Atom feed

新增 `local_tools/feeder.py` 类。

新增 MCP 工具：

`feed.read`

通过单一 API 透明支持 RSS 和 Atom feed。

参数 max_items，带安全上限以避免输出过多。

结构化提取：

- 标题；
- 链接；
- 发布日期；
- 作者；
- 摘要。

自动清理 feed 中的 HTML，并返回 feed 元数据：

- 标题；
- 描述；
- 链接；
- 类型（rss、atom 等）。

返回可用元素总数、返回的元素数量以及截断指示。

### 说明

本次迭代显著扩展了 agent 的操作能力。除了 sandbox 化的文件系统，Hagar 现在拥有可靠的工具来：

探索和搜索内容；
以增量方式读取非常大的文件；
执行确定性的数学计算；
进行统计分析；
转换属于不同领域的计量单位；
通过 RSS 和 Atom feed 消费结构化信息源。

目标仍是优先提供确定性、结构化且便于模型通过原生 tool calling 使用的工具。


## 文档

- `PROJECT_STATE.md` 拆分为 `ARCHITECTURE.md`（系统是什么样）、
  `ROADMAP.md`（要做什么和已做出的决定）以及本 `CHANGELOG.md`。
- 路线图更新了 2026-11-03 的决定：Vault 上的记忆、
  原生工具 calling、`PermissionEvaluator`。

---

# 0.2.0 — 2026-11-03（开发中）

Commit：`137c985` — *Debug, suite di test, audit log e backend multipli*

## 新增

- **审计日志**（`core/audit.py`）：仅追加的 JSON Lines，带 UTC
  时间戳、`session` 和 `turn` id。事件覆盖会话、轮次、工具
  选择、协议、执行、错误、MCP 和 provider。尽力
  写入、可配置截断、日志中不含 API 密钥。
- **多个后端**（`llm/base.py`、`llm/factory.py`、
  `deepseek_client.py`、`claude_client.py`、`gemini_client.py`）：
  `LLMClient` 共享工具选择、JSON 解析与修复；
  每个后端只实现传输和角色
  转换。
- **`filesystem.stat`**：类型、字节大小、ISO 8601 日期和
  sandbox 的有效权限，一次测量完成。
- **测试套件**：259 个测试，1 个跳过，无网络（Ollama 和 MCP
  被模拟），带 `tools/run_tests.ps1` 和 Windows sandbox 的 shim。
- **`tools/bench_models.py`**：对 Ollama 模型在读取、元数据、
  创建和聊天上进行可复现的比较。

## 变更

- `model.provider` 真正选择后端（之前被忽略，总
  使用 Ollama）。API 密钥来自环境变量，绝不来自 YAML。
- 默认模型：`llama3.1:latest` 取代 `qwen3:8b`。
- 工具结果是 `user` 轮次而不是 `system` 轮次，以兼容
  远程后端。
- 配置错误：干净退出（`SystemExit 1`），消息写入
  stderr，并在审计中记录 `llm.failed` 事件。

## 修复

- `core/filesystem.py` 在 `mkdir` 中间被截断：缺少
  `read_file`、`write_file`、`create_file`、`delete_file`、
  `free_space`。每个文件系统工具都以 `AttributeError` 失败。
- `ToolDefinition.origin` 是必填的，但没有任何 provider 传递它：
  注册任何工具都以 `TypeError` 失败。
- `ToolResult` 使用 `tool`，而 `Agent` 使用 `tool_name`。
- `llm/ollama_client.py` 使用 `re` 却没有导入，并两次定义了
  `_tool_call_from_json`。
- `hagar.py` 读取了 `AppConfig` 中不存在的字段：`main()` 无法
  启动。
- `ConfigLoader` 未校验空 YAML、非 mapping 的根、非布尔的
  权限、非列表的 `allowed`。
- `write_file` 可以绕过 `create` 权限创建新文件。
- 解析接受 `parameters` 别名；散文式响应只产生
  一次修复尝试，随后是明确的错误。

## 说明

Ollama 模型对比（4 个任务，临时 sandbox，每轮最多 4 个工具）：

| 模型 | read | stat | create | chat | 修复次数 |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | loop, 4 tool | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | tool errato | file errato | contenuto errato | ok 6.4 s | 3 |

---

# 0.1.0 — 2026-11-02

Commit：`03b35bf` — *versione 0.1 alpha*

首个真正可用的版本：Hagar 不再只是面向 Ollama 的界面，
而是一个可操作的 agent。

## 新增

- YAML 配置的加载与校验；
- `OllamaClient`，带 `generate`、`chat`、`request_tool_call`；
- `ToolRegistry`、`ToolDefinition`、`ToolCall`、`ToolResult`；
- `Agent`，带多步循环、错误处理和工具限制；
- `FileSystemSandbox`，带根、可继承权限、symlink 保护和
  磁盘空间检查；
- 文件系统工具：读取、写入、创建、删除、
  创建目录、切换目录、可用空间；
- 通过 HTTP 的 MCP 客户端，带工具自动发现和命名空间；
- 面向 Markdown 文件的初始 `Vault`。

## 说明

v0.1 是首个能够与本地 LLM 对话、暴露工具、让模型选择使用哪些工具、
在 sandbox 化文件系统上操作，并自主串联多个操作的版本。
