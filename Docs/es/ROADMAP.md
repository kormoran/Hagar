# HAGAR — Roadmap

Versión actual: 0.5.2 (en preparación)
Última actualización: 2026-11-07

Las decisiones tomadas se indican como tales; los puntos aún abiertos están
enumerados al final de cada área. Las secciones 1–9 son el histórico hasta
la 0.5.2; el plan operativo actual es la sección 0.

---

# 0. Plan actual (post-0.5.2)

## 0.1 Estado

Publicado:

- release de GitHub `v0.3.0`;
- CI Linux/macOS/Windows con Python 3.11, 3.12 y 3.13;
- action actualizadas a Node 24;
- documentación italiana más traducciones al inglés, español, chino,
  ruso, portugués y árabe;
- backend `lmstudio`, `openai`/`chatgpt` y `model.timeout`.

Completado después de la release, aún no publicado:

- `HarnessService`: turnos, estado, proyectos, eventos y fin de sesión sin
  `input()`/`stdout`;
- `CommandService`: `/help`, `/tools`, `/status`, `/mcp`, `/audit`,
  `/project`, `/memory` con `CommandResult` estructurado;
- event bridge `Agent`/`ToolRegistry` → `tool.call`, `tool.result`,
  `permission.*`;
- GUI web local `hagar web` con SSE, chat, proyectos, estado y confirmaciones
  ASK modales;
- `QueueConfirmationProvider` con timeout y resolución desde la GUI;
- `core/usage.py`: parsing de tokens para OpenAI/LM Studio/DeepSeek, Claude,
  Gemini y Ollama; `UsageLedger` por sesión;
- barra lateral de la GUI con tokens input/output/total actualizados vía
  `usage.updated`;
- `MemoryIndex`: índice SQLite/FTS5 incremental y reconstruible;
- memoria SQLite como fuente primaria: sesiones, turnos, skill y summary;
- comandos `/memory sessions`, `/memory chat`, `/memory backup`;
- tool `memory.search`, `/memory search`, `/memory reindex`,
  `/memory stats`;
- assets de la GUI separados en `web/index.html`, `web/style.css`, `web/app.js`.

## 0.2 Orden de las próximas releases

| Release | Objetivo | Estado |
|---|---|---|
| **0.4.0** | Índice SQLite de las memorias | fusionado en la 0.5.2 |
| **0.4.x** | GUI: stop del turno, historial, vision | fusionado en la 0.5.2 |
| **0.5.0** | Subagentes | fusionado en la 0.5.2 |
| **0.5.2** | Release actual | en preparación |
| **0.6.0** | Broker LLM | próximo |
| **0.7.0** | Tool SQL de solo lectura | congelado |

El orden puede cambiar, pero la restricción es: **nada de subagentes sin usage y
límites; nada de broker sin subagentes y model registry.**

## 0.3 0.4.0 — Índice SQLite de las memorias

Estado: implementado; quedan la verificación sobre el Vault real y la eventual
medición del rendimiento.

- posición: datos locales de la app, no dentro del Vault sincronizado;
- esquema: notas, skill, decisiones, sesiones, tags, FTS5;
- sync incremental por path/hash/mtime;
- `rebuild()` atómico, índice borrable y reconstruible;
- fallback a la búsqueda léxica si FTS5 no está disponible;
- tool `memory.search` con filtros proyecto/kind/status;
- `/memory reindex` y `/memory stats`;
- ningún path real expuesto al modelo.

Criterio de salida: borrar la DB no pierde memoria; reconstruirla
devuelve los mismos resultados.

## 0.4 0.4.x — GUI

- botón **Stop** del turno — implementado;
- vision: subida de imagen en el compositor, con adapter por proveedor —
  implementado (OpenAI/LM Studio, Claude, Gemini);
- historial de chat visible tras un refresh — implementado como lista
  de los chats pasados con recarga desde el Vault, reanudación de la sesión y
  **+ Nuova chat**;
- pestañas Chat, Chat history, Tool output, Audit, Thinking y Memories —
  implementadas; Audit se deshabilita si el log está apagado, Thinking usa el
  reasoning si está disponible y en su defecto la timeline;
- navegador de memorias de solo lectura — implementado;
- comando `/usage` del lado de la CLI — implementado;
- tool y proveedores LLM como plugin con entry point — implementado;
  audit sink aplazado.

La vision no debe entrar en la memoria como base64: solo hash y
descripción.

## 0.5 0.5.x — Subagentes y consolidación

- [x] MVP síncrono: `AgentSpec`, `agent.run`, tool de solo lectura, memoria
  de solo lectura, confirmaciones denegadas, auditoría `agent.*`, usage separado;
- [x] `agent.spawn/status/wait/result/cancel` con hilos y hasta dos
  subagentes concurrentes;
- [x] registry y workspace privado por hijo, input copiados y cleanup;
- [x] auditoría serializada con lock;
- [x] `reason` obligatorio y capability `AGENT_SPAWN` separada;
- [x] artifact store, mailbox y outbox `artifact.put`/`mailbox.send`,
  con capability `AGENT_DATA` y cleanup;
- [x] auditoría `artifact.discarded` para artifact no exportados;
- [ ] persistencia/orphan retention (solo si es necesaria);
- [x] proyectos y decisiones en la misma base de datos SQLite;
- [x] export Markdown desde la base de datos (`/memory export`);
- [x] import Markdown en la base de datos (`/memory import`);
- [x] FTS5 en la base de datos primaria con ranking y snippet;
- [x] timeout de reloj de 5 minutos por subagente;
- [x] policy del hijo estrictamente más restrictiva que la del padre;
- [x] `agent_id` en los eventos de padre, hijos y registry;
- [x] ASK de los hijos reenviadas al usuario con timeout 180 segundos y DENY;
- [x] tool `decision.choose` con proveedor LLM y clasificador lineal;
- [ ] adapter Jev/Kev y training automático de clasificadores;
- [ ] presupuesto de token/coste;
- [ ] `parent_id` en cada evento interno del hijo;
- [ ] `audio.open`/`AudioInput`: el canal de adjuntos se comparte con las
  imágenes, pero hacen falta proveedores audio-nativos, formatos y semántica ASR
  distintos; ninguna timeline;
- [x] confirmaciones ASK desde consola con input broker, F5/F8 y fallback GUI;

## 0.6 0.6.0 — Broker LLM

- fichas técnicas JSON y benchmark de los modelos (`/models test`);
- detección de hardware CPU/RAM/GPU (`/models hardware`);
- `ModelRegistry` con context window, tool calling, precios, latencia y
  localidad;
- `TaskProfile` con tool requeridos, sensibilidad de datos, presupuesto y contexto;
- routing por reglas/puntuación, no "un LLM elige el modelo";
- propuesta de `AgentSpec` validada por el host;
- el broker nunca concede permisos: solo puede proponer un subconjunto;
- override humano y auditoría `broker.decision`.

## 0.7 0.7.0 — Tool SQL

- solo lectura en la primera versión;
- SQLite `mode=ro`, `PRAGMA query_only`, una sola instrucción;
- nada de `ATTACH`, `PRAGMA` de escritura ni `load_extension`;
- timeout, límite de filas/bytes y auditoría de la query;
- alias de base de datos configurados, nunca rutas arbitrarias;
- capability `DATABASE_READ`;
- escritura y bases de datos de red solo en una fase posterior, con
  `DATABASE_WRITE` y `NETWORK`.

## 0.8 Puntos abiertos

- release workflow idempotente si la release ya existe;
- PyPI: aplazado, no bloquea la 0.4;
- MCP OAuth Atlassian: Basic funciona, el flujo OAuth queda por
  validar;
- test live MCP/OAuth y proveedores remotos;
- mantenimiento de las traducciones: se regeneran solo en release, no en
  cada commit;
- concurrencia y escrituras atómicas del Vault: por evaluar antes de
  subagentes con memoria compartida;
- document tool: contrato y protocolo definidos en `DOCUMENT_TOOL.md`;
  MVP CSV aún por implementar.

## 0.9 Documentación

`Docs/it` es la única fuente mantenida durante el desarrollo. Los directorios
`Docs/en`, `Docs/es`, `Docs/zh`, `Docs/ru`, `Docs/pt` y `Docs/ar` se
regeneran solo cuando se prepara una release.

---

# 1. Dirección

Hagar ha pasado de "idea" a "sistema funcionante" (v0.1) y luego a un
harness con auditoría, backends múltiples y suite de test (v0.2 en curso). El
siguiente salto no es añadir tool: es dar al sistema una **memoria** y
un modo de llamar a los tool menos frágil que el JSON textual.

Orden decidido:

1. memoria sobre Vault;
2. calling nativo para los proveedores que lo admiten;
3. PermissionEvaluator — **v1 hecha** (policy.yaml, ASK, auditoría);
4. higiene (auditoría, MCP, packaging, test live).

---

# 2. Prioridad 1 — Memoria sobre Vault

## 2.0 Estado: v2 implementada (2026-11-04)

Realizado:

- episódica escrita por el harness, una nota por sesión;
- inyección automática de los últimos `context_turns` turnos;
- tool `memory.create_skill`, `memory.list_skills`, `memory.get_context`;
- provenance (`source_session`, `source_turn`, `model`), estado
  `candidate`, deduplicación por slug;
- policy `MEMORY_READ`/`MEMORY_WRITE` y namespace `chat` / `skills`;
- vault ausente → memoria desactivada con aviso, harness activo;
- ciclo de vida `candidate` → `confirmed` → `archived` con revisión
  humana desde la CLI (`/memory review`, `confirm`, `archive`);
- inyección automática de las solas skill confirmadas, top 3 por coincidencia
  léxica;
- retention opción A: ningún borrado automático, solo archivo;
- memoria de proyecto separada de las skill: decisiones, alternativas,
  motivaciones, estado y provenance;
- selección de proyecto al inicio, `--project`/`--free`, comandos
  `/project`;
- summary de fin de sesión con fallback, transcript en `archive/chat/`
  y enlace/hash en el summary;
- review de las decisiones al final de la sesión; si se rechaza, quedan
  `candidate` con `auto_saved: true`;
- contexto de índice con presupuesto `max_context_chars` (caracteres, no
  tokens) y `memory.project_context` para los detalles;
- `project_max_active` para la petición de archivado del proyecto;
- consulta del archivo con `memory.archive_search`,
  `memory.archive_read`, `/memory archive search|read`, filtro por
  proyecto y transcript con `project` en el frontmatter.

Quedan: retention de los chats, búsqueda semántica, GUI.

## 2.1 Decisiones tomadas

- **Episódica escrita por el harness.** Los turnos de chat los registra
  el harness por defecto: es un acta mecánica, no un juicio del
  modelo. Ningún turno perdido, ninguna memoria inventada.
- **Semántica escrita por el LLM, bajo petición.** El modelo puede proponer
  una memoria (skill) solo a través de un tool dedicado. La propuesta es
  explícita, atribuible y revisable — la Primera Ley prohíbe
  tratarla como verdad.
- **Solo Vault Obsidian.** Ninguna escritura en el sistema de archivos real para la
  memoria (por ahora). La `filesystem.sandbox` sigue siendo la sandbox operativa.
- **El Vault no se reescribe.** Los tool añaden notas o secciones; no
  sobrescriben notas cuidadas por el usuario.
- **Proyectos explícitos.** El proyecto se elige al inicio de la lista
  de proyectos activos, o con `--project`; `--free` y "actividad
  libre" no tienen memoria de proyecto.
- **Decisiones de proyecto.** Están separadas de las skill: registran
  decisiones, alternativas y motivaciones. Se proponen como `candidate`
  y se revisan al final de la sesión; si la review se rechaza quedan
  candidate con `auto_saved: true`, no se convierten en verdades automáticas.
- **Nada de cuotas de token.** El contexto está limitado por construcción:
  índice del proyecto, títulos de las decisiones, summary y
  `max_context_chars` en caracteres. No se mide la context window del
  modelo.
- **Archivo, no borrado.** Transcript y decisiones archivadas
  permanecen en el Vault; el archivado de un proyecto es reversible.

## 2.2 Tool previstos

Nombres implementados en el namespace `memory.*`:

| tool | quién lo llama | qué hace |
|---|---|---|
| `memory.create_skill` | LLM | crea una memoria semántica **candidata** |
| `memory.list_skills` | LLM | enumera las memorias disponibles |
| `memory.get_context` | LLM | recupera turnos de chat pasados |

Firmas implementadas:

```text
memory.create_skill(title, content, kind="procedure", tags=None)
    -> {id, title, kind, status, tags, created_at, source_*, path, duplicate}

memory.list_skills(kind=None, status=None, limit=20)
    -> [{id, title, kind, status, tags, created_at, source_*}]

memory.get_context(limit=5, query=None, session=None)
    -> [{session, turn, timestamp, question, answer}]
```

Comportamientos:

- `create_skill`: slug a partir del título, deduplicación por slug, límite de
  longitud (`max_skill_chars`), frontmatter con `status: candidate`,
  `source_session`, `source_turn`, `model`, `created_at`; si ya existe
  un slug igual devuelve el id existente en lugar de duplicar.
- `list_skills`: lee frontmatter y cuerpo (sirve para el recall), filtrable
  por `kind` (`fact` / `procedure`) y `status`.
- `get_context`: sin `session` busca en todas las sesiones; con `query`
  busca por palabras clave en los turnos pasados; `limit` se limita a
  1..50 para no volcar todo el Vault en el contexto.

## 2.3 Estructura en el Vault

```text
<Vault>/Hagar/
  chat/2026-11-03-<session>.md      # una nota por sesión, turnos en append
  skills/<slug>.md                  # una nota por memoria
```

Episódica (una nota por sesión, turnos añadidos al final):

```markdown
---
session: a1b2c3d4
type: chat
created: 2026-11-03T00:12:44+01:00
---

# Chat 2026-11-03

## 2026-11-03T00:12:44+01:00 · 7f3a

**Utente:** ...
**Hagar:** ...
```

Semántica (una nota por skill):

```markdown
---
id: usa-uv-per-python
title: Usare uv per i progetti Python
kind: procedure
status: candidate
tags: [python, tooling]
source_session: a1b2c3d4
source_turn: 7f3a
model: llama3.1:latest
created_at: 2026-11-03T00:15:02+01:00
---

Passi / contenuto proposto dal modello.
```

## 2.4 Configuración

```yaml
vault:
  path: <percorso reale>

memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  max_skill_chars: 4000
```

## 2.5 Comportamiento del harness

- Al final del turno: añade pregunta y respuesta a la nota de sesión (solo
  conversación, **no** output de los tool: esos quedan en la auditoría).
- Al inicio del turno: inyecta los últimos `context_turns` turnos y hasta
  `context_skills` skill **confirmadas** pertinentes (coincidencia léxica),
  sin esperar a que el modelo llame a `get_context`.
- Cada escritura o revisión de memoria produce un evento de auditoría
  (`memory.enabled`, `memory.disabled`, `memory.context`, `memory.turn`,
  `memory.review`, `memory.status`, `memory.failed`); un Vault ausente o
  no escribible no detiene el harness.
- La memoria episódica está separada de la auditoría: la auditoría sigue siendo forense y
  contiene también los datos de los tool.

## 2.6 Puntos abiertos

- **Retention de chat**: cuántas sesiones conservar, si resumir las
  antiguas; la 0.2.0 no borra nada.
- **Búsqueda**: índice (SQLite FTS) o embedding cuando los volúmenes
  crezcan; hoy es por palabra clave.
- **GUI**: confirmación ASK con diálogo modal también para las escrituras de
  memoria y para la review.
- **Selección del contexto**: hoy turnos recientes globales, índice del
  proyecto y top 3 skill confirmadas por coincidencia léxica, sin
  relevancia semántica.
- **Consolidación de decisiones**: el proyecto puede superar
  `project_max_active`; hoy Hagar propone el archivado, no el
  merge de las decisiones duplicadas.

## 2.7 No objetivos (por ahora)

- escritura de memorias en el sistema de archivos real;
- modificación de notas existentes del usuario;
- embedding / ChromaDB / búsqueda semántica (después, si los volúmenes lo
  justifican);
- escritura autónoma de memorias fuera del flujo explícito.

---

# 3. Prioridad 2 — Calling nativo (v1, hecha)

**Estado:** implementado el 2026-11-03. `native_step()` para los cuatro
proveedores, esquema de los parámetros desde `ToolDefinition`, mensajes canónicos
`tool`, varias llamadas por turno, fallback automático en HTTP 400/404/422
y `--no-native-tools`. Verificado live en Ollama y DeepSeek; Claude y
Gemini quedan por probar. Medido con `tools/bench_native.py`: ningún
protocolo vence en todos los modelos (nativo más rápido, texto a veces más
preciso). Queda por afinar para los modelos locales que ignoran los tool.

## 3.1 Objetivo

Eliminar la fragilidad del protocolo JSON textual: nada más de
reparaciones, argumentos validados por el esquema del proveedor, resultados
estructurados.

## 3.2 Enfoque

- Mantener el protocolo textual como **fallback** para los modelos que
  no admiten el calling nativo o lo hacen mal.
- Añadir a `LLMClient` una capacidad declarada
  (`supports_native_tools`) y una ruta nativa.
- El `Agent` debe gestionar ambas: `ToolCall` textual o llamada
  nativa con id; el resultado vuelve en el formato esperado por el proveedor.
- El benchmark mide la mejora (reparaciones por turno,
  corrección de los argumentos).

## 3.3 Transporte por proveedor

| proveedor | petición | resultado tool |
|---|---|---|
| `ollama` | `tools` en `/api/chat` | mensaje con rol `tool` |
| `deepseek` | `tools` (OpenAI) | rol `tool` + `tool_call_id` |
| `claude` | `tools` + bloques `tool_use` | bloque `tool_result` |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 3.4 Riesgos

- Los modelos locales pequeños a menudo no usan bien el calling nativo: hace falta
  el fallback automático.
- Cambia el plumbing de los mensajes: test por proveedor y para la ruta de
  fallback son obligatorios.
- Algunos modelos devuelven varias llamadas en el mismo turno: el Agent
  las ejecuta todas, dentro del límite del turno.

---

# 4. Prioridad 3 — PermissionEvaluator

## 4.1 Estado: v1 implementada

Realizado:

- `Capability`, `Effect`, `Rule`, `Subject`, `Resource`, `Decision` y
  `PermissionEvaluator` en `core/permissions.py`;
- `policy.yaml` leído **antes** del LLM, con fallback a `DENY` total y
  warning en auditoría y chat;
- techo del sistema derivado de `permissions.read/write/shell`;
- scope por `tools` (glob), `paths` y `namespaces` (prefijos);
- `ASK` con `ConsoleConfirmation` (`lo faccio? (y/N)`, default N);
- aplicación en `ToolRegistry.execute` y auditoría de
  `permission.decision` / `permission.confirmation`;
- `ToolDefinition.capabilities` para todos los tool (filesystem y MCP);
- `requires_confirmation` aplicado como suelo de ASK;
- 347 test recopilados, 1 skip.

## 4.2 Queda por hacer

- `ConfirmationProvider` para la GUI (diálogo modal) y para la ejecución
  no interactiva (deny por defecto);
- policy dinámicas por tarea/rol, con solo reducción en runtime (un
  agente puede reducirse los permisos, nunca ampliarlos por sí solo);
- capability de los tool MCP asignadas por la configuración, no
  declaradas por el servidor;
- varios sujetos en ejecución contemporánea (varios agentes con policy
  distintas);
- objetos-recurso para memoria y rutas, no solo tool.

---

# 5. Prioridad 4 — AIsh

Shell dedicado a los LLM, conceptualmente similar a Bash pero sin ningún
acceso al shell real:

- ninguna ejecución de comandos del anfitrión;
- uso exclusivo de tool registrados;
- sistema de archivos simulado y rutas virtuales (`workspace://`);
- integración con tool MCP;
- pipe y comandos virtuales.

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```

Las rutas virtuales resolverían también la exposición de las rutas
absolutas de la sandbox.

---

# 6. Higiene y robustez

Hecha (2026-11-03):

- **MCP**: respuestas `text/event-stream`, notificación
  `notifications/initialized`, normalización de los resultados a texto
  (bloques `text`, `structuredContent`, errores `isError`).
- **MCP auth**: bearer o header personalizado, token solo del entorno,
  servidor omitido con `mcp.failed` si falta el token.
- **MCP OAuth**: flujo authorization code + PKCE con navegador, discovery
  RFC 9728/8414, dynamic registration, cache de token, refresh y retry 401.
- **Auditoría**: rotación a `max_bytes`, cadena de hash verificable con
  `verify_chain`, redacción del output de los tool con
  `include_outputs: false`.
- **Audit retention**: backups con timestamp y `audit.max_files` (default
  100, incluye el archivo activo) con pruning de los más antiguos.
- **Test live**: marcador `live`, excluidos por defecto, `--live` para Ollama
  y proveedores remotos (estos últimos skippados sin clave).
- **Packaging**: metadatos completos, entry point `hagar`, `--config`,
  `--model`, `--no-memory`, `--version`, versión única.
- **URL base**: `model.host` vale para todos los proveedores.
- **Legacy**: eliminados `tools/filesystem.py` y `llm/tool_result.py`.

Quedan:

- device flow / DPoP para MCP OAuth;
- compactación de las sesiones de auditoría;
- confirmaciones GUI para `ASK`;
- alineación continua de la documentación.

---

# 7. Más adelante

- búsqueda semántica sobre el Vault (índice, después eventualmente ChromaDB);
- RAG sobre los documentos;
- gestión de tareas y scratchpad persistente;
- observación del vault (notas modificadas por el usuario);
- agente personal permanente;
- proveedores adicionales (OpenAI es casi gratis: mismo cliente que DeepSeek
  con una base URL distinta).

---

# 8. Orden de trabajo

1. Memoria v2: hecha (ciclo de vida, review CLI, inyección de confirmadas);
   quedan retention de chat, búsqueda semántica y GUI.
2. PermissionEvaluator: v1 hecha; quedan confirmaciones GUI y policy
   dinámicas.
3. Higiene: hecha (packaging, test live, MCP auth/OAuth, auditoría con
   retention, base URL, legacy).
4. Calling nativo: v1 hecha; queda la medición con el benchmark.
5. Release 0.3.0: preparada para GitHub, con CI multiplataforma y
   workflow de release.

---

# 9. Tool locales

Estado al 2026-11-05:

- filesystem v2: `list_dir`, `read_chunk`, `rename`, `copy_file`,
  `search`, además de los tool existentes;
- `local_tools/`: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `feed.read` (proveedores locales, no servidores MCP);
- capability `COMPUTE` siempre en el techo, `NETWORK` controlada por
  `permissions.network` y por la policy (feed en `ask`);
- límites de escritura: `max_write_bytes`, `min_free_bytes`,
  `session_write_bytes` y `ask_over_bytes` con preflight único;
- `feed.read` con policy SSRF: solo direcciones globales, redirect
  revalidados, nada de credenciales en la URL;
- filesystem con raíz virtual `/home/ai`, alias obligatorios y
  permisos por mount (`R`/`W`/`X`);
- runner POSIX `tools/run_tests.sh` junto al de Windows.

Puntos abiertos:

- DNS rebinding: la resolución se valida, pero `requests` resuelve
  de nuevo el nombre en el momento de la conexión; hace falta un resolver
  pinnado o un adapter dedicado para cerrar el caso;
- la calculadora está voluntariamente limitada (nada de álgebra simbólica);
- evaluar un límite de tamaño también para los demás output de los tool.

Cerrado como responsabilidad del usuario:

- hard link, mount y junction dentro de los directorios allowed no están
  controlados por Hagar. Para aislamiento total el usuario debe garantizar
  que no los haya; Hagar no los crea ni los detecta;
- race TOCTOU: Hagar no usa `openat2`, `O_NOFOLLOW` en cada componente ni
  handle de Windows y no garantiza atomicidad entre check y operación. La
  race requiere un proceso local concurrente con acceso de escritura;
  es un escenario malicioso o de entorno comprometido, no uso normal.
  Para aislamiento total hacen falta volumen dedicado, usuario separado, mount
  namespace o contenedor.
