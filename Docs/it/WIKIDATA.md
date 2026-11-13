# Plugin Wikidata

**Ambito:** plugin tool esterno per interrogare Wikidata e leggere
Wikipedia dal modello dentro Hagar.

Il plugin vive in `plugins/wikidata` e usa il contratto descritto in
[PLUGINS.md](PLUGINS.md). È un pacchetto separato: non viene caricato
finché non lo si installa, quindi non cambia il set dei tool built-in.

## 1. Cosa offre

| Tool | A cosa serve |
|---|---|
| `wikidata.search` | Cerca item o proprietà Wikidata per etichetta e restituisce ID, etichetta, descrizione e alias. |
| `wikidata.entity` | Scarica una o più entità per ID con etichette, descrizioni, alias, link Wikipedia e un riassunto compatto delle claim. |
| `wikidata.article` | Legge l'estratto in testo semplice di un articolo Wikipedia, per ID entità o per titolo. |
| `wikidata.query` | Esegue una query SPARQL `SELECT` in sola lettura su Wikidata Query Service. |

Tutti i tool dichiarano la capability `NETWORK` e l'origine
`plugin.wikidata`. Non leggono il filesystem, non scrivono e non
concedono permessi.

### 1.1 `wikidata.search`

Parametri:

- `query` (string, obbligatorio): testo da cercare;
- `language` (string, opzionale): lingua di etichette e ricerca,
  default `it`;
- `limit` (integer, opzionale): da 1 a 50, default 10;
- `entity_type` (string, opzionale): `item` o `property`, default
  `item`.

Restituisce `results` con `id`, `label`, `description`, `aliases`,
`url` e `concept_uri`. `has_more` indica che Wikidata ha altri
risultati oltre il limite richiesto.

### 1.2 `wikidata.entity`

Parametri:

- `ids` (string, obbligatorio): uno o più ID separati da virgola,
  spazio o `|`, al massimo 10;
- `language` (string, opzionale): default `it`;
- `include_claims` (boolean, opzionale): default `true`;
- `max_claims` (integer, opzionale): da 1 a 300, default 50;
- `resolve_labels` (boolean, opzionale): risolve le etichette delle
  proprietà e delle entità referenziate, default `true`.

Le claim sono ordinate per rilevanza: prima le proprietà più utili
(istanza di, sottoclasse di, paese, coordinate, date, luogo di nascita
o morte, occupazione, autori, ecc.), poi le altre claim non-identificativo,
infine gli identificativi esterni. Ogni claim riporta `count`,
`values` e `truncated`; i flag `claims_truncated` e
`claims_omitted_properties` indicano cosa è stato lasciato fuori.

Le etichette Wikidata nella lingua speciale `mul` vengono usate come
fallback, perché molte entità hanno ormai lì l'etichetta principale.

### 1.3 `wikidata.article`

Parametri:

- `entity_id` (string, opzionale): ID Wikidata, es. `Q42`;
- `title` (string, opzionale): titolo dell'articolo Wikipedia;
- `language` (string, opzionale): default `it`;
- `intro_only` (boolean, opzionale): solo introduzione, default
  `false`;
- `max_chars` (integer, opzionale): da 200 a 20000, default 4000.

Bisogna indicare **esattamente uno** tra `entity_id` e `title`. Con
`entity_id` il plugin risolve il sitelink Wikipedia nella lingua
richiesta; se manca, l'errore elenca le lingue disponibili. Il
risultato contiene `extract`, `url`, `thumbnail`, `total_chars`,
`returned_chars` e `truncated`.

### 1.4 `wikidata.query`

Parametri:

- `query` (string, obbligatorio): una query SPARQL `SELECT`, con
  eventuali righe `PREFIX` o `BASE`;
- `max_results` (integer, opzionale): da 1 a 500, default 100.

Restituisce `vars`, `rows`, `row_count`, `total_rows` e `truncated`.
Sono ammesse solo query di lettura. Il plugin rifiuta query che non
iniziano con `SELECT`, la federazione `SERVICE` (tranne
`wikibase:label`) e le clausole `FROM`. Il Query Service può
rispondere `504` nei momenti di carico: l'errore viene restituito al
modello e la query può essere ritentata più tardi.

## 2. Installazione

Prerequisito: Hagar installato nell'ambiente, ad esempio con
`python -m pip install -e .` dalla radice del repository.

```powershell
python -m pip install -e plugins/wikidata
```

L'installazione registra l'entry point:

```toml
[project.entry-points."hagar.tools"]
wikidata = "hagar_wikidata:PLUGIN"
```

Verifica della scoperta:

```powershell
python -c "from importlib.metadata import entry_points; print([e.name for e in entry_points(group='hagar.tools')])"
```

L'output deve contenere `wikidata`. Per rimuovere il plugin:

```powershell
python -m pip uninstall hagar-wikidata
```

Il pacchetto del plugin dichiara solo `requests`; usa i moduli `core`
di Hagar già presenti nell'ambiente. Non va installato in un ambiente
dove Hagar non c'è.

## 3. Abilitazione in Hagar

Il plugin dichiara `NETWORK`, ma la decisione finale resta all'host.
Servono due cose nella configurazione.

### 3.1 Tetto di sistema

In `hagar.yaml`:

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: true
```

Senza `network: true` il tetto di sistema nega la capability e il
plugin non può uscire dalla macchina, anche con una regola di policy
permissiva.

### 3.2 Regola di policy

In `policy.yaml`, sotto il soggetto usato da Hagar:

```yaml
      - capabilities: [NETWORK]
        effect: ask
        tools: ["wikidata.*"]
```

`ask` chiede conferma in chat per ogni chiamata; `allow` la rende
automatica. Il default sicuro resta `deny`. La regola può essere più
stretta, ad esempio solo per la ricerca:

```yaml
      - capabilities: [NETWORK]
        effect: allow
        tools: ["wikidata.search", "wikidata.entity"]
```

La regola inclusa nel `policy.yaml` del repository usa `ask` per
`wikidata.*`.

## 4. Configurazione

Il plugin legge l'ambiente, senza chiavi API:

| Variabile | Default | Significato |
|---|---|---|
| `HAGAR_WIKIDATA_LANGUAGE` | `it` | Lingua predefinita di ricerca, etichette e articoli. |
| `HAGAR_WIKIDATA_TIMEOUT` | `15` | Timeout HTTP in secondi per Wikidata e Wikipedia (2-120). |
| `HAGAR_WIKIDATA_QUERY_TIMEOUT` | `60` | Timeout HTTP in secondi per SPARQL (2-180). |
| `HAGAR_WIKIDATA_USER_AGENT` | `Hagar-Wikidata/1.0 (...)` | User-Agent inviato a Wikimedia. |

Wikimedia richiede uno User-Agent descrittivo. Se si distribuisce il
plugin, è buona norma impostare un valore che identifichi davvero
l'istanza.

## 5. Esempi

Ricerca di un argomento:

```json
{
  "query": "Guida galattica per gli autostoppisti",
  "language": "it",
  "limit": 5
}
```

Entità con i fatti principali:

```json
{
  "ids": "Q42",
  "language": "it",
  "max_claims": 40,
  "resolve_labels": true
}
```

Introduzione dell'articolo:

```json
{
  "entity_id": "Q42",
  "language": "it",
  "intro_only": true,
  "max_chars": 2000
}
```

Query SPARQL:

```json
{
  "query": "PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> SELECT ?item ?itemLabel WHERE { ?item wdt:P31 wd:Q5 . SERVICE wikibase:label { bd:serviceParam wikibase:language \"it\". } } LIMIT 20",
  "max_results": 20
}
```

## 6. Sicurezza e limiti

- Il modello non può fornire URL arbitrari: il client accetta solo
  `https://www.wikidata.org`, `https://query.wikidata.org` e
  `https://<lingua>.wikipedia.org`.
- Le richieste sono in sola lettura, senza login, cookie o chiavi.
- SPARQL accetta solo `SELECT`; `SERVICE` è bloccato tranne
  `wikibase:label`; `FROM` è bloccato. Questo evita federazione verso
  host arbitrari.
- Le risposte sono limitate a 8 MB e i timeout sono configurabili.
  Testi e claim sono troncati con flag espliciti.
- Gli errori di rete o delle API vengono restituiti come JSON con
  `success: false` e `error`, senza interrompere il turno.
- I tool restano soggetti a policy, conferma umana, audit e repeat
  limit dell'host. Il plugin non può concedere permessi.
- Wikidata e Wikipedia hanno rate limit: un uso intenso può produrre
  `429`. Il plugin non aggira il limite e non fa retry automatici.

## 7. Test

I test sono offline e usano risposte HTTP simulate:

```powershell
python -m pytest tests/test_wikidata_plugin.py
```

Coprono registrazione, scoperta da entry point, ricerca, entità,
claim, articoli, SPARQL, errori HTTP e limiti di dimensione.

## 8. File

```text
plugins/wikidata/
  pyproject.toml          entry point hagar.tools
  README.md               guida rapida del pacchetto
  hagar_wikidata/
    __init__.py           PLUGIN e register()
    client.py             client Wikidata, Wikipedia e SPARQL
    tools.py              ToolDefinition e handler
tests/test_wikidata_plugin.py
```
