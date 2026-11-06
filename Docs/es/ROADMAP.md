# HAGAR — Roadmap

Versión actual: 0.2.0 (en desarrollo)
Última actualización: 2026-11-03

Las decisiones tomadas se indican como tales; los puntos aún abiertos se
enumeran al final de cada área.

---

# 1. Dirección

Hagar ha pasado de "idea" a "sistema funcional" (v0.1) y después a un
harness con auditoría, backends múltiples y suite de pruebas (v0.2 en curso). El
siguiente salto no es añadir herramientas: es dar al sistema una **memoria** y
un modo de llamar a las herramientas menos frágil que el JSON textual.

Orden decidido:

1. memoria sobre Vault;
2. calling nativo para los proveedores que lo soportan;
3. PermissionEvaluator — **v1 hecha** (policy.yaml, ASK, auditoría);
4. higiene (auditoría, MCP, packaging, test live).

---

# 2. Prioridad 1 — Memoria sobre Vault

## 2.0 Estado: v2 implementada (2026-11-04)

Realizado:

- episódica escrita por el harness, una nota por sesión;
- inyección automática de los últimos `context_turns` turnos;
- herramientas `memory.create_skill`, `memory.list_skills`, `memory.get_context`;
- provenance (`source_session`, `source_turn`, `model`), estado
  `candidate`, deduplicación por slug;
- política `MEMORY_READ`/`MEMORY_WRITE` y namespace `chat` / `skills`;
- vault ausente → memoria desactivada con aviso, harness activo;
- ciclo de vida `candidate` → `confirmed` → `archived` con revisión
  humana desde la CLI (`/memory review`, `confirm`, `archive`);
- inyección automática de las únicas skill confirmadas, top 3 por match
  léxico;
- retención opción A: ningún borrado automático, solo archivo;
- memoria de proyecto separada de las skill: decisiones, alternativas,
  motivaciones, estado y provenance;
- selección de proyecto al arrancar, `--project`/`--free`, comandos
  `/project`;
- resumen de fin de sesión con fallback, transcript en `archive/chat/`
  y enlace/hash en el resumen;
- revisión de las decisiones al final de la sesión; si se rechaza, siguen
  siendo `candidate` con `auto_saved: true`;
- contexto por índice con presupuesto `max_context_chars` (caracteres, no
  tokens) y `memory.project_context` para los detalles;
- `project_max_active` para la solicitud de archivado del proyecto;
- consulta del archivo con `memory.archive_search`,
  `memory.archive_read`, `/memory archive search|read`, filtro por
  proyecto y transcript con `project` en el frontmatter.

Quedan: retención de los chats, búsqueda semántica, GUI.

## 2.1 Decisiones tomadas

- **Episódica escrita por el harness.** Los turnos de chat los registra
  el harness por defecto: es un acta mecánica, no un juicio del
  modelo. Ningún turno ausente, ninguna memoria inventada.
- **Semántica escrita por el LLM, bajo petición.** El modelo puede proponer
  una memoria (skill) solo a través de una herramienta dedicada. La propuesta es
  explícita, atribuible y revisable — la Primera Ley prohíbe
  tratarla como verdad.
- **Solo Vault Obsidian.** Ninguna escritura en el sistema de archivos real para la
  memoria (por ahora). La `filesystem.sandbox` sigue siendo la sandbox operativa.
- **El Vault no se reescribe.** Las herramientas añaden notas o secciones; no
  sobrescriben notas cuidadas por el usuario.
- **Proyectos explícitos.** El proyecto se elige al arrancar de la lista
  de los proyectos activos, o con `--project`; `--free` y "actividad
  libre" no tienen memoria de proyecto.
- **Decisiones de proyecto.** Están separadas de las skill: registran
  decisiones, alternativas y motivaciones. Se proponen como `candidate`
  y se revisan al final de la sesión; si la revisión se rechaza, siguen
  candidatas con `auto_saved: true`, no se convierten en verdad automática.
- **Nada de cuotas de tokens.** El contexto está limitado por construcción:
  índice del proyecto, títulos de las decisiones, resumen y
  `max_context_chars` en caracteres. No se mide la context window del
  modelo.
- **Archivo, no borrado.** Los transcript y las decisiones archivadas
  siguen en el Vault; el archivado de un proyecto es reversible.

## 2.2 Herramientas previstas

Nombres implementados en el namespace `memory.*`:

| herramienta | quién la llama | qué hace |
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
  chat/2026-11-03-<session>.md      # una nota por sesión, turnos añadidos al final
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

**Usuario:** ...
**Hagar:** ...
```

Semántica (una nota por skill):

```markdown
---
id: usa-uv-per-python
title: Usar uv para los proyectos Python
kind: procedure
status: candidate
tags: [python, tooling]
source_session: a1b2c3d4
source_turn: 7f3a
model: llama3.1:latest
created_at: 2026-11-03T00:15:02+01:00
---

Pasos / contenido propuesto por el modelo.
```

## 2.4 Configuración

```yaml
vault:
  path: <ruta real>

memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  max_skill_chars: 4000
```

## 2.5 Comportamiento del harness

- Al final del turno: añade pregunta y respuesta a la nota de sesión (solo
  conversación, **no** salida de las herramientas: esas quedan en la auditoría).
- Al inicio del turno: inyecta los últimos `context_turns` turnos y hasta
  `context_skills` skill **confirmadas** pertinentes (match léxico),
  sin esperar a que el modelo llame a `get_context`.
- Cada escritura o revisión de memoria produce un evento de auditoría
  (`memory.enabled`, `memory.disabled`, `memory.context`, `memory.turn`,
  `memory.review`, `memory.status`, `memory.failed`); un Vault ausente o
  no escribible no detiene el harness.
- La memoria episódica está separada de la auditoría: la auditoría sigue siendo forense y
  contiene también los datos de las herramientas.

## 2.6 Puntos abiertos

- **Retención de chat**: cuántas sesiones conservar, si resumir las
  antiguas; la 0.2.0 no borra nada.
- **Búsqueda**: índice (SQLite FTS) o embedding cuando los volúmenes
  crezcan; hoy es por palabra clave.
- **GUI**: confirmación ASK con diálogo modal también para las escrituras de
  memoria y para la revisión.
- **Selección del contexto**: hoy turnos recientes globales, índice del
  proyecto y top 3 skill confirmadas por match léxico, sin
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
`tool`, varias llamadas por turno, fallback automático ante HTTP 400/404/422
y `--no-native-tools`. Verificado en vivo en Ollama y DeepSeek; Claude y
Gemini quedan por probar. Medido con `tools/bench_native.py`: ningún
protocolo gana en todos los modelos (el nativo es más rápido, el texto a veces más
preciso). Queda por afinar para los modelos locales que ignoran las herramientas.

## 3.1 Objetivo

Eliminar la fragilidad del protocolo JSON textual: nada más de
reparaciones, argumentos validados por el esquema del proveedor, resultados
estructurados.

## 3.2 Enfoque

- Mantener el protocolo textual como **fallback** para los modelos que
  no soportan el calling nativo o lo hacen mal.
- Añadir a `LLMClient` una capacidad declarada
  (`supports_native_tools`) y una ruta nativa.
- El `Agent` debe gestionar ambas: `ToolCall` textual o llamada
  nativa con id; el resultado vuelve en el formato esperado por el proveedor.
- El benchmark mide la mejora (reparaciones por turno,
  corrección de los argumentos).

## 3.3 Transporte por proveedor

| proveedor | petición | resultado de la herramienta |
|---|---|---|
| `ollama` | `tools` en `/api/chat` | mensaje con rol `tool` |
| `deepseek` | `tools` (OpenAI) | rol `tool` + `tool_call_id` |
| `claude` | `tools` + bloques `tool_use` | bloque `tool_result` |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 3.4 Riesgos

- Los modelos locales pequeños a menudo no usan bien el calling nativo: hace falta
  el fallback automático.
- Cambia el plumbing de los mensajes: son obligatorios los test por proveedor y para la ruta de
  fallback.
- Algunos modelos devuelven varias llamadas en el mismo turno: el Agent
  las ejecuta todas, dentro del límite del turno.

---

# 4. Prioridad 3 — PermissionEvaluator

## 4.1 Estado: v1 implementada

Realizado:

- `Capability`, `Effect`, `Rule`, `Subject`, `Resource`, `Decision` y
  `PermissionEvaluator` en `core/permissions.py`;
- `policy.yaml` leído **antes** del LLM, con fallback a `DENY` total y
  aviso en auditoría y chat;
- techo del sistema derivado de `permissions.read/write/shell`;
- ámbito por `tools` (glob), `paths` y `namespaces` (prefijos);
- `ASK` con `ConsoleConfirmation` (`lo faccio? (y/N)`, default N);
- aplicación en `ToolRegistry.execute` y auditoría de
  `permission.decision` / `permission.confirmation`;
- `ToolDefinition.capabilities` para todas las herramientas (sistema de archivos y MCP);
- `requires_confirmation` aplicado como suelo de ASK;
- 347 test recogidos, 1 skip.

## 4.2 Queda por hacer

- `ConfirmationProvider` para la GUI (diálogo modal) y para la ejecución
  no interactiva (deny por defecto);
- políticas dinámicas por tarea/rol, con solo reducción en runtime (un
  agente puede reducirse los permisos, nunca ampliarlos por sí solo);
- capability de las herramientas MCP asignadas por la configuración, no
  declaradas por el servidor;
- varios sujetos en ejecución simultánea (varios agentes con políticas
  distintas);
- objetos-recurso para memoria y rutas, no solo herramientas.

---

# 5. Prioridad 4 — AIsh

Shell dedicada a los LLM, conceptualmente similar a Bash pero sin ningún
acceso a la shell real:

- ninguna ejecución de comandos del host;
- uso exclusivo de herramientas registradas;
- sistema de archivos simulado y rutas virtuales (`workspace://`);
- integración con herramientas MCP;
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
  RFC 9728/8414, dynamic registration, caché de tokens, refresh y retry 401.
- **Auditoría**: rotación a `max_bytes`, cadena de hash verificable con
  `verify_chain`, redacción de la salida de las herramientas con
  `include_outputs: false`.
- **Retención de auditoría**: copias de seguridad con marca de tiempo y `audit.max_files` (default
  100, incluye el archivo activo) con pruning de los más antiguos.
- **Test live**: marcador `live`, excluidos por defecto, `--live` para Ollama
  y proveedores remotos (estos últimos omitidos si no hay clave).
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

- búsqueda semántica en el Vault (índice y, luego, eventualmente ChromaDB);
- RAG sobre los documentos;
- gestión de tareas y scratchpad persistente;
- observación del vault (notas modificadas por el usuario);
- agente personal permanente;
- proveedores adicionales (OpenAI es casi gratis: el mismo cliente que DeepSeek
  con una base URL distinta).

---

# 8. Orden de trabajo

1. Memoria v2: hecha (ciclo de vida, revisión por CLI, inyección de confirmadas);
   quedan retención de chat, búsqueda semántica y GUI.
2. PermissionEvaluator: v1 hecha; quedan confirmaciones GUI y políticas
   dinámicas.
3. Higiene: hecha (packaging, test live, MCP auth/OAuth, auditoría con
   retención, base URL, legacy).
4. Calling nativo: v1 hecha; queda la medición con el benchmark.
5. Release 0.3.0: preparada para GitHub, con CI multiplataforma y
   workflow de release.

---

# 9. Herramientas locales

Estado al 2026-11-05:

- filesystem v2: `list_dir`, `read_chunk`, `rename`, `copy_file`,
  `search`, además de las herramientas existentes;
- `local_tools/`: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `feed.read` (proveedores locales, no servidores MCP);
- capability `COMPUTE` siempre en el techo, `NETWORK` controlada por
  `permissions.network` y por la política (feed en `ask`);
- límites de escritura: `max_write_bytes`, `min_free_bytes`,
  `session_write_bytes` y `ask_over_bytes` con un único preflight;
- `feed.read` con política SSRF: solo direcciones globales, redirects
  revalidados, nada de credenciales en la URL;
- sistema de archivos con raíz virtual `/home/ai`, alias obligatorios y
  permisos por mount (`R`/`W`/`X`);
- runner POSIX `tools/run_tests.sh` junto al de Windows.

Puntos abiertos:

- DNS rebinding: la resolución se valida, pero `requests` resuelve
  de nuevo el nombre en el momento de la conexión; hace falta un resolver
  fijado (pinned) o un adapter dedicado para cerrar el caso;
- la calculadora está voluntariamente limitada (nada de álgebra simbólica);
- valorar un límite de tamaño también para las demás salidas de las herramientas.

Cerrado como responsabilidad del usuario:

- los hard links, los mounts y las junctions dentro de los directorios allowed no están
  controlados por Hagar. Para un aislamiento total el usuario debe garantizar
  que no los haya; Hagar no los crea ni los detecta;
- race TOCTOU: Hagar no usa `openat2`, `O_NOFOLLOW` en cada componente ni
  handles de Windows y no garantiza atomicidad entre check y operación. La
  race requiere un proceso local concurrente con acceso de escritura;
  es un escenario malicioso o de entorno comprometido, no uso normal.
  Para un aislamiento total hacen falta un volumen dedicado, un usuario separado, un mount
  namespace o un contenedor.
