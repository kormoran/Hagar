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

`spawn` 会立即返回。父级可以继续工作，并在需要时收集结果。
`agent.run` 作为 `spawn + wait` 的快捷方式保留，用于兼容。

`reason` 是必填项：它会被记录到审计中，是父级委派工作的原因。
该工具需要 `AGENT_SPAWN` 能力；子级不会获得该能力，因此不能再创建
其他子智能体。`permissions.agents: true` 是必需的系统上限。

子级的策略必须**严格比父级更严格**。管理器会计算：

```text
child_ceiling = parent_ceiling
              & (FILESYSTEM_READ | MEMORY_READ | COMPUTE | AGENT_DATA)
```

如果结果等于父级的上限，`agent.spawn` 会以
`SubagentPolicyError` 失败。因此，即使策略完全相同也会被拒绝。
如果父级没有评估器，spawn 会被拒绝。

每个智能体都有一个 **5 分钟**（`300` 秒）的墙钟超时。该限制是
协作式的：在智能体循环的检查点处检查；不会中断已经进行中的
HTTP 调用。到期时，子级的状态为 `timed_out`，审计会记录
`agent.timed_out`。

每个子级：

- 使用与父级相同的本地模型，但使用独立的 LLM 客户端；
- 拥有独立的注册表；
- 只能看到能力为 `FILESYSTEM_READ`、`MEMORY_READ` 和 `COMPUTE`
  的工具，外加 `AGENT_DATA`；
- 可以在自己的工作区上使用 `vision.open`，但不能使用
  `agent.*` 或 `filesystem.chdir`；
- 只读取自己的工作区；
- 不写入记忆；
- 通过桥接把 ASK 请求转发给用户，超时为
  180 秒，到期即 DENY。

父级 LLM 不能批准 ASK：请求始终发往人工通道（GUI 或控制台）。
桥接会在请求中加上 `agent_id` 和 `parent_id`。

## 2. 私有工作区

每个子级都会创建一个临时工作区：

```text
<hagar-temp>/hagar-subagent-<id>/
```

子级将其视为：

```text
/home/ai/workspace
```

该工作区是只读的。启动之前，管理器会复制父级指定的输入：

```text
agent.spawn(
    task="分析 CSV",
    reason="这些文件相互独立，需要并行分析",
    inputs=["/home/ai/workspace/report.csv"]
)
```

规则：

- 输入必须是父级沙箱中的文件；
- 父级必须具有读取权限；
- 文件名会被保留；
- 两个同名输入属于错误；
- 子级看不到宿主路径；
- 工作区在轮次结束时被删除。

父级只写入自己的工作区。子级的工作区位于父级的根之外，
因此无法通过其工具访问。

## 2.1 Outbox、artifact 与 mailbox

子级不写入工作区。要产出数据，它使用 outbox：

```text
artifact.put(text, kind?, mime_type?)       -> artifact_id
artifact.put_file(path, mime_type?)          -> artifact_id
mailbox.send(text, artifacts?)               -> message
```

`artifact.put_file` 会从子级只读的工作区读取文件，并将其复制到
由 Hagar 管理的存储中。

父级通过以下方式读取：

```text
artifact.list()
artifact.read(artifact_id, offset?, length?)
artifact.save_to(artifact_id, path, overwrite?)
mailbox.inbox(cursor?, limit?)
mailbox.read(message_id)
mailbox.ack(message_id)
```

`artifact.save_to` 会把整个 artifact 复制到父级沙箱中可写的路径，
而不让内容经过上下文。对于大于模型窗口的 artifact，这是应当
使用的操作：模型只读取自己需要的分块，并用 `save_to` 保存完整
文件。

`save_to` 需要 `AGENT_DATA`、`FILESYSTEM_WRITE` 和
`FILESYSTEM_CREATE`；策略会把它视为写入，并可能请求确认。
它不接受任意的宿主路径。

初始限制：

| 元素 | 限制 |
|---|---|
| 单个 artifact | 50 MB |
| 每轮 artifact 总量 | 256 MB |
| 每轮 artifact 数量 | 200 |
| 每次调用读取量 | 256 KB |
| 单条消息文本 | 64 KB |
| 每个 mailbox 的消息数 | 100 |

artifact 是 Vault 之外的临时文件，带有 SHA-256 哈希和元数据。
mailbox 只包含文本和 `artifact_id` 引用。
轮次结束时，存储和 mailbox 都会被清空。

## 3. 实现的限制

- 最多 **2** 个活动子智能体（可在管理器中通过
  `max_concurrent` 配置）；
- 仅支持本地模型；
- 不支持嵌套：子级的注册表排除 `agent.*`；
- 5 分钟墙钟超时，协作式；
- 除 `max_tool_calls` 外没有 token 预算；
- 没有专用 GUI；
- 不写入记忆；
- 子级的 ASK 会转发给用户，超时 180 秒；到期即
  DENY；
- artifact 和 mailbox 是临时的：轮次结束时消失；
- 子级的内部事件（`turn.*`、`tool.*`）在审计中带有
  `agent_id`。

父级轮次结束时：

1. `finish_turn()` 在超时时间内等待子级；
2. 取消仍然活动的子级；
3. 删除工作区；
4. 忘记任务。

## 4. 隔离的组件

| 组件 | 父级 | 子级 |
|---|---|---|
| LLM 客户端 | `harness.llm` | 新实例，同一模型 |
| 工具注册表 | 完整 | 过滤为只读 |
| 文件系统 | 父级工作区 | 私有的只读工作区 |
| 记忆 | `MemoryStore` | `memory=None`，不写入 |
| Artifact/mailbox | 读取 | 子级的 outbox |
| 确认 | 用户 | 通往用户的桥接，超时 180 |
| 用量 | 父级 ledger | 独立的 ledger |
| 审计 | 共享，带锁 | `agent.*` 事件 |

子级没有父级的自动上下文：父级必须传递 `context`。

## 5. 允许的工具

父级必须具有 `AGENT_SPAWN` 和 `COMPUTE` 能力；子级不会获得
`AGENT_SPAWN`，因此无法创建其他智能体。

子级的注册表包含能力是以下集合子集的工具：

```text
FILESYSTEM_READ
MEMORY_READ
COMPUTE
AGENT_DATA
```

子级会获得 `artifact.put`、`artifact.put_file` 和 `mailbox.send`。
它不会获得 `artifact.read`、`artifact.list`、`mailbox.inbox`、
`mailbox.read` 或 `mailbox.ack`：这些属于父级。

以下工具被显式排除：

```text
filesystem.chdir
agent.*
```

按能力排除的有：

- 文件系统写入；
- 创建、重命名、复制、删除；
- 记忆写入；
- 网络；
- MCP；
- shell。

## 6. 审计

管理器记录的事件：

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

父级和子级的所有事件都带有 `agent_id`。注册表和 Agent 的事件
使用执行该动作的智能体的 id；管理器的事件会额外加上
`agent_id` 和 `parent`。
如果 spawn 的策略不是严格更严格的，就会发出
`agent.policy_rejected`。

`artifact.discarded` 会在轮次结束时对每个未通过
`artifact.save_to` 保存的 artifact 发出：

```text
reason=unread                → 从未读取
reason=read_but_not_saved    → 已读取但未导出
```

如果子级的 ASK 在 180 秒内没有响应，就会发出
`confirmation.timeout`；结果是 DENY。GUI 会显示带有
`agent_id`/`parent_id` 的请求，父级无法解决它。

已导出的 artifact 不会产生该事件：文件已经位于父级的工作区中。
内容绝不会写入审计。

`AuditLog.record` 受锁保护，因此并发写入不会交错哈希链。

## 7. 并发

- 子级使用独立的线程；
- 限制 `max_concurrent = 2`；
- 对任务字典加锁；
- 文件系统上没有竞态条件：工作区彼此独立；
- 不共享 `MemoryStore`、沙箱或 LLM 客户端；
- 本地提供方会承受并发请求；
- `agent.wait` 只阻塞调用方，不阻塞其他子级。

## 8. 测试

`tests/test_subagents.py` 覆盖：

- 使用只读工具执行；
- 排除写入和 `agent.*`；
- 传递上下文；
- 把输入复制到私有工作区；
- 超过 `max_concurrent` 时拒绝；
- 两个并发的子智能体；
- 提供方构建错误；
- 审计事件。

已使用 LM Studio 和 `gemma-3-27b-it` 执行实机测试：两个并发的
子智能体完成，各自使用独立的用量。

## 9. 后续步骤

- 从子级的工作区显式导出 artifact；
- token/时间预算和墙钟超时；
- 如有需要，受控嵌套；
- 所有内部事件上的 `agent_id`；
- 把确认委派给父级或 GUI；
- 由 broker 而不是管理器选择模型。
