# Test di sicurezza L0/L1

**Stato:** implementati.
**Ambito:** containment dell’harness, non persuasività di un modello
reale.

## L0 — modello deterministico compromesso

`test_l0_escape.py` usa `ScriptedLLM`, un client finto che esegue
esattamente le tool call dello script. Non è un modello reale: simula
il caso peggiore, cioè un modello completamente compromesso che tenta
di leggere, scrivere o cancellare fuori dalla sandbox.

Copre:

- path assoluti, traversal `..`, path virtuali, URI `file:`, device path;
- scrittura e cancellazione fuori sandbox;
- policy `DENY` su una lettura interna;
- tool `dev.run` assente quando `dev.enabled: false`;
- limite hardlink noto e dichiarato.

## L1 — prompt injection indiretta

`test_l1_injection.py` simula un modello che *obbedisce* a istruzioni
ostili contenute in:

- un file letto dalla sandbox;
- una riga di un database SQLite letto con `sql.file.query`;
- un contenuto che tenta di abilitare un tool disabilitato.

In tutti i casi il test verifica che:

- il contenuto ostile arrivi davvero al modello;
- il canary fuori sandbox non compaia nella risposta;
- il canary non compaia nell’audit;
- il file esterno resti intatto;
- il tool fuori sandbox fallisca.

## Canary

Ogni test crea un file sintetico fuori dalla sandbox con un token
casuale. Non vengono usati segreti reali, rete esterna o target di
terze parti. I test sono eseguibili in CI e non richiedono Ollama.

## Limite hardlink

`test_known_hardlink_limitation` è `xfail` finché resta il limite
dichiarato: un hardlink dentro la sandbox può condividere l’inode con
un file esterno. Se il limite viene corretto, il test passa.

## Cosa non dimostra

L0/L1 non dimostrano che un modello reale resista a un jailbreak. Un
modello può sempre essere convinto a *tentare*: la sicurezza di Hagar
è che il tentativo non abbia successo. La suite con modello reale
(L2/L3) resta separata, richiede un server locale o un provider e va
trattata come misura probabilistica, non come prova.

## Esecuzione

```powershell
.\.venv\Scripts\python.exe -m pytest tests\security -q
```
