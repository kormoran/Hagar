# HAGAR — Roadmap

Versión actual: 0.7.0 (en desarrollo)
Última actualización: 2026-11-09

Las decisiones tomadas se indican como tales; los puntos aún abiertos están
enumerados al final de cada área. Las secciones 1–9 son el histórico hasta
la 0.6.0; el plan operativo actual es la sección 0.

---

# 0. Plan actual (post-0.6.0)

## 0.1 Orden de las próximas releases

| Release | Objetivo | Estado |
|---|---|---|
| **0.6.0** | Runtime safety + AIsh | publicada |
| **0.7.0** | dev.run + box + Hagar Flow | en desarrollo |
| **0.8.0** | Broker LLM | próximo |
| **0.9.0** | Tool SQL de solo lectura | congelado |

El orden puede cambiar, pero la restricción es: **nada de subagentes sin usage y
límites; nada de broker sin subagentes y model registry.**

## 0.1.1 0.7.0 — Orquestación local

- `dev.run` con recetas de confianza fuera de la sandbox;
- `box.list` y `box.run` para transformaciones LLM acotadas;
- `flow.run`, `flow.validate` y `flow.reference`;
- list comprehension con un solo `for`;
- primitivas de memoria de solo lectura: `memory.search`, `memory.context`,
  `memory.skill` y `project.context`;
- repair explícito con `flow.repair`;
- nada de container mode en esta release.

## 0.2 0.8.0 — Broker LLM

- fichas técnicas JSON y benchmark de los modelos (`/models test`);
- detección de hardware CPU/RAM/GPU (`/models hardware`);
- `ModelRegistry` con context window, tool calling, precios, latencia y
  localidad;
- `TaskProfile` con tool requeridos, sensibilidad de datos, presupuesto y contexto;
- routing por reglas/puntuación, no "un LLM elige el modelo";
- propuesta de `AgentSpec` validada por el host;
- el broker nunca concede permisos: solo puede proponer un subconjunto;
- override humano y auditoría `broker.decision`.

## 0.3 0.8.0 — Tool SQL

- solo lectura en la primera versión;
- SQLite `mode=ro`, `PRAGMA query_only`, una sola instrucción;
- nada de `ATTACH`, `PRAGMA` de escritura ni `load_extension`;
- timeout, límite de filas/bytes y auditoría de la query;
- alias de base de datos configurados, nunca rutas arbitrarias;
- capability `DATABASE_READ`;
- escritura y bases de datos de red solo en una fase posterior, con
  `DATABASE_WRITE` y `NETWORK`.

## 0.4 Puntos abiertos

- release workflow idempotente si la release ya existe;
- PyPI: aplazado;
- MCP OAuth Atlassian: Basic funciona, el flujo OAuth queda por
  validar;
- test live MCP/OAuth y proveedores remotos;
- mantenimiento de las traducciones: se regeneran solo en release, no en
  cada commit;
- document tool: contrato y protocolo definidos en `DOCUMENT_TOOL.md`;
  MVP CSV aún por implementar.

## 0.4.1 Versión completa filesystem — congelada

Implementado ahora:

- `edit_file` con escritura atómica;
- checkpoint del turno y `/undo`;
- timeout por tool y repeat guard;
- output spill y compaction del contexto.

El MVP implementado cubre `edit_file`, escritura atómica,
read-before-overwrite/delete/rename y versión `mtime_ns+size`.
La versión completa está congelada; no entra en la próxima release:

- `edit_file` con patch de varios hunk y diff;
- hash del contenido además de `mtime_ns`/`size`;
- escritura atómica con control CAS a nivel de filesystem;
- observación por agente único con aislamiento explícito entre padre y
  subagentes;
- auditoría `fs.observed`, `fs.guard_denied`, `fs.stale`;
- cobertura de rename/delete de directorios;
- integración GUI y mensajes de recuperación guiada.

## 0.4.2 AIsh — implementada en la 0.6.0

`aish.exec` es una shell semántica sobre los tool Hagar, con policy `DENY`
por defecto. Comandos implementados: navegación, lectura, texto puro,
pipeline y mutaciones de archivos individuales. No ejecuta programas del
host, redirecciones, variables ni command substitution.
`text.transform` proporciona las operaciones textuales acotadas usadas por AIsh.

## 0.4.3 dev.run — implementado

`dev.list` y `dev.run` ejecutan recetas de confianza para test, debug y build.
`recipes.yaml` está fuera de la sandbox, se lee al arranque y no tiene
hot reload. `DEV_EXEC` es DENY por defecto; el backend es solo host.

El container queda congelado para un futuro acceso directo a
filesystem/programas reales, nunca dentro de la sandbox.

## 0.4.4 Boxed transform — implementadas

`box.list` y `box.run` ejecutan `summarize`, `translate` y
`extract_json` con prompt fijo, input/output en archivo y ninguna memoria
o tool. `BOX_EXEC` es DENY por defecto.

Son las primitivas del futuro DSL.

## 0.4.5 Hagar Flow — MVP

`flow.run` ejecuta un subconjunto lineal de Python con validador AST e
intérprete Hagar, sin `eval`/`exec`. Primitivas `fs.*` y `box.*`, límites
de step y tool call. `FLOW_EXEC` es DENY por defecto.

HIR, paralelismo y subagentes quedan fuera del MVP.

## 0.5 Documentación

`Docs/it` es la única fuente mantenida durante el desarrollo. Los directorios
`Docs/en`, `Docs/es`, `Docs/zh`, `Docs/ru`, `Docs/pt` y `Docs/ar` se
regeneran solo cuando se prepara una release.

---

## 1.0 Estado: v2 implementada (2026-11-04)

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

## 1.1 Decisiones tomadas

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

## 1.2 Tool previstos

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

## 1.3 Estructura en el Vault

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

## 1.4 Configuración

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

## 1.5 Comportamiento del harness

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

## 1.6 Puntos abiertos

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

## 1.7 No objetivos (por ahora)

- escritura de memorias en el sistema de archivos real;
- modificación de notas existentes del usuario;
- embedding / ChromaDB / búsqueda semántica (después, si los volúmenes lo
  justifican);
- escritura autónoma de memorias fuera del flujo explícito.

---

## 2 Objetivo

Eliminar la fragilidad del protocolo JSON textual: nada más de
reparaciones, argumentos validados por el esquema del proveedor, resultados
estructurados.

## 2.1 Enfoque

- Mantener el protocolo textual como **fallback** para los modelos que
  no admiten el calling nativo o lo hacen mal.
- Añadir a `LLMClient` una capacidad declarada
  (`supports_native_tools`) y una ruta nativa.
- El `Agent` debe gestionar ambas: `ToolCall` textual o llamada
  nativa con id; el resultado vuelve en el formato esperado por el proveedor.
- El benchmark mide la mejora (reparaciones por turno,
  corrección de los argumentos).

## 2.2 Transporte por proveedor

| proveedor | petición | resultado tool |
|---|---|---|
| `ollama` | `tools` en `/api/chat` | mensaje con rol `tool` |
| `deepseek` | `tools` (OpenAI) | rol `tool` + `tool_call_id` |
| `claude` | `tools` + bloques `tool_use` | bloque `tool_result` |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 2.3 Riesgos

- Los modelos locales pequeños a menudo no usan bien el calling nativo: hace falta
  el fallback automático.
- Cambia el plumbing de los mensajes: test por proveedor y para la ruta de
  fallback son obligatorios.
- Algunos modelos devuelven varias llamadas en el mismo turno: el Agent
  las ejecuta todas, dentro del límite del turno.

---

# 3. Prioridad 3 — PermissionEvaluator

Estado: v1 implementada

## 3.1 Queda por hacer

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

Shell dedicada a los LLM, conceptualmente similar a Bash pero sin ningún
acceso a la shell real:

- ninguna ejecución de comandos del host;
- uso exclusivo de tool registrados;
- filesystem simulado y rutas virtuales (`workspace://`);
- integración con tool MCP;
- pipe y comandos virtuales.

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```


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
- **URL base**: `model.host` vale para todos los proveedores.

Quedan:

- device flow / DPoP para MCP OAuth;
- compactación de las sesiones de auditoría;
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
