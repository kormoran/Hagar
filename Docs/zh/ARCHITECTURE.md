# HAGAR — 架构

版本：0.7.0
最后更新：2026-11-03

---

# 1. Hagar 是什么

Hagar 是一个用 Python 编写的 LLM harness，旨在以弹性方式
运行语言模型。

其目标不是与模型聊天，而是一个**安全**的运行环境，
让 LLM 可以在其中使用工具、查阅持久记忆并与外部
系统交互，而不直接访问宿主机的真实资源。

为此，本项目把 HMI/HCI 与认知工效学的原则应用到
模型运行环境的设计中。

## 1.1 HAGAR 的四条法则

**第一法则——LLM 按定义就不可信。**
不是因为它坏或无用：而是因为它是概率性的。它的每一个
断言都必须被核实，它的每一个动作都必须受到限制。

**第二法则——工具比 LLM 更可靠。**
如果文件系统说某个文件存在，那它就存在。如果工具返回
一个大小，那个大小就是真实的。LLM 解释，工具
测量。

**第三法则——状态必须存在于 LLM 的心智之外。**
ToolRegistry、MCP、FileSystemSandbox 以及（在预期中）
PermissionEvaluator 把知识与控制移出模型之外，
就像在安全关键系统中那样。

**第四法则——每一个动作都必须能在事后得到解释。**
审计日志回答的是正确的问题：不是"LLM 为什么发疯了？"，
而是"它做了什么假设？""它用了哪个工具？""哪个数据是
错的？"。就像航空业那样进行事故调查。

## 1.2 绝对禁令

模型永远不得：

- 直接访问宿主机文件系统；
- 在真实 shell 上执行命令；
- 获取高于配置所定义的权限；
- 得知操作系统的实际组织结构。

所有操作只能通过由 harness 注册并控制的工具进行。

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
  │     ├── LMStudioClient
  │     ├── DeepSeekClient
  │     ├── OpenAIClient
  │     ├── ClaudeClient
  │     └── GeminiClient
  │
  ├── ToolRegistry
  │     ├── filesystem.*
  │     ├── memory.*        (规划中)
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

把一个 YAML 文件（`hagar.yaml`）加载并校验为 `AppConfig`。

各段：

| 段 | 必填 | 内容 |
|---|---|---|
| `model` | 是 | provider、名称、host、timeout、max_tokens、api_key_env、native_tools |
| `vault` | 是 | Obsidian vault 的路径 |
| `filesystem` | 是 | `sandbox`：`{alias, path, permissions}` 列表；`limits`：写入预算 |
| `permissions` | 否 | read、write、shell、network（默认 `true/false/false/false`） |
| `rag` | 否 | `top_k`（默认 8） |
| `mcp_servers` | 否 | endpoint、namespace、auth（bearer/header/oauth） |
| `audit` | 否 | enabled、path、max_field_chars、max_bytes、max_files、include_outputs |
| `policy` | 否 | policy 文件路径、subject |
| `memory` | 否 | enabled、vault_subdir、context_turns、context_skills、max_skill_chars |

校验错误总是产生 `ConfigError`，并在消息中指出
相应字段。审计路径若为相对路径，则相对于
配置文件解析。

## 3.2 LLM 接口与后端（`llm/`）

`LLMClient` 有两条路径：

- **原生 calling**（默认）：`native_step()` 以 provider 的格式发送
  工具 schema，并从响应中读取调用；
- **文本 JSON 协议**（回退）：`request_tool_call()` 请求一个
  包含 `tool`/`arguments` 的 JSON，使用稳健的解析，并尝试
  一次修复。

参数 schema 由 `ToolDefinition` 构建：
OpenAI/Ollama 使用 `tools[].function`，Claude 使用 `tools[].input_schema`，
Gemini 使用 `functionDeclarations`。规范对话使用
`user`/`assistant`/`tool` 三种角色；每个客户端都会翻译它（OpenAI `tool_calls`，
Claude 的 `tool_use`/`tool_result` 块，Gemini 的 `functionCall`/
`functionResponse`）。HTTP 400/404/422 拒绝会产生
`NativeToolsUnavailable`：仅当尚未执行过任何工具时，Agent 才
切换到文本协议。

对于不允许句点的 API，工具名会被规范化
（`filesystem.read_file` → `filesystem__read_file`），并在响应中
还原为内部名称：策略、审计和测试看到的始终是
原始名称。

对于不支持原生工具的模型，文本仍是回退方案；
`model.native_tools: false` 可强制使用它（或在 CLI 中使用 `--no-native-tools`）。

| provider | API | 密钥 | 说明 |
|---|---|---|---|
| `ollama` | `/api/chat`、`/api/generate` | — | 默认 host `localhost:11434` |
| `lmstudio` | `/v1/chat/completions`（OpenAI） | 可选 `LMSTUDIO_API_KEY` | 默认 host `localhost:1234/v1` |
| `deepseek` | `/chat/completions`（OpenAI） | `DEEPSEEK_API_KEY` | system 内联 |
| `openai` / `chatgpt` | `/v1/chat/completions` | `OPENAI_API_KEY` | ChatGPT 通过 API，而非订阅 |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system 独立，轮次交替 |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`、角色 `model` |

密钥只从环境变量读取；`model.api_key_env` 会覆盖
默认名称。`model.host` 是所有 provider 的 base URL（每个 provider 有
自己的默认值），`model.timeout` 是 HTTP 超时（默认 120），
`model.max_tokens` 仅由 Claude 使用。
`llm/factory.py` 构建客户端，并拒绝未知 provider 或
缺失的密钥。内置 provider 是 `llm/plugins.py` 中的 spec；外部
provider 通过 entry point `hagar.llm` 和一个工厂函数
`(config, audit) -> LLMClient` 注册（见 `PLUGINS.md`）。LM Studio
不需要密钥，除非服务器配置要求；OpenAI 需要 API
密钥，而不是 ChatGPT 订阅。
DeepSeek：当前模型是 `deepseek-flash` 和
`deepseek-v4-pro`；`deepseek-chat` 不再被接受。

当前状态：**原生 calling v1**，带自动文本回退
（见 ROADMAP）。

## 3.3 工具模型（`core/tool_*.py`）

`ToolDefinition` 描述名称、描述、类别、参数、
handler、`origin`（`local` 或 `mcp.<namespace>`）、声明的
`capabilities`、启用状态以及 `requires_confirmation`
（由 registry 施加的 ASK 底线）。

`ToolCall` 是模型的请求（`tool`、`arguments`、`id`）；
`ToolResult` 是结构化的结果（`tool_name`、`success`、`output`、
`error`）。

`ToolRegistry` 注册、查找、启用/停用并执行工具；
它向模型暴露元数据，并且是唯一的执行点。

## 3.4 Agent（`core/agent.py`）

多步智能体循环，有两条路径：

- **原生**：一次响应可以包含多个调用；Agent 会重新入队
  `assistant` 消息，以及每个结果带 id 的 `tool` 消息；
- **文本**：一次一个调用，结果作为
  `user` 轮次发送。

两者都是：

1. 模型决定是否需要工具；
2. 如果不需要，最终回答结束该轮次；
3. 如果需要，执行该工具，结果返回模型；
4. 限制 `max_tool_calls` 作用于整个轮次。如果模型
   一味坚持，轮次会以 `Agent stopped after N tool calls`
   结束（防循环保护）。

如果第一个原生步骤以 `NativeToolsUnavailable` 失败，Agent
会切换到文本协议（`llm.native_fallback`）；在执行过
工具之后出错，则以 `turn.error` 关闭轮次，不回退。

每一步都会被记入审计：问题、工具选择、参数、
结果、耗时和最终回答。审计故障不会停止 agent：该
故障会在 stderr 上报告。

`Agent` 接收 `Vault`，但尚未使用它。

## 3.5 FileSystemSandbox（`core/filesystem.py`）

智能体的虚拟文件系统。每个请求都会：

1. 针对当前目录解析（`resolve_path`）；
2. 依据授予的根进行校验（`effective_permissions`）；
3. 由有效权限过滤，更具体的根会
   覆盖更外层的根；
4. 针对 symlink 和可用磁盘空间进行检查
   （`FS_Guardian`，历史名称）。

`DirectoryPermissions` 建模 `read`、`write`、`create`、`rename`、
`delete`、`execute`；`None` 表示"从外层根继承"。
根之外的路径始终是 `PermissionError`。

`FileInfo` / `stat()` 返回类型、字节大小、创建/修改/访问
日期（带本地偏移的 ISO 8601），以及 **sandbox 的有效
权限**，而不是操作系统的 ACL。

**对 sandbox 而言 symlink 并不存在。** Hagar 不显示、不读取、
不跟随也不删除它们：`stat`、`list_dir` 和 `search` 会忽略它们；
`read_file`、`read_chunk` 和 `delete_file` 回答"not
found"；对 symlink 执行 `chdir` 回答"Directory not found"。一个
失效的或指向外部的链接，与一个不存在的路径无法区分。

sandbox 的虚拟根是 `/home/ai`；每个已配置的目录
都暴露为 `/home/ai/<alias>`。`stat`、`list_dir`、`search`、
`read_chunk`、`write`/`create`/`mkdir`/`delete` 的消息以及 `chdir`
都只显示虚拟路径：物理路径永远不会出现在
模型的输出中。输入 `/home/ai/<alias>/...` 会针对
该 alias 的物理目录解析；相对路径则相对于
当前目录。

`/home/ai` 是一个合成目录：可以列出和 stat，但它
不是 mount，也无法用 `chdir` 进入。`filesystem.sandbox` 的条目
仍是宿主系统的路径，可以是绝对的，或在用户选择时带
`~`：它可以是任何存在且可达的目录。Hagar 不会创建目录，
也不假定有专用的 home。

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

没有 `enabled` 标志：`filesystem.sandbox` 中每个有效条目
都会被挂载。无效的 alias 或权限、缺失的路径或重复的路径
会使配置中止。物理路径和内部名称可以
包含空格；alias 不可以，因为它必须保持为单个虚拟
路径段。

`R` 涵盖读取、列出、搜索和 `stat`；`W` 涵盖写入、
创建、重命名、复制和删除；`X` 涵盖 `chdir`。全局
权限 `permissions.read`/`write` 仍是上限：一个 `RWX` 的 alias
不能超过它们。

## 3.6 文件系统工具（`core/filesystem_tools.py`）

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

`list_dir` 返回 `FileInfo` 元数据；`read_chunk` 按字节
读取，带 `has_more`、`next_offset` 和完整的 UTF-8 边界；`search` 使用
带结果上限的递归 glob；`copy_file` 需要 `create`；
`rename` 需要对源有 `rename`，对目标有 `create`。
返回的路径始终是虚拟的（`/home/ai/<alias>/...`）。
`chdir` 需要对 alias 有 `X`。

`list_dir` 每页最多返回 100 个条目（`limit` 最大
500），带 `offset`、`next_offset` 和 `has_more`；如果还有更多条目，
`message` 会说 `voci: riportate X di Y; per continuare usa offset=Z`。
`search` 使用相同的分页：`max_results` 是每页上限
（默认 100，最大 500），`offset` 用于翻动结果。对于大型
目录树，最好收紧 `pattern`/`path`，而不是遍历很多
页。`read_file` 只接受不超过 `CHUNK_SIZE`（4096 字节）的文件；
超过时，错误会指向 `read_chunk()`，因为读取整个文件
会超出上下文窗口。`read_chunk` 返回 `next_offset` 和
完整的 UTF-8 边界。

`list_dir` 和 `search` 不显示 symlink；`read_file` 和 `read_chunk`
把它们当作不存在的文件。

`write_file` 只覆盖已存在的文件；创建要通过
`create_file`，它需要 `create` 权限。无法通过写入
一个新路径来绕过创建禁令。

`read_file`、`read_chunk` 和 `read_bytes` 会记录文件的一个已观测
版本。`write_file`、`edit_file`、`delete_file` 和 `rename` 要求
该文件已在同一 sandbox 中被读取，且版本在此期间没有
变化。版本是 `(st_mtime_ns, st_size)`：它是对盲目覆盖的
协作式保护，而不是针对 TOCTOU 竞态的 CAS。

`edit_file` 把 `old_string` 字面替换为 `new_string`。默认
该字符串只能出现一次；`replace_all` 允许
多次替换。写入使用同一目录中的临时文件和
`os.replace`，因此内容永远不会被看到处于半写状态。
同样的原子机制也用于 `write_file`、`write_bytes` 和
`create_file`。

### 写入限制

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = 停用
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` 是 `write_file`、`create_file` 或 `copy_file`
  单次操作的最大值；
- `min_free_bytes` 是操作之后必须保留的
  空间储备；
- `session_write_bytes` 是会话的累计预算；
- `ask_over_bytes` 把超过阈值的操作提升为 `ASK`。预检
  已集成在 `ToolRegistry` 中：如果策略也说是 `ASK`，则只有一次
  确认。

`0` 表示停用单个限制。超过 `max_write_bytes`、
`session_write_bytes` 或储备会产生错误，而不是确认：
它们是不变式，不是询问。`ask_over_bytes` 是唯一会
询问用户的层级。

`filesystem.stat` 返回包含 `path`、`exists`、`kind`
（`file`/`directory`/`other`）、`size_bytes`、`created_at`、`modified_at`、
`accessed_at`、`permissions` 的 JSON。不存在的路径不是错误：
`exists: false`，并给出适用的权限。

## 3.7 MCP（`llm/mcp_client.py`）

通过 HTTP/JSON-RPC 的 MCP 客户端：`initialize`、`tools/list`、`tools/call`，
自动把工具转换为 `ToolDefinition`，并以
命名空间 `mcp.<namespace>` 注册。

它还支持 `text/event-stream` 响应（streamable HTTP），并在
握手后发送 `notifications/initialized` 通知。它使用
`MCP-Protocol-Version`（默认 `2025-06-18`，带回退），并在服务器返回时
复用 `Mcp-Session-Id`。HTTP 错误
会包含响应体，以便诊断 400。工具结果会被规范化为文本：`text` 块，
否则为 `structuredContent` 或 JSON；带有 `isError`
的结果会变成工具错误。

每个服务器的认证：

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer          # 或 "header"
      token_env: MCP_EXAMPLE_TOKEN
      # header: X-API-Key  # 仅用于 type: header
```

token 只从环境变量读取，不会出现在审计中。如果缺失，
该服务器会以 `mcp.failed` 被跳过，harness 继续运行；其他
服务器仍可用。

### 交互式 OAuth

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # 没有则 dynamic registration
    # client_secret_env: MCP_CLIENT_SECRET
    scopes: [mcp.read]
    audience: api.atlassian.com  # 可选，用于 3LO provider
    redirect_port: 8765       # 0 = 随机端口
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

authorization code + PKCE 流程，回调位于
`http://localhost:<port>/oauth/callback`，并会打开浏览器。如果
scope 包含 `offline_access`，会添加 `prompt=consent`。
元数据从 `.well-known` 发现（资源用 RFC 9728，
authorization server 用 RFC 8414）；如果缺少 `client_id`，则
使用动态注册。token 存放在权限受限的本地文件中
（在系统支持的地方为 `0600`），带自动刷新，并在 `401` 时重试一次。

在等待回调期间按 Ctrl-C 会关闭本地服务器，并以代码 130
退出，不打印 traceback。

限制：没有 device flow、DPoP、mTLS 或 client assertion；浏览器必须
能够到达本地回调。如果回调没有到达，
终端会要求粘贴重定向 URL。

## 3.8 Vault（`memory/vault.py`）

以相对于根目录的路径访问 Obsidian vault，并
防止逃出 vault。它提供读取、写入、追加、
文件列表以及用于递归读取的 `load_all`。记忆的语义
位于 `memory/store.py`（§3.11）。

## 3.9 审计日志（`core/audit.py`）

仅追加的 JSON Lines 文件。每行都有 UTC 时间戳、`session` 和
`event`；同一问题的各个事件共享同一个 `turn` id。

```text
harness.start      provider、模型、根、权限、工具、vault
turn.start         问题、工具上限、原生模式
llm.tool_choice    模型的选择、参数、mode=native
llm.native_fallback provider 不支持原生工具，切换到文本
llm.protocol_error 响应不符合约定（全文，已截断）
llm.repaired       修复成功
llm.repair_failed  修复失败
tool.call          tool、参数、索引
tool.result        结果、输出/错误、耗时（毫秒）
turn.answer        最终回答、使用的工具数量
turn.error         阶段和消息
turn.stop          达到限制
mcp.loaded         命名空间和导入的工具
mcp.failed         命名空间和错误
llm.failed         provider 无法构建（例如缺少密钥）
harness.stop       干净退出（若缺失，说明进程被杀）
memory.enabled     根、子目录、上下文轮次
memory.disabled    停用原因
memory.context     注入 prompt 的轮次和 skill
memory.turn        保存在 vault 中的轮次
memory.failed      阶段和错误
```

属性：

- 尽力写入：I/O 错误不会停止 harness，并且只在
  stderr 上报告一次；
- 可配置的截断（`audit.max_field_chars`，默认 2000）；
- hash 链（`prev`/`hash`），可用 `verify_chain` 验证；
- 超过 `audit.max_bytes` 时轮转到 `<file>.<timestamp>`（0 表示停用）；
- 保留：`audit.max_files`（默认 100）最多保留 N 个文件，
  包括当前活动文件；较旧的备份会被删除；
- 使用 `audit.include_outputs: false` 时，工具输出只记录
  为大小；
- 非 JSON 值会被转为可序列化；
- 日志中不含任何 API 密钥；
- 日志也包含工具输出（因此包含文件内容）：
  必须像 workspace 一样保护它。

## 3.10 权限（`core/permissions.py`）

模型是一个主体 × 客体矩阵：

- **Capability**（`IntFlag`）：一个操作能做什么
  （`FILESYSTEM_READ`、`FILESYSTEM_WRITE`、`FILESYSTEM_CREATE`、
  `FILESYSTEM_DELETE`、`FILESYSTEM_EXEC`、`MEMORY_READ`、
  `MEMORY_WRITE`、`NETWORK`、`MCP_CALL`、`COMPUTE`）。用 `|` 组合；
  校验始终是子集判断。
- **Effect**（`IntEnum`）：`ALLOW`、`ASK`、`DENY`。冲突时
  取较高的值（`DENY > ASK > ALLOW`）。
- **Rule**：capability + 效果 + 可选过滤器 `tools`（glob）、
  `paths` 和 `namespaces`（前缀）+ `reason`。
- **Subject**：谁在请求（agent、用户、系统），带规则和
  default（未指定时为 `DENY`）。
- **Resource**：决策的客体（目前是一个带其
  capability 的工具；将来也包括笔记和路径）。
- **Decision**：效果、原因和所应用的规则。

`PermissionEvaluator.evaluate(subject, resource, scope)`：

1. 资源必须提供所要求的 capability；
2. **系统上限**（由 `permissions.read/write/shell` 导出）
   必须授予它们；
3. 对每项 capability 应用主体的规则：最具体的
   胜出（先比较过滤器数量，再比较前缀长度），相同时
   取更严格的效果；没有规则时适用 default；
4. 当要求多项 capability 时适用 AND：最差的效果胜出。

`ASK` 不是一种决策：它是对人的提问。
`ConfirmationProvider` 提出它——`ConsoleConfirmation` 询问
`lo faccio? (y/N)`，默认 N——没有确认通道时就等于
`DENY`。GUI 可以用模态对话框实现同一协议。

在 CLI 中，`core/input_broker.py` 是控制台的唯一所有者：
它分发提示、确认和 `F5`/`F8` 按键，把终端标题设为
注意信号，并在结束时恢复正常模式。在非交互式 stdin 上
回退到 `input()`。

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

`policy.yaml` 在构建 LLM **之前**读取。如果它不可读或
无效，harness 对所有策略应用 `DENY`，
将其记录到审计（`policy.failed`）并在聊天中报告；harness 的其余
部分继续运行。主体缺失同样会降级为
`DENY`。

检查发生在 `ToolRegistry.execute`，即唯一的执行点，
并产生 `permission.decision` 和
`permission.confirmation` 事件。

`paths` 作用域比较的是**模型所写的**路径
（已规范化），而不是 sandbox 解析出的路径：绝对路径或
`chdir` 可能无法匹配相对前缀，结果仍是 `DENY`（fail closed）。

## 3.11 记忆（`memory/store.py`、`memory/tools.py`）

**默认后端：SQLite。** `memory/sqlite_store.py` 和
`memory/database.py` 使用一个本地数据库（`%LOCALAPPDATA%/Hagar/memory.db`
或 `HAGAR_MEMORY_DB`）作为会话、轮次、skill 和
summary 的事实来源。SQLite 使用 WAL、事务和 `busy_timeout`；备份是
`VACUUM INTO`。下文描述的 `markdown` 后端仅
为兼容性而保留，不再是默认值。

**情景记忆。** harness 把每个已结束的轮次追加到按会话
划分的笔记中：

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

frontmatter 包含 `session`、`type: chat`、`created`；正文中每个轮次一个
小节（`## <timestamp> · <turn>`），包含问题和回答。不会
保存工具输出：它们保留在审计中。

在每个轮次开始时，Agent 会把最近
`memory.context_turns` 个轮次注入 prompt（0 表示停用注入），并截断
问题和回答。当 `memory.context_skills > 0` 时，它会加入最多 N 个
与问题相关的**已确认 skill**，依据标题、tags 和内容做词法匹配；
candidate 和已归档的永远不会进入。该块被标记为数据，而非指令。
记忆错误不会停止轮次：会记录 `memory.failed`。

**语义记忆。** 模型可以用三个工具提出记忆：

| tool | capability | namespace |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

`create_skill` 写入 `<vault>/Hagar/skills/<slug>.md`，frontmatter 包含
`id`、`title`、`kind`（`fact`/`procedure`）、`status: candidate`、`tags`、
`source_session`、`source_turn`、`model`、`created_at`。slug 是
安全的（仅 ASCII，不含路径）；已存在的标题不会被
覆盖，并返回 `duplicate: true`。

`get_context` 返回最近的轮次，或在过去的会话中按关键词
搜索；`list_skills` 按 `kind` 和 `status` 过滤。

**生命周期。** 状态有 `candidate`、`confirmed`、`archived`。
LLM 只创建 candidate；状态转换由人在 CLI 中完成：

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` 一次显示一个 candidate，含来源和
内容，然后询问 `y/N/a/s/q`（确认、保留、归档、跳过、
退出）。确认会写入 `reviewed_at`；`archive` 可用
`confirm` 逆转。每次转换都会在审计中产生 `memory.status` 或 `memory.review`。
笔记仍是 Obsidian 文件：在 frontmatter 中修改 `status`
具有同样效果。

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

项目记忆与 skill 分开：

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

每个项目都有一个 `index.md`，含状态、最后活动、summary 和
活动决策的计数。每个决策都有状态
`candidate`/`active`/`superseded`/`archived`、备选方案、理由、
来源和 `auto_saved`。决策不会被改写：新的
决策可以取代旧的决策。

使用 `memory.backend: sqlite` 时，项目和决策使用同一数据库中的
`projects` 和 `decisions` 表；遗留 Markdown 后端
仍使用 Vault。

启动时 Hagar 显示活动项目和"自由活动"：

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

在会话结束时：

1. transcript 被移动到 `archive/chat/`；
2. 用模型生成一个 summary，并有机械式回退；
3. summary 会连同 transcript 的链接和 hash 一起保存；
4. 如果有项目，LLM 会提出 `candidate` 决策；
5. 用户可以审查它们；如果拒绝，它们保持 `candidate`，并带
   `auto_saved: true`。

注入的上下文使用项目的**索引**：summary、活动决策的
标题和计数，而不是所有正文。细节用
`memory.project_context(query=..., limit=...)` 读取。整体块
受 `max_context_chars` 限制；如果被裁剪，
审计会记录 `memory.context_trimmed`。这不是 token 估算：它是
以字符为单位的预算，确定性的。

当一个项目超过 `project_max_active` 时，Hagar 会询问是否
归档它。归档是可逆的，不会删除任何东西。

**查阅归档。** 已归档的 transcript 在 frontmatter 中带有 `project`。
搜索和读取是按需的：

```text
/memory archive search <testo>
/memory archive read <session> [offset] [limit]
```

同样的工具作为 `memory.archive_search` 和
`memory.archive_read` 暴露；搜索返回 session、turn、timestamp、
项目与 snippet，读取则对轮次分页。归档不会被
自动注入 prompt：summary 仍是索引，transcript 才是需要时
查阅的来源。

如果 `vault.path` 不存在或不可写，记忆会被
停用，并在聊天中给出警告、在审计中记录 `memory.disabled`；其他
组件继续工作。记忆写入受策略约束
（`MEMORY_READ`/`MEMORY_WRITE`）。

## 3.11.1 服务层（`core/service.py`）

`HarnessService` 是 `Harness` 之上稳定的 API：它不从
`input()` 读取，不写 stdout，也不了解 CLI。它暴露：

- `ask(question)`，带 `turn.start`、`turn.answer`、`turn.error` 事件；
- 由 `Agent` 和 `ToolRegistry` 转发过来的工具与权限事件：
  `tool.call`、`tool.result`、`permission.decision`、
  `permission.confirmation`；
- `status()`，含模型、项目、记忆、审计、策略和工具；
- `list_projects()`、`current_project()`、`set_project()`、
  `clear_project()`、`create_project()`；
- `finish_session()`。

事件是 `ServiceEvent(type, data, ts)`，可由 sink（CLI、GUI、测试）
消费。当前 CLI 使用该服务处理轮次、
项目选择和会话关闭。

## 3.11.2 命令服务（`core/command_service.py`）

`CommandService` 把斜杠命令转换为 `CommandResult`：

```text
command, ok, lines, data, error, requires_input
```

它处理 `/help`、`/tools`、`/status`、`/mcp`、`/audit`、`/project` 和
`/memory`，而不写 stdout。CLI 打印 `lines`；GUI 将使用
`data`。`/memory` 的交互式审查仍交由 `MemoryCLI`，
因为它需要人工输入。CLI 对所有斜杠命令都使用该命令服务，
但 `/memory review` 除外。

## 3.11.3 web GUI（`core/web.py`）

`hagar web` 启动一个本地 `ThreadingHTTPServer`，提供：

- `GET /` 聊天页面；
- `GET /static/style.css` 和 `/static/app.js`（资源在 `web/` 中）；
- `GET /api/events` SSE 流；
- `POST /api/message`、`/api/confirm`、`/api/project`、`/api/stop`、
  `/api/new-chat`、`/api/resume`；
- `GET /api/status`、`/api/projects`、`/api/pending`；
- `GET /api/history`、`/api/history/<session>`；
- `GET /api/tools`、`/api/audit`、`/api/thinking`；
- `GET /api/memories`、`/api/memory?path=...`。

GUI 的标签页是 Chat、Chat history、Tool output、Audit、Thinking 和
Memories。侧边栏保留项目、状态和 token；历史记录在专门的
标签页中。`SessionLog` 为 Tool output 和 timeline 保存会话事件；
Audit 读取 JSONL；Thinking 优先使用 provider 暴露的
reasoning，否则显示 timeline。Memories
读取索引，排除聊天、归档和 summary。

点击过去的聊天会调用 `POST /api/resume`：transcript
被重新加载，审计/记忆会话回到该 id，因此
新轮次会继续同一聊天。`POST /api/new-chat` 调用
`MemoryStore.new_session()` 并切换会话，而不触碰
先前的 transcript。

静态资源位于 `web/`（`index.html`、`style.css`、
`app.js`）。`render_index()` 只注入 token；其余内容
通过白名单和 `importlib.resources` 原样提供。

GUI 只是一个 adapter：它使用 `HarnessService`、`CommandService` 和
`QueueConfirmationProvider`。ASK 确认会把轮次线程阻塞在
一个 `threading.Event` 上；服务器保持空闲，并通过
`POST /api/confirm` 解除该请求的阻塞。超时视为拒绝。

侧边栏显示会话的累计 token：`UsageLedger` 通过
`usage_sink` 从每次 LLM 调用接收 usage，并通过 SSE 发布
`usage.updated`。

**Stop：** `POST /api/stop` 调用 `Agent.cancel()`；agent 在
一个步骤与下一步之间检查该事件，并抛出 `AgentCancelled`。轮次会以
协作方式中断，不会中止已经发起的 HTTP 请求。

**Vision：** `POST /api/message` 接受 `images` 为 PNG/JPEG/WebP 的 data URL
（最多 4 张，每张 10 MB）；JSON body 可达
64 MB。`core/images.py` 负责校验和转换；`Agent.ask(question,
images=...)` 构建多模态 content。OpenAI 兼容/LM Studio 的 adapter
使用 `image_url`；Claude 使用 `image` 块；
Gemini 使用 `inlineData`。LM Studio 不直接接受 WebP：
GUI 会把它转换为 PNG。图片不会进入
Markdown 记忆，也不会进入审计。

安全：默认绑定 `127.0.0.1`，随机 token 注入
页面，API 使用 `X-Hagar-Token` 头，SSE 使用 `?token=`。它不支持
多用户，也尚不暴露 Vault 的修改。

## 3.11.6 Vision 输入（`core/images.py`）

`ImageInput` 校验 data URL、MIME 和大小；`Agent.ask` 使用规范的
部分（`text`、`image`），每个后端把它们翻译成自己的
格式。停止和图片的文本与持久内容分开：
记忆只保留问题和回答。

`vision.open` 从 sandbox 读取图片，用 magic number
校验，并作为 `ToolResult.images` 返回。`Agent` 循环会在下一次
调用之前把图片附加到一条合成的用户消息上，因此模型能看到它，
而不会在工具文本中收到 base64。限制：每轮最多 4 张图片，每张 10 MB，
PNG/JPEG/WebP。
child 可以在自己的只读 workspace 中使用 `vision.open`。

音频尚未实现。附件通道本可复用，但
需要不同的音频原生 provider 契约、格式/解码器，以及在
ASR 与音频理解之间做出明确选择；它在路线图中，但没有
时间表。

`memory/export.py` 把 SQLite 数据库导出为 Markdown：
`Hagar/chat/`、`Hagar/skills/`、`Hagar/summaries/`、
`Hagar/projects/<id>/index.md` 和 `decisions/`。写入是原子的
（临时文件 + `os.replace`），且在没有 `--force` 时命令会拒绝
非空目标。

`memory_fts` 是同一数据库中的 FTS5 表，包含列
`entity`、`entity_id`、`kind`、`project`、`status`、`title`、`body`。
`SqliteMemoryIndex.search` 使用 `MATCH`、`bm25()` 和 `snippet()`；如果 FTS5
不可用，则回退到 `LIKE`。`memory/import_markdown.py` 用 upsert 导入
同一结构，并重建 FTS 索引。

## 3.11.4 Token 用量（`core/usage.py`）

`TokenUsage` 规范化 input、output、cache 和 reasoning。
函数 `usage_from_openai`、`usage_from_anthropic`、`usage_from_gemini` 和
`usage_from_ollama` 读取响应的原生字段。

`LLMClient._set_usage()` 更新 `last_usage`，并调用客户端的
`usage_sink`。`HarnessService` 拥有 `UsageLedger`，把它连接到
客户端并发布 `usage.updated`；GUI 在侧边栏使用它，`/usage`
从 CLI 读取它。provider 的 usage 是
事实来源；本地估算只是回退。

## 3.11.5 记忆索引（`memory/index.py`）

`MemoryIndex` 是一个从 Markdown Vault 派生的 SQLite 索引：

- 表 `documents`、`meta` 和 `documents_fts`（FTS5）；
- 按 hash/mtime/size 进行增量同步；
- `rebuild()` 从头重建；
- 带 `project`、`kind`、`status` 过滤器的搜索；
- FTS5 不可用时回退到 `LIKE`；
- 数据库位于应用的本地数据中，而不在同步的 Vault 中。

工具 `memory.search` 使用该索引；`/memory reindex` 和 `/memory stats`
暴露维护与状态。使用默认 SQLite 后端时，
事实来源是 `memory.db`；旧的 `MemoryIndex` 仅用于
遗留 Markdown 后端。

## 3.11.7 决策工具（`core/decisions.py`）

`DecisionRegistry` 选择一个 `DecisionProvider`，`decision.choose`
向模型暴露该选择。内置 provider 有：

- `llm`：向 LLM 客户端请求一个包含 `choice` 和 `probabilities` 的 JSON，
  校验 label 并规范化概率；
- `linear`：加载一个含 label、权重和 bias 的本地 JSON 模型，并用
  softmax 产生概率。

capability `DECISION` 与 `COMPUTE`、`NETWORK` 和
`FILESYSTEM_*` 分开；细节和模型格式见
`DECISIONS.md`。Jev/Kev 尚不是原生 adapter。

## 3.11.8 Hi-Fi（`core/hifi.py`）

`HiFiResolver` 在智能体循环之前执行一次预检：

1. 向模型询问各种解释及其概率；
2. 规范化并排序概率；
3. 如果第一与第二之间的差距超过 `hifi.margin`，就用所选
   解释加上原始文本替换请求；
4. 否则向模型提出一个澄清问题。

事件 `hifi.interpretations` 记录概率和可能的
澄清。无效 JSON 会产生 `hifi.failed`，轮次
在没有预检的情况下继续。

## 3.11.9 Checkpoint（`core/checkpoints.py`）

`HarnessService.ask` 在 sandbox 上打开一个 `WorkspaceCheckpoint`。
checkpoint 不复制 workspace：它只记录某个变更
即将改动的文件。`delete_file`、`rename` 和 `copy_file` 还会记录
目标。`/undo` 恢复最后一个已完成的 checkpoint。

限制：32 MB 快照，仅普通文件，仅最后一个轮次。
如果 checkpoint 不完整，undo 会被拒绝。

## 3.11.10 运行时防护与上下文（`core/tool_registry.py`、`core/context.py`）

`ToolRegistry` 应用：

- `tools.timeout` 对单次调用，通过守护 worker；
- `tools.repeat_limit` 针对每轮 `tool + 参数` 的 hash。

超时是尽力而为：已经启动的 Python handler 不会被
杀死。repeat guard 在每次 `Agent.ask` 时清零计数。

`OutputSpiller` 把超过 12,000 字符的输出移到
`ArtifactStore`，并返回带 `artifact_id` 的摘要。
`ContextCompactor` 在上下文超过 24,000 字符时替换较旧的消息，
保留最后 8 条和 system 消息。

## 3.11.11 AIsh（`core/aish.py`、`local_tools/aish_tool.py`）

`aish.exec` 实现一种命令语言，而不是宿主 shell。
`AishExecutor` 用 `shlex` 解析，拒绝重定向、运算符、
变量和命令替换，并把每条命令转换为对
`ToolRegistry` 的调用。capability `AISH` 被默认 policy 拒绝；
启用它需要显式修改：

```yaml
- capabilities: [AISH]
  effect: allow
  tools: ["aish.*"]
```

内部命令保留底层工具的规则：启用
`aish.exec` 不会启用 `filesystem.delete_file`。

## 3.11.12 `text.transform`（`local_tools/text_transform_tool.py`）

只读工具，操作可枚举：`grep`、`sort`、`uniq`、`cut`、
`tr`、`wc`、`head`、`tail`、`sed_replace`。接受 sandbox 路径
或内联文本；对输入、输出、pattern 和 match 施加限制。

Capability：

```text
FILESYSTEM_READ | COMPUTE
```

不写文件。AIsh 用它处理文本命令；结果的
保存走 `filesystem.write_file`/`create_file`，并带
read-before-write gate。

## 3.11.13 `dev.run`（`core/dev_recipes.py`、`core/dev_runner.py`）

`DevRecipeLoader` 在启动时只读取一次 `recipes.yaml`，
并保留带 hash 的不可变快照。该文件必须位于
可写 sandbox 之外。

`DevRunner` 执行一个 recipe：

- 校验类型化参数和 `cwd`；
- 把项目复制到临时目录；
- 以 `shell=False` 执行单个 argv；
- 使用最小环境；
- 应用超时并 kill 进程组；
- 分离 stdout/stderr；
- 限制输出；
- 记录审计。

capability `DEV_EXEC` 默认 DENY。`dev.run` 不接受任意
命令，也不使用容器：recipe 是受信的；sandbox 不
隔离宿主进程。容器仍为将来直接访问真实
文件系统/程序而保留（冻结）。

## 3.11.14 Boxed transform（`core/boxes.py`）

box 是带固定 prompt、输入/输出走文件、
没有记忆、工具或自主性的有界 LLM 函数。

工具：

```text
box.list
box.run
```

初始 box：

```text
summarize
translate
extract_json
```

`BoxRunner` 从 sandbox 读取输入，在需要处应用分块，
调用 LLM 客户端，校验输出 JSON，并在
read-before-write gate 下写入结果。`BOX_EXEC` 默认 DENY。

## 3.11.15 Hagar Flow（`core/flow/`）

`validate()` 用 `ast.parse` 解析代码，拒绝 import、类、
函数、lambda、try、dict/set comprehension、多于
一个 `for` 的 comprehension、dunder 和动态调用，并校验
可用的原语。带单个 `for` 和可选 `if` 的 list comprehension
受支持。

`FlowRunner` 在没有 `eval`/`exec` 的情况下解释已验证的 AST：

- 线性作用域；
- step、迭代、工具调用和超时的预算；
- `fs.*`、`box.*`、`memory.*` 和 `project.context` 原语由
  内部 registry 传入；
- 每个原语的 policy 和确认；
- 带行和列的错误。

`FLOW_EXEC` 默认 DENY。`flow.run` 从不修复代码：
`flow.repair` 提出一个有效候选而不执行它，最多
`flow.repair_attempts` 次尝试。运行时、policy、
确认和超时错误不会被修复。HIR 尚未出现：
已验证的 AST 就是 MVP 的 IR。

## 3.12 启动与打包

项目用 `pip install -e .` 安装，并在
`pyproject.toml` 中声明包。entry point 是 `hagar = "hagar:main"`。当前
版本是 `0.7.0`。

示例配置是 `hagar.example.yaml`；`hagar.yaml` 是一个
被 git 忽略的本地文件。示例的默认 Vault 是
`./vault`，必须在启动前创建。

```text
hagar --config PATH       配置文件
hagar --model NAME        覆盖 model.name
hagar --project NAME      选中一个活动项目
hagar --free              以自由活动启动
hagar --no-memory         为本会话停用记忆
hagar --no-native-tools   使用文本 JSON 协议
hagar --version
```

配置按以下顺序查找：`--config`、环境变量
`HAGAR_CONFIG`、`./hagar.yaml`。`python -m hagar` 可在项目
目录中运行。

GitHub Actions CI 在 Linux、macOS 和 Windows 上以
Python 3.11/3.12/3.13 运行测试套件，构建 sdist 和 wheel，执行 `twine check`，
并验证 wheel 的安装。`Release` workflow 从 `v*` 标签
启动，校验标签与包版本一致，
并用构建产物创建 GitHub release。

live 测试不在常规套件中，通过
`--live` 启用：它们验证 Ollama 和远程 provider（后者仅在
API 密钥存在时）。

## 3.13 本地工具（`local_tools/`）

它们不是 MCP 服务器：它们是本地 provider，向 registry 注册
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
  （Kuwaiti algorithm）。表格式伊斯兰历可能与
  基于观测或 Umm al-Qura 的历法相差一天。
- `think.echo` 原样返回收到的字符串；它用于
  在推理链中把某个中间步骤外化。
- `text.diff` 返回两段文本之间的统一 diff，输入
  最多 20000 字符，输出最多 20000，`context` 为 0..10。它不会
  应用该 diff。
- `url.parse` 在不做 DNS 或网络访问的情况下拆解 scheme、host、端口、path、query 和 fragment；
  它把 URL 限制为 4096 字符，参数限制为 100 个。如果
  URL 含有凭据，会在输出中做遮蔽。
- `clock`、`calendar`、`think`、`text` 和 `url` 不访问文件系统
  或网络，并落入 `COMPUTE` allow 规则。
- 计算器使用 AST 白名单，而不是 `eval()`，对
  表达式、节点数和指数都有限制。
- `feed.read` 用 `requests` 下载（超时 15 秒，最大 5 MB），只接受
  http/https URL，并使用 `feedparser`；`NETWORK` 策略是 `ask`。
- SSRF：每个 host 都用 `getaddrinfo` 解析，每个地址都必须是
  全局地址；loopback、私有网络、link-local、multicast 和
  保留地址都会被拒绝。重定向不是自动的：每个
  `Location` 都会被重新校验，并在 3 次跳转后停止。带
  凭据的 URL 会被拒绝。
- 需要 `permissions.network: true`，系统上限才会
  授予 `NETWORK`；`COMPUTE` 始终在上限中，但策略可以拒绝它。
- 需要 `permissions.agents: true` 才能授予 `AGENT_SPAWN`；策略
  还必须允许 `agent.*`。
- `local_tools` 在 `pyproject.toml` 中声明，并随项目
  安装。

内置工具由 `local_tools/plugins.py` 通过与外部插件相同的
`ToolPlugin` 契约注册。外部插件通过 entry point `hagar.tools`
发现，并收到一个 `PluginContext`。
策略和 sandbox 仍留在 registry 中：插件不能授予
权限。故障的插件会被跳过并记录到审计，而不会
阻止其他插件。

## 3.14 插件

`core/plugins.py` 定义：

- 面向工具的 `ToolPlugin` + `PluginContext`；
- 面向 LLM provider 的 `LLMProvider`；
- 通过 `importlib.metadata.entry_points` 发现；
- 错误隔离和 `plugin.loaded`/`plugin.error` 审计。

内置 provider 位于 `llm/plugins.py`，并在外部 provider
之前注册。外部 provider 不能替换内置名称。
Python 插件是受信的，并在进程内运行；对于不受信的
扩展，边界仍是 MCP 或独立进程。完整契约
见 `PLUGINS.md`。

## 3.15 异步子智能体

`core/subagents.py` 实现：

- `agent.spawn/status/wait/result/cancel` 和同步的 `agent.run`；
- spawn 时强制要求 `reason`，并记录到审计；
- capability `AGENT_SPAWN` 是独立的：child 不会收到它，也不能
  创建其他 agent；
- child 的策略严格更严格；相同或更宽的策略
  会被拒绝并报 `SubagentPolicyError`；
- 5 分钟的墙钟超时，协作式，状态 `timed_out`；
- 父级、child 和 registry 的所有审计事件中都带 `agent_id`；
- 最多两个并发子智能体；
- 同一本地模型，但使用独立的 LLM 客户端；
- 每个 child 有私有的临时 workspace；
- 输入从父级 workspace 复制；
- child 的出站通道 `artifact.put`/`artifact.put_file` 和 `mailbox.send`；
- 临时 artifact store（每个 artifact 最大 50 MB，每轮 256 MB）
  和内存中的 mailbox（每条消息最大 64 KB）；
- 父级用 `artifact.read`、`artifact.list`、
  `mailbox.inbox/read/ack` 进行有界读取；
- `artifact.save_to` 把整个 artifact 复制到父级 sandbox 中可写的路径，
  而不经过上下文；
- capability `AGENT_DATA`；
- registry 被过滤为 `FILESYSTEM_READ`、`MEMORY_READ`、`COMPUTE` 和
  `AGENT_DATA`；
- 排除 `filesystem.chdir` 和 `agent.*`；
- 不写入记忆；
- child 的 ASK 由 `ParentBridgeConfirmation` 转发给用户，
  超时 180 秒，到期即 DENY；父级 LLM 不批准；
- usage 独立；
- 审计 `agent.spawned/started/finished/cancelled/failed`；
- 轮次结束时，对未导出的 artifact 记录 `artifact.discarded`，含
  原因 `unread` 或 `read_but_not_saved`，元数据不含内容；
- 轮次结束时清理 workspace 和 job。

`AuditLog.record` 用锁串行化并发写入。
目前还没有 artifact 导出、token/时间预算、嵌套或
专用 GUI。细节见 `SUBAGENTS.md`。

---

# 4. 安全模型

- agent 看不到真实文件系统：只有解析到 sandbox
  内部的路径。
- 操作只经过 `ToolRegistry`；没有宿主 shell。
- 权限在配置和策略中声明，并由 sandbox 与
  `PermissionEvaluator` 应用；嵌套的根
  可以限制权限。
- 错误也是数据：拒绝会作为工具结果返回给模型，
  而不是被隐藏。
- 每个动作都会在审计中留下痕迹，带会话和轮次。

---

# 5. 开发

- 套件：`./tools/run_tests.sh`（Linux/macOS）或
  `.\tools\run_tests.ps1`（Windows）。在 Windows 上：892 通过，2 跳过
  （没有 Developer Mode 时 symlink 不可用）。在 Debian Linux
  上（2026-11-12）：所有测试为绿，包括 symlink（894 通过，0
  跳过）。shim 的细节与理由见 README §3.1。
- live 测试：`./tools/run_tests.sh --live`（Linux/macOS）或
  `.\tools\run_tests.ps1 --live`（Windows）——多 9 个测试（Ollama；
  远程 provider，如果密钥存在）。
- 模型对比：`python tools/bench_models.py`（README §3.5）。
- 协议对比：`python tools/bench_native.py --provider ollama`
  （README §3.5）。
- 常规套件不访问网络：Ollama 和 MCP 都被模拟。

## 5.1 跨平台

- 内部路径使用 `pathlib.Path`；展示给 agent 的路径
  始终使用 `/` 和虚拟根 `/home/ai`。
- `filesystem.sandbox` 包含宿主系统的路径，可以是绝对的，或在用户
  选择时带 `~`：`Path.expanduser()` 仅在路径使用它时
  解析 home。不假定存在专用的 home。
- 每个 mount 都有一个显式且唯一（不区分大小写）的 alias；
  物理路径可以位于任何卷上。
- `tools/run_tests.sh` 是 POSIX runner；`tools/run_tests.ps1` 和
  `tools/pytest_shim` 仅用于 token 受限的 Windows
  sandbox。
- 仅存的显式 Windows 分支是 `stat` 中的创建时间：
  可用时用 `st_birthtime`，否则在 Windows 上用 `st_ctime`；在 Linux 上
  `created_at` 可以为 `None`。
- 外部 API（OAuth、MCP、LLM）使用 HTTP 和 `webbrowser`，而不是
  系统命令。
- GitHub Actions CI 覆盖 Linux、macOS 和 Windows 上的 Python
  3.11/3.12/3.13；symlink、OAuth token 权限和 loopback 回调
  仍需通过 live 测试验证，而不在离线套件中。

---

# 6. 已知限制与技术债

- `PermissionEvaluator` 已覆盖 v1：仍缺动态主体、
  GUI 确认，以及由配置分配的 MCP capability。
- 原生 calling 取决于模型：有些会忽略工具或
  返回多个调用；文本回退覆盖的是错误，而不是
  选择的质量。
- MCP 客户端支持 bearer/header 和 OAuth authorization code；不
  支持 device flow、DPoP、mTLS 或 client assertion。
- skill 的审查在 CLI 中手动完成；缺少 GUI。
- 记忆中的搜索按关键词进行，没有索引，也没有
  embedding。
- 注入的上下文使用全局最近轮次，以及最多 3 个按词法匹配的
  已确认 skill，没有语义选择。
- 记忆不会按时间长短删除聊天或 skill：`archive` 是
  唯一从上下文移除的方式。
- 审计有轮转和保留（`max_files`），但没有会话级
  压缩，也没有链的外部锚定。
- `feed.read` 校验地址和重定向，但 DNS
  rebinding 的情形仍存在：`requests` 在连接时会第二次解析名称；
  需要一个 pinned resolver。
- 计算器不是 CAS：它只处理有限的数值表达式，
  不处理符号表达式。
- `stat().created_at` 在缺少 `st_birthtime` 的 Linux 上为 `None`；不会
  凭空编造创建日期。
- 两个 alias 不能指向同一个物理路径：alias
  标识一个 mount，虚拟输出必须保持唯一。

## 6.1 用户责任：硬链接、mount 与 TOCTOU

**Hagar 不检查允许目录内的硬链接、mount/junction 和 TOCTOU
竞态。** 这不是 Hagar 的缺陷：sandbox 是
基于路径的，不会对整个操作用 handle/file descriptor。

硬链接是同一 inode 的第二个名字，它没有路径
目标，sandbox 无法知道外部是否还存在另一个名字。一个
mount 或 junction 可以暴露另一个文件系统，却仍留在
路径前缀之内。TOCTOU 竞态可以在 symlink 检查与
实际操作之间替换某个组成部分：Hagar 不使用 `openat2`、
对每个组成部分使用 `O_NOFOLLOW`，也不使用 Windows handle，因此不保证
检查与访问之间的原子性。

Hagar 的文件系统工具不会创建硬链接。如果某个硬链接或
mount 已存在于 sandbox 目录内，Hagar 会把它当作
普通文件或目录，并可以读取、修改它，或删除其内部
名称。

因此责任是划分的：

- **Hagar 保证**解析后的路径在检查时仍留在 alias 内，
  保证 symlink 不可见，保证 `R`/`W`/`X` 权限被应用，
  并保证真实路径不会出现在模型的输出中。
- **用户保证**在 `filesystem.sandbox` 中配置的目录
  不包含指向不应被访问内容的硬链接、mount 或 junction，
  并且如果希望完全隔离，则保证没有不受信的并发进程
  能在执行期间修改这些目录。

TOCTOU 竞态需要一个对 sandbox 目录有写访问权限的本地并发
行为者：它们不是正常使用中的偶发情形，
而是恶意或被攻陷环境的场景。
要实现强隔离，需要专用卷、独立用户、
mount namespace 或容器；这不是路径解析器的职责。

这些点作为**用户责任**关闭，而不是 Hagar 的技术
债。硬链接、mount/junction 和 TOCTOU 竞态在本版本中
既不会被检测，也不会被阻止。

---

# 7. 文档地图

- `MANUAL.md` — 用户手册：命令、配置、策略、默认值。
- `ARCHITECTURE.md` — 本文档：系统今天的样子。
- `ROADMAP.md` — 要做什么、已做出的决定和开放问题。
- `PLUGINS.md` — 工具与 LLM provider 插件的契约。
- `DOCUMENT_TOOL.md` — document tool 的规范、图 schema 和
  原生宿主协议。
- `SUBAGENTS.md` — 子智能体 MVP 与限制。
- `CHANGELOG.md` — 版本历史。
- `README.md` — 启动、配置、测试。
