# HAGAR — Architecture

Version: 0.5.2
Last updated: 2026-11-03

---

# 1. What Hagar is

Hagar is a harness for LLMs written in Python, designed for the
resilient execution of language models.

The goal is not a chat with a model, but an operating environment
that is **safe** and in which an LLM can use tools, consult a persistent
memory and interact with external systems without directly accessing
the real resources of the host machine.

To this end the project applies principles from HMI/HCI and Cognitive
Ergonomics to the design of the environment in which the model operates.

## 1.1 The Four Laws of HAGAR

**First law — An LLM is not trustworthy by definition.**
Not because it is evil or useless: because it is probabilistic. Every
statement of its must be verified and every action of its must be limited.

**Second law — Tools are more reliable than the LLM.**
If the filesystem says a file exists, it exists. If the tool returns
a size, that size is real. The LLM interprets, tools
measure.

**Third law — State must exist outside the LLM's mind.**
ToolRegistry, MCP, FileSystemSandbox and (prospectively)
PermissionEvaluator move knowledge and control outside the model,
as in safety-critical systems.

**Fourth law — Every action must be explainable afterwards.**
The audit log answers the right question: not "why did the LLM go crazy?"
but "what assumption did it make?", "which tool did it use?", "which data was
wrong?". Incident investigation, as in aviation.

## 1.2 Absolute prohibitions

The model must never:

- access the host filesystem directly;
- execute commands on the real shell;
- obtain privileges higher than those defined by the configuration;
- know the actual organization of the operating system.

All operations pass exclusively through tools registered and
controlled by the harness.

## 1.3 Architectural principles

- separation between model and operating system;
- security by default;
- plugin architecture;
- independence from the LLM provider;
- extensibility through tools and the MCP protocol.

---

# 2. Architecture

```text
User
  │
  ▼
Agent ──────────────── AuditLog (JSON Lines)
  │
  ├── LLMClient (llm/base.py)
  │     ├── OllamaClient
  │     ├── LMStudioClient
  │     ├── DeepSeekClient
  │     ├── OpenAIClient
  │     ├── ClaudeClient
  │     └── GeminiClient
  │
  ├── ToolRegistry
  │     ├── filesystem.*
  │     ├── memory.*        (planned)
  │     └── mcp.*
  │
  ├── FileSystemSandbox
  │
  ├── MCPClient
  │
  └── Vault (Obsidian)
```

Execution flow:

```text
User
  ↓
Agent              turn.start
  ↓
LLMClient          llm.tool_choice
  ↓
ToolCall
  ↓
ToolRegistry       tool.call
  ↓
ToolResult         tool.result
  ↓
LLMClient
  ↓
Final answer       turn.answer
```

---

# 3. Components

## 3.1 Config (`core/config.py`)

Loads and validates a YAML file (`hagar.yaml`) into an `AppConfig`.

Sections:

| section | mandatory | content |
|---|---|---|
| `model` | yes | provider, name, host, timeout, max_tokens, api_key_env, native_tools |
| `vault` | yes | path of the Obsidian vault |
| `filesystem` | yes | `sandbox`: list of `{alias, path, permissions}`; `limits`: write budget |
| `permissions` | no | read, write, shell, network (default `true/false/false/false`) |
| `rag` | no | `top_k` (default 8) |
| `mcp_servers` | no | endpoint, namespace, auth (bearer/header/oauth) |
| `audit` | no | enabled, path, max_field_chars, max_bytes, max_files, include_outputs |
| `policy` | no | path of the policy file, subject |
| `memory` | no | enabled, vault_subdir, context_turns, context_skills, max_skill_chars |

Validation errors always produce `ConfigError`, with a message that
indicates the field. The audit path, if relative, is resolved
relative to the configuration file.

## 3.2 LLM interface and backends (`llm/`)

`LLMClient` has two paths:

- **native calling** (default): `native_step()` sends the tool
  schemas in the provider's format and reads the calls from the response;
- **textual JSON protocol** (fallback): `request_tool_call()` asks for a
  JSON with `tool`/`arguments`, with robust parsing and one repair
  attempt.

The parameter schema is built from `ToolDefinition`:
OpenAI/Ollama use `tools[].function`, Claude `tools[].input_schema`,
Gemini `functionDeclarations`. The canonical conversation uses the roles
`user`/`assistant`/`tool`; each client translates it (OpenAI `tool_calls`,
Claude `tool_use`/`tool_result` blocks, Gemini `functionCall`/
`functionResponse`). An HTTP 400/404/422 refusal produces
`NativeToolsUnavailable`: the Agent switches to the textual protocol only if it has
not yet executed any tool.

Tool names are normalized for the APIs that do not allow the
dot (`filesystem.read_file` → `filesystem__read_file`) and mapped back to the
internal name in the response: policy, audit and tests always see the
original name.

Text remains the fallback for models that do not support native tools;
`model.native_tools: false` forces it (or `--no-native-tools` from the CLI).

| provider | API | key | notes |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | default host `localhost:11434` |
| `lmstudio` | `/v1/chat/completions` (OpenAI) | optional `LMSTUDIO_API_KEY` | default host `localhost:1234/v1` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | inline system |
| `openai` / `chatgpt` | `/v1/chat/completions` | `OPENAI_API_KEY` | ChatGPT via API, not subscription |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | separate system, alternating turns |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, `model` role |

The key is read only from the environment; `model.api_key_env` overrides the
default name. `model.host` is the base URL of all providers (with a
default per provider), `model.timeout` is the HTTP timeout (default 120),
`model.max_tokens` is used only by Claude.
`llm/factory.py` builds the client and rejects unknown providers or
missing keys. The built-in providers are specs in `llm/plugins.py`; an
external provider registers itself with the `hagar.llm` entry point and a factory
`(config, audit) -> LLMClient` (see `PLUGINS.md`). LM Studio does not
require a key unless the server is configured that way; OpenAI requires an
API key, not a ChatGPT subscription.
DeepSeek: the current models are `deepseek-flash` and
`deepseek-v4-pro`; `deepseek-chat` is no longer accepted.

Current state: **native calling v1** with automatic textual fallback
(see ROADMAP).

## 3.3 Tool model (`core/tool_*.py`)

`ToolDefinition` describes name, description, category, parameters,
handler, `origin` (`local` or `mcp.<namespace>`), the declared
`capabilities`, the enabling state and `requires_confirmation`
(ASK floor applied by the registry).

`ToolCall` is the model's request (`tool`, `arguments`, `id`);
`ToolResult` is the structured outcome (`tool_name`, `success`, `output`,
`error`).

`ToolRegistry` registers, looks up, enables/disables and executes the tools;
it exposes the metadata to the model and is the only execution point.

## 3.4 Agent (`core/agent.py`)

Multi-step agentic loop, with two paths:

- **native**: a response may contain multiple calls; the Agent re-queues
  the `assistant` message and a `tool` message with the id for each
  result;
- **textual**: one call at a time, with the result sent as a
  `user` turn.

In both:

1. the model decides whether a tool is needed;
2. if not, the final answer closes the turn;
3. if so, the tool is executed and the result goes back to the model;
4. the `max_tool_calls` limit applies to the whole turn. If the model
   insists, the turn closes with `Agent stopped after N tool calls`
   (loop protection).

If the first native step fails with `NativeToolsUnavailable`, the Agent
switches to the textual protocol (`llm.native_fallback`); an error after a
tool has been executed closes the turn with `turn.error`, without
fallback.

Every step is recorded in the audit: question, tool choice, arguments,
outcome, duration and final answer. A broken audit does not stop the agent: the
failure is reported on stderr.

The `Agent` receives the `Vault` but does not use it yet.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

The agent's virtual filesystem. Every request is:

1. resolved against the current directory (`resolve_path`);
2. checked against the granted roots (`effective_permissions`);
3. filtered by the effective permissions, with the more specific roots
   overriding the more external ones;
4. checked against symlinks and the available disk space
   (`FS_Guardian`, legacy name).

`DirectoryPermissions` models `read`, `write`, `create`, `rename`,
`delete`, `execute`; `None` means "inherit from the external root".
A path outside the roots is always `PermissionError`.

`FileInfo` / `stat()` return type, size in bytes, creation/modification/access
dates (ISO 8601 with local offset) and the sandbox's **effective permissions**,
not the operating system's ACLs.

**Symlinks do not exist for the sandbox.** Hagar does not show them, does not
read them, does not follow them and does not delete them: `stat`, `list_dir` and `search`
ignore them; `read_file`, `read_chunk` and `delete_file` reply "not
found"; `chdir` on a symlink replies "Directory not found". A broken link
or a link pointing outside is indistinguishable from a nonexistent path.

The virtual root of the sandbox is `/home/ai`; every configured directory
is exposed as `/home/ai/<alias>`. `stat`, `list_dir`, `search`,
`read_chunk`, the messages of `write`/`create`/`mkdir`/`delete` and `chdir`
show only virtual paths: the physical path never appears
in the model's output. An input `/home/ai/<alias>/...` is resolved
against the physical directory of the alias; relative paths remain
relative to the current directory.

`/home/ai` is a synthetic directory: it can be listed and stat'ed, but it
is not a mount and it is not possible to `chdir` into it. The entries of
`filesystem.sandbox` remain host system paths, absolute or with
`~` if the user chooses so: it can be any existing and reachable
directory. Hagar does not create directories and does not assume a dedicated
home.

```yaml
filesystem:
  sandbox:
    - alias: documenti
      path: C:\Users\pippo\Documenti
      permissions: RWX
    - alias: ebooks
      path: D:\ebooks
      permissions: R
```

There is no `enabled` flag: every valid entry of `filesystem.sandbox`
is mounted. Invalid aliases or permissions, a missing path or a duplicate path
stop the configuration. The physical paths and the internal names may
contain spaces; the alias may not, because it must remain a single virtual
segment.

`R` covers reading, listing, searching and `stat`; `W` covers writing,
creation, renaming, copying and deletion; `X` covers `chdir`. The global
`permissions.read`/`write` permissions remain a ceiling: an alias
`RWX` cannot exceed them.

## 3.6 Filesystem tools (`core/filesystem_tools.py`)

```text
filesystem.read_file
filesystem.write_file
filesystem.create_file
filesystem.delete_file
filesystem.mkdir
filesystem.chdir
filesystem.list_dir
filesystem.read_chunk
filesystem.rename
filesystem.copy_file
filesystem.search
filesystem.free_space
filesystem.stat
```

`list_dir` returns `FileInfo` metadata; `read_chunk` reads by byte
with `has_more`, `next_offset` and complete UTF-8 boundaries; `search` uses a
recursive glob with a result limit; `copy_file` requires `create`;
`rename` requires `rename` on the source and `create` on the destination.
The returned paths are always virtual (`/home/ai/<alias>/...`).
`chdir` requires `X` on the alias.

`list_dir` returns at most 100 entries per page (`limit` maximum
500) with `offset`, `next_offset` and `has_more`; if there are more entries the
`message` says `items: showing X of Y; to continue use offset=Z`.
`search` uses the same pagination: `max_results` is the page limit
(default 100, maximum 500), `offset` scrolls the results. For large
trees it is better to restrict `pattern`/`path` instead of iterating many
pages. `read_file` accepts only files up to `CHUNK_SIZE` (4096 bytes);
beyond that, the error refers to `read_chunk()` because reading the whole file
would exceed the context window. `read_chunk` returns `next_offset` and
complete UTF-8 boundaries.

`list_dir` and `search` do not show symlinks; `read_file` and `read_chunk`
treat them as nonexistent files.

`write_file` overwrites only existing files; creation goes through
`create_file`, which requires the `create` permission. It is not possible to
bypass the creation ban by writing a new path.

### Write limits

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = disabled
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` is the maximum per single operation of
  `write_file`, `create_file` or `copy_file`;
- `min_free_bytes` is the space reserve that must remain after
  the operation;
- `session_write_bytes` is the cumulative budget of the session;
- `ask_over_bytes` raises operations above the threshold to `ASK`. The preflight
  is built into `ToolRegistry`: even if the policy also says `ASK`, the
  confirmation is a single one.

`0` disables the individual limit. Exceeding `max_write_bytes`,
`session_write_bytes` or the reserve produces an error, not a confirmation:
they are invariants, not questions. `ask_over_bytes` is the only level that
asks the user.

`filesystem.stat` returns JSON with `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. A nonexistent path is not an error:
`exists: false` with the applicable permissions.

## 3.7 MCP (`llm/mcp_client.py`)

MCP client over HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
automatic conversion of the tools into `ToolDefinition` and registration with
the `mcp.<namespace>` namespace.

It also supports `text/event-stream` responses (streamable HTTP) and sends
the `notifications/initialized` notification after the handshake. It uses
`MCP-Protocol-Version` (default `2025-06-18`, with fallback) and reuses
`Mcp-Session-Id` when the server returns it. HTTP errors
include the response body to make 400s diagnosable.
The tool results are normalized to text: `text` blocks,
otherwise `structuredContent` or JSON; a result with `isError`
becomes a tool error.

Authentication per server:

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer          # or "header"
      token_env: MCP_EXAMPLE_TOKEN
      # header: X-API-Key  # only with type: header
```

The token is read only from the environment and does not appear in the audit. If it is missing,
the server is skipped with `mcp.failed` and the harness keeps going; the other
servers remain available.

### Interactive OAuth

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # without it, dynamic registration
    # client_secret_env: MCP_CLIENT_SECRET
    scopes: [mcp.read]
    audience: api.atlassian.com  # optional, for 3LO providers
    redirect_port: 8765       # 0 = random port
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

Authorization code + PKCE flow, with callback on
`http://localhost:<port>/oauth/callback` and browser opening. If the
scope contains `offline_access`, `prompt=consent` is added.
The metadata is discovered from `.well-known` (RFC 9728 for the
resource, RFC 8414 for the authorization server); if `client_id` is missing,
dynamic registration is used. The tokens are in a local file with
restricted permissions (`0600` where the system supports them), with automatic
refresh and a single retry on `401`.

Ctrl-C while waiting for the callback closes the local server and exits
with code 130, without a traceback.

Limits: no device flow, DPoP, mTLS or client assertion; the browser must
be able to reach the local callback. If the callback does not arrive, the
terminal asks you to paste the redirection URL.

## 3.8 Vault (`memory/vault.py`)

Access to the Obsidian vault with paths relative to the root and
protection against escaping the vault. It offers reading, writing, append,
file listing and `load_all` for recursive reading. The semantics
of the memory lives in `memory/store.py` (§3.11).

## 3.9 Audit log (`core/audit.py`)

Append-only JSON Lines file. Every line has a UTC timestamp, `session` and
`event`; the events of the same question share a `turn` id.

```text
harness.start      provider, model, roots, permissions, tools, vault
turn.start         question, tool limit, native mode
llm.tool_choice    model choice, arguments, mode=native
llm.native_fallback provider without native tools, switch to text
llm.protocol_error non-compliant response (full text, truncated)
llm.repaired       successful repair
llm.repair_failed  failed repair
tool.call          tool, arguments, index
tool.result        outcome, output/error, duration in ms
turn.answer        final answer, number of tools used
turn.error         phase and message
turn.stop          limit reached
mcp.loaded         namespace and imported tools
mcp.failed         namespace and error
llm.failed         provider not buildable (e.g. missing key)
harness.stop       clean exit (if missing, the process was killed)
memory.enabled     root, subdir, context turns
memory.disabled    reason for the disabling
memory.context     turns and skills injected into the prompt
memory.turn        turn saved in the vault
memory.failed      phase and error
```

Properties:

- best effort writing: an I/O error does not stop the harness and is
  reported only once on stderr;
- configurable truncation (`audit.max_field_chars`, default 2000);
- hash chain (`prev`/`hash`) verifiable with `verify_chain`;
- rotation into `<file>.<timestamp>` beyond `audit.max_bytes` (0 disables);
- retention: `audit.max_files` (default 100) keeps at most N files,
  including the active one; the oldest backups are deleted;
- with `audit.include_outputs: false` the tool output is recorded
  only as a size;
- non-JSON values made serializable;
- no API key in the log;
- the log also contains the tool output (hence file contents):
  it must be protected like the workspace.

## 3.10 Permissions (`core/permissions.py`)

The model is a subject × object matrix:

- **Capability** (`IntFlag`): what an operation can do
  (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`, `FILESYSTEM_CREATE`,
  `FILESYSTEM_DELETE`, `FILESYSTEM_EXEC`, `MEMORY_READ`,
  `MEMORY_WRITE`, `NETWORK`, `MCP_CALL`, `COMPUTE`). They combine with `|`;
  the check is always a subset check.
- **Effect** (`IntEnum`): `ALLOW`, `ASK`, `DENY`. On conflict
  the highest value wins (`DENY > ASK > ALLOW`).
- **Rule**: capability + effect + optional `tools` (glob),
  `paths` and `namespaces` (prefixes) filters + `reason`.
- **Subject**: who asks (agent, user, system), with rules and
  default (`DENY` if not specified).
- **Resource**: the object of the decision (for now a tool with its
  capabilities; in the future also notes and paths).
- **Decision**: effect, reason and applied rule.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. the resource must offer the requested capabilities;
2. the **system ceiling** (derived from `permissions.read/write/shell`)
   must grant them;
3. for each capability the rules of the subject apply: the most
   specific one wins (number of filters, then length of the prefix), on a
   tie the more restrictive effect; without rules the default applies;
4. with multiple requested capabilities the AND applies: the worst effect wins.

`ASK` is not a decision: it is a question to a human. The
`ConfirmationProvider` asks it — `ConsoleConfirmation` asks
`shall I do it? (y/N)` with default N — and without a confirmation channel
`DENY` applies. A GUI can implement the same protocol with a modal
dialog.

In the CLI `core/input_broker.py` is the only owner of the console:
it distributes prompts, confirmations and the `F5`/`F8` keys, sets the terminal
title as an attention signal and restores the normal mode at the
end. On non-interactive stdin it falls back to `input()`.

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
        paths: ["note"]
      - capabilities: [COMPUTE]
        effect: allow
        tools:
          - "calculator.*"
          - "statistics.*"
          - "units.*"
          - "clock.*"
          - "calendar.*"
          - "think.*"
          - "text.*"
          - "url.*"
      - capabilities: [NETWORK]
        effect: ask
        tools: ["feed.*"]
```

`policy.yaml` is read **before** building the LLM. If it is not
readable or not valid, the harness applies `DENY` to all policies,
records it in the audit (`policy.failed`) and reports it in the chat; the rest
of the harness keeps working. A missing subject also degrades to
`DENY`.

The check happens in `ToolRegistry.execute`, the only execution point, and produces the events `permission.decision` and
`permission.confirmation`.

The `paths` scope compares the path **written by the model**
(normalized), not the one resolved by the sandbox: an absolute path or
a `chdir` may not match a relative prefix, and the
result remains `DENY` (fail closed).

## 3.11 Memory (`memory/store.py`, `memory/tools.py`)

**Default backend: SQLite.** `memory/sqlite_store.py` and
`memory/database.py` use a local database (`%LOCALAPPDATA%/Hagar/memory.db`
or `HAGAR_MEMORY_DB`) as the source of truth for sessions, turns, skills and
summaries. SQLite uses WAL, transactions and `busy_timeout`; the backup is
`VACUUM INTO`. The `markdown` backend described below remains available
only for compatibility and is no longer the default.

**Episodic.** The harness queues every completed turn into a note per
session:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter with `session`, `type: chat`, `created`; body with one
section per turn (`## <timestamp> · <turn>`), question and answer. The tool
outputs are not saved: those remain in the audit.

At the beginning of every turn the Agent injects into the prompt the last
`memory.context_turns` turns (0 disables the injection), truncating
question and answer. With `memory.context_skills > 0` it adds up to N
**confirmed skills** relevant to the question, by lexical match on
title, tags and content; candidates and archived ones never enter.
The block is labelled as data, not instructions. A memory error
does not stop the turn: `memory.failed` is recorded.

**Semantics.** The model can propose a memory with three tools:

| tool | capability | namespace |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

`create_skill` writes `<vault>/Hagar/skills/<slug>.md` with frontmatter
`id`, `title`, `kind` (`fact`/`procedure`), `status: candidate`, `tags`,
`source_session`, `source_turn`, `model`, `created_at`. The slug is
safe (ASCII only, no path); an already existing title is not
overwritten and returns `duplicate: true`.

`get_context` returns the last turns or searches by keyword
in past sessions; `list_skills` filters by `kind` and `status`.

**Lifecycle.** The states are `candidate`, `confirmed`, `archived`.
The LLM creates only candidates; the transition is human, from the CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` shows one candidate at a time with provenance and
content, then asks `y/N/a/s/q` (confirm, leave, archive, skip,
exit). The confirmation writes `reviewed_at`; `archive` is reversible with
`confirm`. Every transition produces `memory.status` or `memory.review`
in the audit. The notes remain Obsidian files: changing `status` in the
frontmatter has the same effect.

**Configuration**:

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

### Project memory

Project memory is separate from skills:

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

Every project has an `index.md` with state, last activity, summary and
count of the active decisions. Every decision has state
`candidate`/`active`/`superseded`/`archived`, alternatives, rationale,
provenance and `auto_saved`. Decisions are not rewritten: a new
decision can replace an old one.

With `memory.backend: sqlite` projects and decisions use the `projects`
and `decisions` tables of the same database; the legacy Markdown backend
keeps using the Vault.

At start-up Hagar shows the active projects and "free activity":

```text
/project list
/project new <name>
/project select <name>
/project free
/project status
/project archive <name>
/project unarchive <name>
```

The non-interactive overrides are `--project <name>` and `--free`.

At the end of the session:

1. the transcript is moved to `archive/chat/`;
2. a summary is generated with the model, with mechanical fallback;
3. the summary is saved with link and hash of the transcript;
4. if there is a project, the LLM proposes `candidate` decisions;
5. the user can review them; if they refuse, they remain `candidate` with
   `auto_saved: true`.

The injected context uses the project's **index**: summary, titles
of the active decisions and count, not all the bodies. The details are
read with `memory.project_context(query=..., limit=...)`. The overall
block is limited by `max_context_chars`; if it is trimmed,
the audit records `memory.context_trimmed`. It is not a token estimate: it is
a budget in characters, deterministic.

When a project exceeds `project_max_active`, Hagar asks whether to
archive it. Archiving is reversible and deletes nothing.

**Archive consultation.** The archived transcripts have the `project`
in the frontmatter. Search and reading are on demand:

```text
/memory archive search <text>
/memory archive read <session> [offset] [limit]
```

The same tools are exposed as `memory.archive_search` and
`memory.archive_read`; the search returns session, turn, timestamp,
project and snippet, the read paginates the turns. There is no automatic
injection of the archive into the prompt: the summary remains the index, the
transcript is the source to consult when needed.

If `vault.path` does not exist or is not writable, the memory is
disabled with a warning in the chat and `memory.disabled` in the audit; the
other components keep working. The memory writes are
subject to the policies (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.11.1 Service layer (`core/service.py`)

`HarnessService` is the stable API above the `Harness`: it does not read from
`input()`, does not write to stdout and does not know the CLI. It exposes:

- `ask(question)` with `turn.start`, `turn.answer`, `turn.error` events;
- tool and permission events forwarded by `Agent` and `ToolRegistry`:
  `tool.call`, `tool.result`, `permission.decision`,
  `permission.confirmation`;
- `status()` with model, project, memory, audit, policy and tools;
- `list_projects()`, `current_project()`, `set_project()`,
  `clear_project()`, `create_project()`;
- `finish_session()`.

The events are `ServiceEvent(type, data, ts)` and can be consumed
by a sink (CLI, GUI, tests). The current CLI uses the service for turns,
project selection and session closing.

## 3.11.2 Command service (`core/command_service.py`)

`CommandService` turns slash commands into `CommandResult`:

```text
command, ok, lines, data, error, requires_input
```

It handles `/help`, `/tools`, `/status`, `/mcp`, `/audit`, `/project` and
`/memory` without writing to stdout. The CLI prints `lines`; the GUI will use
`data`. The interactive review of `/memory` remains delegated to `MemoryCLI`
because it requires human input. The CLI uses the command service for all
slash commands, except `/memory review`.

## 3.11.3 Web GUI (`core/web.py`)

`hagar web` starts a local `ThreadingHTTPServer` with:

- `GET /` chat page;
- `GET /static/style.css` and `/static/app.js` (assets in `web/`);
- `GET /api/events` SSE stream;
- `POST /api/message`, `/api/confirm`, `/api/project`, `/api/stop`,
  `/api/new-chat`, `/api/resume`;
- `GET /api/status`, `/api/projects`, `/api/pending`;
- `GET /api/history`, `/api/history/<session>`;
- `GET /api/tools`, `/api/audit`, `/api/thinking`;
- `GET /api/memories`, `/api/memory?path=...`.

The GUI tabs are Chat, Chat history, Tool output, Audit, Thinking and
Memories. The sidebar holds project, status and tokens; the history is in the
dedicated tab. `SessionLog` keeps the session events for Tool
output and timeline; Audit reads the JSONL; Thinking prefers the
reasoning exposed by the provider and otherwise shows the timeline. Memories
reads the index, excluding chats, archive and summaries.

A click on a past chat calls `POST /api/resume`: the transcript
is reloaded and the audit/memory session returns to that id, so the
new turns continue the same chat. `POST /api/new-chat` calls
`MemoryStore.new_session()` and changes the session, without touching the
previous transcripts.

The static assets live in `web/` (`index.html`, `style.css`,
`app.js`). `render_index()` injects only the token; the rest is served
verbatim with a whitelist and `importlib.resources`.

The GUI is an adapter: it uses `HarnessService`, `CommandService` and
`QueueConfirmationProvider`. ASK confirmations block the turn thread
on a `threading.Event`; the server remains free and releases the request with
`POST /api/confirm`. A timeout counts as a refusal.

The sidebar shows the cumulative tokens of the session: `UsageLedger` receives
the usage from every LLM call through `usage_sink` and publishes
`usage.updated` over SSE.

**Stop:** `POST /api/stop` calls `Agent.cancel()`; the agent checks
the event between one step and the next and raises `AgentCancelled`. The turn is
interrupted cooperatively, it does not abort an HTTP request already in
progress.

**Vision:** `POST /api/message` accepts `images` as PNG/JPEG/WebP data URLs
(max 4, 10 MB each); the JSON body can reach
64 MB. `core/images.py` validates and converts; `Agent.ask(question,
images=...)` builds multimodal content. The OpenAI-compatible/LM Studio
adapters use `image_url`; Claude uses `image` blocks; Gemini uses
`inlineData`. LM Studio does not accept WebP
directly: the GUI converts it to PNG. The image does not end up in the
Markdown memory or in the audit.

Security: default bind `127.0.0.1`, random token injected into the
page, `X-Hagar-Token` header for the APIs and `?token=` for SSE. It is not
multi-user and does not yet expose Vault modification.

## 3.11.6 Vision input (`core/images.py`)

`ImageInput` validates data URL, MIME and size; `Agent.ask` uses canonical
parts (`text`, `image`) and every backend translates them into its own
format. The text of the stop and of the images is separate from the persistent
content: the memory keeps only the question and the answer.

`vision.open` reads an image from the sandbox, validates it with a magic number
and returns it as `ToolResult.images`. The `Agent` loop attaches
the image to a synthetic user message before the next
call, so the model sees it without receiving base64 in the text of the
tool. Limits: 4 images per turn, 10 MB per image, PNG/JPEG/WebP.
The child can use `vision.open` in its own read-only workspace.

Audio is not implemented. The attachment channel would be reusable, but
a different audio-native provider contract, formats/decoders and an
explicit choice between ASR and audio understanding are needed; it is in the roadmap without a
timeline.

`memory/export.py` exports the SQLite database to Markdown:
`Hagar/chat/`, `Hagar/skills/`, `Hagar/summaries/`,
`Hagar/projects/<id>/index.md` and `decisions/`. Writing is atomic
(temp + `os.replace`) and the command rejects a non-empty destination
without `--force`.

`memory_fts` is an FTS5 table in the same database, with columns
`entity`, `entity_id`, `kind`, `project`, `status`, `title`, `body`.
`SqliteMemoryIndex.search` uses `MATCH`, `bm25()` and `snippet()`; if FTS5
is not available it falls back to `LIKE`. `memory/import_markdown.py` imports
the same structure with upsert and rebuilds the FTS index.

## 3.11.4 Token usage (`core/usage.py`)

`TokenUsage` normalizes input, output, cache and reasoning. The functions
`usage_from_openai`, `usage_from_anthropic`, `usage_from_gemini` and
`usage_from_ollama` read the native fields of the responses.

`LLMClient._set_usage()` updates `last_usage` and calls the client's
`usage_sink`. `HarnessService` owns the `UsageLedger`, connects it to the
client and publishes `usage.updated`; the GUI uses it in the sidebar and `/usage`
reads it from the CLI. The provider's usage is the
truth; a local estimate remains only a fallback.

## 3.11.5 Memory index (`memory/index.py`)

`MemoryIndex` is an SQLite index derived from the Markdown Vault:

- `documents`, `meta` and `documents_fts` (FTS5) tables;
- incremental sync by hash/mtime/size;
- `rebuild()` rebuilds from scratch;
- search with `project`, `kind`, `status` filters;
- `LIKE` fallback if FTS5 is not available;
- database in the app's local data, not in the synced Vault.

The `memory.search` tool uses the index; `/memory reindex` and `/memory stats`
expose maintenance and status. With the default SQLite backend the
source of truth is `memory.db`; the old `MemoryIndex` remains only for the
legacy Markdown backend.

## 3.11.7 Decision tools (`core/decisions.py`)

`DecisionRegistry` selects a `DecisionProvider` and `decision.choose`
exposes the choice to the model. The built-in providers are:

- `llm`: asks the LLM client for a JSON with `choice` and `probabilities`,
  validates the labels and normalizes the probabilities;
- `linear`: loads a local JSON model with labels, weights and bias and uses
  softmax to produce the probabilities.

The `DECISION` capability is separate from `COMPUTE`, `NETWORK` and
`FILESYSTEM_*`; the details and the model format are in
`DECISIONS.md`. Jev/Kev are not native adapters yet.

## 3.12 Start-up and packaging

The project installs with `pip install -e .` and declares the packages in
`pyproject.toml`. The entry point is `hagar = "hagar:main"`. The current
version is `0.5.2`.

The example configuration is `hagar.example.yaml`; `hagar.yaml` is a
local file ignored by git. The example's default Vault is
`./vault` and must be created before start-up.

```text
hagar --config PATH       configuration file
hagar --model NAME        overrides model.name
hagar --project NAME      selects an active project
hagar --free              starts in free activity
hagar --no-memory         disables the memory for the session
hagar --no-native-tools   uses the textual JSON protocol
hagar --version
```

The configuration is searched in this order: `--config`, the
`HAGAR_CONFIG` variable, `./hagar.yaml`. `python -m hagar` works from the
project directory.

The GitHub Actions CI runs the suite on Linux, macOS and Windows with
Python 3.11/3.12/3.13, builds sdist and wheel, runs `twine check` and
tries the wheel installation. The `Release` workflow starts from a `v*` tag,
verifies that the tag matches the package version and
creates the GitHub release with the artifacts.

The live tests are excluded from the normal suite and are enabled with
`--live`: they verify Ollama and the remote providers (the latter only if
the API key is present).

## 3.13 Local tools (`local_tools/`)

They are not MCP servers: they are local providers that register `ToolDefinition`s
in the registry and live outside the core, in a separate package.

| module | tool | capability |
|---|---|---|
| `calculator` | `calculator.evaluate` | `COMPUTE` |
| `statistics` | `statistics.compute` | `COMPUTE` |
| `unit_converter` | `units.convert` | `COMPUTE` |
| `clock` | `clock.now` | `COMPUTE` |
| `calendar` | `calendar.date` | `COMPUTE` |
| `think` | `think.echo` | `COMPUTE` |
| `text` | `text.diff` | `COMPUTE` |
| `url` | `url.parse` | `COMPUTE` |
| `feeder` | `feed.read` | `NETWORK` |

- `clock.now` returns local time, date, timezone, UTC offset and epoch.
- `calendar.date` converts the local date, or an optional ISO date, into the
  proleptic Julian calendar or the tabular Islamic calendar
  (Kuwaiti algorithm). The tabular Islamic calendar may differ by
  one day from those based on observation or on Umm al-Qura.
- `think.echo` returns exactly the string received; it serves to
  externalize an intermediate step in reasoning chains.
- `text.diff` returns a unified diff between two texts, with a maximum input
  of 20000 characters, maximum output of 20000 and `context` 0..10. It does not
  apply the diff.
- `url.parse` splits scheme, host, port, path, query and fragment without
  DNS or network; it limits the URL to 4096 characters and the parameters to 100. If
  the URL contains credentials, it redacts them in the output.
- `clock`, `calendar`, `think`, `text` and `url` do not access the filesystem
  or the network, and fall under the `COMPUTE` allow rule.
- The calculator uses an AST whitelist, not `eval()`, with limits on
  expression, number of nodes and exponent.
- `feed.read` downloads with `requests` (timeout 15 s, maximum 5 MB), accepts
  only http/https URLs and uses `feedparser`; the `NETWORK` policy is `ask`.
- SSRF: every host is resolved with `getaddrinfo` and every address must
  be global; loopback, private networks, link-local, multicast and
  reserved ones are refused. Redirects are not automatic: every
  `Location` is revalidated and they stop after 3 hops. A URL with
  credentials is refused.
- `permissions.network: true` is required for the system ceiling
  to grant `NETWORK`; `COMPUTE` is always in the ceiling but the policy can deny it.
- `permissions.agents: true` is required for `AGENT_SPAWN`; the policy
  must also allow `agent.*`.
- `local_tools` is declared in `pyproject.toml` and installed with the
  project.

The built-in tools are registered by `local_tools/plugins.py` through
the same `ToolPlugin` contract as the external plugins. The external plugins are
discovered with the `hagar.tools` entry point and receive a `PluginContext`.
Policy and sandbox remain in the registry: a plugin cannot grant
permissions. A broken plugin is skipped and recorded in the audit, without
stopping the others.

## 3.14 Plugins

`core/plugins.py` defines:

- `ToolPlugin` + `PluginContext` for the tools;
- `LLMProvider` for the LLM providers;
- discovery via `importlib.metadata.entry_points`;
- error isolation and `plugin.loaded`/`plugin.error` audit.

The built-in providers are in `llm/plugins.py` and are registered before
the external ones. An external provider cannot replace a built-in name.
Python plugins are trusted and run in-process; for untrusted
extensions the boundary remains MCP or a separate process. The full contract
is in `PLUGINS.md`.

## 3.15 Asynchronous subagents

`core/subagents.py` implements:

- `agent.spawn/status/wait/result/cancel` and the synchronous `agent.run`;
- `reason` mandatory at spawn, recorded in the audit;
- separate `AGENT_SPAWN` capability: the child does not receive it and cannot
  create other agents;
- strictly more restrictive child policy; equal or broader
  policies are refused with `SubagentPolicyError`;
- 5-minute wall timeout, cooperative, with `timed_out` state;
- `agent_id` in all the audit events of the parent, of the child and of the
  registry;
- up to two concurrent subagents;
- same local model but separate LLM client;
- private temporary workspace for each child;
- inputs copied from the parent's workspace;
- `artifact.put`/`artifact.put_file` and `mailbox.send` outbox for the
  child;
- temporary artifact store (max 50 MB per artifact, 256 MB per turn)
  and in-memory mailbox (max 64 KB per message);
- bounded reading by the parent with `artifact.read`, `artifact.list`,
  `mailbox.inbox/read/ack`;
- `artifact.save_to` copies the whole artifact to a writable path of the
  parent's sandbox, without going through the context;
- `AGENT_DATA` capability;
- registry filtered to `FILESYSTEM_READ`, `MEMORY_READ`, `COMPUTE` and
  `AGENT_DATA`;
- exclusion of `filesystem.chdir` and `agent.*`;
- no memory writes;
- the child's ASKs forwarded to the user by `ParentBridgeConfirmation`,
  timeout 180 seconds and DENY at expiry; the parent LLM does not approve;
- separate usage;
- `agent.spawned/started/finished/cancelled/failed` audit;
- at the end of the turn, `artifact.discarded` for artifacts not exported, with
  reason `unread` or `read_but_not_saved` and metadata without content;
- cleanup of workspace and jobs at the end of the turn.

`AuditLog.record` is serialized with a lock for concurrent writes.
There are not yet artifact exports, token/time budgets, nesting or a
dedicated GUI. The details are in `SUBAGENTS.md`.

---

# 4. Security model

- The agent does not see the real filesystem: only paths resolved inside the
  sandbox.
- The operations pass only through the `ToolRegistry`; no host shell.
- The permissions are declared in the configuration and in the policies, and are
  applied by the sandbox and `PermissionEvaluator`; nested roots
  can restrict the permissions.
- Errors are data: a refusal is returned to the model as a
  tool result, not hidden.
- Every action leaves a trace in the audit, with session and turn.

---

# 5. Development

- Suite: `./tools/run_tests.sh` (Linux/macOS) or
  `.\tools\run_tests.ps1` (Windows). On Windows: 832 passed, 2 skipped
  (symlinks not available without Developer Mode). On Debian Linux
  (2026-11-06): all tests green, including the symlinks (743 passed, 0
  skipped). Details and rationale of the shim in README §3.1.
- Live tests: `./tools/run_tests.sh --live` (Linux/macOS) or
  `.\tools\run_tests.ps1 --live` (Windows) — 9 extra tests (Ollama;
  remote providers if the keys are present).
- Model comparison: `python tools/bench_models.py` (README §3.5).
- Protocol comparison: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- The normal suite does not touch the network: Ollama and MCP are simulated.

## 5.1 Cross-platform

- The internal paths use `pathlib.Path`; the ones shown to the agent
  always use `/` and the virtual root `/home/ai`.
- `filesystem.sandbox` contains host system paths, absolute or with
  `~` if the user chooses so: `Path.expanduser()` resolves the home only
  when the path uses it. It is not assumed that a dedicated home exists.
- Every mount has an explicit and unique alias (case-insensitive); the
  physical path can be on any volume.
- `tools/run_tests.sh` is the POSIX runner; `tools/run_tests.ps1` and
  `tools/pytest_shim` serve only the Windows sandbox with a restricted
  token.
- The only explicitly Windows branch left is the creation date in
  `stat`: `st_birthtime` where available, otherwise `st_ctime` on
  Windows; on Linux `created_at` may be `None`.
- The external APIs (OAuth, MCP, LLM) use HTTP and `webbrowser`, not
  system commands.
- The GitHub Actions CI covers Linux, macOS and Windows on Python
  3.11/3.12/3.13; symlinks, OAuth token permissions and loopback callbacks
  remain to be verified with live tests, not in the offline suite.

---

# 6. Known limits and technical debt

- `PermissionEvaluator` covers v1: dynamic subjects, GUI
  confirmations and MCP capabilities assigned by the configuration remain to be done.
- Native calling depends on the model: some ignore the tools or
  return multiple calls; the textual fallback covers the errors, not
  the quality of the choice.
- The MCP client supports bearer/header and OAuth authorization code; it does not
  handle device flow, DPoP, mTLS or client assertion.
- The review of skills is manual from the CLI; a GUI is missing.
- The memory search is by keyword, without an index or
  embeddings.
- The injected context uses global recent turns and up to 3 confirmed
  skills by lexical match, without semantic selection.
- The memory does not delete chats or skills by age: `archive` is
  the only removal from the context.
- The audit has rotation and retention (`max_files`), but no session
  compaction and no external anchoring of the chain.
- `feed.read` validates the addresses and the redirects, but the DNS
  rebinding case remains: `requests` resolves the name a second time at
  connection time; a pinned resolver is needed.
- The calculator is not a CAS: it handles only limited numeric
  expressions, not symbolic ones.
- `stat().created_at` is `None` on Linux when `st_birthtime` is missing; a
  creation date is not invented.
- Two aliases cannot point to the same physical path: the alias
  identifies a mount and the virtual output must remain unique.

## 6.1 User responsibility: hard links, mounts and TOCTOU

**Hagar does not check hard links, mounts/junctions and TOCTOU races
inside the allowed directories.** It is not a defect of Hagar: the sandbox is
path-based and does not use handles/file descriptors for the whole operation.

A hard link is a second name of the same inode, it has no path target
and the sandbox cannot know whether another name exists outside. A
mount or a junction can expose another filesystem while remaining inside
the path prefix. A TOCTOU race can change a component between the
symlink check and the actual operation: Hagar does not use `openat2`,
`O_NOFOLLOW` on every component or Windows handles, so it does not guarantee
atomicity between check and access.

Hagar's filesystem tools do not create hard links. If a hard link or a
mount already exists inside a sandbox directory, Hagar treats it as
a normal file or directory and can read it, modify it or delete its
internal name.

The responsibility is therefore split:

- **Hagar guarantees** that the resolved paths remain inside the alias at
  the moment of the check, that the symlinks are invisible, that the `R`/`W`/`X`
  permissions are applied and that the real paths do not end up
  in the model's output.
- **The user guarantees** that the directories configured in
  `filesystem.sandbox` do not contain hard links, mounts or junctions towards
  contents that must not be accessible, and that no untrusted
  concurrent process can modify those directories during
  execution, if total isolation is wanted.

TOCTOU races require a concurrent local actor with write access to
the sandbox directories: they are not an accidental case
of normal use, but a malicious scenario or one of compromised environment.
For strong isolation a dedicated volume, a separate user,
a mount namespace or a container are needed; it is not the job of the path
resolver.

The points are closed as **user responsibility**, not as technical debts
of Hagar. Hard links, mounts/junctions and TOCTOU races are not
detected or blocked by this version.

---

# 7. Documentation map

- `MANUAL.md` — user manual: commands, configuration, policies, defaults.
- `ARCHITECTURE.md` — this document: how the system is today.
- `ROADMAP.md` — what to do, decisions taken and open points.
- `PLUGINS.md` — contracts for tool and LLM provider plugins.
- `DOCUMENT_TOOL.md` — document tool specification, graph schema and
   protocol of the native host.
- `SUBAGENTS.md` — subagent MVP and limits.
- `CHANGELOG.md` — version history.
- `README.md` — start-up, configuration, tests.
