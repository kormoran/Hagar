# Паспорта моделей

**Статус:** реализовано
**Команды:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Назначение

Паспорта снабжают будущий брокер LLM измеренными данными, а не
предположениями. Один паспорт на провайдера/модель сохраняется в формате
JSON в:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

либо в `HAGAR_MODEL_CARDS`, либо в `$XDG_STATE_HOME/hagar/models`.

## Формат

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

`last_tested_at` присутствует всегда и обновляется при каждом
`/models test`.

## Что измеряется

- задержка чата: min, среднее, p50, p95, max;
- токены вывода в секунду;
- валидность JSON;
- валидный выбор в множестве меток;
- вызов инструментов с помощью тестового инструмента;
- аппаратное обеспечение на момент проверки.

Пока не измеряется:

- семантическое качество ответов;
- калибровка вероятностей;
- точность на конкретном наборе данных;
- TTFT в потоковом режиме;
- конкурентная нагрузка;
- энергопотребление.

## Команды

```text
/models list
/models show <provider> <model>
/models test
/models hardware
```

`/models test` проверяет текущую модель LLM и сохраняет паспорт.

## Аппаратное обеспечение

`detect_hardware()` работает по принципу best-effort и является
многоплатформенным:

- Windows: реестр, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

Поля, которые не удаётся определить, остаются `null`, а не нулём.
Отсутствие данных не означает, что оборудования не существует.

## Будущее использование в брокере

Брокер будет использовать паспорт для фильтрации и сортировки:

```text
требуемые возможности
доступное оборудование
достаточные RAM/VRAM
задержка p50/p95
стоимость
локальность
последняя проверка
```

Старый паспорт нельзя удалять: его нужно помечать как устаревший или
проверять повторно.
