# HAGAR — Changelog

The format is free but stable: versions in descending order, with a
reference to the commit when useful.

---

# 0.5.2 — 2026-11-08

## Summary

Consolidation release: SQLite memory, subagents, vision, decision
tools, model cards, Markdown import/export and CLI input broker.

## Breaking changes

- the default memory is no longer the Markdown Vault: it uses
  `%LOCALAPPDATA%/Hagar/memory.db` or `HAGAR_MEMORY_DB`;
- the Vault is not imported automatically;
- the `markdown` backend remains available only as legacy;
- `memory.database` and `decisions.*` are new configuration sections.

## New LLM backends

- New `lmstudio` backend for LM Studio's local OpenAI-compatible
  server, default `http://localhost:1234/v1`, without a key unless
  the server is configured that way.
- New `openai` backend (alias `chatgpt`) for the OpenAI Chat
  Completions API, key `OPENAI_API_KEY`, configurable base URL.
- The two backends share the OpenAI-compatible client, with native
  tool calling and textual JSON fallback on HTTP 400/404/422.
- Configurable `model.timeout` (default 120 s), passed to all
  backends; useful for large local models.
- `hagar.example.yaml` and the Italian documentation updated.

## Service layer

- New `core/service.py` with `HarnessService`: turns, status, project,
  end of session and structured events (`ServiceEvent`).
- `hagar.py` uses the service for `ask`, project selection and session
  closing; the CLI remains an adapter.
- `tool.call`, `tool.result`, `permission.decision` and
  `permission.confirmation` events forwarded by `Agent` and `ToolRegistry` to the
  service sink; the tool output is truncated in the events.
- New `CommandService` for `/help`, `/tools`, `/status`, `/mcp`,
  `/audit`, `/project` and `/memory`, with a structured `CommandResult`.
- The CLI uses the command service for the slash commands; `/memory review`
  remains interactive.
- New `QueueConfirmationProvider`: ASK confirmations from the GUI with a queue,
  timeout and explicit refusal.
- New local web GUI (`hagar web`): chat, SSE events, status, projects,
  tool calls and confirmation modal; local token and `127.0.0.1` bind.
- Browser SSE disconnections no longer produce tracebacks on
  Windows (`ConnectionAbortedError`/WinError 10053).
- Ctrl-C closes `hagar web` immediately: no `shutdown()` from the
  `serve_forever` thread, no join of the SSE threads and summary skipped at
  shutdown.
- New `core/usage.py`: OpenAI/DeepSeek/LM Studio, Claude, Gemini and Ollama
  usage parsing, with a `UsageLedger` per session.
- The GUI shows input, output and total tokens in the sidebar, updated
  via the `usage.updated` event.
- GUI HTML, CSS and JavaScript separated into `web/` and served as
  static assets; `core/web.py` injects only the token.
- New `memory/index.py`: incremental and rebuildable SQLite/FTS5 index
  of the Markdown memories, with lexical fallback.
- New `memory.search` tool; `/memory search`, `reindex`,
  `stats` commands.
- Cooperative turn stop (`Agent.cancel`, `POST /api/stop`) with a
  button in the GUI and `turn.cancelled` event.
- Vision image input (`core/images.py`) with data URL, MIME and 10 MB
  limit validation; OpenAI/LM Studio, Claude and Gemini adapters.
- Image upload in the GUI with preview and removal; WebP converted
  to PNG before sending. No image saved in memory or audit.
- GUI JSON body up to 64 MB, to accept high-resolution images in
  base64.
- Chat history in the dedicated tab: list of `chat/` and
  `archive/chat/`; a click resumes the same session and the new turns
  continue the transcript.
- **+ New chat** button with `MemoryStore.new_session()` and context
  reset; the previous transcripts remain in the Vault.
- GUI tabs: Chat, Chat history, Tool output, Audit, Thinking, Memories.
- In-memory `SessionLog` for tool calls/results and timeline;
  `/api/tools`, `/api/audit`, `/api/thinking`.
- Read-only memories browser: `/api/memories`, `/api/memory`.
- `/usage` in the CLI for the cumulative tokens of the session; same ledger
  used by the GUI.
- Tools and LLM providers are plugins: built-in in `local_tools/plugins.py`
  and `llm/plugins.py`, external via the `hagar.tools`/`hagar.llm` entry point.
- Plugin errors isolated and recorded in the audit; policy and sandbox
  remain in the host.
- Documented the design of the document tool in `DOCUMENT_TOOL.md`:
  structure/semantics graph, CSV MVP, `FormatPlugin` contract, C ABI and
  JSON protocol of the native host.
- Asynchronous subagents: `agent.spawn/status/wait/result/cancel`, up to
  two concurrent children, separate LLM client, private workspace with copied
  inputs, read-only registry, memory without writes, denied confirmations,
  dedicated usage and audit; cleanup at the end of the turn.
- Mandatory `reason` at spawn and separate `AGENT_SPAWN` capability:
  the child cannot create others; `permissions.agents` controls the
  system ceiling.
- Subagent policy strictly more restrictive than the parent's; equal or
  not more limited policies are refused.
- 5-minute wall timeout per subagent, cooperative, with `timed_out`
  state; `agent_id` in all audit events.
- Subagent ASKs forwarded to the user with `ParentBridgeConfirmation`,
  180-second timeout and DENY at expiry; the parent LLM does not approve.
- `vision.open` loads PNG/JPEG/WebP from the sandbox and attaches them to the turn;
  `ToolResult.images` and the Agent loop handle the multimodal channel
  without base64 in the text. Audio in the roadmap.
- SQLite memory as primary source: `memory/sqlite_store.py`,
  `memory/database.py`, WAL and backup; `/memory sessions`,
  `/memory chat` and `/memory backup` commands. Projects and decisions in the same
  database; Markdown backend only legacy.
- Markdown export of the database with `/memory export <path> [--force]`:
  chats, skills, summaries, projects and decisions, atomic writing.
- Markdown import with `/memory import <path> [--force]`; FTS5 in the
  primary database with `bm25`/`snippet` and `LIKE` fallback.
- CLI with `ConsoleInputBroker`: a single console reader, attention
  title and ASK confirmations with `F5` allow / `F8` deny; `y/N` fallback.
  The broker saves and restores the terminal, also on Ctrl-C.
- New tool class `decision.*` with `decision.choose`: local/remote LLM
  provider and local linear classifier, validated probabilities,
  `decision.result` audit and `DECISION` capability.
- Model technical cards and benchmarks: `/models list|show|test|hardware`,
  latency, JSON, tool calling, date of the last test and CPU/RAM/GPU
  detection without mandatory dependencies.
- Temporary artifact store and internal mailbox: `artifact.put`,
  `artifact.put_file`, `mailbox.send` for the child; `artifact.read`,
  `artifact.list`, `mailbox.inbox/read/ack` for the parent. `AGENT_DATA`
  capability, quotas and cleanup at the end of the turn.
- `artifact.save_to` copies the whole artifact to a writable path of the
  parent's sandbox; it requires `AGENT_DATA`, `FILESYSTEM_WRITE` and
  `FILESYSTEM_CREATE`, with possible policy confirmation.
- `artifact.discarded` audit at the end of the turn for artifacts not exported,
  with reason `unread` or `read_but_not_saved`; persistence remains
  postponed.
- Audit disabled: tab disabled with the `audit off` label.
- Thinking shows the reasoning exposed by the provider, otherwise the
  event timeline.
- Foundation for the future GUI, without `input()` or `print()` in the service.

# 0.3.0 — 2026-11-05

## Project memory, summaries and archive

- New project memory separate from skills:
  `Hagar/projects/<id>/index.md` and `decisions/<data>-<slug>.md`, with
  state `candidate`/`active`/`superseded`/`archived`, alternatives,
  rationale, provenance and `auto_saved`.
- At start-up Hagar shows the active projects and "free activity"; commands
  `/project list|new|select|free|status` and `--project`/`--free` overrides.
- At the end of the session the transcript is moved to `archive/chat/` and
  replaced by a summary with link and hash; mechanical fallback if the
  model is not available.
- Project decisions are proposed as `candidate` and reviewed
  at the end of the session; if the user refuses, they remain candidates with
  `auto_saved: true`.
- Index-based context: summary and titles of the active decisions, not the
  bodies; details with `memory.project_context`. Budget
  `max_context_chars` (characters, not tokens) and `memory.context_trimmed`
  audit.
- `project_max_active` triggers the project archiving request;
  archiving is reversible and deletes nothing.
- If the `projects` directory is not writable, the memory remains active
  and the projects are disabled with `project.disabled`.
- Archive consultation: `memory.archive_search` and
  `memory.archive_read`, `/memory archive search|read` commands, with
  filter by project and transcript preserving `project` in the
  frontmatter. The archive is never injected automatically.

## Console commands and manual

- New chat commands: `/help`, `/tools [category]`, `/status`, `/mcp`,
  `/audit [n]`.
- `/tools` groups the tools by category and shows the capabilities.
- `/status` reports model, calling, project, memory, audit and
  filesystem.
- `/mcp` lists configured servers, endpoints and imported tools.
- `/audit` reads the last events of the current log, without exposing the
  unselected fields.
- Unknown `/` commands are not sent to the model.
- New `Docs/it/MANUAL.md` with commands, CLI, `hagar.yaml`,
  `policy.yaml`, defaults and error behaviours.

## MCP, OAuth and clean exit

- MCP client updated to `MCP-Protocol-Version` `2025-06-18` with
  fallback, reuse of `Mcp-Session-Id` and HTTP body in the errors.
- OAuth: optional `audience`, `prompt=consent` with `offline_access`,
  `http://localhost:<port>/oauth/callback` callback, scopes in the
  dynamic registration.
- Ctrl-C during OAuth or a turn closes the local callback and exits with
  code 130, without traceback.

## Local tools and filesystem v2

- New `local_tools/` directory for the local providers: calculus, statistics,
  unit conversion, time/date and feeds. They are not MCP servers: they register
  `ToolDefinition` in the registry.
- Added tools: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `clock.now`, `calendar.date`, `think.echo`,
  `text.diff`, `url.parse`, `feed.read`.
- Filesystem: `list_dir`, `read_chunk`, `rename`, `copy_file`, `search`.
- New `COMPUTE` capability (local computations, always in the ceiling) and
  `NETWORK` (enabled by `permissions.network: true`); `feed.read`
  requires `NETWORK`.
- `permissions.network` in the configuration; policy: `COMPUTE` allow for
  calculator/statistics/units, `NETWORK` ask for feed.
- `feedparser` among the dependencies; the feed is downloaded with
  `requests`, timeout and 5 MB limit, and only from http/https URLs.
- SSRF: mandatory DNS resolution, global addresses only
  (no loopback, private networks, link-local, multicast or reserved),
  manual revalidated redirects (maximum 3) and refusal of URLs with
  credentials.
- Restored the sandbox `rename` permission, lost during
  the extension; `filesystem.rename` requires `rename` on the source and
  `create` on the destination.
- Renamed `MCP_tools/` → `local_tools/`: they are local providers, not
  MCP servers; package, imports, tests and documentation updated.
- Filesystem with virtual root `/home/ai`: `stat`, `list_dir`,
  `search`, `read_chunk` and the tool messages no longer expose the
  physical path; `/home/ai/...` inputs are accepted.
- `read_chunk` aligns the boundaries to UTF-8 characters and returns
  `next_offset`; it no longer splits multibyte characters.
- `read_file` refuses files over 4096 bytes and refers to `read_chunk()`
  to avoid loading the whole file into the context window.
- `list_dir` returns at most 100 entries per page and `search` 100
  results (maximum 500); both support `offset`, `next_offset`,
  `has_more` and the message
  `items: showing X of Y; to continue use offset=Z`. For large
  trees it is better to restrict pattern/path instead of iterating pages.
- New write limits `filesystem.limits`:
  `max_write_bytes` per operation, `min_free_bytes` as a reserve,
  cumulative `session_write_bytes` and `ask_over_bytes` for the confirmation.
  The first three are invariants; `ask_over_bytes` goes through the preflight of
  `ToolRegistry` and asks only once, even if the policy is `ASK`.
- Symlinks do not exist for the sandbox: they are not shown, read,
  followed or deleted; `chdir` on a link replies
  "Directory not found". Project decision: they remain invisible
  even if the host filesystem supports them.
- Hard links, mounts and junctions inside the allowed directories are not
  checked or detected by Hagar. It is not a defect: a hard link is a
  second name of the same inode and a mount can expose another
  filesystem while remaining inside the prefix. The filesystem tools do not create
  hard links. For total isolation the user must guarantee that there are none in the
  sandbox directories. User responsibility,
  point closed.
- TOCTOU: this version does not use `openat2`, `O_NOFOLLOW` on every
  component or Windows handles, so it does not guarantee atomicity between check
  and operation. The race requires a concurrent local process with
  write access: a malicious scenario or compromised environment, not
  normal use. Closed as user responsibility; for total isolation
  a dedicated volume, a separate user, a mount namespace or a
  container are needed.
- `filesystem.allowed` replaced by `filesystem.sandbox`: every entry has
  `alias`, `path` and `R`/`W`/`X` permissions. The agent sees
  `/home/ai/<alias>/...`; no `hdN`, no volumes or synthetic intermediate
  directories. `/home/ai` lists the aliases but is not a mount.
- Per-alias permissions: `R` reading/listing/search/stat, `W`
  writing/creation/renaming/copying/deletion, `X` `chdir`; the global
  permissions remain a ceiling.
- Mandatory alias, single segment, unique case-insensitively, without
  reserved Windows names; the sandbox entries remain host system
  paths and Hagar does not create directories. The physical paths and the internal names
  may contain spaces; the alias may not.
- POSIX runner `tools/run_tests.sh`; `run_tests.ps1` and the shim remain
  specific to the Windows sandbox. Benchmark commands updated.
- Cross-platform fix from the CI: `vault_subdir` also rejects paths with a
  Windows drive (`I:/...`) on POSIX; the symlink refusal is no longer
  swallowed by `except OSError`, so the path is not resolved
  outside the sandbox.
- 832 tests passed, 2 skipped on Windows; 834 passed, 0 skipped on Debian
  Linux (2026-11-06), including the symlink tests.

## Release and cross-platform

- Version `0.3.0` in `pyproject.toml` and `hagar.py`.
- GitHub Actions CI on Linux, macOS and Windows with Python 3.11, 3.12 and
  3.13; package build, `twine check` and wheel smoke test.
- Actions updated to `checkout@v7`, `setup-python@v7` and
  `upload-artifact@v7`, all on Node 24; removed the Node 20 deprecation
  warning.
- Release workflow on `v*` tags: sdist/wheel build, verification that the tag
  matches the version and creation of the GitHub release.
- Portable `hagar.example.yaml`; the local `hagar.yaml` and `testvault/` are
  ignored by git.
- `MANIFEST.in`, `SECURITY.md`, `CONTRIBUTING.md` and `RELEASING.md` for the
  first public release.

# 0.2.0 — 2026-11-04

First release with reviewable memory, native calling, MCP auth/OAuth,
audit retention and installable packaging.

## Memory v2

- Lifecycle `candidate` → `confirmed` → `archived`: the LLM proposes,
  the user promotes from the CLI.
- `/memory list`, `/memory show`, `/memory review`,
  `/memory confirm`, `/memory archive` commands.
- Automatic injection of confirmed skills only, up to
  `memory.context_skills` (default 3), by lexical match; candidates
  and archived ones stay out.
- `reviewed_at` in the frontmatter; `memory.review` and
  `memory.status` audit events.
- Retention option A: no automatic deletion; `archive` is
  reversible with `confirm`.
- `memory.context_skills` in the configuration; 552 tests passed, 1 skipped.

## Interactive MCP OAuth

- Authorization code + PKCE flow with callback on `127.0.0.1` and
  browser opening; manual fallback by pasting the URL.
- RFC 9728 (protected resource) and RFC 8414 (authorization
  server) discovery, with dynamic client registration if `client_id` is missing.
- Local token cache with `0600` permissions, automatic refresh and a
  single retry on `401`.
- `auth.type: oauth` config with `authorization_server`, `client_id`,
  `client_secret_env`, `scopes`, `redirect_port`, `token_cache`,
  `timeout`.
- Limits: no device flow, DPoP, mTLS or client assertion.
- 522 tests passed, 1 skipped.

## Audit retention

- Rotation into `<file>.<timestamp>` beyond `audit.max_bytes`.
- `audit.max_files` (default 100) limits the number of audit files,
  including the active one; the oldest backups are deleted.
- The hash chain continues from the most recent backup if the active file
  is missing.
- 504 tests passed, 1 skipped.

## MCP auth

- `mcp_servers[].auth`: `type: bearer` or `type: header`, with
  `token_env` and, for the header, the header name.
- The token is read only from the environment: it does not go into the YAML, the audit or
  the logs.
- Missing or non-ASCII token: the server is skipped with `mcp.failed` and
  the harness keeps going with the others.
- 496 tests passed, 1 skipped.

## Native vs text benchmark

- `tools/bench_native.py`: 9 filesystem tasks on the same registry,
  comparison between `native_step()` and `request_tool_call()`, with accuracy,
  latency and repairs.
- First measurements: `llama3.1` 4/5 vs 5/5, `qwen3:8b` 4/5 vs 5/5,
  `hermes3:8b` 4/5 vs 3/5, `deepseek-flash` 8/9 vs 9/9 (Ollama subset,
  full DeepSeek suite).
- No universal winner: the default remains native, with opt-out per
  model through `model.native_tools` or `--no-native-tools`.

## DeepSeek (live)

- Updated models: `deepseek-flash` (default) and `deepseek-v4-pro`;
  `deepseek-chat` is no longer valid.
- Error messages with the API response body; non-ASCII keys
  refused with `ConfigError`.
- Tool names normalized for the APIs that do not allow the dot
  (`filesystem.read_file` → `filesystem__read_file`), with return to the
  internal name.
- `tools/diagnose_deepseek.py` for network, key shape and endpoint,
  without printing the key.
- Live tests: chat, native calling and end-to-end on the filesystem.
- 479 tests passed, 1 skipped; 9 live tests with `--live`.

## Native calling (v1)

- `LLMClient.native_step()` and `LLMReply`: native calling for Ollama,
  DeepSeek, Claude and Gemini; parameter schema from `ToolDefinition`.
- Canonical `assistant` messages with `tool_calls` and `tool` messages with
  `tool_call_id`; every backend translates them (`tool_calls`, `tool_use`/
  `tool_result`, `functionCall`/`functionResponse`).
- The Agent executes multiple calls per turn, within the `max_tool_calls` limit.
- Automatic fallback to the textual protocol on HTTP 400/404/422 at the first
  step, with `llm.native_fallback` event; `model.native_tools: false` and
  `--no-native-tools` force it.
- Audit: `turn.start` with `native`, `llm.tool_choice` with `mode=native`.
- 476 tests passed, 1 skipped; 7 live tests with `--live`.

## Hygiene (v1)

- **Packaging**: complete `pyproject.toml` (metadata, dependencies,
  setuptools), `hagar` entry point, single version (`hagar.__version__`);
  `pip install -e .` verified.
- **CLI**: `--config`, `--model`, `--no-memory`, `--version`;
  configuration looked up in `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml`.
- **Live tests**: `live` marker, excluded from the normal suite, `--live`
  for Ollama and remote providers (skipped without a key).
- **MCP**: `text/event-stream` responses, `notifications/initialized`
  notification, normalization of the results to text.
- **Audit**: hash chain (`prev`/`hash`, `verify_chain`), rotation at
  `max_bytes`, redaction of the tool output with `include_outputs`.
- **Base URL**: `model.host` used by all providers.
- **Legacy**: removed `tools/filesystem.py` and `llm/tool_result.py`.
- 442 tests passed, 1 skipped; 6 live tests with `--live`.

## Memory (v1)

- `memory/store.py`: episodic memory (one note per session in
  `<vault>/Hagar/chat/`) and semantic memory
  (`<vault>/Hagar/skills/<slug>.md`);
- automatic injection of the last `memory.context_turns` turns into the
  prompt, with truncation; a memory error does not make the turn fail;
- `memory.create_skill` (provenance and `candidate` state),
  `memory.list_skills`, `memory.get_context` (keyword search) tools;
- `MEMORY_READ`/`MEMORY_WRITE` capability, `chat`/`skills` namespace for
  the policies;
- `memory.*` configuration and disabling with a warning if the vault
  is missing;
- `memory.enabled`, `memory.disabled`, `memory.context`,
  `memory.turn`, `memory.failed` audit events;

## Permissions (PermissionEvaluator v1)

- new `core/permissions.py`: `Capability` (IntFlag), `Effect`
  (`ALLOW` / `ASK` / `DENY`, with deny-overrides), `Rule` with scope by
  tool, path and namespace, `Subject`, `Resource`, `Decision` and
  pure evaluator;
- separate `policy.yaml`, read before building the LLM: in case of
  error all policies become `DENY`, with `policy.failed` event and
  warning in the chat;
- system ceiling derived from `permissions.read/write/shell`;
- `ASK` with console confirmation (`shall I do it? (y/N)`, default N) and
  `ConfirmationProvider` for future GUIs;
- `ToolRegistry.execute` applies the policy and records
  `permission.decision` and `permission.confirmation`;
- `ToolDefinition.capabilities` for all tools (filesystem and MCP);
- `requires_confirmation` now applied as an ASK floor;
- removed the incomplete `PolicyRule` stub from `core/models.py`;

## Filesystem v2, math tools and feed

### Filesystem

- `filesystem.list_dir`: non-recursive listing of the contents of a directory.
- `filesystem.list_dir` returns complete metadata through `FileInfo` for each found element.
- `filesystem.read_chunk`: incremental reading of large files through offset and length.
- `filesystem.read_chunk` works at byte level and returns `has_more` to let the agent continue reading.
- `filesystem.rename`: renames or moves files inside the sandbox.
- `filesystem.copy_file`: copies files with permission and available space checks.
- `filesystem.search`: recursive search through glob patterns (`*.py`, `*.md`, etc.).
- `filesystem.search` returns:
  - total number of results found;
  - number of results returned;
  - truncation indication (`truncated`);
  - list of results as `FileInfo`.
- Improved autonomous exploration of the sandbox: the agent can now enumerate directories, search files and read very large documents without saturating the context window.

### Calculator

- New `local_tools/calculator.py` class.
- Parsing through a safe AST, without using `eval()`.
- Support for:
  - `+`
  - `-`
  - `*`
  - `/`
  - `//`
  - `%`
  - `**`
  - parentheses.
- Mathematical constants:
  - `pi`
  - `e`
- Supported functions:
  - `sqrt`
  - `abs`
  - `sin`
  - `cos`
  - `tan`
  - `asin`
  - `acos`
  - `atan`
  - `log`
  - `log10`
  - `exp`
  - `floor`
  - `ceil`
  - `round`
- New MCP tool:

  `calculator.evaluate`

All operations are validated through a whitelist of AST nodes, operators and allowed functions.

### Statistics

New local_tools/statistics.py class.

New MCP tool:

`statistics.compute`

The class is `Stats_calc`; the tool exposed to the model is
`statistics.compute`. Supported operations:

- mean
- median
- stdev
- variance
- min
- max
- sum
- count

Structured results with:

- outcome of the operation;
- type of statistic requested;
- number of samples processed;
- result or error.

### Unit conversion

New `local_tools/unit_converter.py` class.

New MCP tool:

`units.convert`

Support for the categories:

Length

- mm
- cm
- m
- km

Mass

- mg
- g
- kg
- t

Time

- ms
- s
- min
- hour
- day

Temperature

- c
- f
- k

Angle

- deg
- rad

Data size

- b
- kb
- mb
- gb
- tb

Alias system and unit normalization:

meters → m
kilometers → km
hours → hour
celsius → c
fahrenheit → f
degrees → deg
etc.

Dedicated conversions for:

temperature (with offset);
angles (degrees/radians).

Linear conversions for all the other categories.

### RSS and Atom feed

New `local_tools/feeder.py` class.

New MCP tool:

`feed.read`

Transparent support for RSS and Atom feeds through a single API.

max_items parameter with a safety limit to avoid excessive output.

Structured extraction of:

- title;
- link;
- publication date;
- author;
- summary.

Automatic cleaning of the HTML present in the feeds and return of the feed metadata:

- title;
- description;
- link;
- type (rss, atom, etc.).

Return of the total number of available items, number of items returned and truncation indication.

### Notes

This iteration significantly expands the operational capabilities of the agent. In addition to the sandboxed filesystem, Hagar now has reliable tools to:

explore and search contents;
read very large files incrementally;
perform deterministic mathematical calculations;
carry out statistical analyses;
convert units of measurement belonging to different domains;
consume structured information sources through RSS and Atom feeds.

The goal remains to favour deterministic, structured tools that are easy to use by the models through native tool calling.


## Documentation

- `PROJECT_STATE.md` split into `ARCHITECTURE.md` (how the system is),
  `ROADMAP.md` (what to do and decisions made) and this `CHANGELOG.md`.
- Roadmap updated with the decisions of 2026-11-03: memory on Vault,
  native tool calling, `PermissionEvaluator`.

---

# 0.2.0 — 2026-11-03 (in development)

Commit: `137c985` — *Debug, test suite, audit log and multiple backends*

## Added

- **Audit log** (`core/audit.py`): append-only JSON Lines with UTC
  timestamp, `session` and `turn` id. Events for session, turn, tool
  choice, protocol, execution, errors, MCP and provider. Best effort
  writing, configurable truncation, no API key in the log.
- **Multiple backends** (`llm/base.py`, `llm/factory.py`,
  `deepseek_client.py`, `claude_client.py`, `gemini_client.py`):
  `LLMClient` shares tool selection, JSON parsing and repair;
  each backend implements only the transport and the conversion of the
  roles.
- **`filesystem.stat`**: type, size in bytes, ISO 8601 dates and
  effective sandbox permissions, in a single measurement.
- **Test suite**: 259 tests, 1 skipped, without network (Ollama and MCP
  simulated), with `tools/run_tests.ps1` and a shim for the Windows sandbox.
- **`tools/bench_models.py`**: reproducible comparison of the Ollama
  models on reading, metadata, creation and chat.

## Changed

- `model.provider` really selects the backend (before it was ignored and
  Ollama was always used). API keys from the environment, never from the YAML.
- Default model: `llama3.1:latest` instead of `qwen3:8b`.
- Tool results are `user` turns and not `system`, for compatibility
  with the remote backends.
- Configuration errors: clean exit (`SystemExit 1`) with message
  on stderr and `llm.failed` event in the audit.

## Fixed

- `core/filesystem.py` was truncated in the middle of `mkdir`: `read_file`,
  `write_file`, `create_file`, `delete_file`,
  `free_space` were missing. Every filesystem tool failed with `AttributeError`.
- `ToolDefinition.origin` was mandatory but no provider passed it:
  registering any tool failed with `TypeError`.
- `ToolResult` used `tool` while the `Agent` used `tool_name`.
- `llm/ollama_client.py` used `re` without importing it and defined
  `_tool_call_from_json` twice.
- `hagar.py` read nonexistent `AppConfig` fields: `main()` did not
  start.
- `ConfigLoader` did not validate empty YAML, non-mapping roots, non-boolean
  permissions, `allowed` not a list.
- `write_file` could create new files bypassing the `create` permission.
- The parsing accepts the `parameters` alias; a prose answer produces
  a single repair attempt, then an explicit error.

## Notes

Ollama model comparison (4 activities, temporary sandbox, max 4 tools per
turn):

| model | read | stat | create | chat | repairs |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | loop, 4 tools | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | wrong tool | wrong file | wrong content | ok 6.4 s | 3 |

---

# 0.1.0 — 2026-11-02

Commit: `03b35bf` — *version 0.1 alpha*

First really working version: Hagar is no longer an interface
to Ollama, it is an operational agent.

## Added

- loading and validation of the YAML configuration;
- `OllamaClient` with `generate`, `chat`, `request_tool_call`;
- `ToolRegistry`, `ToolDefinition`, `ToolCall`, `ToolResult`;
- `Agent` with multi-step loop, error handling and tool limit;
- `FileSystemSandbox` with roots, inheritable permissions, symlink
  protection and disk space check;
- filesystem tools: reading, writing, creation, deletion,
  directory creation, directory change, free space;
- MCP client over HTTP with automatic tool discovery and namespace;
- initial `Vault` for the Markdown files.

## Notes

v0.1 is the first version able to dialogue with a local LLM,
expose tools, let the model choose which ones to use, operate on a
sandboxed filesystem and chain multiple operations autonomously.
