# HAGAR — 用户手册

版本：**0.5.2**

本手册描述 Hagar 可观察到的行为：命令、
选项、配置、策略以及错误情形。关于内部设计
请参见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

---

# 1. 快速开始

要求：Python 3.11 或更高版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

cp hagar.example.yaml hagar.yaml
mkdir -p vault logs

hagar --config hagar.yaml
```

在 Windows 上：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item hagar.example.yaml hagar.yaml
New-Item -ItemType Directory -Force vault, logs
hagar --config hagar.yaml
```

`hagar.yaml`、`testvault/` 和 `logs/` 属于本地内容，不应纳入版本控制。

## 1.1 启动顺序

1. Hagar 读取配置。
2. 加载 `policy.yaml`；如果它无效，则对所有策略应用 `DENY`。
3. 构建 LLM 客户端。
4. 如果已配置，则初始化 Vault 和记忆。
5. 构建文件系统 sandbox。
6. 注册本地工具。
7. 尝试加载 MCP 服务器；某个服务器失败不会阻止其他服务器。
8. 显示项目选择。
9. 进入聊天循环。

---

# 2. 聊天命令

命令以 `/` 开头。未知命令**不会发送给
模型**：Hagar 会回复 `Comando sconosciuto` 并建议使用 `/help`。

## 2.1 全局命令

| 命令 | 行为 |
|---|---|
| `/help` 或 `/?` | 列出可用命令 |
| `/tools [类别]` | 列出工具与 capability；过滤器可选 |
| `/status` | 显示模型、项目、记忆、审计和 sandbox |
| `/usage` | 显示会话中消耗的 token |
| `/models ...` | 供 broker 使用的卡片、基准测试和硬件信息 |
| `/models hardware` | 检测本机的 CPU、RAM 和 GPU |
| `/mcp` | 列出 MCP 服务器、端点和导入的工具 |
| `/audit [n]` | 显示最近 `n` 个事件；默认 10，最多 50 |
| `exit` | 退出 |
| `quit` | 退出 |
| `Ctrl-D` | 退出 |
| `Ctrl-C` | 中断；在 OAuth 期间以代码 130 退出 |

`/status` 和 `/audit` 是面向人的命令：它们不经过模型，也不
消耗 tool call。

## 2.2 项目

| 命令 | 行为 |
|---|---|
| `/project` 或 `/project list` 或 `/project ls` | 列出活动项目 |
| `/project new <名称>` | 创建项目并选中它 |
| `/project select <id>` 或 `/project use <id>` | 选中一个活动项目 |
| `/project free` 或 `/project none` | 切换到自由活动 |
| `/project status` 或 `/project current` | 显示当前项目 |
| `/project archive <id>` | 归档一个项目 |
| `/project unarchive <id>` | 重新激活一个已归档项目 |
| `/project help` | 帮助 |

`select` 和 `archive` 使用项目的 **id**，而不是标题。

在自由活动中不会读取或写入项目记忆；聊天、
summary 和 skill 仍然可用。

## 2.3 记忆

| 命令 | 行为 |
|---|---|
| `/memory` 或 `/memory help` 或 `/memory ?` | 帮助 |
| `/memory list [candidate\|confirmed\|archived]` | 列出 skill 和计数 |
| `/memory show <slug>` | 显示一个 skill |
| `/memory search <文本>` | 在 SQLite 记忆中搜索 |
| `/memory sessions` | 列出已记录的聊天 |
| `/memory chat <session>` | 显示某个聊天的轮次 |
| `/memory reindex` | 优化/重建 SQLite 索引 |
| `/memory stats` | 数据库状态与计数 |
| `/memory backup <path>` | 数据库的一致性副本 |
| `/memory export <path> [--force]` | 将聊天、skill、summary 和项目导出为 Markdown |
| `/memory import <path> [--force]` | 将 Markdown 结构导入数据库 |
| `/memory review` | 对 candidate 进行交互式审查 |
| `/memory confirm <slug>` | 确认一个 skill |
| `/memory archive <slug>` | 归档一个 skill |
| `/memory archive search <文本>` | 在已归档的 transcript 中搜索 |
| `/memory archive read <session> [offset] [limit]` | 读取一份已归档的 transcript |

`search` 和 `read` 是保留字：一个名称恰好为
`search` 或 `read` 的 skill slug 无法用此命令归档。

不存在删除命令：只能归档。

默认后端是 SQLite（`memory.backend: sqlite`）。数据库
位于应用的本地数据目录中，而不在 Vault 中：

```text
%LOCALAPPDATA%/Hagar/memory.db
```

或者 `HAGAR_MEMORY_DB`。`markdown` 后端仅为兼容性而
保留。Vault 不再由 SQLite 后端更新。

## 2.4 什么不是命令

工具（`filesystem.*`、`memory.*`、`mcp.*`、`clock.now` 等）由模型
通过 registry 调用。它们不以 `/tool` 的形式输入。
唯一的例外是信息类命令 `/tools`、`/status`、`/models`、`/mcp`、
`/audit`，它们是控制台命令而非工具。

---

# 3. 命令行

```text
hagar [opzioni]
hagar web [opzioni]
```

| 选项 | 效果 |
|---|---|
| `--config PATH` | 使用显式的配置文件 |
| `--model NAME` | 覆盖 `model.name` |
| `--project NAME` | 启动时选中一个活动项目 |
| `--free` | 以自由活动启动 |
| `--no-memory` | 为本会话停用记忆和项目 |
| `--no-native-tools` | 强制使用文本 JSON 协议 |
| `--host HOST` | web GUI 的主机（默认 `127.0.0.1`） |
| `--port PORT` | web GUI 的端口（默认 `8765`） |
| `--version` | 打印版本 |

`--project` 与 `--free` 互斥。

## 3.0 web GUI

```bash
hagar web
hagar --config hagar.yaml web --port 8765
```

在 `http://127.0.0.1:8765/` 上打开本地 GUI。

- 该服务器面向单个本地用户：默认为 `127.0.0.1`。
- 浏览器会在页面中收到一个随机 token；API 要求在
  `X-Hagar-Token` 头中提供它。
- 聊天显示轮次、tool call、结果和 ASK 确认。
- 顶部有 **Chat**、**Chat history**、**Tool output**、
  **Audit** 和 **Thinking** 标签页。
- **Chat history** 列出过去的聊天，每条聊天一行；点击
  即恢复该聊天：transcript 会从数据库重新加载，新的
  轮次会追加到同一会话。
- **+ Nuova chat** 按钮打开一个新会话并清空
  上下文；先前的聊天仍保留在历史中。
- **Memories** 是对已索引笔记（skill、项目、决策）的只读
  浏览器；它支持搜索和打开文本。
- **Tool output** 显示本会话的 tool call 与结果。
- **Audit** 显示日志事件；如果审计被停用，该标签页会被
  禁用并显示 `audit off`。
- **Thinking** 显示 provider 暴露的推理内容（若有）；否则
  显示智能体事件的时间线。
- **Memories** 以只读方式显示数据库中的记忆和 skill，支持搜索。
- **Stop** 按钮以协作方式中断当前轮次。
- **Immagine** 按钮可附加 PNG/JPEG/WebP（最多 4 张，每张 10 MB），
  供 vision 模型使用。WebP 在 GUI 中会被转换为 PNG，因为 LM
  Studio 不直接接受它。图片不会被保存
  到记忆或审计中：到达模型的是 data URL，而不是
  宿主机路径。
- 底部侧边栏显示会话的累计 token：input、
  output 和总计。
- 模型可以用 `vision.open` 从 sandbox 加载图片；
  该图片会被附加到当前轮次，而不会以 base64 形式
  返回到上下文中。
- ASK 确认是模态的：轮次保持等待，而服务器
  继续响应。超时等同于拒绝。子智能体的请求会
  显示 `agent_id` 和 `parent_id`；LLM 父级不能
  批准它们。子智能体的超时为 180 秒。
- 在 CLI 中只有一个线程拥有输入。当有确认处于活动状态时，
  终端标题会请求注意，并接受 `F5` =
  allow、`F8` = deny，以及 `y/N`。如果终端不支持功能
  键，则仍可使用 `y/N` 和 GUI。
- CLI 中的 Ctrl-C 会在退出前恢复终端的正常模式。
- GUI 尚不支持多用户，也不提供对记忆的直接修改。
- Ctrl-C 会关闭服务器并尝试结束会话。

不要在不可信的网络上使用 `--host 0.0.0.0`：GUI 会把 harness
的工具暴露给任何能访问该端口的人。

## 3.1 配置文件的查找

顺序：

1. `--config PATH`
2. 环境变量 `HAGAR_CONFIG`
3. 当前目录下的 `./hagar.yaml`

`hagar.yaml` 中的相对路径——audit、policy、Vault——是
相对于配置文件所在目录解析的，而不是相对于
你启动 Hagar 的目录。

## 3.2 退出码

| 代码 | 含义 |
|---|---|
| `0` | 正常退出或 `--version` |
| `1` | 配置错误或项目无效 |
| `130` | 被 Ctrl-C 中断 |

MCP 错误不会改变退出码：它会被记录，而
harness 继续运行。

---

# 4. `hagar.yaml`

最小示例：

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

| 字段 | 默认值 | 说明 |
|---|---|---|
| `provider` | 必填 | `ollama`、`lmstudio`、`deepseek`、`openai`（`chatgpt`）、`claude`、`gemini` |
| `name` | 必填 | 模型在 provider 处的名称 |
| `host` | provider 默认值 | API 的 base URL |
| `native_tools` | `true` | 若为 `false`，则使用文本 JSON 协议 |
| `max_tokens` | `1024` | 仅由 Claude 使用 |
| `timeout` | `120` | 每次调用的 HTTP 超时（秒） |
| `api_key_env` | 标准名称 | 密钥所在的环境变量 |

Provider 与密钥：

| Provider | 标准密钥 | 默认值 |
|---|---|---|
| `ollama` | 无 | `http://localhost:11434` |
| `lmstudio` | 无，可选 `LMSTUDIO_API_KEY` | `http://localhost:1234/v1` |
| `deepseek` | `DEEPSEEK_API_KEY` | API DeepSeek |
| `openai` / `chatgpt` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `claude` | `ANTHROPIC_API_KEY` | API Anthropic |
| `gemini` | `GEMINI_API_KEY` | API Gemini |

密钥绝不能写入 YAML。如果缺少某个密钥，客户端
不会被构建，启动会以明确的错误失败。LM Studio
不需要密钥，除非本地服务器被配置为
要求密钥。`chatgpt` 是 `openai` 的别名：ChatGPT 订阅并不
授予 API 访问权限，需要 OpenAI 密钥和 API 额度。

在 LM Studio 中，原生 tool calling 取决于模型及其
模板。如果模型接受请求但以文本作答，而不是
发出 `tool_calls`，Hagar 就无法执行该工具：应使用
`model.native_tools: false` 或使用支持工具的模型。

在启用原生 calling 的情况下，Hagar 使用 provider 的结构化
工具。如果 provider 拒绝该 schema（HTTP 400/404/422），则在第一步
就会为该会话切换到文本 JSON 协议。该回退
覆盖的是技术性错误，并不保证模型能正确选择工具。

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

| 字段 | 默认值 | 效果 |
|---|---|---|
| `enabled` | `true` | 启用/停用日志 |
| `path` | `logs/audit.jsonl` | JSON Lines 文件 |
| `max_field_chars` | `2000` | 截断字段 |
| `max_bytes` | `5000000` | 轮转阈值 |
| `max_files` | `100` | 保留的轮转文件数 |
| `include_outputs` | `true` | 若为 `false`，则对工具输出做遮蔽处理 |

审计包含敏感数据：文件输出、响应和文本。它必须
像 workspace 一样受到保护。`/audit` 只显示当前文件
中的事件，不显示轮转后的事件。

主要事件：`harness.start`、`turn.start`、`llm.tool_choice`、
`tool.call`、`tool.result`、`turn.answer`、`permission.decision`、
`permission.confirmation`、`memory.*`、`mcp.loaded`、`mcp.failed`、
`harness.stop`。

## 4.3 `policy`

```yaml
policy:
  path: policy.yaml
  subject: assistant
```

`path` 相对于配置文件。如果文件不可读或
无效：

- 所有策略变为 `DENY`；
- 记录 `policy.failed`；
- Hagar 保持启动，但不执行任何工具；
- 控制台显示 `Policy: DENY ALL`。

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

使用 SQLite 后端时，它仅由遗留 Markdown 后端和遗留
项目使用。使用 `memory.backend: sqlite` 时，它甚至可以不存在。

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

| 字段 | 默认值 | 效果 |
|---|---|---|
| `enabled` | `true` | 启用记忆 |
| `backend` | `sqlite` | `sqlite` 或遗留 `markdown` |
| `database` | 本地数据 | SQLite 数据库的显式路径 |
| `vault_subdir` | `Hagar` | 遗留 Vault 的子目录 |
| `context_turns` | `10` | 注入的最近轮次；`0` 表示停用 |
| `context_skills` | `3` | 注入的已确认 skill |
| `context_project_memories` | `10` | 活动决策的标题 |
| `max_context_chars` | `6000` | 记忆块的预算 |
| `project_max_active` | `200` | 项目维护阈值 |
| `summary_max_chars` | `4000` | summary 的最大长度 |
| `max_skill_chars` | `4000` | 单个 skill 的最大长度 |

`vault_subdir` 必须保持在 Vault 内部：绝对路径、`..`、
`I:/...` 以及其他 Windows 驱动器即使在 Linux 上也会被拒绝。

使用 `backend: sqlite` 时，默认数据库为：

```text
%LOCALAPPDATA%/Hagar/memory.db
```

或 `HAGAR_MEMORY_DB`。SQLite 使用 WAL、事务和 `VACUUM INTO` 进行
备份；Vault 不会被更新。

预算以**字符**为单位，而不是 token。当该块被
裁剪时，审计会记录 `memory.context_trimmed`。

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

每个条目：

| 字段 | 必填 | 说明 |
|---|---|---|
| `alias` | 是 | 单个路径段，唯一且不区分大小写 |
| `path` | 是 | 宿主机上已存在的目录 |
| `permissions` | 否 | 默认 `R`；字母 `R`、`W`、`X` |

权限：

| 字母 | 涵盖 |
|---|---|
| `R` | 读取、列出、搜索、`stat` |
| `W` | 写入、创建、重命名、复制、删除 |
| `X` | 在该目录中 `chdir` |

智能体看到的是 `/home/ai/<alias>/...`。`/home/ai` 会列出别名，但
它不是物理目录，也无法用 `chdir` 进入。

约束：

- 重复的 alias 和 path 会使配置中止；
- 缺失的 path 会使配置中止；
- 物理路径可以包含空格；alias 不可以；
- Hagar 不会创建 sandbox 目录，也不假定有专用的 home。

写入限制：

| 字段 | 效果 |
|---|---|
| `max_write_bytes` | 单次操作的最大值 |
| `min_free_bytes` | 剩余的最小可用空间 |
| `session_write_bytes` | 每会话的累计最大值 |
| `ask_over_bytes` | 超过此阈值时请求确认 |

`0` 表示停用单个限制。这些限制是不变式：超限
属于工具错误，而不是警告。

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
  agents: false
```

它们是**系统上限**。默认：`read=true`，其他为 `false`。

| 字段 | 授予 |
|---|---|
| `read` | filesystem read、memory read |
| `write` | filesystem write/create/delete、memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |
| `agents` | `AGENT_SPAWN` 和 `AGENT_DATA`，用于 `agent.*`/`artifact.*`/`mailbox.*` |

`COMPUTE` 和 `MCP_CALL` 始终在上限之内，但策略可以拒绝它们。
如果上限不授予某项 capability，策略也不能授予它。
仅 `agents: true` 不够：策略必须为 `agent.*` 提供一条
`AGENT_SPAWN` 规则。

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

这是文档检索的预期值。在本版本中它不会修改记忆
上下文。

## 4.9 `mcp_servers`

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer
      token_env: MCP_EXAMPLE_TOKEN
```

字段：

| 字段 | 说明 |
|---|---|
| `endpoint` | MCP 服务器的 HTTP/JSON-RPC URL |
| `namespace` | 导入工具的前缀：`mcp.<namespace>.*` |
| `auth` | 可选：`bearer`、`header` 或 `oauth` |

Bearer/header：

```yaml
auth:
  type: header
  header: Authorization
  token_env: ATLASSIAN_BASIC
```

从环境变量读取的值会**原样**发送：对于 Basic，
它必须已经是 `Basic <base64>`，而不仅仅是 token。

OAuth：

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

该流程是 authorization code + PKCE，本地回调为
`http://localhost:<port>/oauth/callback`。如果缺少 `client_id`，会尝试
dynamic registration。使用 `offline_access` 时会添加
`prompt=consent`。token 存放在权限受限的本地文件中，并会自动
续期。

如果某个 MCP 服务器失败：

- 记录 `mcp.failed`；
- 跳过该服务器；
- 其他服务器和 harness 的其余部分继续运行；
- `/mcp` 对该命名空间显示零个工具。

---

# 5. `policy.yaml`

示例：

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

## 5.1 效果

| 效果 | 含义 |
|---|---|
| `allow` | 该工具可以执行 |
| `ask` | 需要人工确认 |
| `deny` | 该工具不执行 |

严重程度顺序：`DENY > ASK > ALLOW`。当要求多项 capability 时，
适用 AND：最严重的生效。

没有确认通道的 `ASK` 等同于 `DENY`。控制台确认
会显示 `lo faccio? (y/N)`，默认值为 `N`。

## 5.2 Capability

| 名称 | 用途 |
|---|---|
| `FILESYSTEM_READ` | 读取、列出、搜索、stat |
| `FILESYSTEM_WRITE` | 修改 |
| `FILESYSTEM_CREATE` | 创建、复制、在目标处重命名 |
| `FILESYSTEM_DELETE` | 删除 |
| `FILESYSTEM_EXEC` | 进入/在 sandbox 中执行 |
| `MEMORY_READ` | 读取记忆 |
| `MEMORY_WRITE` | 写入记忆 |
| `NETWORK` | 网络访问 |
| `MCP_CALL` | 调用 MCP 工具 |
| `COMPUTE` | 无网络/文件系统的本地计算 |

## 5.3 规则与特异性

一条规则可以用以下方式过滤：

- `tools`：对名称的 glob（`filesystem.*`、`mcp.atlassian.*`）；
- `paths`：对模型所写路径的前缀匹配；
- `namespaces`：对命名空间的前缀匹配。

最具体的规则胜出：先比较过滤器的数量，再比较
前缀长度。若相同，则更严格的效果胜出。
没有规则时适用该主体的 `default`；安全的默认值是 `deny`。

`paths` 作用域比较的是**模型所写的**路径，而不是在 `chdir` 之后
解析出的路径：绝对路径或目录切换可能对不上，并
产生 `DENY`（fail closed）。

## 5.4 错误

如果 `policy.yaml` 无效、缺少某项 capability，或主体
不存在：

- Hagar 对所有策略应用 `DENY`；
- 记录 `policy.failed`；
- 显示一条警告；
- 不执行任何工具。

---

# 6. 默认行为

| 情形 | 行为 |
|---|---|
| 没有 `hagar.yaml` | 配置错误，退出码 1 |
| YAML 无效 | 配置错误，退出码 1 |
| 策略无效 | 全部 DENY，harness 仍启动 |
| 记忆被停用 | 检查 `memory.database` 和目录权限 |
| `Projects: disabled` | 检查 SQLite 数据库或遗留后端中的 `vault.path` |
| 没有活动项目 | 自由活动 |
| 非交互式启动 | 自由活动，除非指定 `--project`/`--free` |
| `--project` 不存在 | 错误，退出码 1 |
| MCP 服务器无法访问 | `mcp.failed`，跳过该服务器 |
| 模型/Ollama 无法访问 | 轮次错误，harness 保持运行 |
| 缺少 API 密钥 | 客户端未构建，启动时出错 |
| 工具被拒绝 | 向模型返回错误结果，不执行 |
| 工具处于 `ASK` 且无确认 | 拒绝 |
| 超出写入限制 | 工具错误，不写入 |
| 用 `read_file` 读取超过 4096 字节的文件 | 错误，应使用 `read_chunk` |
| 页面超过限制 | `has_more`/`next_offset` |
| Symlink | 不可见；操作如同路径不存在 |
| 硬链接/mount/junction | 不检测；由用户负责 |
| TOCTOU 竞态 | 不检查；由用户负责 |
| 轮次中记忆缺失 | `memory.failed`，轮次继续 |
| 有轮次时结束会话 | summary、归档、项目审查 |
| 审查被拒绝 | 决策成为带 `auto_saved: true` 的 candidate |
| 项目超出 `project_max_active` | 请求归档 |
| OAuth 期间按 Ctrl-C | 关闭回调，退出码 130 |
| 未知的 `/` 命令 | 提示消息，不发送给模型 |

## 6.1 结束会话

退出时，如果记忆已启用且存在轮次：

1. transcript 被移动到 `archive/chat/`；
2. 生成一个 summary（由 LLM 生成，并有机械式回退）；
3. summary 会连同链接和 hash 一起保存；
4. 如果有项目，LLM 会提出候选决策；
5. 用户可以审查它们；如果拒绝，它们保持为 candidate。

如果没有轮次，则不会创建任何 summary。

## 6.2 Hagar 不做什么

- 不执行 shell 命令；
- 不向模型提供物理路径；
- 不保证操作系统级隔离：sandbox 是基于路径的；
- 不检查硬链接、mount、junction 或 TOCTOU；
- 不按时间长短删除聊天或 skill；
- 不加密 Vault；
- 不会自动把某个 skill 或决策提升为事实。

---

# 7. 操作安全

- 模型是不可信的：策略和确认才是控制手段。
- SQLite 数据库包含对话和决策：必须受到保护。
- 审计可能包含文件输出：必须受到保护。
- API 密钥只存在于环境中。
- MCP/OAuth token 存储在权限受限的本地缓存中。
- 不要在没有必要时把 Ollama 或 LM Studio 暴露在网络上。
- 在允许目录内的硬链接或 mount 可能暴露
  外部内容：Hagar 不会检测到它们。

---

# 8. 故障排查

| 症状 | 检查项 |
|---|---|
| `Policy: DENY ALL` | 验证 `policy.yaml` 和 `policy.path` |
| `Memory: disabled` | 检查 `memory.database` 和权限 |
| `Projects: disabled` | 检查 SQLite 数据库 |
| `Failed to load MCP server` | endpoint、token、`/mcp` |
| `MCP auth token missing` | `token_env` 指示的变量 |
| `MCP HTTP 401` | 凭据/头 Basic 或 OAuth |
| `MCP HTTP 400` | 服务器的协议、会话或参数 |
| `read_file` 文件过大 | 使用 `read_chunk` |
| `PermissionError` | 策略、`R/W/X` 权限、sandbox 之外的路径 |
| 工具未列出 | MCP 服务器失败或工具未注册 |
| 命令无法识别 | `/help` |

对于配置错误，Hagar 以代码 1 退出，并把
详细信息打印到 stderr。对于轮次错误，模型会收到该工具的
结果，审计则保留该事件。
