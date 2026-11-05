<p align="center">
  <img src="Docs/HAGAR.jpg">
</p>

# H.A.G.A.R.

Harness Agentico Generale per AI Resiliente (General Resilient Agentic Harness for AIs)

# 0. How It All Started - Security First

I created HAGAR because no other harness would isolate my files by default. DeepSeek harness, Claude Code, AutoGen, whatever: let them free and all of them give away your filesystem to LLMs. YOU must enforce limits and do it well, or else. None of them guarantees your data won't be read with untold purposes, or by mistake, or both. If not by the harness itself, by that oh-so-cool plugin/skill/whatever you just installed...

**HAGAR reverts that default: YOU state what LLMs can see, write, search, and where.** No LLM can read or write anything outside the directories that you explicitly state as readable or writable in the config file. If a directory is not in the [filesystem] config section, no way. For LLMs, it does not exist.

Developing HAGAR, another concept dawned on me: why an LLM should care for the OS anyway? In the AI world the real performance boundary is set by model calls: they takes seconds or even minutes. Direct OS access shave some milliseconds: does it worth the risk? I answered no.

So, **HAGAR does its best to isolate the LLM from the OS.** Every interaction with files, memories, machine is done by tools (either MCP or those embedded in HAGAR). The AI does not know which OS is running on. Ideally, it shall never know: if there will ever be a way for an AI to know the OS through HAGAR isolation, I will see it as a security hazard and fix it (or at least state the issue in docs and let users know).

|Harness	|Sees host FS	|Sees actual OS |Isolation	 |
|-----------|---------------|---------------|------------|
|Claude Code|Partly			|Yes			|Permissions |
|Codex CLI	|Partly			|Yes			|Sandbox	 |
|OpenHands	|No				|Yes			|Docker		 |
|E2B		|No				|Yes			|VM/Container|
|`HAGAR`	|`No`			|`No`			|`Virtual FS`|

**Other harnesses try to give LLMs a computer: HAGAR tells LLMs that the computer does not exist.** The AIs should focus more on knowledge management than on technical details (even if they are really good at it). The more an harness can automate, the less thinking (and tokens) is necessary. This way, even small models could shine.

Or, put differently: for the LLM, HAGAR is reality.

# 1. Project Vision

Hagar is an LLM harness developed in Python, designed for the secure execution of LLMs.

The goal is not merely to provide a chat interface with a language model, but to create a ***safe and secure*** operating environment in which an LLM can use tools, consult persistent memory, and interact with external systems — all without having direct access to the host machine's actual resources — while preventing or at least mitigating common errors.

To this purpose, I adopted principles and methodologies from both cybersecurity (least privilege level, CIA triad) and HMI/HCI (Human-Machine Interface/Interaction for industrial machinery) and Cognitive Ergonomics, applying them to the design of the environment in which the LLM operates. 

As per the statements above and in order to establish a general rule of conduct for any future development, I hereby state **The Four Laws of HAGAR**:

## 1.1 First Law of HAGAR
**An LLM is, by definition, untrustworthy.** This is not because it is malicious or useless, but because it is probabilistic. Therefore, every statement it makes must be verified, and every action it takes must be constrained.

## 1.2 Second Law of HAGAR
**Tools are more reliable than the LLM.** If the filesystem indicates that a file exists, it exists. If a tool returns a file size, that size is real. The LLM interprets, but tools provide measurements.

## 1.3 Third Law of HAGAR
**State must exist outside the LLM’s "mind."** By implementing components such as `ToolRegistry`, `MCP`, `FilesystemSandbox`, and `PermissionEvaluator`, we shift knowledge and control outside of the model itself. This aligns with standard practices for safety-critical systems. 

## 1.4 Fourth Law of HAGAR
**Every action must be explainable after the fact.** For this purpose, HAGAR implements an audit log: when something goes wrong — and eventually it will — the question should not be "Why did the LLM go haywire?" but rather: "What assumption did it make?" "Which tool did it use?" "Which piece of data was incorrect?" In other words: incident investigation must be possible — much like in aviation. HAGAR does support it AND will ever do.

## 1.5 Software Architecture

Structurally, HAGAR is built upon five fundamental principles:

- separation between the model and the operating system;
- security by default;
- a plugin-based architecture;
- independence from any specific LLM provider;
- extensibility via tools and the MCP (Model Context Protocol).

---

# 2. Absolute Prohibitions

The model must never:

- directly access the host filesystem;
- execute commands in the actual shell;
- obtain privileges beyond those defined in its configuration;
- have knowledge of the operating system's actual organization.

All operations must take place exclusively through tools that are registered and controlled by the harness.

---

# 3. Development

## 3.0 Install and CLI

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

`pip install -e .` declares the `core`, `llm` and `memory` packages and
installs the `hagar` command:

```powershell
hagar --config hagar.yaml
hagar --model qwen3:8b
hagar --no-memory
hagar --no-native-tools
hagar --version
```

The configuration is searched as `--config`, then the `HAGAR_CONFIG`
environment variable, then `./hagar.yaml`. `python -m hagar` also works
from a source checkout.

## 3.1 Test suite

The suite runs offline and covers configuration, the filesystem sandbox,
the tool registry, the agent loop, the audit log, every LLM backend,
Ollama response parsing, the MCP client, memory, the vault and the
harness wiring.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.\tools\run_tests.ps1
```

Live tests call real services and are excluded by default:

```powershell
.\tools\run_tests.ps1 --live
```

They need a running Ollama server; the remote-provider checks run only
when the corresponding API key is set (`DEEPSEEK_API_KEY`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`). Model overrides:
`HAGAR_LIVE_OLLAMA_MODEL`, `HAGAR_LIVE_DEEPSEEK_MODEL`,
`HAGAR_LIVE_CLAUDE_MODEL`, `HAGAR_LIVE_GEMINI_MODEL`.

`tools/run_tests.ps1` puts `tools/pytest_shim` on `PYTHONPATH`. The shim is
needed when the tests run under a restricted token (for example the DSH
sandbox on Windows): Python 3.13+ applies the POSIX `0o700` mode to
`tempfile.mkdtemp()`, and the restricted token cannot open the resulting
directory, so every `tmp_path` fixture fails with "Permission denied".
On Windows the POSIX mode bits carry no meaning, so the shim restores the
`0o777` default; confinement is still enforced by the token and the jail.

## 3.2 Layout

```
hagar.py            entry point and harness wiring
core/               config, agent, audit log, registry, sandbox and tools
llm/                LLM backends (Ollama, DeepSeek, Claude, Gemini), MCP client
memory/             vault access
tests/              pytest suite
tools/              development helpers (test runner, sandbox shim, model benchmark)
local_tools/		Embedded AI tools in HAGAR - not MCP, just locals available to LLMs
```

## 3.3 LLM backends

`model.provider` selects the backend. Tool schemas, message conversion and
the native/fallback paths are shared in `llm/base.py`, so switching
provider does not change the harness.

Native tool calling is the default for all four providers. If a model
rejects it (HTTP 400/404/422), the agent falls back to the text JSON
protocol for the session; set `model.native_tools: false` or pass
`--no-native-tools` to force the text protocol.

| provider   | transport                    | API key                |
|------------|------------------------------|------------------------|
| `ollama`   | native `/api/chat`           | none                   |
| `deepseek` | OpenAI-compatible REST       | `DEEPSEEK_API_KEY`     |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

DeepSeek's current model names are `deepseek-flash` (default) and
`deepseek-v4-pro`; the old `deepseek-chat` is no longer accepted. The live
test uses `deepseek-flash` unless `HAGAR_LIVE_DEEPSEEK_MODEL` overrides it.
`tools/diagnose_deepseek.py` checks DNS, key shape and endpoint without
printing the key.

Keys are read from the environment, never from the YAML file. If the
default variable name does not suit you, set `model.api_key_env`.
`model.host` is the base URL of any provider (with a per-provider
default; Ollama uses `http://localhost:11434`) and `model.max_tokens` only
applies to Claude (default 1024).

```yaml
model:
  provider: gemini
  name: gemini-2.0-flash
```

Each backend normalizes the dialogue to its own format: Claude receives
system messages in the dedicated `system` field and alternating turns,
Gemini receives `systemInstruction` and the `model` role. The shared
protocol between the agent and the client only uses `user` and
`assistant`.

## 3.4 Audit log

Every session appends JSON Lines to `audit.path` (default
`logs/audit.jsonl`, resolved relative to the configuration file):

```yaml
audit:
  enabled: true
  path: logs/audit.jsonl
  max_field_chars: 2000
```

Events: `harness.start`, `turn.start`, `llm.tool_choice`,
`llm.protocol_error`, `llm.repaired`, `llm.repair_failed`, `tool.call`,
`tool.result`, `turn.answer`, `turn.error`, `turn.stop`, `mcp.loaded`,
`mcp.failed`, `llm.failed`, `harness.stop`. A missing `harness.stop` in
the last session means the process was killed or crashed.

Each record carries a UTC timestamp, the session id and, where relevant,
a turn id shared by all events of one question. Truncation is controlled
by `audit.max_field_chars`; API keys are never written to the log.

The log is made to be read after an incident, not by the model. It may
contain the content of files read through the filesystem tools, so it
should be treated with the same care as the workspace itself.

## 3.5 Permissions and `policy.yaml`

Every tool call is authorized before execution. A tool declares its
**capabilities** (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`,
`FILESYSTEM_CREATE`, `FILESYSTEM_DELETE`, `MEMORY_READ`,
`MEMORY_WRITE`, `MCP_CALL`, ...); a **subject** (the agent) declares
rules mapping capabilities to `allow`, `ask` or `deny`, optionally
scoped by tool name, path prefix or namespace.

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
```

`ask` prompts on the console with `do it? (y/N)` (default N); the
`ConfirmationProvider` protocol leaves room for a GUI modal dialog. The
policy file is read before the LLM is created: if it is missing or
invalid, every policy becomes `DENY`, the failure is written to the
audit log (`policy.failed`) and shown in chat, and the harness keeps
running.

## 3.6 Memory

The harness keeps an episodic memory of the conversation in the
Obsidian vault (`<vault>/Hagar/chat/`) and injects the last
`memory.context_turns` turns into every prompt. The model can save
durable memories with `memory.create_skill` (stored as `candidate` with
provenance), list them with `memory.list_skills`, and search past turns
with `memory.get_context`.

```yaml
memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  max_skill_chars: 4000
```

If the vault is missing or unwritable, memory is disabled with a warning
and the harness keeps running. Memory writes go through the policy
engine (`MEMORY_READ`/`MEMORY_WRITE`; by default writes ask for
confirmation). See ARCHITECTURE §3.11 for the vault layout.

---

# 4. Documentation

HAGAR has multilanguage documentation. At present, languages supported
are: it, en, es, pt, zh, ru. Each language has its dedicated subdir in Docs.

- [MANUAL.md](Docs/.../MANUAL.md) — config format, console commands, 
  command line options, default assumptions, 
- [ARCHITECTURE.md](Docs/.../ARCHITECTURE.md) — how the harness works
  today: components, security model, known limits.
- [ROADMAP.md](Docs/.../ROADMAP.md) — planned work, decisions already
  taken and open questions.
- [CHANGELOG.md](Docs/.../CHANGELOG.md) — version history.
