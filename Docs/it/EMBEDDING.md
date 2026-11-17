# Cambiare modello di embedding

Hagar non ha un comando dedicato al cambio del modello di embedding.
Questa è la procedura manuale per un utente che vuole farlo in modo
controllato.

> **Avvertenza.** Il provider integrato è specifico per E5. La procedura
> configura un modello **compatibile** con lo stesso layout ONNX e lo
> stesso tokenizer. Un modello con architettura, input o pooling diversi
> richiede un provider dedicato, non solo un cambio di YAML.

## Compatibilità richiesta

Il provider `builtin` presume:

```text
repo con onnx/model_O4.onnx
repo con onnx/tokenizer.json
output ONNX [batch, sequenza, dimensione]
pooling mean sui token
input input_ids e attention_mask
token_type_ids opzionale
prefissi E5 query: / passage:
revisione fissata da MODEL_REVISION
```

La revisione e i nomi dei file sono nel codice, non nella
configurazione. Se il nuovo modello non li rispetta, il download o il
caricamento falliscono.

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
output token-level, non già pooled
dimensione output = embedding.dimensions
```

Se l’output è `[batch, dimensione]` senza asse sequenza, il pooling
attuale non è compatibile.

## 5. Configurare

```yaml
embedding:
  enabled: true
  provider: builtin
  model: "modello-compatibile"
  dimensions: 384
  checksums:
    model.onnx: "<sha256 del file>"
    tokenizer.json: "<sha256 del file>"
  cache_dir: "C:\\Users\\<utente>\\AppData\\Local\\Hagar\\embedding-models"
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

## 7. Ricostruire i vettori

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

## 8. Ricalibrare

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

## 9. Verifica finale

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
modello con pooling diverso
modello con output già pooled
modello con input names diversi
modello senza tokenizer.json
modello con file ONNX dal nome diverso
revisione remota diversa
```

Per questi casi serve modificare `OnnxE5Provider` o aggiungere un nuovo
provider. La calibrazione è già indipendente dal modello, ma il
caricamento no.
