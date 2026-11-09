# `text.transform`

**Stato:** implementato nella 0.6.0
**Capability:** `FILESYSTEM_READ | COMPUTE`
**Tipo:** read-only

## Scopo

`text.transform` applica una trasformazione testuale dichiarativa a un
file della sandbox o a testo inline. Non scrive file e non esegue
programmi.

```text
text.transform(
    operation,
    path?,
    text?,
    ...
)
```

Un solo input tra `path` e `text`.

## Operazioni

| Operazione | Parametri principali |
|---|---|
| `grep` | `pattern`, `ignore_case`, `invert`, `line_numbers` |
| `sort` | `numeric`, `reverse`, `unique` |
| `uniq` | — |
| `cut` | `delimiter`, `fields` |
| `tr` | `set1`, `set2` |
| `wc` | `unit`: `lines`, `words`, `bytes` |
| `head` | `count` |
| `tail` | `count` |
| `sed_replace` | `pattern`, `replacement`, `ignore_case`, `global_replace` |

## Risultato

```json
{
  "operation": "grep",
  "text": "...",
  "matches": 2,
  "truncated": false
}
```

`truncated: true` significa che l’output ha superato il limite inline.

## Limiti

- input massimo 1.000.000 caratteri;
- output inline massimo 100.000 caratteri;
- pattern massimo 1.000 caratteri;
- massimo 10.000 match per `grep`;
- `sort -n` richiede righe numeriche;
- regex Python: il chiamante deve evitare pattern con backtracking
  catastrofico;
- niente binari, symlink, path host o scrittura.

## Policy

La regola consigliata, già presente in `policy.yaml`:

```yaml
- capabilities: [FILESYSTEM_READ, COMPUTE]
  effect: allow
  tools: ["text.transform"]
```

`text.transform` non concede scrittura: per salvare il risultato servono
`filesystem.write_file` o `filesystem.create_file`, con il normale gate
read-before-write.

## Uso da AIsh

AIsh usa il tool per:

```text
grep sort uniq cut tr wc head tail sed
```

`sed` è limitato a:

```text
sed 's/PATTERN/REPLACEMENT/[g]'
```

non è un interprete sed completo.
