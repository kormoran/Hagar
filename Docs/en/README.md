<p align="center">
  <img src="../HAGAR.jpg">
</p>

[Italiano](../it/README.md) · [English](../en/README.md) · [Español](../es/README.md) · [中文](../zh/README.md) · [Русский](../ru/README.md) · [Português](../pt/README.md) · [العربية](../ar/README.md)

# H.A.G.A.R.

General Resilient Agentic Harness for AIs (*Harness Agentico Generale per AI Resiliente*)

# 0. How it all began: security

I created HAGAR because no other harness for AI isolated my files by default. Whether it was DeepSeek, Claude Code, AutoGen or anything else, if left free they all end up exposing your file system to LLMs. It is up to YOU to impose limits, and you have to do it well, otherwise you are on your own. None of these tools guarantees that your data will not be read for unspecified purposes, by mistake, or for both reasons. And if it is not the harness itself doing it, it might be that really cool plugin, that extremely useful skill, or any other addition you have just installed...

**HAGAR flips this approach: it is YOU who establishes what LLMs can see, write or search, and where.** No LLM can read or write anything outside the directories you have explicitly marked as readable or writable in the configuration file. If a directory is not in the `[filesystem]` section of the configuration, it does not exist: to LLMs, it is as if it were not there.

While developing HAGAR, another question arose: why should an LLM need to interact with the operating system? In the world of artificial intelligence, the real performance bottleneck is model calls, which can take seconds (sometimes MANY seconds). Direct access to the operating system saves only a few milliseconds: is it worth taking the risk? My answer is no.

For this reason, **HAGAR does its best to isolate the LLM from the operating system.** Every interaction with files, memories or the machine itself happens through specific tools (based on the MCP protocol or integrated directly into HAGAR). The AI does not know which operating system it is running on, and should never know: if there were a way for an AI to work out the operating system it runs on despite HAGAR's isolation, I would consider that a security flaw and fix it (or, at the very least, document the problem to inform users).

|Harness	|Sees host FS	|Sees the OS		|Isolation	  |
|-----------|---------------|---------------|-------------|
|Claude Code|Partial		|Yes	 		|Permissions	  |
|Codex CLI	|Partial		|Yes	 		|Sandbox	  |
|OpenHands	|No				|Yes	 		|Docker		  |
|E2B		|No				|Yes				|VM/Container |
|`HAGAR`	|`No`			|`No`			|`Virtual FS`|

**Other harnesses try to give LLMs a computer: HAGAR tells LLMs that the computer does not exist.**
AI should focus on knowledge management more than on technical details (even though they are very good at both). The more a framework can automate, the less reasoning (and the fewer tokens) is required. That way even the smallest models can express their full potential.

Or, put another way: to an LLM, HAGAR is reality.

# 1. Project vision

HAGAR is a harness for LLMs, developed in Python, designed for the safe execution of language models.

The goal is not just to provide a chat interface for an LLM, but to create an operating environment that is ***safe and protected***, in which the LLM can use tools, consult a persistent memory and interact with external systems — all without having direct access to the real resources of the host machine — preventing or at least mitigating the most common mistakes.

That is why I adopted principles and methodologies from both information security (principle of least privilege, CIA triad) and the HMI/HCI field (human-machine interaction/interface, typical of industrial machinery) and from cognitive ergonomics, applying them to the design of the environment in which the LLM operates: as with human work, HAGAR's further purpose is to create an environment for LLMs where doing the right thing is easy and making mistakes is hard.

On the basis of the above and in order to establish a general rule of conduct for every future development of this software, I state here **the Four Laws of HAGAR**:

## 1.1 First Law of HAGAR
**An LLM is, by definition, unreliable.** This does not mean that it is malicious or useless, but that its operation is probabilistic in nature. Consequently, every statement it makes must be verified and every action it takes must be subject to constraints.

## 1.2 Second Law of HAGAR
**Tools are more reliable than the LLM.** If the file system says that a file exists, then it really exists. If a tool returns the size of a file, that size is real. The LLM interprets, but tools measure.

## 1.3 Third Law of HAGAR
**State must exist outside the LLM's "mind".** By implementing components such as `ToolRegistry`, `MCP`, `FilesystemSandbox`, `Memory` and `PermissionEvaluator`, we move knowledge and control outside the model itself. This is in line with standard practice for systems in which security is a critical requirement.

## 1.4 Fourth Law of HAGAR
**Every action must be explainable after the fact.** For this reason HAGAR implements an *audit log*: when something goes wrong — and sooner or later it will — the question must not be "Why did the LLM go crazy?", but "What assumptions did it make?", "Which tool did it use?", "Which piece of data was wrong?". In other words, it must be possible to conduct an incident analysis, exactly as in aviation. HAGAR acknowledges this need and will always provide the tools to do it.

## 1.5 Software architecture

From a structural point of view, HAGAR rests on five fundamental principles:

- separation between the model and the operating system;
- security by default;
- plugin architecture;
- independence from any specific LLM provider;
- extensibility through tools (*tools*) and MCP (Model Context Protocol).

---

# 2. Absolute prohibitions

The model is strictly forbidden to:

- access the host file system directly;
- execute commands in a real OS shell;
- obtain privileges higher than those defined in the configuration;
- know the real operating system.

All operations must take place only through tools registered and controlled by the harness.

---

# 3. Development

## 3.0 Installation and CLI

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

The configuration is looked up in the following order: the `--config` parameter,
the `HAGAR_CONFIG` environment variable and finally the `./hagar.yaml` file.
It is also possible to use `python -m hagar`, working directly on the source code.

## 3.1 Layout

```
hagar.py            Harness launcher script
hagar.yaml          Default configuration script
policy.yaml			Permission configuration for tools (built-in and MCP)
core/               config, agent, audit log, registry, sandbox and tools
llm/                LLM backends (Ollama, DeepSeek, Claude, Gemini), MCP client
memory/             vault access
tests/              pytest suite
tools/              development helpers (test runner, sandbox shim, model benchmark)
local_tools/		Tools for AIs built into HAGAR - not MCP, but available directly
```

## 3.2 LLM backends

`model.provider` selects the backend. Tool schemas, message conversion and the native or fallback paths are handled in `llm/base.py`; therefore, changing provider requires no changes to the execution infrastructure (harness).

Native tool calling is the default for all four backends. If a model rejects that mode (returning an HTTP 400, 404 or 422 error), the agent switches to the textual JSON protocol for the whole session; you can force the textual protocol by setting `model.native_tools: false` or by passing the `--no-native-tools` argument.

| provider   | transport                    | API key                |
|------------|------------------------------|------------------------|
| `ollama`   | native `/api/chat`           | none                   |
| `deepseek` | OpenAI-compatible REST       | `DEEPSEEK_API_KEY`     |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

The model names currently supported for DeepSeek are `deepseek-flash` (default) and `deepseek-v4-pro`; the old `deepseek-chat` is no longer accepted. The live test uses `deepseek-flash`, unless it is overridden by the `HAGAR_LIVE_DEEPSEEK_MODEL` variable. The `tools/diagnose_deepseek.py` script lets you check DNS, the key format and the endpoint, without showing the key itself.

Keys are read only from environment variables and never from the YAML file. If the default variable name does not suit your needs, you can specify another one with `model.api_key_env`. The `model.host` parameter sets the provider's base URL (with a provider-specific default; for example, Ollama uses `http://localhost:11434`), while `model.max_tokens` applies to Claude only (with a default of 1024).

```yaml
model:
provider: gemini
name: gemini-2.0-flash
```

Each backend normalizes the dialogue according to its own format: Claude receives system messages in the dedicated `system` field and alternating turns, while Gemini receives `systemInstruction` and the `model` role. The protocol shared by the agent and the client uses only the `user` and `assistant` roles.

## 3.3 Audit log

Each session appends JSON Lines entries to the path specified in `audit.path` (default: `logs/audit.jsonl`, resolved relative to the configuration file):

```yaml
audit:
enabled: true
path: logs/audit.jsonl
max_field_chars: 2000
```

Events recorded: `harness.start`, `turn.start`, `llm.tool_choice`, `llm.protocol_error`, `llm.repaired`, `llm.repair_failed`, `tool.call`, `tool.result`, `turn.answer`, `turn.error`, `turn.stop`, `mcp.loaded`, `mcp.failed`, `llm.failed`, `harness.stop`. The absence of a `harness.stop` event in the last session indicates that the process was killed forcibly or crashed.

Each record includes a UTC timestamp, the session ID and, where relevant, a turn ID shared by all events relating to a single request. Data truncation is governed by the `audit.max_field_chars` parameter; API keys are never written to the log.

The log is meant to be consulted after an incident, not to be read by the model. Since it may contain the content of files read through the file system tools, it must be treated with the same care reserved for the workspace itself.

## 3.4 Authorizations and `policy.yaml`

Every tool call is authorized before it is executed. A tool declares its
**capability** (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`,
`FILESYSTEM_CREATE`, `FILESYSTEM_DELETE`, `MEMORY_READ`,
`MEMORY_WRITE`, `MCP_CALL`, ...); a **subject** (the agent) defines
rules that map those capabilities to `allow`, `ask` or `deny`,
possibly scoped by tool name, path prefix or namespace.

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

The `ask` option prompts a request on the console such as `lo faccio? (y/N)` (with a default value of `N`); the `ConfirmationProvider` protocol also lets you implement a modal dialog in a graphical interface (GUI).
The policy file is read before the LLM is created: if it is missing or
invalid, every policy is set to `DENY`, the error is recorded in the audit log (`policy.failed`) and shown in the chat, while the harness keeps running.

## 3.5 Memory

The system keeps an episodic memory of the conversation inside the Obsidian vault
(`<vault>/Hagar/chat/`) and inserts the latest `memory.context_turns` turns into every prompt. The model can save persistent memories through
`memory.create_skill` (archived as `candidate` with provenance information),
list them with `memory.list_skills` and consult previous passages
through `memory.get_context`.

```yaml
memory:
enabled: true
vault_subdir: Hagar
context_turns: 10
max_skill_chars: 4000
```

If the vault is missing or not writable, the memory feature is disabled
with a warning, while the system keeps working. Memory writes go through the policy engine (`MEMORY_READ`/`MEMORY_WRITE`; by default, write operations require confirmation). See ARCHITECTURE §3.11 for the vault structure.
---

# 4. Documentation

HAGAR has documentation in several languages. The languages currently supported
are: Italian, English, Spanish, Portuguese, Chinese, Russian. Each language has its own dedicated subdirectory in Docs.

- [MANUAL.md](MANUAL.md) — configuration format, console commands,
  command-line options, basic assumptions.
- [ARCHITECTURE.md](ARCHITECTURE.md) — The software architecture of this
  version of the harness: components, security model, known limits.
- [ROADMAP.md](ROADMAP.md) — Designed features to be implemented, decisions already made
  and issues still open.
- [CHANGELOG.md](CHANGELOG.md) — history of changes.
