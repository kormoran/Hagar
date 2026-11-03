# Athena Changelog
2026-10-26

## 1. Riparazione repository
Corretti tre difetti che impedivano il caricamento corretto del sistema:

- payload mancanti in events.py;
- metodi PromptManager fuori classe;
- errori gravi in mcp_agent.py.

## 2. Multi-LLM
Implementato:

- [[llm.instances]]
- routing per purpose
- PromptAgent multipli
- LLMFactory per istanza
- telemetria per istanza
Compatibilità mantenuta con configurazioni esistenti.

## 3. Estrazione
Introdotti:

- schema Extraction
- validazione rigida
- DeterministicExtractor
- LLMExtractor
- parsing JSON robusto

## 4. Architettura:

extract → orchestrator → respond

### 4.1 Orchestrator

Creato Orchestrator minimale.

Supporta:
- respond
- abort
- clarify

Predisposto per il ciclo di correzione A–F.

### 4.2 Archiver
Corretta incompatibilità tra: **chat** e **respond**. Gli episodi vengono nuovamente salvati correttamente.

## 5. Testing
Suite portata a:

- 576 test verdi

## 6. Sessioni recenti

### 6.1 - 2026-10-23

Architettura a tre stadi
Decisione approvata: estrazione → logica → generazione

#### 6.1.1 Auto-verifica

Creato il concetto di: Caso F: errore individuato internamente da Athena.

#### 6.1.2 Ciclo di correzione

Definita la tassonomia:

A Chat
B MCP
C System
D Logic
E Altro
F Auto-verifica

#### 6.1.3 Multi-LLM
Approvata l'architettura:

- N PromptAgent
- uno per istanza

### 6.2 - 2026-10-19

Persistenza: completata migrazione a ID interi progressivi.
Identità: introdotto ATHENA_IDENTITY_ID = 1 protetto da modifiche e cancellazioni.
Relazioni: Implementato supporto per:
- source_type
- target_type
Cancellazione esplicita delle relazioni.

### 6.3 - 2026-10-14
Configurazione: migrazione completa verso **athena.toml** e **Athenaconf.py** come loader.
Sessioni future: aggiungere una sezione per ogni giornata di lavoro.

Formato consigliato:

YYYY-MM-DD
Implementato
...
Modificato
...
Decisioni prese
...
Test
...