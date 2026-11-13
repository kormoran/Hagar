# hagar-wikidata

Plugin tool esterno per Hagar: permette al modello di cercare su
Wikidata, leggere entità e claim, recuperare estratti da Wikipedia ed
eseguire query SPARQL in sola lettura.

Documentazione completa: [Docs/it/WIKIDATA.md](../../Docs/it/WIKIDATA.md).

## Tool

| Tool | Descrizione |
|---|---|
| `wikidata.search` | Cerca item o proprietà per etichetta. |
| `wikidata.entity` | Legge etichette, descrizioni, sitelink e claim di una o più entità. |
| `wikidata.article` | Legge l'estratto di un articolo Wikipedia per ID entità o titolo. |
| `wikidata.query` | Esegue una query SPARQL `SELECT` in sola lettura. |

Tutti dichiarano la capability `NETWORK`. Il plugin non concede
permessi: policy, conferma, sandbox e audit restano nell'host.

## Installazione

Dalla radice del repository Hagar:

```powershell
python -m pip install -e plugins/wikidata
```

Il pacchetto registra l'entry point `hagar.tools`:

```toml
[project.entry-points."hagar.tools"]
wikidata = "hagar_wikidata:PLUGIN"
```

Per rimuoverlo:

```powershell
python -m pip uninstall hagar-wikidata
```

## Abilitazione

In `hagar.yaml` il tetto di sistema deve concedere la rete:

```yaml
permissions:
  network: true
```

In `policy.yaml` serve una regola per `wikidata.*`:

```yaml
      - capabilities: [NETWORK]
        effect: ask
        tools: ["wikidata.*"]
```

`ask` richiede conferma per ogni chiamata; `allow` la rende
automatica. Senza regola vale il default `deny`.

## Esempio

```json
{
  "ids": "Q42",
  "language": "it",
  "max_claims": 40
}
```

Risposta (ridotta):

```json
{
  "success": true,
  "entities": [
    {
      "id": "Q42",
      "label": "Douglas Adams",
      "description": "scrittore di fantascienza ed umorista britannico (1952–2001)",
      "wikipedia": {
        "it": {
          "title": "Douglas Adams",
          "url": "https://it.wikipedia.org/wiki/Douglas_Adams"
        }
      },
      "claims": [
        {
          "property": "P31",
          "property_label": "istanza di",
          "values": [{"id": "Q5", "label": "umano"}]
        }
      ]
    }
  ]
}
```

## Configurazione

| Variabile | Default | Uso |
|---|---|---|
| `HAGAR_WIKIDATA_LANGUAGE` | `it` | Lingua predefinita. |
| `HAGAR_WIKIDATA_TIMEOUT` | `15` | Timeout HTTP per Wikidata/Wikipedia. |
| `HAGAR_WIKIDATA_QUERY_TIMEOUT` | `60` | Timeout HTTP per SPARQL. |
| `HAGAR_WIKIDATA_USER_AGENT` | `Hagar-Wikidata/1.0 (...)` | User-Agent Wikimedia. |

## Sicurezza

- Solo endpoint Wikimedia in HTTPS; nessun URL arbitrario dal modello.
- Solo lettura: nessun login, cookie o chiave API.
- SPARQL solo `SELECT`; `SERVICE` bloccato tranne `wikibase:label`;
  `FROM` bloccato.
- Risposte limitate a 8 MB, timeout espliciti e output troncato con
  flag.
- Errori restituiti come JSON `{"success": false, "error": "..."}`.

## Test

```powershell
python -m pytest tests/test_wikidata_plugin.py
```

I test sono offline e simulano le risposte HTTP.

## Licenza

MIT, come Hagar.
