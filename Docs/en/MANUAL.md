# HAGAR — User manual

Version: **0.3.0**

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
2. Loads `policy.yaml`; if it is invalid, it applies `DENY` to everything.
3. Builds the LLM client.
4. Initializes the Vault and the memory, if configured.
5. Builds the filesystem sandbox.
6. Registers the local tools.
7. Tries to load the MCP servers; a failed server does not stop the others.
8. Shows the project selection.
9. Enters the chat loop.

---

# 2. Chat commands

Commands start with `/`. An unknown command **is not sent to the
model**: Hagar replies `Comando sconosciuto` and suggests `/help`.

## 2.1 Global commands

| Command | Behaviour |
|---|---|
| `/help` or `/?` | lists the available commands |
| `/tools [category]` | lists the tools and the capabilities; the filter is optional |
| `/status` | shows model, project, memory, audit and sandbox |
| `/mcp` | lists MCP servers, endpoints and imported tools |
| `/audit [n]` | shows the last `n` events; default 10, maximum 50 |
| `exit` | exits |
| `quit` | exits |
| `Ctrl-D` | exits |
| `Ctrl-C` | interrupts; during OAuth it exits with code 130 |

`/status` and `/audit` are human commands: they do not go through the model and do not
consume tool calls.

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

In free activity, project memory is neither read nor written; chat,
summary and skills remain available.

## 2.3 Memory

| Command | Behaviour |
|---|---|
| `/memory` or `/memory help` or `/memory ?` | help |
| `/memory list [candidate\|confirmed\|archived]` | lists the skills and the counts |
| `/memory show <slug>` | shows a skill |
| `/memory review` | interactive review of the candidates |
| `/memory confirm <slug>` | confirms a skill |
| `/memory archive <slug>` | archives a skill |
| `/memory archive search <text>` | searches the archived transcripts |
| `/memory archive read <session> [offset] [limit]` | reads an archived transcript |

The words `search` and `read` are reserved: a skill slug named
exactly `search` or `read` cannot be archived with this command.

There is no deletion command: you only archive.

## 2.4 What is not a command

The tools (`filesystem.*`, `memory.*`, `mcp.*`, `clock.now`, ...) are
called by the model through the registry. They are not typed as `/tool`.
The only exception is the informational commands `/tools`, `/status`, `/mcp`,
`/audit`, which are console commands and not tools.

---

# 3. Command line

```text
hagar [options]
```

| Option | Effect |
|---|---|
| `--config PATH` | uses an explicit configuration file |
| `--model NAME` | overrides `model.name` |
| `--project NAME` | selects an active project at start-up |
| `--free` | starts in free activity |
| `--no-memory` | disables memory and projects for the session |
| `--no-native-tools` | forces the textual JSON protocol |
| `--version` | prints the version |

`--project` and `--free` are mutually exclusive.

## 3.1 Configuration lookup

Order:

1. `--config PATH`
2. the `HAGAR_CONFIG` variable
3. `./hagar.yaml` in the current directory

Relative paths inside `hagar.yaml` — audit, policy, Vault — are
resolved against the directory of the configuration file, not the
directory from which you launch Hagar.

## 3.2 Exit codes

| Code | Meaning |
|---|---|
| `0` | normal exit or `--version` |
| `1` | configuration error or invalid project |
| `130` | interruption with Ctrl-C |

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
| `provider` | mandatory | `ollama`, `deepseek`, `claude`, `gemini` |
| `name` | mandatory | model name at the provider |
| `host` | provider default | API base URL |
| `native_tools` | `true` | if `false`, uses the textual JSON protocol |
| `max_tokens` | `1024` | used only by Claude |
| `api_key_env` | standard name | environment variable of the key |

Providers and keys:

| Provider | Standard key |
|---|---|
| `ollama` | none |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `claude` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |

Keys must never be written in the YAML. If a key is missing, the client
is not built and start-up fails with an explicit error.

With native calling active, Hagar uses the provider's structured tools.
If the provider rejects the schema (HTTP 400/404/422), on the first
step it switches to the textual JSON protocol for that session. The fallback
covers the technical error, it does not guarantee that the model chooses the right tool.

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
| `include_outputs` | `true` | if `false`, redacts tool output |

The audit contains sensitive data: file output, answers and texts. It must
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

`path` is relative to the configuration. If the file is unreadable or
invalid:

- every policy becomes `DENY`;
- `policy.failed` is recorded;
- Hagar stays running but no tool is executed;
- the console shows `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

It is the root of the Markdown memory. It must exist and be writable.
If it is missing or not writable, memory is disabled with a warning;
the rest of the harness keeps going.

## 4.5 `memory`

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

| Field | Default | Effect |
|---|---|---|
| `enabled` | `true` | enables memory |
| `vault_subdir` | `Hagar` | subdirectory inside the Vault |
| `context_turns` | `10` | recent turns injected; `0` disables |
| `context_skills` | `3` | confirmed skills injected |
| `context_project_memories` | `10` | titles of active decisions |
| `max_context_chars` | `6000` | budget of the memory block |
| `project_max_active` | `200` | project maintenance threshold |
| `summary_max_chars` | `4000` | maximum length of the summary |
| `max_skill_chars` | `4000` | maximum length of a skill |

`vault_subdir` must stay inside the Vault: absolute paths, `..`,
`I:/...` and other Windows drives are rejected even on Linux.

The budget is in **characters**, not tokens. When the block is
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
| `R` | reading, listing, searching, `stat` |
| `W` | writing, creating, renaming, copying, deleting |
| `X` | `chdir` into the directory |

The agent sees `/home/ai/<alias>/...`. `/home/ai` lists the aliases but is not
a physical directory and it is not possible to `chdir` into it.

Constraints:

- duplicate aliases and paths stop the configuration;
- a missing path stops the configuration;
- physical paths may contain spaces; aliases may not;
- Hagar does not create sandbox directories and does not assume a dedicated home.

Write limits:

| Field | Effect |
|---|---|
| `max_write_bytes` | maximum per single operation |
| `min_free_bytes` | minimum free space remaining |
| `session_write_bytes` | maximum cumulative per session |
| `ask_over_bytes` | above this threshold it asks for confirmation |

`0` disables the individual limit. The limits are invariants: exceeding
one is a tool error, not a warning.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
```

They are the **system ceiling**. Default: `read=true`, the others `false`.

| Field | Grants |
|---|---|
| `read` | filesystem read, memory read |
| `write` | filesystem write/create/delete, memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |

`COMPUTE` and `MCP_CALL` are always in the ceiling, but the policy can deny them.
If the ceiling does not grant a capability, the policy cannot grant it.

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

The value read from the environment is sent **as is**: for Basic
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

The flow is authorization code + PKCE with local callback
`http://localhost:<port>/oauth/callback`. If `client_id` is missing, dynamic
registration is attempted. With `offline_access`, `prompt=consent` is added.
The tokens are in a restricted local file and are renewed
automatically.

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
| `ask` | human confirmation is required |
| `deny` | the tool is not executed |

Order of severity: `DENY > ASK > ALLOW`. With several capabilities requested,
AND applies: the worst effect wins.

`ASK` without a confirmation channel is equivalent to `DENY`. Console confirmation
shows `lo faccio? (y/N)` and the default is `N`.

## 5.2 Capabilities

| Name | Use |
|---|---|
| `FILESYSTEM_READ` | reading, listing, searching, stat |
| `FILESYSTEM_WRITE` | modification |
| `FILESYSTEM_CREATE` | creation, copy, rename to destination |
| `FILESYSTEM_DELETE` | deletion |
| `FILESYSTEM_EXEC` | entering/executing in the sandbox |
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
prefix length. On a tie the more restrictive effect wins.
Without rules, the subject's `default` applies; the safe default is `deny`.

The `paths` scope compares the path **written by the model**, not the one
resolved after `chdir`: an absolute path or a directory change may not
match and produces `DENY` (fail closed).

## 5.4 Errors

If `policy.yaml` is invalid, a capability is missing or the subject does not
exist:

- Hagar applies `DENY` to every policy;
- records `policy.failed`;
- shows a warning;
- executes no tool.

---

# 6. Default behaviours

| Situation | Behaviour |
|---|---|
| No `hagar.yaml` | configuration error, exit 1 |
| Invalid YAML | configuration error, exit 1 |
| Invalid policy | total DENY, harness started |
| Vault missing/not writable | memory disabled, harness started |
| `projects` not writable | projects disabled, memory active |
| No active project | free activity |
| Non-interactive start-up | free activity, unless `--project`/`--free` |
| `--project` does not exist | error, exit 1 |
| MCP server unreachable | `mcp.failed`, server skipped |
| Model/Ollama unreachable | turn error, harness stays active |
| API key missing | client not built, error at start-up |
| Tool denied | error result to the model, no execution |
| Tool in `ASK` without confirmation | refusal |
| Write limit exceeded | tool error, no write |
| File above 4096 bytes with `read_file` | error, use `read_chunk` |
| Page beyond the limit | `has_more`/`next_offset` |
| Symlink | invisible; operation as a non-existent path |
| Hard link/mount/junction | not detected; user responsibility |
| TOCTOU race | not checked; user responsibility |
| Memory missing during the turn | `memory.failed`, the turn continues |
| End of session with turns | summary, archive, project review |
| Review refused | candidate decisions with `auto_saved: true` |
| Project above `project_max_active` | request to archive |
| Ctrl-C during OAuth | callback closed, exit 130 |
| Unknown `/` command | message, not sent to the model |

## 6.1 End of session

On exit, if memory is active and there are turns:

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
- The Vault is plain-text Markdown: it may contain conversations and decisions.
- The audit may contain file output: it must be protected.
- API keys live only in the environment.
- MCP/OAuth tokens live in local caches with restricted permissions.
- Do not expose Ollama or LM Studio on the network without need.
- A hard link or a mount inside an allowed directory can expose
  external content: Hagar does not detect them.

---

# 8. Troubleshooting

| Symptom | Check |
|---|---|
| `Policy: DENY ALL` | validate `policy.yaml` and `policy.path` |
| `Memory: disabled` | does `vault.path` exist? is it writable? |
| `Projects: disabled` | does `vault.path/Hagar/projects` exist? |
| `Failed to load MCP server` | endpoint, token, `/mcp` |
| `MCP auth token missing` | the variable named by `token_env` |
| `MCP HTTP 401` | Basic or OAuth credentials/headers |
| `MCP HTTP 400` | protocol, session or server parameters |
| `read_file` too large | use `read_chunk` |
| `PermissionError` | policy, `R/W/X` permissions, path outside the sandbox |
| Tool not listed | MCP server failed or tool not registered |
| Command not recognised | `/help` |

For a configuration error, Hagar exits with code 1 and prints the
detail to stderr. For a turn error, the model receives the
tool result and the audit keeps the event.
