# Pannello di controllo e Sandbox manager

**Ambito:** due pagine amministrative della GUI web locale di Hagar.
Sono un’interfaccia per l’utente, non nuovi tool per il modello.

## 1. Accesso

```powershell
hagar --config hagar.yaml web
```

Nella pagina principale, accanto alla chat e nella sidebar, ci sono i
pulsanti **Pannello** e **Sandbox**. Entrambe le pagine hanno
**Torna alla chat** in alto.

Il server resta locale (`127.0.0.1` per default). Le pagine ricevono il
token di sessione come la GUI principale; le API amministrative lo
richiedono nell’header `X-Hagar-Token`.

## 2. Pannello di controllo

### 2.1 Tool

Elenca i tool built-in, locali e plugin con categoria, origine e
capability. Clic su una riga alterna **allow** / **deny**.

- `deny` disabilita il tool nel registry: il modello non lo vede e non
  può eseguirlo.
- `allow` lo riabilita, ma **la policy dell’host resta attiva**: un
  tool può essere abilitato qui e comunque negato da `policy.yaml` o
  dal tetto di sistema.
- Il toggle è runtime e non modifica `policy.yaml`.

### 2.2 Modello IA

Mostra i provider disponibili e i modelli noti per ciascuno:

- modelli statici per i provider supportati;
- modelli presenti nelle schede `ModelCardStore`;
- per Ollama e LM Studio, i modelli realmente esposti dal server
  locale, con timeout breve.

Il combo **Filtra provider** restringe l’elenco a un solo provider.
Seleziona provider e modello, poi premi **Cambia modello**.

Se il broker LLM è attivo (`broker.enabled: true`), il pannello mostra
profilo e modello scelto dal broker, disabilita il cambio diretto e
rimanda al comando `/models use <profilo>`. Il broker resta l’unico
responsabile della scelta; il pannello non lo bypassa. La
procedura:

1. valida provider e nome;
2. crea il nuovo client con la configurazione del provider;
3. sostituisce il client dell’agente, quello dell’harness e quello
   dell’eventuale resolver Hi-Fi;
4. mantiene il collegamento al ledger di usage;
5. registra `admin.model_changed` nell’audit.

La modifica è **runtime**: non scrive `hagar.yaml`. Se il provider
richiede una chiave API mancante, il cambio fallisce e il modello
precedente resta attivo.

### 2.3 Configurazione

Campi modificabili a runtime:

| Gruppo | Valori |
|---|---|
| Hi-Fi | attivo, margine, numero interpretazioni |
| Tool | timeout, limite ripetizioni |
| Modello | timeout, max token, native tool calling |
| Filesystem | max byte per scrittura, spazio minimo, byte per sessione, soglia conferma |
| Memoria | turni di contesto, skill di contesto, max caratteri contesto |

**Applica** valida tutti i valori prima di applicarli; un valore non
valido non cambia lo stato. I valori sono applicati agli oggetti vivi
dell’harness, non solo alla dataclass.

**Ritorna a configurazione hagar.yaml**:

- ricarica il file di configurazione;
- ripristina i valori modificabili;
- ricrea il client se provider, modello, host o variabile della chiave
  sono cambiati; con broker attivo ricrea il `BrokerLLMClient`;
- riabilita tutti i tool;
- cancella gli override RWX del sandbox manager.

Non ricarica policy, permessi di sistema, audit, server MCP o il
catalogo/profili del broker: sono scelte che richiedono un riavvio.

Le modifiche amministrative sono rifiutate con `409` mentre un turno è
in corso. Le letture restano disponibili.

## 3. Sandbox manager

Mostra un albero dei file e delle directory nella sandbox. I nodi sono
caricati in modo lazy: aprendo una directory vengono letti i figli.

Per ogni elemento ci sono tre checkbox:

| Checkbox | Significato |
|---|---|
| **R** | lettura, elenco, stat |
| **W** | scrittura, creazione, rename e delete |
| **X** | ingresso/esecuzione nella directory |

I permessi sono override per percorso, applicati sopra i permessi della
radice. Per una directory valgono anche per i discendenti, finché un
discendente non ha un override più specifico. Sono runtime e non
toccano il filesystem del sistema operativo.

La riga in basso mostra il **path reale** dell’elemento selezionato.
È un’informazione per l’utente locale: il modello continua a vedere
solo path virtuali e non riceve questa riga.

**Crea directory** crea una sottodirectory nella directory selezionata.
Non esiste alcun pulsante o endpoint di cancellazione. Il nome non può
contenere separatori o `..`.

### 3.1 Semantica di W

Il modello storico della sandbox distingue `write`, `create`, `rename`
e `delete`; la GUI li espone insieme come **W** per semplicità. Un
override W=true li abilita tutti, W=false li disabilita tutti. Il
dettaglio resta visibile nelle API e nei `FileInfo`.

## 4. API

| Metodo | Path | Funzione |
|---|---|---|
| GET | `/api/admin/control` | Tool, provider/modelli, impostazioni. `?refresh=1` forza la riscoperta dei modelli locali. |
| POST | `/api/admin/tool` | `{name, enabled}`: allow/deny runtime. |
| POST | `/api/admin/model` | `{provider, model}`: cambio modello runtime. |
| POST | `/api/admin/settings` | `{values: {...}}` oppure `{reset: true}`. |
| GET | `/api/admin/sandbox?path=...` | Elenco di una directory, con `real_path` e paginazione. |
| POST | `/api/admin/sandbox/permissions` | `{path, read, write, execute}`. |
| POST | `/api/admin/sandbox/mkdir` | `{path, name}`: crea una sottodirectory. |

Non esistono endpoint di delete. Le API sono protette dal token e
rifiutano le mutazioni durante un turno.

## 5. Sicurezza

- Le pagine sono servite solo dal server locale; non usare
  `--host 0.0.0.0` su reti non fidate.
- Il token è iniettato nella pagina, come per la GUI principale.
- Il modello non ha accesso HTTP alle API amministrative: non sono
  `ToolDefinition`.
- I path reali sono mostrati solo nella pagina Sandbox
  all’utente locale; i tool del modello continuano a usare path
  virtuali.
- Allow/deny non scavalca policy, conferme, audit o tetto di sistema.
- Il reset da `hagar.yaml` non ricarica la policy: per cambiarla serve
  un riavvio.

## 6. Test

```powershell
python -m pytest tests/test_admin.py -q
python -m pytest tests/test_web.py -q
python -m pytest tests/test_web_admin_integration.py -q
```

I test coprono tool toggle, impostazioni, reset, cambio modello,
albero sandbox, override RWX, mkdir, rifiuto durante un turno e le
rotte HTTP con token.
