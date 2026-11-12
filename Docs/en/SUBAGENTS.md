# Subagents — asynchronous phase

**Status:** implemented
**Date:** 2026-11-07  
**Tools:** `agent.spawn`, `agent.status`, `agent.wait`, `agent.result`,
`agent.cancel`, `agent.run` (synchronous compatibility), `artifact.*`,
`mailbox.*`

## 1. What they do

The model can start up to two concurrent subagents:

```text
agent.spawn(task, reason, context?, inputs?) -> agent_id
agent.status(agent_id) -> state
agent.wait(agent_id, timeout?) -> result
agent.result(agent_id) -> result
agent.cancel(agent_id) -> ok
```

`spawn` returns immediately. The parent can keep working and collect
the results when needed. `agent.run` remains as a `spawn + wait`
shortcut for compatibility.

`reason` is mandatory: it is recorded in the audit and is the reason
why the parent delegates the work. The tool requires the `AGENT_SPAWN`
capability; the child does not receive it, so it cannot create others.
`permissions.agents: true` is the necessary system ceiling.

The child's policy must be **strictly more restrictive** than
the parent's. The manager computes:

```text
child_ceiling = parent_ceiling
              & (FILESYSTEM_READ | MEMORY_READ | COMPUTE | AGENT_DATA)
```

If the result is equal to the parent's ceiling, `agent.spawn` fails with
`SubagentPolicyError`. Therefore even identical policies are refused.
If the parent has no evaluator, the spawn is refused.

Every agent has a **5-minute** (`300` seconds) wall timeout. The
limit is cooperative: it is checked at the checkpoints of the agent loop;
it does not interrupt an HTTP call already in progress. On expiry the
child's state is `timed_out` and the audit records `agent.timed_out`.

Every child:

- uses the same local model as the parent, but a separate LLM client;
- has a separate registry;
- sees only the tools with the `FILESYSTEM_READ`,
  `MEMORY_READ` and `COMPUTE` capabilities, plus `AGENT_DATA`;
- can use `vision.open` on its own workspace, but not
  `agent.*` or `filesystem.chdir`;
- reads only its own workspace;
- does not write to memory;
- forwards ASK requests to the user through a bridge, with a 180-second
  timeout and DENY on expiry.

The parent LLM cannot approve an ASK: the request always goes to the human
channel (GUI or console). The bridge adds `agent_id` and `parent_id` to the
request.

## 2. Private workspace

For every child a temporary workspace is created:

```text
<hagar-temp>/hagar-subagent-<id>/
```

The child sees it as:

```text
/home/ai/workspace
```

The workspace is read-only. Before start-up, the manager copies the
inputs indicated by the parent:

```text
agent.spawn(
    task="analyse the CSV",
    reason="the files are independent and must be analysed in parallel",
    inputs=["/home/ai/workspace/report.csv"]
)
```

Rules:

- the inputs must be files in the parent's sandbox;
- the parent must have read permission;
- the file name is preserved;
- two inputs with the same name are an error;
- the child does not see the host path;
- the workspace is deleted at the end of the turn.

The parent writes only in its own workspace. The child's workspace is
outside the parent's roots, so it is not reachable by its tools.

## 2.1 Outbox, artifacts and mailbox

The child does not write in the workspace. To produce data it uses the outbox:

```text
artifact.put(text, kind?, mime_type?)       -> artifact_id
artifact.put_file(path, mime_type?)          -> artifact_id
mailbox.send(text, artifacts?)               -> message
```

`artifact.put_file` reads a file from the child's read-only workspace and
copies it into the store managed by Hagar.

The parent reads with:

```text
artifact.list()
artifact.read(artifact_id, offset?, length?)
artifact.save_to(artifact_id, path, overwrite?)
mailbox.inbox(cursor?, limit?)
mailbox.read(message_id)
mailbox.ack(message_id)
```

`artifact.save_to` copies the whole artifact to a writable path of the
parent's sandbox without letting the content pass through the context. It is
the operation to use for artifacts larger than the model's window:
the model reads only the chunks it needs and saves the complete file
with `save_to`.

`save_to` requires `AGENT_DATA`, `FILESYSTEM_WRITE` and
`FILESYSTEM_CREATE`; the policy treats it as a write and can
ask for confirmation. It does not accept arbitrary host paths.

Initial limits:

| Element | Limit |
|---|---|
| single artifact | 50 MB |
| total artifacts per turn | 256 MB |
| artifacts per turn | 200 |
| read per call | 256 KB |
| text of a message | 64 KB |
| messages per mailbox | 100 |

The artifacts are temporary files outside the Vault, with SHA-256 hash and
metadata. The mailbox contains only text and `artifact_id` references.
At the end of the turn the store and the mailbox are emptied.

## 3. Implementation limits

- maximum **2** active subagents (configurable in the manager as
  `max_concurrent`);
- local models only;
- no nesting: the child's registry excludes `agent.*`;
- 5-minute wall timeout, cooperative;
- no token budget beyond `max_tool_calls`;
- no dedicated GUI;
- no memory writes;
- child ASKs forwarded to the user with a 180-second timeout; on
  expiry DENY;
- artifacts and mailbox are ephemeral: they disappear at the end of the turn;
- the child's internal events (`turn.*`, `tool.*`) have `agent_id` in
  the audit.

At the end of the parent's turn:

1. `finish_turn()` waits for the children for a timeout;
2. cancels those still active;
3. deletes the workspaces;
4. forgets the jobs.

## 4. Isolated components

| Component | Parent | Child |
|---|---|---|
| LLM client | `harness.llm` | new instance, same model |
| Tool registry | complete | read-only filtered |
| Filesystem | parent workspace | private read-only workspace |
| Memory | `MemoryStore` | `memory=None`, no writes |
| Artifact/mailbox | reading | child outbox |
| Confirmations | user | bridge to the user, timeout 180 |
| Usage | parent ledger | separate ledger |
| Audit | shared, with lock | `agent.*` events |

The child does not have the parent's automatic context: the parent must pass
`context`.

## 5. Allowed tools

The parent must have the `AGENT_SPAWN` and `COMPUTE` capabilities; the child
does not receive `AGENT_SPAWN` and therefore cannot create other agents.

The child's registry includes the tools whose capabilities are a
subset of:

```text
FILESYSTEM_READ
MEMORY_READ
COMPUTE
AGENT_DATA
```

The child receives `artifact.put`, `artifact.put_file` and `mailbox.send`.
It does not receive `artifact.read`, `artifact.list`, `mailbox.inbox`,
`mailbox.read` or `mailbox.ack`: those belong to the parent.

Explicitly excluded:

```text
filesystem.chdir
agent.*
```

Excluded by capability:

- filesystem writing;
- creation, renaming, copying, deletion;
- memory writing;
- network;
- MCP;
- shell.

## 6. Audit

Events recorded by the manager:

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

Main fields:

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

All the events of the parent and of the children carry `agent_id`. The events
of the registry and of the Agent use the id of the agent that performed
the action; the manager events add `agent_id` and `parent`.
`agent.policy_rejected` is emitted if the spawn does not have a strictly
more restrictive policy.

`artifact.discarded` is emitted at the end of the turn for every artifact not
saved with `artifact.save_to`:

```text
reason=unread                → never read
reason=read_but_not_saved    → read but not exported
```

`confirmation.timeout` is emitted if the child's ASK remains without an
answer for 180 seconds; the outcome is DENY. The GUI shows the request with
`agent_id`/`parent_id` and the parent cannot resolve it.

The exported artifacts do not produce the event: the file is already in the
parent's workspace. The content is never written to the audit.

`AuditLog.record` is protected by a lock, so concurrent writes do not
interleave the hash chain.

## 7. Concurrency

- separate threads for the children;
- `max_concurrent = 2` limit;
- lock on the job dictionary;
- no race condition on the filesystem: separate workspaces;
- no sharing of `MemoryStore`, sandbox or LLM client;
- local provider with concurrent requests;
- `agent.wait` blocks only the caller, not the other children.

## 8. Tests

`tests/test_subagents.py` covers:

- execution with read-only tools;
- exclusion of writing and `agent.*`;
- context passing;
- copying of the inputs into the private workspace;
- refusal beyond `max_concurrent`;
- two concurrent subagents;
- provider construction error;
- audit events.

Live test run with LM Studio and `gemma-3-27b-it`: two concurrent
subagents completed, each with separate usage.

## 9. Next steps

- explicit export of the artifacts from the child's workspace;
- token/time budget and wall timeout;
- controlled nesting, if required;
- `agent_id` on all internal events;
- confirmations delegated to the parent or to the GUI;
- model chosen by the broker, not by the manager.
