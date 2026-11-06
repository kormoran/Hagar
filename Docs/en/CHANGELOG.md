# HAGAR — Changelog

The format is free but stable: versions in descending order, with a
reference to the commit when useful.

---

# 0.3.0 — 2026-11-05

## Project memory, summary and archive

- New project memory separate from skills:
  `Hagar/projects/<id>/index.md` and `decisions/<date>-<slug>.md`, with
  state `candidate`/`active`/`superseded`/`archived`, alternatives,
  rationale, provenance and `auto_saved`.
- At start-up Hagar shows the active projects and “free activity”; commands
  `/project list|new|select|free|status` and overrides `--project`/`--free`.
- At the end of the session the transcript is moved to `archive/chat/` and
  replaced by a summary with link and hash; mechanical fallback if the
  model is not available.
- Project decisions are proposed as `candidate` and reviewed
  at the end of the session; if the user refuses, they remain candidates with
  `auto_saved: true`.
- Index-based context: summary and titles of the active decisions, not the
  bodies; details with `memory.project_context`. Budget
  `max_context_chars` (characters, not tokens) and audit
  `memory.context_trimmed`.
- `project_max_active` triggers the request to archive the
  project; archiving is reversible and deletes nothing.
- If the `projects` directory is not writable, memory stays active
  and projects are disabled with `project.disabled`.
- Archive consultation: `memory.archive_search` and
  `memory.archive_read`, commands `/memory archive search|read`, with
  a filter by project and a transcript that keeps `project` in the
  frontmatter. The archive is never injected automatically.

## Console commands and manual

- New chat commands: `/help`, `/tools [category]`, `/status`, `/mcp`,
  `/audit [n]`.
- `/tools` groups the tools by category and shows the capabilities.
- `/status` reports model, calling, project, memory, audit and
  filesystem.
- `/mcp` lists configured servers, endpoints and imported tools.
- `/audit` reads the latest events of the current log, without exposing the
  unselected fields.
- Unknown `/` commands are not sent to the model.
- New `Docs/it/MANUAL.md` with commands, CLI, `hagar.yaml`,
  `policy.yaml`, defaults and behaviours in case of error.

## MCP, OAuth and clean exit

- MCP client updated to `MCP-Protocol-Version` `2025-06-18` with
  fallback, reuse of `Mcp-Session-Id` and HTTP body in the errors.
- OAuth: optional `audience`, `prompt=consent` with `offline_access`,
  callback `http://localhost:<port>/oauth/callback`, scope in the
  dynamic registration.
- Ctrl-C during OAuth or a turn closes the local callback and exits with
  code 130, without a traceback.

## Local tools and filesystem v2

- New `local_tools/` directory for the local providers: calculation, statistics,
  unit conversion, time/date and feeds. They are not MCP servers: they register
  `ToolDefinition` in the registry.
- Tools added: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `clock.now`, `calendar.date`, `think.echo`,
  `text.diff`, `url.parse`, `feed.read`.
- Filesystem: `list_dir`, `read_chunk`, `rename`, `copy_file`, `search`.
- New capabilities `COMPUTE` (local calculations, always in the ceiling) and
  `NETWORK` (enabled by `permissions.network: true`); `feed.read`
  requires `NETWORK`.
- `permissions.network` in the configuration; policy: `COMPUTE` allow for
  calculator/statistics/units, `NETWORK` ask for feed.
- `feedparser` among the dependencies; the feed is downloaded with
  `requests`, with timeout and a 5 MB limit, and only from http/https URLs.
- SSRF: mandatory DNS resolution, global addresses only
  (no loopback, private networks, link-local, multicast or reserved),
  manual revalidated redirects (maximum 3) and refusal of URLs with
  credentials.
- Restored the sandbox's `rename` permission, lost during the
  extension; `filesystem.rename` requires `rename` on the source and
  `create` on the destination.
- Renamed `MCP_tools/` → `local_tools/`: they are local providers, not
  MCP servers; package, imports, tests and documentation updated.
- Filesystem with virtual root `/home/ai`: `stat`, `list_dir`,
  `search`, `read_chunk` and the tool messages no longer expose the
  physical path; `/home/ai/...` inputs are accepted.
- `read_chunk` aligns the boundaries to UTF-8 characters and returns
  `next_offset`; it no longer splits multibyte characters.
- `read_file` refuses files above 4096 bytes and points to `read_chunk()`
  to avoid loading the whole file into the context window.
- `list_dir` returns at most 100 entries per page and `search` 100
  results (maximum 500); both support `offset`, `next_offset`,
  `has_more` and the message
  `voci: riportate X di Y; per continuare usa offset=Z`. For large
  trees it is better to narrow pattern/path instead of iterating pages.
- New write limits `filesystem.limits`:
  `max_write_bytes` per operation, `min_free_bytes` as a reserve,
  cumulative `session_write_bytes` and `ask_over_bytes` for confirmation.
  The first three are invariants; `ask_over_bytes` goes through the preflight of
  `ToolRegistry` and asks only once, even if the policy is `ASK`.
- Symlinks do not exist for the sandbox: they are not shown, read,
  followed or deleted; `chdir` on a link answers
  “Directory not found”. Project decision: they stay invisible
  even if the host filesystem supports them.
- Hard links, mounts and junctions inside the allowed directories are not
  checked or detected by Hagar. This is not a defect: a hard link is a
  second name of the same inode and a mount can expose another
  filesystem while remaining inside the prefix. The filesystem tools do not create
  hard links. For total isolation the user must ensure that there are none in the
  sandbox directories. User responsibility,
  point closed.
- TOCTOU: this version does not use `openat2`, `O_NOFOLLOW` on every
  component or Windows handles, therefore it does not guarantee atomicity between check
  and operation. The race requires a concurrent local process with
  write access: malicious scenario or compromised environment, not
  normal use. Closed as user responsibility; for total isolation
  a dedicated volume, a separate user, a mount namespace or a
  container are needed.
- `filesystem.allowed` replaced by `filesystem.sandbox`: every entry has
  `alias`, `path` and permissions `R`/`W`/`X`. The agent sees
  `/home/ai/<alias>/...`; no `hdN`, no volumes or synthetic
  intermediate directories. `/home/ai` lists the aliases but is not a mount.
- Permissions per alias: `R` reading/listing/searching/stat, `W`
  writing/creating/renaming/copying/deleting, `X` `chdir`; the
  global permissions remain a ceiling.
- Mandatory alias, single segment, unique case-insensitively, without
  reserved Windows names; the sandbox entries remain host system
  paths and Hagar does not create directories. Physical paths and internal names
  can contain spaces; the alias cannot.
- POSIX runner `tools/run_tests.sh`; `run_tests.ps1` and the shim remain
  specific to the Windows sandbox. Benchmark commands updated.
- Cross-platform fix from the CI: `vault_subdir` also rejects paths with
  a Windows drive (`I:/...`) on POSIX; the symlink refusal is no longer
  swallowed by `except OSError`, so the path is not resolved
  outside the sandbox.
- 691 tests passed, 2 skipped on Windows; 693 passed, 0 skipped on Debian
  Linux (2026-11-06), including the symlink tests.

## Release and cross-platform

- Version `0.3.0` in `pyproject.toml` and `hagar.py`.
- GitHub Actions CI on Linux, macOS and Windows with Python 3.11, 3.12 and
  3.13; package build, `twine check` and wheel smoke test.
- Actions updated to `checkout@v7`, `setup-python@v7` and
  `upload-artifact@v7`, all on Node 24; the Node 20 deprecation
  warning was removed.
- Release workflow on `v*` tags: sdist/wheel build, check that the tag
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
- Commands `/memory list`, `/memory show`, `/memory review`,
  `/memory confirm`, `/memory archive`.
- Automatic injection of confirmed skills only, up to
  `memory.context_skills` (default 3), by lexical match; candidates
  and archived ones stay out.
- `reviewed_at` in the frontmatter; audit events `memory.review` and
  `memory.status`.
- Retention option A: no automatic deletion; `archive` is
  reversible with `confirm`.
- `memory.context_skills` in the configuration; 552 tests passed, 1 skipped.

## Interactive MCP OAuth

- Authorization code + PKCE flow with callback on `127.0.0.1` and
  browser opening; manual fallback by pasting the URL.
- RFC 9728 (protected resource) and RFC 8414 (authorization
  server) discovery, with dynamic client registration if `client_id` is missing.
- Local token cache with `0600` permissions, automatic refresh and one
  retry on `401`.
- Config `auth.type: oauth` with `authorization_server`, `client_id`,
  `client_secret_env`, `scopes`, `redirect_port`, `token_cache`,
  `timeout`.
- Limits: no device flow, DPoP, mTLS or client assertion.
- 522 tests passed, 1 skipped.

## Audit retention

- Rotation to `<file>.<timestamp>` beyond `audit.max_bytes`.
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
- No universal winner: the default stays native, with opt-out per
  model through `model.native_tools` or `--no-native-tools`.

## DeepSeek (live)

- Updated models: `deepseek-flash` (default) and `deepseek-v4-pro`;
  `deepseek-chat` is no longer valid.
- Error messages with the API response body; non-ASCII keys
  rejected with `ConfigError`.
- Tool names normalized for APIs that do not allow the dot
  (`filesystem.read_file` → `filesystem__read_file`), with a return to the
  internal name.
- `tools/diagnose_deepseek.py` for network, key shape and endpoint,
  without printing the key.
- Live tests: chat, native calling and end-to-end on the filesystem.
- 479 tests passed, 1 skipped; 9 live tests with `--live`.

## Native calling (v1)

- `LLMClient.native_step()` and `LLMReply`: native calling for Ollama,
  DeepSeek, Claude and Gemini; parameter schema from `ToolDefinition`.
- Canonical `assistant` messages with `tool_calls` and `tool` with
  `tool_call_id`; every backend translates them (`tool_calls`, `tool_use`/
  `tool_result`, `functionCall`/`functionResponse`).
- The Agent executes several calls per turn, within the `max_tool_calls` limit.
- Automatic fallback to the textual protocol on HTTP 400/404/422 at the first
  step, with the `llm.native_fallback` event; `model.native_tools: false` and
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
- automatic injection of the latest `memory.context_turns` turns into the
  prompt, with truncation; a memory error does not make the turn fail;
- tools `memory.create_skill` (provenance and `candidate` state),
  `memory.list_skills`, `memory.get_context` (keyword search);
- capability `MEMORY_READ`/`MEMORY_WRITE`, namespace `chat`/`skills` for
  the policies;
- `memory.*` configuration and deactivation with a warning if the vault
  is missing;
- audit events `memory.enabled`, `memory.disabled`, `memory.context`,
  `memory.turn`, `memory.failed`;

## Permissions (PermissionEvaluator v1)

- new `core/permissions.py`: `Capability` (IntFlag), `Effect`
  (`ALLOW` / `ASK` / `DENY`, with deny-overrides), `Rule` with scope per
  tool, path and namespace, `Subject`, `Resource`, `Decision` and a pure
  evaluator;
- separate `policy.yaml`, read before building the LLM: in case of
  error every policy becomes `DENY`, with the `policy.failed` event and
  a warning in the chat;
- system ceiling derived from `permissions.read/write/shell`;
- `ASK` with console confirmation (`lo faccio? (y/N)`, default N) and
  `ConfirmationProvider` for future GUIs;
- `ToolRegistry.execute` applies the policy and records
  `permission.decision` and `permission.confirmation`;
- `ToolDefinition.capabilities` for all tools (filesystem and MCP);
- `requires_confirmation` now applied as an ASK floor;
- removed the incomplete `PolicyRule` stub from `core/models.py`;

## Filesystem v2, mathematical tools and feeds

### Filesystem

- `filesystem.list_dir`: non-recursive listing of the contents of a directory.
- `filesystem.list_dir` returns complete metadata through `FileInfo` for every element found.
- `filesystem.read_chunk`: incremental reading of large files through offset and length.
- `filesystem.read_chunk` works at the byte level and returns `has_more` to let the agent continue reading.
- `filesystem.rename`: renames or moves files inside the sandbox.
- `filesystem.copy_file`: copies files with verification of the permissions and of the available space.
- `filesystem.search`: recursive search through glob patterns (`*.py`, `*.md`, etc.).
- `filesystem.search` returns:
  - total number of results found;
  - number of results returned;
  - truncation indication (`truncated`);
  - list of results as `FileInfo`.
- Improved autonomous exploration of the sandbox: the agent can now enumerate directories, search for files and read very large documents without saturating the context window.

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

### RSS and Atom feeds

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

This iteration significantly widens the operational capabilities of the agent. Besides the sandboxed filesystem, Hagar now has reliable tools to:

explore and search for content;
read very large files incrementally;
perform deterministic mathematical calculations;
carry out statistical analyses;
convert units of measurement belonging to different domains;
consume structured information sources through RSS and Atom feeds.

The goal remains to favour deterministic, structured tools that are easy for the models to use through native tool calling.


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
  `LLMClient` shares tool selection, JSON parsing and repair; every backend
  implements only the transport and the role conversion.
- **`filesystem.stat`**: type, size in bytes, ISO 8601 dates and
  effective sandbox permissions, in a single measurement.
- **Test suite**: 259 tests, 1 skipped, without network (Ollama and MCP
  simulated), with `tools/run_tests.ps1` and a shim for the Windows
  sandbox.
- **`tools/bench_models.py`**: reproducible comparison of the Ollama models
  on reading, metadata, creation and chat.

## Changed

- `model.provider` really selects the backend (before it was ignored and
  Ollama was always used). API keys from the environment, never from the YAML.
- Default model: `llama3.1:latest` instead of `qwen3:8b`.
- Tool results are `user` turns and not `system`, for compatibility
  with the remote backends.
- Configuration errors: clean exit (`SystemExit 1`) with a message
  on stderr and an `llm.failed` event in the audit.

## Fixed

- `core/filesystem.py` was truncated in the middle of `mkdir`: `read_file`, `write_file`, `create_file`, `delete_file`,
  `free_space` were missing. Every filesystem tool failed with `AttributeError`.
- `ToolDefinition.origin` was mandatory but no provider passed it:
  the registration of any tool failed with `TypeError`.
- `ToolResult` used `tool` while the `Agent` used `tool_name`.
- `llm/ollama_client.py` used `re` without importing it and defined
  `_tool_call_from_json` twice.
- `hagar.py` read non-existent fields of `AppConfig`: `main()` did not
  start.
- `ConfigLoader` did not validate empty YAML, non-mapping roots, non-boolean
  permissions, `allowed` not a list.
- `write_file` could create new files bypassing the `create` permission.
- The parsing accepts the `parameters` alias; a prose response produces
  a single repair attempt, then an explicit error.

## Notes

Ollama model comparison (4 tasks, temporary sandbox, maximum 4 tools per
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
to Ollama, it is an operating agent.

## Added

- loading and validation of the YAML configuration;
- `OllamaClient` with `generate`, `chat`, `request_tool_call`;
- `ToolRegistry`, `ToolDefinition`, `ToolCall`, `ToolResult`;
- `Agent` with multi-step loop, error handling and tool limit;
- `FileSystemSandbox` with roots, inheritable permissions, protection from
  symlinks and disk space check;
- filesystem tools: reading, writing, creation, deletion,
  directory creation, directory change, free space;
- MCP client over HTTP with automatic discovery of the tools and namespace;
- initial `Vault` for the Markdown files.

## Notes

v0.1 is the first version able to talk to a local LLM,
expose tools, let the model choose which ones to use, operate on a
sandboxed filesystem and chain several operations autonomously.
