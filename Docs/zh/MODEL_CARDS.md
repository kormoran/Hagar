# 模型技术卡片

**状态：** 已实现
**命令：** `/models list`、`/models show`、`/models test`、`/models hardware`

## 目的

卡片用实测数据而非猜测为未来的 LLM broker 提供输入。每个 provider/模型
组合都以 JSON 形式保存到：

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

或者 `HAGAR_MODEL_CARDS`，或 `$XDG_STATE_HOME/hagar/models`。

## 格式

```json
{
  "card_version": 1,
  "provider": "lmstudio",
  "model": "gemma-3-27b-it",
  "tested_at": "2026-11-08T20:00:00+00:00",
  "last_tested_at": "2026-11-08T20:00:00+00:00",
  "hardware": {
    "platform": "Windows",
    "cpu": {
      "model": "...",
      "physical_cores": 8,
      "logical_cores": 16,
      "mhz_current": 3600,
      "mhz_max": 4200,
      "ghz_current": 3.6,
      "ghz_max": 4.2
    },
    "memory": {
      "total_bytes": 34359738368,
      "total_gib": 32.0,
      "available_bytes": 17179869184,
      "available_gib": 16.0
    },
    "gpus": [
      {
        "name": "NVIDIA ...",
        "vendor": "NVIDIA",
        "vram_bytes": 8589934592,
        "driver": "...",
        "api": "CUDA"
      }
    ]
  },
  "capabilities": {
    "chat": true,
    "structured_json": true,
    "tool_calling": true,
    "native_tools": true
  },
  "benchmarks": {
    "chat": {
      "attempts": 3,
      "successes": 3,
      "duration_ms": {
        "count": 3,
        "min": 500.0,
        "mean": 700.0,
        "p50": 680.0,
        "p95": 800.0,
        "max": 800.0
      },
      "output_tokens_per_second": 42.5,
      "errors": []
    },
    "structured": {
      "attempts": 3,
      "valid_json": 3,
      "valid_choice": 3,
      "duration_ms": {},
      "errors": []
    },
    "tool_call": {
      "attempts": 2,
      "successes": 2,
      "duration_ms": {},
      "errors": []
    }
  }
}
```

`last_tested_at` 始终存在，并在每次 `/models test` 时更新。

## 测量内容

- 聊天延迟：min、平均值、p50、p95、max；
- 每秒输出 token 数；
- JSON 有效性；
- 在 label 集合中的有效选择；
- 使用一个基准 tool 进行 tool calling；
- 在文本任务上的确定性质量；
- 在合成图像上的 vision 质量；
- 测试时的硬件。

## 按任务的质量

`/models test` 还会运行一套确定性的质量测试：

```text
extraction   JSON 字段提取
instruction  精确指令遵循
reasoning    简单数值计算
coding       Python 片段阅读
summary      带要点的摘要
translation  IT→EN 与 EN→IT 翻译
```

每个用例执行两次。得分是各回答的平均值，范围 0 到 1。它不是
语义基准测试：它是一项紧凑、可重复的测试，为 broker 提供比
声明质量更好的信号。

翻译把 chrF 与 path、命令和必需术语的保持结合起来。必需术语的
权重远高于 chrF；错误的技术翻译会被明确扣分。摘要衡量要点的
出现情况以及对长度的遵守。

卡片包含：

```json
{
  "quality": {
    "suite_version": 3,
    "overall": 0.75,
    "tasks": {
      "extraction": {"attempts": 2, "mean": 0.83},
      "instruction": {"attempts": 2, "mean": 1.0},
      "reasoning": {"attempts": 2, "mean": 1.0},
      "coding": {"attempts": 2, "mean": 0.5},
      "summary": {"attempts": 2, "cases": 2, "mean": 0.8},
      "translation": {"attempts": 2, "cases": 2, "mean": 0.7}
    }
  }
}
```

语料位于 `benchmarks/corpus/`：

```text
7 段文本
2 个翻译 reference
10 张合成图像
带 SHA-256 的 manifest.yaml
```

文本套件是 `quality_v3`；vision 套件是 `vision_v2`。

TaskProfile 中的 `quality_task` 选择要使用的任务；如果没有，
broker 使用配置档案的名称。如果卡片没有实测质量，则使用
目录中声明的质量。

## Provider discovery

命令：

```text
/models discover lmstudio
/models discover ollama
```

读取运行时元数据，并将其规范化为 `ProviderModelInfo`：

```text
provider
model
model_type
context_window
quantization
state
capabilities
hagar_capabilities
```

映射：

```text
LM Studio tool_use     → tool_calling
LM Studio type vlm     → vision
Ollama tools           → tool_calling
Ollama thinking        → reasoning
Ollama vision          → vision
Ollama completion      → text_generation
```

`completion` 不会自动映射到 `chat`：一个模型可以完成文本
而不具备对话能力。`chat` 仍然是需要校验的 capability。

## 记忆与上下文

`memory_bench` 使用合成的对话：

```text
简单 recall
distractor
两条记忆之间的矛盾
持久指令
长上下文
错误前提
```

结果会进入质量任务 `memory`；`memory_chat` 配置档案把它用于
broker。始终不会使用用户的真实记忆。

## P1 基准测试

```text
tool      → 多个 tool、distractor、参数检查
JSON      → schema_valid 与 field_f1
coding    → 在子进程中执行的单元测试
production → 带 tool 和记忆的 prompt、真实延迟
```

可执行的 coding 应被视为可信的本地基准测试：它在带超时的
临时进程中执行模型生成的代码。

## 不适用的套件

不相关的套件不等于零分：

```json
{
  "vision": {
    "not_applicable": true,
    "reason": "model type does not support vision"
  }
}
```

`verified_capabilities` 把 `not_applicable` 视为缺失的
capability，而不是零分。live run 以这种方式标记 `llm` 模型的
vision。

## 经验证的 capability

卡片区分：

```text
capabilities           由目录声明
capabilities_verified  由基准测试测量
```

Capability：

```text
chat
coding
structured_json
tool_calling
native_tools
vision
ocr
reasoning
```

broker 在存在时使用 `capabilities_verified`。一个声称支持 `chat`
但拒绝对话的模型不会被选用于 chat 配置档案；它仍可被选用于
`coding` 或 `tool_calling`。

示例：

```json
{
  "capabilities": {
    "chat": false,
    "coding": true,
    "structured_json": true,
    "tool_calling": true,
    "native_tools": true,
    "vision": false,
    "ocr": false,
    "reasoning": true
  }
}
```

## 自适应超时

broker 使用卡片的 p95 延迟来估算单次调用的超时：

```text
timeout = clamp(p95 * safety * input_factor * output_factor, floor, ceiling)
```

配置：

```yaml
timeouts:
  adaptive: true
  floor_seconds: 30
  ceiling_seconds: 900
  safety_factor: 1.5
  cold_start_seconds: 120
  turn_ceiling_seconds: 1800
```

慢速工具单独配置：

```yaml
tools:
  timeout: 120
  timeouts:
    document.ocr_pdf: 900
```

轮次不会低于已配置工具的最大超时。

## 回答与 reasoning

LM Studio 可能把回答文本放在：

```text
message.content
message.reasoning_content
message.reasoning
message.thinking
```

Hagar 使用 `content` 作为主要回答。如果它为空，则使用清理后的
reasoning 作为回退，并记录 `llm.reasoning_fallback`。如果模型
同时有 tool call，reasoning 绝不替代文本：工具调用保持优先。

某些模型会返回 chat template 的 wrapper：

```text
<|im_start|>assistant ... <|im_end|>
<start_of_turn>model ... <end_of_turn>
<answer> ... </answer>
<thinking> ... </thinking>
```

Hagar 会移除这些已知 wrapper，但不会移除像 `<b>...</b>` 这样的
通用 HTML。被清理的回答会记录 `llm.text_cleaned`。

## Vision

仅在请求时：

```text
/models test vision
```

使用合成且固定的图像池：

```text
主色
物体计数
空间关系
OCR
柱状图
UI 字段
小字号文本的 OCR
带标签的图表
多字段 UI
场景描述
```

每张图像在 run 中都有 id 和 SHA-256。得分是用例的平均值。
不具备 vision 能力的模型不应使用该命令测试。

## 运行历史

每次 `/models test` 还会保存一次独立的 run：

```text
%LOCALAPPDATA%/Hagar/benchmark-runs/<run_id>.json
```

或者 `HAGAR_BENCHMARK_RUNS`。

命令：

```text
/models runs
/models runs 5
```

卡片包含最近一次结果；历史保留各次 run 以便长期对比。卡片
不会被删除。

每次 run 还包含 `suite_manifest`，其中有：

```text
套件版本
质量用例与 prompt
vision 图像、id 与 SHA-256
```

这样即使套件被扩展，某个结果仍然可解释。

尚不测量：

- 回答的语义质量；
- 概率的校准；
- 在特定数据集上的准确率；
- 流式模式下的 TTFT；
- 并发负载；
- 能耗；
- 音频；
- 人类偏好。

## 命令

```text
/models list
/models show <provider> <model>
/models test
/models test vision
/models runs [n]
/models hardware
```

`/models test` 测试当前的 LLM 模型并保存卡片。
`/models test vision` 运行 vision 套件。

## 硬件

`detect_hardware()` 是尽力而为且跨平台的：

- Windows：registry、`GlobalMemoryStatusEx`、`wmic`、`nvidia-smi`；
- Linux：`/proc/cpuinfo`、`/proc/meminfo`、`/sys/class/drm`、`nvidia-smi`；
- macOS：`sysctl`、`system_profiler`。

无法检测的字段保持 `null`，而不是零。缺少某项数据并不
意味着该硬件不存在。

## 未来在 broker 中的用途

broker 将使用卡片来过滤和排序：

```text
所需 capability
可用硬件
足够的 RAM/VRAM
p50/p95 延迟
成本
本地性
最近一次测试
```

旧卡片不应删除：应标记为已过期或重新测试。
