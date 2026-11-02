## 0 H.A.G.A.R.

Harness Agentico Generale per AI Resilienti (General Agentic Harness for Resilient AIs)


# 1. Project Vision

Hagar is an LLM harness developed in Python, designed for the resilient execution of LLMs.

The goal is not merely to provide a chat interface with a language model, but to create a ***secure*** operating environment in which an LLM can use tools, consult persistent memory, and interact with external systems — all without having direct access to the host machine's actual resources — while preventing or at least mitigating common errors.

To this end, we adopt principles and methodologies from HMI/HCI (Human-Machine Interface/Interaction for industrial machinery) and Cognitive Ergonomics, applying them to the design of the environment in which the LLM operates. As a first iteration of the project, we define **The Four Laws of HAGAR**:

## 1.1 First Law of HAGAR
**An LLM is, by definition, untrustworthy.** This is not because it is malicious or useless, but because it is probabilistic. Therefore, every statement it makes must be verified, and every action it takes must be constrained.

## 1.2 Second Law of HAGAR
**Tools are more reliable than the LLM.** If the filesystem indicates that a file exists, it exists. If a tool returns a file size, that size is real. The LLM interprets, but tools provide measurements.

## 1.3 Third Law of HAGAR
**State must exist outside the LLM’s "mind."** By implementing components such as `ToolRegistry`, `MCP`, `FilesystemSandbox`, and (forthcoming) `PermissionEvaluator`, we shift knowledge and control outside of the model itself. This aligns with standard practices for safety-critical systems. 

## 1.4 HAGAR’s Fourth Law
**Every action must be explainable after the fact.** An audit log is essential: when something goes wrong — and eventually it will — the question should not be "Why did the LLM go haywire?" but rather: "What assumption did it make?" "Which tool did it use?" "Which piece of data was incorrect?" In other words: incident investigation — much like in aviation.

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

## 3.1 Test suite

The suite runs offline and covers configuration, the filesystem sandbox,
the tool registry, the agent loop, the audit log, every LLM backend,
Ollama response parsing, the MCP client, the vault and the harness wiring.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
.\tools\run_tests.ps1
```

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
```

## 3.3 LLM backends

`model.provider` selects the backend. The agent loop, tool selection and
JSON parsing are shared (`llm/base.py`), so switching provider does not
change the harness.

| provider   | transport                    | API key                |
|------------|------------------------------|------------------------|
| `ollama`   | native `/api/chat`           | none                   |
| `deepseek` | OpenAI-compatible REST       | `DEEPSEEK_API_KEY`     |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

Keys are read from the environment, never from the YAML file. If the
default variable name does not suit you, set `model.api_key_env`.
`model.host` is only used by Ollama (default `http://localhost:11434`) and
`model.max_tokens` only by Claude (default 1024).

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

## 3.5 Model check

`tools/bench_models.py` runs a few representative turns (read, stat,
create, chat without tools) against a temporary sandbox and prints one
JSON line per model/task: tool calls with arguments, tool results, JSON
repairs, elapsed time and the final answer.

```powershell
.\.venv\Scripts\python.exe tools\bench_models.py
.\.venv\Scripts\python.exe tools\bench_models.py llama3.1:latest
```

It needs a running Ollama server and already pulled models; the scratch
area is `.bench/` (gitignored).
