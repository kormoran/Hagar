# HAGAR — Architecture

Version: 0.2.0 (in development)
Last updated: 2026-11-03

---

# 1. What Hagar is

Hagar is a harness for LLMs written in Python, designed for the
resilient execution of language models.

The goal is not a chat with a model, but a **safe** operating environment
in which an LLM can use tools, consult a persistent memory
and interact with external systems without directly accessing
the real resources of the host machine.

To this end the project applies HMI/HCI and Cognitive
Ergonomics principles to the design of the environment in which the model operates.

## 1.1 The Four Laws of HAGAR

**First law — The LLM is untrustworthy by definition.**
Not because it is bad or useless: because it is probabilistic. Every
statement of its must be verified and every action of its must be limited.

**Second law — Tools are more reliable than the LLM.**
If the filesystem says a file exists, it exists. If the tool returns
a size, that size is real. The LLM interprets, the tools
measure.

**Third law — State must exist outside the LLM's mind.**
ToolRegistry, MCP, FileSystemSandbox and (prospectively)
PermissionEvaluator move knowledge and control outside the model,
as in safety-critical systems.

**Fourth law — Every action must be explainable afterwards.**
The audit log answers the right question: not "why did the LLM go crazy?"
but "what assumption did it make?", "which tool did it use?", "which piece of data was
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
  │     ├── DeepSeekClient
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
| `model` | yes | provider, name, host, max_tokens, api_key_env, native_tools |
| `vault` | yes | path of the Obsidian vault |
| `filesystem` | yes | `sandbox`: list of `{alias, path, permissions}`; `limits`: write budget |
| `permissions` | no | read, write, shell, network (default `true/false/false/false`) |
| `rag` | no | `top_k` (default 8) |
| `mcp_servers` | no | endpoint, namespace, auth (bearer/header/oauth) |
| `audit` | no | enabled, path, max_field_chars, max_bytes, max_files, include_outputs |
| `policy` | no | policy file path, subject |
| `memory` | no | enabled, vault_subdir, context_turns, context_skills, max_skill_chars |

Validation errors always produce `ConfigError`, with a message that
names the field. The audit path, if relative, is resolved
against the configuration file.

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
`functionResponse`). An HTTP 400/404/422 rejection produces
`NativeToolsUnavailable`: the Agent switches to the textual protocol only if it
has not yet executed any tool.

Tool names are normalized for APIs that do not allow the
dot (`filesystem.read_file` → `filesystem__read_file`) and mapped back to the
internal name in the response: policy, audit and tests always see the
original name.

Text remains the fallback for models that do not support native tools;
`model.native_tools: false` forces it (or `--no-native-tools` from the CLI).

| provider | API | key | notes |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | default host `localhost:11434` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | separate system, alternating turns |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, `model` role |

The key is read only from the environment; `model.api_key_env` overrides the
default name. `model.host` is the base URL of all providers (with a
per-provider default), `model.max_tokens` is used only by Claude.
`llm/factory.py` builds the client and rejects unknown providers or
missing keys. DeepSeek: the current models are `deepseek-flash` and
`deepseek-v4-pro`; `deepseek-chat` is no longer accepted.

Current state: **native calling v1** with automatic textual fallback
(see ROADMAP).

## 3.3 Tool model (`core/tool_*.py`)

`ToolDefinition` describes name, description, category, parameters,
handler, `origin` (`local` or `mcp.<namespace>`), the declared
`capabilities`, the enabled state and `requires_confirmation`
(ASK floor applied by the registry).

`ToolCall` is the model's request (`tool`, `arguments`, `id`);
`ToolResult` is the structured outcome (`tool_name`, `success`, `output`,
`error`).

`ToolRegistry` registers, looks up, enables/disables and executes the tools;
it exposes the metadata to the model and is the only execution point.

## 3.4 Agent (`core/agent.py`)

Multi-step agentic loop, with two paths:

- **native**: one response can contain several calls; the Agent re-queues
  the `assistant` message and one `tool` message with the id for each
  result;
- **textual**: one call at a time, with the result sent as a
  `user` turn.

In both:

1. the model decides whether a tool is needed;
2. if not, the final answer closes the turn;
3. if so, the tool is executed and the result goes back to the model;
4. the `max_tool_calls` limit applies to the whole turn. If the model
   persists, the turn closes with `Agent stopped after N tool calls`
   (loop protection).

If the first native step fails with `NativeToolsUnavailable`, the Agent
switches to the textual protocol (`llm.native_fallback`); an error after a
tool has been executed closes the turn with `turn.error`, without
fallback.

Every step is recorded in the audit: question, tool choice, arguments,
outcome, duration and final answer. A broken audit does not stop the agent: the
fault is reported on stderr.

The `Agent` receives the `Vault` but does not use it yet.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

The agent's virtual filesystem. Every request is:

1. resolved against the current directory (`resolve_path`);
2. checked against the granted roots (`effective_permissions`);
3. filtered by the effective permissions, with the most specific roots
   overriding the outer ones;
4. checked against symlinks and available disk space
   (`FS_Guardian`, legacy name).

`DirectoryPermissions` models `read`, `write`, `create`, `rename`,
`delete`, `execute`; `None` means "inherits from the outer root".
A path outside the roots is always a `PermissionError`.

`FileInfo` / `stat()` return type, size in bytes, creation/modification/access
dates (ISO 8601 with local offset) and the **effective sandbox
permissions**, not the operating system ACLs.

**Symlinks do not exist for the sandbox.** Hagar does not show them, does not
read them, does not follow them and does not delete them: `stat`, `list_dir` and `search`
ignore them; `read_file`, `read_chunk` and `delete_file` answer "not
found"; `chdir` on a symlink answers "Directory not found". A broken
link or a link to the outside is indistinguishable from a non-existent path.

The virtual root of the sandbox is `/home/ai`; every configured directory
is exposed as `/home/ai/<alias>`. `stat`, `list_dir`, `search`,
`read_chunk`, the messages of `write`/`create`/`mkdir`/`delete` and `chdir`
show only virtual paths: the physical path never appears in the
model's output. An input `/home/ai/<alias>/...` is resolved
against the alias's physical directory; relative paths remain
relative to the current directory.

`/home/ai` is a synthetic directory: you can list it and stat it, but it
is not a mount and it is not possible to `chdir` into it. The entries of
`filesystem.sandbox` remain host system paths, absolute or with
`~` if the user chooses so: it can be any existing and
reachable directory. Hagar does not create directories and does not assume a
dedicated home.

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
stop the configuration. Physical paths and internal names can
contain spaces; the alias cannot, because it must remain a single virtual
segment.

`R` covers reading, listing, searching and `stat`; `W` covers writing,
creation, rename, copy and deletion; `X` covers `chdir`. The
global `permissions.read`/`write` permissions remain a ceiling: an `RWX` alias
cannot exceed them.

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

`list_dir` returns `FileInfo` metadata; `read_chunk` reads by bytes
with `has_more`, `next_offset` and complete UTF-8 boundaries; `search` uses a
recursive glob with a result limit; `copy_file` requires `create`;
`rename` requires `rename` on the source and `create` on the destination.
The returned paths are always virtual (`/home/ai/<alias>/...`).
`chdir` requires `X` on the alias.

`list_dir` returns at most 100 entries per page (`limit` maximum
500) with `offset`, `next_offset` and `has_more`; if there are more entries the
`message` says `voci: riportate X di Y; per continuare usa offset=Z`.
`search` uses the same pagination: `max_results` is the page limit
(default 100, maximum 500), `offset` walks through the results. For large
trees it is better to narrow `pattern`/`path` instead of iterating many
pages. `read_file` accepts only files up to `CHUNK_SIZE` (4096 bytes);
beyond that, the error points to `read_chunk()` because reading the whole file
would exceed the context window. `read_chunk` returns `next_offset` and
complete UTF-8 boundaries.

`list_dir` and `search` do not show symlinks; `read_file` and `read_chunk`
treat them as non-existent files.

`write_file` only overwrites existing files; creation goes through
`create_file`, which requires the `create` permission. It is not possible to
bypass the creation prohibition by writing a new path.

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
  confirmation happens only once.

`0` disables the individual limit. Exceeding `max_write_bytes`,
`session_write_bytes` or the reserve produces an error, not a confirmation:
they are invariants, not questions. `ask_over_bytes` is the only level that
asks the user.

`filesystem.stat` returns JSON with `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. A non-existent path is not an error:
`exists: false` with the applicable permissions.

## 3.7 MCP (`llm/mcp_client.py`)

MCP client over HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
automatic conversion of the tools into `ToolDefinition` and registration with
namespace `mcp.<namespace>`.

It also supports `text/event-stream` responses (streamable HTTP) and sends
the `notifications/initialized` notification after the handshake. It uses
`MCP-Protocol-Version` (default `2025-06-18`, with fallback) and reuses
`Mcp-Session-Id` when the server returns it. HTTP errors
include the response body to make 400s diagnosable.
Tool results are normalized to text: `text` blocks,
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

The token is read only from the environment and does not appear in the audit. If it is
missing, the server is skipped with `mcp.failed` and the harness keeps going; the other
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

Authorization code + PKCE flow, with callback at
`http://localhost:<port>/oauth/callback` and browser opening. If the
scope contains `offline_access`, `prompt=consent` is added.
The metadata is discovered from `.well-known` (RFC 9728 for the
resource, RFC 8414 for the authorization server); if `client_id` is missing,
dynamic registration is used. The tokens are in a local file with
restricted permissions (`0600` where the system supports them), with automatic
refresh and one retry on `401`.

Ctrl-C while waiting for the callback closes the local server and exits
with code 130, without a traceback.

Limits: no device flow, DPoP, mTLS or client assertion; the browser must
be able to reach the local callback. If the callback does not arrive, the
terminal asks you to paste the redirect URL.

## 3.8 Vault (`memory/vault.py`)

Access to the Obsidian vault with paths relative to the root and
protection against escaping the vault. It offers reading, writing, append,
file listing and `load_all` for recursive reading. The semantics
of the memory live in `memory/store.py` (§3.11).

## 3.9 Audit log (`core/audit.py`)

Append-only JSON Lines file. Every line has a UTC timestamp, `session` and
`event`; the events of the same question share a `turn` id.

```text
harness.start      provider, model, roots, permissions, tools, vault
turn.start         question, tool limit, native mode
llm.tool_choice    model choice, arguments, mode=native
llm.native_fallback provider without native tools, switch to text
llm.protocol_error non-conforming response (full text, truncated)
llm.repaired       successful repair
llm.repair_failed  failed repair
tool.call          tool, arguments, index
tool.result        outcome, output/error, duration in ms
turn.answer        final answer, number of tools used
turn.error         phase and message
turn.stop          limit reached
mcp.loaded         namespace and imported tools
mcp.failed         namespace and error
llm.failed         provider that cannot be built (e.g. missing key)
harness.stop       clean exit (if missing, the process was killed)
memory.enabled     root, subdir, context turns
memory.disabled    reason for the deactivation
memory.context     turns and skills injected into the prompt
memory.turn        turn saved in the vault
memory.failed      phase and error
```

Properties:

- best effort writing: an I/O error does not stop the harness and is
  reported only once on stderr;
- configurable truncation (`audit.max_field_chars`, default 2000);
- hash chain (`prev`/`hash`) verifiable with `verify_chain`;
- rotation to `<file>.<timestamp>` beyond `audit.max_bytes` (0 disables);
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
- **Effect** (`IntEnum`): `ALLOW`, `ASK`, `DENY`. In case of conflict
  the highest value wins (`DENY > ASK > ALLOW`).
- **Rule**: capability + effect + optional filters `tools` (glob),
  `paths` and `namespaces` (prefixes) + `reason`.
- **Subject**: who asks (agent, user, system), with rules and
  default (`DENY` if not specified).
- **Resource**: the object of the decision (for now a tool with its
  capabilities; in the future also notes and paths).
- **Decision**: effect, reason and applied rule.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. the resource must offer the requested capabilities;
2. the **system ceiling** (derived from `permissions.read/write/shell`)
   must grant them;
3. for each capability the subject's rules apply: the most specific
   wins (number of filters, then prefix length), on a tie the most
   restrictive effect; without rules the default applies;
4. with several capabilities requested, AND applies: the worst effect wins.

`ASK` is not a decision: it is a question to a human. The
`ConfirmationProvider` asks it — `ConsoleConfirmation` prompts
`lo faccio? (y/N)` with default N — and without a confirmation channel
`DENY` applies. A GUI will be able to implement the same protocol with a modal
dialog.

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
readable or not valid, the harness applies `DENY` to every policy,
records it in the audit (`policy.failed`) and reports it in the chat; the rest
of the harness keeps working. A missing subject also degrades to
`DENY`.

The check happens in `ToolRegistry.execute`, the only execution
point, and produces the `permission.decision` and
`permission.confirmation` events.

The `paths` scope compares the path **written by the model**
(normalized), not the one resolved by the sandbox: an absolute path or
a `chdir` may not match a relative prefix, and the
result stays `DENY` (fail closed).

## 3.11 Memory (`memory/store.py`, `memory/tools.py`)

**Episodic.** The harness appends every concluded turn to a note per
session:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter with `session`, `type: chat`, `created`; body with one
section per turn (`## <timestamp> · <turn>`), question and answer. Tool
outputs are not saved: those remain in the audit.

At the start of every turn the Agent injects into the prompt the latest
`memory.context_turns` turns (0 disables the injection), truncating
question and answer. With `memory.context_skills > 0` it adds up to N
**confirmed skills** relevant to the question, by lexical match on
title, tags and content; candidates and archived ones never enter.
The block is labelled as data, not instructions. A memory error
does not stop the turn: `memory.failed` is recorded.

**Semantic.** The model can propose a memory with three tools:

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

`get_context` returns the latest turns or searches by keyword
in past sessions; `list_skills` filters by `kind` and `status`.

**Lifecycle.** The states are `candidate`, `confirmed`, `archived`.
The LLM only creates candidates; the transition is human, from the CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` shows one candidate at a time with provenance and
content, then asks `y/N/a/s/q` (confirm, leave, archive, skip,
exit). Confirmation writes `reviewed_at`; `archive` is reversible with
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
<vault>/Hagar/projects/<id>/decisions/<date>-<slug>.md
<vault>/Hagar/summaries/<date>-<session>.md
<vault>/Hagar/archive/chat/<date>-<session>.md
```

Every project has an `index.md` with state, last activity, summary and
count of active decisions. Every decision has state
`candidate`/`active`/`superseded`/`archived`, alternatives, rationale,
provenance and `auto_saved`. Decisions are not rewritten: a new
decision can replace an old one.

At start-up Hagar shows the active projects and “free activity”:

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

The injected context uses the project **index**: summary, titles
of the active decisions and count, not all the bodies. Details are
read with `memory.project_context(query=..., limit=...)`. The overall
block is limited by `max_context_chars`; if it is trimmed,
the audit records `memory.context_trimmed`. It is not a token estimate: it is
a character budget, deterministic.

When a project exceeds `project_max_active`, Hagar asks whether to
archive it. Archiving is reversible and deletes nothing.

**Archive consultation.** The archived transcripts have the `project`
in the frontmatter. Search and reading are on demand:

```text
/memory archive search <text>
/memory archive read <session> [offset] [limit]
```

The same tools are exposed as `memory.archive_search` and
`memory.archive_read`; search returns session, turn, timestamp,
project and snippet, reading pages through the turns. There is no automatic
injection of the archive into the prompt: the summary remains the index, the
transcript is the source to consult when needed.

If `vault.path` does not exist or is not writable, memory is
disabled with a warning in the chat and `memory.disabled` in the audit; the
other components keep working. Memory writes are
subject to the policies (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.12 Start-up and packaging

The project is installed with `pip install -e .` and declares the packages in
`pyproject.toml`. The entry point is `hagar = "hagar:main"`. The current
version is `0.3.0`.

The example configuration is `hagar.example.yaml`; `hagar.yaml` is a
local file ignored by git. The default Vault of the example is
`./vault` and must be created before start-up.

```text
hagar --config PATH       configuration file
hagar --model NAME        overrides model.name
hagar --project NAME      selects an active project
hagar --free              starts in free activity
hagar --no-memory         disables memory for the session
hagar --no-native-tools   uses the textual JSON protocol
hagar --version
```

The configuration is looked up in this order: `--config`, the
`HAGAR_CONFIG` variable, `./hagar.yaml`. `python -m hagar` works from the
project directory.

The GitHub Actions CI runs the suite on Linux, macOS and Windows with
Python 3.11/3.12/3.13, builds sdist and wheel, runs `twine check` and
tests the wheel installation. The `Release` workflow starts from a
`v*` tag, checks that the tag matches the package version and
creates the GitHub release with the artifacts.

Live tests are excluded from the normal suite and are enabled with
`--live`: they check Ollama and the remote providers (the latter only if
the API key is present).

## 3.13 Local tools (`local_tools/`)

They are not MCP servers: they are local providers that register `ToolDefinition`
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

- `clock.now` returns local time, date, time zone, UTC offset and epoch.
- `calendar.date` converts the local date, or an optional ISO date, into the
  proleptic Julian calendar or the tabular Islamic one
  (Kuwaiti algorithm). The tabular Islamic calendar may differ by
  one day from observation-based ones or from Umm al-Qura.
- `think.echo` returns exactly the string received; it serves to
  externalize an intermediate step in reasoning chains.
- `text.diff` returns a unified diff between two texts, with a maximum input
  of 20000 characters, a maximum output of 20000 and `context` 0..10. It does
  not apply the diff.
- `url.parse` breaks down scheme, host, port, path, query and fragment without
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
  reserved addresses are rejected. Redirects are not automatic: every
  `Location` is revalidated and they stop after 3 hops. A URL with
  credentials is rejected.
- `permissions.network: true` is required for the system ceiling to
  grant `NETWORK`; `COMPUTE` is always in the ceiling but the policy can deny it.
- `local_tools` is declared in `pyproject.toml` and installed with the
  project.

---

# 4. Security model

- The agent does not see the real filesystem: only paths resolved inside the
  sandbox.
- Operations pass only through the `ToolRegistry`; no host shell.
- The permissions are declared in the configuration and in the policies, and are
  applied by the sandbox and the `PermissionEvaluator`; nested roots
  can restrict the permissions.
- Errors are data: a refusal is returned to the model as a
  tool result, not hidden.
- Every action leaves a trace in the audit, with session and turn.

---

# 5. Development

- Suite: `./tools/run_tests.sh` (Linux/macOS) or
  `.\tools\run_tests.ps1` (Windows). On Windows: 691 passed, 2 skipped
  (symlinks not available without Developer Mode). On Debian Linux
  (2026-11-06): all tests green, including symlinks (693 passed, 0
  skipped). Details and rationale of the shim in README §3.1.
- Live tests: `./tools/run_tests.sh --live` (Linux/macOS) or
  `.\tools\run_tests.ps1 --live` (Windows) — 9 more tests (Ollama;
  remote providers if the keys are present).
- Model comparison: `python tools/bench_models.py` (README §3.5).
- Protocol comparison: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- The normal suite does not touch the network: Ollama and MCP are simulated.

## 5.1 Cross-platform

- Internal paths use `pathlib.Path`; the ones shown to the agent
  always use `/` and the virtual root `/home/ai`.
- `filesystem.sandbox` contains host system paths, absolute or with
  `~` if the user chooses so: `Path.expanduser()` resolves the home only
  when the path uses it. It is not assumed that a dedicated home exists.
- Every mount has an explicit and unique alias (case-insensitive); the
  physical path can be on any volume.
- `tools/run_tests.sh` is the POSIX runner; `tools/run_tests.ps1` and
  `tools/pytest_shim` only serve the Windows sandbox with a restricted
  token.
- The only explicitly Windows branch left is the creation date in
  `stat`: `st_birthtime` where available, otherwise `st_ctime` on
  Windows; on Linux `created_at` can be `None`.
- The external APIs (OAuth, MCP, LLM) use HTTP and `webbrowser`, not system
  commands.
- The GitHub Actions CI covers Linux, macOS and Windows on Python
  3.11/3.12/3.13; symlinks, OAuth token permissions and loopback callbacks
  remain to be verified with live tests, not in the offline suite.

---

# 6. Known limits and technical debt

- `PermissionEvaluator` covers v1: dynamic subjects, GUI
  confirmations and MCP capabilities assigned by the configuration remain.
- Native calling depends on the model: some ignore the tools or
  return several calls; the textual fallback covers errors, not
  the quality of the choice.
- The MCP client supports bearer/header and OAuth authorization code; it does not
  handle device flow, DPoP, mTLS or client assertion.
- Skill review is manual from the CLI; a GUI is missing.
- Memory search is by keyword, without an index or
  embeddings.
- The injected context uses recent global turns and up to 3 confirmed
  skills by lexical match, without semantic selection.
- Memory does not delete chats or skills by age: `archive` is
  the only removal from the context.
- The audit has rotation and retention (`max_files`), but not compaction
  of the sessions nor an external anchoring of the chain.
- `feed.read` validates the addresses and the redirects, but the DNS
  rebinding case remains: `requests` resolves the name a second time at
  connection time; a pinned resolver is needed.
- The calculator is not a CAS: it only handles limited numeric
  expressions, not symbolic ones.
- `stat().created_at` is `None` on Linux when `st_birthtime` is missing; a
  creation date is not invented.
- Two aliases cannot point to the same physical path: the alias
  identifies a mount and the virtual output must remain unique.

## 6.1 User responsibility: hard links, mounts and TOCTOU

**Hagar does not check hard links, mounts/junctions and TOCTOU races
inside the allowed directories.** This is not a defect of Hagar: the sandbox is
path-based and does not use handles/file descriptors for the whole operation.

A hard link is a second name of the same inode, it has no path target
and the sandbox cannot know whether another name exists outside. A
mount or a junction can expose another filesystem while remaining inside
the path prefix. A TOCTOU race can change a component between the
symlink check and the real operation: Hagar does not use `openat2`,
`O_NOFOLLOW` on every component or Windows handles, therefore it does not guarantee
atomicity between check and access.

Hagar's filesystem tools do not create hard links. If a hard link or a
mount already exists inside a sandbox directory, Hagar treats it as
a normal file or directory and can read it, modify it or delete its
internal name.

The responsibility is therefore divided:

- **Hagar guarantees** that the resolved paths stay inside the alias at
  the time of the check, that symlinks are invisible, that the `R`/`W`/`X`
  permissions are applied and that the real paths do not end up
  in the model's output.
- **The user guarantees** that the directories configured in
  `filesystem.sandbox` do not contain hard links, mounts or junctions to
  content that must not be accessible, and that no untrusted
  concurrent process can modify those directories during
  execution, if total isolation is wanted.

TOCTOU races require a concurrent local actor with write access
to the sandbox directories: they are not an accidental case
of normal use, but a malicious scenario or a compromised environment.
Strong isolation requires a dedicated volume, a separate user,
a mount namespace or a container; it is not the job of the path
resolver.

The points are closed as **user responsibility**, not as technical
debts of Hagar. Hard links, mounts/junctions and TOCTOU races are not
detected or blocked by this version.

---

# 7. Documentation map

- `MANUAL.md` — user manual: commands, configuration, policies, defaults.
- `ARCHITECTURE.md` — this document: how the system is today.
- `ROADMAP.md` — what to do, decisions made and open points.
- `CHANGELOG.md` — history of the versions.
- `README.md` — start-up, configuration, tests.
