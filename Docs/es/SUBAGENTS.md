# Subagentes — fase asíncrona

**Estado:** implementado
**Fecha:** 2026-11-07
**Tool:** `agent.spawn`, `agent.status`, `agent.wait`, `agent.result`,
`agent.cancel`, `agent.run` (compatibilidad síncrona), `artifact.*`,
`mailbox.*`

## 1. Qué hacen

El modelo puede iniciar hasta dos subagentes concurrentes:

```text
agent.spawn(task, reason, context?, inputs?) -> agent_id
agent.status(agent_id) -> estado
agent.wait(agent_id, timeout?) -> resultado
agent.result(agent_id) -> resultado
agent.cancel(agent_id) -> ok
```

`spawn` retorna de inmediato. El padre puede seguir trabajando y recoger
los resultados cuando los necesita. `agent.run` permanece como atajo
`spawn + wait` por compatibilidad.

`reason` es obligatorio: se registra en el audit y es la motivación
por la que el padre delega el trabajo. El tool requiere la capability
`AGENT_SPAWN`; el hijo no la recibe, por lo que no puede crear otros.
`permissions.agents: true` es el techo de sistema necesario.

La policy del hijo debe ser **estrictamente más restrictiva** que
la del padre. El manager calcula:

```text
child_ceiling = parent_ceiling
              & (FILESYSTEM_READ | MEMORY_READ | COMPUTE | AGENT_DATA)
```

Si el resultado es igual al techo del padre, `agent.spawn` falla con
`SubagentPolicyError`. Por lo tanto, también se rechazan policy idénticas.
Si el padre no tiene un evaluator, el spawn se rechaza.

Cada agente tiene un timeout de reloj de **5 minutos** (`300` segundos). El
límite es cooperativo: se comprueba en los checkpoints del ciclo del agente;
no interrumpe una llamada HTTP ya en curso. Al expirar, el estado del
hijo es `timed_out` y el audit registra `agent.timed_out`.

Cada hijo:

- usa el mismo modelo local que el padre, pero un cliente LLM separado;
- tiene un registry separado;
- solo ve los tool con capability `FILESYSTEM_READ`,
  `MEMORY_READ` y `COMPUTE`, más `AGENT_DATA`;
- puede usar `vision.open` en su propio workspace, pero no
  `agent.*` ni `filesystem.chdir`;
- lee solo su propio workspace;
- no escribe en la memoria;
- reenvía las peticiones ASK al usuario mediante un bridge, con un timeout de
  180 segundos y DENY al expirar.

El padre LLM no puede aprobar un ASK: la petición va siempre al canal
humano (GUI o consola). El bridge añade `agent_id` y `parent_id` a la
petición.

## 2. Workspace privado

Para cada hijo se crea un workspace temporal:

```text
<hagar-temp>/hagar-subagent-<id>/
```

El hijo lo ve como:

```text
/home/ai/workspace
```

El workspace es de solo lectura. Antes del inicio, el manager copia los
input indicados por el padre:

```text
agent.spawn(
    task="analizza il CSV",
    reason="i file sono indipendenti e vanno analizzati in parallelo",
    inputs=["/home/ai/workspace/report.csv"]
)
```

Reglas:

- los input deben ser archivos dentro del sandbox del padre;
- el padre debe tener el permiso de lectura;
- el nombre del archivo se conserva;
- dos input con el mismo nombre son un error;
- el hijo no ve el path del host;
- el workspace se elimina al final del turno.

El padre escribe solo en su propio workspace. El workspace del hijo está
fuera de las raíces del padre, por lo que no es alcanzable desde sus tool.

## 2.1 Outbox, artifact y mailbox

El hijo no escribe en el workspace. Para producir datos usa la outbox:

```text
artifact.put(text, kind?, mime_type?)       -> artifact_id
artifact.put_file(path, mime_type?)          -> artifact_id
mailbox.send(text, artifacts?)               -> message
```

`artifact.put_file` lee un archivo del workspace de solo lectura del hijo y
lo copia en el store gestionado por Hagar.

El padre lee con:

```text
artifact.list()
artifact.read(artifact_id, offset?, length?)
artifact.save_to(artifact_id, path, overwrite?)
mailbox.inbox(cursor?, limit?)
mailbox.read(message_id)
mailbox.ack(message_id)
```

`artifact.save_to` copia el artifact completo a un path escribible del
sandbox del padre sin hacer pasar el contenido por el contexto. Es
la operación que hay que usar para artifact más grandes que la ventana del modelo:
el modelo lee solo los chunk que necesita y guarda el archivo completo
con `save_to`.

`save_to` requiere `AGENT_DATA`, `FILESYSTEM_WRITE` y
`FILESYSTEM_CREATE`; la policy lo trata como una escritura y puede
pedir confirmación. No acepta path de host arbitrarios.

Límites iniciales:

| Elemento | Límite |
|---|---|
| artifact individual | 50 MB |
| total de artifact por turno | 256 MB |
| artifact por turno | 200 |
| lectura por llamada | 256 KB |
| texto de un mensaje | 64 KB |
| mensajes por mailbox | 100 |

Los artifact son archivos temporales fuera del Vault, con hash SHA-256 y
metadatos. La mailbox contiene solo texto y referencias `artifact_id`.
Al final del turno, el store y la mailbox se vacían.

## 3. Límites de la implementación

- máximo **2** subagentes activos (configurable en el manager como
  `max_concurrent`);
- solo modelos locales;
- sin anidamiento: el registry del hijo excluye `agent.*`;
- timeout de reloj de 5 minutos, cooperativo;
- ningún presupuesto de token más allá de `max_tool_calls`;
- ninguna GUI dedicada;
- ninguna escritura de memoria;
- ASK del hijo reenviadas al usuario con timeout de 180 segundos; al
  expirar, DENY;
- artifact y mailbox son efímeros: desaparecen al final del turno;
- los eventos internos del hijo (`turn.*`, `tool.*`) tienen `agent_id` en
  el audit.

Al final del turno del padre:

1. `finish_turn()` espera a los hijos durante un timeout;
2. cancela los que siguen activos;
3. elimina los workspace;
4. olvida los job.

## 4. Componentes aislados

| Componente | Padre | Hijo |
|---|---|---|
| Cliente LLM | `harness.llm` | nueva instancia, mismo modelo |
| Tool registry | completo | filtrado de solo lectura |
| Filesystem | workspace del padre | workspace privado de solo lectura |
| Memoria | `MemoryStore` | `memory=None`, ninguna escritura |
| Artifact/mailbox | lectura | outbox del hijo |
| Confirmaciones | usuario | bridge hacia el usuario, timeout 180 |
| Usage | ledger del padre | ledger separado |
| Audit | compartido, con lock | eventos `agent.*` |

El hijo no tiene el contexto automático del padre: el padre debe pasar
`context`.

## 5. Tool admitidos

El padre debe tener las capability `AGENT_SPAWN` y `COMPUTE`; el hijo
no recibe `AGENT_SPAWN` y, por lo tanto, no puede crear otros agentes.

El registry del hijo incluye los tool cuyas capability son un
subconjunto de:

```text
FILESYSTEM_READ
MEMORY_READ
COMPUTE
AGENT_DATA
```

El hijo recibe `artifact.put`, `artifact.put_file` y `mailbox.send`.
No recibe `artifact.read`, `artifact.list`, `mailbox.inbox`,
`mailbox.read` ni `mailbox.ack`: esos son del padre.

Se excluyen explícitamente:

```text
filesystem.chdir
agent.*
```

Se excluyen por capability:

- escritura en el filesystem;
- creación, renombrado, copia, borrado;
- escritura en la memoria;
- red;
- MCP;
- shell.

## 6. Audit

Eventos registrados por el manager:

```text
agent.spawned
agent.policy_rejected
agent.started
agent.finished
agent.timed_out
agent.cancelled
agent.failed
confirmation.timeout
artifact.discarded
```

Campos principales:

```text
agent_id
agent
parent
task
inputs
max_tool_calls
max_seconds
status
usage
duration_ms
error
artifact
owner
kind
size
sha256
read_count
reason
```

Todos los eventos del padre y de los hijos llevan `agent_id`. Los eventos
del registry y del Agent usan el id del agente que ha ejecutado
la acción; los eventos del manager añaden `agent_id` y `parent`.
`agent.policy_rejected` se emite si el spawn no tiene una policy
estrictamente más restrictiva.

`artifact.discarded` se emite al final del turno por cada artifact no
guardado con `artifact.save_to`:

```text
reason=unread                → nunca leído
reason=read_but_not_saved    → leído pero no exportado
```

`confirmation.timeout` se emite si el ASK del hijo queda sin
respuesta durante 180 segundos; el resultado es DENY. La GUI muestra la petición con
`agent_id`/`parent_id` y el padre no puede resolverla.

Los artifact exportados no producen el evento: el archivo ya está en el
workspace del padre. El contenido nunca se escribe en el audit.

`AuditLog.record` está protegido por lock, de modo que las escrituras concurrentes no
entrelazan la cadena de hash.

## 7. Concurrencia

- hilos separados para los hijos;
- límite `max_concurrent = 2`;
- lock sobre el diccionario de job;
- ninguna condición de race sobre el filesystem: workspace separados;
- ninguna compartición de `MemoryStore`, sandbox o cliente LLM;
- proveedor local con peticiones concurrentes;
- `agent.wait` bloquea solo al llamante, no a los demás hijos.

## 8. Test

`tests/test_subagents.py` cubre:

- ejecución con tool de solo lectura;
- exclusión de escritura y `agent.*`;
- paso del contexto;
- copia de los input en el workspace privado;
- rechazo por encima de `max_concurrent`;
- dos subagentes concurrentes;
- error de construcción del proveedor;
- eventos de audit.

Test live ejecutado con LM Studio y `gemma-3-27b-it`: dos subagentes
concurrentes completados, cada uno con usage separado.

## 9. Próximos pasos

- export explícito de los artifact desde el workspace del hijo;
- presupuesto de token/tiempo y timeout de reloj;
- anidamiento controlado, si se requiere;
- `agent_id` en todos los eventos internos;
- confirmaciones delegadas al padre o a la GUI;
- modelo elegido por el broker, no por el manager.
