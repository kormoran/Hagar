# Cambiare modello di embedding

Hagar non ha un comando dedicato al cambio del modello di embedding.
Questa è la procedura manuale per un utente che vuole farlo in modo
controllato.

> **Avvertenza.** Il caricamento è generico per modelli ONNX con
> `tokenizer.json`, ma non per qualsiasi architettura. Il modello deve
> rispettare uno dei formati descritti sotto. In caso contrario serve un
> provider dedicato.

## Compatibilità richiesta

Il provider `onnx` supporta:

```text
file locali model.onnx e tokenizer.json
qualsiasi nome file remoto, mappato in embedding.files
revisione remota configurabile
output token-level [batch, sequenza, dimensione]
output già pooled [batch, dimensione]
pooling mean o cls per l'output token-level
input input_ids e attention_mask
token_type_ids opzionale
prefissi configurabili
```

`preset: e5-small` mantiene i valori attuali: revisione, file, checksum,
prefissi e pooling E5.

Non sono supportati modelli con nomi di input diversi, pooling diverso
da mean/cls o tokenizer non in formato `tokenizer.json`.

## 1. Fermare Hagar

Chiudere la chat e il server web. Il motore viene costruito all’avvio e
non cambia durante la sessione.

## 2. Backup

Fermare Hagar prima di copiare il database SQLite. Con il backend
predefinito, salvare:

```text
memory.db
memory.db-wal
memory.db-shm
hagar.yaml
```

In alternativa, con Hagar fermo:

```sql
VACUUM INTO 'memory-backup.db';
```

Non copiare solo `memory.db` mentre il processo è attivo: il database
usa WAL.

## 3. Ottenere il modello

Scaricare i due file dalla revisione scelta e calcolare gli SHA-256.

Windows:

```powershell
Get-FileHash -Algorithm SHA256 .\model_O4.onnx
Get-FileHash -Algorithm SHA256 .\tokenizer.json
```

Linux/macOS:

```bash
sha256sum model_O4.onnx tokenizer.json
```

I digest devono essere di 64 caratteri esadecimali.

## 4. Verificare la compatibilità ONNX

```powershell
python -c "import onnxruntime as ort; s=ort.InferenceSession('model_O4.onnx'); print([i.name for i in s.get_inputs()]); print([o.shape for o in s.get_outputs()])"
```

Controllare:

```text
input_ids presente
attention_mask presente
output token-level oppure pooled
dimensione output = embedding.dimensions
```

Se l’output è `[batch, dimensione]`, configurare `output: pooled`.
Se è `[batch, sequenza, dimensione]`, usare `output: token` e scegliere
`pooling: mean` o `pooling: cls`.

## 5. Configurare

```yaml
embedding:
  enabled: true
  provider: onnx
  model: "modello-compatibile"
  revision: "<revisione Hugging Face>"
  dimensions: 384
  files:
    model.onnx: "onnx/model.onnx"
    tokenizer.json: "onnx/tokenizer.json"
  checksums:
    model.onnx: "<sha256 del file>"
    tokenizer.json: "<sha256 del file>"
  pooling: mean
  output: token
  query_prefix: ""
  document_prefix: ""
  cache_dir: "C:\\Users\\<utente>\\AppData\\Local\\Hagar\\embedding-models"
```

Per il preset E5-small basta:

```yaml
embedding:
  enabled: true
  provider: onnx
  preset: e5-small
```

`cache_dir` è facoltativo. La cache viene separata per nome modello.

## 6. Avviare e controllare il caricamento

```powershell
hagar --config hagar.yaml
```

All’avvio Hagar verifica:

```text
presenza dei file
SHA-256
dimensioni dei vettori
caricamento ONNX
```

Se il checksum non corrisponde, il file viene rimosso e il motore
embedding viene disattivato. Hagar continua a funzionare senza recall
vettoriale.

## 7. Cambio rilevato automaticamente

All’avvio Hagar confronta il modello corrente con:

```text
meta.embedding_model
modelli presenti in memory_embeddings
```

Se il modello è cambiato, chiede:

```text
Il modello di embedding è cambiato.
Posso scartare i vettori vecchi e ricrearli?
```

Se l’utente accetta:

```text
elimina i vettori del modello precedente
ricalcola skill, summary, decisioni e progetti
salva il nuovo modello in meta.embedding_model
```

Se l’utente rifiuta:

```text
embedding disattivato
vector search disattivata
FTS e memoria normale continuano a funzionare
```

Il consenso viene chiesto prima che Hagar sia pronto. Nella GUI web il
prompt usa il terminale da cui è stato avviato `hagar web`; in un
processo senza terminale il silenzio vale come rifiuto e la sessione
parte senza embedding.

## 8. Ricostruire i vettori

Prima senza pruning, per non cancellare i vecchi vettori prima di aver
verificato il nuovo modello:

```text
/memory embeddings reindex
```

Controllare:

```text
/memory embeddings status
/memory embeddings search "una domanda di prova"
```

Solo dopo la verifica:

```text
/memory embeddings reindex --prune
```

`--prune` rimuove i vettori dei modelli precedenti e quelli delle
entità scomparse.

## 9. Ricalibrare

```powershell
hagar calibrate `
  --config hagar.yaml `
  --dataset calibration.jsonl `
  --output embedding-thresholds.yaml
```

Copiare i valori di:

```text
memory.vector_min_score
memory.vector_strong_score
memory.vector_margin
```

in `hagar.yaml`. Le soglie del vecchio modello non sono valide.

## 10. Verifica finale

```text
/memory embeddings status
/memory embeddings search "<domanda reale>"
```

Controllare anche una domanda con un termine esatto: deve passare dal
canale FTS.

## Rollback

Se il nuovo modello non funziona:

```text
1. fermare Hagar
2. ripristinare hagar.yaml
3. ripristinare memory.db e i file WAL
4. avviare Hagar
5. eseguire /memory embeddings reindex
```

Se il database è stato ricostruito con il nuovo modello, il ripristino
del backup è la via più sicura per tornare ai vettori precedenti.

## Cosa non è supportato

```text
modello senza tokenizer.json
modello con input names diversi
modello con pooling diverso da mean/cls
modello con output non token-level o pooled
modello che richiede codice Python custom
```

Per questi casi serve modificare `OnnxProvider` o aggiungere un nuovo
provider. La calibrazione è già indipendente dal modello, ma il
caricamento no.

## Famiglia E5

`preset: e5-small` è incluso e verificato. E5-base ed E5-large possono
essere configurati come modelli custom con revisione, file e checksum
espliciti; non sono preset preconfezionati in questa versione.
