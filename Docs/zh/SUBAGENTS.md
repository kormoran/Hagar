# 子智能体 — 异步阶段

**状态：** 已实现
**日期：** 2026-11-07
**工具：** `agent.spawn`、`agent.status`、`agent.wait`、`agent.result`、
`agent.cancel`、`agent.run`（同步兼容）、`artifact.*`、
`mailbox.*`

## 1. 它们做什么

模型最多可以启动两个并发子智能体：

```text
agent.spawn(task, reason, context?, inputs?) -> agent_id
agent.status(agent_id) -> 状态
agent.wait(agent_id, timeout?) -> 结果
agent.result(agent_id) -> 结果
agent.cancel(agent_id) -> ok
```

`spawn` 立即返回。父级可以继续工作，并在需要时收集
结果。`agent.run` 仍作为 `spawn + wait` 的快捷方式保留，
以保持兼容。

`reason` 是必填的：它会记录到审计中，是父级
委派工作的理由。该工具需要 capability
`AGENT_SPAWN`；child 不会收到它，因此不能创建其他子智能体。
`permissions.agents: true` 是所需的系统上限。

child 的策略必须**严格严于**
父级的策略。manager 会计算：

```text
child_ceiling = parent_ceiling
              & (FILESYSTEM_READ | MEMORY_READ | COMPUTE | AGENT_DATA)
```

如果结果等于父级的上限，`agent.spawn` 会以
`SubagentPolicyError` 失败。因此相同的策略也会被拒绝。
如果父级没有 evaluator，spawn 会被拒绝。

每个 agent 都有 **5 分钟**（`300` 秒）的墙钟超时。该
限制是协作式的：在 agent 循环的检查点被检查；
不会中断已经正在进行的 HTTP 调用。到期时 child 的状态
为 `timed_out`，审计记录 `agent.timed_out`。

每个 child：

- 使用与父级相同的本地模型，但使用独立的 LLM 客户端；
- 有独立的 registry；
- 只能看到 capability 为 `FILESYSTEM_READ`、
  `MEMORY_READ` 和 `COMPUTE` 的工具，外加 `AGENT_DATA`；
- 可以在自己的 workspace 上使用 `vision.open`，但不能使用
  `agent.*` 或 `filesystem.chdir`；
- 只读自己的 workspace；
- 不写入记忆；
- 通过 bridge 把 ASK 请求转发给用户，超时
  180 秒，到期即 DENY。

父级 LLM 不能批准 ASK：请求始终发往人工
通道（GUI 或控制台）。bridge 会给请求加上 `agent_id` 和 `parent_id`。

## 2. 私有 workspace

为每个 child 创建一个临时 workspace：

```text
<hagar-temp>/hagar-subagent-<id>/
```

child 看到的是：

```text
/home/ai/workspace
```

该 workspace 是只读的。启动之前，manager 会复制父级
指定的输入：

```text
agent.spawn(
    task="分析 CSV",
    reason="这些文件彼此独立，可以并行分析",
    inputs=["/home/ai/workspace/report.csv"]
)
```

规则：

- 输入必须是父级 sandbox 中的文件；
- 父级必须有读取权限；
- 文件名会被保留；
- 两个同名输入是错误；
- child 看不到宿主路径；
- workspace 在轮次结束时被删除。

父级只写入自己的 workspace。child 的 workspace 在
父级的根之外，因此无法通过它的工具访问。

## 2.1 Outbox、artifact 与 mailbox

child 不写入 workspace。要产出数据，它使用 outbox：

```text
artifact.put(text, kind?, mime_type?)       -> artifact_id
artifact.put_file(path, mime_type?)          -> artifact_id
mailbox.send(text, artifacts?)               -> message
```

`artifact.put_file` 从 child 的只读 workspace 读取文件，
并把它复制到 Hagar 管理的 store 中。

父级用以下方式读取：

```text
artifact.list()
artifact.read(artifact_id, offset?, length?)
artifact.save_to(artifact_id, path, overwrite?)
mailbox.inbox(cursor?, limit?)
mailbox.read(message_id)
mailbox.ack(message_id)
```

`artifact.save_to` 把整个 artifact 复制到父级 sandbox 中可写的路径，
而不让内容经过上下文。对于大于模型窗口的 artifact，
这就是应当使用的操作：
模型只读取它需要的块，并用 `save_to` 保存完整文件。

`save_to` 需要 `AGENT_DATA`、`FILESYSTEM_WRITE` 和
`FILESYSTEM_CREATE`；策略把它当作写入，并可能
请求确认。它不接受任意的宿主路径。

初始限制：

| 元素 | 限制 |
|---|---|
| 单个 artifact | 50 MB |
| 每轮 artifact 总量 | 256 MB |
| 每轮 artifact 数量 | 200 |
| 每次调用读取量 | 256 KB |
| 单条消息文本 | 64 KB |
| 每个 mailbox 的消息数 | 100 |

artifact 是 Vault 之外的临时文件，带 SHA-256 hash 和
元数据。mailbox 只包含文本和 `artifact_id` 引用。
轮次结束时，store 和 mailbox 都会被清空。

## 3. 实现的限制

- 最多 **2** 个活动子智能体（可在 manager 中配置为
  `max_concurrent`）；
- 仅限本地模型；
- 不支持嵌套：child 的 registry 排除 `agent.*`；
- 5 分钟墙钟超时，协作式；
- 除 `max_tool_calls` 外没有 token 预算；
- 没有专用 GUI；
- 不写入记忆；
- child 的 ASK 转发给用户，超时 180 秒；到期
  即 DENY；
- artifact 和 mailbox 是临时的：轮次结束时消失；
- child 的内部事件（`turn.*`、`tool.*`）在审计中带
  `agent_id`。

在父级轮次结束时：

1. `finish_turn()` 在超时内等待子级；
2. 取消仍活动的子级；
3. 删除 workspace；
4. 忘记 job。

## 4. 隔离的组件

| 组件 | 父级 | Child |
|---|---|---|
| LLM client | `harness.llm` | 新实例，同一模型 |
| Tool registry | 完整 | 过滤为只读 |
| Filesystem | 父级 workspace | 私有只读 workspace |
| 记忆 | `MemoryStore` | `memory=None`，不写入 |
| Artifact/mailbox | 读 | child 的 outbox |
| 确认 | 用户 | 通往用户的 bridge，超时 180 |
| Usage | 父级 ledger | 独立 ledger |
| 审计 | 共享，带锁 | `agent.*` 事件 |

child 没有父级的自动上下文：父级必须传递
`context`。

## 5. 允许的工具

父级必须有 capability `AGENT_SPAWN` 和 `COMPUTE`；child
不会收到 `AGENT_SPAWN`，因此不能创建其他 agent。

child 的 registry 包含 capability 是以下集合的
子集的工具：

```text
FILESYSTEM_READ
MEMORY_READ
COMPUTE
AGENT_DATA
```

child 会收到 `artifact.put`、`artifact.put_file` 和 `mailbox.send`。
它不会收到 `artifact.read`、`artifact.list`、`mailbox.inbox`、
`mailbox.read` 或 `mailbox.ack`：那些属于父级。

被显式排除的：

```text
filesystem.chdir
agent.*
```

按 capability 排除的：

- 文件系统写入；
- 创建、重命名、复制、删除；
- 记忆写入；
- 网络；
- MCP；
- shell。

## 6. 审计

manager 记录的事件：

```text
agent.spawned
agent.policy_rejected
agent.started
agent.finished
agent.timed_out
agent.cancelled
agent.failed
confirmation.timeout
artifact.discarded
```

主要字段：

```text
agent_id
agent
parent
task
inputs
max_tool_calls
max_seconds
status
usage
duration_ms
error
artifact
owner
kind
size
sha256
read_count
reason
```

父级和子级的所有事件都带 `agent_id`。registry 和 Agent 的事件
使用执行该动作的 agent 的 id；manager 的事件额外带
`agent_id` 和 `parent`。
如果 spawn 没有严格更严格的策略，
会发出 `agent.policy_rejected`。

`artifact.discarded` 在轮次结束时对每个未用
`artifact.save_to` 保存的 artifact 发出：

```text
reason=unread                → 从未读取
reason=read_but_not_saved    → 已读取但未导出
```

如果 child 的 ASK 在 180 秒内没有响应，
会发出 `confirmation.timeout`；结果是 DENY。GUI 显示该请求，带
`agent_id`/`parent_id`，父级不能解决它。

已导出的 artifact 不会产生该事件：文件已经在父级的
workspace 中。内容绝不会写入审计。

`AuditLog.record` 受锁保护，因此并发写入不会
交错 hash 链。

## 7. 并发

- 为子级使用独立线程；
- 限制 `max_concurrent = 2`；
- 对 job 字典加锁；
- 文件系统上没有竞态条件：workspace 相互独立；
- 不共享 `MemoryStore`、sandbox 或 LLM 客户端；
- 本地 provider 承受并发请求；
- `agent.wait` 只阻塞调用者，不阻塞其他子级。

## 8. 测试

`tests/test_subagents.py` 覆盖：

- 用只读工具执行；
- 排除写入和 `agent.*`；
- 传递上下文；
- 把输入复制到私有 workspace；
- 超过 `max_concurrent` 时拒绝；
- 两个并发子智能体；
- provider 构建错误；
- 审计事件。

用 LM Studio 和 `gemma-3-27b-it` 执行了 live 测试：两个并发
子智能体完成，各自使用独立的 usage。

## 9. 后续步骤

- 从 child 的 workspace 显式导出 artifact；
- token/时间预算和墙钟超时；
- 如有需要，受控嵌套；
- 所有内部事件上的 `agent_id`；
- 把确认委派给父级或 GUI；
- 模型由 broker 而非 manager 选择。
