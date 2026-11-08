# HAGAR — Roadmap

Current version: 0.5.2 (in preparation)
Last updated: 2026-11-07

The decisions already made are marked as such; the points still open are
listed at the end of each area. Sections 1–9 are the history up to
0.5.2; the current operational plan is section 0.

---

# 0. Current plan (post-0.5.2)

## 0.1 Status

Published:

- GitHub release `v0.3.0`;
- Linux/macOS/Windows CI with Python 3.11, 3.12 and 3.13;
- actions updated to Node 24;
- Italian documentation plus translations into English, Spanish, Chinese,
  Russian, Portuguese and Arabic;
- `lmstudio`, `openai`/`chatgpt` backends and `model.timeout`.

Completed after the release, not yet released:

- `HarnessService`: turns, status, projects, events and end of session without
  `input()`/`stdout`;
- `CommandService`: `/help`, `/tools`, `/status`, `/mcp`, `/audit`,
  `/project`, `/memory` with a structured `CommandResult`;
- event bridge `Agent`/`ToolRegistry` → `tool.call`, `tool.result`,
  `permission.*`;
- local web GUI `hagar web` with SSE, chat, projects, status and modal ASK
  confirmations;
- `QueueConfirmationProvider` with timeout and resolution from the GUI;
- `core/usage.py`: token parsing for OpenAI/LM Studio/DeepSeek, Claude,
  Gemini and Ollama; `UsageLedger` per session;
- GUI sidebar with input/output/total tokens updated via
  `usage.updated`;
- `MemoryIndex`: incremental and rebuildable SQLite/FTS5 index;
- SQLite memory as primary source: sessions, turns, skills and summaries;
- `/memory sessions`, `/memory chat`, `/memory backup` commands;
- `memory.search` tool, `/memory search`, `/memory reindex`,
  `/memory stats`;
- GUI assets separated into `web/index.html`, `web/style.css`, `web/app.js`.

## 0.2 Order of the next releases

| Release | Goal | Status |
|---|---|---|
| **0.4.0** | SQLite index of the memories | merged into 0.5.2 |
| **0.4.x** | GUI: turn stop, history, vision | merged into 0.5.2 |
| **0.5.0** | Subagents | merged into 0.5.2 |
| **0.5.2** | Current release | in preparation |
| **0.6.0** | LLM broker | next |
| **0.7.0** | Read-only SQL tool | frozen |

The order may change, but the constraint is: **no subagents without usage and
limits; no broker without subagents and model registry.**

## 0.3 0.4.0 — SQLite index of the memories

Status: implemented; verification on the real Vault and the possible
performance measurement remain.

- location: app local data, not inside the synced Vault;
- schema: notes, skills, decisions, sessions, tags, FTS5;
- incremental sync by path/hash/mtime;
- atomic `rebuild()`, index that can be deleted and rebuilt;
- fallback to lexical search if FTS5 is not available;
- `memory.search` tool with project/kind/status filters;
- `/memory reindex` and `/memory stats`;
- no real path exposed to the model.

Exit criterion: deleting the DB does not lose memory; rebuilding it
returns the same results.

## 0.4 0.4.x — GUI

- **Stop** button for the turn — implemented;
- vision: image upload in the composer, with adapters per provider —
  implemented (OpenAI/LM Studio, Claude, Gemini);
- chat history visible after a refresh — implemented as a list
  of past chats with reload from the Vault, session resume and
  **+ New chat**;
- Chat, Chat history, Tool output, Audit, Thinking and Memories tabs —
  implemented; Audit disables itself if the log is off, Thinking uses the
  reasoning if available and otherwise the timeline;
- read-only memories browser — implemented;
- `/usage` command on the CLI side — implemented;
- tools and LLM providers as plugins with entry points — implemented;
  audit sink postponed.

Vision must not enter the memory as base64: only hash and
description.

## 0.5 0.5.x — Subagents and consolidation

- [x] Synchronous MVP: `AgentSpec`, `agent.run`, read-only tools, read-only
  memory, denied confirmations, `agent.*` audit, separate usage;
- [x] `agent.spawn/status/wait/result/cancel` with threads and up to two
  concurrent subagents;
- [x] private registry and workspace per child, copied inputs and cleanup;
- [x] audit serialized with a lock;
- [x] mandatory `reason` and separate `AGENT_SPAWN` capability;
- [x] artifact store, mailbox and `artifact.put`/`mailbox.send` outbox,
  with `AGENT_DATA` capability and cleanup;
- [x] `artifact.discarded` audit for artifacts not exported;
- [ ] persistence/orphan retention (only if necessary);
- [x] projects and decisions in the same SQLite database;
- [x] Markdown export from the database (`/memory export`);
- [x] Markdown import into the database (`/memory import`);
- [x] FTS5 in the primary database with ranking and snippet;
- [x] 5-minute wall timeout per subagent;
- [x] child policy strictly more restrictive than the parent's;
- [x] `agent_id` in the events of parent, children and registry;
- [x] children's ASKs forwarded to the user with 180-second timeout and DENY;
- [x] `decision.choose` tool with LLM provider and linear classifier;
- [ ] Jev/Kev adapters and automatic classifier training;
- [ ] token/cost budget;
- [ ] `parent_id` on every internal event of the child;
- [ ] `audio.open`/`AudioInput`: the attachment channel is shared with the
  images, but audio-native providers, formats and a different ASR semantics
  are needed; no timeline;
- [x] ASK confirmations from the console with input broker, F5/F8 and GUI fallback;

## 0.6 0.6.0 — LLM broker

- JSON technical cards and model benchmarks (`/models test`);
- CPU/RAM/GPU hardware detection (`/models hardware`);
- `ModelRegistry` with context window, tool calling, prices, latency and
  locality;
- `TaskProfile` with required tools, data sensitivity, budget and context;
- rule/score routing, not "an LLM chooses the model";
- `AgentSpec` proposal validated by the host;
- the broker never grants permissions: it can only propose a subset;
- human override and `broker.decision` audit.

## 0.7 0.7.0 — SQL tool

- read-only in the first version;
- SQLite `mode=ro`, `PRAGMA query_only`, a single statement;
- no `ATTACH`, writing `PRAGMA` or `load_extension`;
- timeout, row/byte limit and query audit;
- configured database aliases, never arbitrary paths;
- `DATABASE_READ` capability;
- writing and network databases only in a later phase, with
  `DATABASE_WRITE` and `NETWORK`.

## 0.8 Open points

- release workflow idempotent if the release already exists;
- PyPI: postponed, it does not block 0.4;
- MCP OAuth Atlassian: Basic works, the OAuth flow remains to be
  validated;
- MCP/OAuth and remote provider live tests;
- translation maintenance: they are regenerated only at release, not on
  every commit;
- Vault concurrency and atomic writes: to be evaluated before
  subagents with shared memory;
- document tool: contract and protocol defined in `DOCUMENT_TOOL.md`;
  CSV MVP still to be implemented.

## 0.9 Documentation

`Docs/it` is the only source maintained during development. The
`Docs/en`, `Docs/es`, `Docs/zh`, `Docs/ru`, `Docs/pt` and `Docs/ar` directories are
regenerated only when preparing a release.

---

# 1. Direction

Hagar has gone from "idea" to "working system" (v0.1) and then to a
harness with audit, multiple backends and a test suite (v0.2 in progress). The
next leap is not adding tools: it is giving the system a **memory** and
a way of calling tools that is less fragile than textual JSON.

Decided order:

1. memory on Vault;
2. native calling for the providers that support it;
3. PermissionEvaluator — **v1 done** (policy.yaml, ASK, audit);
4. hygiene (audit, MCP, packaging, live tests).

---

# 2. Priority 1 — Memory on Vault

## 2.0 Status: v2 implemented (2026-11-04)

Done:

- episodic written by the harness, one note per session;
- automatic injection of the last `context_turns` turns;
- `memory.create_skill`, `memory.list_skills`, `memory.get_context` tools;
- provenance (`source_session`, `source_turn`, `model`), `candidate` state,
  deduplication by slug;
- `MEMORY_READ`/`MEMORY_WRITE` policy and `chat` / `skills` namespace;
- missing vault → memory disabled with a warning, harness active;
- lifecycle `candidate` → `confirmed` → `archived` with human review
  from the CLI (`/memory review`, `confirm`, `archive`);
- automatic injection of confirmed skills only, top 3 by lexical
  match;
- retention option A: no automatic deletion, archive only;
- project memory separate from skills: decisions, alternatives,
  rationales, state and provenance;
- project selection at start-up, `--project`/`--free`, `/project`
  commands;
- end-of-session summary with fallback, transcript in `archive/chat/`
  and link/hash in the summary;
- review of the decisions at the end of the session; if refused, they remain
  `candidate` with `auto_saved: true`;
- index-based context with `max_context_chars` budget (characters, not
  tokens) and `memory.project_context` for the details;
- `project_max_active` for the project archiving request;
- archive consultation with `memory.archive_search`,
  `memory.archive_read`, `/memory archive search|read`, filter by
  project and transcript with `project` in the frontmatter.

Remaining: chat retention, semantic search, GUI.

## 2.1 Decisions made

- **Episodic written by the harness.** Chat turns are recorded
  by the harness by default: it is a mechanical record, not a judgement of the
  model. No missing turn, no invented memory.
- **Semantics written by the LLM, on request.** The model can propose
  a memory (skill) only through a dedicated tool. The proposal is
  explicit, attributable and reviewable — the First Law forbids
  treating it as truth.
- **Obsidian Vault only.** No writing to the real filesystem for the
  memory (for now). `filesystem.sandbox` remains the operational sandbox.
- **The Vault is not rewritten.** The tools add notes or sections; they do not
  overwrite notes curated by the user.
- **Explicit projects.** The project is chosen at start-up from the list
  of active projects, or with `--project`; `--free` and "free
  activity" have no project memory.
- **Project decisions.** They are separate from skills: they record
  decisions, alternatives and rationales. They are proposed as `candidate`
  and reviewed at the end of the session; if the review is refused they remain
  candidate with `auto_saved: true`, they do not become automatic truth.
- **No token quotas.** The context is limited by construction:
  project index, decision titles, summary and
  `max_context_chars` in characters. The model's context window is not
  measured.
- **Archive, not deletion.** Archived transcripts and decisions
  remain in the Vault; archiving a project is reversible.

## 2.2 Planned tools

Names implemented in the `memory.*` namespace:

| tool | who calls it | what it does |
|---|---|---|
| `memory.create_skill` | LLM | creates a **candidate** semantic memory |
| `memory.list_skills` | LLM | lists the available memories |
| `memory.get_context` | LLM | retrieves past chat turns |

Implemented signatures:

```text
memory.create_skill(title, content, kind="procedure", tags=None)
    -> {id, title, kind, status, tags, created_at, source_*, path, duplicate}

memory.list_skills(kind=None, status=None, limit=20)
    -> [{id, title, kind, status, tags, created_at, source_*}]

memory.get_context(limit=5, query=None, session=None)
    -> [{session, turn, timestamp, question, answer}]
```

Behaviours:

- `create_skill`: slug from the title, deduplication by slug, length limit
  (`max_skill_chars`), frontmatter with `status: candidate`,
  `source_session`, `source_turn`, `model`, `created_at`; if an
  equal slug already exists it returns the existing id instead of duplicating.
- `list_skills`: reads frontmatter and body (needed for recall), filterable
  by `kind` (`fact` / `procedure`) and `status`.
- `get_context`: without `session` it searches all sessions; with `query`
  it searches by keywords in the past turns; `limit` is clamped to
  1..50 so as not to pour the whole Vault into the context.

## 2.3 Structure in the Vault

```text
<Vault>/Hagar/
  chat/2026-11-03-<session>.md      # one note per session, turns appended
  skills/<slug>.md                  # one note per memory
```

Episodic (one note per session, turns appended at the end):

```markdown
---
session: a1b2c3d4
type: chat
created: 2026-11-03T00:12:44+01:00
---

# Chat 2026-11-03

## 2026-11-03T00:12:44+01:00 · 7f3a

**User:** ...
**Hagar:** ...
```

Semantics (one note per skill):

```markdown
---
id: usa-uv-per-python
title: Using uv for Python projects
kind: procedure
status: candidate
tags: [python, tooling]
source_session: a1b2c3d4
source_turn: 7f3a
model: llama3.1:latest
created_at: 2026-11-03T00:15:02+01:00
---

Steps / content proposed by the model.
```

## 2.4 Configuration

```yaml
vault:
  path: <real path>

memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  max_skill_chars: 4000
```

## 2.5 Harness behaviour

- At the end of the turn: adds question and answer to the session note (conversation
  only, **not** tool output: those remain in the audit).
- At the beginning of the turn: injects the last `context_turns` turns and up to
  `context_skills` relevant **confirmed** skills (lexical match),
  without waiting for the model to call `get_context`.
- Every memory write or review produces an audit event
  (`memory.enabled`, `memory.disabled`, `memory.context`, `memory.turn`,
  `memory.review`, `memory.status`, `memory.failed`); a missing or
  non-writable Vault does not stop the harness.
- Episodic memory is separate from the audit: the audit remains forensic and
  also contains the tool data.

## 2.6 Open points

- **Chat retention**: how many sessions to keep, whether to summarize the
  old ones; 0.2.0 deletes nothing.
- **Search**: index (SQLite FTS) or embedding when the volumes
  grow; today it is by keyword.
- **GUI**: ASK confirmation with a modal dialog also for the memory
  writes and for the review.
- **Context selection**: today global recent turns, project index
  and top 3 confirmed skills by lexical match, without
  semantic relevance.
- **Decision consolidation**: the project can exceed
  `project_max_active`; today Hagar proposes archiving, not the
  merge of duplicate decisions.

## 2.7 Non-goals (for now)

- writing memories to the real filesystem;
- modifying existing notes of the user;
- embedding / ChromaDB / semantic search (later, if the volumes
  justify it);
- autonomous writing of memories outside the explicit flow.

---

# 3. Priority 2 — Native calling (v1, done)

**Status:** implemented on 2026-11-03. `native_step()` for the four
providers, parameter schema from `ToolDefinition`, canonical `tool`
messages, multiple calls per turn, automatic fallback on HTTP 400/404/422
and `--no-native-tools`. Verified live on Ollama and DeepSeek; Claude and
Gemini remain to be tried. Measured with `tools/bench_native.py`: no
protocol wins on all models (native faster, text sometimes more
accurate). It remains to be refined for the local models that ignore the tools.

## 3.1 Goal

Eliminate the fragility of the textual JSON protocol: no more
repairs, arguments validated by the provider schema, structured
results.

## 3.2 Approach

- Keep the textual protocol as a **fallback** for the models that
  do not support native calling or do it badly.
- Add to `LLMClient` a declared capability
  (`supports_native_tools`) and a native path.
- The `Agent` must handle both: textual `ToolCall` or native
  call with id; the result goes back in the format expected by the provider.
- The benchmark measures the improvement (repairs per turn,
  correctness of the arguments).

## 3.3 Transport per provider

| provider | request | tool result |
|---|---|---|
| `ollama` | `tools` in `/api/chat` | message with `tool` role |
| `deepseek` | `tools` (OpenAI) | `tool` role + `tool_call_id` |
| `claude` | `tools` + `tool_use` blocks | `tool_result` block |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 3.4 Risks

- Small local models often do not use native calling well: the automatic
  fallback is needed.
- The message plumbing changes: tests per provider and per the fallback
  path are mandatory.
- Some models return multiple calls in the same turn: the Agent
  executes them all, within the turn limit.

---

# 4. Priority 3 — PermissionEvaluator

## 4.1 Status: v1 implemented

Done:

- `Capability`, `Effect`, `Rule`, `Subject`, `Resource`, `Decision` and
  `PermissionEvaluator` in `core/permissions.py`;
- `policy.yaml` read **before** the LLM, with fallback to total `DENY` and
  warning on audit and chat;
- system ceiling derived from `permissions.read/write/shell`;
- scope by `tools` (glob), `paths` and `namespaces` (prefixes);
- `ASK` with `ConsoleConfirmation` (`shall I do it? (y/N)`, default N);
- enforcement in `ToolRegistry.execute` and audit of
  `permission.decision` / `permission.confirmation`;
- `ToolDefinition.capabilities` for all tools (filesystem and MCP);
- `requires_confirmation` applied as an ASK floor;
- 347 tests collected, 1 skipped.

## 4.2 Still to do

- `ConfirmationProvider` for the GUI (modal dialog) and for non-interactive
  execution (deny by default);
- dynamic policies per task/role, with runtime reduction only (an
  agent can reduce its permissions, never widen them by itself);
- capabilities of MCP tools assigned by the configuration, not
  declared by the server;
- multiple subjects executing at the same time (multiple agents with
  different policies);
- resource objects for memory and paths, not only tools.

---

# 5. Priority 4 — AIsh

Shell dedicated to LLMs, conceptually similar to Bash but without any
access to the real shell:

- no execution of host commands;
- exclusive use of registered tools;
- simulated filesystem and virtual paths (`workspace://`);
- integration with MCP tools;
- pipes and virtual commands.

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```

Virtual paths would also solve the exposure of the absolute paths
of the sandbox.

---

# 6. Hygiene and robustness

Done (2026-11-03):

- **MCP**: `text/event-stream` responses, `notifications/initialized`
  notification, normalization of the results to text
  (`text` blocks, `structuredContent`, `isError` errors).
- **MCP auth**: bearer or custom header, token only from the environment,
  server skipped with `mcp.failed` if the token is missing.
- **MCP OAuth**: authorization code + PKCE flow with browser, RFC 9728/8414
  discovery, dynamic registration, token cache, refresh and 401 retry.
- **Audit**: rotation at `max_bytes`, hash chain verifiable with
  `verify_chain`, redaction of the tool output with
  `include_outputs: false`.
- **Audit retention**: timestamped backups and `audit.max_files` (default
  100, includes the active file) with pruning of the oldest.
- **Live tests**: `live` marker, excluded by default, `--live` for Ollama
  and remote providers (the latter skipped without a key).
- **Packaging**: complete metadata, `hagar` entry point, `--config`,
  `--model`, `--no-memory`, `--version`, single version.
- **Base URL**: `model.host` applies to all providers.
- **Legacy**: removed `tools/filesystem.py` and `llm/tool_result.py`.

Remaining:

- device flow / DPoP for MCP OAuth;
- compaction of the audit sessions;
- GUI confirmations for `ASK`;
- continuous alignment of the documentation.

---

# 7. Later

- semantic search on the Vault (index, then possibly ChromaDB);
- RAG on the documents;
- activity management and persistent scratchpad;
- vault observation (notes modified by the user);
- permanent personal agent;
- additional providers (OpenAI is almost free: same client as DeepSeek
  with a different base URL).

---

# 8. Work order

1. Memory v2: done (lifecycle, CLI review, injection of confirmed ones);
   chat retention, semantic search and GUI remain.
2. PermissionEvaluator: v1 done; GUI confirmations and dynamic policies
   remain.
3. Hygiene: done (packaging, live tests, MCP auth/OAuth, audit with
   retention, base URL, legacy).
4. Native calling: v1 done; the benchmark measurement remains.
5. Release 0.3.0: prepared for GitHub, with multi-platform CI and
   release workflow.

---

# 9. Local tools

Status as of 2026-11-05:

- filesystem v2: `list_dir`, `read_chunk`, `rename`, `copy_file`,
  `search`, in addition to the existing tools;
- `local_tools/`: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `feed.read` (local providers, not MCP servers);
- capability `COMPUTE` always in the ceiling, `NETWORK` controlled by
  `permissions.network` and by the policy (feed in `ask`);
- write limits: `max_write_bytes`, `min_free_bytes`,
  `session_write_bytes` and `ask_over_bytes` with a single preflight;
- `feed.read` with SSRF policy: global addresses only, redirects
  revalidated, no credentials in the URL;
- filesystem with virtual root `/home/ai`, mandatory aliases and
  per-mount permissions (`R`/`W`/`X`);
- POSIX runner `tools/run_tests.sh` alongside the Windows one.

Open points:

- DNS rebinding: the resolution is validated, but `requests` resolves
  the name again at connection time; a pinned resolver or a dedicated
  adapter is needed to close the case;
- the calculator is deliberately limited (no symbolic algebra);
- evaluate a size limit also for the other tool outputs.

Closed as user responsibility:

- hard links, mounts and junctions inside the allowed directories are not
  checked by Hagar. For total isolation the user must guarantee
  that there are none; Hagar does not create them and does not detect them;
- TOCTOU race: Hagar does not use `openat2`, `O_NOFOLLOW` on every component or
  Windows handles and does not guarantee atomicity between check and operation. The
  race requires a concurrent local process with write access;
  it is a malicious scenario or one of compromised environment, not normal use.
  For total isolation a dedicated volume, a separate user, a mount
  namespace or a container are needed.
