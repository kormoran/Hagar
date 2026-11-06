# HAGAR — 路线图

当前版本：0.2.0（开发中）
最后更新：2026-11-03

已做出的决定会明确标注；仍未解决的问题列在
每个领域的末尾。

---

# 1. 方向

Hagar 已经从“想法”变成“可运行的系统”（v0.1），随后成为一个
带审计、多后端和测试套件的 harness（v0.2 进行中）。下一个
飞跃不是增加工具：而是给系统一个**记忆**，以及一种
比特文本 JSON 更不脆弱的工具调用方式。

已决定的顺序：

1. Vault 上的记忆；
2. 为支持的 provider 提供原生 calling；
3. PermissionEvaluator —— **v1 已完成**（policy.yaml、ASK、审计）；
4. 卫生性工作（审计、MCP、打包、live 测试）。

---

# 2. 优先级 1 — Vault 上的记忆

## 2.0 状态：v2 已实现（2026-11-04）

已完成：

- 由 harness 写入的情景记忆，每个会话一个笔记；
- 自动注入最近的 `context_turns` 个轮次；
- 工具 `memory.create_skill`、`memory.list_skills`、`memory.get_context`；
- provenance（`source_session`、`source_turn`、`model`）、状态
  `candidate`、按 slug 去重；
- 策略 `MEMORY_READ`/`MEMORY_WRITE` 以及命名空间 `chat` / `skills`；
- vault 缺失 → 记忆被禁用并给出警告，harness 继续运行；
- 生命周期 `candidate` → `confirmed` → `archived`，带 CLI 人工
  复核（`/memory review`、`confirm`、`archive`）；
- 只自动注入已确认的 skill，按词法匹配取前 3 个；
- 保留策略选项 A：不自动删除，只归档；
- 项目记忆与 skill 分开：决策、备选方案、
  理由、状态和 provenance；
- 启动时选择项目，`--project`/`--free`，`/project`
  命令；
- 会话结束摘要带机械回退，transcript 存入 `archive/chat/`，
  摘要中包含链接/哈希；
- 会话结束时复核决策；若被拒绝，它们保持
  `candidate` 并带 `auto_saved: true`；
- 基于索引的上下文，预算 `max_context_chars`（字符，而非
  token），细节通过 `memory.project_context` 获取；
- `project_max_active` 用于触发项目归档请求；
- 通过 `memory.archive_search`、
  `memory.archive_read`、`/memory archive search|read` 查阅归档，
  支持按项目过滤，transcript 在 frontmatter 中保留 `project`。

仍待完成：聊天保留策略、语义搜索、GUI。

## 2.1 已做出的决定

- **情景记忆由 harness 写入。** 聊天轮次默认由 harness
  记录：这是机械的会议记录，不是模型的判断。没有
  缺失的轮次，也没有凭空编造的记忆。
- **语义记忆由 LLM 按需写入。** 模型只能通过
  专用工具提出记忆（skill）。该提议是显式的、可归属的、
  可复核的——第一法则禁止把它当作真理。
- **只使用 Obsidian Vault。** 记忆不写入真实文件系统
  （目前如此）。`filesystem.sandbox` 仍是操作 sandbox。
- **Vault 不会被改写。** 工具会添加笔记或章节；它们不会
  覆盖用户精心维护的笔记。
- **显式项目。** 项目在启动时从活动项目列表中选择，
  或通过 `--project` 指定；`--free` 和“自由
  活动”没有项目记忆。
- **项目决策。** 它们与 skill 分开：记录
  决策、备选方案和理由。它们以 `candidate` 形式提出，
  并在会话结束时复核；如果复核被拒绝，它们保持
  candidate 并带 `auto_saved: true`，不会自动成为真理。
- **不做 token 配额。** 上下文在构造上就是受限的：
  项目索引、决策标题、摘要，以及以字符计的
  `max_context_chars`。不测量模型的上下文窗口。
- **归档，而非删除。** 已归档的 transcript 和决策
  仍留在 Vault 中；项目的归档是可逆的。

## 2.2 计划的工具

在 `memory.*` 命名空间中已实现的名称：

| 工具 | 谁调用 | 做什么 |
|---|---|---|
| `memory.create_skill` | LLM | 创建一个**候选**语义记忆 |
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

- `create_skill`：由标题生成 slug、按 slug 去重、长度限制
  （`max_skill_chars`）、frontmatter 包含 `status: candidate`、
  `source_session`、`source_turn`、`model`、`created_at`；如果已存在
  相同的 slug，则返回现有 id，而不是重复创建。
- `list_skills`：读取 frontmatter 和正文（recall 需要），可按
  `kind`（`fact` / `procedure`）和 `status` 过滤。
- `get_context`：没有 `session` 时搜索所有会话；带 `query` 时
  在过去的轮次中按关键字搜索；`limit` 被限制在
  1..50，以免把整个 Vault 倾泻进上下文。

## 2.3 Vault 中的结构

```text
<Vault>/Hagar/
  chat/2026-11-03-<session>.md      # 每个会话一个笔记，轮次追加
  skills/<slug>.md                  # 每个记忆一个笔记
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

**用户：** ...
**Hagar：** ...
```

语义记忆（每个 skill 一个笔记）：

```markdown
---
id: usa-uv-per-python
title: 用 uv 管理 Python 项目
kind: procedure
status: candidate
tags: [python, tooling]
source_session: a1b2c3d4
source_turn: 7f3a
model: llama3.1:latest
created_at: 2026-11-03T00:15:02+01:00
---

模型提出的步骤/内容。
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
  对话，**不含**工具输出：它们留在审计中）。
- 轮次开始时：注入最近的 `context_turns` 个轮次，以及最多
  `context_skills` 个相关的**已确认** skill（词法匹配），
  不必等模型调用 `get_context`。
- 每次写入或复核记忆都会产生审计事件
  （`memory.enabled`、`memory.disabled`、`memory.context`、`memory.turn`、
  `memory.review`、`memory.status`、`memory.failed`）；Vault 缺失或
  不可写不会中止 harness。
- 情景记忆与审计是分开的：审计保持取证用途，
  并且也包含工具数据。

## 2.6 待解决的问题

- **聊天保留**：保留多少会话，是否对旧会话做摘要；
  0.2.0 不删除任何内容。
- **搜索**：当数据量增长时使用索引（SQLite FTS）或 embedding；
  目前是按关键字。
- **GUI**：为记忆写入和复核也提供带模态对话框的 ASK
  确认。
- **上下文选择**：目前是全局的最近轮次、项目索引
  以及按词法匹配的前 3 个已确认 skill，没有
  语义相关性。
- **决策合并**：项目可能超过
  `project_max_active`；目前 Hagar 提议归档，而不是
  合并重复的决策。

## 2.7 非目标（目前）

- 把记忆写入真实文件系统；
- 修改用户已有的笔记；
- embedding / ChromaDB / 语义搜索（以后，如果数据量
  证明有必要）；
- 在显式流程之外自主写入记忆。

---

# 3. 优先级 2 — 原生 calling（v1，已完成）

**状态：** 于 2026-11-03 实现。四个 provider 的 `native_step()`、
来自 `ToolDefinition` 的参数 schema、规范的 `tool` 消息、
每轮多次调用、HTTP 400/404/422 上的自动回退
以及 `--no-native-tools`。已在 Ollama 和 DeepSeek 上完成 live 验证；
Claude 和 Gemini 仍待测试。用 `tools/bench_native.py` 测量：没有
哪种协议能在所有模型上胜出（原生更快，文本有时更
精确）。对于忽略工具的本地模型仍有待改进。

## 3.1 目标

消除文本 JSON 协议的脆弱性：不再有修复，参数由
provider 的 schema 校验，结果结构化。

## 3.2 方法

- 保留文本协议作为**回退**，用于不支持原生 calling
  或支持不佳的模型。
- 为 `LLMClient` 添加声明式能力
  （`supports_native_tools`）和原生路径。
- `Agent` 必须同时处理两者：文本 `ToolCall` 或带 id 的原生
  调用；结果以 provider 期望的格式返回。
- 基准测试衡量改进（每轮修复次数、
  参数正确性）。

## 3.3 各 provider 的传输方式

| provider | 请求 | 工具结果 |
|---|---|---|
| `ollama` | `/api/chat` 中的 `tools` | 带 `tool` 角色的消息 |
| `deepseek` | `tools`（OpenAI） | `tool` 角色 + `tool_call_id` |
| `claude` | `tools` + `tool_use` 块 | `tool_result` 块 |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 3.4 风险

- 小型本地模型常常无法很好地使用原生 calling：需要
  自动回退。
- 消息管道会变化：按 provider 以及回退路径的测试
  是必须的。
- 有些模型会在同一轮返回多个调用：Agent
  会在轮次限制内全部执行。

---

# 4. 优先级 3 — PermissionEvaluator

## 4.1 状态：v1 已实现

已完成：

- `core/permissions.py` 中的 `Capability`、`Effect`、`Rule`、`Subject`、`Resource`、`Decision` 和
  `PermissionEvaluator`；
- `policy.yaml` 在 LLM **之前**读取，出错时回退为完全 `DENY`，
  并在审计和聊天中给出警告；
- 由 `permissions.read/write/shell` 推导的系统上限；
- 按 `tools`（glob）、`paths` 和 `namespaces`（前缀）划分作用域；
- `ASK` 配合 `ConsoleConfirmation`（`lo faccio? (y/N)`，默认 N）；
- 在 `ToolRegistry.execute` 中应用，并审计
  `permission.decision` / `permission.confirmation`；
- 所有工具（文件系统和 MCP）的 `ToolDefinition.capabilities`；
- `requires_confirmation` 作为 ASK 下限应用；
- 收集到 347 个测试，1 个跳过。

## 4.2 仍待完成

- 用于 GUI（模态对话框）和非交互执行
  （默认拒绝）的 `ConfirmationProvider`；
- 按任务/角色的动态策略，仅允许运行时收缩（一个
  智能体可以缩小自己的权限，但绝不能自行扩大）；
- 由配置分配 MCP 工具的 capability，而不是
  由服务器声明；
- 多个主体同时执行（多个策略不同的
  智能体）；
- 针对记忆和路径的资源客体，而不仅是工具。

---

# 5. 优先级 4 — AIsh

专为 LLM 设计的 shell，概念上类似 Bash，但完全不
访问真实 shell：

- 不执行任何宿主命令；
- 只使用已注册的工具；
- 模拟的文件系统和虚拟路径（`workspace://`）；
- 与 MCP 工具集成；
- 管道和虚拟命令。

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```

虚拟路径还能解决 sandbox 绝对路径暴露的问题。

---

# 6. 卫生性与健壮性

已完成（2026-11-03）：

- **MCP**：`text/event-stream` 响应、`notifications/initialized`
  通知、结果规范化为文本（`text` 块、`structuredContent`、
  `isError` 错误）。
- **MCP auth**：bearer 或自定义 header，token 只来自环境，
  缺少 token 时服务器以 `mcp.failed` 跳过。
- **MCP OAuth**：带浏览器的 authorization code + PKCE 流程、RFC 9728/8414
  discovery、dynamic registration、token 缓存、refresh 和 401 重试。
- **审计**：在 `max_bytes` 时轮转，可用 `verify_chain`
  校验的哈希链，用 `include_outputs: false` 对工具输出
  脱敏。
- **审计保留**：带时间戳的备份和 `audit.max_files`（默认
  100，包含活动文件），并清理最旧的备份。
- **live 测试**：`live` 标记，默认排除，`--live` 用于 Ollama
  和远程 provider（后者在没有密钥时跳过）。
- **打包**：完整的元数据、入口点 `hagar`、`--config`、
  `--model`、`--no-memory`、`--version`、唯一版本号。
- **Base URL**：`model.host` 适用于所有 provider。
- **遗留代码**：移除了 `tools/filesystem.py` 和 `llm/tool_result.py`。

仍待完成：

- MCP OAuth 的 device flow / DPoP；
- 审计会话的压缩；
- `ASK` 的 GUI 确认；
- 文档的持续同步。

---

# 7. 更远的将来

- Vault 上的语义搜索（先索引，之后可能用 ChromaDB）；
- 基于文档的 RAG；
- 任务管理和持久 scratchpad；
- vault 观察（用户修改的笔记）；
- 永久个人智能体；
- 更多 provider（OpenAI 几乎免费：同一个 DeepSeek 客户端，
  只是 base URL 不同）。

---

# 8. 工作顺序

1. 记忆 v2：已完成（生命周期、CLI 复核、注入已确认 skill）；
   仍待完成聊天保留、语义搜索和 GUI。
2. PermissionEvaluator：v1 已完成；仍待完成 GUI 确认和动态
   策略。
3. 卫生性：已完成（打包、live 测试、MCP auth/OAuth、带保留策略的
   审计、base URL、遗留代码）。
4. 原生 calling：v1 已完成；仍待完成基准测量。
5. 0.3.0 发布：已为 GitHub 准备好，带跨平台 CI 和
   release 工作流。

---

# 9. 本地工具

截至 2026-11-05 的状态：

- 文件系统 v2：`list_dir`、`read_chunk`、`rename`、`copy_file`、
  `search`，以及原有的工具；
- `local_tools/`：`calculator.evaluate`、`statistics.compute`、
  `units.convert`、`feed.read`（本地 provider，不是 MCP 服务器）；
- capability `COMPUTE` 始终在上限内，`NETWORK` 由
  `permissions.network` 和策略控制（feed 为 `ask`）；
- 写入限制：`max_write_bytes`、`min_free_bytes`、
  `session_write_bytes` 和 `ask_over_bytes`，带统一预检；
- `feed.read` 带 SSRF 策略：仅全局地址，重定向
  重新校验，URL 中不含凭据；
- 文件系统使用虚拟根目录 `/home/ai`，别名必填，
  并按挂载设置权限（`R`/`W`/`X`）；
- POSIX 运行器 `tools/run_tests.sh` 与 Windows 版本并存。

待解决的问题：

- DNS rebinding：解析结果会被校验，但 `requests` 在连接时会
  再次解析名称；需要固定（pinned）的解析器或专用
  adapter 才能彻底解决；
- 计算器是刻意受限的（没有符号代数）；
- 考虑为其他工具输出也设置大小限制。

作为用户责任关闭：

- 允许目录内部的硬链接、挂载和 junction 不受
  Hagar 检查。要实现完全隔离，用户必须保证
  不存在这些对象；Hagar 不会创建它们，也不会检测它们；
- TOCTOU 竞态：Hagar 不使用 `openat2`、对每个组件使用 `O_NOFOLLOW`
  或 Windows handle，也不保证检查与操作之间的原子性。该
  竞态需要一个有写权限的本地并发进程；
  这是恶意场景或环境被攻破的场景，而不是正常使用。
  要实现完全隔离，需要专用卷、独立用户、挂载
  命名空间或容器。
