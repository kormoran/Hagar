# Schede tecniche dei modelli

**Stato:** implementato
**Comandi:** `/models list`, `/models show`, `/models test`, `/models hardware`

## Scopo

Le schede alimentano il futuro broker LLM con dati misurati, non con
supposizioni. Una scheda per provider/modello viene salvata come JSON in:

```text
%LOCALAPPDATA%/Hagar/models/<provider>/<provider>-<model>.json
```

oppure `HAGAR_MODEL_CARDS`, o `$XDG_STATE_HOME/hagar/models`.

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

`last_tested_at` è sempre presente e viene aggiornato a ogni `/models test`.

## Cosa misura

- latenza chat: min, media, p50, p95, max;
- token di output al secondo;
- validità JSON;
- scelta valida nell'insieme delle label;
- tool calling con un tool di benchmark;
- qualità deterministica su task testuali;
- qualità vision su immagini sintetiche;
- hardware al momento della prova.

## Qualità per task

`/models test` esegue anche una suite qualità deterministica:

```text
extraction   estrazione di campi in JSON
instruction  rispetto di un'istruzione esatta
reasoning    calcolo numerico semplice
coding       lettura di un frammento Python
summary      riassunto con punti chiave
translation  traduzione IT→EN e EN→IT
```

Ogni caso viene eseguito due volte. Il punteggio è la media delle
risposte, da 0 a 1. Non è un benchmark semantico: è un test compatto e
ripetibile per dare al broker un segnale migliore della qualità
dichiarata.

La traduzione combina chrF con la conservazione di path, comandi e
termini richiesti. I termini obbligatori pesano molto più di chrF; una
traduzione tecnica sbagliata viene penalizzata esplicitamente. Il
riassunto misura la presenza dei punti chiave e il rispetto della
lunghezza.

La scheda contiene:

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

Il corpus è in `benchmarks/corpus/`:

```text
7 testi
2 reference di traduzione
10 immagini sintetiche
manifest.yaml con SHA-256
```

La suite testuale è `quality_v3`; la suite vision è `vision_v2`.

Un `quality_task` nel TaskProfile seleziona il task da usare; se manca,
il broker usa il nome del profilo. Se la scheda non ha qualità misurata,
usa la qualità dichiarata nel catalogo.

## Discovery del provider

Comando:

```text
/models discover lmstudio
/models discover ollama
```

Legge i metadati del runtime e li normalizza in `ProviderModelInfo`:

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

`completion` non viene mappato automaticamente su `chat`: un modello
può completare testo senza essere conversazionale. `chat` resta una
capability da verificare.

## Suite non applicabili

Una suite non pertinente non vale zero:

```json
{
  "vision": {
    "not_applicable": true,
    "reason": "model type does not support vision"
  }
}
```

`verified_capabilities` tratta `not_applicable` come capability assente,
non come punteggio zero. La run live marca così i modelli `llm` per la
vision.

## Capability verificate

La scheda distingue:

```text
capabilities           dichiarate dal catalogo
capabilities_verified  misurate dal benchmark
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

Il broker usa `capabilities_verified` quando presente. Un modello che
dichiara `chat` ma rifiuta la conversazione non viene selezionato per un
profilo chat; può comunque essere selezionato per `coding` o
`tool_calling`.

Esempio:

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

## Timeout adattivi

Il broker usa la latenza p95 della scheda per stimare il timeout della
singola chiamata:

```text
timeout = clamp(p95 * safety * input_factor * output_factor, floor, ceiling)
```

Configurazione:

```yaml
timeouts:
  adaptive: true
  floor_seconds: 30
  ceiling_seconds: 900
  safety_factor: 1.5
  cold_start_seconds: 120
  turn_ceiling_seconds: 1800
```

I tool lenti si configurano separatamente:

```yaml
tools:
  timeout: 120
  timeouts:
    document.ocr_pdf: 900
```

Il turno non scende sotto il timeout massimo dei tool configurati.

## Risposte e reasoning

LM Studio può mettere il testo della risposta in:

```text
message.content
message.reasoning_content
message.reasoning
message.thinking
```

Hagar usa `content` come risposta principale. Se è vuoto, usa il
reasoning ripulito come fallback e registra `llm.reasoning_fallback`.
Se il modello ha anche tool call, il reasoning non sostituisce mai il
testo: la chiamata al tool resta prioritaria.

Alcuni modelli restituiscono wrapper di chat template:

```text
<|im_start|>assistant ... <|im_end|>
<start_of_turn>model ... <end_of_turn>
<answer> ... </answer>
<thinking> ... </thinking>
```

Hagar rimuove questi wrapper noti, ma non HTML generico come
`<b>...</b>`. Le risposte ripulite registrano `llm.text_cleaned`.

## Vision

Solo su richiesta:

```text
/models test vision
```

Usa un pool sintetico e fisso di immagini:

```text
colore dominante
conteggio di oggetti
relazione spaziale
OCR
grafico a barre
campo UI
OCR con testo piccolo
grafico con etichette
UI a più campi
descrizione di una scena
```

Ogni immagine ha un id e uno SHA-256 nel run. Il punteggio è la media
dei casi. Un modello senza capacità vision non deve essere testato con
questo comando.

## Storico dei run

Ogni `/models test` salva anche un run separato:

```text
%LOCALAPPDATA%/Hagar/benchmark-runs/<run_id>.json
```

oppure `HAGAR_BENCHMARK_RUNS`.

Comandi:

```text
/models runs
/models runs 5
```

La scheda contiene l'ultimo risultato; lo storico conserva i run per i
confronti nel tempo. Le schede non vengono cancellate.

Ogni run contiene anche `suite_manifest`, con:

```text
versione della suite
casi qualità e prompt
immagini vision, id e SHA-256
```

In questo modo un risultato resta interpretabile anche quando le suite
vengono estese.

Non misura ancora:

- qualità semantica delle risposte;
- calibrazione delle probabilità;
- accuratezza su un dataset specifico;
- TTFT in streaming;
- carico concorrente;
- consumo energetico;
- audio;
- preferenza umana.

## Comandi

```text
/models list
/models show <provider> <model>
/models test
/models test vision
/models runs [n]
/models hardware
```

`/models test` prova il modello LLM corrente e salva la scheda.
`/models test vision` esegue la suite vision.

## Hardware

`detect_hardware()` è best-effort e multipiattaforma:

- Windows: registry, `GlobalMemoryStatusEx`, `wmic`, `nvidia-smi`;
- Linux: `/proc/cpuinfo`, `/proc/meminfo`, `/sys/class/drm`, `nvidia-smi`;
- macOS: `sysctl`, `system_profiler`.

I campi non rilevabili restano `null`, non zero. L'assenza di un dato non
significa che l'hardware non esista.

## Uso futuro nel broker

Il broker userà la scheda per filtrare e ordinare:

```text
capabilities richieste
hardware disponibile
RAM/VRAM sufficienti
latenza p50/p95
costo
località
ultima prova
```

Una scheda vecchia non va cancellata: va marcata come scaduta o
ritestata.
