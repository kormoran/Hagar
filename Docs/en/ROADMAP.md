# HAGAR — Roadmap

Current version: 0.7.0 (in development)
Last updated: 2026-11-09

The decisions already made are marked as such; the points still open are
listed at the end of each area. Sections 1–9 are the history up to
0.6.0; the current operational plan is section 0.

---

# 0. Current plan (post-0.6.0)

## 0.1 Order of the next releases

| Release | Goal | Status |
|---|---|---|
| **0.6.0** | Runtime safety + AIsh | released |
| **0.7.0** | dev.run + box + Hagar Flow | in development |
| **0.8.0** | LLM broker | next |
| **0.9.0** | Read-only SQL tool | frozen |

The order may change, but the constraint is: **no subagents without usage and
limits; no broker without subagents and model registry.**

## 0.1.1 0.7.0 — Local orchestration

- `dev.run` with trusted recipes outside the sandbox;
- `box.list` and `box.run` for bounded LLM transformations;
- `flow.run`, `flow.validate` and `flow.reference`;
- list comprehension with a single `for`;
- read-only memory primitives: `memory.search`, `memory.context`,
  `memory.skill` and `project.context`;
- explicit repair with `flow.repair`;
- no container mode in this release.

## 0.2 0.8.0 — LLM broker

- JSON technical cards and model benchmarks (`/models test`);
- CPU/RAM/GPU hardware detection (`/models hardware`);
- `ModelRegistry` with context window, tool calling, prices, latency and
  locality;
- `TaskProfile` with required tools, data sensitivity, budget and context;
- rule/score routing, not "an LLM chooses the model";
- `AgentSpec` proposal validated by the host;
- the broker never grants permissions: it can only propose a subset;
- human override and `broker.decision` audit.

## 0.3 0.8.0 — SQL tool

- read-only in the first version;
- SQLite `mode=ro`, `PRAGMA query_only`, a single statement;
- no `ATTACH`, writing `PRAGMA` or `load_extension`;
- timeout, row/byte limit and query audit;
- configured database aliases, never arbitrary paths;
- `DATABASE_READ` capability;
- writing and network databases only in a later phase, with
  `DATABASE_WRITE` and `NETWORK`.

## 0.4 Open points

- release workflow idempotent if the release already exists;
- PyPI: postponed;
- MCP OAuth Atlassian: Basic works, the OAuth flow remains to be
  validated;
- MCP/OAuth and remote provider live tests;
- translation maintenance: they are regenerated only at release, not on
  every commit;
- document tool: contract and protocol defined in `DOCUMENT_TOOL.md`;
  CSV MVP still to be implemented.

## 0.4.1 Complete filesystem version — frozen

Implemented now:

- `edit_file` with atomic write;
- turn checkpoint and `/undo`;
- per-tool timeout and repeat guard;
- output spill and context compaction.

The implemented MVP covers `edit_file`, atomic write,
read-before-overwrite/delete/rename and `mtime_ns+size` versioning.
The complete version is frozen; it does not enter the next release:

- `edit_file` with multi-hunk patch and diff;
- content hash in addition to `mtime_ns`/`size`;
- atomic write with filesystem-level CAS check;
- per-agent observation with explicit isolation between parent and
  subagents;
- audit `fs.observed`, `fs.guard_denied`, `fs.stale`;
- coverage of directory rename/delete;
- GUI integration and guided recovery messages.

## 0.4.2 AIsh — implemented in 0.6.0

`aish.exec` is a semantic shell on top of the Hagar tools, with a `DENY`
policy by default. Implemented commands: navigation, reading, plain text,
pipelines and single-file mutations. It does not execute host programs,
redirections, variables or command substitution.
`text.transform` provides the bounded text operations used by AIsh.

## 0.4.3 dev.run — implemented

`dev.list` and `dev.run` execute trusted recipes for tests, debugging and builds.
`recipes.yaml` lives outside the sandbox, is read at start-up and has no
hot reload. `DEV_EXEC` is DENY by default; the backend is host only.

The container remains frozen for future direct access to
real filesystems/programs, never inside the sandbox.

## 0.4.4 Boxed transform — implemented

`box.list` and `box.run` execute `summarize`, `translate` and
`extract_json` with a fixed prompt, file input/output and no memory
or tools. `BOX_EXEC` is DENY by default.

They are the primitives of the future DSL.

## 0.4.5 Hagar Flow — MVP

`flow.run` executes a linear subset of Python with an AST validator and
a Hagar interpreter, without `eval`/`exec`. Primitives `fs.*` and `box.*`, limits
on steps and tool calls. `FLOW_EXEC` is DENY by default.

HIR, parallelism and subagents remain outside the MVP.

## 0.5 Documentation

`Docs/it` is the only source maintained during development. The
`Docs/en`, `Docs/es`, `Docs/zh`, `Docs/ru`, `Docs/pt` and `Docs/ar` directories are
regenerated only when preparing a release.

---

## 1.0 Status: v2 implemented (2026-11-04)

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

## 1.1 Decisions made

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

## 1.2 Planned tools

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

## 1.3 Structure in the Vault

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

## 1.4 Configuration

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

## 1.5 Harness behaviour

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

## 1.6 Open points

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

## 1.7 Non-goals (for now)

- writing memories to the real filesystem;
- modifying existing notes of the user;
- embedding / ChromaDB / semantic search (later, if the volumes
  justify it);
- autonomous writing of memories outside the explicit flow.

---

## 2 Goal

Eliminate the fragility of the textual JSON protocol: no more
repairs, arguments validated by the provider schema, structured
results.

## 2.1 Approach

- Keep the textual protocol as a **fallback** for the models that
  do not support native calling or do it badly.
- Add to `LLMClient` a declared capability
  (`supports_native_tools`) and a native path.
- The `Agent` must handle both: textual `ToolCall` or native
  call with id; the result goes back in the format expected by the provider.
- The benchmark measures the improvement (repairs per turn,
  correctness of the arguments).

## 2.2 Transport per provider

| provider | request | tool result |
|---|---|---|
| `ollama` | `tools` in `/api/chat` | message with `tool` role |
| `deepseek` | `tools` (OpenAI) | `tool` role + `tool_call_id` |
| `claude` | `tools` + `tool_use` blocks | `tool_result` block |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 2.3 Risks

- Small local models often do not use native calling well: the automatic
  fallback is needed.
- The message plumbing changes: tests per provider and per the fallback
  path are mandatory.
- Some models return multiple calls in the same turn: the Agent
  executes them all, within the turn limit.

---

# 3. Priority 3 — PermissionEvaluator

Status: v1 implemented

## 3.1 Still to do

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
- **Base URL**: `model.host` applies to all providers.

Remaining:

- device flow / DPoP for MCP OAuth;
- compaction of the audit sessions;
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
