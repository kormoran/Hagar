# Fichas técnicas dos modelos

**Estado:** implementado
**Comandos:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Objetivo

As fichas alimentam o futuro broker LLM com dados medidos, não com
suposições. Uma ficha por provider/modelo é guardada como JSON em:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

ou `HAGAR_MODEL_CARDS`, ou `$XDG_STATE_HOME/hagar/models`.

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

`last_tested_at` está sempre presente e é atualizado a cada `/models test`.

## O que mede

- latência de chat: min, média, p50, p95, max;
- tokens de output por segundo;
- validade do JSON;
- escolha válida no conjunto de labels;
- tool calling com uma tool de benchmark;
- qualidade determinística em tarefas textuais;
- qualidade vision em imagens sintéticas;
- hardware no momento do teste.

## Qualidade por tarefa

`/models test` executa também uma suite de qualidade determinística:

```text
extraction   extração de campos em JSON
instruction  cumprimento de uma instrução exata
reasoning    cálculo numérico simples
coding       leitura de um fragmento Python
summary      resumo com pontos-chave
translation  tradução IT→EN e EN→IT
```

Cada caso é executado duas vezes. A pontuação é a média das respostas,
de 0 a 1. Não é um benchmark semântico: é um teste compacto e repetível
para dar ao broker um sinal melhor do que a qualidade declarada.

A tradução combina chrF com a conservação de paths, comandos e termos
exigidos. Os termos obrigatórios pesam muito mais do que chrF; uma
tradução técnica errada é penalizada explicitamente. O resumo mede a
presença dos pontos-chave e o cumprimento do comprimento.

A ficha contém:

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

O corpus está em `benchmarks/corpus/`:

```text
7 textos
2 reference de tradução
10 imagens sintéticas
manifest.yaml com SHA-256
```

A suite textual é `quality_v3`; a suite vision é `vision_v2`.

Um `quality_task` no TaskProfile seleciona a tarefa a usar; se faltar,
o broker usa o nome do perfil. Se a ficha não tiver qualidade medida,
usa a qualidade declarada no catálogo.

## Discovery do provider

Comando:

```text
/models discover lmstudio
/models discover ollama
```

Lê os metadados do runtime e normaliza-os em `ProviderModelInfo`:

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

`completion` não é mapeado automaticamente para `chat`: um modelo pode
completar texto sem ser conversacional. `chat` continua a ser uma
capability a verificar.

## Memória e contexto

`memory_bench` usa conversas sintéticas:

```text
recall simples
distractor
contradição entre duas memórias
instrução persistente
contexto longo
falsa premissa
```

O resultado alimenta a tarefa de qualidade `memory`; o perfil
`memory_chat` usa-o para o broker. Nunca são usadas memórias reais do
utilizador.

## Benchmark P1

```text
tool      → mais ferramentas, distractor, controlo de argumentos
JSON      → schema_valid e field_f1
coding    → unit test executados em subprocesso
production → prompt com ferramentas e memória, latência real
```

O coding executável deve ser considerado um benchmark local fidedigno:
executa código gerado pelo modelo num processo temporário com timeout.

## Suites não aplicáveis

Uma suite não pertinente não vale zero:

```json
{
  "vision": {
    "not_applicable": true,
    "reason": "model type does not support vision"
  }
}
```

`verified_capabilities` trata `not_applicable` como capability ausente,
não como pontuação zero. O run live marca assim os modelos `llm` para a
vision.

## Capability verificadas

A ficha distingue:

```text
capabilities           declaradas pelo catálogo
capabilities_verified  medidas pelo benchmark
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

O broker usa `capabilities_verified` quando presente. Um modelo que
declara `chat` mas recusa a conversa não é selecionado para um perfil
chat; pode no entanto ser selecionado para `coding` ou `tool_calling`.

Exemplo:

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

O broker usa a latência p95 da ficha para estimar o timeout da chamada
individual:

```text
timeout = clamp(p95 * safety * input_factor * output_factor, floor, ceiling)
```

Configuração:

```yaml
timeouts:
  adaptive: true
  floor_seconds: 30
  ceiling_seconds: 900
  safety_factor: 1.5
  cold_start_seconds: 120
  turn_ceiling_seconds: 1800
```

As ferramentas lentas configuram-se separadamente:

```yaml
tools:
  timeout: 120
  timeouts:
    document.ocr_pdf: 900
```

O turno não desce abaixo do timeout máximo das ferramentas configuradas.

## Respostas e reasoning

O LM Studio pode colocar o texto da resposta em:

```text
message.content
message.reasoning_content
message.reasoning
message.thinking
```

O Hagar usa `content` como resposta principal. Se estiver vazio, usa o
reasoning limpo como fallback e regista `llm.reasoning_fallback`. Se o
modelo tiver também tool call, o reasoning nunca substitui o texto: a
chamada à ferramenta continua prioritária.

Alguns modelos devolvem wrappers de chat template:

```text
<|im_start|>assistant ... <|im_end|>
<start_of_turn>model ... <end_of_turn>
<answer> ... </answer>
<thinking> ... </thinking>
```

O Hagar remove estes wrappers conhecidos, mas não HTML genérico como
`<b>...</b>`. As respostas limpas registam `llm.text_cleaned`.

## Vision

Apenas a pedido:

```text
/models test vision
```

Usa um pool sintético e fixo de imagens:

```text
cor dominante
contagem de objetos
relação espacial
OCR
gráfico de barras
campo UI
OCR com texto pequeno
gráfico com etiquetas
UI com vários campos
descrição de uma cena
```

Cada imagem tem um id e um SHA-256 no run. A pontuação é a média dos
casos. Um modelo sem capacidade vision não deve ser testado com este
comando.

## Histórico dos runs

Cada `/models test` guarda também um run separado:

```text
%LOCALAPPDATA%/Hagar/benchmark-runs/<run_id>.json
```

ou `HAGAR_BENCHMARK_RUNS`.

Comandos:

```text
/models runs
/models runs 5
```

A ficha contém o último resultado; o histórico conserva os runs para
comparações ao longo do tempo. As fichas não são apagadas.

Cada run contém também `suite_manifest`, com:

```text
versão da suite
casos de qualidade e prompt
imagens vision, id e SHA-256
```

Assim, um resultado continua interpretável mesmo quando as suites são
estendidas.

Ainda não mede:

- qualidade semântica das respostas;
- calibração das probabilidades;
- acurácia num dataset específico;
- TTFT em streaming;
- carga concorrente;
- consumo energético;
- áudio;
- preferência humana.

## Comandos

```text
/models list
/models show <provider> <model>
/models test
/models test vision
/models runs [n]
/models hardware
```

`/models test` testa o modelo LLM atual e guarda a ficha.
`/models test vision` executa a suite vision.

## Hardware

`detect_hardware()` é best-effort e multiplataforma:

- Windows: registry, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

Os campos não detetáveis permanecem `null`, não zero. A ausência de um dado não
significa que o hardware não exista.

## Uso futuro no broker

O broker usará a ficha para filtrar e ordenar:

```text
capabilities requeridas
hardware disponível
RAM/VRAM suficientes
latência p50/p95
custo
localidade
último teste
```

Uma ficha antiga não deve ser apagada: deve ser marcada como expirada ou
testada novamente.
