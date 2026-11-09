# Checkpoint, timeout, spill e compaction

**Stato:** implementati nella 0.6.0
**Configurazione:** sezione `tools`
**Comando:** `/undo`

## 1. Checkpoint del turno

Prima di ogni turno Hagar apre un checkpoint. Il sandbox registra solo i
file che una mutazione sta per cambiare:

```text
write_file
edit_file
create_file
write_bytes
delete_file
rename
copy_file
```

Non viene copiato l'intero workspace. Il checkpoint conserva contenuto e
modalità dei file toccati; se un file è stato creato, l'undo lo elimina.

```text
/undo
```

ripristina l'ultimo checkpoint completato.

Limiti:

- solo file, non directory;
- solo l'ultimo turno;
- massimo 32 MB di snapshot;
- se il checkpoint è incompleto, l'undo viene rifiutato;
- l'undo non modifica la memoria SQLite né l'audit.

## 2. Timeout per tool

```yaml
tools:
  timeout: 120
```

Il timeout vale per una singola chiamata. `0` disabilita il limite.

I tool che non completano entro il limite restituiscono un errore
`tool.timeout`. Un handler Python già in esecuzione non viene ucciso:
il worker è un thread demone e può terminare dopo il timeout. Per questo
il timeout va usato soprattutto su tool di rete o potenzialmente lenti,
non come garanzia di interruzione di una scrittura.

## 3. Repeat guard

```yaml
tools:
  repeat_limit: 3
```

Hagar calcola un hash di `tool + argomenti` per ogni turno.

```text
seconda chiamata identica  → audit tool.repeat
terza chiamata identica    → bloccata
```

`0` disabilita il blocco.

## 4. Output spill

Gli output oltre 12.000 caratteri vengono salvati nell'`ArtifactStore`:

```text
tool.spilled
  artifact_id
  original_chars
```

Al modello arriva un riepilogo con anteprima e `artifact_id`; il contenuto
completo si legge con `artifact.read` finché l'artifact è disponibile.
Questo evita di riempire il contesto con output enormi.

## 5. Compaction del contesto

Quando la conversazione interna supera 24.000 caratteri, Hagar sostituisce
i messaggi più vecchi con un segnaposto, mantenendo gli ultimi 8 messaggi.
I messaggi `system` non vengono rimossi.

```text
context.compacted
  messages
```

La compaction è deterministica: non chiama un LLM e non riscrive la
memoria persistente.

## Limiti

- checkpoint, spill e compaction non sono ancora persistiti tra sessioni;
- la compaction è una potatura, non un riassunto semantico;
- lo spill è pensato anche per il futuro broker;
- il repeat guard è per turno, non globale;
- il timeout non interrompe un handler già in esecuzione;
- la versione completa con per-agent isolation, hash e audit `fs.*` è
  congelata nella roadmap.
