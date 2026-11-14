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
- детерминированное качество на текстовых задачах;
- качество vision на синтетических изображениях;
- аппаратное обеспечение на момент проверки.

## Качество по задачам

`/models test` также выполняет детерминированный набор тестов качества:

```text
extraction   извлечение полей в JSON
instruction  соблюдение точной инструкции
reasoning    простой численный расчёт
coding       чтение фрагмента Python
summary      сводка с ключевыми пунктами
translation  перевод IT→EN и EN→IT
```

Каждый случай выполняется дважды. Оценка — среднее ответов, от 0 до 1.
Это не семантический бенчмарк: это компактный и воспроизводимый тест,
дающий брокеру сигнал лучше заявленного качества.

Перевод сочетает chrF с сохранением путей, команд и требуемых
терминов. Обязательные термины весят гораздо больше chrF; неверный
технический перевод штрафуется явно. Сводка измеряет наличие ключевых
пунктов и соблюдение длины.

Паспорт содержит:

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

Корпус находится в `benchmarks/corpus/`:

```text
7 текстов
2 эталона перевода
10 синтетических изображений
manifest.yaml с SHA-256
```

Текстовый набор — `quality_v3`; набор vision — `vision_v2`.

`quality_task` в TaskProfile выбирает используемую задачу; если его нет,
брокер использует имя профиля. Если у паспорта нет измеренного качества,
используется качество, заявленное в каталоге.

## Обнаружение провайдера

Команда:

```text
/models discover lmstudio
/models discover ollama
```

Она читает метаданные runtime и нормализует их в `ProviderModelInfo`:

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

Сопоставление:

```text
LM Studio tool_use     → tool_calling
LM Studio type vlm     → vision
Ollama tools           → tool_calling
Ollama thinking        → reasoning
Ollama vision          → vision
Ollama completion      → text_generation
```

`completion` не сопоставляется автоматически с `chat`: модель
может завершать текст, не будучи разговорной. `chat` остаётся
capability, которую нужно проверить.

## Память и контекст

`memory_bench` использует синтетические диалоги:

```text
простой recall
distractor
противоречие между двумя памятями
постоянная инструкция
длинный контекст
ложная предпосылка
```

Результат питает задачу качества `memory`; профиль
`memory_chat` использует её для брокера. Реальные памяти
пользователя никогда не используются.

## Benchmark P1

```text
tool       → несколько инструментов, distractor, контроль аргументов
JSON       → schema_valid и field_f1
coding     → unit-тесты, выполняемые в подпроцессе
production → prompt с инструментами и памятью, реальная задержка
```

Исполняемый coding следует считать доверенным локальным бенчмарком: он
выполняет сгенерированный моделью код во временном процессе с тайм-аутом.

## Неприменимые наборы

Неподходящий набор не оценивается нулём:

```json
{
  "vision": {
    "not_applicable": true,
    "reason": "model type does not support vision"
  }
}
```

`verified_capabilities` трактует `not_applicable` как отсутствующую
capability, а не как нулевую оценку. Живой run так помечает модели `llm`
для vision.

## Проверенные capability

Паспорт различает:

```text
capabilities           заявленные каталогом
capabilities_verified  измеренные бенчмарком
```

Capability:

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

Брокер использует `capabilities_verified`, когда оно присутствует. Модель,
заявляющая `chat`, но отказывающаяся от разговора, не выбирается для
профиля chat; при этом она может быть выбрана для `coding` или
`tool_calling`.

Пример:

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

## Адаптивные тайм-ауты

Брокер использует задержку p95 из паспорта, чтобы оценить тайм-аут
отдельного вызова:

```text
timeout = clamp(p95 * safety * input_factor * output_factor, floor, ceiling)
```

Конфигурация:

```yaml
timeouts:
  adaptive: true
  floor_seconds: 30
  ceiling_seconds: 900
  safety_factor: 1.5
  cold_start_seconds: 120
  turn_ceiling_seconds: 1800
```

Медленные инструменты настраиваются отдельно:

```yaml
tools:
  timeout: 120
  timeouts:
    document.ocr_pdf: 900
```

Ход не опускается ниже максимального тайм-аута настроенных инструментов.

## Ответы и reasoning

LM Studio может помещать текст ответа в:

```text
message.content
message.reasoning_content
message.reasoning
message.thinking
```

Hagar использует `content` как основной ответ. Если он пуст, то
использует очищенный reasoning как fallback и регистрирует
`llm.reasoning_fallback`. Если у модели есть и вызовы инструментов,
reasoning никогда не заменяет текст: вызов инструмента остаётся
приоритетным.

Некоторые модели возвращают обёртки шаблона чата:

```text
<|im_start|>assistant ... <|im_end|>
<start_of_turn>model ... <end_of_turn>
<answer> ... </answer>
<thinking> ... </thinking>
```

Hagar удаляет эти известные обёртки, но не произвольный HTML вроде
`<b>...</b>`. Очищенные ответы регистрируют `llm.text_cleaned`.

## Vision

Только по запросу:

```text
/models test vision
```

Используется синтетический и фиксированный пул изображений:

```text
доминирующий цвет
подсчёт объектов
пространственное отношение
OCR
столбчатая диаграмма
поле UI
OCR с мелким текстом
диаграмма с подписями
UI с несколькими полями
описание сцены
```

У каждого изображения есть id и SHA-256 в run. Оценка — среднее
случаев. Модель без возможности vision не должна тестироваться этой
командой.

## История запусков

Каждый `/models test` также сохраняет отдельный run:

```text
%LOCALAPPDATA%/Hagar/benchmark-runs/<run_id>.json
```

или `HAGAR_BENCHMARK_RUNS`.

Команды:

```text
/models runs
/models runs 5
```

Паспорт содержит последний результат; история хранит запуски для
сравнений во времени. Паспорта не удаляются.

Каждый run также содержит `suite_manifest` с:

```text
версия набора
случаи качества и prompt
изображения vision, id и SHA-256
```

Так результат остаётся интерпретируемым, даже когда наборы
расширяются.

Пока не измеряется:

- семантическое качество ответов;
- калибровка вероятностей;
- точность на конкретном наборе данных;
- TTFT в потоковом режиме;
- конкурентная нагрузка;
- энергопотребление;
- аудио;
- человеческое предпочтение.

## Команды

```text
/models list
/models show <provider> <model>
/models test
/models test vision
/models runs [n]
/models hardware
```

`/models test` проверяет текущую модель LLM и сохраняет паспорт.
`/models test vision` выполняет набор vision.

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
