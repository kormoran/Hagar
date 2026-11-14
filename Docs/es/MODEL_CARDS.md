# Tarjetas de modelo

**Estado:** implementado
**Comandos:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Propósito

Las tarjetas alimentan el futuro broker LLM con datos medidos, no con
suposiciones. Se guarda una tarjeta por proveedor/modelo como JSON en:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

o bien en `HAGAR_MODEL_CARDS`, o en `$XDG_STATE_HOME/hagar/models`.

## Formato

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

`last_tested_at` siempre está presente y se actualiza en cada `/models test`.

## Qué mide

- latencia de chat: min, media, p50, p95, max;
- tokens de salida por segundo;
- validez del JSON;
- elección válida dentro del conjunto de etiquetas;
- tool calling con un tool de benchmark;
- calidad determinista en tareas textuales;
- calidad vision en imágenes sintéticas;
- hardware en el momento de la prueba.

## Calidad por tarea

`/models test` ejecuta también una suite de calidad determinista:

```text
extraction   extracción de campos en JSON
instruction  respeto de una instrucción exacta
reasoning    cálculo numérico simple
coding       lectura de un fragmento de Python
summary      resumen con puntos clave
translation  traducción IT→EN y EN→IT
```

Cada caso se ejecuta dos veces. La puntuación es la media de las
respuestas, de 0 a 1. No es un benchmark semántico: es un test compacto y
repetible para dar al broker una señal mejor que la calidad
declarada.

La traducción combina chrF con la conservación de path, comandos y
términos requeridos. Los términos obligatorios pesan mucho más que chrF; una
traducción técnica equivocada se penaliza explícitamente. El
resumen mide la presencia de los puntos clave y el respeto de la
longitud.

La tarjeta contiene:

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

El corpus está en `benchmarks/corpus/`:

```text
7 textos
2 reference de traducción
10 imágenes sintéticas
manifest.yaml con SHA-256
```

La suite textual es `quality_v3`; la suite vision es `vision_v2`.

Un `quality_task` en el TaskProfile selecciona el task que se debe usar; si falta,
el broker usa el nombre del perfil. Si la tarjeta no tiene calidad medida,
usa la calidad declarada en el catálogo.

## Descubrimiento del proveedor

Comando:

```text
/models discover lmstudio
/models discover ollama
```

Lee los metadatos del runtime y los normaliza en `ProviderModelInfo`:

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

Mapping:

```text
LM Studio tool_use     → tool_calling
LM Studio type vlm     → vision
Ollama tools           → tool_calling
Ollama thinking        → reasoning
Ollama vision          → vision
Ollama completion      → text_generation
```

`completion` no se mapea automáticamente a `chat`: un modelo
puede completar texto sin ser conversacional. `chat` sigue siendo una
capability que hay que verificar.

## Memoria y contexto

`memory_bench` usa conversaciones sintéticas:

```text
recall simple
distractor
contradicción entre dos memorias
instrucción persistente
contexto largo
falsa premisa
```

El resultado alimenta el task de calidad `memory`; el perfil
`memory_chat` lo usa para el broker. Nunca se usan memorias reales
del usuario.

## Benchmark P1

```text
tool      → más tool, distractor, control de argumentos
JSON      → schema_valid y field_f1
coding    → unit test ejecutados en subproceso
production → prompt con tool y memoria, latencia real
```

El coding ejecutable debe considerarse un benchmark local de confianza: ejecuta
código generado por el modelo en un proceso temporal con timeout.

## Suites no aplicables

Una suite no pertinente no vale cero:

```json
{
  "vision": {
    "not_applicable": true,
    "reason": "model type does not support vision"
  }
}
```

`verified_capabilities` trata `not_applicable` como capability ausente,
no como puntuación cero. La run live marca así los modelos `llm` para la
vision.

## Capability verificadas

La tarjeta distingue:

```text
capabilities           declaradas por el catálogo
capabilities_verified  medidas por el benchmark
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

El broker usa `capabilities_verified` cuando está presente. Un modelo que
declara `chat` pero rechaza la conversación no se selecciona para un
perfil chat; puede ser seleccionado igualmente para `coding` o
`tool_calling`.

Ejemplo:

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

## Timeout adaptativos

El broker usa la latencia p95 de la tarjeta para estimar el timeout de la
llamada individual:

```text
timeout = clamp(p95 * safety * input_factor * output_factor, floor, ceiling)
```

Configuración:

```yaml
timeouts:
  adaptive: true
  floor_seconds: 30
  ceiling_seconds: 900
  safety_factor: 1.5
  cold_start_seconds: 120
  turn_ceiling_seconds: 1800
```

Los tool lentos se configuran por separado:

```yaml
tools:
  timeout: 120
  timeouts:
    document.ocr_pdf: 900
```

El turno no baja del timeout máximo de los tool configurados.

## Respuestas y reasoning

LM Studio puede poner el texto de la respuesta en:

```text
message.content
message.reasoning_content
message.reasoning
message.thinking
```

Hagar usa `content` como respuesta principal. Si está vacío, usa el
reasoning limpiado como fallback y registra `llm.reasoning_fallback`.
Si el modelo tiene también tool call, el reasoning no sustituye nunca el
texto: la llamada al tool sigue siendo prioritaria.

Algunos modelos devuelven wrapper de chat template:

```text
<|im_start|>assistant ... <|im_end|>
<start_of_turn>model ... <end_of_turn>
<answer> ... </answer>
<thinking> ... </thinking>
```

Hagar elimina estos wrapper conocidos, pero no HTML genérico como
`<b>...</b>`. Las respuestas limpiadas registran `llm.text_cleaned`.

## Vision

Solo bajo petición:

```text
/models test vision
```

Usa un pool sintético y fijo de imágenes:

```text
color dominante
recuento de objetos
relación espacial
OCR
gráfico de barras
campo UI
OCR con texto pequeño
gráfico con etiquetas
UI de varios campos
descripción de una escena
```

Cada imagen tiene un id y un SHA-256 en el run. La puntuación es la media
de los casos. Un modelo sin capacidad vision no debe probarse con
este comando.

## Historial de los run

Cada `/models test` guarda además un run separado:

```text
%LOCALAPPDATA%/Hagar/benchmark-runs/<run_id>.json
```

o bien `HAGAR_BENCHMARK_RUNS`.

Comandos:

```text
/models runs
/models runs 5
```

La tarjeta contiene el último resultado; el historial conserva los run para las
comparaciones en el tiempo. Las tarjetas no se borran.

Cada run contiene también `suite_manifest`, con:

```text
versión de la suite
casos de calidad y prompt
imágenes vision, id y SHA-256
```

De este modo un resultado sigue siendo interpretable incluso cuando las suites
se amplían.

Todavía no mide:

- calidad semántica de las respuestas;
- calibración de las probabilidades;
- exactitud sobre un dataset específico;
- TTFT en streaming;
- carga concurrente;
- consumo energético;
- audio;
- preferencia humana.

## Comandos

```text
/models list
/models show <provider> <model>
/models test
/models test vision
/models runs [n]
/models hardware
```

`/models test` prueba el modelo LLM actual y guarda la tarjeta.
`/models test vision` ejecuta la suite vision.

## Hardware

`detect_hardware()` es best-effort y multiplataforma:

- Windows: registry, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

Los campos que no se pueden detectar quedan en `null`, no en cero. La
ausencia de un dato no significa que el hardware no exista.

## Uso futuro en el broker

El broker usará la tarjeta para filtrar y ordenar:

```text
capabilities solicitadas
hardware disponible
RAM/VRAM suficientes
latencia p50/p95
costo
localidad
última prueba
```

Una tarjeta antigua no debe borrarse: debe marcarse como caducada o
volverse a probar.
