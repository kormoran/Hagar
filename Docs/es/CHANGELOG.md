# HAGAR — Changelog

El formato es libre pero estable: versiones en orden decreciente, con
referencia al commit cuando es útil.

---

# 0.3.0 — 2026-11-05

## Memoria de proyecto, resumen y archivo

- Nueva memoria de proyecto separada de las skill:
  `Hagar/projects/<id>/index.md` y `decisions/<data>-<slug>.md`, con
  estado `candidate`/`active`/`superseded`/`archived`, alternativas,
  motivación, provenance y `auto_saved`.
- Al arrancar Hagar muestra los proyectos activos y "actividad libre"; comandos
  `/project list|new|select|free|status` y overrides `--project`/`--free`.
- Al final de la sesión el transcript se mueve a `archive/chat/` y
  se sustituye por un resumen con enlace y hash; fallback mecánico si el
  modelo no está disponible.
- Las decisiones de proyecto se proponen como `candidate` y se revisan
  al final de la sesión; si el usuario rechaza, siguen candidatas con
  `auto_saved: true`.
- Contexto por índice: resumen y títulos de las decisiones activas, no los
  cuerpos; detalles con `memory.project_context`. Presupuesto
  `max_context_chars` (caracteres, no tokens) y auditoría
  `memory.context_trimmed`.
- `project_max_active` dispara la solicitud de archivado del
  proyecto; el archivado es reversible y no borra nada.
- Si el directorio `projects` no es escribible, la memoria sigue activa
  y los proyectos se deshabilitan con `project.disabled`.
- Consulta del archivo: `memory.archive_search` y
  `memory.archive_read`, comandos `/memory archive search|read`, con
  filtro por proyecto y transcript que conserva `project` en el
  frontmatter. El archivo no se inyecta nunca automáticamente.

## Comandos de consola y manual

- Nuevos comandos de chat: `/help`, `/tools [categoría]`, `/status`, `/mcp`,
  `/audit [n]`.
- `/tools` agrupa las herramientas por categoría y muestra las capability.
- `/status` informa de modelo, calling, proyecto, memoria, auditoría y
  sistema de archivos.
- `/mcp` enumera servidores configurados, endpoint y herramientas importadas.
- `/audit` lee los últimos eventos del registro actual, sin exponer los
  campos no seleccionados.
- Los comandos `/` desconocidos no se envían al modelo.
- Nuevo `Docs/it/MANUAL.md` con comandos, CLI, `hagar.yaml`,
  `policy.yaml`, defaults y comportamientos en caso de error.

## MCP, OAuth y salida limpia

- Cliente MCP actualizado a `MCP-Protocol-Version` `2025-06-18` con
  fallback, reutilización de `Mcp-Session-Id` y cuerpo HTTP en los errores.
- OAuth: `audience` opcional, `prompt=consent` con `offline_access`,
  callback `http://localhost:<port>/oauth/callback`, scope en la
  dynamic registration.
- Ctrl-C durante OAuth o un turno cierra el callback local y sale con
  código 130, sin traceback.

## Herramientas locales y filesystem v2

- Nuevo directorio `local_tools/` para los proveedores locales: cálculo, estadística,
  conversión de unidades, hora/fecha y feed. No son servidores MCP: registran
  `ToolDefinition` en el registry.
- Herramientas añadidas: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `clock.now`, `calendar.date`, `think.echo`,
  `text.diff`, `url.parse`, `feed.read`.
- Filesystem: `list_dir`, `read_chunk`, `rename`, `copy_file`, `search`.
- Nuevas capability `COMPUTE` (cálculos locales, siempre en el techo) y
  `NETWORK` (habilitada por `permissions.network: true`); `feed.read`
  requiere `NETWORK`.
- `permissions.network` en la configuración; política: `COMPUTE` allow para
  calculator/statistics/units, `NETWORK` ask para feed.
- `feedparser` entre las dependencias; el feed se descarga con
  `requests`, timeout y límite de 5 MB, y solo desde URL http/https.
- SSRF: resolución DNS obligatoria, solo direcciones globales
  (nada de loopback, redes privadas, link-local, multicast o reservadas),
  redirects manuales revalidados (máximo 3) y rechazo de las URL con
  credenciales.
- Restaurado el permiso `rename` de la sandbox, perdido durante
  la extensión; `filesystem.rename` requiere `rename` en el origen y
  `create` en el destino.
- Renombrado `MCP_tools/` → `local_tools/`: son proveedores locales, no
  servidores MCP; paquete, import, test y documentación actualizados.
- Filesystem con raíz virtual `/home/ai`: `stat`, `list_dir`,
  `search`, `read_chunk` y los mensajes de las herramientas ya no exponen el
  path físico; las entradas `/home/ai/...` son aceptadas.
- `read_chunk` alinea los límites a los caracteres UTF-8 y devuelve
  `next_offset`; ya no parte caracteres multibyte.
- `read_file` rechaza archivos de más de 4096 bytes y remite a `read_chunk()`
  para evitar cargar todo el archivo en la context window.
- `list_dir` devuelve como máximo 100 entradas por página y `search` 100
  resultados (máximo 500); ambos soportan `offset`, `next_offset`,
  `has_more` y el mensaje
  `voci: riportate X di Y; per continuare usa offset=Z`. Para árboles
  grandes conviene restringir pattern/path en lugar de iterar páginas.
- Nuevos límites de escritura `filesystem.limits`:
  `max_write_bytes` por operación, `min_free_bytes` como reserva,
  `session_write_bytes` acumulado y `ask_over_bytes` para la confirmación.
  Los tres primeros son invariantes; `ask_over_bytes` pasa por el preflight de
  `ToolRegistry` y pide una sola vez, aunque la política sea `ASK`.
- Los symlink no existen para la sandbox: no se muestran, leen,
  siguen ni borran; `chdir` sobre un enlace responde
  "Directory not found". Decisión de proyecto: siguen invisibles
  aunque el sistema de archivos anfitrión los soporte.
- Los hard links, los mounts y las junctions dentro de los directorios allowed no están
  controlados ni detectados por Hagar. No es un defecto: un hard link es un
  segundo nombre del mismo inode y un mount puede exponer otro
  sistema de archivos permaneciendo dentro del prefijo. Las herramientas del sistema de archivos no crean
  hard links. Para un aislamiento total el usuario debe garantizar que en los
  directorios de la sandbox no los haya. Responsabilidad del usuario,
  punto cerrado.
- TOCTOU: esta versión no usa `openat2`, `O_NOFOLLOW` en cada
  componente ni handles de Windows, por lo que no garantiza atomicidad entre check
  y operación. La race requiere un proceso local concurrente con
  acceso de escritura: escenario malicioso o entorno comprometido, no
  uso normal. Cerrado como responsabilidad del usuario; para un aislamiento
  total hacen falta un volumen dedicado, un usuario separado, un mount namespace o
  un contenedor.
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
  unidad de Windows (`I:/...`) en POSIX; el rechazo de los symlink ya no se
  traga con `except OSError`, por lo que la ruta no se resuelve
  fuera de la sandbox.
- 691 test superados, 2 skip en Windows; 693 superados, 0 skip en Debian
  Linux (2026-11-06), incluidos los test de symlink.

## Publicación y multiplataforma

- Versión `0.3.0` en `pyproject.toml` y `hagar.py`.
- CI de GitHub Actions en Linux, macOS y Windows con Python 3.11, 3.12 y
  3.13; build del paquete, `twine check` y smoke test del wheel.
- Actions actualizadas a `checkout@v7`, `setup-python@v7` y
  `upload-artifact@v7`, todas sobre Node 24; eliminado el aviso de
  deprecación de Node 20.
- Workflow de release sobre tag `v*`: build sdist/wheel, verificación de que el tag
  corresponde a la versión y creación de la release de GitHub.
- `hagar.example.yaml` portable; `hagar.yaml` local y `testvault/` están
  ignorados por git.
- `MANIFEST.in`, `SECURITY.md`, `CONTRIBUTING.md` y `RELEASING.md` para el
  primer lanzamiento público.

# 0.2.0 — 2026-11-04

Primera release con memoria revisable, calling nativo, MCP auth/OAuth,
retención de la auditoría y packaging instalable.

## Memoria v2

- Ciclo de vida `candidate` → `confirmed` → `archived`: el LLM propone,
  el usuario promueve desde la CLI.
- Comandos `/memory list`, `/memory show`, `/memory review`,
  `/memory confirm`, `/memory archive`.
- Inyección automática de las únicas skill confirmadas, hasta
  `memory.context_skills` (default 3), por match léxico; las candidatas
  y las archivadas quedan fuera.
- `reviewed_at` en el frontmatter; eventos de auditoría `memory.review` y
  `memory.status`.
- Retención opción A: ningún borrado automático; `archive` es
  reversible con `confirm`.
- `memory.context_skills` en la configuración; 552 test superados, 1 skip.

## MCP OAuth interactivo

- Flujo authorization code + PKCE con callback en `127.0.0.1` y
  apertura del navegador; fallback manual pegando la URL.
- Discovery RFC 9728 (protected resource) y RFC 8414 (authorization
  server), con registración dinámica del cliente si falta `client_id`.
- Caché de tokens local con permisos `0600`, refresh automático y retry una
  vez ante `401`.
- Config `auth.type: oauth` con `authorization_server`, `client_id`,
  `client_secret_env`, `scopes`, `redirect_port`, `token_cache`,
  `timeout`.
- Límites: nada de device flow, DPoP, mTLS ni client assertion.
- 522 test superados, 1 skip.

## Retención de auditoría

- Rotación en `<file>.<timestamp>` por encima de `audit.max_bytes`.
- `audit.max_files` (default 100) limita el número de archivos de auditoría,
  incluido el activo; las copias de seguridad más antiguas se eliminan.
- La cadena de hash continúa desde la copia de seguridad más reciente si falta el archivo
  activo.
- 504 test superados, 1 skip.

## MCP auth

- `mcp_servers[].auth`: `type: bearer` o `type: header`, con
  `token_env` y, para el header, el nombre del header.
- El token se lee solo del entorno: no va en el YAML, en la auditoría ni
  en los registros.
- Token ausente o no ASCII: el servidor se omite con `mcp.failed` y
  el harness continúa con los demás.
- 496 test superados, 1 skip.

## Benchmark nativo vs texto

- `tools/bench_native.py`: 9 tareas de sistema de archivos sobre el mismo registry,
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
- Mensajes de error con el cuerpo de la respuesta API; claves no ASCII
  rechazadas con `ConfigError`.
- Nombres de las herramientas normalizados para las API que no admiten el punto
  (`filesystem.read_file` → `filesystem__read_file`), con vuelta al
  nombre interno.
- `tools/diagnose_deepseek.py` para red, forma de la clave y endpoint,
  sin imprimir la clave.
- Test live: chat, calling nativo y end-to-end sobre el sistema de archivos.
- 479 test superados, 1 skip; 9 test live con `--live`.

## Calling nativo (v1)

- `LLMClient.native_step()` y `LLMReply`: calling nativo para Ollama,
  DeepSeek, Claude y Gemini; esquema de los parámetros desde `ToolDefinition`.
- Mensajes canónicos `assistant` con `tool_calls` y `tool` con
  `tool_call_id`; cada backend los traduce (`tool_calls`, `tool_use`/
  `tool_result`, `functionCall`/`functionResponse`).
- El Agent ejecuta varias llamadas por turno, dentro del límite `max_tool_calls`.
- Fallback automático al protocolo textual ante HTTP 400/404/422 en el primer
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
  para Ollama y proveedores remotos (omitidos si no hay clave).
- **MCP**: respuestas `text/event-stream`, notificación
  `notifications/initialized`, normalización de los resultados a texto.
- **Auditoría**: cadena de hash (`prev`/`hash`, `verify_chain`), rotación a
  `max_bytes`, redacción de la salida de las herramientas con `include_outputs`.
- **URL base**: `model.host` usado por todos los proveedores.
- **Legacy**: eliminados `tools/filesystem.py` y `llm/tool_result.py`.
- 442 test superados, 1 skip; 6 test live con `--live`.

## Memoria (v1)

- `memory/store.py`: memoria episódica (una nota por sesión en
  `<vault>/Hagar/chat/`) y semántica
  (`<vault>/Hagar/skills/<slug>.md`);
- inyección automática de los últimos `memory.context_turns` turnos en el
  prompt, con truncado; un error de memoria no hace fallar el turno;
- herramientas `memory.create_skill` (provenance y estado `candidate`),
  `memory.list_skills`, `memory.get_context` (búsqueda por palabra clave);
- capability `MEMORY_READ`/`MEMORY_WRITE`, namespace `chat`/`skills` para
  las políticas;
- configuración `memory.*` y desactivación con aviso si falta el
  vault;
- eventos de auditoría `memory.enabled`, `memory.disabled`, `memory.context`,
  `memory.turn`, `memory.failed`;

## Permisos (PermissionEvaluator v1)

- nuevo `core/permissions.py`: `Capability` (IntFlag), `Effect`
  (`ALLOW` / `ASK` / `DENY`, con deny-overrides), `Rule` con ámbito por
  herramienta, ruta y namespace, `Subject`, `Resource`, `Decision` y
  evaluator puro;
- `policy.yaml` separado, leído antes de construir el LLM: en caso de
  error todas las políticas pasan a `DENY`, con evento `policy.failed` y
  aviso en el chat;
- techo del sistema derivado de `permissions.read/write/shell`;
- `ASK` con confirmación por consola (`lo faccio? (y/N)`, default N) y
  `ConfirmationProvider` para las futuras GUI;
- `ToolRegistry.execute` aplica la política y registra
  `permission.decision` y `permission.confirmation`;
- `ToolDefinition.capabilities` para todas las herramientas (sistema de archivos y MCP);
- `requires_confirmation` ahora aplicado como suelo de ASK;
- eliminado el stub incompleto `PolicyRule` de `core/models.py`;

## Filesystem v2, herramientas matemáticas y feed

### Filesystem

- `filesystem.list_dir`: listado no recursivo del contenido de un directorio.
- `filesystem.list_dir` devuelve metadatos completos mediante `FileInfo` para cada elemento encontrado.
- `filesystem.read_chunk`: lectura incremental de archivos de gran tamaño mediante offset y longitud.
- `filesystem.read_chunk` opera a nivel de bytes y devuelve `has_more` para permitir al agente continuar la lectura.
- `filesystem.rename`: renombra o mueve archivos dentro de la sandbox.
- `filesystem.copy_file`: copia archivos con verificación de los permisos y del espacio disponible.
- `filesystem.search`: búsqueda recursiva mediante pattern glob (`*.py`, `*.md`, etc.).
- `filesystem.search` devuelve:
  - número total de resultados encontrados;
  - número de resultados devueltos;
  - indicación de truncado (`truncated`);
  - lista de los resultados como `FileInfo`.
- Mejorada la exploración autónoma de la sandbox: el agente puede ahora enumerar directorios, buscar archivos y leer documentos muy grandes sin saturar la context window.

### Calculadora

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
- Funciones soportadas:
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
- Nueva herramienta MCP:

  `calculator.evaluate`
  
Todas las operaciones se validan mediante whitelist de nodos AST, operadores y funciones permitidas.

### Estadística

Nueva clase local_tools/statistics.py.

Nueva herramienta MCP:

`statistics.compute`

La clase es `Stats_calc`; la herramienta expuesta al modelo es
`statistics.compute`. Operaciones soportadas:

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

Nueva herramienta MCP:

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

Tamaño de datos

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

Nueva herramienta MCP:

`feed.read`

Soporte transparente a feeds RSS y Atom mediante una única API.

Parámetro max_items con límite de seguridad para evitar salidas excesivas.

Extracción estructurada de:

- título;
- enlace;
- fecha de publicación;
- autor;
- sumario.

Limpieza automática del HTML presente en los feeds y devolución de los metadatos del feed:

- título;
- descripción;
- enlace;
- tipo (rss, atom, etc.).

Devolución del número total de elementos disponibles, número de elementos devueltos e indicación de truncado.

### Notas

Esta iteración amplía de forma significativa las capacidades operativas del agente. Además del sistema de archivos en sandbox, Hagar dispone ahora de herramientas fiables para:

explorar y buscar contenidos;
leer archivos muy grandes de forma incremental;
ejecutar cálculos matemáticos deterministas;
efectuar análisis estadísticos;
convertir unidades de medida pertenecientes a dominios diferentes;
consumir fuentes informativas estructuradas mediante feeds RSS y Atom.

El objetivo sigue siendo privilegiar herramientas deterministas, estructuradas y fácilmente utilizables por los modelos mediante tool calling nativo.


## Documentación

- `PROJECT_STATE.md` dividido en `ARCHITECTURE.md` (cómo es el sistema),
  `ROADMAP.md` (qué hacer y decisiones tomadas) y este `CHANGELOG.md`.
- Roadmap actualizada con las decisiones del 2026-11-03: memoria sobre Vault,
  calling nativo de las herramientas, `PermissionEvaluator`.

---

# 0.2.0 — 2026-11-03 (en desarrollo)

Commit: `137c985` — *Depuración, suite de pruebas, registro de auditoría y backends múltiples*

## Añadido

- **Registro de auditoría** (`core/audit.py`): JSON Lines append-only con marca de tiempo
  UTC, `session` y `turn` id. Eventos por sesión, turno, elección de la
  herramienta, protocolo, ejecución, errores, MCP y proveedor. Escritura best
  effort, truncado configurable, ninguna clave API en el registro.
- **Backends múltiples** (`llm/base.py`, `llm/factory.py`,
  `deepseek_client.py`, `claude_client.py`, `gemini_client.py`):
  `LLMClient` comparte selección de las herramientas, parsing y reparación del
  JSON; cada backend implementa solo el transporte y la conversión de los
  roles.
- **`filesystem.stat`**: tipo, tamaño en bytes, fechas ISO 8601 y
  permisos efectivos de la sandbox, en una sola medida.
- **Suite de pruebas**: 259 test, 1 skip, sin red (Ollama y MCP
  simulados), con `tools/run_tests.ps1` y shim para la sandbox de Windows.
- **`tools/bench_models.py`**: comparación reproducible de los modelos
  Ollama en lectura, metadatos, creación y chat.

## Cambiado

- `model.provider` selecciona de verdad el backend (antes se ignoraba y se
  usaba siempre Ollama). Claves API del entorno, nunca del YAML.
- Modelo por defecto: `llama3.1:latest` en lugar de `qwen3:8b`.
- Los resultados de las herramientas son turnos `user` y no `system`, por compatibilidad
  con los backends remotos.
- Errores de configuración: salida limpia (`SystemExit 1`) con mensaje
  en stderr y evento `llm.failed` en la auditoría.

## Corregido

- `core/filesystem.py` estaba truncado a mitad de `mkdir`: faltaban
  `read_file`, `write_file`, `create_file`, `delete_file`,
  `free_space`. Cada herramienta del sistema de archivos fallaba con `AttributeError`.
- `ToolDefinition.origin` era obligatorio pero ningún proveedor lo pasaba:
  el registro de cualquier herramienta fallaba con `TypeError`.
- `ToolResult` usaba `tool` mientras el `Agent` usaba `tool_name`.
- `llm/ollama_client.py` usaba `re` sin importarlo y definía dos veces
  `_tool_call_from_json`.
- `hagar.py` leía campos inexistentes de `AppConfig`: `main()` no
  arrancaba.
- `ConfigLoader` no validaba YAML vacío, raíces no-mapping, permisos
  no booleanos, `allowed` no lista.
- `write_file` podía crear archivos nuevos eludiendo el permiso `create`.
- El parsing acepta el alias `parameters`; una respuesta en prosa produce
  un solo intento de reparación y después un error explícito.

## Notas

Comparación de modelos Ollama (4 tareas, sandbox temporal, máx. 4 herramientas por
turno):

| modelo | read | stat | create | chat | reparaciones |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | bucle, 4 herramientas | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | herramienta errónea | archivo erróneo | contenido erróneo | ok 6.4 s | 3 |

---

# 0.1.0 — 2026-11-02

Commit: `03b35bf` — *versión 0.1 alpha*

Primera versión realmente funcional: Hagar ya no es una interfaz
hacia Ollama, es un agente operativo.

## Añadido

- carga y validación de la configuración YAML;
- `OllamaClient` con `generate`, `chat`, `request_tool_call`;
- `ToolRegistry`, `ToolDefinition`, `ToolCall`, `ToolResult`;
- `Agent` con ciclo multi-step, gestión de errores y límite de herramientas;
- `FileSystemSandbox` con raíces, permisos heredables, protección frente a
  los symlink y control del espacio de disco;
- herramientas del sistema de archivos: lectura, escritura, creación, borrado,
  creación de directorios, cambio de directorio, espacio libre;
- cliente MCP vía HTTP con discovery automático de las herramientas y namespace;
- `Vault` inicial para los archivos Markdown.

## Notas

La v0.1 es la primera versión capaz de dialogar con un LLM local,
exponer herramientas, hacer que el modelo elija cuáles usar, operar sobre un
sistema de archivos en sandbox y encadenar varias operaciones de forma autónoma.
