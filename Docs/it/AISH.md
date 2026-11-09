# AIsh

**Stato:** implementato nella 0.6.0
**Tool:** `aish.exec`
**Capability:** `AISH`
**Policy:** DENY di default

## Cos'è

AIsh è un piccolo linguaggio di comando sopra i tool Hagar. Non è una
shell di sistema e non esegue programmi:

```text
aish.exec("ls /home/ai/progetto")
  → filesystem.list_dir
  → policy
  → sandbox
  → audit
```

Non usa `subprocess`, non conosce path host, non espande variabili e non
esegue command substitution.

## Policy

Il repository contiene la regola di default:

```yaml
- capabilities: [AISH]
  effect: deny
  tools: ["aish.*"]
```

Per abilitare AIsh, l'utente deve modificare `policy.yaml`:

```yaml
- capabilities: [AISH]
  effect: allow
  tools: ["aish.*"]
```

Questo abilita solo `aish.exec`. I comandi interni passano comunque dalle
regole dei tool:

```text
cat   → filesystem.read_file
mkdir → filesystem.mkdir
cp    → filesystem.copy_file
rm    → filesystem.delete_file
```

Quindi una policy che permette `aish.exec` ma nega `filesystem.delete_file`
continua a impedire `rm`.

## Comandi implementati

### Lettura

```text
pwd cd ls stat cat head tail wc grep find
sha256sum df date basename dirname
```

### Testo

```text
echo printf sort uniq cut tr sed
```

Usano `text.transform`; `sed` supporta solo
`s/PATTERN/REPLACEMENT/[g]`.

### Mutazioni semplici

```text
mkdir touch cp mv rm
```

`rm` e `mv` richiedono che il file sia stato letto in precedenza, come i
tool filesystem. `cp` non sovrascrive una destinazione esistente.

## Pipeline

```text
cat note.txt | grep errore | sort | wc -l
```

Le pipeline sono consentite solo tra comandi di lettura/testo. Un comando
di mutazione dentro una pipeline viene rifiutato.

## Cosa non è supportato

```text
> >> <          redirezione
; && || &       separatori e operatori
$() `...`       command substitution
$VAR ${VAR}     variabili
* ? []          glob (usare find)
sed awk         linguaggi
bash sh python  programmi host
find -exec      esecuzione
```

## Limiti

- niente glob: usare `find -name`;
- niente redirezione: le mutazioni sono comandi espliciti;
- niente `rm -r`, `cp -r`, directory ricorsive;
- output limitato a 100.000 caratteri;
- l'help dei comandi è volutamente minimale;
- l'implementazione è volutamente lessicale: non c'è una shell POSIX
  completa.

Le trasformazioni testuali passano da
[`text.transform`](TEXT_TRANSFORM.md).

## Audit

Ogni comando produce:

```text
aish.command
  command
  arguments
  pipeline
```

Gli audit dei tool interni (`tool.call`, `tool.result`,
`permission.decision`) restano attivi.
