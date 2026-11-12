# Broker LLM

**Stato:** in sviluppo — ModelRegistry implementato

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

## Cosa manca

```text
TaskProfile
Broker.select
/models route
/models explain
BrokerLLMClient
benchmark di qualità per task
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
