# Dataset di calibrazione Hagar

File:

```text
calibration/hagar-calibration-300.jsonl
```

Composizione:

```text
60 query
120 positivi
180 negativi
300 brani totali
60 argomenti etichettati
```

Ogni riga contiene:

```json
{
  "query": "...",
  "positives": ["...", "..."],
  "negatives": ["...", "...", "..."],
  "topic": "..."
}
```

`topic` è un campo descrittivo; `memory.calibration.load_pairs` lo ignora.

## Lunghezze

Query:

```text
minima   27 caratteri
massima  85 caratteri
media    52 caratteri
```

Brani:

```text
minima   220 caratteri
massima 1009 caratteri
media    458 caratteri
```

Distribuzione:

```text
220–399 caratteri    189
400–899 caratteri     88
900–1009 caratteri    23
```

Le lunghezze sono volutamente miste. I brani brevi rappresentano skill e
decisioni sintetiche; quelli medi e lunghi rappresentano summary e
memorie più articolate.

## Avvertenza

Questo è un **dataset sintetico di partenza**, costruito per verificare
la pipeline e il formato. I brani sono testi Hagar-like, non memorie
reali dell'utente, e contengono frasi di contesto condivise tra più
documenti.

Non usare i valori prodotti da questo dataset come calibrazione
definitiva. Le soglie reali vanno ricalcolate con:

```text
memorie effettivamente presenti nel database
query scritte dall'utente
negativi presi da memorie dello stesso progetto
```

In particolare, i negativi sintetici possono risultare troppo simili ai
positivi e abbassare la precisione misurata.

## Esecuzione

```powershell
hagar calibrate `
  --config hagar.yaml `
  --dataset calibration/hagar-calibration-300.jsonl `
  --output embedding-thresholds.yaml
```

Il comando richiede:

```yaml
embedding:
  enabled: true
```

e un motore installato:

```powershell
pip install "hagar[embedding]"
```

## Validazione

```powershell
python -c "from memory.calibration import load_pairs; p=load_pairs('calibration/hagar-calibration-300.jsonl'); print(len(p), sum(len(x.positives) for x in p), sum(len(x.negatives) for x in p))"
```

Output atteso:

```text
60 120 180
```

## Come sostituirlo con dati reali

Per ogni query reale:

```text
1. scegli 1–2 memorie che rispondono davvero
2. scegli 3–5 memorie dello stesso progetto che non rispondono
3. mantieni le lunghezze simili a quelle delle memorie indicizzate
4. non citare il testo del positivo nella query
```

Meglio 50 query reali ben costruite che 300 brani sintetici.
