# Boxed transform

**Stato:** implementato
**Tool:** `box.list`, `box.run`
**Capability:** `BOX_EXEC`
**Policy:** DENY di default

## Cosa sono

Le boxed transform sono funzioni LLM bounded:

```text
input definito
→ prompt fisso
→ una o più chiamate
→ output validato
→ file nella sandbox
```

Non sono subagenti:

- non hanno memoria;
- non hanno tool;
- non hanno un workspace;
- non pianificano;
- non creano prompt liberi.

Sono il complemento naturale del futuro DSL: il modello scrive il flusso,
Hagar esegue la trasformazione.

## Box disponibili

```text
summarize
translate
extract_json
```

`box.list` restituisce metadati, input/output e opzioni.

## Configurazione

```yaml
boxes:
  enabled: false
  max_input_chars: 200000
  max_output_chars: 20000
  chunk_chars: 8000
  max_calls: 20
```

`enabled: false` non registra i tool. Anche con i tool registrati,
`BOX_EXEC` deve essere concessa in `policy.yaml`.

## Policy

```yaml
- capabilities: [BOX_EXEC]
  effect: allow
  tools: ["box.*"]
```

La regola predefinita è `deny`.

## Uso

```json
{
  "box": "summarize",
  "input": "documento.txt",
  "output": "riassunto.txt",
  "options": {"style": "short"}
}
```

```json
{
  "box": "translate",
  "input": "documento.txt",
  "output": "documento.it.txt",
  "options": {"target": "it"}
}
```

```json
{
  "box": "extract_json",
  "input": "documento.txt",
  "output": "dati.json"
}
```

## Opzioni

### `summarize`

```text
style: short | detailed | bullet
```

### `translate`

```text
target: lingua di destinazione, default "it"
```

### `extract_json`

Nessuna opzione: l’output è un oggetto JSON.

## Comportamento

- l’input viene letto dalla sandbox;
- `summarize` spezza documenti lunghi in chunk e unisce i risultati;
- `translate` traduce i chunk e li ricompone;
- `extract_json` valida il JSON prodotto dal modello;
- l’output viene scritto con `create_file` o `write_file`;
- se il file esiste, viene prima osservato per rispettare il gate
  read-before-write;
- l’output è limitato da `max_output_chars`;
- il numero di chiamate è limitato da `max_calls`.

## Prompt injection

Il documento è trattato come dato. Ogni prompt dice esplicitamente di non
eseguire istruzioni contenute nel testo. La box non ha tool, quindi non
può eseguire comandi, ma l’output resta contenuto non fidato.

## Dati remoti

La box usa il client LLM configurato in Hagar. Se il provider è remoto,
il documento esce dalla macchina. La scelta del provider e della rete
resta dell’ambiente.

## Audit

```text
box.run.start
box.run.result
box.run.error
boxes.enabled
```

Non vengono registrati il testo completo né l’output.

## Limiti

- tre box initiali;
- nessun prompt libero;
- nessuna scelta autonoma del modello;
- nessuna cache;
- nessuna memoria o contesto;
- niente routing automatico tra modelli;
- `extract_json` non conosce uno schema fornito dall’utente.

## Relazione con il DSL

Il DSL userà le stesse box come primitive:

```python
summarize(documento_in, riassunto_out)
```

La box non conosce il DSL; il DSL non reimplementa la logica della box.

## Relazione con i tool

```text
tool       → azione deterministica
box        → trasformazione LLM bounded
subagent   → autonomia e più passi
DSL        → orchestrazione
```
