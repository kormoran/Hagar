# Modalità Hi-Fi

**Stato:** implementata nella 0.6.0
**Attivazione:** `hagar --hifi` oppure `hifi.enabled: true`
**Configurazione:** sezione `hifi`

## Cosa fa

Prima di rispondere, Hagar chiede al modello di interpretare la richiesta:

```text
La richiesta dell'utente è:
<<<
<richiesta>
>>>

Fornisci le tre interpretazioni più probabili di questa richiesta
e una stima numerica della probabilità di ciascuna.
```

La risposta deve essere JSON:

```json
{
  "interpretations": [
    {"text": "riassumi il documento", "probability": 0.7},
    {"text": "traduci il documento", "probability": 0.2},
    {"text": "altro", "probability": 0.1}
  ]
}
```

## Decisione

Hagar ordina le interpretazioni e calcola:

```text
margine = probabilità_prima - probabilità_seconda
```

Con il valore predefinito `margin: 0.20`:

```text
margine > 0.20   → risponde usando la prima interpretazione
margine <= 0.20  → chiede chiarimento
```

Il margine è in **punti percentuali**: `0.60` contro `0.35` produce
`0.25`, quindi Hagar risponde. `0.50` contro `0.40` produce `0.10`,
quindi chiede chiarimento.

## Risposta o chiarimento

Se il margine è sufficiente, il modello riceve:

```text
Interpretazione scelta: <prima>
Probabilità stimata: <probabilità>

Richiesta originale:
<richiesta>

Rispondi alla richiesta originale tenendo conto
dell'interpretazione scelta.
```

Se il margine è insufficiente, Hagar chiede al modello di formulare una
domanda:

```text
Intendi:
A) <prima interpretazione>
B) <seconda interpretazione>
Oppure un'altra interpretazione?
```

Il chiarimento viene restituito all'utente e registrato nella memoria
come normale turno; la richiesta successiva può quindi riprendere il
contesto.

## Configurazione

```yaml
hifi:
  enabled: true
  margin: 0.20
  interpretations: 3
```

`margin` deve essere tra 0 e 1. `interpretations` deve essere almeno 2.

## Audit

Eventi:

```text
hifi.enabled
hifi.interpretations
hifi.resolved
hifi.clarification
hifi.failed
```

`hifi.failed` significa che la classificazione non era valida: Hagar
prosegue con la risposta normale, senza bloccare il turno.

## Limiti

- una chiamata LLM aggiuntiva per ogni turno;
- possibili errori di calibrazione delle probabilità;
- immagini non supportate dal pre-pass: con immagini la modalità viene
  saltata;
- il classificatore non usa i tool;
- il modello può restituire JSON non valido: in quel caso il turno
  continua senza Hi-Fi.

## Esempio

```bash
hagar --hifi
```

```text
Utente: sistemami quel file

Hi-Fi: interpretazioni
  0.55  sposta il file
  0.40  copia il file
  0.05  altro

margine 0.15 ≤ 0.20
→ Hagar: Intendi spostare o copiare il file, oppure altro?
```
