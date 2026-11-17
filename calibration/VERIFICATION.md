# Verifica della pipeline di calibrazione

Data: 2026-11-17

## Ambiente

```text
Python 3.13.18
modello intfloat/multilingual-e5-small
revisione 614241f622f53c4eeff9890bdc4f31cfecc418b3
dimensione 384
checksum SHA-256 verificato
```

## Dataset

```text
query       60
positivi   120
negativi   180
brani      300
```

Lunghezze:

```text
query        27–85 caratteri
brani       220–1009 caratteri
media        458 caratteri
token        57–234
brani > 512 token    0
```

## Comando eseguito

```powershell
hagar calibrate `
  --config .tmp/calibration-config.yaml `
  --dataset calibration/hagar-calibration-300.jsonl `
  --output .tmp/calibration-result-300.yaml
```

Il comando è terminato con successo e ha scritto il file YAML.

## Risultato

```yaml
memory:
  vector_min_score: 0.841
  vector_strong_score: 0.841
  vector_margin: 0.020
```

Metriche:

```text
precision  0.4921
recall     0.7833
f1         0.6045
```

## Controlli superati

```text
lettura JSONL
60 query
120 positivi
180 negativi
300 testi unici
nessun testo vuoto
nessun testo oltre 512 token
embedding reali con E5
calibrazione completata
output YAML valido
soglie accettate da ConfigLoader
```

## Esito

La pipeline funziona tecnicamente:

```text
dataset → embedding → soglie → YAML → configurazione
```

Il dataset sintetico però **non è adatto alla calibrazione definitiva**.

La precisione è 0.4921: a quella soglia molti negativi vengono
considerati pertinenti. Le cause principali sono:

```text
contesto sintetico condiviso tra i brani
negativi difficili ma in parte semanticamente vicini
assenza di memorie reali del progetto
assenza di un insieme di validazione separato
```

## Decisione

Non applicare:

```text
vector_min_score: 0.841
vector_strong_score: 0.841
vector_margin: 0.020
```

come valori di produzione. Restano i default:

```text
vector_min_score: 0.82
vector_strong_score: 0.84
vector_margin: 0.04
```

## Prossimo passo

Costruire un dataset reale:

```text
query scritte dall'utente
positivi presi dalle memorie effettive
negativi presi dallo stesso progetto
lunghezze uguali a quelle indicizzate
20–30% delle query tenute fuori per la validazione
```

La pipeline è pronta; manca il dataset reale.
