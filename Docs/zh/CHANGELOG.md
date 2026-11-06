# HAGAR — 变更日志

格式自由但保持稳定：版本按降序排列，在有用时
给出 commit 引用。

---

# 0.3.0 — 2026-11-05

## 项目记忆、摘要与归档

- 新增与 skill 分开的项目记忆：
  `Hagar/projects/<id>/index.md` 和 `decisions/<data>-<slug>.md`，带有
  状态 `candidate`/`active`/`superseded`/`archived`、备选方案、
  理由、provenance 和 `auto_saved`。
- 启动时 Hagar 显示活动项目和“自由活动”；命令
  `/project list|new|select|free|status` 以及覆盖项 `--project`/`--free`。
- 会话结束时，transcript 被移动到 `archive/chat/`，并由带链接和
  哈希的摘要取代；如果模型不可用，则使用机械回退。
- 项目决策以 `candidate` 形式提出，并在会话结束时
  复核；如果用户拒绝，它们保持 candidate 并带
  `auto_saved: true`。
- 索引式上下文：摘要和活动决策的标题，而不是
  正文；细节通过 `memory.project_context`。预算
  `max_context_chars`（字符，而非 token）以及审计事件
  `memory.context_trimmed`。
- `project_max_active` 触发项目归档请求；
  归档是可逆的，不会删除任何内容。
- 如果 `projects` 目录不可写，记忆保持启用，
  项目被禁用并记录 `project.disabled`。
- 归档查阅：`memory.archive_search` 和
  `memory.archive_read`，命令 `/memory archive search|read`，支持
  按项目过滤，transcript 在
  frontmatter 中保留 `project`。归档永远不会被自动注入。

## 控制台命令与手册

- 新的聊天命令：`/help`、`/tools [类别]`、`/status`、`/mcp`、
  `/audit [n]`。
- `/tools` 按类别对工具分组，并显示 capability。
- `/status` 报告模型、calling、项目、记忆、审计和
  文件系统。
- `/mcp` 列出已配置的服务器、端点和已导入的工具。
- `/audit` 读取当前日志的最后若干事件，不暴露
  未选中的字段。
- 未知的 `/` 命令不会发送给模型。
- 新增 `Docs/it/MANUAL.md`，包含命令、CLI、`hagar.yaml`、
  `policy.yaml`、默认值以及出错时的行为。

## MCP、OAuth 与干净退出

- MCP 客户端更新到 `MCP-Protocol-Version` `2025-06-18`，带回退、
  复用 `Mcp-Session-Id`，并在错误中包含 HTTP 响应体。
- OAuth：可选 `audience`、`offline_access` 时使用 `prompt=consent`、
  回调 `http://localhost:<port>/oauth/callback`，dynamic registration
  中包含 scope。
- 在 OAuth 或某个轮次期间按 Ctrl-C 会关闭本地回调并以
  代码 130 退出，不产生 traceback。

## 本地工具与文件系统 v2

- 新增 `local_tools/` 目录用于本地 provider：计算、统计、
  单位换算、时间/日期和 feed。它们不是 MCP 服务器：它们向
  registry 注册 `ToolDefinition`。
- 新增工具：`calculator.evaluate`、`statistics.compute`、
  `units.convert`、`clock.now`、`calendar.date`、`think.echo`、
  `text.diff`、`url.parse`、`feed.read`。
- 文件系统：`list_dir`、`read_chunk`、`rename`、`copy_file`、`search`。
- 新增 capability `COMPUTE`（本地计算，始终在上限内）和
  `NETWORK`（由 `permissions.network: true` 启用）；`feed.read`
  需要 `NETWORK`。
- 配置中的 `permissions.network`；策略：对
  calculator/statistics/units 允许 `COMPUTE`，对 feed 询问 `NETWORK`。
- `feedparser` 加入依赖；feed 通过 `requests` 下载，带超时和 5 MB 上限，
  且只能使用 http/https URL。
- SSRF：强制 DNS 解析，仅全局地址
  （不允许 loopback、私有网络、link-local、multicast 或保留地址），
  手动重新校验重定向（最多 3 次），拒绝带
  凭据的 URL。
- 恢复在扩展过程中丢失的 sandbox `rename` 权限；
  `filesystem.rename` 需要对源路径有 `rename`、
  对目标路径有 `create`。
- 把 `MCP_tools/` 重命名为 `local_tools/`：它们是本地 provider，而不是
  MCP 服务器；package、import、测试和文档已更新。
- 文件系统使用虚拟根目录 `/home/ai`：`stat`、`list_dir`、
  `search`、`read_chunk` 以及工具消息不再暴露
  物理路径；接受 `/home/ai/...` 形式的输入。
- `read_chunk` 把边界对齐到 UTF-8 字符并返回
  `next_offset`；不再拆分多字节字符。
- `read_file` 拒绝超过 4096 字节的文件，并指向 `read_chunk()`
  以避免把整个文件加载到上下文窗口。
- `list_dir` 每页最多返回 100 个条目，`search` 最多 100
  个结果（最大 500）；两者都支持 `offset`、`next_offset`、
  `has_more` 以及消息
  `voci: riportate X di Y; per continuare usa offset=Z`。对于大型
  目录树，最好收窄 pattern/path，而不是迭代分页。
- 新增写入限制 `filesystem.limits`：
  `max_write_bytes` 表示单次操作，`min_free_bytes` 作为储备，
  `session_write_bytes` 为累计值，`ask_over_bytes` 用于确认。
  前三项是不变式；`ask_over_bytes` 经过 `ToolRegistry`
  的预检，即使策略为 `ASK` 也只询问一次。
- 对 sandbox 而言符号链接不存在：它们不会被显示、读取、
  跟随或删除；对链接执行 `chdir` 回答
  “Directory not found”。项目决定：即使宿主文件系统
  支持它们，也保持不可见。
- 允许目录内部的硬链接、挂载和 junction 不受 Hagar
  检查，也不会被检测。这不是缺陷：硬链接是同一 inode 的
  第二个名称，而挂载可以在仍处于前缀之内的情况下暴露另一个
  文件系统。文件系统工具不会创建
  硬链接。要实现完全隔离，用户必须保证 sandbox
  目录中不存在这些对象。属于用户责任，
  该问题已关闭。
- TOCTOU：本版本不使用 `openat2`、对每个组件使用 `O_NOFOLLOW`
  或 Windows handle，因此不保证检查与操作之间的
  原子性。该竞态需要一个有写权限的本地并发进程：
  属于恶意场景或环境被攻破，而不是正常使用。
  作为用户责任关闭；要实现完全
  隔离，需要专用卷、独立用户、挂载命名空间或
  容器。
- `filesystem.allowed` 被 `filesystem.sandbox` 取代：每个条目都有
  `alias`、`path` 和 `R`/`W`/`X` 权限。智能体看到
  `/home/ai/<alias>/...`；没有 `hdN`，没有卷，也没有合成的
  中间目录。`/home/ai` 列出别名，但不是挂载点。
- 按别名的权限：`R` 读取/列出/搜索/stat，`W`
  写入/创建/重命名/复制/删除，`X` `chdir`；全局
  权限仍是上限。
- 别名必填、单个路径段、大小写不敏感地唯一、不包含
  Windows 保留名；sandbox 条目仍是宿主机路径，
  Hagar 不创建目录。物理路径和内部名称
  可以包含空格；别名不可以。
- POSIX 运行器 `tools/run_tests.sh`；`run_tests.ps1` 和 shim 仍
  专用于 Windows sandbox。基准测试命令已更新。
- 来自 CI 的跨平台修复：`vault_subdir` 在 POSIX 上也拒绝带
  Windows 驱动器（`I:/...`）的路径；符号链接的拒绝不再被
  `except OSError` 吞掉，因此路径不会被解析到
  sandbox 之外。
- Windows 上 691 个测试通过，2 个跳过；Debian
  Linux 上 693 个通过，0 个跳过（2026-11-06），包括符号链接测试。

## 发布与跨平台

- `pyproject.toml` 和 `hagar.py` 中的版本为 `0.3.0`。
- GitHub Actions CI 在 Linux、macOS 和 Windows 上运行 Python 3.11、3.12 和
  3.13；构建包、`twine check` 以及 wheel 的冒烟测试。
- Action 更新到 `checkout@v7`、`setup-python@v7` 和
  `upload-artifact@v7`，全部基于 Node 24；移除了 Node 20 的
  弃用警告。
- 基于 `v*` 标签的 release 工作流：构建 sdist/wheel，校验标签
  与版本一致，并创建 GitHub release。
- `hagar.example.yaml` 可移植；本地 `hagar.yaml` 和 `testvault/` 被
  git 忽略。
- 为首次公开发布准备 `MANIFEST.in`、`SECURITY.md`、`CONTRIBUTING.md` 和
  `RELEASING.md`。

# 0.2.0 — 2026-11-04

首个带可复核记忆、原生 calling、MCP auth/OAuth、
审计保留和可安装打包的版本。

## 记忆 v2

- 生命周期 `candidate` → `confirmed` → `archived`：LLM 提出，
  用户从 CLI 提升。
- 命令 `/memory list`、`/memory show`、`/memory review`、
  `/memory confirm`、`/memory archive`。
- 只自动注入已确认的 skill，最多
  `memory.context_skills` 个（默认 3），按词法匹配；candidate
  和已归档的不会进入。
- frontmatter 中的 `reviewed_at`；审计事件 `memory.review` 和
  `memory.status`。
- 保留策略选项 A：不自动删除；`archive` 可用 `confirm`
  逆转。
- 配置中的 `memory.context_skills`；552 个测试通过，1 个跳过。

## 交互式 MCP OAuth

- Authorization code + PKCE 流程，回调位于 `127.0.0.1` 并
  打开浏览器；可手动粘贴 URL 回退。
- RFC 9728（受保护资源）和 RFC 8414（授权服务器）
  discovery，缺少 `client_id` 时进行 dynamic client registration。
- 本地 token 缓存，权限 `0600`，自动刷新，并在 `401` 时
  重试一次。
- 配置 `auth.type: oauth`，含 `authorization_server`、`client_id`、
  `client_secret_env`、`scopes`、`redirect_port`、`token_cache`、
  `timeout`。
- 限制：没有 device flow、DPoP、mTLS 或 client assertion。
- 522 个测试通过，1 个跳过。

## 审计保留

- 超过 `audit.max_bytes` 时轮转为 `<file>.<timestamp>`。
- `audit.max_files`（默认 100）限制审计文件数量，
  包括活动文件；更旧的备份会被删除。
- 如果活动文件缺失，哈希链会从最新的备份继续。
- 504 个测试通过，1 个跳过。

## MCP auth

- `mcp_servers[].auth`：`type: bearer` 或 `type: header`，带
  `token_env`，对于 header 还要给出 header 名称。
- token 只从环境读取：不写入 YAML、审计或
  日志。
- token 缺失或非 ASCII：服务器以 `mcp.failed` 跳过，
  harness 继续使用其他服务器。
- 496 个测试通过，1 个跳过。

## 原生与文本基准

- `tools/bench_native.py`：同一 registry 上的 9 个文件系统任务，
  比较 `native_step()` 与 `request_tool_call()`，衡量准确率、
  延迟和修复次数。
- 初步测量：`llama3.1` 4/5 对 5/5，`qwen3:8b` 4/5 对 5/5，
  `hermes3:8b` 4/5 对 3/5，`deepseek-flash` 8/9 对 9/9（Ollama 子集，
  DeepSeek 完整套件）。
- 没有通用赢家：默认仍是原生，可按模型通过
  `model.native_tools` 或 `--no-native-tools` 选择退出。

## DeepSeek（live）

- 更新的模型：`deepseek-flash`（默认）和 `deepseek-v4-pro`；
  `deepseek-chat` 不再有效。
- 错误消息包含 API 响应体；非 ASCII 密钥
  以 `ConfigError` 拒绝。
- 为不允许点号的 API 规范化工具名称
  （`filesystem.read_file` → `filesystem__read_file`），并恢复
  内部名称。
- `tools/diagnose_deepseek.py` 用于检查网络、密钥形态和端点，
  且不打印密钥。
- live 测试：聊天、原生 calling 以及文件系统上的端到端测试。
- 479 个测试通过，1 个跳过；使用 `--live` 时 9 个 live 测试。

## 原生 calling（v1）

- `LLMClient.native_step()` 和 `LLMReply`：Ollama、
  DeepSeek、Claude 和 Gemini 的原生 calling；参数 schema 来自 `ToolDefinition`。
- 规范的 `assistant` 消息带 `tool_calls`，`tool` 消息带
  `tool_call_id`；每个后端都会翻译它们（`tool_calls`、`tool_use`/
  `tool_result`、`functionCall`/`functionResponse`）。
- Agent 在 `max_tool_calls` 限制内每轮执行多个调用。
- 第一步出现 HTTP 400/404/422 时自动回退到文本协议，
  并记录事件 `llm.native_fallback`；`model.native_tools: false` 和
  `--no-native-tools` 可强制使用文本。
- 审计：`turn.start` 带 `native`，`llm.tool_choice` 带 `mode=native`。
- 476 个测试通过，1 个跳过；使用 `--live` 时 7 个 live 测试。

## 卫生性（v1）

- **打包**：完整的 `pyproject.toml`（元数据、依赖、
  setuptools）、入口点 `hagar`、唯一版本号（`hagar.__version__`）；
  已验证 `pip install -e .`。
- **CLI**：`--config`、`--model`、`--no-memory`、`--version`；
  配置按 `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml` 的顺序查找。
- **live 测试**：`live` 标记，从常规套件中排除，`--live`
  用于 Ollama 和远程 provider（没有密钥时跳过）。
- **MCP**：`text/event-stream` 响应、`notifications/initialized`
  通知、结果规范化为文本。
- **审计**：哈希链（`prev`/`hash`、`verify_chain`）、在
  `max_bytes` 时轮转、用 `include_outputs` 对工具输出脱敏。
- **Base URL**：所有 provider 都使用 `model.host`。
- **遗留代码**：移除了 `tools/filesystem.py` 和 `llm/tool_result.py`。
- 442 个测试通过，1 个跳过；使用 `--live` 时 6 个 live 测试。

## 记忆（v1）

- `memory/store.py`：情景记忆（每个会话一个笔记，位于
  `<vault>/Hagar/chat/`）和语义记忆
  （`<vault>/Hagar/skills/<slug>.md`）；
- 自动把最近的 `memory.context_turns` 个轮次注入 prompt，
  带截断；记忆错误不会使轮次失败；
- 工具 `memory.create_skill`（provenance 和 `candidate` 状态）、
  `memory.list_skills`、`memory.get_context`（按关键字搜索）；
- capability `MEMORY_READ`/`MEMORY_WRITE`，用于策略的命名空间
  `chat`/`skills`；
- 配置 `memory.*`，vault 缺失时禁用并给出警告；
- 审计事件 `memory.enabled`、`memory.disabled`、`memory.context`、
  `memory.turn`、`memory.failed`；

## 权限（PermissionEvaluator v1）

- 新增 `core/permissions.py`：`Capability`（IntFlag）、`Effect`
  （`ALLOW` / `ASK` / `DENY`，带 deny-overrides）、带 tool、path 和
  namespace 作用域的 `Rule`、`Subject`、`Resource`、`Decision` 以及
  纯 evaluator；
- 独立的 `policy.yaml`，在构建 LLM 之前读取：出错时所有策略
  变为 `DENY`，并产生事件 `policy.failed` 和聊天中的
  警告；
- 由 `permissions.read/write/shell` 推导的系统上限；
- `ASK` 带控制台确认（`lo faccio? (y/N)`，默认 N）以及
  供未来 GUI 使用的 `ConfirmationProvider`；
- `ToolRegistry.execute` 应用策略并记录
  `permission.decision` 和 `permission.confirmation`；
- 所有工具（文件系统和 MCP）的 `ToolDefinition.capabilities`；
- `requires_confirmation` 现在作为 ASK 下限应用；
- 从 `core/models.py` 移除了不完整的 `PolicyRule` 存根；

## 文件系统 v2、数学工具与 feed

### 文件系统

- `filesystem.list_dir`：非递归地列出目录内容。
- `filesystem.list_dir` 通过 `FileInfo` 为每个找到的元素返回完整元数据。
- `filesystem.read_chunk`：通过 offset 和长度增量读取大文件。
- `filesystem.read_chunk` 在字节层面操作，并返回 `has_more`，以便智能体继续读取。
- `filesystem.rename`：在 sandbox 内重命名或移动文件。
- `filesystem.copy_file`：复制文件，并校验权限和可用空间。
- `filesystem.search`：通过 glob 模式（`*.py`、`*.md` 等）递归搜索。
- `filesystem.search` 返回：
  - 找到的结果总数；
  - 返回的结果数量；
  - 截断指示（`truncated`）；
  - 以 `FileInfo` 表示的结果列表。
- 改进了对 sandbox 的自主探索：智能体现在可以枚举目录、搜索文件并读取非常大的文档，而不会耗尽上下文窗口。

### Calculator

- 新增类 `local_tools/calculator.py`。
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

所有操作都通过 AST 节点、运算符和允许函数的白名单进行校验。

### 统计

新增类 local_tools/statistics.py。

新增 MCP 工具：

`statistics.compute`

类名为 `Stats_calc`；暴露给模型的工具是
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
- 请求的统计类型；
- 处理的样本数；
- 结果或错误。

### 单位换算

新增类 `local_tools/unit_converter.py`。

新增 MCP 工具：

`units.convert`

支持以下类别：

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

数据量

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
等。

专用换算：

温度（带偏移）；
角度（度/弧度）。

其他所有类别使用线性换算。

### RSS 与 Atom feed

新增类 `local_tools/feeder.py`。

新增 MCP 工具：

`feed.read`

通过单一 API 透明支持 RSS 和 Atom feed。

参数 max_items 带有安全上限，以避免输出过多。

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

返回可用元素总数、返回元素数量以及截断指示。

### 说明

本次迭代显著扩展了智能体的操作能力。除了 sandbox 化的文件系统，Hagar 现在还拥有可靠的工具来：

探索和检索内容；
增量读取非常大的文件；
执行确定性的数学计算；
进行统计分析；
换算属于不同领域的计量单位；
通过 RSS 和 Atom feed 消费结构化信息源。

目标仍然是优先采用确定性、结构化且便于模型通过原生 tool calling 使用的工具。


## 文档

- `PROJECT_STATE.md` 拆分为 `ARCHITECTURE.md`（系统的现状）、
  `ROADMAP.md`（要做什么和已做出的决定）以及本 `CHANGELOG.md`。
- 路线图已按 2026-11-03 的决定更新：Vault 上的记忆、
  tool 的原生 calling、`PermissionEvaluator`。

---

# 0.2.0 — 2026-11-03（开发中）

Commit：`137c985` — *调试、测试套件、审计日志与多后端*

## 新增

- **审计日志**（`core/audit.py`）：仅追加的 JSON Lines，带 UTC 时间戳、
  `session` 和 `turn` id。覆盖会话、轮次、工具选择、协议、
  执行、错误、MCP 和 provider 的事件。尽力而为的写入、
  可配置截断、日志中不含任何 API 密钥。
- **多后端**（`llm/base.py`、`llm/factory.py`、
  `deepseek_client.py`、`claude_client.py`、`gemini_client.py`）：
  `LLMClient` 共享工具选择、JSON 解析与修复；每个后端
  只实现传输和角色转换。
- **`filesystem.stat`**：类型、以字节计的大小、ISO 8601 日期以及
  sandbox 的有效权限，一次测量全部给出。
- **测试套件**：259 个测试，1 个跳过，无网络（Ollama 和 MCP
  都是模拟的），带 `tools/run_tests.ps1` 和 Windows sandbox 的
  shim。
- **`tools/bench_models.py`**：在读取、元数据、创建和聊天方面对 Ollama
  模型进行可复现的对比。

## 变更

- `model.provider` 现在真正选择后端（之前被忽略，总是
  使用 Ollama）。API 密钥来自环境，绝不来自 YAML。
- 默认模型：用 `llama3.1:latest` 取代 `qwen3:8b`。
- 工具结果是 `user` 轮次而不是 `system` 轮次，以兼容
  远程后端。
- 配置错误：干净退出（`SystemExit 1`），消息输出到 stderr，
  并在审计中记录事件 `llm.failed`。

## 修复

- `core/filesystem.py` 在 `mkdir` 中途被截断：缺少
  `read_file`、`write_file`、`create_file`、`delete_file`、
  `free_space`。文件系统的每个工具都以 `AttributeError` 失败。
- `ToolDefinition.origin` 是必填的，但没有任何 provider 传入它：
  注册任何工具都会以 `TypeError` 失败。
- `ToolResult` 使用 `tool`，而 `Agent` 使用 `tool_name`。
- `llm/ollama_client.py` 使用了 `re` 却没有导入，并且两次定义了
  `_tool_call_from_json`。
- `hagar.py` 读取了 `AppConfig` 中不存在的字段：`main()` 无法
  启动。
- `ConfigLoader` 没有校验空 YAML、非 mapping 的根、非布尔的
  权限、非列表的 `allowed`。
- `write_file` 可以绕过 `create` 权限创建新文件。
- 解析接受别名 `parameters`；散文式回答只产生
  一次修复尝试，随后是明确的错误。

## 说明

Ollama 模型对比（4 项任务、临时 sandbox、每轮最多 4 个工具）：

| 模型 | read | stat | create | chat | 修复次数 |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | 循环，4 个工具 | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | 工具错误 | 文件错误 | 内容错误 | ok 6.4 s | 3 |

---

# 0.1.0 — 2026-11-02

Commit：`03b35bf` — *0.1 alpha 版本*

第一个真正可用的版本：Hagar 不再只是通往 Ollama 的接口，
而是一个可运行的智能体。

## 新增

- YAML 配置的加载与校验；
- `OllamaClient`，带 `generate`、`chat`、`request_tool_call`；
- `ToolRegistry`、`ToolDefinition`、`ToolCall`、`ToolResult`；
- `Agent`，带多步循环、错误处理和工具上限；
- `FileSystemSandbox`，带根目录、可继承权限、符号链接防护
  和磁盘空间检查；
- 文件系统工具：读取、写入、创建、删除、
  创建目录、切换目录、剩余空间；
- 通过 HTTP 的 MCP 客户端，自动发现工具并带命名空间；
- 用于 Markdown 文件的初始 `Vault`。

## 说明

v0.1 是第一个能够与本地 LLM 对话、暴露工具、让模型
选择使用哪些工具、在 sandbox 化的文件系统上操作并自主
串联多个操作的版本。
