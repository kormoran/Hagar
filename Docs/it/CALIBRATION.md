# Calibrazione delle soglie di recall

La calibrazione è una funzione ufficiale di Hagar:

```text
hagar calibrate
```

Serve a scegliere `memory.vector_min_score`, `memory.vector_strong_score`
e `memory.vector_margin` per il modello di embedding configurato. Va
rieseguita quando cambia il modello, la dimensione dei vettori o la
distribuzione delle memorie.

## Dataset

Formato JSONL, una riga per query:

```json
{"query": "Come vengono generati i summary?", "positives": ["I summary vengono generati in background da un job durevole."], "negatives": ["Il broker sceglie il modello in base al task."]}
{"query": "Dove sono salvate le memorie?", "positives": ["Le memorie sono nel database SQLite locale."], "negatives": ["Le note Obsidian sono nel vault Markdown."]}
```

`positive`/`positives` e `negative`/`negatives` accettano una stringa o
una lista. Ogni query deve avere almeno un positivo e un negativo.

È accettato anche un array JSON con la stessa struttura.

## Esecuzione

```powershell
hagar calibrate `
  --config hagar.yaml `
  --dataset calibration.jsonl `
  --output embedding-thresholds.yaml
```

Senza `--output` il risultato viene stampato come YAML.

Il comando richiede:

```yaml
embedding:
  enabled: true
```

e un motore installato:

```powershell
pip install "hagar[embedding]"
```

## Cosa calcola

```text
vector_min_score
    soglia che massimizza F1 sul dataset

vector_strong_score
    soglia più alta con precisione >= --min-precision
    (default 0.90)

vector_margin
    25° percentile del distacco tra miglior positivo
    e miglior negativo, limitato tra 0.02 e 0.20
```

Il report mostra anche:

```text
queries
positives
negatives
precision
recall
f1
```

Con meno di 20 query il report segnala che il campione è piccolo.

## Output

```yaml
memory:
  vector_min_score: 0.820
  vector_strong_score: 0.840
  vector_margin: 0.040
```

Copiare i tre valori in `hagar.yaml`, oppure usare il file come base per
la sezione `memory` della configurazione.

## Cambiare modello

Modificare la configurazione:

```yaml
embedding:
  model: "altro-modello"
  dimensions: 768
  cache_dir: "..."

memory:
  vector_min_score: 0.0
  vector_strong_score: 0.0
  vector_margin: 0.0
```

Poi eseguire di nuovo:

```powershell
hagar calibrate `
  --config hagar.yaml `
  --dataset calibration.jsonl `
  --output embedding-thresholds.yaml
```

Le soglie non sono trasferibili tra modelli diversi: vanno ricalibrate.

La procedura completa per cambiare modello, inclusi backup, checksum e
rollback, è in `EMBEDDING.md`.

## Checksum per un modello diverso

Il provider built-in conosce i checksum di `multilingual-e5-small`. Se si
usa un altro modello ONNX con gli stessi nomi file, dichiarare i digest:

```yaml
embedding:
  model: "altro-modello"
  dimensions: 768
  checksums:
    model.onnx: "<sha256>"
    tokenizer.json: "<sha256>"
```

Se un digest manca o non corrisponde, il motore embedding non viene
caricato. Questa è una scelta intenzionale: meglio nessun recall
vettoriale che vettori calcolati da un modello diverso.

## Verifica del modello

Prima del caricamento Hagar verifica SHA-256 di:

```text
model.onnx
tokenizer.json
```

Se il checksum non corrisponde, il motore embedding viene disattivato e
Hagar continua senza recall vettoriale. Il file corrotto viene rimosso e
riscaricato al tentativo successivo.
