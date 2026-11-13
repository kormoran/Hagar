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
- 测试时的硬件。

尚不测量：

- 回答的语义质量；
- 概率的校准；
- 在特定数据集上的准确率；
- 流式模式下的 TTFT；
- 并发负载；
- 能耗。

## 命令

```text
/models list
/models show <provider> <model>
/models test
/models hardware
```

`/models test` 测试当前的 LLM 模型并保存卡片。

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
