# HAGAR — 用户手册

版本：**0.3.0**

本手册描述 Hagar 的可观察行为：命令、
选项、配置、策略以及错误情形。关于内部设计，
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

`hagar.yaml`、`testvault/` 和 `logs/` 都是本地文件，不应纳入版本控制。

## 1.1 启动顺序

1. Hagar 读取配置。
2. 加载 `policy.yaml`；如果它无效，则对所有操作应用 `DENY`。
3. 构建 LLM 客户端。
4. 如果已配置，初始化 Vault 和记忆。
5. 构建文件系统 sandbox。
6. 注册本地工具。
7. 尝试加载 MCP 服务器；某个服务器失败不会阻止其他服务器。
8. 显示项目选择。
9. 进入聊天循环。

---

# 2. 聊天命令

命令以 `/` 开头。未知命令**不会发送给
模型**：Hagar 会回复 `Comando sconosciuto`（未知命令）并建议使用 `/help`。

## 2.1 全局命令

| 命令 | 行为 |
|---|---|
| `/help` 或 `/?` | 列出可用命令 |
| `/tools [类别]` | 列出工具和 capability；过滤器是可选的 |
| `/status` | 显示模型、项目、记忆、审计和 sandbox |
| `/mcp` | 列出 MCP 服务器、端点和已导入的工具 |
| `/audit [n]` | 显示最近 `n` 个事件；默认 10，最多 50 |
| `exit` | 退出 |
| `quit` | 退出 |
| `Ctrl-D` | 退出 |
| `Ctrl-C` | 中断；在 OAuth 过程中以代码 130 退出 |

`/status` 和 `/audit` 是面向人的命令：它们不经过模型，也不
消耗工具调用。

## 2.2 项目

| 命令 | 行为 |
|---|---|
| `/project` 或 `/project list` 或 `/project ls` | 列出活动项目 |
| `/project new <名称>` | 创建一个项目并选中它 |
| `/project select <id>` 或 `/project use <id>` | 选择一个活动项目 |
| `/project free` 或 `/project none` | 切换到自由活动 |
| `/project status` 或 `/project current` | 显示当前项目 |
| `/project archive <id>` | 归档一个项目 |
| `/project unarchive <id>` | 重新激活一个已归档项目 |
| `/project help` | 帮助 |

`select` 和 `archive` 使用项目的 **id**，而不是标题。

在自由活动中，不会读取也不会写入项目记忆；聊天、
摘要和 skill 仍然可用。

## 2.3 记忆

| 命令 | 行为 |
|---|---|
| `/memory` 或 `/memory help` 或 `/memory ?` | 帮助 |
| `/memory list [candidate\|confirmed\|archived]` | 列出 skill 及数量 |
| `/memory show <slug>` | 显示一个 skill |
| `/memory review` | 对 candidate 进行交互式复核 |
| `/memory confirm <slug>` | 确认一个 skill |
| `/memory archive <slug>` | 归档一个 skill |
| `/memory archive search <文本>` | 在已归档的 transcript 中搜索 |
| `/memory archive read <session> [offset] [limit]` | 读取一个已归档的 transcript |

`search` 和 `read` 是保留字：名为
`search` 或 `read` 的 skill slug 无法通过该命令归档。

没有删除命令：只能归档。

## 2.4 什么不是命令

工具（`filesystem.*`、`memory.*`、`mcp.*`、`clock.now` 等）由模型
通过 registry 调用。它们不以 `/tool` 的形式输入。
唯一的例外是信息类命令 `/tools`、`/status`、`/mcp`、
`/audit`，它们属于控制台命令，而不是工具。

---

# 3. 命令行

```text
hagar [opzioni]
```

| 选项 | 效果 |
|---|---|
| `--config PATH` | 使用显式的配置文件 |
| `--model NAME` | 覆盖 `model.name` |
| `--project NAME` | 在启动时选择一个活动项目 |
| `--free` | 以自由活动方式启动 |
| `--no-memory` | 为该会话禁用记忆和项目 |
| `--no-native-tools` | 强制使用文本 JSON 协议 |
| `--version` | 打印版本 |

`--project` 与 `--free` 互斥。

## 3.1 配置的查找

顺序：

1. `--config PATH`
2. 变量 `HAGAR_CONFIG`
3. 当前目录下的 `./hagar.yaml`

`hagar.yaml` 内的相对路径——审计、策略、Vault——都是
相对于配置文件所在目录解析，而不是相对于
你启动 Hagar 时所在的目录。

## 3.2 退出代码

| 代码 | 含义 |
|---|---|
| `0` | 正常退出或 `--version` |
| `1` | 配置错误或项目无效 |
| `130` | 通过 Ctrl-C 中断 |

MCP 错误不会改变退出代码：它会被记录，harness
继续运行。

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
| `provider` | 必填 | `ollama`、`deepseek`、`claude`、`gemini` |
| `name` | 必填 | 模型在 provider 处的名称 |
| `host` | provider 默认值 | API 的 base URL |
| `native_tools` | `true` | 若为 `false`，使用文本 JSON 协议 |
| `max_tokens` | `1024` | 仅由 Claude 使用 |
| `api_key_env` | 标准名称 | 密钥所在的环境变量 |

Provider 与密钥：

| Provider | 标准密钥 |
|---|---|
| `ollama` | 无 |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `claude` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |

密钥绝不应写入 YAML。如果缺少密钥，客户端
不会被构建，启动会以明确的错误失败。

启用原生 calling 时，Hagar 使用 provider 提供的结构化
工具。如果 provider 拒绝该 schema（HTTP 400/404/422），则在
第一步就切换到该会话的文本 JSON 协议。回退机制
只覆盖技术错误，并不保证模型能正确选择工具。

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
| `enabled` | `true` | 启用/禁用日志 |
| `path` | `logs/audit.jsonl` | JSON Lines 文件 |
| `max_field_chars` | `2000` | 截断字段 |
| `max_bytes` | `5000000` | 轮转阈值 |
| `max_files` | `100` | 保留的轮转文件数量 |
| `include_outputs` | `true` | 若为 `false`，对工具输出脱敏 |

审计包含敏感数据：文件输出、回答和文本。必须
像保护工作区一样保护它。`/audit` 只显示当前文件的
事件，不显示轮转文件中的事件。

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
- Hagar 保持启动，但不会执行任何工具；
- 控制台显示 `Policy: DENY ALL`。

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

这是 Markdown 记忆的根目录。它必须存在且可写。
如果缺失或不可写，记忆会被禁用并给出警告；
harness 的其余部分继续运行。

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

| 字段 | 默认值 | 效果 |
|---|---|---|
| `enabled` | `true` | 启用记忆 |
| `vault_subdir` | `Hagar` | Vault 内的子目录 |
| `context_turns` | `10` | 注入的最近轮次；`0` 表示禁用 |
| `context_skills` | `3` | 注入的已确认 skill 数量 |
| `context_project_memories` | `10` | 活动决策的标题数量 |
| `max_context_chars` | `6000` | 记忆块的字符预算 |
| `project_max_active` | `200` | 项目维护阈值 |
| `summary_max_chars` | `4000` | 摘要的最大长度 |
| `max_skill_chars` | `4000` | 单个 skill 的最大长度 |

`vault_subdir` 必须留在 Vault 内部：绝对路径、`..`、
`I:/...` 以及其他 Windows 驱动器即使在 Linux 上也会被拒绝。

预算以**字符**计，而不是 token。当记忆块被
截断时，审计会记录 `memory.context_trimmed`。

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
| `alias` | 是 | 单个路径段，大小写不敏感地唯一 |
| `path` | 是 | 宿主系统中已存在的目录 |
| `permissions` | 否 | 默认 `R`；字母 `R`、`W`、`X` |

权限：

| 字母 | 涵盖 |
|---|---|
| `R` | 读取、列出、搜索、`stat` |
| `W` | 写入、创建、重命名、复制、删除 |
| `X` | 在该目录中 `chdir` |

智能体看到的是 `/home/ai/<alias>/...`。`/home/ai` 会列出别名，但它
不是物理目录，无法用 `chdir` 进入。

约束：

- 重复的别名和路径会中止配置；
- 缺少路径会中止配置；
- 物理路径可以包含空格；别名不可以；
- Hagar 不会创建 sandbox 目录，也不假定存在专用的 home 目录。

写入限制：

| 字段 | 效果 |
|---|---|
| `max_write_bytes` | 单次操作的最大值 |
| `min_free_bytes` | 必须保留的最小剩余空间 |
| `session_write_bytes` | 每个会话的累计上限 |
| `ask_over_bytes` | 超过该阈值时请求确认 |

`0` 表示禁用该项限制。这些限制是不变式：超限属于
工具错误，而不是警告。

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
```

它们是**系统上限**。默认：`read=true`，其余为 `false`。

| 字段 | 授予 |
|---|---|
| `read` | 文件系统读取、记忆读取 |
| `write` | 文件系统写入/创建/删除、记忆写入 |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |

`COMPUTE` 和 `MCP_CALL` 始终在上限之内，但策略可以拒绝它们。
如果上限不授予某项 capability，策略也无法授予。

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

文档检索的预期取值。在本版本中不会改变记忆
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

从环境读取的值会**原样**发送：对于 Basic
它必须已经是 `Basic <base64>`，而不只是 token。

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

流程为 authorization code + PKCE，本地回调
`http://localhost:<port>/oauth/callback`。如果缺少 `client_id`，会尝试
dynamic registration。使用 `offline_access` 时会添加
`prompt=consent`。token 保存在一个受限制的本地文件中，并会
自动续期。

如果某个 MCP 服务器失败：

- 记录 `mcp.failed`；
- 该服务器被跳过；
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
| `allow` | 工具可以执行 |
| `ask` | 需要人工确认 |
| `deny` | 工具不执行 |

严重程度顺序：`DENY > ASK > ALLOW`。当要求多项 capability 时，
适用 AND 逻辑：最差的效果胜出。

没有确认通道的 `ASK` 等同于 `DENY`。控制台确认
显示 `lo faccio? (y/N)`，默认值为 `N`。

## 5.2 Capability

| 名称 | 用途 |
|---|---|
| `FILESYSTEM_READ` | 读取、列出、搜索、stat |
| `FILESYSTEM_WRITE` | 修改 |
| `FILESYSTEM_CREATE` | 创建、复制、重命名到目标位置 |
| `FILESYSTEM_DELETE` | 删除 |
| `FILESYSTEM_EXEC` | 进入/在 sandbox 中执行 |
| `MEMORY_READ` | 读取记忆 |
| `MEMORY_WRITE` | 写入记忆 |
| `NETWORK` | 网络访问 |
| `MCP_CALL` | 调用 MCP 工具 |
| `COMPUTE` | 无需网络/文件系统的本地计算 |

## 5.3 规则与特异性

规则可以通过以下方式过滤：

- `tools`：对名称做 glob（`filesystem.*`、`mcp.atlassian.*`）；
- `paths`：对模型写入的路径做前缀匹配；
- `namespaces`：对命名空间做前缀匹配。

最具体的规则胜出：先看过滤器数量，再看前缀
长度。若相同，则采用更严格的效果。
没有规则时适用主体的 `default`；安全的默认值是 `deny`。

`paths` 作用域比较的是**模型写入的**路径，而不是
在 `chdir` 之后解析出的路径：绝对路径或切换目录可能
无法匹配前缀，从而产生 `DENY`（fail closed）。

## 5.4 错误

如果 `policy.yaml` 无效、缺少某项 capability 或主体
不存在：

- Hagar 对所有策略应用 `DENY`；
- 记录 `policy.failed`；
- 显示警告；
- 不执行任何工具。

---

# 6. 默认行为

| 情形 | 行为 |
|---|---|
| 没有 `hagar.yaml` | 配置错误，退出 1 |
| YAML 无效 | 配置错误，退出 1 |
| 策略无效 | 全部 DENY，harness 仍启动 |
| Vault 缺失/不可写 | 记忆禁用，harness 仍启动 |
| `projects` 不可写 | 项目禁用，记忆仍启用 |
| 没有活动项目 | 自由活动 |
| 非交互式启动 | 自由活动，除非使用 `--project`/`--free` |
| `--project` 不存在 | 错误，退出 1 |
| MCP 服务器不可达 | `mcp.failed`，服务器被跳过 |
| 模型/Ollama 不可达 | 轮次错误，harness 保持运行 |
| 缺少 API 密钥 | 客户端未构建，启动时出错 |
| 工具被拒绝 | 向模型返回错误结果，不执行 |
| 工具处于 `ASK` 且无确认 | 拒绝 |
| 超过写入限制 | 工具错误，不写入 |
| `read_file` 读取超过 4096 字节的文件 | 错误，请使用 `read_chunk` |
| 分页超出限制 | `has_more`/`next_offset` |
| Symlink | 不可见；操作视为路径不存在 |
| 硬链接/挂载/junction | 不检测；由用户负责 |
| TOCTOU 竞态 | 不检查；由用户负责 |
| 轮次进行中记忆缺失 | `memory.failed`，轮次继续 |
| 会话结束时存在轮次 | 摘要、归档、项目复核 |
| 复核被拒绝 | 决策成为 candidate 并带 `auto_saved: true` |
| 项目超过 `project_max_active` | 请求归档 |
| OAuth 期间 Ctrl-C | 关闭回调，退出 130 |
| 未知 `/` 命令 | 显示消息，不发送给模型 |

## 6.1 会话结束

退出时，如果记忆已启用且存在轮次：

1. transcript 被移动到 `archive/chat/`；
2. 生成摘要（LLM，若不可用则机械回退）；
3. 摘要与链接和哈希一起保存；
4. 如果存在项目，LLM 提出候选决策；
5. 用户可以复核它们；如果拒绝，它们仍为 candidate。

如果没有轮次，则不会创建任何摘要。

## 6.2 Hagar 不做什么

- 不执行 shell 命令；
- 不向模型提供物理路径；
- 不保证操作系统级隔离：sandbox 是基于路径的；
- 不检查硬链接、挂载、junction 或 TOCTOU；
- 不按时间清除聊天或 skill；
- 不加密 Vault；
- 不会自动把某个 skill 或决策提升为真理。

---

# 7. 操作安全

- 模型是不可信的：策略与确认才是控制手段。
- Vault 是明文 Markdown：它可能包含对话和决策。
- 审计可能包含文件输出：必须加以保护。
- API 密钥只存在于环境变量中。
- MCP/OAuth token 保存在权限受限的本地缓存中。
- 除非确有必要，不要把 Ollama 或 LM Studio 暴露在网络上。
- 位于允许目录中的硬链接或挂载可能暴露
  外部内容：Hagar 不会检测它们。

---

# 8. 故障排查

| 症状 | 检查 |
|---|---|
| `Policy: DENY ALL` | 验证 `policy.yaml` 和 `policy.path` |
| `Memory: disabled` | `vault.path` 是否存在？是否可写？ |
| `Projects: disabled` | `vault.path/Hagar/projects` 是否存在？ |
| `Failed to load MCP server` | 端点、token、`/mcp` |
| `MCP auth token missing` | `token_env` 指定的变量 |
| `MCP HTTP 401` | Basic 或 OAuth 的凭据/header |
| `MCP HTTP 400` | 服务器的协议、会话或参数 |
| `read_file` 文件过大 | 请使用 `read_chunk` |
| `PermissionError` | 策略、`R/W/X` 权限、路径是否在 sandbox 之外 |
| 工具未列出 | MCP 服务器失败或工具未注册 |
| 命令无法识别 | `/help` |

对于配置错误，Hagar 以代码 1 退出，并把
详细信息打印到 stderr。对于轮次错误，模型会收到
工具结果，审计则保留该事件。
