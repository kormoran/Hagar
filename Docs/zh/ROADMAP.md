# HAGAR — 路线图

当前版本：0.7.0（开发中）
最后更新：2026-11-09

已做出的决定会标明；仍未解决的问题列在每个领域的末尾。第 1–9 节是截至
0.6.0 的历史；当前行动计划是第 0 节。

---

# 0. 当前计划（0.6.0 之后）

## 0.1 后续版本的顺序

| Release | 目标 | 状态 |
|---|---|---|
| **0.6.0** | 运行时安全 + AIsh | 已发布 |
| **0.7.0** | dev.run + box + Hagar Flow | 开发中 |
| **0.8.0** | LLM broker | 下一步 |
| **0.9.0** | 只读 SQL 工具 | 冻结 |

顺序可以改变，但约束是：**没有 usage 和限制，就没有子智能体；没有子智能体和
model registry，就没有 broker。**

## 0.1.1 0.7.0 — 本地编排

- `dev.run`，带沙箱之外的可信配方；
- `box.list` 和 `box.run`，用于有边界的 LLM 转换；
- `flow.run`、`flow.validate` 和 `flow.reference`；
- 只带一个 `for` 的 list comprehension；
- 只读记忆原语：`memory.search`、`memory.context`、
  `memory.skill` 和 `project.context`；
- 用 `flow.repair` 进行显式修复；
- 此版本没有 container mode。

## 0.2 0.8.0 — LLM broker

- 模型的 JSON 技术卡片与基准测试（`/models test`）；
- CPU/RAM/GPU 硬件检测（`/models hardware`）；
- `ModelRegistry`，含 context window、tool calling、价格、延迟和
  本地性；
- `TaskProfile`，含所需工具、数据敏感性、预算和上下文；
- 基于规则/评分的路由，而不是"由一个 LLM 选择模型"；
- 由 host 校验的 `AgentSpec` 提议；
- broker 永不授予权限：它只能提议一个子集；
- 人工覆盖和 `broker.decision` 审计。

## 0.3 0.8.0 — SQL 工具

- 第一版只读；
- SQLite `mode=ro`、`PRAGMA query_only`，只允许一条语句；
- 不允许 `ATTACH`、写入型 `PRAGMA` 或 `load_extension`；
- 超时、行/字节上限和查询审计；
- 配置好的数据库 alias，绝不允许任意路径；
- capability `DATABASE_READ`；
- 写入和网络数据库只在后续阶段，使用
  `DATABASE_WRITE` 和 `NETWORK`。

## 0.4 开放问题

- 如果 release 已存在，release workflow 应幂等；
- PyPI：推迟；
- MCP OAuth Atlassian：Basic 可用，OAuth 流程仍待
  验证；
- MCP/OAuth 和远程 provider 的 live 测试；
- 译文的维护：只在发布时重新生成，而不是在
  每次提交时；
- document tool：契约与协议已在 `DOCUMENT_TOOL.md` 中定义；
  CSV MVP 仍待实现。

## 0.4.1 完整文件系统版本 — 冻结

现已实现：

- 带原子写入的 `edit_file`；
- 轮次检查点和 `/undo`；
- 按工具超时和重复防护；
- 输出溢出和上下文压缩。

已实现的 MVP 覆盖 `edit_file`、原子写入、
覆盖/删除/重命名前读取，以及 `mtime_ns+size` 版本。
完整版本已冻结；不会进入下一个版本：

- 带多 hunk 补丁和 diff 的 `edit_file`；
- 除 `mtime_ns`/`size` 之外的内容 hash；
- 带文件系统级 CAS 检查的原子写入；
- 按单个智能体观察，并在父级和子智能体之间显式隔离；
- 审计 `fs.observed`、`fs.guard_denied`、`fs.stale`；
- 目录 rename/delete 的覆盖；
- GUI 集成和引导式恢复消息。

## 0.4.2 AIsh — 已在 0.6.0 中实现

`aish.exec` 是 Hagar 工具之上的语义 shell，默认策略为 `DENY`。已实现的命令：
导航、读取、纯文本、管道和单文件变更。它不执行宿主程序、
重定向、变量或命令替换。
`text.transform` 提供 AIsh 使用的有界文本操作。

## 0.4.3 dev.run — 已实现

`dev.list` 和 `dev.run` 执行用于测试、调试和构建的可信配方。
`recipes.yaml` 位于沙箱之外，在启动时读取，没有
热重载。`DEV_EXEC` 默认为 DENY；后端仅为 host。

容器保持冻结，以备未来直接访问真实文件系统/程序，
绝不在沙箱内。

## 0.4.4 Boxed transform — 已实现

`box.list` 和 `box.run` 以固定 prompt、基于文件的输入/输出，且没有
记忆或工具，执行 `summarize`、`translate` 和
`extract_json`。`BOX_EXEC` 默认为 DENY。

它们是未来 DSL 的原语。

## 0.4.5 Hagar Flow — MVP

`flow.run` 执行带 AST 校验器和 Hagar 解释器的 Python 线性子集，
不使用 `eval`/`exec`。原语 `fs.*` 和 `box.*`，以及步数和
工具调用上限。`FLOW_EXEC` 默认为 DENY。

HIR、并行和子智能体不在 MVP 内。

## 0.5 文档

`Docs/it` 是开发期间唯一维护的来源。`Docs/en`、`Docs/es`、`Docs/zh`、
`Docs/ru`、`Docs/pt` 和 `Docs/ar` 目录只在准备发布时重新生成。

---

## 1.0 状态：v2 已实现（2026-11-04）

已实现：

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
- 带回退的会话结束 summary，transcript 位于 `archive/chat/`，
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

## 1.1 已做出的决定

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

## 1.2 计划的工具

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

## 1.3 Vault 中的结构

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

## 1.4 配置

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

## 1.5 harness 的行为

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

## 1.6 开放问题

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

## 1.7 非目标（目前）

- 把记忆写入真实文件系统；
- 修改用户已有的笔记；
- embedding / ChromaDB / 语义搜索（之后，如果数据量
  证明有必要）；
- 在显式流程之外自主写入记忆。

---

## 2 目标

消除文本 JSON 协议的脆弱性：不再需要
修复，参数由 provider 的 schema 校验，结果
结构化。

## 2.1 方法

- 对不支持原生 calling 或做得不好的模型，保留文本协议作为
  **回退**。
- 给 `LLMClient` 添加一个声明式能力
  （`supports_native_tools`）和一条原生路径。
- `Agent` 必须同时处理两者：文本的 `ToolCall`，或带 id 的
  原生调用；结果以 provider 期望的格式返回。
- 基准测试衡量改进（每轮修复次数、
  参数正确性）。

## 2.2 按 provider 的传输

| provider | 请求 | 工具结果 |
|---|---|---|
| `ollama` | `/api/chat` 中的 `tools` | 角色为 `tool` 的消息 |
| `deepseek` | `tools`（OpenAI） | 角色 `tool` + `tool_call_id` |
| `claude` | `tools` + `tool_use` 块 | `tool_result` 块 |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 2.3 风险

- 小型本地模型常常不能很好地使用原生 calling：需要
  自动回退。
- 消息的管道会变化：每个 provider 和回退路径的测试
  都是必须的。
- 有些模型会在同一轮返回多个调用：Agent
  会在轮次限制内全部执行。

---

# 3. 优先级 3 — PermissionEvaluator

状态：v1 已实现

## 3.1 仍需完成

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
  `include_outputs: false` 对工具输出做脱敏。
- **审计保留**：带时间戳的备份和 `audit.max_files`（默认
  100，包含活动文件），并修剪最旧的。
- **base URL**：`model.host` 适用于所有 provider。

剩余：

- MCP OAuth 的 device flow / DPoP；
- 审计会话的压缩；
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
