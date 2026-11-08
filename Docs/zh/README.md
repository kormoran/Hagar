<p align="center">
  <img src="../HAGAR.jpg">
</p>

[Italiano](../it/README.md) · [English](../en/README.md) · [Español](../es/README.md) · [中文](../zh/README.md) · [Русский](../ru/README.md) · [Português](../pt/README.md) · [العربية](../ar/README.md)

# H.A.G.A.R.

面向 AI 的通用弹性智能体 harness（Harness Agentico Generale per AI Resiliente / General Resilient Agentic Harness for AIs）

# 0. 一切是如何开始的：安全

我开发 HAGAR，是因为没有其他 AI harness 默认隔离我的文件。无论是 DeepSeek、Claude Code、AutoGen 还是别的什么，只要任其自由运行，它们最终都会把你的文件系统暴露给 LLM。必须由**你**来施加限制，而且必须做得对，否则后果自负。这些工具没有一个能保证你的数据不会为了说不清的目的、出于失误，或两者兼有而被读取。而且，即便不是 harness 本身这样做，也可能是你刚装的那个很酷的插件、那个极其好用的 skill，或任何其他你刚添加的东西……

**HAGAR 颠覆了这一做法：由你决定 LLM 能看到什么、写入什么、搜索什么，以及在何处。** 任何 LLM 都无法读写你在配置文件中明确指定为可读或可写目录之外的任何内容。如果某个目录不在配置的 `[filesystem]` 段中，它就不存在：对 LLM 来说，就好像它从来不存在。

在开发 HAGAR 的过程中，我还产生了另一个疑问：LLM 为什么需要与操作系统交互？在人工智能领域，真正的性能瓶颈是模型调用，它可能耗时数秒（有时是很多秒）。直接访问操作系统只能节省几毫秒：值得为此冒险吗？我的回答是不值得。

因此，**HAGAR 尽一切可能把 LLM 与操作系统隔离开。** 每一次对文件、记忆或机器本身的交互都通过专门的工具完成（这些工具基于 MCP 协议，或直接集成在 HAGAR 中）。AI 不知道自己运行在哪个操作系统上，而且它永远不该知道：如果存在某种方式，让 AI 在 HAGAR 的隔离之下仍能推断出自己所运行的操作系统，我会把它视为安全漏洞并加以修复（或者至少记录该问题，以告知用户）。

|Harness	|可见宿主 FS	|可见操作系统		|隔离方式	  |
|-----------|---------------|---------------|-------------|
|Claude Code|部分		|是	 		|权限	  |
|Codex CLI	|部分		|是	 		|Sandbox	  |
|OpenHands	|否				|是	 		|Docker		  |
|E2B		|否				|是				|VM/容器 |
|`HAGAR`	|`否`			|`否`			|`虚拟 FS`|

**其他 harness 试图给 LLM 一台计算机：HAGAR 则告诉 LLM，计算机并不存在。**
AI 应当把精力放在知识管理上，而不是技术细节上（尽管它们在这两方面都很擅长）。一个框架能自动化的部分越多，所需的推理（以及 token 数量）就越少。这样，即使是最小的模型也能发挥出全部潜力。

或者换个说法：对 LLM 而言，HAGAR 就是现实。

# 1. 项目愿景

HAGAR 是一个用 Python 开发的 LLM harness，旨在安全地运行语言模型。

其目标不只是为 LLM 提供一个聊天界面，而是创建一个***安全且受保护***的运行环境，让 LLM 可以在其中使用工具、查阅持久记忆并与外部系统交互——同时不直接访问宿主机的真实资源——从而预防或至少缓解最常见的错误。

为此，我采纳了来自信息安全领域的原则与方法（最小权限原则、CIA 三元组），也吸收了 HMI/HCI 领域（人机交互/人机界面，常见于工业机械）以及认知工效学的做法，并把它们应用到 LLM 运行环境的设计中：正如在人的工作中那样，HAGAR 的进一步目标是为 LLM 创造一个"做对很容易、做错很困难"的环境。

基于上述内容，并为确立本软件未来一切开发的一般行为准则，我在此陈述**HAGAR 的四条法则**：

## 1.1 HAGAR 第一法则
**LLM 按定义就是不可靠的。** 这并不意味着它恶意或无用，而是说它的运行本质上是概率性的。因此，它的每一个断言都必须被核实，它的每一个动作都必须受到约束。

## 1.2 HAGAR 第二法则
**工具比 LLM 更可靠。** 如果文件系统说某个文件存在，那它就确实存在。如果某个工具返回文件大小，那个大小就是真实的。LLM 负责解释，工具负责测量。

## 1.3 HAGAR 第三法则
**状态必须存在于 LLM 的"心智"之外。** 通过实现 `ToolRegistry`、`MCP`、`FilesystemSandbox`、`Memory` 和 `PermissionEvaluator` 等组件，我们把知识与控制转移到模型自身之外。这符合那些将安全视为关键需求的系统的标准实践。

## 1.4 HAGAR 第四法则
**每一个动作都必须能在事后得到解释。** 因此 HAGAR 实现了*审计日志*：当事情出错时——迟早会出错——问题不应是"LLM 为什么发疯了？"，而应是"它采取了哪些前提假设？""它使用了哪个工具？""哪个数据是错误的？"。换句话说，必须能够像航空业那样进行事故分析。HAGAR 认识到这一必要性，并将始终提供进行这种分析的手段。

## 1.5 软件架构

从结构上看，HAGAR 建立在五项基本原则之上：

- 模型与操作系统之间的分离；
- 默认安全（*security by default*）；
- 插件架构；
- 独立于任何特定的 LLM 提供方；
- 通过工具（*tools*）和 MCP（Model Context Protocol）实现可扩展性。

---

# 2. 绝对禁令

模型被绝对禁止：

- 直接访问宿主机的文件系统；
- 在真实的操作系统 shell 中执行命令；
- 获取高于配置中所定义的权限；
- 得知真实的操作系统。

所有操作只能通过由 harness 注册并控制的工具进行。

---

# 3. 开发

## 3.0 安装与 CLI

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

`pip install -e .` 声明 `core`、`llm`、`memory` 和
`local_tools` 这些包，并安装 `hagar` 命令：

```powershell
hagar --config hagar.yaml
hagar --model qwen3:8b
hagar --no-memory
hagar --no-native-tools
hagar --version

# 本地 web GUI
hagar web
hagar --config hagar.yaml web --port 8765
```

web GUI 使用 `http://127.0.0.1:8765/`，为 API 使用随机 token，
提供 ASK 模态确认、轮次停止、图片上传，以及聊天、历史、工具输出、
审计、thinking 和记忆标签页，并在侧边栏显示会话的累计 token。
详情见 `MANUAL.md` §3.0。

配置文件的查找顺序如下：`--config` 参数、
环境变量 `HAGAR_CONFIG`，最后是文件 `./hagar.yaml`。
此外，也可以直接基于源代码使用 `python -m hagar`。

## 3.1 目录布局

```
hagar.py            harness 启动脚本
hagar.yaml          默认配置文件
policy.yaml			工具（内置与 MCP）的权限配置
core/               config、agent、审计日志、registry、sandbox、service 与 web server
llm/                LLM 后端（Ollama、LM Studio、DeepSeek、OpenAI、Claude、Gemini）、MCP 客户端
memory/             SQLite 记忆（sqlite_store.py）与遗留 markdown 后端
web/                本地 GUI 的 HTML、CSS 与 JavaScript
tests/              pytest 测试套件
tools/              开发辅助工具（测试运行器、sandbox shim、模型基准测试）
local_tools/        集成工具；内置工具经由 local_tools/plugins.py
core/plugins.py     插件（hagar.tools、hagar.llm）的契约与发现
core/subagents.py   同步、只读的 MVP 子智能体管理器
llm/plugins.py      以插件形式注册的内置 LLM provider
```

## 3.2 LLM 后端

`model.provider` 用于选择后端。工具的 schema、消息转换以及原生或回退路径都在 `llm/base.py` 中处理；因此，更换 provider 不需要修改执行基础设施（harness）。

原生 tool calling 是所有后端的默认设置。如果某个模型拒绝该模式（返回 HTTP 400、404 或 422 错误），智能体会在整个会话中切换到基于文本 JSON 的协议；也可以通过设置 `model.native_tools: false` 或传入 `--no-native-tools` 参数强制使用文本协议。

| provider   | 传输方式                    | API 密钥             |
|------------|------------------------------|------------------------|
| `ollama`   | 原生 `/api/chat`           | 无                |
| `lmstudio` | 本地 OpenAI 兼容    | 无（可选）    |
| `deepseek` | 兼容 OpenAI 的 REST  | `DEEPSEEK_API_KEY`     |
| `openai`   | OpenAI Chat Completions      | `OPENAI_API_KEY`       |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

`chatgpt` 是 `openai` 的别名。ChatGPT 订阅并不授予 API 访问权限：需要 OpenAI 密钥和 API 额度。LM Studio 必须已启用本地服务器并加载了模型；默认端点是 `http://localhost:1234/v1`。如果 LM Studio 服务器要求密钥，可以设置 `LMSTUDIO_API_KEY` 或 `model.api_key_env`；否则不需要。

在 LM Studio 中，原生 tool calling 取决于模型及其模板：有些模型接受请求，但以文本作答，而不是发出 `tool_calls`。这种情况下应使用 `model.native_tools: false`（文本 JSON 协议）或使用支持工具的模型。

目前 DeepSeek 支持的模型名称为 `deepseek-flash`（默认）和 `deepseek-v4-pro`；旧的 `deepseek-chat` 不再被接受。live 测试使用 `deepseek-flash`，除非被 `HAGAR_LIVE_DEEPSEEK_MODEL` 变量覆盖。脚本 `tools/diagnose_deepseek.py` 可用于检查 DNS、密钥格式和端点，而不会显示密钥本身。

密钥只从环境变量读取，绝不从 YAML 文件读取。如果默认的变量名不适合你的需求，可以用 `model.api_key_env` 指定另一个。参数 `model.host` 表示 provider 的 base URL（每个 provider 都有各自的默认值；例如 Ollama 使用 `http://localhost:11434`，LM Studio 使用 `http://localhost:1234/v1`），而 `model.timeout` 是以秒为单位的 HTTP 超时（默认 120），`model.max_tokens` 仅适用于 Claude（默认值为 1024）。

```yaml
model:
provider: gemini
name: gemini-2.0-flash
```

每个后端都按自己的格式规范化对话：Claude 在专用字段 `system` 中接收系统消息，并接收交替排列的轮次；而 Gemini 接收 `systemInstruction` 和 `model` 角色。智能体与客户端之间共享的协议只使用 `user` 和 `assistant` 两种角色。

## 3.3 审计日志

每个会话都会向 `audit.path` 指定的路径（默认值：`logs/audit.jsonl`，相对于配置文件解析）追加 JSON Lines 格式的记录：

```yaml
audit:
enabled: true
path: logs/audit.jsonl
max_field_chars: 2000
```

记录的事件：`harness.start`、`turn.start`、`llm.tool_choice`、`llm.protocol_error`、`llm.repaired`、`llm.repair_failed`、`tool.call`、`tool.result`、`turn.answer`、`turn.error`、`turn.stop`、`mcp.loaded`、`mcp.failed`、`llm.failed`、`harness.stop`。如果最近一次会话中缺少 `harness.stop` 事件，说明进程被强制终止或发生了崩溃。

每条记录都包含 UTC 时间戳、会话 ID，以及在适用情况下由同一请求的所有相关事件共享的轮次 ID。数据的截断由参数 `audit.max_field_chars` 控制；API 密钥绝不会写入日志。

日志的设计目的是在事故发生后供查阅，而不是供模型阅读。由于它可能包含通过文件系统访问工具读取的文件内容，因此必须像对待工作区（workspace）本身一样谨慎对待。

## 3.4 授权与 `policy.yaml`

每次工具调用在执行前都会被授权。工具声明自己的
**capability**（`FILESYSTEM_READ`、`FILESYSTEM_WRITE`、
`FILESYSTEM_CREATE`、`FILESYSTEM_DELETE`、`MEMORY_READ`、
`MEMORY_WRITE`、`MCP_CALL` 等）；**主体**（智能体）定义
规则，把这些功能关联到 `allow`（允许）、`ask`（询问）或 `deny`（拒绝），
并可按工具名称、路径前缀或命名空间加以限定。

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

`ask` 选项会在控制台生成形如 `lo faccio? (y/N)` 的请求（默认值为 `N`）；`ConfirmationProvider` 协议还允许在图形界面（GUI）中实现模态对话框。
策略文件在创建 LLM 之前读取：如果文件缺失或
无效，所有策略都会被设为 `DENY`，错误会被记录到审计日志（`policy.failed`）并显示在聊天中，而 harness 继续运行。

## 3.5 记忆

记忆是一个本地 SQLite 数据库，是事实的来源：
会话、轮次、skill 和摘要。模型可以用
`memory.create_skill` 保存记忆，用 `memory.list_skills` 列出这些记忆，并通过
`memory.get_context` 查阅先前的轮次。

```yaml
memory:
  enabled: true
  backend: sqlite
  context_turns: 10
  max_skill_chars: 4000
```

默认数据库为 `%LOCALAPPDATA%/Hagar/memory.db`（或者
`HAGAR_MEMORY_DB`）。`markdown` 后端仅为兼容性而保留。
写入操作会经过策略引擎。CLI 的 `/memory` 命令
可用于检查聊天、skill 和统计信息。

## 3.6 Decision tool

`decision.choose` 提出一个固定选项的问题，并返回标签、
概率和 provider。它支持一个决策用 LLM（本地或远程）以及一个
本地线性分类器。详见 [DECISIONS.md](DECISIONS.md)。

## 3.7 模型卡片与基准测试

`/models test` 测量延迟、结构化 JSON 和 tool calling，并保存
一份包含硬件和最近一次测试日期的 JSON 卡片。详见
[MODEL_CARDS.md](MODEL_CARDS.md)。

---

# 4. 文档

HAGAR 拥有多语言文档。目前支持的语言
包括：意大利语、英语、西班牙语、葡萄牙语、中文、俄语。每种语言在 Docs 中都有专属子目录。

- [MANUAL.md](MANUAL.md) — 配置格式、控制台命令、
  命令行选项、基本前提假设。
- [ARCHITECTURE.md](ARCHITECTURE.md) — 本版本 harness
  的软件架构：组件、安全模型、已知限制。
- [ROADMAP.md](ROADMAP.md) — 计划实现的功能、已做出的决定
  以及仍待解决的问题。
- [PLUGINS.md](PLUGINS.md) — 工具与 LLM provider 插件的契约。
- [DOCUMENT_TOOL.md](DOCUMENT_TOOL.md) — document tool 的规范、
  语义图、格式插件与原生宿主。
- [SUBAGENTS.md](SUBAGENTS.md) — 子智能体 MVP、隔离与限制。
- [CHANGELOG.md](CHANGELOG.md) — 变更历史。
