# Broker LLM

**Stato:** in sviluppo — ModelRegistry, TaskProfile, Broker e
BrokerLLMClient implementati

## Scopo

Il broker sceglie un modello in base al task, alle capability richieste,
al contesto, alla privacy, al costo e ai dati misurati.

Non concede permessi e non modifica la policy: propone un modello,
l’host lo valida e costruisce il client.

## Componenti

```text
ModelRegistry      catalogo dichiarato + schede misurate
TaskProfile        requisiti del task
Broker             filtri, punteggio, scelta
BrokerLLMClient    integrazione con l’agente (dopo)
```

## ModelRegistry

File di catalogo:

```yaml
version: 1

models:
  - id: lmstudio/qwen2.5-coder-7b
    provider: lmstudio
    model: qwen2.5-coder-7b-instruct
    context_window: 32768
    capabilities:
      - chat
      - structured_json
      - tool_calling
      - native_tools
    locality: local
    quality: 0.75
    cost_per_1k_input: 0
    cost_per_1k_output: 0
    enabled: true
```

Campi:

```text
id                    univoco
provider              provider Hagar
model                 nome nel provider
context_window        token, opzionale
capabilities          chat, structured_json, tool_calling,
                      native_tools, vision, reasoning
locality              local, remote, unknown
quality               0.0–1.0, dichiarata
cost_per_1k_input     costo dichiarato
cost_per_1k_output    costo dichiarato
enabled               booleano
```

Il catalogo può essere una lista o una mappa con id come chiave.

## Merge con le schede

`ModelCardStore` contiene i dati **misurati**:

```text
latenza
JSON
tool calling
hardware al momento della prova
```

Il registry unisce catalogo e scheda per `provider/model`:

```text
catalogo dichiarato = fonte dei requisiti e dei costi
scheda misurata     = fonte delle prestazioni osservate
```

La scheda non sovrascrive i campi dichiarati.

## Validazione

Il loader rifiuta:

```text
versione diversa da 1
id/provider/model mancanti
id duplicati
provider/model duplicati
capability sconosciute
context_window non positivo
quality fuori da 0–1
locality sconosciuta
costi negativi
chiavi sconosciute
```

## API

```python
registry = ModelRegistry.load("models.yaml")
entry = registry.get("lmstudio/qwen2.5-coder-7b")

registry.enabled()
registry.with_capability("tool_calling")
registry.find("lmstudio", "qwen2.5-coder-7b-instruct")
```

Ogni voce espone la scheda misurata in `entry.card` e
`entry.measured_at`.

## TaskProfile

I profili descrivono il task, non il modello:

```yaml
version: 1

profiles:
  coding:
    description: Scrittura e revisione di codice con tool.
    required_capabilities:
      - chat
      - tool_calling
    min_context: 16000
    privacy: any
    max_latency_ms: 30000
    quality_floor: 0.70
    prefer: quality
```

Campi:

```text
name                     univoco
required_capabilities    chat, structured_json, tool_calling,
                         native_tools, vision, reasoning
min_context              token minimi
privacy                  any, local_only, remote_only
max_latency_ms           latenza massima
max_cost_per_1k_input    costo massimo input
max_cost_per_1k_output   costo massimo output
quality_floor            qualità minima dichiarata
prefer                   quality, latency, cost, context, balanced
enabled                  booleano
```

Un profilo non nomina provider o modelli. La scelta spetta al broker.

## Broker.select

Il broker applica prima i filtri hard, poi un punteggio.

Filtri:

```text
enabled
required_capabilities
min_context
privacy
max_latency_ms
max_cost_per_1k_input
max_cost_per_1k_output
quality_floor
```

Punteggio:

```text
quality        qualità dichiarata
latency        p50 misurata nella scheda
cost           costo massimo input/output dichiarato
context        contesto disponibile
```

Pesi per `prefer`:

```text
quality   0.70 qualità, 0.15 latenza, 0.075 costo, 0.075 contesto
latency   0.20 qualità, 0.60 latenza, 0.10 costo, 0.10 contesto
cost      0.20 qualità, 0.10 latenza, 0.60 costo, 0.10 contesto
context   0.20 qualità, 0.10 latenza, 0.10 costo, 0.60 contesto
balanced  0.35 qualità, 0.25 latenza, 0.20 costo, 0.20 contesto
```

Un dato mancante non vale zero: riceve un penalty e il motivo viene
registrato.

La selezione è deterministica:

```text
score desc
quality desc
model_id asc
```

## API

```python
broker = Broker(registry, profiles)
selection = broker.select("coding")
report = broker.explain("coding")
```

`selection` contiene:

```text
profile
model_id
provider
model
score
reasons
excluded
```

`excluded` contiene, per ogni modello scartato, il motivo.

## Comandi

Configurazione:

```yaml
broker:
  enabled: true
  catalog: models.yaml
  profiles: profiles.yaml
  default_profile: coding
```

I percorsi relativi sono risolti rispetto al file di configurazione.

```text
/models route
/models route coding
/models explain
/models explain private_chat
/models use quick_chat
```

`route` mostra il modello scelto e i motivi. `explain` mostra anche i
modelli esclusi e il motivo. `use` cambia il profilo attivo e il client
LLM; se il nuovo modello non è disponibile, il client precedente resta
attivo e l’errore viene restituito.

Se `broker.enabled` è false, o il catalogo non è valido, Hagar continua
ad avviarsi e il comando restituisce un errore esplicito. L’errore viene
registrato nell’audit come `broker.disabled`.

## BrokerLLMClient

Con `broker.enabled: true`, Hagar crea il client LLM tramite il broker:

```text
config.model = fallback dichiarato
broker.default_profile = profilo usato per la scelta
```

La scelta avviene alla costruzione e può essere cambiata in modo
esplicito con `/models use <profilo>`. Ogni cambio ricostruisce il
client e registra `broker.decision` con `action: switch`. Se il nuovo
client non si costruisce, resta attivo quello precedente.

```text
broker.decision   modello scelto, profilo, score
broker.fallback   nessun modello eleggibile, si usa config.model
broker.fallback_client  il client scelto non si costruisce
broker.switch_failed    cambio esplicito non riuscito
```

L’adapter delega:

```text
chat
generate
request_tool_call
native_step
native_tools
usage_sink
last_usage
last_reasoning
```

Il broker non concede capability, non modifica la policy e non cambia
sandbox. La scelta viene registrata nell’audit.

La selezione non avviene ancora per ogni turno: usa il profilo
`broker.default_profile`. La scelta dinamica per task arriverà dopo.

## Cosa manca

```text
selezione dinamica per task
benchmark di qualità per task
scelta esplicita del profilo per un turno
integrazione con i subagenti
```

## Regole future

```text
il broker non concede capability
il broker non sceglie per i subagenti senza regola esplicita
l’override umano vince
il modello configurato resta il fallback
ogni scelta produce audit broker.decision
un dato mancante produce un penalty, non un valore zero
```
