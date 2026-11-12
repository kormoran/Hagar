<p align="center">
  <img src="../HAGAR.jpg">
</p>

[Italiano](../it/README.md) · [English](../en/README.md) · [Español](../es/README.md) · [中文](../zh/README.md) · [Русский](../ru/README.md) · [Português](../pt/README.md) · [العربية](../ar/README.md)

# H.A.G.A.R.

General Resilient Agentic Harness for AIs (Harness Agentico Generale per AI Resiliente)

# 0. How it all began: security

I created HAGAR because no other harness for AIs isolated my files by default. Whether it was DeepSeek, Claude Code, AutoGen or anything else, if left free they all end up exposing your file system to LLMs. It is up to YOU to impose limits and you have to do it well, otherwise you are on your own. None of these tools guarantees that your data will not be read for unspecified purposes, by mistake, or both. And if it is not the harness itself doing it, it could be that really cool plugin, that very useful skill, or any other addition you have just installed...

**HAGAR reverses this approach: it is YOU who establishes what LLMs can see, write or search, and where.** No LLM can read or write anything outside the directories that you have explicitly marked as readable or writable in the configuration file. If a directory is not in the `[filesystem]` section of the configuration, it does not exist: for LLMs, it is as if it were not there.

While developing HAGAR, another question arose: why should an LLM need to interact with the operating system? In the world of artificial intelligence, the real performance bottleneck is model calls, which can take seconds (sometimes MANY seconds). Direct access to the operating system saves only a few milliseconds: is it worth taking the risk? My answer is no.

For this reason, **HAGAR does its best to isolate the LLM from the operating system.** Every interaction with files, memories or the machine itself happens through specific tools (based on the MCP protocol or integrated directly into HAGAR). The AI does not know which operating system it is running on, and should never know: if there were a way for an AI to figure out the operating system it runs on despite HAGAR's isolation, I would consider it a security flaw and fix it (or, at the very least, document the problem to inform users).

|Harness	|Sees host FS	|Sees the OS		|Isolation	  |
|-----------|---------------|---------------|-------------|
|Claude Code|Partial		|Yes 	 		|Permissions	  |
|Codex CLI	|Partial		|Yes 	 		|Sandbox	  |
|OpenHands	|No				|Yes 	 		|Docker		  |
|E2B		|No				|Yes				|VM/Container |
|`HAGAR`	|`No`			|`No`			|`Virtual FS`|

**Other harnesses try to give LLMs a computer: HAGAR tells LLMs that the computer does not exist.**
AIs should focus on knowledge management rather than technical details (even though they are very good at both). The more a framework can automate, the less reasoning (and the fewer tokens) is required. That way even smaller models can express their full potential.

Or, put another way: for an LLM, HAGAR is reality.

# 1. Project vision

HAGAR is a harness for LLMs, developed in Python, designed for the safe execution of language models.

The goal is not merely to provide a chat interface for an LLM, but to create a ***safe and protected*** operating environment in which the LLM can use tools, consult a persistent memory and interact with external systems — all without having direct access to the real resources of the host machine — preventing or at least mitigating the most common mistakes.

For this reason I adopted principles and methodologies from both information security (principle of least privilege, CIA triad) and the HMI/HCI field (human-machine interaction/interface, typical of industrial machinery) and from cognitive ergonomics, applying them to the design of the environment in which the LLM operates: as is done with human work, HAGAR's further purpose is to create an environment for LLMs where doing the right thing is easy and making mistakes is hard.

On the basis of the above, and in order to establish a general rule of conduct for every future development of this software, I hereby state **the Four Laws of HAGAR**:

## 1.1 First Law of HAGAR
**An LLM is, by definition, unreliable.** This does not mean that it is malicious or useless, but that its operation is probabilistic in nature. Consequently, every statement it makes must be verified and every action it takes must be subject to constraints.

## 1.2 Second Law of HAGAR
**Tools are more reliable than the LLM.** If the file system says that a file exists, then it really exists. If a tool returns the size of a file, that size is real. The LLM interprets, but tools measure.

## 1.3 Third Law of HAGAR
**State must exist outside the LLM's "mind".** By implementing components such as `ToolRegistry`, `MCP`, `FilesystemSandbox`, `Memory` and `PermissionEvaluator`, we move knowledge and control outside the model itself. This is in line with standard practices for systems in which security is a critical requirement.

## 1.4 Fourth Law of HAGAR
**Every action must be explainable after the fact.** For this reason HAGAR implements an *audit log*: when something goes wrong — and sooner or later it will — the question must not be "Why did the LLM go crazy?", but "What assumptions did it adopt?", "Which tool did it use?", "Which data was wrong?". In other words, it must be possible to conduct an incident analysis, exactly as in aviation. HAGAR recognizes this need and will always provide the tools to do it.

## 1.5 Software Architecture

From a structural point of view, HAGAR is based on five fundamental principles:

- separation between the model and the operating system;
- security by default (*security by default*);
- plugin architecture;
- independence from any specific LLM provider;
- extensibility through tools (*tools*) and the MCP (Model Context Protocol).

---

# 2. Absolute Prohibitions

The model is absolutely forbidden to:

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

`pip install -e .` declares the `core`, `llm`, `memory` and
`local_tools` packages and installs the `hagar` command:

```powershell
hagar --config hagar.yaml
hagar --model qwen3:8b
hagar --no-memory
hagar --no-native-tools
hagar --version

# local web GUI
hagar web
hagar --config hagar.yaml web --port 8765
```

The web GUI uses `http://127.0.0.1:8765/`, a random token for the APIs,
modal ASK confirmations, turn stop, image upload, tabs for chat,
history, tool output, audit, thinking and memories, and cumulative
session tokens in the sidebar. For details see `MANUAL.md` §3.0.

The configuration is searched in the following order: the `--config` parameter,
the `HAGAR_CONFIG` environment variable and finally the `./hagar.yaml` file.
It is also possible to use `python -m hagar` working directly on the source code.

## 3.1 Layout

```
hagar.py            Harness launch script
hagar.yaml          Default configuration script
policy.yaml			Permission configuration for tools (built-in and MCP)
core/               config, agent, audit log, registry, sandbox, service and web server
llm/                LLM backends (Ollama, LM Studio, DeepSeek, OpenAI, Claude, Gemini), MCP client
memory/             SQLite memory (sqlite_store.py) and legacy markdown backend
web/                HTML, CSS and JavaScript of the local GUI
tests/              pytest suite
tools/              development helpers (test runner, sandbox shim, model benchmark)
local_tools/        built-in tools; the built-ins go through local_tools/plugins.py
core/plugins.py     plugin contracts and discovery (hagar.tools, hagar.llm)
core/subagents.py   manager of the synchronous, read-only MVP subagent
llm/plugins.py      built-in LLM providers registered as plugins
```

## 3.2 LLM backends

`model.provider` selects the backend. Tool schemas, message conversion and the native or fallback paths are handled in `llm/base.py`; therefore, changing provider does not require changes to the execution infrastructure (harness).

Native tool calling is the default for all backends. If a model rejects this mode (returning an HTTP 400, 404 or 422 error), the agent switches to the textual JSON protocol for the entire session; the use of the textual protocol can be forced by setting `model.native_tools: false` or by passing the `--no-native-tools` argument.

| provider   | transport                    | API key                |
|------------|------------------------------|------------------------|
| `ollama`   | native `/api/chat`           | none                   |
| `lmstudio` | local OpenAI-compatible      | none (optional)        |
| `deepseek` | OpenAI-compatible REST       | `DEEPSEEK_API_KEY`     |
| `openai`   | OpenAI Chat Completions      | `OPENAI_API_KEY`       |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

`chatgpt` is an alias of `openai`. A ChatGPT subscription does not give access to the API: an OpenAI key and API credit are required. LM Studio must have the local server running and a model loaded; the default endpoint is `http://localhost:1234/v1`. If the LM Studio server requires a key, you can set `LMSTUDIO_API_KEY` or `model.api_key_env`; otherwise it is not needed.

With LM Studio, native tool calling depends on the model and its template: some models accept the request but answer in text instead of emitting `tool_calls`. In that case use `model.native_tools: false` (textual JSON protocol) or a tool-capable model.

The model names currently supported for DeepSeek are `deepseek-flash` (default) and `deepseek-v4-pro`; the old `deepseek-chat` is no longer accepted. The live test uses `deepseek-flash`, unless it is overridden by the `HAGAR_LIVE_DEEPSEEK_MODEL` variable. The `tools/diagnose_deepseek.py` script lets you check DNS, the key format and the endpoint, without showing the key itself.

Keys are read only from environment variables and never from the YAML file. If the default variable name does not suit your needs, you can specify another one with `model.api_key_env`. The `model.host` parameter indicates the provider's base URL (with a specific default for each one; for example, Ollama uses `http://localhost:11434` and LM Studio `http://localhost:1234/v1`), `model.timeout` is the HTTP timeout in seconds (default 120) and `model.max_tokens` applies only to Claude (with a default value of 1024).

```yaml
model:
  provider: gemini
  name: gemini-2.0-flash
```

Each backend normalizes the dialogue according to its own format: Claude receives system messages in the dedicated `system` field and alternating turns, while Gemini receives `systemInstruction` and the `model` role. The protocol shared between the agent and the client uses exclusively the `user` and `assistant` roles.

## 3.3 Audit log

Each session appends entries in JSON Lines format to the path specified in `audit.path` (default value: `logs/audit.jsonl`, resolved relative to the configuration file):

```yaml
audit:
  enabled: true
  path: logs/audit.jsonl
  max_field_chars: 2000
```

Events recorded: `harness.start`, `turn.start`, `llm.tool_choice`, `llm.protocol_error`, `llm.repaired`, `llm.repair_failed`, `tool.call`, `tool.result`, `turn.answer`, `turn.error`, `turn.stop`, `mcp.loaded`, `mcp.failed`, `llm.failed`, `harness.stop`. The absence of a `harness.stop` event in the last session indicates that the process was forcibly terminated or crashed.

Each record includes a UTC timestamp, the session ID and, where applicable, a turn ID shared by all events relating to a single request. Data truncation is governed by the `audit.max_field_chars` parameter; API keys are never written to the log.

The log is intended to be consulted after an incident, not to be read by the model. Since it may contain the content of files read through the file system access tools, it must be treated with the same care reserved for the workspace itself.

## 3.4 Authorizations and `policy.yaml`

Every call to a tool is authorized before it is executed. A tool declares its own
**capabilities** (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`,
`FILESYSTEM_CREATE`, `FILESYSTEM_DELETE`, `MEMORY_READ`,
`MEMORY_WRITE`, `MCP_CALL`, ...); a **subject** (the agent) defines
rules that associate those capabilities with `allow`, `ask` or `deny`,
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

The `ask` option generates a prompt in the console of the type `shall I do it? (y/N)` (default value `N`); the `ConfirmationProvider` protocol also makes it possible to implement a modal dialog window in a graphical interface (GUI).
The policy file is read before the LLM is created: if it is missing or
invalid, every policy is set to `DENY`, the error is recorded in the audit log (`policy.failed`) and displayed in the chat, while the harness keeps running.

## 3.5 Memory

Memory is a local SQLite database and represents the source of truth:
sessions, turns, skills and summaries. The model can save memories with
`memory.create_skill`, list them with `memory.list_skills` and consult
previous turns with `memory.get_context`.

```yaml
memory:
  enabled: true
  backend: sqlite
  context_turns: 10
  max_skill_chars: 4000
```

The default database is `%LOCALAPPDATA%/Hagar/memory.db` (or
`HAGAR_MEMORY_DB`). The `markdown` backend remains only for compatibility.
Writes go through the policy engine. The CLI `/memory` commands
allow you to inspect chats, skills and statistics.

## 3.6 Decision tool

`decision.choose` asks a fixed-choice question and returns label,
probability and provider. It supports a decision LLM (local or remote) and a
local linear classifier. Details in [DECISIONS.md](DECISIONS.md).

## 3.7 Model cards and benchmarks

`/models test` measures latency, structured JSON and tool calling and saves
a JSON card with the hardware and the date of the last test. Details in
[MODEL_CARDS.md](MODEL_CARDS.md).

## 3.8 Hi-Fi mode

With `--hifi` Hagar asks the model for three interpretations of the request
and, if the two most likely ones are too close, asks for clarification
instead of answering. Details in [HIFI.md](HIFI.md).

## 3.9 Checkpoints, timeouts and context

Hagar saves a checkpoint of the files modified during the turn, limits
tool calls, spills large outputs and prunes old context.
Details in [RUNTIME_GUARDS.md](RUNTIME_GUARDS.md).

## 3.10 AIsh

`aish.exec` is a restricted semantic shell: commands are translated
into Hagar tools, not executed as programs. It is **DENY by default** and must be
explicitly enabled in `policy.yaml`. Details in [AISH.md](AISH.md).
Textual transformations use [text.transform](TEXT_TRANSFORM.md).

## 3.11 Development recipes

`dev.run` runs trusted recipes for tests, debug and build, without a shell and
without arbitrary commands. It is **DENY by default** and requires `DEV_EXEC`.
Details in [DEV_RUN.md](DEV_RUN.md).

## 3.12 Boxed transform

`box.run` runs bounded LLM transformations (`summarize`, `translate`,
`extract_json`) without memory, tools or free prompt. It is **DENY by default**
and requires `BOX_EXEC`. Details in [BOXES.md](BOXES.md).

## 3.13 Hagar Flow

`flow.run` runs a validated linear subset of Python interpreted by Hagar,
without imports, functions, try or access to Python objects. It is **DENY by
default** and requires `FLOW_EXEC`. Details in
[FLOW.md](FLOW.md).

---

# 4. Documentation

HAGAR has documentation in multiple languages. The currently supported languages
are: Italian, English, Spanish, Portuguese, Chinese, Russian. Each language has its own dedicated subdirectory in Docs.

- [MANUAL.md](MANUAL.md) — configuration format, console commands,
  command-line options, basic assumptions.
- [ARCHITECTURE.md](ARCHITECTURE.md) — The software architecture of this
  version of the harness: components, security model, known limits.
- [ROADMAP.md](ROADMAP.md) — Features planned for implementation, decisions already made
  and still open questions.
- [PLUGINS.md](PLUGINS.md) — contracts for tool and LLM provider plugins.
- [HIFI.md](HIFI.md) — interpretation and clarification pre-pass.
- [RUNTIME_GUARDS.md](RUNTIME_GUARDS.md) — checkpoints, timeouts, spill and compaction.
- [AISH.md](AISH.md) — restricted semantic shell and DENY policy.
- [TEXT_TRANSFORM.md](TEXT_TRANSFORM.md) — bounded textual transformations.
- [DEV_RUN.md](DEV_RUN.md) — recipes for tests, debug and build.
- [BOXES.md](BOXES.md) — bounded LLM transformations.
- [FLOW.md](FLOW.md) — restricted DSL and interpreter.
- [DECISIONS.md](DECISIONS.md) — decision tools and providers.
- [MODEL_CARDS.md](MODEL_CARDS.md) — cards, benchmarks and hardware.
- [DOCUMENT_TOOL.md](DOCUMENT_TOOL.md) — document tool specification,
  semantic graph, format plugins and native host.
- [SUBAGENTS.md](SUBAGENTS.md) — subagent MVP, isolation and limits.
- [CHANGELOG.md](CHANGELOG.md) — change history.
