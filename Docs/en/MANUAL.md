# HAGAR — User manual

Version: **0.5.2**

This manual describes the observable behaviour of Hagar: commands,
options, configuration, policies and error cases. For the internal design
see [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

# 1. Quick start

Requirements: Python 3.11 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

cp hagar.example.yaml hagar.yaml
mkdir -p vault logs

hagar --config hagar.yaml
```

On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item hagar.example.yaml hagar.yaml
New-Item -ItemType Directory -Force vault, logs
hagar --config hagar.yaml
```

`hagar.yaml`, `testvault/` and `logs/` are local and must not be versioned.

## 1.1 Start-up order

1. Hagar reads the configuration.
2. It loads `policy.yaml`; if it is not valid, it applies `DENY` to everything.
3. It builds the LLM client.
4. It initializes the Vault and the memory, if configured.
5. It builds the filesystem sandbox.
6. It registers the local tools.
7. It tries to load the MCP servers; a failed server does not stop the others.
8. It shows the project choice.
9. It enters the chat loop.

---

# 2. Chat commands

Commands start with `/`. An unknown command **is not sent to the
model**: Hagar replies `Unknown command` and suggests `/help`.

## 2.1 Global commands

| Command | Behaviour |
|---|---|
| `/help` or `/?` | lists the available commands |
| `/tools [category]` | lists the tools and the capabilities; the filter is optional |
| `/status` | shows model, project, memory, audit and sandbox |
| `/usage` | shows the tokens consumed in the session |
| `/models ...` | cards, benchmarks and hardware for the broker |
| `/models hardware` | detects the machine's CPU, RAM and GPU |
| `/mcp` | lists MCP servers, endpoints and imported tools |
| `/audit [n]` | shows the last `n` events; default 10, maximum 50 |
| `exit` | exits |
| `quit` | exits |
| `Ctrl-D` | exits |
| `Ctrl-C` | interrupts; during OAuth it exits with code 130 |

`/status` and `/audit` are human commands: they do not go through the model
and do not consume tool calls.

## 2.2 Project

| Command | Behaviour |
|---|---|
| `/project` or `/project list` or `/project ls` | lists the active projects |
| `/project new <name>` | creates a project and selects it |
| `/project select <id>` or `/project use <id>` | selects an active project |
| `/project free` or `/project none` | switches to free activity |
| `/project status` or `/project current` | shows the current project |
| `/project archive <id>` | archives a project |
| `/project unarchive <id>` | reactivates an archived project |
| `/project help` | help |

`select` and `archive` use the project **id**, not the title.

In free activity, project memory is neither read nor written; chats,
summaries and skills remain available.

## 2.3 Memory

| Command | Behaviour |
|---|---|
| `/memory` or `/memory help` or `/memory ?` | help |
| `/memory list [candidate\|confirmed\|archived]` | lists the skills and the counts |
| `/memory show <slug>` | shows a skill |
| `/memory search <text>` | searches the SQLite memories |
| `/memory sessions` | lists the recorded chats |
| `/memory chat <session>` | shows the turns of a chat |
| `/memory reindex` | optimizes/rebuilds the SQLite indexes |
| `/memory stats` | state and counts of the database |
| `/memory backup <path>` | consistent copy of the database |
| `/memory export <path> [--force]` | exports chats, skills, summaries and projects to Markdown |
| `/memory import <path> [--force]` | imports a Markdown structure into the database |
| `/memory review` | interactive review of the candidates |
| `/memory confirm <slug>` | confirms a skill |
| `/memory archive <slug>` | archives a skill |
| `/memory archive search <text>` | searches the archived transcripts |
| `/memory archive read <session> [offset] [limit]` | reads an archived transcript |

The words `search` and `read` are reserved: a skill slug called
exactly `search` or `read` cannot be archived with this command.

There is no delete command: you can only archive.

The default backend is SQLite (`memory.backend: sqlite`). The database
lives in the app's local data, not in the Vault:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

or `HAGAR_MEMORY_DB`. The `markdown` backend remains only for
compatibility. The Vault is no longer updated by the SQLite backend.

## 2.4 What is not a command

The tools (`filesystem.*`, `memory.*`, `mcp.*`, `clock.now`, ...) are
called by the model through the registry. They are not typed as `/tool`.
The only exception are the informational commands `/tools`, `/status`, `/models`, `/mcp`,
`/audit`, which are console commands and not tools.

---

# 3. Command line

```text
hagar [options]
hagar web [options]
```

| Option | Effect |
|---|---|
| `--config PATH` | uses an explicit configuration file |
| `--model NAME` | overrides `model.name` |
| `--project NAME` | selects an active project at start-up |
| `--free` | starts in free activity |
| `--no-memory` | disables memory and projects for the session |
| `--no-native-tools` | forces the textual JSON protocol |
| `--host HOST` | host of the web GUI (default `127.0.0.1`) |
| `--port PORT` | port of the web GUI (default `8765`) |
| `--version` | prints the version |

`--project` and `--free` are mutually exclusive.

## 3.0 Web GUI

```bash
hagar web
hagar --config hagar.yaml web --port 8765
```

It opens a local GUI at `http://127.0.0.1:8765/`.

- The server is meant for a single local user: default `127.0.0.1`.
- The browser receives a random token in the page; the APIs require it
  in the `X-Hagar-Token` header.
- The chat shows turns, tool calls, results and ASK confirmations.
- At the top there are the tabs **Chat**, **Chat history**, **Tool output**,
  **Audit** and **Thinking**.
- **Chat history** lists the past chats, one row per chat; a click
  resumes the chat: the transcript is reloaded from the database and the new
  turns are added to the same session.
- The **+ New chat** button opens a new session and resets the
  context; the previous chat remains in the history.
- **Memories** is a read-only browser of the indexed notes
  (skills, projects, decisions); it allows searching and opening the text.
- **Tool output** shows the tool calls and the results of the session.
- **Audit** shows the events of the log; if the audit is disabled the tab is
  disabled and shows `audit off`.
- **Thinking** shows the reasoning exposed by the provider, if present;
  otherwise the timeline of the agent's events.
- **Memories** shows the memories and skills of the database in read-only mode, with search.
- The **Stop** button interrupts the turn cooperatively.
- The **Image** button attaches PNG/JPEG/WebP (max 4, 10 MB each)
  for vision models. WebP is converted to PNG in the GUI because LM
  Studio does not accept it directly. Images are not saved
  in the memory or in the audit: the model receives the data URL, not the
  host path.
- The sidebar at the bottom shows the cumulative tokens of the session: input,
  output and total.
- The model can load images from the sandbox with `vision.open`;
  the image is attached to the turn, not returned as base64 in the
  context.
- ASK confirmations are modal: the turn waits and the server
  keeps responding. A timeout is equivalent to a refusal. The requests of the
  subagents show `agent_id` and `parent_id`; the parent LLM cannot
  approve them. The subagent timeout is 180 seconds.
- In the CLI a single thread owns the input. When a confirmation is active,
  the terminal title asks for attention and `F5` =
  allow, `F8` = deny are accepted, in addition to `y/N`. If the terminal does not support the
  function keys, `y/N` and the GUI remain.
- Ctrl-C in the CLI restores the normal terminal mode before
  exiting.
- The GUI is not yet multi-user and does not expose direct changes to the memory.
- Ctrl-C closes the server and attempts to end the session.

Do not use `--host 0.0.0.0` on an untrusted network: the GUI exposes the tools
of the harness to anyone who can reach the port.

## 3.1 Configuration lookup

Order:

1. `--config PATH`
2. the `HAGAR_CONFIG` variable
3. `./hagar.yaml` in the current directory

Relative paths inside `hagar.yaml` — audit, policy, Vault — are
resolved relative to the directory of the configuration file, not to the
directory from which you launch Hagar.

## 3.2 Exit codes

| Code | Meaning |
|---|---|
| `0` | normal exit or `--version` |
| `1` | configuration error or invalid project |
| `130` | interrupted with Ctrl-C |

An MCP error does not change the exit code: it is recorded and the
harness keeps going.

---

# 4. `hagar.yaml`

Minimal example:

```yaml
model:
  provider: ollama
  name: llama3.1:latest

vault:
  path: ./vault

filesystem:
  sandbox:
    - alias: workspace
      path: .
      permissions: RX
```

## 4.1 `model`

| Field | Default | Notes |
|---|---|---|
| `provider` | mandatory | `ollama`, `lmstudio`, `deepseek`, `openai` (`chatgpt`), `claude`, `gemini` |
| `name` | mandatory | model name at the provider |
| `host` | provider default | base URL of the API |
| `native_tools` | `true` | if `false`, uses the textual JSON protocol |
| `max_tokens` | `1024` | used only by Claude |
| `timeout` | `120` | HTTP timeout in seconds for each call |
| `api_key_env` | standard name | environment variable of the key |

Providers and keys:

| Provider | Standard key | Default |
|---|---|---|
| `ollama` | none | `http://localhost:11434` |
| `lmstudio` | none, optional `LMSTUDIO_API_KEY` | `http://localhost:1234/v1` |
| `deepseek` | `DEEPSEEK_API_KEY` | DeepSeek API |
| `openai` / `chatgpt` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `claude` | `ANTHROPIC_API_KEY` | Anthropic API |
| `gemini` | `GEMINI_API_KEY` | Gemini API |

The keys must never be written in the YAML. If a key is missing, the client
is not built and start-up fails with an explicit error. LM Studio
does not require a key, unless the local server is configured to
require one. `chatgpt` is an alias of `openai`: a ChatGPT subscription does not
give access to the API, an OpenAI key and API credit are required.

With LM Studio, native tool calling depends on the model and its
template. If the model accepts the request but answers in text instead
of emitting `tool_calls`, Hagar cannot execute the tool: use
`model.native_tools: false` or a tool-capable model.

With native calling active, Hagar uses the provider's structured
tools. If the provider rejects the schema (HTTP 400/404/422), at the first
step it switches to the textual JSON protocol for that session. The fallback
covers the technical error, it does not guarantee that the model chooses the tool well.

## 4.2 `audit`

```yaml
audit:
  enabled: true
  path: logs/audit.jsonl
  max_field_chars: 2000
  max_bytes: 5000000
  max_files: 100
  include_outputs: true
```

| Field | Default | Effect |
|---|---|---|
| `enabled` | `true` | enables/disables the log |
| `path` | `logs/audit.jsonl` | JSON Lines file |
| `max_field_chars` | `2000` | truncates the fields |
| `max_bytes` | `5000000` | rotation threshold |
| `max_files` | `100` | rotated files to keep |
| `include_outputs` | `true` | if `false`, redacts the tool output |

The audit contains sensitive data: file outputs, answers and texts. It must
be protected like the workspace. `/audit` shows only the events of the current
file, not the rotated ones.

Main events: `harness.start`, `turn.start`, `llm.tool_choice`,
`tool.call`, `tool.result`, `turn.answer`, `permission.decision`,
`permission.confirmation`, `memory.*`, `mcp.loaded`, `mcp.failed`,
`harness.stop`.

## 4.3 `policy`

```yaml
policy:
  path: policy.yaml
  subject: assistant
```

`path` is relative to the configuration. If the file is not readable or is not
valid:

- all policies become `DENY`;
- `policy.failed` is recorded;
- Hagar stays running but no tool is executed;
- the console shows `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

With the SQLite backend it is used only by the legacy Markdown backend and by the
legacy projects. With `memory.backend: sqlite` it may not even exist.

## 4.5 `memory`

```yaml
memory:
  enabled: true
  backend: sqlite
  database: ./hagar-memory.db
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  context_project_memories: 10
  max_context_chars: 6000
  project_max_active: 200
  summary_max_chars: 4000
  max_skill_chars: 4000
```

| Field | Default | Effect |
|---|---|---|
| `enabled` | `true` | enables the memory |
| `backend` | `sqlite` | `sqlite` or legacy `markdown` |
| `database` | local data | explicit path of the SQLite database |
| `vault_subdir` | `Hagar` | subdirectory of the legacy Vault |
| `context_turns` | `10` | recent turns injected; `0` disables |
| `context_skills` | `3` | confirmed skills injected |
| `context_project_memories` | `10` | titles of active decisions |
| `max_context_chars` | `6000` | budget of the memory block |
| `project_max_active` | `200` | project maintenance threshold |
| `summary_max_chars` | `4000` | maximum length of the summary |
| `max_skill_chars` | `4000` | maximum length of a skill |

`vault_subdir` must stay inside the Vault: absolute paths, `..`,
`I:/...` and other Windows drives are rejected even on Linux.

With `backend: sqlite` the default database is:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

or `HAGAR_MEMORY_DB`. SQLite uses WAL, transactions and `VACUUM INTO` for
backup; the Vault is not updated.

The budget is in **characters**, not in tokens. When the block is
trimmed, the audit records `memory.context_trimmed`.

## 4.6 `filesystem`

```yaml
filesystem:
  sandbox:
    - alias: documenti
      path: C:\Users\pippo\Documenti
      permissions: RWX
  limits:
    max_write_bytes: 0
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

Each entry:

| Field | Mandatory | Notes |
|---|---|---|
| `alias` | yes | a single segment, unique case-insensitively |
| `path` | yes | existing directory of the host system |
| `permissions` | no | default `R`; letters `R`, `W`, `X` |

Permissions:

| Letter | Covers |
|---|---|
| `R` | read, list, search, `stat` |
| `W` | write, create, rename, copy, delete |
| `X` | `chdir` into the directory |

The agent sees `/home/ai/<alias>/...`. `/home/ai` lists the aliases but is not
a physical directory and it is not possible to enter it with `chdir`.

Constraints:

- duplicate aliases and paths stop the configuration;
- a missing path stops the configuration;
- the physical paths may contain spaces; the aliases may not;
- Hagar does not create sandbox directories and does not assume a dedicated home.

Write limits:

| Field | Effect |
|---|---|
| `max_write_bytes` | maximum per single operation |
| `min_free_bytes` | minimum remaining free space |
| `session_write_bytes` | maximum cumulative per session |
| `ask_over_bytes` | above this threshold it asks for confirmation |

`0` disables the individual limit. The limits are invariants: exceeding one
is a tool error, not a warning.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
  agents: false
```

These are the **system ceiling**. Default: `read=true`, the others `false`.

| Field | Grants |
|---|---|
| `read` | filesystem read, memory read |
| `write` | filesystem write/create/delete, memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |
| `agents` | `AGENT_SPAWN` and `AGENT_DATA`, for `agent.*`/`artifact.*`/`mailbox.*` |

`COMPUTE` and `MCP_CALL` are always in the ceiling, but the policy can deny them.
If the ceiling does not grant a capability, the policy cannot grant it.
`agents: true` alone is not enough: the policy must have an `AGENT_SPAWN` rule
for `agent.*`.

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

Value intended for document retrieval. It does not change the memory
context in this version.

## 4.9 `mcp_servers`

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer
      token_env: MCP_EXAMPLE_TOKEN
```

Fields:

| Field | Notes |
|---|---|
| `endpoint` | HTTP/JSON-RPC URL of the MCP server |
| `namespace` | prefix of the imported tools: `mcp.<namespace>.*` |
| `auth` | optional: `bearer`, `header` or `oauth` |

Bearer/header:

```yaml
auth:
  type: header
  header: Authorization
  token_env: ATLASSIAN_BASIC
```

The value read from the environment is sent **as it is**: for Basic
it must already be `Basic <base64>`, not just the token.

OAuth:

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    client_id: ...
    client_secret_env: MCP_CLIENT_SECRET
    scopes: [read:me, offline_access]
    audience: api.atlassian.com
    redirect_port: 8765
    token_cache: .hagar/oauth/example.json
    timeout: 300
```

The flow is authorization code + PKCE with a local callback
`http://localhost:<port>/oauth/callback`. If `client_id` is missing,
dynamic registration is attempted. With `offline_access`,
`prompt=consent` is added. The tokens are in a restricted local file and are
renewed automatically.

If an MCP server fails:

- `mcp.failed` is recorded;
- the server is skipped;
- the other servers and the rest of the harness keep going;
- `/mcp` shows zero tools for that namespace.

---

# 5. `policy.yaml`

Example:

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
        tools: ["filesystem.*"]

      - capabilities: [COMPUTE]
        effect: allow
        tools: ["calculator.*", "statistics.*", "units.*",
                "clock.*", "calendar.*", "think.*", "text.*", "url.*"]

      - capabilities: [MCP_CALL]
        effect: ask
        tools: ["mcp.*"]

      - capabilities: [MEMORY_READ]
        effect: allow
        tools: ["memory.*"]

      - capabilities: [MEMORY_WRITE]
        effect: ask
        tools: ["memory.*"]
```

## 5.1 Effects

| Effect | Meaning |
|---|---|
| `allow` | the tool can be executed |
| `ask` | a human confirmation is required |
| `deny` | the tool is not executed |

Order of severity: `DENY > ASK > ALLOW`. With multiple requested capabilities
the AND applies: the worst effect wins.

`ASK` without a confirmation channel is equivalent to `DENY`. The console confirmation
shows `shall I do it? (y/N)` and the default is `N`.

## 5.2 Capabilities

| Name | Use |
|---|---|
| `FILESYSTEM_READ` | reading, listing, searching, stat |
| `FILESYSTEM_WRITE` | modification |
| `FILESYSTEM_CREATE` | creation, copy, rename to destination |
| `FILESYSTEM_DELETE` | deletion |
| `FILESYSTEM_EXEC` | entry/execution in the sandbox |
| `MEMORY_READ` | memory reading |
| `MEMORY_WRITE` | memory writing |
| `NETWORK` | network access |
| `MCP_CALL` | call to an MCP tool |
| `COMPUTE` | local computation without network/filesystem |

## 5.3 Rules and specificity

A rule can filter with:

- `tools`: glob on the name (`filesystem.*`, `mcp.atlassian.*`);
- `paths`: prefixes on the path written by the model;
- `namespaces`: prefixes on the namespace.

The most specific rule wins: first the number of filters, then the
length of the prefix. On a tie the more restrictive effect wins.
Without rules, the subject's `default` applies; the safe default is `deny`.

The `paths` scope compares the path **written by the model**, not the one
resolved after `chdir`: an absolute path or a directory change may not
match and produces `DENY` (fail closed).

## 5.4 Errors

If `policy.yaml` is invalid, a capability is missing or the subject does not
exist:

- Hagar applies `DENY` to all policies;
- it records `policy.failed`;
- it shows a warning;
- it does not execute any tool.

---

# 6. Default behaviours

| Situation | Behaviour |
|---|---|
| No `hagar.yaml` | configuration error, exit 1 |
| Invalid YAML | configuration error, exit 1 |
| Invalid policy | total DENY, harness started |
| Memory disabled | check `memory.database` and the directory permissions |
| `Projects: disabled` | check the SQLite database or `vault.path` in the legacy backend |
| No active project | free activity |
| Non-interactive start-up | free activity, unless `--project`/`--free` |
| Nonexistent `--project` | error, exit 1 |
| Unreachable MCP server | `mcp.failed`, server skipped |
| Unreachable model/Ollama | turn error, harness stays active |
| Missing API key | client not built, error at start-up |
| Denied tool | error result to the model, no execution |
| Tool in `ASK` without confirmation | refusal |
| Write limit exceeded | tool error, no write |
| File over 4096 bytes with `read_file` | error, use `read_chunk` |
| Page over the limit | `has_more`/`next_offset` |
| Symlink | invisible; operation as a nonexistent path |
| Hard link/mount/junction | not detected; user responsibility |
| TOCTOU race | not checked; user responsibility |
| Memory absent during the turn | `memory.failed`, the turn continues |
| End of session with turns | summary, archive, project review |
| Review refused | candidate decisions with `auto_saved: true` |
| Project over `project_max_active` | archiving request |
| Ctrl-C during OAuth | callback closed, exit 130 |
| Unknown `/` command | message, not sent to the model |

## 6.1 End of session

On exit, if the memory is active and there are turns:

1. the transcript is moved to `archive/chat/`;
2. a summary is generated (LLM, with mechanical fallback);
3. the summary is saved with link and hash;
4. if there is a project, the LLM proposes candidate decisions;
5. the user can review them; if they refuse, they remain candidates.

If there are no turns, no summary is created.

## 6.2 What Hagar does not do

- it does not execute shell commands;
- it does not give the model physical paths;
- it does not guarantee OS isolation: the sandbox is path-based;
- it does not check hard links, mounts, junctions or TOCTOU;
- it does not delete chats or skills by age;
- it does not encrypt the Vault;
- it does not automatically promote a skill or a decision to truth.

---

# 7. Operational security

- The model is untrusted: policies and confirmations are the controls.
- The SQLite database contains conversations and decisions: it must be protected.
- The audit may contain file outputs: it must be protected.
- The API keys are only in the environment.
- The MCP/OAuth tokens are in local caches with restricted permissions.
- Do not expose Ollama or LM Studio on the network without need.
- A hard link or a mount inside an allowed directory can expose
  external contents: Hagar does not detect them.

---

# 8. Troubleshooting

| Symptom | Check |
|---|---|
| `Policy: DENY ALL` | validate `policy.yaml` and `policy.path` |
| `Memory: disabled` | check `memory.database` and the permissions |
| `Projects: disabled` | check the SQLite database |
| `Failed to load MCP server` | endpoint, token, `/mcp` |
| `MCP auth token missing` | variable indicated by `token_env` |
| `MCP HTTP 401` | Basic or OAuth credentials/header |
| `MCP HTTP 400` | protocol, session or server parameters |
| `read_file` too large | use `read_chunk` |
| `PermissionError` | policy, `R/W/X` permissions, path outside the sandbox |
| Tool not listed | failed MCP server or unregistered tool |
| Unrecognized command | `/help` |

For a configuration error, Hagar exits with code 1 and prints the
detail to stderr. For a turn error, the model receives the
tool result and the audit keeps the event.
