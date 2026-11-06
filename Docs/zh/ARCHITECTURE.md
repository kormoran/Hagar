# HAGAR — 架构

版本：0.2.0（开发中）
最后更新：2026-11-03

---

# 1. Hagar 是什么

Hagar 是一个用 Python 编写的 LLM harness，旨在以弹性方式执行
语言模型。

其目标不是与模型聊天，而是一个**安全**的运行环境：
LLM 可以在其中使用工具、查阅持久记忆并与外部系统交互，
而不直接访问宿主机的真实资源。

为此，本项目把人机交互/人机界面（HMI/HCI）与认知
工效学的原则应用到模型运行环境的设计中。

## 1.1 HAGAR 的四条法则

**第一法则——LLM 按定义不可信。**
不是因为它恶意或无用：而是因为它是概率性的。它的每个
断言都必须被核实，它的每个动作都必须受到限制。

**第二法则——工具比 LLM 更可靠。**
如果文件系统说某个文件存在，它就存在。如果工具返回
一个大小，那个大小就是真实的。LLM 负责解释，工具
负责测量。

**第三法则——状态必须存在于 LLM 的心智之外。**
ToolRegistry、MCP、FileSystemSandbox 以及（在计划中）
PermissionEvaluator 把知识与控制移出模型，
如同在安全关键系统中那样。

**第四法则——每个动作都必须能在事后解释。**
审计日志回答的是正确的问题：不是“LLM 为什么发疯了？”，
而是“它做了什么假设？”、“它用了哪个工具？”、“哪个数据是
错误的？”。事故调查，如同航空业。

## 1.2 绝对禁令

模型绝不能：

- 直接访问宿主文件系统；
- 在真实 shell 上执行命令；
- 获取高于配置所定义的权限；
- 得知操作系统的实际组织结构。

所有操作都只通过由 harness 注册并
控制的工具进行。

## 1.3 架构原则

- 模型与操作系统之间的分离；
- 默认安全；
- 插件架构；
- 独立于 LLM provider；
- 通过工具和 MCP 协议实现可扩展性。

---

# 2. 架构

```text
用户
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
  │     ├── memory.*        （计划中）
  │     └── mcp.*
  │
  ├── FileSystemSandbox
  │
  ├── MCPClient
  │
  └── Vault (Obsidian)
```

执行流程：

```text
用户
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
最终回答           turn.answer
```

---

# 3. 组件

## 3.1 配置（`core/config.py`）

把 YAML 文件（`hagar.yaml`）加载并校验为一个 `AppConfig`。

各段：

| 段 | 必填 | 内容 |
|---|---|---|
| `model` | 是 | provider、名称、host、max_tokens、api_key_env、native_tools |
| `vault` | 是 | Obsidian vault 的路径 |
| `filesystem` | 是 | `sandbox`：`{alias, path, permissions}` 的列表；`limits`：写入预算 |
| `permissions` | 否 | read、write、shell、network（默认 `true/false/false/false`） |
| `rag` | 否 | `top_k`（默认 8） |
| `mcp_servers` | 否 | endpoint、namespace、auth（bearer/header/oauth） |
| `audit` | 否 | enabled、path、max_field_chars、max_bytes、max_files、include_outputs |
| `policy` | 否 | policy 文件路径、subject |
| `memory` | 否 | enabled、vault_subdir、context_turns、context_skills、max_skill_chars |

校验错误总是产生 `ConfigError`，其消息会
指明字段。审计路径如果是相对路径，会相对于
配置文件解析。

## 3.2 LLM 接口与后端（`llm/`）

`LLMClient` 有两条路径：

- **原生 calling**（默认）：`native_step()` 以 provider 的格式发送工具
  schema，并从响应中读取调用；
- **文本 JSON 协议**（回退）：`request_tool_call()` 请求一个带有
  `tool`/`arguments` 的 JSON，采用稳健解析并尝试
  一次修复。

参数 schema 由 `ToolDefinition` 构建：
OpenAI/Ollama 使用 `tools[].function`，Claude 使用 `tools[].input_schema`，
Gemini 使用 `functionDeclarations`。规范对话使用
`user`/`assistant`/`tool` 角色；每个客户端都会翻译它（OpenAI 用 `tool_calls`，
Claude 用 `tool_use`/`tool_result` 块，Gemini 用 `functionCall`/
`functionResponse`）。HTTP 400/404/422 拒绝会产生
`NativeToolsUnavailable`：只有在尚未
执行过工具时，Agent 才会切换到文本协议。

工具名称会为不允许点号的 API 做规范化
（`filesystem.read_file` → `filesystem__read_file`），并在响应中恢复为
内部名称：策略、审计和测试看到的始终是原始
名称。

文本仍是那些不支持原生工具的模型的回退方案；
`model.native_tools: false` 会强制使用它（或命令行上的 `--no-native-tools`）。

| provider | API | 密钥 | 说明 |
|---|---|---|---|
| `ollama` | `/api/chat`、`/api/generate` | — | 默认 host `localhost:11434` |
| `deepseek` | `/chat/completions`（OpenAI） | `DEEPSEEK_API_KEY` | system 内联 |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system 分离，轮次交替 |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`，`model` 角色 |

密钥只从环境读取；`model.api_key_env` 覆盖
默认名称。`model.host` 是所有 provider 的 base URL（每个 provider
有一个默认值），`model.max_tokens` 只由 Claude 使用。
`llm/factory.py` 构建客户端，并拒绝未知 provider 或
缺失的密钥。DeepSeek：当前模型是 `deepseek-flash` 和
`deepseek-v4-pro`；`deepseek-chat` 不再被接受。

当前状态：**原生 calling v1**，带自动文本回退
（见 ROADMAP）。

## 3.3 工具模型（`core/tool_*.py`）

`ToolDefinition` 描述名称、描述、类别、参数、
handler、`origin`（`local` 或 `mcp.<namespace>`）、声明的
`capabilities`、启用状态以及 `requires_confirmation`
（由 registry 施加的 ASK 下限）。

`ToolCall` 是模型的请求（`tool`、`arguments`、`id`）；
`ToolResult` 是结构化结果（`tool_name`、`success`、`output`、
`error`）。

`ToolRegistry` 负责注册、查找、启用/禁用和执行工具；
它向模型暴露元数据，并且是唯一的执行点。

## 3.4 Agent（`core/agent.py`）

多步智能体循环，有两条路径：

- **原生**：一个响应可以包含多个调用；Agent 会重新排队
  `assistant` 消息以及每个结果对应的带 id 的 `tool`
  消息；
- **文本**：一次一个调用，结果作为
  `user` 轮次发送。

两者都遵循：

1. 模型判断是否需要工具；
2. 如果不需要，最终回答结束本轮；
3. 如果需要，执行工具并把结果返回给模型；
4. 限制 `max_tool_calls` 对整轮有效。如果模型
   坚持，轮次以 `Agent stopped after N tool calls`
   结束（防止循环）。

如果第一个原生步骤因 `NativeToolsUnavailable` 失败，Agent
会切换到文本协议（`llm.native_fallback`）；在执行过
工具之后发生的错误会以 `turn.error` 结束轮次，而不
回退。

每一步都会记入审计：问题、工具选择、参数、
结果、时长和最终回答。审计损坏不会阻止智能体：故障
会在 stderr 上报。

`Agent` 接收 `Vault`，但尚未使用它。

## 3.5 FileSystemSandbox（`core/filesystem.py`）

智能体的虚拟文件系统。每个请求都会：

1. 相对于当前目录解析（`resolve_path`）；
2. 对照已授予的根目录校验（`effective_permissions`）；
3. 按有效权限过滤，更具体的根目录会覆盖
   更外层的根目录；
4. 检查符号链接和可用磁盘空间
   （`FS_Guardian`，遗留名称）。

`DirectoryPermissions` 建模 `read`、`write`、`create`、`rename`、
`delete`、`execute`；`None` 表示“从外层根目录继承”。
根目录之外的路径始终是 `PermissionError`。

`FileInfo` / `stat()` 返回类型、以字节计的大小、创建/修改/访问日期
（ISO 8601，带本地偏移）以及 **sandbox 的有效权限**，
而不是操作系统的 ACL。

**对 sandbox 而言，符号链接不存在。** Hagar 不显示、不
读取、不跟随也不删除它们：`stat`、`list_dir` 和 `search` 忽略它们；
`read_file`、`read_chunk` 和 `delete_file` 回答 “not
found”；对符号链接执行 `chdir` 回答 “Directory not found”。损坏的链接
或指向外部的链接与不存在的路径无法区分。

sandbox 的虚拟根目录是 `/home/ai`；每个配置的目录
都作为 `/home/ai/<alias>` 暴露。`stat`、`list_dir`、`search`、
`read_chunk`、`write`/`create`/`mkdir`/`delete` 的消息以及 `chdir`
只显示虚拟路径：物理路径从不出现在
模型的输出中。输入 `/home/ai/<alias>/...` 会解析为
该别名的物理目录；相对路径则相对于
当前目录。

`/home/ai` 是一个合成目录：可以列出和 stat，但它
不是挂载点，也无法在其中 `chdir`。`filesystem.sandbox`
的条目仍然是宿主机路径，可以是绝对路径，或在用户选择时
使用 `~`：可以是任何存在且可达的目录。Hagar 不创建
目录，也不假定存在专用的 home 目录。

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

没有 `enabled` 标志：`filesystem.sandbox` 的每个有效条目
都会被挂载。无效的别名或权限、缺失的路径或重复的路径
会中止配置。物理路径和内部名称可以
包含空格；别名不可以，因为它必须保持为单个
虚拟路径段。

`R` 涵盖读取、列出、搜索和 `stat`；`W` 涵盖写入、
创建、重命名、复制和删除；`X` 涵盖 `chdir`。
全局权限 `permissions.read`/`write` 仍然是上限：一个 `RWX` 别名
不能超过它们。

## 3.6 文件系统工具（`core/filesystem_tools.py`）

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

`list_dir` 返回 `FileInfo` 元数据；`read_chunk` 按字节
读取，带 `has_more`、`next_offset` 和完整的 UTF-8 边界；`search` 使用
带结果上限的递归 glob；`copy_file` 需要 `create`；
`rename` 需要对源路径有 `rename`、对目标路径有 `create`。
返回的路径始终是虚拟路径（`/home/ai/<alias>/...`）。
`chdir` 需要对该别名有 `X`。

`list_dir` 每页最多返回 100 个条目（`limit` 最大
500），带 `offset`、`next_offset` 和 `has_more`；如果还有其他条目，
`message` 会显示 `voci: riportate X di Y; per continuare usa offset=Z`。
`search` 使用相同的分页：`max_results` 是页面上限
（默认 100，最大 500），`offset` 用于遍历结果。对于大型
目录树，最好收窄 `pattern`/`path`，而不是迭代许多
页。`read_file` 只接受不超过 `CHUNK_SIZE`（4096 字节）的文件；
超过时，错误会指向 `read_chunk()`，因为读取整个文件
会超出上下文窗口。`read_chunk` 返回 `next_offset` 和
完整的 UTF-8 边界。

`list_dir` 和 `search` 不显示符号链接；`read_file` 和 `read_chunk`
把它们视为不存在的文件。

`write_file` 只覆盖已存在的文件；创建通过
`create_file` 完成，它需要 `create` 权限。无法通过写入
新路径来绕过创建禁令。

### 写入限制

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = 已禁用
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` 是 `write_file`、`create_file` 或 `copy_file`
  单次操作的最大值；
- `min_free_bytes` 是操作后必须保留的
  空间储备；
- `session_write_bytes` 是会话的累计预算；
- `ask_over_bytes` 把超过阈值的操作提升为 `ASK`。预检
  集成在 `ToolRegistry` 中：即使策略也说 `ASK`，
  也只确认一次。

`0` 禁用单项限制。超过 `max_write_bytes`、
`session_write_bytes` 或储备会产生错误，而不是确认：
它们是不变式，不是提问。`ask_over_bytes` 是唯一会
询问用户的层级。

`filesystem.stat` 返回 JSON，包含 `path`、`exists`、`kind`
（`file`/`directory`/`other`）、`size_bytes`、`created_at`、`modified_at`、
`accessed_at`、`permissions`。不存在的路径不是错误：
`exists: false`，并附带适用的权限。

## 3.7 MCP（`llm/mcp_client.py`）

通过 HTTP/JSON-RPC 的 MCP 客户端：`initialize`、`tools/list`、`tools/call`，
自动把工具转换为 `ToolDefinition`，并以
命名空间 `mcp.<namespace>` 注册。

它还支持 `text/event-stream` 响应（streamable HTTP），并在
握手后发送 `notifications/initialized` 通知。它使用
`MCP-Protocol-Version`（默认 `2025-06-18`，带回退），并在服务器
返回时复用 `Mcp-Session-Id`。HTTP 错误
包含响应体，以便诊断 400。
工具结果会被规范化为文本：`text` 块，
否则用 `structuredContent` 或 JSON；带 `isError` 的结果
会成为工具错误。

按服务器认证：

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer          # 或 "header"
      token_env: MCP_EXAMPLE_TOKEN
      # header: X-API-Key  # 仅用于 type: header
```

token 只从环境读取，不会出现在审计中。如果缺失，
服务器会以 `mcp.failed` 跳过，harness 继续运行；其他
服务器仍然可用。

### 交互式 OAuth

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # 缺省时使用 dynamic registration
    # client_secret_env: MCP_CLIENT_SECRET
    scopes: [mcp.read]
    audience: api.atlassian.com  # 可选，用于 3LO provider
    redirect_port: 8765       # 0 = 随机端口
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

Authorization code + PKCE 流程，回调位于
`http://localhost:<port>/oauth/callback`，并打开浏览器。如果
scope 包含 `offline_access`，会添加 `prompt=consent`。
元数据从 `.well-known` 发现（资源用 RFC 9728，
授权服务器用 RFC 8414）；如果缺少 `client_id`，
则使用动态注册。token 保存在权限受限的本地文件中
（在系统支持的地方为 `0600`），带自动刷新，
并在 `401` 时重试一次。

等待回调期间按 Ctrl-C 会关闭本地服务器并以代码 130
退出，不产生 traceback。

限制：没有 device flow、DPoP、mTLS 或 client assertion；浏览器必须
能够访问本地回调。如果回调没有到达，
终端会要求粘贴重定向 URL。

## 3.8 Vault（`memory/vault.py`）

以相对于根目录的路径访问 Obsidian vault，并
防止越出 vault。提供读取、写入、追加、
文件列表以及用于递归读取的 `load_all`。记忆的语义
位于 `memory/store.py`（§3.11）。

## 3.9 审计日志（`core/audit.py`）

仅追加的 JSON Lines 文件。每行都有 UTC 时间戳、`session` 和
`event`；同一问题的各事件共享一个 `turn` id。

```text
harness.start      provider、模型、根目录、权限、工具、vault
turn.start         问题、工具上限、原生模式
llm.tool_choice    模型的选择、参数、mode=native
llm.native_fallback provider 不支持原生工具，切换到文本
llm.protocol_error 响应不合规（完整文本，已截断）
llm.repaired       修复成功
llm.repair_failed  修复失败
tool.call          tool、参数、索引
tool.result        结果、output/error、以 ms 计的时长
turn.answer        最终回答、使用的工具数量
turn.error         阶段和消息
turn.stop          达到限制
mcp.loaded         命名空间和导入的工具
mcp.failed         命名空间和错误
llm.failed         provider 无法构建（例如缺少密钥）
harness.stop       干净退出（若缺失，进程被强制终止）
memory.enabled     根目录、子目录、上下文轮次
memory.disabled    禁用原因
memory.context     注入 prompt 的轮次和 skill
memory.turn        保存到 vault 的轮次
memory.failed      阶段和错误
```

属性：

- 尽力而为（best effort）的写入：I/O 错误不会中止 harness，并且只
  在 stderr 上报告一次；
- 可配置截断（`audit.max_field_chars`，默认 2000）；
- 哈希链（`prev`/`hash`），可用 `verify_chain` 校验；
- 超过 `audit.max_bytes` 时轮转为 `<file>.<timestamp>`（0 表示禁用）；
- 保留策略：`audit.max_files`（默认 100）最多保留 N 个文件，
  包括当前活动文件；更旧的备份会被删除；
- 使用 `audit.include_outputs: false` 时，工具输出只记录
  为大小；
- 非 JSON 值会被转换为可序列化形式；
- 日志中没有任何 API 密钥；
- 日志还包含工具输出（因此也包含文件内容）：
  必须像工作区一样加以保护。

## 3.10 权限（`core/permissions.py`）

模型是一个主体 × 客体矩阵：

- **Capability**（`IntFlag`）：某个操作可以做什么
  （`FILESYSTEM_READ`、`FILESYSTEM_WRITE`、`FILESYSTEM_CREATE`、
  `FILESYSTEM_DELETE`、`FILESYSTEM_EXEC`、`MEMORY_READ`、
  `MEMORY_WRITE`、`NETWORK`、`MCP_CALL`、`COMPUTE`）。它们用 `|` 组合；
  校验始终是子集判断。
- **Effect**（`IntEnum`）：`ALLOW`、`ASK`、`DENY`。发生冲突时
  取较高值（`DENY > ASK > ALLOW`）。
- **Rule**：capability + 效果 + 可选过滤器 `tools`（glob）、
  `paths` 和 `namespaces`（前缀）+ `reason`。
- **Subject**：谁在请求（agent、user、system），带规则和
  default（未指定时为 `DENY`）。
- **Resource**：决策的客体（目前是带其
  capability 的工具；将来也包括笔记和路径）。
- **Decision**：效果、原因和适用的规则。

`PermissionEvaluator.evaluate(subject, resource, scope)`：

1. 资源必须提供所请求的 capability；
2. **系统上限**（由 `permissions.read/write/shell` 推导）
   必须授予这些 capability；
3. 对每项 capability 应用主体规则：最具体的规则胜出
   （先看过滤器数量，再看前缀长度），相同时取
   更严格的效果；没有规则时适用 default；
4. 当要求多项 capability 时适用 AND：最差的效果胜出。

`ASK` 不是一项决策：它是对人的提问。
`ConfirmationProvider` 负责提出——`ConsoleConfirmation` 询问
`lo faccio? (y/N)`，默认 N——没有确认通道时等同
`DENY`。GUI 将来可以用模态对话框实现同一协议。

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

`policy.yaml` 在构建 LLM **之前**读取。如果它不可读
或无效，harness 对所有策略应用 `DENY`，
记入审计（`policy.failed`）并在聊天中提示；harness 的其余部分
继续运行。主体缺失同样会降级为
`DENY`。

检查发生在 `ToolRegistry.execute`，即唯一的执行点，
并产生 `permission.decision` 和
`permission.confirmation` 事件。

`paths` 作用域比较的是**模型写入的**路径
（已规范化），而不是 sandbox 解析出的路径：绝对路径或
`chdir` 可能无法匹配相对前缀，结果仍是 `DENY`
（fail closed）。

## 3.11 记忆（`memory/store.py`、`memory/tools.py`）

**情景记忆。** harness 把每个已结束的轮次追加到一个
按会话划分的笔记中：

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter 包含 `session`、`type: chat`、`created`；正文为每个轮次
一个区块（`## <timestamp> · <turn>`），包含问题和回答。工具的
输出不会被保存：它们保留在审计中。

在每个轮次开始时，Agent 会把最近的
`memory.context_turns` 个轮次注入 prompt（0 表示禁用注入），并对
问题和回答做截断。当 `memory.context_skills > 0` 时，它最多添加 N 个
与问题相关的**已确认 skill**，依据标题、tags 和内容的词法匹配；
candidate 和已归档的 skill 永远不会进入。该区块被标记为数据，
而不是指令。记忆错误不会中止轮次：会记录 `memory.failed`。

**语义记忆。** 模型可以通过三个工具提出记忆：

| 工具 | capability | 命名空间 |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

`create_skill` 写入 `<vault>/Hagar/skills/<slug>.md`，frontmatter 包含
`id`、`title`、`kind`（`fact`/`procedure`）、`status: candidate`、`tags`、
`source_session`、`source_turn`、`model`、`created_at`。slug 是
安全的（仅 ASCII，不含路径）；已存在的标题不会被
覆盖，并返回 `duplicate: true`。

`get_context` 返回最近的轮次，或在过去的会话中按关键字
搜索；`list_skills` 按 `kind` 和 `status` 过滤。

**生命周期。** 状态有 `candidate`、`confirmed`、`archived`。
LLM 只能创建 candidate；转换由人通过 CLI 完成：

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` 一次显示一个 candidate 及其 provenance 和
内容，然后询问 `y/N/a/s/q`（确认、保留、归档、跳过、
退出）。确认会写入 `reviewed_at`；`archive` 可用
`confirm` 逆转。每次转换都会在审计中产生 `memory.status` 或
`memory.review`。笔记仍是 Obsidian 文件：在
frontmatter 中修改 `status` 具有相同的效果。

**配置**：

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

### 项目记忆

项目记忆与 skill 是分开的：

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

每个项目都有一个 `index.md`，包含状态、最后活动、摘要和
活动决策的数量。每个决策都有状态
`candidate`/`active`/`superseded`/`archived`、备选方案、理由、
provenance 和 `auto_saved`。决策不会被改写：新的
决策可以取代旧的决策。

启动时 Hagar 显示活动项目和“自由活动”：

```text
/project list
/project new <nome>
/project select <nome>
/project free
/project status
/project archive <nome>
/project unarchive <nome>
```

非交互式覆盖项是 `--project <nome>` 和 `--free`。

会话结束时：

1. transcript 被移动到 `archive/chat/`；
2. 用模型生成摘要，带机械回退；
3. 摘要与 transcript 的链接和哈希一起保存；
4. 如果存在项目，LLM 提出 `candidate` 决策；
5. 用户可以复核它们；如果拒绝，它们保持 `candidate` 并带
   `auto_saved: true`。

注入的上下文使用项目的**索引**：摘要、活动决策的标题
和计数，而不是所有正文。细节通过
`memory.project_context(query=..., limit=...)` 读取。整个区块
受 `max_context_chars` 限制；如果被截断，
审计会记录 `memory.context_trimmed`。这不是 token 估算：
而是以字符计的预算，确定性的。

当项目超过 `project_max_active` 时，Hagar 询问是否
归档它。归档是可逆的，不会删除任何内容。

**归档查阅。** 已归档的 transcript 在 frontmatter 中包含 `project`。
搜索和读取是按需的：

```text
/memory archive search <testo>
/memory archive read <session> [offset] [limit]
```

同样的工具以 `memory.archive_search` 和
`memory.archive_read` 暴露；搜索返回 session、turn、timestamp、
项目和片段，读取则对轮次分页。归档不会被自动注入
prompt：摘要仍是索引，transcript 是需要时查阅的
来源。

如果 `vault.path` 不存在或不可写，记忆会被
禁用，并在聊天中给出警告、在审计中记录 `memory.disabled`；其他
组件继续运行。记忆的写入受
策略约束（`MEMORY_READ`/`MEMORY_WRITE`）。

## 3.12 启动与打包

项目通过 `pip install -e .` 安装，并在
`pyproject.toml` 中声明包。入口点是 `hagar = "hagar:main"`。当前
版本是 `0.3.0`。

示例配置是 `hagar.example.yaml`；`hagar.yaml` 是一个
被 git 忽略的本地文件。示例中的默认 Vault 是
`./vault`，必须在启动前创建。

```text
hagar --config PATH       配置文件
hagar --model NAME        覆盖 model.name
hagar --project NAME      选择一个活动项目
hagar --free              以自由活动方式启动
hagar --no-memory         为该会话禁用记忆
hagar --no-native-tools   使用文本 JSON 协议
hagar --version
```

配置按以下顺序查找：`--config`、变量
`HAGAR_CONFIG`、`./hagar.yaml`。`python -m hagar` 可在项目
目录中运行。

GitHub Actions CI 在 Linux、macOS 和 Windows 上以
Python 3.11/3.12/3.13 运行测试套件，构建 sdist 和 wheel，执行 `twine check`，
并测试 wheel 的安装。`Release` 工作流由 `v*` 标签触发，
校验标签与包版本一致，并
创建带产物的 GitHub release。

live 测试被排除在常规套件之外，通过
`--live` 启用：它们会验证 Ollama 和远程 provider（后者仅在
存在 API 密钥时）。

## 3.13 本地工具（`local_tools/`）

它们不是 MCP 服务器：而是本地 provider，向 registry 注册
`ToolDefinition`，并位于 core 之外的一个独立包中。

| 模块 | 工具 | capability |
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

- `clock.now` 返回本地时间、日期、时区、UTC 偏移和 epoch。
- `calendar.date` 把本地日期，或一个可选的 ISO 日期，转换为
  前推儒略历或表格式伊斯兰历
  （Kuwaiti algorithm）。表格式伊斯兰历可能比
  基于观测或 Umm al-Qura 的历法相差一天。
- `think.echo` 原样返回收到的字符串；用于
  在推理链中把中间步骤外置。
- `text.diff` 返回两段文本之间的统一 diff，输入
  上限 20000 字符，输出上限 20000，`context` 为 0..10。它不
  应用该 diff。
- `url.parse` 拆分 scheme、host、端口、path、query 和 fragment，不进行
  DNS 或网络访问；URL 上限 4096 字符，参数上限 100。如果
  URL 含有凭据，会在输出中对其脱敏。
- `clock`、`calendar`、`think`、`text` 和 `url` 不访问文件系统
  或网络，因此适用 `COMPUTE` allow 规则。
- 计算器使用 AST 白名单，而不是 `eval()`，并对
  表达式、节点数量和指数设有上限。
- `feed.read` 使用 `requests` 下载（超时 15 秒，最大 5 MB），只接受
  http/https URL，并使用 `feedparser`；`NETWORK` 策略为 `ask`。
- SSRF：每个 host 都用 `getaddrinfo` 解析，每个地址都必须
  是全局地址；loopback、私有网络、link-local、multicast 和
  保留地址都会被拒绝。重定向不是自动的：每个
  `Location` 都会重新校验，并在 3 次跳转后停止。带
  凭据的 URL 会被拒绝。
- 需要 `permissions.network: true`，系统上限才会
  授予 `NETWORK`；`COMPUTE` 始终在上限内，但策略可以拒绝它。
- `local_tools` 在 `pyproject.toml` 中声明，并随项目
  一起安装。

---

# 4. 安全模型

- 智能体看不到真实文件系统：只有解析到 sandbox
  内部的路径。
- 操作只经过 `ToolRegistry`；没有宿主 shell。
- 权限在配置和策略中声明，并由 sandbox 与
  `PermissionEvaluator` 施加；嵌套的根目录
  可以进一步限制权限。
- 错误也是数据：拒绝会作为工具结果返回给模型，
  而不是被隐藏。
- 每个动作都在审计中留下痕迹，带会话和轮次。

---

# 5. 开发

- 套件：`./tools/run_tests.sh`（Linux/macOS）或
  `.\tools\run_tests.ps1`（Windows）。在 Windows 上：691 个通过，2 个跳过
  （没有 Developer Mode 时符号链接不可用）。在 Debian Linux
  （2026-11-06）：所有测试通过，包括符号链接（693 个通过，0 个
  跳过）。shim 的细节与理由见 README §3.1。
- live 测试：`./tools/run_tests.sh --live`（Linux/macOS）或
  `.\tools\run_tests.ps1 --live`（Windows）——多 9 个测试（Ollama；
  远程 provider 在存在密钥时）。
- 模型对比：`python tools/bench_models.py`（README §3.5）。
- 协议对比：`python tools/bench_native.py --provider ollama`
  （README §3.5）。
- 常规套件不访问网络：Ollama 和 MCP 都是模拟的。

## 5.1 跨平台

- 内部路径使用 `pathlib.Path`；展示给智能体的路径
  始终使用 `/` 和虚拟根目录 `/home/ai`。
- `filesystem.sandbox` 包含宿主机路径，可以是绝对路径，或在用户
  选择时使用 `~`：`Path.expanduser()` 只在路径使用 home 时才
  解析它。不假定存在专用的 home 目录。
- 每个挂载都有一个显式且唯一的别名（大小写不敏感）；
  物理路径可以位于任何卷上。
- `tools/run_tests.sh` 是 POSIX 运行器；`tools/run_tests.ps1` 和
  `tools/pytest_shim` 仅用于 token 受限的 Windows
  sandbox。
- 唯一明确保留的 Windows 分支是 `stat` 中的创建日期：
  在可用时用 `st_birthtime`，否则在 Windows 上用 `st_ctime`；
  在 Linux 上 `created_at` 可以是 `None`。
- 外部 API（OAuth、MCP、LLM）使用 HTTP 和 `webbrowser`，而不是
  系统命令。
- GitHub Actions CI 覆盖 Linux、macOS 和 Windows 上的 Python
  3.11/3.12/3.13；符号链接、OAuth token 权限和 loopback 回调
  仍需通过 live 测试验证，而不在离线套件中。

---

# 6. 已知限制与技术债

- `PermissionEvaluator` 覆盖了 v1：动态主体、GUI
  确认以及由配置分配的 MCP capability 仍然待办。
- 原生 calling 取决于模型：有些会忽略工具或
  返回多个调用；文本回退只覆盖错误，而不覆盖
  选择的质量。
- MCP 客户端支持 bearer/header 和 OAuth authorization code；不
  支持 device flow、DPoP、mTLS 或 client assertion。
- skill 的复核是手动的 CLI 操作；缺少 GUI。
- 记忆中的搜索是按关键字，没有索引，也没有
  embedding。
- 注入的上下文使用全局的最近轮次，以及最多 3 个按词法匹配的
  已确认 skill，没有语义选择。
- 记忆不会按时间清除聊天或 skill：`archive` 是
  从上下文中移除的唯一方式。
- 审计有轮转和保留（`max_files`），但没有会话
  压缩，也没有链的外部锚定。
- `feed.read` 校验地址和重定向，但 DNS rebinding
  的情况仍存在：`requests` 在建立连接时会第二次解析名称；
  需要一个固定（pinned）的解析器。
- 计算器不是 CAS：它只处理有限的数值表达式，
  不支持符号运算。
- 在缺少 `st_birthtime` 的 Linux 上，`stat().created_at` 是 `None`；不会
  凭空编造创建日期。
- 两个别名不能指向同一个物理路径：别名
  标识一个挂载，虚拟输出必须保持唯一。

## 6.1 用户责任：硬链接、挂载与 TOCTOU

**Hagar 不检查允许目录内部的硬链接、挂载/junction 以及 TOCTOU 竞态。**
这不是 Hagar 的缺陷：sandbox 是基于路径的，并不
在整个操作中使用 handle/文件描述符。

硬链接是同一 inode 的第二个名称，它没有路径形式的
目标，sandbox 无法知道外部是否还有另一个名称。挂载或
junction 可以在仍处于路径前缀之内的情况下暴露另一个
文件系统。TOCTOU 竞态可以在符号链接检查与真实操作
之间改变某个路径组件：Hagar 不使用 `openat2`、
对每个组件使用 `O_NOFOLLOW` 或 Windows handle，因此不保证
检查与访问之间的原子性。

Hagar 的文件系统工具不会创建硬链接。如果某个硬链接或
挂载已经存在于 sandbox 的某个目录中，Hagar 会把它当作
普通文件或目录，并可以读取、修改或删除其
内部名称。

因此责任是划分的：

- **Hagar 保证**检查时解析出的路径仍留在别名之内，
  符号链接不可见，`R`/`W`/`X` 权限得到应用，
  并且真实路径不会出现在模型的输出中。
- **用户保证** `filesystem.sandbox` 中配置的目录
  不包含指向不应被访问内容的硬链接、挂载或 junction，
  并且如果希望获得完全隔离，没有任何不可信的并发进程
  会在执行期间修改这些目录。

TOCTOU 竞态需要一个对 sandbox 目录有写权限的本地并发
参与者：它们不是正常使用中的偶然情况，
而是恶意场景或环境被攻破的场景。
要实现强隔离，需要专用卷、独立用户、
挂载命名空间或容器；这不是路径解析器的职责。

这些点作为**用户责任**关闭，而不是 Hagar 的技术债。
本版本不会检测也不会阻止硬链接、挂载/junction
和 TOCTOU 竞态。

---

# 7. 文档地图

- `MANUAL.md` — 用户手册：命令、配置、策略、默认值。
- `ARCHITECTURE.md` — 本文档：系统今天的样子。
- `ROADMAP.md` — 要做什么、已做出的决定和待解决的问题。
- `CHANGELOG.md` — 版本历史。
- `README.md` — 启动、配置、测试。
