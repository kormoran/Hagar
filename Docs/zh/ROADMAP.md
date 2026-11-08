# HAGAR — 路线图

当前版本：0.5.2（准备中）
最后更新：2026-11-07

已做出的决定会被标明；仍未解决的问题列在每个
领域的末尾。第 1–9 节是截至
0.5.2 的历史；当前的行动计划是第 0 节。

---

# 0. 当前计划（0.5.2 之后）

## 0.1 状态

已发布：

- GitHub release `v0.3.0`；
- 覆盖 Python 3.11、3.12 和 3.13 的 Linux/macOS/Windows CI；
- action 升级到 Node 24；
- 意大利语文档，以及英语、西班牙语、中文、
  俄语、葡萄牙语和阿拉伯语译文；
- `lmstudio`、`openai`/`chatgpt` 后端和 `model.timeout`。

发布后已完成、尚未发布：

- `HarnessService`：轮次、状态、项目、事件和会话结束，不依赖
  `input()`/`stdout`；
- `CommandService`：`/help`、`/tools`、`/status`、`/mcp`、`/audit`、
  `/project`、`/memory`，带结构化的 `CommandResult`；
- 事件桥 `Agent`/`ToolRegistry` → `tool.call`、`tool.result`、
  `permission.*`；
- 本地 web GUI `hagar web`，带 SSE、聊天、项目、状态和模态
  ASK 确认；
- `QueueConfirmationProvider`，支持超时并从 GUI 解决；
- `core/usage.py`：为 OpenAI/LM Studio/DeepSeek、Claude、
  Gemini 和 Ollama 解析 token；按会话的 `UsageLedger`；
- GUI 侧边栏，显示通过 `usage.updated` 更新的
  input/output/总计 token；
- `MemoryIndex`：可增量重建的 SQLite/FTS5 索引；
- SQLite 记忆作为主要来源：会话、轮次、skill 和 summary；
- 命令 `/memory sessions`、`/memory chat`、`/memory backup`；
- 工具 `memory.search`、`/memory search`、`/memory reindex`、
  `/memory stats`；
- GUI 资源分离到 `web/index.html`、`web/style.css`、`web/app.js`。

## 0.2 后续版本的顺序

| Release | 目标 | 状态 |
|---|---|---|
| **0.4.0** | 记忆的 SQLite 索引 | 已并入 0.5.2 |
| **0.4.x** | GUI：轮次停止、历史、vision | 已并入 0.5.2 |
| **0.5.0** | 子智能体 | 已并入 0.5.2 |
| **0.5.2** | 当前版本 | 准备中 |
| **0.6.0** | LLM broker | 下一步 |
| **0.7.0** | 只读 SQL 工具 | 冻结 |

顺序可以变化，但约束是：**没有 usage 和限制，就没有
子智能体；没有子智能体和 model registry，就没有 broker。**

## 0.3 0.4.0 — 记忆的 SQLite 索引

状态：已实现；只剩在真实 Vault 上的验证，以及可能的
性能测量。

- 位置：应用的本地数据，不在同步的 Vault 内；
- schema：笔记、skill、决策、会话、tag、FTS5；
- 按 path/hash/mtime 增量同步；
- 原子的 `rebuild()`，索引可删除并可重建；
- FTS5 不可用时回退到词法搜索；
- 工具 `memory.search`，带 project/kind/status 过滤；
- `/memory reindex` 和 `/memory stats`；
- 不向模型暴露任何真实路径。

退出标准：删除 DB 不会丢失记忆；重建它
会返回相同的结果。

## 0.4 0.4.x — GUI

- 轮次的 **Stop** 按钮——已实现；
- vision：在 composer 中上传图片，按 provider 提供 adapter——
  已实现（OpenAI/LM Studio、Claude、Gemini）；
- 刷新后可见的聊天历史——已实现为过去聊天的列表，
  从 Vault 重新加载、恢复会话，并有
  **+ Nuova chat**；
- Chat、Chat history、Tool output、Audit、Thinking 和 Memories 标签页——
  已实现；日志关闭时 Audit 会被禁用，Thinking 在可用时使用
  reasoning，否则使用 timeline；
- 只读的记忆浏览器——已实现；
- CLI 侧的 `/usage` 命令——已实现；
- 以 entry point 形式提供的工具与 LLM provider 插件——已实现；
  audit sink 推迟。

vision 不得以 base64 形式进入记忆：只保留 hash 和
描述。

## 0.5 0.5.x — 子智能体与整合

- [x] 同步 MVP：`AgentSpec`、`agent.run`、只读工具、只读
  记忆、拒绝确认、`agent.*` 审计、独立 usage；
- [x] `agent.spawn/status/wait/result/cancel`，带线程，最多两个
  并发子智能体；
- [x] 每个 child 的 registry 和私有 workspace、复制输入和清理；
- [x] 用锁串行化的审计；
- [x] 强制的 `reason` 和独立的 `AGENT_SPAWN` capability；
- [x] artifact store、mailbox 和出站通道 `artifact.put`/`mailbox.send`，
  带 `AGENT_DATA` capability 和清理；
- [x] 对未导出 artifact 的 `artifact.discarded` 审计；
- [ ] 持久化/孤儿保留（仅在必要时）；
- [x] 项目和决策在同一个 SQLite 数据库中；
- [x] 从数据库导出 Markdown（`/memory export`）；
- [x] 把 Markdown 导入数据库（`/memory import`）；
- [x] 主数据库中的 FTS5，带 ranking 和 snippet；
- [x] 每个子智能体 5 分钟的墙钟超时；
- [x] child 的策略严格严于父级；
- [x] 父级、子级和 registry 事件中的 `agent_id`；
- [x] child 的 ASK 转发给用户，超时 180 秒并 DENY；
- [x] `decision.choose` 工具，带 LLM provider 和线性分类器；
- [ ] Jev/Kev adapter 和分类器的自动训练；
- [ ] token/成本预算；
- [ ] child 每个内部事件上的 `parent_id`；
- [ ] `audio.open`/`AudioInput`：附件通道与图片共享，
  但需要音频原生 provider、格式和不同的 ASR 语义；
  没有时间表；
- [x] 来自控制台的 ASK 确认，带 input broker、F5/F8 和 GUI 回退；

## 0.6 0.6.0 — LLM broker

- 模型的 JSON 技术卡片与基准测试（`/models test`）；
- CPU/RAM/GPU 硬件检测（`/models hardware`）；
- `ModelRegistry`，含 context window、tool calling、价格、延迟和
  本地性；
- `TaskProfile`，含所需工具、数据敏感性、预算和上下文；
- 基于规则/评分的路由，而不是"由一个 LLM 选择模型"；
- 由 host 校验的 `AgentSpec` 提议；
- broker 永不授予权限：它只能提议一个子集；
- 人工覆盖和 `broker.decision` 审计。

## 0.7 0.7.0 — SQL 工具

- 第一版只读；
- SQLite `mode=ro`、`PRAGMA query_only`，只允许一条语句；
- 不允许 `ATTACH`、写入型 `PRAGMA` 或 `load_extension`；
- 超时、行/字节上限和查询审计；
- 配置好的数据库 alias，绝不允许任意路径；
- capability `DATABASE_READ`；
- 写入和网络数据库只在后续阶段，使用
  `DATABASE_WRITE` 和 `NETWORK`。

## 0.8 开放问题

- 如果 release 已存在，release workflow 应幂等；
- PyPI：推迟，不阻塞 0.4；
- MCP OAuth Atlassian：Basic 可用，OAuth 流程仍待
  验证；
- MCP/OAuth 和远程 provider 的 live 测试；
- 译文的维护：只在发布时重新生成，而不是在
  每次提交时；
- Vault 的并发与原子写入：在引入共享记忆的子智能体之前
  需要评估；
- document tool：契约与协议已在 `DOCUMENT_TOOL.md` 中定义；
  CSV MVP 仍待实现。

## 0.9 文档

`Docs/it` 是开发期间唯一维护的来源。`Docs/en`、`Docs/es`、`Docs/zh`、`Docs/ru`、`Docs/pt` 和 `Docs/ar` 目录
只在准备发布时重新生成。

---

# 1. 方向

Hagar 已从"想法"变成"可运行的系统"（v0.1），再变成一个
带审计、多个后端和测试套件的 harness（v0.2 进行中）。
下一个跨越不是增加工具：而是给系统一个**记忆**，
以及一种比文本 JSON 更不易出错的方式来调用工具。

已决定的顺序：

1. Vault 上的记忆；
2. 对支持的 provider 使用原生 calling；
3. PermissionEvaluator——**v1 已完成**（policy.yaml、ASK、审计）；
4. 卫生（审计、MCP、打包、live 测试）。

---

# 2. 优先级 1 — Vault 上的记忆

## 2.0 状态：v2 已实现（2026-11-04）

已交付：

- 由 harness 写入的情景记忆，每个会话一个笔记；
- 自动注入最近 `context_turns` 个轮次；
- 工具 `memory.create_skill`、`memory.list_skills`、`memory.get_context`；
- 来源信息（`source_session`、`source_turn`、`model`），状态
  `candidate`，按 slug 去重；
- 策略 `MEMORY_READ`/`MEMORY_WRITE` 和命名空间 `chat` / `skills`；
- vault 缺失 → 记忆被停用并给出警告，harness 仍运行；
- 生命周期 `candidate` → `confirmed` → `archived`，由人从 CLI
  审查（`/memory review`、`confirm`、`archive`）；
- 只自动注入已确认的 skill，按词法匹配取前 3 个；
- 保留策略选项 A：不自动删除，只归档；
- 项目记忆与 skill 分开：决策、备选方案、
  理由、状态和来源；
- 启动时选择项目、`--project`/`--free`、`/project`
  命令；
- 带回退的会话结束 summary，transcript 移动到 `archive/chat/`，
  并在 summary 中带链接/hash；
- 会话结束时审查决策；如果被拒绝，它们保持
  `candidate`，并带 `auto_saved: true`；
- 带 `max_context_chars` 预算（字符，而不是
  token）的索引式上下文，以及用于细节的 `memory.project_context`；
- 用于请求项目归档的 `project_max_active`；
- 用 `memory.archive_search`、
  `memory.archive_read`、`/memory archive search|read` 查阅归档，
  支持按项目过滤，transcript 的 frontmatter 中带 `project`。

剩余：聊天保留、语义搜索、GUI。

## 2.1 已做出的决定

- **情景记忆由 harness 写入。** 聊天轮次默认由 harness 记录：
  这是机械式记录，而不是模型的判断。不会有缺失的轮次，
  也不会有编造的记忆。
- **语义记忆由 LLM 按需写入。** 模型只能通过专用工具
  提出记忆（skill）。该提议是显式的、可归属的、可审查的——
  第一法则禁止把它当作事实。
- **只用 Obsidian Vault。** 记忆不写入真实文件系统
  （目前）。`filesystem.sandbox` 仍是操作 sandbox。
- **Vault 不会被重写。** 工具只添加笔记或小节；不会
  覆盖用户精心维护的笔记。
- **项目是显式的。** 项目在启动时从活动项目列表中
  选择，或用 `--project`；`--free` 和"自由
  活动"没有项目记忆。
- **项目决策。** 它们与 skill 分开：记录
  决策、备选方案和理由。它们作为 `candidate` 提出，
  在会话结束时审查；如果审查被拒绝，它们保持
  candidate，带 `auto_saved: true`，不会自动成为事实。
- **没有 token 配额。** 上下文在构造上受限：
  项目索引、决策标题、summary 和以字符计
  `max_context_chars`。不测量模型的上下文窗口。
- **归档，而非删除。** 已归档的 transcript 和决策
  仍留在 Vault 中；项目归档是可逆的。

## 2.2 计划的工具

已在 `memory.*` 命名空间中实现的名称：

| tool | 谁调用它 | 做什么 |
|---|---|---|
| `memory.create_skill` | LLM | 创建一条**候选**语义记忆 |
| `memory.list_skills` | LLM | 列出可用记忆 |
| `memory.get_context` | LLM | 取回过去的聊天轮次 |

已实现的签名：

```text
memory.create_skill(title, content, kind="procedure", tags=None)
    -> {id, title, kind, status, tags, created_at, source_*, path, duplicate}

memory.list_skills(kind=None, status=None, limit=20)
    -> [{id, title, kind, status, tags, created_at, source_*}]

memory.get_context(limit=5, query=None, session=None)
    -> [{session, turn, timestamp, question, answer}]
```

行为：

- `create_skill`：由标题生成 slug，按 slug 去重，长度限制
  （`max_skill_chars`），frontmatter 含 `status: candidate`、
  `source_session`、`source_turn`、`model`、`created_at`；如果已存在
  相同 slug，则返回已存在的 id，而不是重复创建。
- `list_skills`：读取 frontmatter 和正文（用于 recall），可按
  `kind`（`fact` / `procedure`）和 `status` 过滤。
- `get_context`：没有 `session` 时搜索所有会话；有 `query` 时
  在过去轮次中按关键词搜索；`limit` 被限制在
  1..50，以免把整个 Vault 灌进上下文。

## 2.3 Vault 中的结构

```text
<Vault>/Hagar/
  chat/2026-11-03-<session>.md      # 每会话一个笔记，轮次追加
  skills/<slug>.md                  # 每条记忆一个笔记
```

情景记忆（每个会话一个笔记，轮次追加到末尾）：

```markdown
---
session: a1b2c3d4
type: chat
created: 2026-11-03T00:12:44+01:00
---

# Chat 2026-11-03

## 2026-11-03T00:12:44+01:00 · 7f3a

**用户:** ...
**Hagar:** ...
```

语义记忆（每个 skill 一个笔记）：

```markdown
---
id: usa-uv-per-python
title: Usare uv per i progetti Python
kind: procedure
status: candidate
tags: [python, tooling]
source_session: a1b2c3d4
source_turn: 7f3a
model: llama3.1:latest
created_at: 2026-11-03T00:15:02+01:00
---

由模型提出的步骤 / 内容。
```

## 2.4 配置

```yaml
vault:
  path: <percorso reale>

memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  max_skill_chars: 4000
```

## 2.5 harness 的行为

- 轮次结束时：把问题和回答追加到会话笔记（只有
  对话，**不**包含工具输出：那些留在审计中）。
- 轮次开始时：注入最近 `context_turns` 个轮次，以及最多
  `context_skills` 个相关的**已确认** skill（词法匹配），
  而不等模型调用 `get_context`。
- 每次记忆写入或审查都会产生一个审计事件
  （`memory.enabled`、`memory.disabled`、`memory.context`、`memory.turn`、
  `memory.review`、`memory.status`、`memory.failed`）；Vault 缺失或
  不可写不会停止 harness。
- 情景记忆与审计分开：审计保持取证用途，
  也包含工具数据。

## 2.6 开放问题

- **聊天保留**：保留多少个会话，是否摘要
  旧的；0.2.0 不删除任何东西。
- **搜索**：当数据量增长时使用索引（SQLite FTS）或 embedding；
  目前是按关键词。
- **GUI**：对记忆写入和审查也用模态对话框做 ASK
  确认。
- **上下文选择**：目前是全局最近轮次、项目
  索引和按词法匹配的前 3 个已确认 skill，没有
  语义相关性。
- **决策整合**：项目可能超过
  `project_max_active`；目前 Hagar 提议归档，而不是
  合并重复的决策。

## 2.7 非目标（目前）

- 把记忆写入真实文件系统；
- 修改用户已有的笔记；
- embedding / ChromaDB / 语义搜索（之后，如果数据量
  证明有必要）；
- 在显式流程之外自主写入记忆。

---

# 3. 优先级 2 — 原生 calling（v1，已完成）

**状态：** 2026-11-03 实现。对四个 provider 的 `native_step()`、
来自 `ToolDefinition` 的参数 schema、规范的 `tool` 消息、
每轮多次调用、HTTP 400/404/422 上的自动回退
以及 `--no-native-tools`。已在 Ollama 和 DeepSeek 上实测；
Claude 和 Gemini 仍待测试。用 `tools/bench_native.py` 测量：没有哪种
协议在所有模型上都胜出（原生更快，文本有时更
准确）。对于忽略工具的本地模型仍需改进。

## 3.1 目标

消除文本 JSON 协议的脆弱性：不再需要
修复，参数由 provider 的 schema 校验，结果
结构化。

## 3.2 方法

- 对不支持原生 calling 或做得不好的模型，保留文本协议作为
  **回退**。
- 给 `LLMClient` 添加一个声明式能力
  （`supports_native_tools`）和一条原生路径。
- `Agent` 必须同时处理两者：文本的 `ToolCall`，或带 id 的
  原生调用；结果以 provider 期望的格式返回。
- 基准测试衡量改进（每轮修复次数、
  参数正确性）。

## 3.3 按 provider 的传输

| provider | 请求 | 工具结果 |
|---|---|---|
| `ollama` | `/api/chat` 中的 `tools` | 角色为 `tool` 的消息 |
| `deepseek` | `tools`（OpenAI） | 角色 `tool` + `tool_call_id` |
| `claude` | `tools` + `tool_use` 块 | `tool_result` 块 |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 3.4 风险

- 小型本地模型常常不能很好地使用原生 calling：需要
  自动回退。
- 消息的管道会变化：每个 provider 和回退路径的测试
  都是必须的。
- 有些模型会在同一轮返回多个调用：Agent
  会在轮次限制内全部执行。

---

# 4. 优先级 3 — PermissionEvaluator

## 4.1 状态：v1 已实现

已交付：

- `core/permissions.py` 中的 `Capability`、`Effect`、`Rule`、`Subject`、`Resource`、`Decision` 和
  `PermissionEvaluator`；
- `policy.yaml` 在 LLM **之前**读取，回退为全面 `DENY`，
  并在审计和聊天中给出警告；
- 由 `permissions.read/write/shell` 导出的系统上限；
- 按 `tools`（glob）、`paths` 和 `namespaces`（前缀）限定的作用域；
- `ASK` 与 `ConsoleConfirmation`（`lo faccio? (y/N)`，默认 N）；
- 在 `ToolRegistry.execute` 中应用，并审计
  `permission.decision` / `permission.confirmation`；
- 所有工具（文件系统和 MCP）的 `ToolDefinition.capabilities`；
- `requires_confirmation` 作为 ASK 底线应用；
- 收集到 347 个测试，1 个跳过。

## 4.2 仍需完成

- 面向 GUI（模态对话框）和非交互执行
  （默认拒绝）的 `ConfirmationProvider`；
- 按任务/角色的动态策略，运行时只能收缩（一个
  agent 可以自我收缩权限，但永远不能自行扩大）；
- 由配置分配、而非由服务器声明的 MCP 工具 capability；
- 多个并发执行的主体（多个带不同策略的
  agent）；
- 面向记忆和路径的资源对象，而不仅是工具。

---

# 5. 优先级 4 — AIsh

专用于 LLM 的 shell，概念上类似 Bash，但完全没有对
真实 shell 的访问：

- 不执行宿主命令；
- 只使用已注册的工具；
- 模拟文件系统和虚拟路径（`workspace://`）；
- 与 MCP 工具集成；
- 管道和虚拟命令。

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```

虚拟路径还能解决 sandbox 绝对路径
暴露的问题。

---

# 6. 卫生与稳健性

已完成（2026-11-03）：

- **MCP**：`text/event-stream` 响应、
  `notifications/initialized` 通知、把结果规范化为文本
  （`text` 块、`structuredContent`、`isError` 错误）。
- **MCP auth**：bearer 或自定义 header，token 只来自环境变量，
  如果 token 缺失则以 `mcp.failed` 跳过服务器。
- **MCP OAuth**：带浏览器的 authorization code + PKCE 流程、RFC 9728/8414
  发现、动态注册、token 缓存、刷新和 401 重试。
- **审计**：按 `max_bytes` 轮转，可用
  `verify_chain` 验证的 hash 链，用
  `include_outputs: false` 对工具输出做遮蔽。
- **审计保留**：带时间戳的备份和 `audit.max_files`（默认
  100，包含活动文件），并修剪最旧的。
- **live 测试**：marker `live`，默认排除，`--live` 用于 Ollama
  和远程 provider（后者在没有密钥时跳过）。
- **打包**：完整元数据、entry point `hagar`、`--config`、
  `--model`、`--no-memory`、`--version`、单一版本号。
- **base URL**：`model.host` 适用于所有 provider。
- **遗留**：移除了 `tools/filesystem.py` 和 `llm/tool_result.py`。

剩余：

- MCP OAuth 的 device flow / DPoP；
- 审计会话的压缩；
- `ASK` 的 GUI 确认；
- 文档的持续对齐。

---

# 7. 更远的将来

- Vault 上的语义搜索（先索引，之后可能用 ChromaDB）；
- 对文档做 RAG；
- 任务管理和持久 scratchpad；
- vault 观察（用户修改的笔记）；
- 永久个人 agent；
- 更多 provider（OpenAI 几乎免费：与 DeepSeek 相同的客户端，
  只是 base URL 不同）。

---

# 8. 工作顺序

1. 记忆 v2：已完成（生命周期、CLI 审查、注入已确认项）；
   剩余聊天保留、语义搜索和 GUI。
2. PermissionEvaluator：v1 已完成；剩余 GUI 确认和动态
   策略。
3. 卫生：已完成（打包、live 测试、MCP auth/OAuth、带保留的
   审计、base URL、遗留）。
4. 原生 calling：v1 已完成；只剩用基准测试测量。
5. Release 0.3.0：已为 GitHub 准备好，带多平台 CI 和
   release workflow。

---

# 9. 本地工具

截至 2026-11-05 的状态：

- 文件系统 v2：`list_dir`、`read_chunk`、`rename`、`copy_file`、
  `search`，以及已有工具；
- `local_tools/`：`calculator.evaluate`、`statistics.compute`、
  `units.convert`、`feed.read`（本地 provider，不是 MCP 服务器）；
- capability `COMPUTE` 始终在上限中，`NETWORK` 由
  `permissions.network` 和策略控制（feed 为 `ask`）；
- 写入限制：`max_write_bytes`、`min_free_bytes`、
  `session_write_bytes` 和 `ask_over_bytes`，带统一预检；
- `feed.read` 带 SSRF 策略：只允许全局地址、重定向
  重新校验、URL 中不含凭据；
- 文件系统带虚拟根 `/home/ai`、强制 alias 和
  按 mount 的权限（`R`/`W`/`X`）；
- POSIX runner `tools/run_tests.sh` 与 Windows 版并存。

开放问题：

- DNS rebinding：解析会被校验，但 `requests` 在连接时会
  再次解析名称；需要一个 pinned resolver 或专用
  adapter 来彻底解决；
- 计算器是有意受限的（没有符号代数）；
- 考虑对其他工具输出也设置大小限制。

作为用户责任关闭：

- 允许目录内的硬链接、mount 和 junction 不由 Hagar
  检查。要实现完全隔离，用户必须保证
  其中没有这类对象；Hagar 不创建也不检测它们；
- TOCTOU 竞态：Hagar 不使用 `openat2`、对每个组成部分的 `O_NOFOLLOW` 或
  Windows handle，也不保证检查与操作之间的原子性。
  该竞态需要带写访问权限的本地并发进程；
  这是恶意或环境被攻陷的场景，不是正常使用。
  要实现完全隔离，需要专用卷、独立用户、mount
  namespace 或容器。
