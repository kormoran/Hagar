# HAGAR — Changelog

El formato es libre pero estable: versiones en orden decreciente, con
referencia al commit cuando es útil.

---

# 0.5.2 — 2026-11-08

## Resumen

Release de consolidación: memoria SQLite, subagentes, vision, tool
de decisión, fichas de modelo, import/export Markdown e input broker CLI.

## Breaking change

- la memoria predeterminada ya no es el Vault Markdown: usa
  `%LOCALAPPDATA%/Hagar/memory.db` o `HAGAR_MEMORY_DB`;
- el Vault no se importa automáticamente;
- el backend `markdown` sigue disponible solo como legacy;
- `memory.database` y `decisions.*` son nuevas secciones de configuración.

## Nuevos backends LLM

- Nuevo backend `lmstudio` para el servidor local compatible con OpenAI de
  LM Studio, default `http://localhost:1234/v1`, sin clave salvo
  configuración del servidor.
- Nuevo backend `openai` (alias `chatgpt`) para la API OpenAI Chat
  Completions, clave `OPENAI_API_KEY`, base URL configurable.
- Los dos backends comparten el cliente compatible con OpenAI, con native
  tool calling y fallback JSON textual en HTTP 400/404/422.
- `model.timeout` configurable (default 120 s) y pasado a todos los
  backends; útil para modelos locales grandes.
- `hagar.example.yaml` y la documentación italiana actualizados.

## Service layer

- Nuevo `core/service.py` con `HarnessService`: turnos, estado, proyecto,
  fin de sesión y eventos estructurados (`ServiceEvent`).
- `hagar.py` usa el service para `ask`, selección de proyecto y cierre de
  sesión; la CLI sigue siendo un adapter.
- Eventos `tool.call`, `tool.result`, `permission.decision` y
  `permission.confirmation` reenviados por `Agent` y `ToolRegistry` al
  sink del service; el output de los tool se trunca en los eventos.
- Nuevo `CommandService` para `/help`, `/tools`, `/status`, `/mcp`,
  `/audit`, `/project` y `/memory`, con `CommandResult` estructurado.
- La CLI usa el command service para los comandos slash; `/memory review`
  sigue siendo interactivo.
- Nuevo `QueueConfirmationProvider`: confirmaciones ASK desde la GUI con cola,
  timeout y rechazo explícito.
- Nueva GUI web local (`hagar web`): chat, eventos SSE, estado, proyectos,
  tool call y modal de confirmación; token local y bind `127.0.0.1`.
- Las desconexiones SSE del navegador ya no producen traceback en
  Windows (`ConnectionAbortedError`/WinError 10053).
- Ctrl-C cierra de inmediato `hagar web`: nada de `shutdown()` desde el hilo de
  `serve_forever`, nada de join de los hilos SSE y summary omitido al
  apagado.
- Nuevo `core/usage.py`: parsing de usage OpenAI/DeepSeek/LM Studio,
  Claude, Gemini y Ollama, con `UsageLedger` por sesión.
- La GUI muestra input, output y total de tokens en la barra lateral, actualizados
  vía evento `usage.updated`.
- HTML, CSS y JavaScript de la GUI separados en `web/` y servidos como
  assets estáticos; `core/web.py` inyecta solo el token.
- Nuevo `memory/index.py`: índice SQLite/FTS5 incremental y
  reconstruible de las memorias Markdown, con fallback léxico.
- Nuevo tool `memory.search`; comandos `/memory search`, `reindex`,
  `stats`.
- Stop cooperativo del turno (`Agent.cancel`, `POST /api/stop`) con
  botón en la GUI y evento `turn.cancelled`.
- Entrada de imágenes vision (`core/images.py`) con validación de data URL,
  MIME y límite 10 MB; adapter OpenAI/LM Studio, Claude y Gemini.
- Subida de imágenes en la GUI con vista previa y eliminación; WebP convertido
  a PNG antes del envío. Ninguna imagen guardada en memoria o auditoría.
- Body JSON de la GUI hasta 64 MB, para aceptar imágenes de alta
  resolución en base64.
- Historial de chat en la pestaña dedicada: lista de `chat/` y
  `archive/chat/`; un clic reanuda la misma sesión y los nuevos turnos
  continúan el transcript.
- Botón **+ Nuova chat** con `MemoryStore.new_session()` y reset del
  contexto; los transcript anteriores quedan en el Vault.
- Pestañas GUI: Chat, Chat history, Tool output, Audit, Thinking, Memories.
- `SessionLog` en memoria para tool call/resultados y timeline;
  `/api/tools`, `/api/audit`, `/api/thinking`.
- Navegador de memorias de solo lectura: `/api/memories`, `/api/memory`.
- `/usage` en la CLI para los tokens acumulados de la sesión; mismo ledger
  usado por la GUI.
- Tool y proveedores LLM son plugin: built-in en `local_tools/plugins.py`
  y `llm/plugins.py`, externos vía entry point `hagar.tools`/`hagar.llm`.
- Errores de los plugins aislados y registrados en la auditoría; policy y sandbox
  permanecen en el host.
- Documentado el diseño del document tool en `DOCUMENT_TOOL.md`:
  grafo estructura/semántica, CSV MVP, contrato `FormatPlugin`, ABI C y
  protocolo JSON del host nativo.
- Subagentes asíncronos: `agent.spawn/status/wait/result/cancel`, hasta
  dos hijos concurrentes, cliente LLM separado, workspace privado con input
  copiados, registry de solo lectura, memoria sin escrituras, confirmaciones denegadas,
  usage y auditoría dedicados; cleanup al final del turno.
- `reason` obligatorio en el spawn y capability `AGENT_SPAWN` separada:
  el hijo no puede crear otros; `permissions.agents` controla el
  techo del sistema.
- Policy del subagente estrictamente más restrictiva que la del padre; policy
  iguales o no más limitadas se rechazan.
- Timeout de reloj de 5 minutos por subagente, cooperativo, con estado
  `timed_out`; `agent_id` en todos los eventos de auditoría.
- ASK de los subagentes reenviadas al usuario con `ParentBridgeConfirmation`,
  timeout 180 segundos y DENY al expirar; el padre LLM no aprueba.
- `vision.open` carga PNG/JPEG/WebP desde la sandbox y los adjunta al turno;
  `ToolResult.images` y el ciclo Agent gestionan el canal multimodal
  sin base64 en el texto. Audio en el roadmap.
- Memoria SQLite como fuente primaria: `memory/sqlite_store.py`,
  `memory/database.py`, WAL y backup; comandos `/memory sessions`,
  `/memory chat` y `/memory backup`. Proyectos y decisiones en la misma
  base de datos; backend Markdown solo legacy.
- Export Markdown de la base de datos con `/memory export <path> [--force]`:
  chat, skill, summary, proyectos y decisiones, escritura atómica.
- Import Markdown con `/memory import <path> [--force]`; FTS5 en la
  base de datos primaria con `bm25`/`snippet` y fallback `LIKE`.
- CLI con `ConsoleInputBroker`: un solo lector de consola, título de
  atención y confirmaciones ASK con `F5` allow / `F8` deny; fallback `y/N`.
  El broker guarda y restablece el terminal, también en Ctrl-C.
- Nueva clase de tool `decision.*` con `decision.choose`: proveedor LLM
  local/remoto y clasificador lineal local, probabilidades validadas,
  auditoría `decision.result` y capability `DECISION`.
- Fichas técnicas de los modelos y benchmark: `/models list|show|test|hardware`,
  latencia, JSON, tool calling, fecha de la última prueba y detección de
  CPU/RAM/GPU sin dependencias obligatorias.
- Artifact store temporal y mailbox interna: `artifact.put`,
  `artifact.put_file`, `mailbox.send` para el hijo; `artifact.read`,
  `artifact.list`, `mailbox.inbox/read/ack` para el padre. Capability
  `AGENT_DATA`, cuotas y cleanup al final del turno.
- `artifact.save_to` copia el artifact entero a una ruta escribible de la
  sandbox del padre; requiere `AGENT_DATA`, `FILESYSTEM_WRITE` y
  `FILESYSTEM_CREATE`, con eventual confirmación de policy.
- Auditoría `artifact.discarded` al final del turno para los artifact no exportados,
  con motivo `unread` o `read_but_not_saved`; la persistencia sigue
  aplazada.
- Auditoría desactivada: pestaña deshabilitada con etiqueta `audit off`.
- Thinking muestra el reasoning expuesto por el proveedor, en su defecto la
  timeline de los eventos.
- Base para la futura GUI, sin `input()` ni `print()` en el service.

# 0.3.0 — 2026-11-05

## Memoria de proyecto, summary y archivo

- Nueva memoria de proyecto separada de las skill:
  `Hagar/projects/<id>/index.md` y `decisions/<data>-<slug>.md`, con
  estado `candidate`/`active`/`superseded`/`archived`, alternativas,
  motivación, provenance y `auto_saved`.
- Al inicio Hagar muestra los proyectos activos y "actividad libre"; comandos
  `/project list|new|select|free|status` y override `--project`/`--free`.
- Al final de la sesión el transcript se traslada a `archive/chat/` y
  se sustituye por un summary con enlace y hash; fallback mecánico si el
  modelo no está disponible.
- Las decisiones de proyecto se proponen como `candidate` y se revisan
  al final de la sesión; si el usuario rechaza, quedan candidate con
  `auto_saved: true`.
- Contexto de índice: summary y títulos de las decisiones activas, no los
  cuerpos; detalles con `memory.project_context`. Presupuesto
  `max_context_chars` (caracteres, no tokens) y auditoría
  `memory.context_trimmed`.
- `project_max_active` dispara la petición de archivado del
  proyecto; el archivado es reversible y no borra nada.
- Si el directorio `projects` no es escribible, la memoria sigue activa
  y los proyectos se deshabilitan con `project.disabled`.
- Consulta del archivo: `memory.archive_search` y
  `memory.archive_read`, comandos `/memory archive search|read`, con
  filtro por proyecto y transcript que conserva `project` en el
  frontmatter. El archivo nunca se inyecta automáticamente.

## Comandos de consola y manual

- Nuevos comandos de chat: `/help`, `/tools [categoría]`, `/status`, `/mcp`,
  `/audit [n]`.
- `/tools` agrupa los tool por categoría y muestra las capability.
- `/status` informa de modelo, calling, proyecto, memoria, auditoría y
  filesystem.
- `/mcp` enumera servidores configurados, endpoints y tool importados.
- `/audit` lee los últimos eventos del log actual, sin exponer los
  campos no seleccionados.
- Los comandos `/` desconocidos no se envían al modelo.
- Nuevo `Docs/it/MANUAL.md` con comandos, CLI, `hagar.yaml`,
  `policy.yaml`, default y comportamientos en caso de error.

## MCP, OAuth y salida limpia

- Cliente MCP actualizado a `MCP-Protocol-Version` `2025-06-18` con
  fallback, reutilización de `Mcp-Session-Id` y cuerpo HTTP en los errores.
- OAuth: `audience` opcional, `prompt=consent` con `offline_access`,
  callback `http://localhost:<port>/oauth/callback`, scope en la
  dynamic registration.
- Ctrl-C durante OAuth o un turno cierra el callback local y sale con
  código 130, sin traceback.

## Instrumentos locales y filesystem v2

- Nuevo directorio `local_tools/` para los proveedores locales: cálculo, estadística,
  conversión de unidades, hora/fecha y feed. No son servidores MCP: registran
  `ToolDefinition` en el registry.
- Tool añadidos: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `clock.now`, `calendar.date`, `think.echo`,
  `text.diff`, `url.parse`, `feed.read`.
- Filesystem: `list_dir`, `read_chunk`, `rename`, `copy_file`, `search`.
- Nuevas capability `COMPUTE` (cálculos locales, siempre en el techo) y
  `NETWORK` (habilitada por `permissions.network: true`); `feed.read`
  requiere `NETWORK`.
- `permissions.network` en configuración; policy: `COMPUTE` allow para
  calculator/statistics/units, `NETWORK` ask para feed.
- `feedparser` entre las dependencias; el feed se descarga con
  `requests`, timeout y límite de 5 MB, y solo desde URL http/https.
- SSRF: resolución DNS obligatoria, solo direcciones globales
  (nada de loopback, redes privadas, link-local, multicast o reservadas),
  redirect manuales revalidados (máximo 3) y rechazo de las URL con
  credenciales.
- Restaurado el permiso `rename` de la sandbox, perdido durante
  la extensión; `filesystem.rename` requiere `rename` en el origen y
  `create` en el destino.
- Renombrado `MCP_tools/` → `local_tools/`: son proveedores locales, no
  servidores MCP; package, import, test y documentación actualizados.
- Filesystem con raíz virtual `/home/ai`: `stat`, `list_dir`,
  `search`, `read_chunk` y los mensajes de los tool ya no exponen la
  ruta física; las entradas `/home/ai/...` se aceptan.
- `read_chunk` alinea los límites con los caracteres UTF-8 y devuelve
  `next_offset`; ya no parte caracteres multibyte.
- `read_file` rechaza archivos de más de 4096 bytes y remite a `read_chunk()`
  para evitar cargar todo el archivo en la context window.
- `list_dir` devuelve como máximo 100 entradas por página y `search` 100
  resultados (máximo 500); ambos admiten `offset`, `next_offset`,
  `has_more` y el mensaje
  `voci: riportate X di Y; per continuare usa offset=Z`. Para árboles
  grandes conviene restringir pattern/path en lugar de iterar páginas.
- Nuevos límites de escritura `filesystem.limits`:
  `max_write_bytes` por operación, `min_free_bytes` como reserva,
  `session_write_bytes` acumulado y `ask_over_bytes` para la confirmación.
  Los tres primeros son invariantes; `ask_over_bytes` pasa por el preflight de
  `ToolRegistry` y pregunta una sola vez, aunque la policy sea `ASK`.
- Los symlink no existen para la sandbox: no se muestran, leen,
  siguen ni borran; `chdir` sobre un enlace responde
  "Directory not found". Decisión de proyecto: siguen invisibles
  aunque el sistema de archivos anfitrión los admita.
- Hard link, mount y junction dentro de los directorios allowed no están
  controlados ni detectados por Hagar. No es un defecto: un hard link es un
  segundo nombre del mismo inode y un mount puede exponer otro
  sistema de archivos permaneciendo dentro del prefijo. Los tool de filesystem no crean
  hard link. Para aislamiento total el usuario debe garantizar que en los
  directorios de la sandbox no los haya. Responsabilidad del usuario,
  punto cerrado.
- TOCTOU: esta versión no usa `openat2`, `O_NOFOLLOW` en cada
  componente ni handle de Windows, por lo que no garantiza atomicidad entre check
  y operación. La race requiere un proceso local concurrente con
  acceso de escritura: escenario malicioso o entorno comprometido, no
  uso normal. Cerrado como responsabilidad del usuario; para aislamiento
  total hacen falta volumen dedicado, usuario separado, mount namespace o
  contenedor.
- `filesystem.allowed` sustituido por `filesystem.sandbox`: cada entrada tiene
  `alias`, `path` y permisos `R`/`W`/`X`. El agente ve
  `/home/ai/<alias>/...`; nada de `hdN`, nada de volúmenes o directorios
  intermedios sintéticos. `/home/ai` enumera los alias pero no es un mount.
- Permisos por alias: `R` lectura/listado/búsqueda/stat, `W`
  escritura/creación/renombrado/copia/borrado, `X` `chdir`; los
  permisos globales siguen siendo un techo.
- Alias obligatorio, un solo segmento, único sin distinguir mayúsculas, sin
  nombres reservados de Windows; las entradas de la sandbox siguen siendo rutas del sistema
  anfitrión y Hagar no crea directorios. Las rutas físicas y los nombres internos
  pueden contener espacios; el alias no.
- Runner POSIX `tools/run_tests.sh`; `run_tests.ps1` y el shim siguen
  específicos de la sandbox de Windows. Actualizados los comandos de benchmark.
- Fix multiplataforma desde la CI: `vault_subdir` rechaza también las rutas con
  drive de Windows (`I:/...`) en POSIX; el rechazo de los symlink ya no es
  engullido por `except OSError`, por lo que la ruta no se resuelve
  fuera de la sandbox.
- 832 test superados, 2 skip en Windows; 834 superados, 0 skip en Debian
  Linux (2026-11-06), incluidos los test de symlink.

## Release y multiplataforma

- Versión `0.3.0` en `pyproject.toml` y `hagar.py`.
- CI GitHub Actions en Linux, macOS y Windows con Python 3.11, 3.12 y
  3.13; build del paquete, `twine check` y smoke test del wheel.
- Action actualizadas a `checkout@v7`, `setup-python@v7` y
  `upload-artifact@v7`, todas en Node 24; eliminado el warning de
  deprecación de Node 20.
- Workflow de release sobre tag `v*`: build sdist/wheel, verificación de que el tag
  corresponde a la versión y creación de la release de GitHub.
- `hagar.example.yaml` portátil; `hagar.yaml` local y `testvault/` están
  ignorados por git.
- `MANIFEST.in`, `SECURITY.md`, `CONTRIBUTING.md` y `RELEASING.md` para el
  primer lanzamiento público.

# 0.2.0 — 2026-11-04

Primera release con memoria revisable, calling nativo, MCP auth/OAuth,
retention de la auditoría y packaging instalable.

## Memoria v2

- Ciclo de vida `candidate` → `confirmed` → `archived`: el LLM propone,
  el usuario promueve desde la CLI.
- Comandos `/memory list`, `/memory show`, `/memory review`,
  `/memory confirm`, `/memory archive`.
- Inyección automática de las solas skill confirmadas, hasta
  `memory.context_skills` (default 3), por coincidencia léxica; las candidate
  y las archivadas quedan fuera.
- `reviewed_at` en el frontmatter; eventos de auditoría `memory.review` y
  `memory.status`.
- Retention opción A: ningún borrado automático; `archive` es
  reversible con `confirm`.
- `memory.context_skills` en configuración; 552 test superados, 1 skip.

## MCP OAuth interactivo

- Flujo authorization code + PKCE con callback en `127.0.0.1` y
  apertura del navegador; fallback manual pegando la URL.
- Discovery RFC 9728 (protected resource) y RFC 8414 (authorization
  server), con registro dinámico del cliente si falta `client_id`.
- Cache de token local con permisos `0600`, refresh automático y retry una
  vez en `401`.
- Config `auth.type: oauth` con `authorization_server`, `client_id`,
  `client_secret_env`, `scopes`, `redirect_port`, `token_cache`,
  `timeout`.
- Límites: nada de device flow, DPoP, mTLS o client assertion.
- 522 test superados, 1 skip.

## Audit retention

- Rotación en `<file>.<timestamp>` por encima de `audit.max_bytes`.
- `audit.max_files` (default 100) limita el número de archivos de auditoría,
  incluido el activo; las copias más antiguas se eliminan.
- La cadena de hash continúa desde el backup más reciente si falta
  el archivo activo.
- 504 test superados, 1 skip.

## MCP auth

- `mcp_servers[].auth`: `type: bearer` o bien `type: header`, con
  `token_env` y, para el header, el nombre del header.
- El token se lee solo del entorno: no va en el YAML, en la auditoría ni
  en los log.
- Token ausente o no ASCII: el servidor se omite con `mcp.failed` y
  el harness continúa con los demás.
- 496 test superados, 1 skip.

## Benchmark nativo vs texto

- `tools/bench_native.py`: 9 task de filesystem sobre el mismo registry,
  comparación entre `native_step()` y `request_tool_call()`, con precisión,
  latencia y reparaciones.
- Primeras mediciones: `llama3.1` 4/5 vs 5/5, `qwen3:8b` 4/5 vs 5/5,
  `hermes3:8b` 4/5 vs 3/5, `deepseek-flash` 8/9 vs 9/9 (subset Ollama,
  suite completa DeepSeek).
- Ningún vencedor universal: el default sigue siendo nativo, con opt-out por
  modelo mediante `model.native_tools` o `--no-native-tools`.

## DeepSeek (live)

- Modelos actualizados: `deepseek-flash` (default) y `deepseek-v4-pro`;
  `deepseek-chat` ya no es válido.
- Mensajes de error con el cuerpo de la respuesta de la API; claves no ASCII
  rechazadas con `ConfigError`.
- Nombres de los tool normalizados para las API que no admiten el punto
  (`filesystem.read_file` → `filesystem__read_file`), con retorno al
  nombre interno.
- `tools/diagnose_deepseek.py` para red, forma de la clave y endpoint,
  sin imprimir la clave.
- Test live: chat, calling nativo y end-to-end sobre el filesystem.
- 479 test superados, 1 skip; 9 test live con `--live`.

## Calling nativo (v1)

- `LLMClient.native_step()` y `LLMReply`: calling nativo para Ollama,
  DeepSeek, Claude y Gemini; esquema de los parámetros desde `ToolDefinition`.
- Mensajes canónicos `assistant` con `tool_calls` y `tool` con
  `tool_call_id`; cada backend los traduce (`tool_calls`, `tool_use`/
  `tool_result`, `functionCall`/`functionResponse`).
- El Agent ejecuta varias llamadas por turno, dentro del límite `max_tool_calls`.
- Fallback automático al protocolo textual en HTTP 400/404/422 en el primer
  paso, con evento `llm.native_fallback`; `model.native_tools: false` y
  `--no-native-tools` lo fuerzan.
- Auditoría: `turn.start` con `native`, `llm.tool_choice` con `mode=native`.
- 476 test superados, 1 skip; 7 test live con `--live`.

## Higiene (v1)

- **Packaging**: `pyproject.toml` completo (metadatos, dependencias,
  setuptools), entry point `hagar`, versión única (`hagar.__version__`);
  `pip install -e .` verificado.
- **CLI**: `--config`, `--model`, `--no-memory`, `--version`;
  configuración buscada en `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml`.
- **Test live**: marcador `live`, excluidos de la suite normal, `--live`
  para Ollama y proveedores remotos (skippados sin clave).
- **MCP**: respuestas `text/event-stream`, notificación
  `notifications/initialized`, normalización de los resultados a texto.
- **Auditoría**: cadena de hash (`prev`/`hash`, `verify_chain`), rotación a
  `max_bytes`, redacción del output de los tool con `include_outputs`.
- **URL base**: `model.host` usado por todos los proveedores.
- **Legacy**: eliminados `tools/filesystem.py` y `llm/tool_result.py`.
- 442 test superados, 1 skip; 6 test live con `--live`.

## Memoria (v1)

- `memory/store.py`: memoria episódica (una nota por sesión en
  `<vault>/Hagar/chat/`) y semántica
  (`<vault>/Hagar/skills/<slug>.md`);
- inyección automática de los últimos `memory.context_turns` turnos en el
  prompt, con truncamiento; un error de memoria no hace fallar el turno;
- tool `memory.create_skill` (provenance y estado `candidate`),
  `memory.list_skills`, `memory.get_context` (búsqueda por palabra clave);
- capability `MEMORY_READ`/`MEMORY_WRITE`, namespace `chat`/`skills` para
  las policy;
- configuración `memory.*` y desactivación con aviso si falta el
  vault;
- eventos de auditoría `memory.enabled`, `memory.disabled`, `memory.context`,
  `memory.turn`, `memory.failed`;

## Permisos (PermissionEvaluator v1)

- nuevo `core/permissions.py`: `Capability` (IntFlag), `Effect`
  (`ALLOW` / `ASK` / `DENY`, con deny-overrides), `Rule` con scope por
  tool, path y namespace, `Subject`, `Resource`, `Decision` y
  evaluator puro;
- `policy.yaml` separado, leído antes de construir el LLM: en caso de
  error todas las policy pasan a `DENY`, con evento `policy.failed` y
  warning en el chat;
- techo del sistema derivado de `permissions.read/write/shell`;
- `ASK` con confirmación desde consola (`lo faccio? (y/N)`, default N) y
  `ConfirmationProvider` para las futuras GUI;
- `ToolRegistry.execute` aplica la policy y registra
  `permission.decision` y `permission.confirmation`;
- `ToolDefinition.capabilities` para todos los tool (filesystem y MCP);
- `requires_confirmation` ahora aplicado como suelo de ASK;
- eliminado el stub incompleto `PolicyRule` de `core/models.py`;

## Filesystem v2, instrumentos matemáticos y feed

### Filesystem

- `filesystem.list_dir`: listado no recursivo del contenido de un directorio.
- `filesystem.list_dir` devuelve metadatos completos mediante `FileInfo` para cada elemento encontrado.
- `filesystem.read_chunk`: lectura incremental de archivos grandes mediante offset y longitud.
- `filesystem.read_chunk` opera a nivel de byte y devuelve `has_more` para permitir al agente continuar la lectura.
- `filesystem.rename`: renombra o mueve archivos dentro de la sandbox.
- `filesystem.copy_file`: copia archivos con verificación de los permisos y del espacio disponible.
- `filesystem.search`: búsqueda recursiva mediante patrón glob (`*.py`, `*.md`, etc.).
- `filesystem.search` devuelve:
  - número total de resultados encontrados;
  - número de resultados devueltos;
  - indicación de truncamiento (`truncated`);
  - lista de los resultados como `FileInfo`.
- Mejorada la exploración autónoma de la sandbox: el agente puede ahora enumerar directorios, buscar archivos y leer documentos muy grandes sin saturar la context window.

### Calculator

- Nueva clase `local_tools/calculator.py`.
- Parsing mediante AST seguro, sin uso de `eval()`.
- Soporte a:
  - `+`
  - `-`
  - `*`
  - `/`
  - `//`
  - `%`
  - `**`
  - paréntesis.
- Constantes matemáticas:
  - `pi`
  - `e`
- Funciones admitidas:
  - `sqrt`
  - `abs`
  - `sin`
  - `cos`
  - `tan`
  - `asin`
  - `acos`
  - `atan`
  - `log`
  - `log10`
  - `exp`
  - `floor`
  - `ceil`
  - `round`
- Nuevo tool MCP:

  `calculator.evaluate`

Todas las operaciones se validan mediante whitelist de nodos AST, operadores y funciones permitidas.

### Estadística

Nueva clase local_tools/statistics.py.

Nuevo tool MCP:

`statistics.compute`

La clase es `Stats_calc`; el tool expuesto al modelo es
`statistics.compute`. Operaciones admitidas:

- mean
- median
- stdev
- variance
- min
- max
- sum
- count

Resultados estructurados con:

- resultado de la operación;
- tipo de estadística solicitada;
- número de muestras procesadas;
- resultado o error.

### Conversión de unidades

Nueva clase `local_tools/unit_converter.py`.

Nuevo tool MCP:

`units.convert`

Soporte a las categorías:

Longitud

- mm
- cm
- m
- km

Masa

- mg
- g
- kg
- t

Tiempo

- ms
- s
- min
- hour
- day

Temperatura

- c
- f
- k

Ángulo

- deg
- rad

Dimensión de datos

- b
- kb
- mb
- gb
- tb

Sistema de alias y normalización de las unidades:

meters → m
kilometers → km
hours → hour
celsius → c
fahrenheit → f
degrees → deg
etc.

Conversiones dedicadas para:

temperatura (con offset);
ángulos (grados/radianes).

Conversiones lineales para todas las demás categorías.

### Feed RSS y Atom

Nueva clase `local_tools/feeder.py`.

Nuevo tool MCP:

`feed.read`

Soporte transparente a feed RSS y Atom mediante una única API.

Parámetro max_items con límite de seguridad para evitar output excesivos.

Extracción estructurada de:

- título;
- enlace;
- fecha de publicación;
- autor;
- sumario.

Limpieza automática del HTML presente en los feed y devolución de los metadatos del feed:

- título;
- descripción;
- enlace;
- tipo (rss, atom, etc.).

Devolución del número total de elementos disponibles, número de elementos devueltos e indicación de truncamiento.

### Notas

Esta iteración amplía de forma significativa las capacidades operativas del agente. Además del filesystem en sandbox, Hagar dispone ahora de instrumentos fiables para:

explorar y buscar contenidos;
leer archivos muy grandes de forma incremental;
ejecutar cálculos matemáticos deterministas;
realizar análisis estadísticos;
convertir unidades de medida pertenecientes a dominios diferentes;
consumir fuentes informativas estructuradas mediante feed RSS y Atom.

El objetivo sigue siendo privilegiar instrumentos deterministas, estructurados y fácilmente utilizables por los modelos mediante tool calling nativo.


## Documentación

- `PROJECT_STATE.md` dividido en `ARCHITECTURE.md` (cómo es el sistema),
  `ROADMAP.md` (qué hacer y decisiones tomadas) y este `CHANGELOG.md`.
- Roadmap actualizado con las decisiones del 2026-11-03: memoria sobre Vault,
  calling nativo de los tool, `PermissionEvaluator`.

---

# 0.2.0 — 2026-11-03 (en desarrollo)

Commit: `137c985` — *Debug, suite de test, audit log y backends múltiples*

## Añadido

- **Audit log** (`core/audit.py`): JSON Lines append-only con timestamp
  UTC, `session` y `turn` id. Eventos por sesión, turno, elección del
  tool, protocolo, ejecución, errores, MCP y proveedor. Escritura best
  effort, truncamiento configurable, ninguna clave API en el log.
- **Backends múltiples** (`llm/base.py`, `llm/factory.py`,
  `deepseek_client.py`, `claude_client.py`, `gemini_client.py`):
  `LLMClient` comparte selección de los tool, parsing y reparación del
  JSON; cada backend implementa solo el transporte y la conversión de los
  roles.
- **`filesystem.stat`**: tipo, tamaño en bytes, fechas ISO 8601 y
  permisos efectivos de la sandbox, en una sola medición.
- **Suite de test**: 259 test, 1 skip, sin red (Ollama y MCP
  simulados), con `tools/run_tests.ps1` y shim para la sandbox de Windows.
- **`tools/bench_models.py`**: comparación reproducible de los modelos
  Ollama en lectura, metadatos, creación y chat.

## Cambiado

- `model.provider` selecciona de verdad el backend (antes se ignoraba y se
  usaba siempre Ollama). Claves API del entorno, nunca del YAML.
- Modelo predeterminado: `llama3.1:latest` en lugar de `qwen3:8b`.
- Los resultados de los tool son turnos `user` y no `system`, por compatibilidad
  con los backends remotos.
- Errores de configuración: salida limpia (`SystemExit 1`) con mensaje
  en stderr y evento `llm.failed` en la auditoría.

## Corregido

- `core/filesystem.py` estaba truncado a mitad de `mkdir`: faltaban
  `read_file`, `write_file`, `create_file`, `delete_file`,
  `free_space`. Cada tool del filesystem fallaba con `AttributeError`.
- `ToolDefinition.origin` era obligatorio pero ningún proveedor lo pasaba:
  el registro de cualquier tool fallaba con `TypeError`.
- `ToolResult` usaba `tool` mientras el `Agent` usaba `tool_name`.
- `llm/ollama_client.py` usaba `re` sin importarlo y definía dos veces
  `_tool_call_from_json`.
- `hagar.py` leía campos inexistentes de `AppConfig`: `main()` no
  arrancaba.
- `ConfigLoader` no validaba YAML vacío, raíces no-mapping, permisos
  no booleanos, `allowed` no lista.
- `write_file` podía crear archivos nuevos eludiendo el permiso `create`.
- El parsing acepta el alias `parameters`; una respuesta en prosa produce
  un solo intento de reparación, después error explícito.

## Notas

Comparación de modelos Ollama (4 actividades, sandbox temporal, máx. 4 tool por
turno):

| modelo | read | stat | create | chat | reparaciones |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | loop, 4 tool | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | tool errato | file errato | contenuto errato | ok 6.4 s | 3 |

---

# 0.1.0 — 2026-11-02

Commit: `03b35bf` — *versione 0.1 alpha*

Primera versión realmente funcional: Hagar ya no es una interfaz
hacia Ollama, es un agente operativo.

## Añadido

- carga y validación de la configuración YAML;
- `OllamaClient` con `generate`, `chat`, `request_tool_call`;
- `ToolRegistry`, `ToolDefinition`, `ToolCall`, `ToolResult`;
- `Agent` con ciclo multi-step, gestión de errores y límite de los tool;
- `FileSystemSandbox` con raíces, permisos heredables, protección contra
  los symlink y control del espacio de disco;
- tool de filesystem: lectura, escritura, creación, borrado,
  creación de directorios, cambio de directorio, espacio libre;
- cliente MCP vía HTTP con descubrimiento automático de los tool y namespace;
- `Vault` inicial para los archivos Markdown.

## Notas

La v0.1 es la primera versión capaz de dialogar con un LLM local,
exponer instrumentos, hacer que el modelo elija cuáles usar, operar sobre un
filesystem en sandbox y encadenar varias operaciones de forma autónoma.
