# HAGAR — Arquitectura

Versión: 0.7.0
Última actualización: 2026-11-03

---

# 1. Qué es Hagar

Hagar es un harness para LLM escrito en Python, diseñado para la ejecución
resiliente de modelos lingüísticos.

El objetivo no es un chat con un modelo, sino un entorno operativo
**seguro** en el que un LLM pueda usar tool, consultar una memoria
persistente e interactuar con sistemas externos sin acceder directamente
a los recursos reales de la máquina anfitriona.

Con este fin el proyecto aplica principios de HMI/HCI y Cognitive
Ergonomics al diseño del entorno en el que opera el modelo.

## 1.1 Las Cuatro Leyes de HAGAR

**Primera ley — El LLM no es fiable por definición.**
No porque sea malo o inútil: porque es probabilístico. Toda afirmación suya
debe verificarse y toda acción suya debe limitarse.

**Segunda ley — Los tool son más fiables que el LLM.**
Si el sistema de archivos dice que un archivo existe, existe. Si el tool
devuelve un tamaño, ese tamaño es real. El LLM interpreta, los tool miden.

**Tercera ley — El estado debe existir fuera de la mente del LLM.**
ToolRegistry, MCP, FileSystemSandbox y (en perspectiva)
PermissionEvaluator trasladan conocimiento y control fuera del modelo,
como en los sistemas safety-critical.

**Cuarta ley — Toda acción debe poder explicarse después.**
El registro de auditoría responde a la pregunta correcta: no "¿por qué se
volvió loco el LLM?" sino "¿qué supuesto ha hecho?", "¿qué tool ha usado?",
"¿qué dato era erróneo?". Investigación de incidentes, como en aviación.

## 1.2 Prohibiciones absolutas

El modelo nunca debe:

- acceder directamente al sistema de archivos del anfitrión;
- ejecutar comandos en el shell real;
- obtener privilegios superiores a los definidos por la configuración;
- conocer la organización efectiva del sistema operativo.

Todas las operaciones pasan exclusivamente a través de tool registrados y
controlados por el harness.

## 1.3 Principios arquitectónicos

- separación entre modelo y sistema operativo;
- seguridad por defecto;
- arquitectura de plugins;
- independencia del proveedor LLM;
- extensibilidad mediante tool y protocolo MCP.

---

# 2. Arquitectura

```text
Usuario
  │
  ▼
Agent ──────────────── AuditLog (JSON Lines)
  │
  ├── LLMClient (llm/base.py)
  │     ├── OllamaClient
  │     ├── LMStudioClient
  │     ├── DeepSeekClient
  │     ├── OpenAIClient
  │     ├── ClaudeClient
  │     └── GeminiClient
  │
  ├── ToolRegistry
  │     ├── filesystem.*
  │     ├── memory.*        (planificado)
  │     └── mcp.*
  │
  ├── FileSystemSandbox
  │
  ├── MCPClient
  │
  └── Vault (Obsidian)
```

Flujo de ejecución:

```text
Usuario
  ↓
Agent              turn.start
  ↓
LLMClient          llm.tool_choice
  ↓
ToolCall
  ↓
ToolRegistry       tool.call
  ↓
ToolResult         tool.result
  ↓
LLMClient
  ↓
Respuesta final    turn.answer
```

---

# 3. Componentes

## 3.1 Config (`core/config.py`)

Carga y valida un archivo YAML (`hagar.yaml`) en un `AppConfig`.

Secciones:

| sección | obligatoria | contenido |
|---|---|---|
| `model` | sí | proveedor, nombre, host, timeout, max_tokens, api_key_env, native_tools |
| `vault` | sí | ruta del vault Obsidian |
| `filesystem` | sí | `sandbox`: lista de `{alias, path, permissions}`; `limits`: presupuesto de escritura |
| `permissions` | no | read, write, shell, network (default `true/false/false/false`) |
| `rag` | no | `top_k` (default 8) |
| `mcp_servers` | no | endpoint, namespace, auth (bearer/header/oauth) |
| `audit` | no | enabled, path, max_field_chars, max_bytes, max_files, include_outputs |
| `policy` | no | path del archivo policy, subject |
| `memory` | no | enabled, vault_subdir, context_turns, context_skills, max_skill_chars |

Los errores de validación producen siempre `ConfigError`, con un mensaje que
indica el campo. La ruta de la auditoría, si es relativa, se resuelve
respecto al archivo de configuración.

## 3.2 Interfaz LLM y backends (`llm/`)

`LLMClient` tiene dos rutas:

- **calling nativo** (predeterminado): `native_step()` envía los esquemas de
  los tool en el formato del proveedor y lee las llamadas de la respuesta;
- **protocolo JSON textual** (fallback): `request_tool_call()` pide un
  JSON con `tool`/`arguments`, con parsing robusto y un intento de
  reparación.

El esquema de los parámetros lo construye `ToolDefinition`:
OpenAI/Ollama usan `tools[].function`, Claude `tools[].input_schema`,
Gemini `functionDeclarations`. La conversación canónica usa los roles
`user`/`assistant`/`tool`; cada cliente la traduce (OpenAI `tool_calls`,
Claude bloques `tool_use`/`tool_result`, Gemini `functionCall`/
`functionResponse`). Un rechazo HTTP 400/404/422 produce
`NativeToolsUnavailable`: el Agent pasa al protocolo textual solo si no
ha ejecutado aún ningún tool.

Los nombres de los tool se normalizan para las API que no admiten el
punto (`filesystem.read_file` → `filesystem__read_file`) y se restituyen al
nombre interno en la respuesta: policy, auditoría y test ven siempre el nombre
original.

El texto sigue siendo el fallback para modelos que no admiten los tool nativos;
`model.native_tools: false` lo fuerza (o `--no-native-tools` desde la CLI).

| proveedor | API | clave | notas |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | host default `localhost:11434` |
| `lmstudio` | `/v1/chat/completions` (OpenAI) | opcional `LMSTUDIO_API_KEY` | host default `localhost:1234/v1` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `openai` / `chatgpt` | `/v1/chat/completions` | `OPENAI_API_KEY` | ChatGPT vía API, no suscripción |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system separado, turnos alternos |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, rol `model` |

La clave se lee solo del entorno; `model.api_key_env` sobrescribe el
nombre predeterminado. `model.host` es la URL base de todos los proveedores (con un
default por proveedor), `model.timeout` es el timeout HTTP (default 120),
`model.max_tokens` lo usa solo Claude.
`llm/factory.py` construye el cliente y rechaza proveedores desconocidos o
claves ausentes. Los proveedores built-in son spec en `llm/plugins.py`; un
proveedor externo se registra con el entry point `hagar.llm` y una factory
`(config, audit) -> LLMClient` (véase `PLUGINS.md`). LM Studio no
requiere clave salvo configuración del servidor; OpenAI requiere una
clave API, no una suscripción de ChatGPT.
DeepSeek: los modelos actuales son `deepseek-flash` y
`deepseek-v4-pro`; `deepseek-chat` ya no se acepta.

Estado actual: **calling nativo v1** con fallback textual automático
(véase ROADMAP).

## 3.3 Modelo de los tool (`core/tool_*.py`)

`ToolDefinition` describe nombre, descripción, categoría, parámetros,
handler, `origin` (`local` o `mcp.<namespace>`), las `capabilities`
declaradas, el estado de habilitación y `requires_confirmation`
(suelo de ASK aplicado por el registry).

`ToolCall` es la petición del modelo (`tool`, `arguments`, `id`);
`ToolResult` es el resultado estructurado (`tool_name`, `success`, `output`,
`error`).

`ToolRegistry` registra, busca, habilita/deshabilita y ejecuta los tool;
expone los metadatos al modelo y es el único punto de ejecución.

## 3.4 Agent (`core/agent.py`)

Ciclo agéntico multi-step, con dos rutas:

- **nativo**: una respuesta puede contener varias llamadas; el Agent reencola
  el mensaje `assistant` y un mensaje `tool` con el id de cada
  resultado;
- **textual**: una llamada por vez, con el resultado enviado como
  turno `user`.

En ambos:

1. el modelo decide si hace falta un tool;
2. si no hace falta, la respuesta final cierra el turno;
3. si hace falta, el tool se ejecuta y el resultado vuelve al modelo;
4. el límite `max_tool_calls` vale para todo el turno. Si el modelo
   insiste, el turno se cierra con `Agent stopped after N tool calls`
   (protección contra bucles).

Si el primer paso nativo falla con `NativeToolsUnavailable`, el Agent
pasa al protocolo textual (`llm.native_fallback`); un error después de que
se haya ejecutado un tool cierra el turno con `turn.error`, sin
fallback.

Cada paso se registra en la auditoría: pregunta, elección del tool, argumentos,
resultado, duración y respuesta final. Una auditoría rota no detiene al agente: el
fallo se señala en stderr.

El `Agent` recibe el `Vault` pero aún no lo usa.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

Sistema de archivos virtual del agente. Cada petición se:

1. resuelve contra el directorio actual (`resolve_path`);
2. verifica contra las raíces concedidas (`effective_permissions`);
3. filtra por los permisos efectivos, con las raíces más específicas que
   sobrescriben las más externas;
4. controla contra los symlink y el espacio de disco disponible
   (`FS_Guardian`, nombre heredado).

`DirectoryPermissions` modela `read`, `write`, `create`, `rename`,
`delete`, `execute`; `None` significa "hereda de la raíz externa".
Una ruta fuera de las raíces es siempre `PermissionError`.

`FileInfo` / `stat()` devuelven tipo, tamaño en bytes, fechas de
creación/modificación/acceso (ISO 8601 con offset local) y los permisos
**efectivos de la sandbox**, no las ACL del sistema operativo.

**Los symlink no existen para la sandbox.** Hagar no los muestra, no los
lee, no los sigue y no los borra: `stat`, `list_dir` y `search` los
ignoran; `read_file`, `read_chunk` y `delete_file` responden "not
found"; `chdir` sobre un symlink responde "Directory not found". Un enlace
roto o hacia el exterior es indistinguible de una ruta inexistente.

La raíz virtual de la sandbox es `/home/ai`; cada directorio configurado
se expone como `/home/ai/<alias>`. `stat`, `list_dir`, `search`,
`read_chunk`, los mensajes de `write`/`create`/`mkdir`/`delete` y `chdir`
muestran solo rutas virtuales: la ruta física nunca aparece en el
output del modelo. Una entrada `/home/ai/<alias>/...` se resuelve
contra el directorio físico del alias; las rutas relativas siguen siendo
relativas al directorio actual.

`/home/ai` es un directorio sintético: se puede listar y statar, pero no
es un mount y no es posible hacer `chdir` en él. Las entradas de
`filesystem.sandbox` siguen siendo rutas del sistema anfitrión, absolutas o con
`~` si el usuario lo elige: puede ser cualquier directorio existente y
alcanzable. Hagar no crea directorios ni presupone un home
dedicado.

```yaml
filesystem:
  sandbox:
    - alias: documenti
      path: C:\Users\pippo\Documenti
      permissions: RWX
    - alias: ebooks
      path: D:\ebooks
      permissions: R
```

No existe un flag `enabled`: cada entrada válida de `filesystem.sandbox`
se monta. Alias o permisos inválidos, ruta ausente o ruta duplicada
detienen la configuración. Las rutas físicas y los nombres internos pueden
contener espacios; el alias no, porque debe seguir siendo un único segmento
virtual.

`R` cubre lectura, listado, búsqueda y `stat`; `W` cubre escritura,
creación, renombrado, copia y borrado; `X` cubre `chdir`. Los
permisos globales `permissions.read`/`write` siguen siendo un techo: un alias
`RWX` no puede superarlos.

## 3.6 Tool de filesystem (`core/filesystem_tools.py`)

```text
filesystem.read_file
filesystem.write_file
filesystem.edit_file
filesystem.create_file
filesystem.delete_file
filesystem.mkdir
filesystem.chdir
filesystem.list_dir
filesystem.read_chunk
filesystem.rename
filesystem.copy_file
filesystem.search
filesystem.free_space
filesystem.stat
```

`list_dir` devuelve metadatos `FileInfo`; `read_chunk` lee por bytes
con `has_more`, `next_offset` y límites UTF-8 completos; `search` usa un
glob recursivo con límite de resultados; `copy_file` requiere `create`;
`rename` requiere `rename` en el origen y `create` en el destino.
Las rutas devueltas son siempre virtuales (`/home/ai/<alias>/...`).
`chdir` requiere `X` sobre el alias.

`list_dir` devuelve como máximo 100 entradas por página (`limit` máximo
500) con `offset`, `next_offset` y `has_more`; si hay otras entradas el
`message` dice `voci: riportate X di Y; per continuare usa offset=Z`.
`search` usa la misma paginación: `max_results` es el límite de página
(default 100, máximo 500), `offset` recorre los resultados. Para árboles
grandes conviene restringir `pattern`/`path` en lugar de iterar muchas
páginas. `read_file` acepta solo archivos de hasta `CHUNK_SIZE` (4096 bytes);
por encima, el error remite a `read_chunk()` porque leer todo el archivo
superaría la context window. `read_chunk` devuelve `next_offset` y
límites UTF-8 completos.

`list_dir` y `search` no muestran los symlink; `read_file` y `read_chunk`
los tratan como archivos inexistentes.

`write_file` sobrescribe solo archivos existentes; la creación pasa por
`create_file`, que requiere el permiso `create`. No es posible
eludir la prohibición de creación escribiendo una ruta nueva.

`read_file`, `read_chunk` y `read_bytes` registran una versión observada
del archivo. `write_file`, `edit_file`, `delete_file` y `rename` requieren
que el archivo se haya leído en la misma sandbox y que la versión no haya
cambiado entretanto. La versión es `(st_mtime_ns, st_size)`: es una
protección cooperativa contra la sobrescritura ciega, no un CAS contra race
TOCTOU.

`edit_file` sustituye literalmente `old_string` por `new_string`. Por
defecto la cadena debe aparecer una sola vez; `replace_all` permite
varias sustituciones. La escritura usa un archivo temporal en el mismo
directorio y `os.replace`, por lo que el contenido nunca se ve a medias.
El mismo mecanismo atómico lo usan `write_file`, `write_bytes` y
`create_file`.

### Límites de escritura

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = deshabilitado
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` es el máximo por operación individual de
  `write_file`, `create_file` o `copy_file`;
- `min_free_bytes` es la reserva de espacio que debe quedar después de
  la operación;
- `session_write_bytes` es el presupuesto acumulado de la sesión;
- `ask_over_bytes` eleva a `ASK` las operaciones por encima del umbral. El preflight
  está integrado en `ToolRegistry`: si también la policy dice `ASK`, la
  confirmación es única.

`0` deshabilita el límite individual. Superar `max_write_bytes`,
`session_write_bytes` o la reserva produce un error, no una confirmación:
son invariantes, no preguntas. `ask_over_bytes` es el único nivel que
pregunta al usuario.

`filesystem.stat` devuelve JSON con `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. Una ruta inexistente no es un error:
`exists: false` con los permisos aplicables.

## 3.7 MCP (`llm/mcp_client.py`)

Cliente MCP vía HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
conversión automática de los tool en `ToolDefinition` y registro con
namespace `mcp.<namespace>`.

Admite también respuestas `text/event-stream` (streamable HTTP) y envía
la notificación `notifications/initialized` tras el handshake. Usa
`MCP-Protocol-Version` (default `2025-06-18`, con fallback) y reutiliza
`Mcp-Session-Id` cuando el servidor lo devuelve. Los errores HTTP
incluyen el cuerpo de la respuesta para hacer diagnosticables los 400.
Los resultados de los tool se normalizan a texto: bloques `text`,
o bien `structuredContent` o JSON; un resultado con `isError`
se convierte en un error del tool.

Autenticación por servidor:

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer          # o bien "header"
      token_env: MCP_EXAMPLE_TOKEN
      # header: X-API-Key  # solo con type: header
```

El token se lee solo del entorno y no aparece en la auditoría. Si falta,
el servidor se omite con `mcp.failed` y el harness continúa; los demás
servidores siguen disponibles.

### OAuth interactivo

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # sin él, dynamic registration
    # client_secret_env: MCP_CLIENT_SECRET
    scopes: [mcp.read]
    audience: api.atlassian.com  # opcional, para proveedores 3LO
    redirect_port: 8765       # 0 = puerto aleatorio
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

Flujo authorization code + PKCE, con callback en
`http://localhost:<port>/oauth/callback` y apertura del navegador. Si el
scope contiene `offline_access`, se añade `prompt=consent`.
Los metadatos se descubren desde `.well-known` (RFC 9728 para el
recurso, RFC 8414 para el authorization server); si falta `client_id` se
usa el registro dinámico. Los tokens están en un archivo local con
permisos restringidos (`0600` donde el sistema los admite), con refresh
automático y retry una vez en `401`.

Ctrl-C durante la espera del callback cierra el servidor local y sale
con código 130, sin traceback.

Límites: nada de device flow, DPoP, mTLS o client assertion; el navegador debe
poder alcanzar el callback local. Si el callback no llega, el
terminal pide pegar la URL de redirección.

## 3.8 Vault (`memory/vault.py`)

Acceso al vault Obsidian con rutas relativas a la raíz y
protección contra la salida del vault. Ofrece lectura, escritura, append,
listado de los archivos y `load_all` para la lectura recursiva. La semántica
de la memoria vive en `memory/store.py` (§3.11).

## 3.9 Registro de auditoría (`core/audit.py`)

Archivo JSON Lines append-only. Cada línea tiene timestamp UTC, `session` y
`event`; los eventos de una misma pregunta comparten un id `turn`.

```text
harness.start      proveedor, modelo, raíces, permisos, tool, vault
turn.start         pregunta, límite de tool, modo nativo
llm.tool_choice    elección del modelo, argumentos, mode=native
llm.native_fallback proveedor sin tool nativos, paso al texto
llm.protocol_error respuesta no conforme (texto íntegro, truncado)
llm.repaired       reparación realizada con éxito
llm.repair_failed  reparación fallida
tool.call          tool, argumentos, índice
tool.result        resultado, output/error, duración en ms
turn.answer        respuesta final, número de tool usados
turn.error         fase y mensaje
turn.stop          límite alcanzado
mcp.loaded         namespace y tool importados
mcp.failed         namespace y error
llm.failed         proveedor no construible (p. ej. clave ausente)
harness.stop       salida limpia (si falta, el proceso ha sido matado)
memory.enabled     raíz, subdir, turnos de contexto
memory.disabled    motivo de la desactivación
memory.context     turnos y skill inyectados en el prompt
memory.turn        turno guardado en el vault
memory.failed      fase y error
```

Propiedades:

- escritura best effort: un error de E/S no detiene el harness y se
  señala una sola vez en stderr;
- truncamiento configurable (`audit.max_field_chars`, default 2000);
- cadena de hash (`prev`/`hash`) verificable con `verify_chain`;
- rotación en `<file>.<timestamp>` por encima de `audit.max_bytes` (0 desactiva);
- retention: `audit.max_files` (default 100) mantiene como máximo N archivos,
  incluido el activo; las copias más antiguas se eliminan;
- con `audit.include_outputs: false` el output de los tool se registra
  solo como tamaño;
- valores no JSON convertidos a serializables;
- ninguna clave API en el log;
- el log contiene también el output de los tool (por tanto contenidos de archivos):
  debe protegerse como el workspace.

## 3.10 Permisos (`core/permissions.py`)

El modelo es una matriz sujeto × objeto:

- **Capability** (`IntFlag`): qué puede hacer una operación
  (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`, `FILESYSTEM_CREATE`,
  `FILESYSTEM_DELETE`, `FILESYSTEM_EXEC`, `MEMORY_READ`,
  `MEMORY_WRITE`, `NETWORK`, `MCP_CALL`, `COMPUTE`). Se combinan con `|`;
  la verificación es siempre de subconjunto.
- **Effect** (`IntEnum`): `ALLOW`, `ASK`, `DENY`. En caso de conflicto
  vence el valor más alto (`DENY > ASK > ALLOW`).
- **Rule**: capability + efecto + filtros opcionales `tools` (glob),
  `paths` y `namespaces` (prefijos) + `reason`.
- **Subject**: quién pide (agente, usuario, sistema), con reglas y
  default (`DENY` si no se especifica).
- **Resource**: el objeto de la decisión (por ahora un tool con sus
  capability; en el futuro también notas y rutas).
- **Decision**: efecto, motivo y regla aplicada.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. el recurso debe ofrecer las capability solicitadas;
2. el **techo del sistema** (derivado de `permissions.read/write/shell`)
   debe concederlas;
3. para cada capability se aplican las reglas del sujeto: vence la
   más específica (número de filtros, después longitud del prefijo), en
   caso de empate el efecto más restrictivo; sin reglas vale el default;
4. con varias capability solicitadas vale el AND: vence el efecto peor.

`ASK` no es una decisión: es una pregunta a un humano. El
`ConfirmationProvider` la plantea — `ConsoleConfirmation` pregunta
`lo faccio? (y/N)` con default N — y sin canal de confirmación vale
`DENY`. Una GUI puede implementar el mismo protocolo con un diálogo
modal.

En CLI `core/input_broker.py` es el único propietario de la consola:
distribuye prompts, confirmaciones y las teclas `F5`/`F8`, establece el título del
terminal como señal de atención y restablece el modo normal al
final. Con stdin no interactivo recurre a `input()`.

```yaml
version: 1
subjects:
  assistant:
    default: deny
    rules:
      - capabilities: [FILESYSTEM_READ]
        effect: allow
        tools: ["filesystem.*"]
      - capabilities: [FILESYSTEM_WRITE, FILESYSTEM_CREATE]
        effect: ask
        paths: ["note"]
      - capabilities: [COMPUTE]
        effect: allow
        tools:
          - "calculator.*"
          - "statistics.*"
          - "units.*"
          - "clock.*"
          - "calendar.*"
          - "think.*"
          - "text.*"
          - "url.*"
      - capabilities: [NETWORK]
        effect: ask
        tools: ["feed.*"]
```

`policy.yaml` se lee **antes** de construir el LLM. Si no es
legible o no es válido, el harness aplica `DENY` a todas las policy,
lo registra en la auditoría (`policy.failed`) y lo señala en el chat; el resto
del harness sigue funcionando. Un sujeto ausente también degrada a
`DENY`.

El control se realiza en `ToolRegistry.execute`, único punto de
ejecución, y produce los eventos `permission.decision` y
`permission.confirmation`.

El scope `paths` compara la ruta **escrita por el modelo**
(normalizada), no la resuelta por la sandbox: una ruta absoluta o
un `chdir` pueden no corresponder a un prefijo relativo, y el
resultado sigue siendo `DENY` (fail closed).

## 3.11 Memoria (`memory/store.py`, `memory/tools.py`)

**Backend predeterminado: SQLite.** `memory/sqlite_store.py` y
`memory/database.py` usan una base de datos local (`%LOCALAPPDATA%/Hagar/memory.db`
o `HAGAR_MEMORY_DB`) como fuente de verdad para sesiones, turnos, skill y
summary. SQLite usa WAL, transacciones y `busy_timeout`; el backup es
`VACUUM INTO`. El backend `markdown` descrito abajo sigue disponible
solo por compatibilidad y ya no es el default.

**Episódica.** El harness encola cada turno concluido en una nota por
sesión:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter con `session`, `type: chat`, `created`; cuerpo con una
sección por turno (`## <timestamp> · <turn>`), pregunta y respuesta. No
se guardan los output de los tool: esos quedan en la auditoría.

Al inicio de cada turno el Agent inyecta en el prompt los últimos
`memory.context_turns` turnos (0 desactiva la inyección), truncando
pregunta y respuesta. Con `memory.context_skills > 0` añade hasta N
**skill confirmadas** pertinentes a la pregunta, por coincidencia léxica en
título, tags y contenido; las candidate y las archivadas nunca entran.
El bloque se etiqueta como datos, no como instrucciones. Un error de memoria
no detiene el turno: se registra `memory.failed`.

**Semántica.** El modelo puede proponer una memoria con tres tool:

| tool | capability | namespace |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

`create_skill` escribe `<vault>/Hagar/skills/<slug>.md` con frontmatter
`id`, `title`, `kind` (`fact`/`procedure`), `status: candidate`, `tags`,
`source_session`, `source_turn`, `model`, `created_at`. El slug es
seguro (solo ASCII, sin rutas); un título ya existente no se
sobrescribe y devuelve `duplicate: true`.

`get_context` devuelve los últimos turnos o busca por palabra clave
en las sesiones pasadas; `list_skills` filtra por `kind` y `status`.

**Ciclo de vida.** Los estados son `candidate`, `confirmed`, `archived`.
El LLM crea solo candidate; la transición es humana, desde la CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` muestra una candidate por vez con provenance y
contenido, luego pregunta `y/N/a/s/q` (confirmar, dejar, archivar, saltar,
salir). La confirmación escribe `reviewed_at`; `archive` es reversible con
`confirm`. Cada transición produce `memory.status` o `memory.review`
en la auditoría. Las notas siguen siendo archivos Obsidian: modificar `status` en el
frontmatter tiene el mismo efecto.

**Configuración**:

```yaml
memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  context_project_memories: 10
  max_context_chars: 6000
  project_max_active: 200
  summary_max_chars: 4000
  max_skill_chars: 4000
```

### Memoria de proyecto

La memoria de proyecto está separada de las skill:

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

Cada proyecto tiene un `index.md` con estado, última actividad, summary y
recuento de las decisiones activas. Cada decisión tiene estado
`candidate`/`active`/`superseded`/`archived`, alternativas, motivación,
provenance y `auto_saved`. Las decisiones no se reescriben: una nueva
decisión puede sustituir a una antigua.

Con `memory.backend: sqlite` proyectos y decisiones usan las tablas
`projects` y `decisions` de la misma base de datos; el backend Markdown
heredado sigue usando el Vault.

Al inicio Hagar muestra los proyectos activos y "actividad libre":

```text
/project list
/project new <nome>
/project select <nome>
/project free
/project status
/project archive <nome>
/project unarchive <nome>
```

Los override no interactivos son `--project <nome>` y `--free`.

Al final de la sesión:

1. el transcript se traslada a `archive/chat/`;
2. se genera un summary con el modelo, con fallback mecánico;
3. el summary se guarda con enlace y hash del transcript;
4. si hay un proyecto, el LLM propone decisiones `candidate`;
5. el usuario puede revisarlas; si las rechaza, quedan `candidate` con
   `auto_saved: true`.

El contexto inyectado usa el **índice** del proyecto: summary, títulos
de las decisiones activas y recuento, no todos los cuerpos. Los detalles se
leen con `memory.project_context(query=..., limit=...)`. El bloque
global está limitado por `max_context_chars`; si se recorta,
la auditoría registra `memory.context_trimmed`. No es una estimación de tokens: es
un presupuesto en caracteres, determinista.

Cuando un proyecto supera `project_max_active`, Hagar pregunta si
archivarlo. El archivado es reversible y no borra nada.

**Consulta del archivo.** Los transcript archivados tienen el `project`
en el frontmatter. La búsqueda y la lectura son on demand:

```text
/memory archive search <testo>
/memory archive read <session> [offset] [limit]
```

Los mismos instrumentos se exponen como `memory.archive_search` y
`memory.archive_read`; la búsqueda devuelve session, turn, timestamp,
proyecto y snippet, la lectura pagina los turnos. No hay inyección
automática del archivo en el prompt: el summary sigue siendo el índice, el
transcript es la fuente que consultar cuando hace falta.

Si `vault.path` no existe o no es escribible, la memoria se
desactiva con un aviso en el chat y `memory.disabled` en la auditoría; los
demás componentes siguen funcionando. Las escrituras de memoria están
sujetas a las policy (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.11.1 Service layer (`core/service.py`)

`HarnessService` es la API estable sobre el `Harness`: no lee de
`input()`, no escribe en stdout y no conoce la CLI. Expone:

- `ask(question)` con eventos `turn.start`, `turn.answer`, `turn.error`;
- eventos tool y permisos reenviados por `Agent` y `ToolRegistry`:
  `tool.call`, `tool.result`, `permission.decision`,
  `permission.confirmation`;
- `status()` con modelo, proyecto, memoria, auditoría, policy y tool;
- `list_projects()`, `current_project()`, `set_project()`,
  `clear_project()`, `create_project()`;
- `finish_session()`.

Los eventos son `ServiceEvent(type, data, ts)` y pueden ser consumidos
por un sink (CLI, GUI, test). La CLI actual usa el service para los turnos, la
selección de proyecto y el cierre de sesión.

## 3.11.2 Command service (`core/command_service.py`)

`CommandService` transforma los comandos slash en `CommandResult`:

```text
command, ok, lines, data, error, requires_input
```

Gestiona `/help`, `/tools`, `/status`, `/mcp`, `/audit`, `/project` y
`/memory` sin escribir en stdout. La CLI imprime `lines`; la GUI usará
`data`. La review interactiva de `/memory` sigue confiada a `MemoryCLI`
porque requiere input humano. La CLI usa el command service para todos los
comandos slash, excepto `/memory review`.

## 3.11.3 Web GUI (`core/web.py`)

`hagar web` inicia un `ThreadingHTTPServer` local con:

- `GET /` página de chat;
- `GET /static/style.css` y `/static/app.js` (assets en `web/`);
- `GET /api/events` stream SSE;
- `POST /api/message`, `/api/confirm`, `/api/project`, `/api/stop`,
  `/api/new-chat`, `/api/resume`;
- `GET /api/status`, `/api/projects`, `/api/pending`;
- `GET /api/history`, `/api/history/<session>`;
- `GET /api/tools`, `/api/audit`, `/api/thinking`;
- `GET /api/memories`, `/api/memory?path=...`.

Las pestañas de la GUI son Chat, Chat history, Tool output, Audit, Thinking y
Memories. La barra lateral tiene proyecto, estado y tokens; el historial está en la
pestaña dedicada. `SessionLog` conserva los eventos de la sesión para Tool
output y timeline; Audit lee el JSONL; Thinking privilegia el
reasoning expuesto por el proveedor y en su defecto muestra la timeline. Memories
lee el índice, excluyendo chat, archivo y summary.

Un clic en un chat pasado llama a `POST /api/resume`: el transcript
se recarga y la sesión de auditoría/memoria vuelve a ese id, así los
nuevos turnos continúan el mismo chat. `POST /api/new-chat` llama a
`MemoryStore.new_session()` y cambia la sesión, sin tocar los
transcript anteriores.

Los assets estáticos viven en `web/` (`index.html`, `style.css`,
`app.js`). `render_index()` inyecta solo el token; el resto se sirve
verbatim con whitelist e `importlib.resources`.

La GUI es un adapter: usa `HarnessService`, `CommandService` y
`QueueConfirmationProvider`. Las confirmaciones ASK bloquean el hilo del turno
en un `threading.Event`; el servidor queda libre y desbloquea la petición con
`POST /api/confirm`. Un timeout vale como rechazo.

La barra lateral muestra los tokens acumulados de la sesión: `UsageLedger` recibe
el usage de cada llamada LLM mediante `usage_sink` y publica
`usage.updated` en SSE.

**Stop:** `POST /api/stop` llama a `Agent.cancel()`; el agente controla
el evento entre un paso y otro y lanza `AgentCancelled`. El turno se
interrumpe de forma cooperativa, no aborta una petición HTTP ya en
curso.

**Vision:** `POST /api/message` acepta `images` como data URL
PNG/JPEG/WebP (máx. 4, 10 MB cada una); el body JSON puede llegar a
64 MB. `core/images.py` valida y convierte; `Agent.ask(question,
images=...)` construye content multimodal. Los adapter
compatibles con OpenAI/LM Studio usan `image_url`; Claude usa bloques
`image`; Gemini usa `inlineData`. LM Studio no acepta WebP
directamente: la GUI lo convierte a PNG. La imagen no acaba en la
memoria Markdown ni en la auditoría.

Seguridad: bind predeterminado `127.0.0.1`, token aleatorio inyectado en la
página, header `X-Hagar-Token` para las API y `?token=` para SSE. No es
multiusuario y aún no expone la modificación del Vault.

## 3.11.6 Entrada vision (`core/images.py`)

`ImageInput` valida data URL, MIME y dimensión; `Agent.ask` usa partes
canónicas (`text`, `image`) y cada backend las traduce a su propio
formato. El texto del stop y de las imágenes está separado del contenido
persistente: la memoria conserva solo la pregunta y la respuesta.

`vision.open` lee una imagen de la sandbox, la valida con magic number
y la devuelve como `ToolResult.images`. El ciclo `Agent` adjunta
la imagen a un mensaje de usuario sintético antes de la llamada
siguiente, así el modelo la ve sin recibir base64 en el texto del
tool. Límites: 4 imágenes por turno, 10 MB por imagen, PNG/JPEG/WebP.
El child puede usar `vision.open` en su propio workspace de solo lectura.

El audio no está implementado. El canal de adjuntos sería reutilizable, pero
hacen falta un contrato de proveedor audio-native distinto, formatos/decoder y una
elección explícita entre ASR y comprensión de audio; está en el roadmap sin
timeline.

`memory/export.py` exporta la base de datos SQLite a Markdown:
`Hagar/chat/`, `Hagar/skills/`, `Hagar/summaries/`,
`Hagar/projects/<id>/index.md` y `decisions/`. La escritura es atómica
(temp + `os.replace`) y el comando rechaza un destino no vacío
sin `--force`.

`memory_fts` es una tabla FTS5 en la misma base de datos, con columnas
`entity`, `entity_id`, `kind`, `project`, `status`, `title`, `body`.
`SqliteMemoryIndex.search` usa `MATCH`, `bm25()` y `snippet()`; si FTS5
no está disponible recurre a `LIKE`. `memory/import_markdown.py` importa
la misma estructura con upsert y reconstruye el índice FTS.

## 3.11.4 Token usage (`core/usage.py`)

`TokenUsage` normaliza input, output, cache y reasoning. Las funciones
`usage_from_openai`, `usage_from_anthropic`, `usage_from_gemini` y
`usage_from_ollama` leen los campos nativos de las respuestas.

`LLMClient._set_usage()` actualiza `last_usage` y llama al `usage_sink`
del cliente. `HarnessService` posee el `UsageLedger`, lo conecta al
cliente y publica `usage.updated`; la GUI lo usa en la barra lateral y `/usage`
lo lee desde la CLI. El usage del proveedor es la
verdad; una estimación local sigue siendo solo un fallback.

## 3.11.5 Memory index (`memory/index.py`)

`MemoryIndex` es un índice SQLite derivado del Vault Markdown:

- tablas `documents`, `meta` y `documents_fts` (FTS5);
- sync incremental por hash/mtime/size;
- `rebuild()` reconstruye desde cero;
- búsqueda con filtros `project`, `kind`, `status`;
- fallback `LIKE` si FTS5 no está disponible;
- base de datos en los datos locales de la app, no en el Vault sincronizado.

El tool `memory.search` usa el índice; `/memory reindex` y `/memory stats`
exponen mantenimiento y estado. Con el backend predeterminado SQLite la
fuente de verdad es `memory.db`; el antiguo `MemoryIndex` queda solo para el
backend Markdown heredado.

## 3.11.7 Decision tools (`core/decisions.py`)

`DecisionRegistry` selecciona un `DecisionProvider` y `decision.choose`
expone la elección al modelo. Los proveedores built-in son:

- `llm`: pide al cliente LLM un JSON con `choice` y `probabilities`,
  valida las label y normaliza las probabilidades;
- `linear`: carga un modelo JSON local con label, pesos y bias y usa
  softmax para producir las probabilidades.

La capability `DECISION` está separada de `COMPUTE`, `NETWORK` y
`FILESYSTEM_*`; los detalles y el formato del modelo están en
`DECISIONS.md`. Jev/Kev aún no son adapter nativos.

## 3.11.8 Hi-Fi (`core/hifi.py`)

`HiFiResolver` ejecuta un pre-pass antes del bucle agéntico:

1. pide al modelo las interpretaciones con probabilidad;
2. normaliza y ordena las probabilidades;
3. si el margen entre la primera y la segunda supera `hifi.margin`,
   sustituye la petición por la interpretación elegida más el texto
   original;
4. en caso contrario pide al modelo una pregunta de aclaración.

El evento `hifi.interpretations` registra las probabilidades y la eventual
aclaración. Un JSON no válido produce `hifi.failed` y el turno
continúa sin pre-pass.

## 3.11.9 Checkpoint (`core/checkpoints.py`)

`HarnessService.ask` abre un `WorkspaceCheckpoint` sobre el sandbox. El
checkpoint no copia el workspace: anota solo los archivos que una mutación
está a punto de cambiar. `delete_file`, `rename` y `copy_file` registran también
el destino. `/undo` restaura el último checkpoint completado.

Límite: 32 MB de snapshot, solo archivos regulares, solo el último turno.
Si el checkpoint está incompleto, el undo se rechaza.

## 3.11.10 Guardias runtime y contexto (`core/tool_registry.py`, `core/context.py`)

`ToolRegistry` aplica:

- `tools.timeout` por llamada individual, mediante worker demonio;
- `tools.repeat_limit` sobre el hash `tool + argumentos` por turno.

El timeout es best effort: un handler Python ya iniciado no se
mata. El repeat guard pone a cero el contador en cada `Agent.ask`.

`OutputSpiller` mueve los output de más de 12.000 caracteres
al `ArtifactStore` y devuelve un resumen con `artifact_id`.
`ContextCompactor` sustituye los mensajes más antiguos cuando el contexto
supera 24.000 caracteres, preservando los últimos 8 y los mensajes system.

## 3.11.11 AIsh (`core/aish.py`, `local_tools/aish_tool.py`)

`aish.exec` implementa un lenguaje de comandos, no un shell del anfitrión.
`AishExecutor` hace parsing con `shlex`, rechaza redirecciones, operadores,
variables y command substitution, y traduce cada comando en una llamada
al `ToolRegistry`. La capability `AISH` está denegada por la policy predeterminada;
habilitarla requiere una modificación explícita:

```yaml
- capabilities: [AISH]
  effect: allow
  tools: ["aish.*"]
```

Los comandos internos conservan las reglas de los tool subyacentes: habilitar
`aish.exec` no habilita `filesystem.delete_file`.

## 3.11.12 `text.transform` (`local_tools/text_transform_tool.py`)

Tool read-only con operaciones enumeradas: `grep`, `sort`, `uniq`, `cut`,
`tr`, `wc`, `head`, `tail`, `sed_replace`. Acepta una ruta de la sandbox
o texto inline; aplica límites de input, output, pattern y match.

Capability:

```text
FILESYSTEM_READ | COMPUTE
```

No escribe archivos. AIsh lo usa para los comandos textuales; el guardado del
resultado pasa por `filesystem.write_file`/`create_file` con el gate
read-before-write.

## 3.11.13 `dev.run` (`core/dev_recipes.py`, `core/dev_runner.py`)

`DevRecipeLoader` lee `recipes.yaml` una sola vez al arranque y
conserva un snapshot inmutable con hash. El archivo debe estar fuera de la
sandbox escribible.

`DevRunner` ejecuta una receta:

- valida parámetros tipados y `cwd`;
- copia el proyecto en un directorio temporal;
- ejecuta un solo argv con `shell=False`;
- usa un entorno mínimo;
- aplica timeout y kill del process group;
- separa stdout/stderr;
- limita el output;
- registra auditoría.

La capability `DEV_EXEC` es DENY por defecto. `dev.run` no acepta comandos
arbitrarios y no usa contenedores: las recetas son de confianza; la sandbox no
aísla el proceso del anfitrión. El contenedor queda congelado para un futuro
acceso directo a filesystem/programas reales.

## 3.11.14 Boxed transform (`core/boxes.py`)

Las box son funciones LLM bounded con prompt fijo, input/output en archivo
y sin memoria, tool ni autonomía.

Tool:

```text
box.list
box.run
```

Box iniciales:

```text
summarize
translate
extract_json
```

`BoxRunner` lee el input de la sandbox, aplica chunking donde hace falta,
llama al cliente LLM, valida el output JSON y escribe el resultado con el
gate read-before-write. `BOX_EXEC` es DENY por defecto.

## 3.11.15 Hagar Flow (`core/flow/`)

`validate()` parsea el código con `ast.parse`, rechaza import, clases,
funciones, lambda, try, dict/set comprehension, comprehension con más de
un `for`, dunder y llamadas dinámicas, y verifica las primitivas
disponibles. Las list comprehension con un solo `for` e `if` opcionales
están soportadas.

`FlowRunner` interpreta el AST validado sin `eval`/`exec`:

- scope lineal;
- presupuesto de step, iteraciones, tool call y timeout;
- primitivas `fs.*`, `box.*`, `memory.*` y `project.context` pasadas por
  un registry interno;
- policy y confirmaciones por cada primitiva;
- errores con línea y columna.

`FLOW_EXEC` es DENY por defecto. `flow.run` nunca repara el código:
`flow.repair` propone un candidato válido sin ejecutarlo, con un
máximo de `flow.repair_attempts` intentos. Los errores de runtime, policy,
confirmación y timeout no se reparan. El HIR aún no está presente:
el AST validado es el IR del MVP.

## 3.12 Inicio y packaging

El proyecto se instala con `pip install -e .` y declara los package en
`pyproject.toml`. El entry point es `hagar = "hagar:main"`. La versión
actual es `0.7.0`.

La configuración de ejemplo es `hagar.example.yaml`; `hagar.yaml` es un
archivo local ignorado por git. El Vault predeterminado del ejemplo es
`./vault` y debe crearse antes del inicio.

```text
hagar --config PATH       archivo de configuración
hagar --model NAME        sobrescribe model.name
hagar --project NAME      selecciona un proyecto activo
hagar --free              inicia en actividad libre
hagar --no-memory         desactiva la memoria para la sesión
hagar --no-native-tools   usa el protocolo JSON textual
hagar --version
```

La configuración se busca en este orden: `--config`, variable
`HAGAR_CONFIG`, `./hagar.yaml`. `python -m hagar` funciona desde la
directorio del proyecto.

La CI de GitHub Actions ejecuta la suite en Linux, macOS y Windows con
Python 3.11/3.12/3.13, construye sdist y wheel, ejecuta `twine check` y
prueba la instalación del wheel. El workflow `Release` parte de un tag
`v*`, verifica que el tag corresponda a la versión del paquete y
crea la release de GitHub con los artefactos.

Los test live están excluidos de la suite normal y se habilitan con
`--live`: verifican Ollama y los proveedores remotos (estos últimos solo si
la clave API está presente).

## 3.13 Tool locales (`local_tools/`)

No son servidores MCP: son proveedores locales que registran `ToolDefinition`
en el registry y viven fuera del core, en un package separado.

| módulo | tool | capability |
|---|---|---|
| `calculator` | `calculator.evaluate` | `COMPUTE` |
| `statistics` | `statistics.compute` | `COMPUTE` |
| `unit_converter` | `units.convert` | `COMPUTE` |
| `clock` | `clock.now` | `COMPUTE` |
| `calendar` | `calendar.date` | `COMPUTE` |
| `think` | `think.echo` | `COMPUTE` |
| `text` | `text.diff` | `COMPUTE` |
| `url` | `url.parse` | `COMPUTE` |
| `feeder` | `feed.read` | `NETWORK` |

- `clock.now` devuelve hora local, fecha, huso, offset UTC y epoch.
- `calendar.date` convierte la fecha local, o una fecha ISO opcional, al
  calendario juliano proléptico o al islámico tabular
  (Kuwaiti algorithm). El calendario islámico tabular puede diferir en
  un día de los basados en la observación o en Umm al-Qura.
- `think.echo` devuelve exactamente la cadena recibida; sirve para
  externalizar un pasaje intermedio en las cadenas de razonamiento.
- `text.diff` devuelve un diff unificado entre dos textos, con input
  máximo 20000 caracteres, output máximo 20000 y `context` 0..10. No
  aplica el diff.
- `url.parse` descompone scheme, host, puerto, path, query y fragment sin
  DNS ni red; limita la URL a 4096 caracteres y los parámetros a 100. Si
  la URL contiene credenciales, las redacta en el output.
- `clock`, `calendar`, `think`, `text` y `url` no acceden a filesystem
  ni a red, y recaen en la regla `COMPUTE` allow.
- La calculadora usa una whitelist AST, no `eval()`, con límites en
  expresión, número de nodos y exponente.
- `feed.read` descarga con `requests` (timeout 15 s, máximo 5 MB), acepta
  solo URL http/https y usa `feedparser`; la policy `NETWORK` es `ask`.
- SSRF: cada host se resuelve con `getaddrinfo` y cada dirección debe
  ser global; loopback, redes privadas, link-local, multicast y
  reservadas se rechazan. Los redirect no son automáticos: cada
  `Location` se revalida y se detiene tras 3 saltos. Una URL con
  credenciales se rechaza.
- `permissions.network: true` es necesario para que el techo del sistema
  conceda `NETWORK`; `COMPUTE` está siempre en el techo pero la policy puede denegarlo.
- `permissions.agents: true` es necesario para `AGENT_SPAWN`; la policy
  debe además permitir `agent.*`.
- `local_tools` está declarado en `pyproject.toml` e instalado con el
  proyecto.

Los tool built-in los registra `local_tools/plugins.py` mediante
el mismo contrato `ToolPlugin` de los plugins externos. Los plugins externos se
descubren con el entry point `hagar.tools` y reciben un `PluginContext`.
Policy y sandbox permanecen en el registry: un plugin no puede conceder
permisos. Un plugin defectuoso se omite y se registra en la auditoría, sin
detener a los demás.

## 3.14 Plugin

`core/plugins.py` define:

- `ToolPlugin` + `PluginContext` para los tool;
- `LLMProvider` para los proveedores LLM;
- descubrimiento vía `importlib.metadata.entry_points`;
- aislamiento de los errores y auditoría `plugin.loaded`/`plugin.error`.

Los proveedores built-in están en `llm/plugins.py` y se registran antes
que los externos. Un proveedor externo no puede sustituir un nombre built-in.
Los plugins Python son trusted y se ejecutan in-process; para extensiones no
fidables el límite sigue siendo MCP o un proceso separado. El contrato completo
está en `PLUGINS.md`.

## 3.15 Subagentes asíncronos

`core/subagents.py` implementa:

- `agent.spawn/status/wait/result/cancel` y `agent.run` síncrono;
- `reason` obligatorio en el spawn, registrado en la auditoría;
- capability `AGENT_SPAWN` separada: el hijo no la recibe y no puede
  crear otros agentes;
- policy del hijo estrictamente más restrictiva; policy iguales o más
  amplias se rechazan con `SubagentPolicyError`;
- timeout de reloj de 5 minutos, cooperativo, con estado `timed_out`;
- `agent_id` en todos los eventos de auditoría del padre, del hijo y del
  registry;
- hasta dos subagentes concurrentes;
- mismo modelo local pero cliente LLM separado;
- workspace temporal privado para cada hijo;
- input copiado del workspace del padre;
- outbox `artifact.put`/`artifact.put_file` y `mailbox.send` para el
  hijo;
- artifact store temporal (máx. 50 MB por artifact, 256 MB por turno)
  y mailbox en memoria (máx. 64 KB por mensaje);
- lectura bounded del padre con `artifact.read`, `artifact.list`,
  `mailbox.inbox/read/ack`;
- `artifact.save_to` copia el artifact entero a una ruta escribible de la
  sandbox del padre, sin pasar por el contexto;
- capability `AGENT_DATA`;
- registry filtrado a `FILESYSTEM_READ`, `MEMORY_READ`, `COMPUTE` y
  `AGENT_DATA`;
- exclusión de `filesystem.chdir` y `agent.*`;
- ninguna escritura de memoria;
- ASK del hijo reenviadas al usuario por `ParentBridgeConfirmation`,
  timeout 180 segundos y DENY al expirar; el padre LLM no aprueba;
- usage separado;
- auditoría `agent.spawned/started/finished/cancelled/failed`;
- al final del turno, `artifact.discarded` para los artifact no exportados, con
  motivo `unread` o `read_but_not_saved` y metadatos sin contenido;
- cleanup de workspace y job al final del turno.

`AuditLog.record` está serializado con lock para las escrituras concurrentes.
Aún no hay export de artifact, presupuesto de token/tiempo, anidamiento ni
GUI dedicada. Los detalles están en `SUBAGENTS.md`.

---

# 4. Modelo de seguridad

- El agente no ve el sistema de archivos real: solo rutas resueltas dentro de la
  sandbox.
- Las operaciones pasan solo por el `ToolRegistry`; ningún shell del anfitrión.
- Los permisos se declaran en configuración y en las policy, y los
  aplican la sandbox y el `PermissionEvaluator`; las raíces anidadas
  pueden restringir los permisos.
- Los errores son datos: un rechazo se devuelve al modelo como
  resultado del tool, no se oculta.
- Cada acción deja una huella en la auditoría, con sesión y turno.

---

# 5. Desarrollo

- Suite: `./tools/run_tests.sh` (Linux/macOS) o bien
  `.\tools\run_tests.ps1` (Windows). En Windows: 892 superados, 2 skip
  (symlink no disponibles sin Developer Mode). En Debian Linux
  (2026-11-12): todos los test en verde, incluidos los symlink (894 superados, 0
  skip). Detalles y motivación del shim en README §3.1.
- Test live: `./tools/run_tests.sh --live` (Linux/macOS) o bien
  `.\tools\run_tests.ps1 --live` (Windows) — 9 test más (Ollama;
  proveedores remotos si las claves están presentes).
- Comparación de modelos: `python tools/bench_models.py` (README §3.5).
- Comparación de protocolos: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- La suite normal no toca la red: Ollama y MCP están simulados.

## 5.1 Multiplataforma

- Las rutas internas usan `pathlib.Path`; las que se muestran al agente
  usan siempre `/` y la raíz virtual `/home/ai`.
- `filesystem.sandbox` contiene rutas del sistema anfitrión, absolutas o con
  `~` si el usuario lo elige: `Path.expanduser()` resuelve el home solo
  cuando la ruta lo usa. No se presupone que exista un home dedicado.
- Cada mount tiene un alias explícito y único (sin distinguir mayúsculas); la
  ruta física puede estar en cualquier volumen.
- `tools/run_tests.sh` es el runner POSIX; `tools/run_tests.ps1` y
  `tools/pytest_shim` sirven solo a la sandbox de Windows con token
  restringido.
- La única rama explícitamente Windows que queda es la fecha de creación en
  `stat`: `st_birthtime` donde está disponible, si no `st_ctime` en
  Windows; en Linux `created_at` puede ser `None`.
- Las API externas (OAuth, MCP, LLM) usan HTTP y `webbrowser`, no
  comandos de sistema.
- La CI de GitHub Actions cubre Linux, macOS y Windows en Python
  3.11/3.12/3.13; symlink, permisos de los tokens OAuth y callback loopback
  quedan por verificar con test live, no en la suite offline.

---

# 6. Límites conocidos y deuda técnica

- `PermissionEvaluator` cubre la v1: quedan los sujetos dinámicos, las
  confirmaciones GUI y las capability MCP asignadas por la configuración.
- El calling nativo depende del modelo: algunos ignoran los tool o
  devuelven varias llamadas; el fallback textual cubre los errores, no
  la calidad de la elección.
- El cliente MCP admite bearer/header y OAuth authorization code; no
  gestiona device flow, DPoP, mTLS ni client assertion.
- La revisión de las skill es manual desde la CLI; falta una GUI.
- La búsqueda en la memoria es por palabra clave, sin índice ni
  embedding.
- El contexto inyectado usa turnos recientes globales y hasta 3 skill
  confirmadas por coincidencia léxica, sin selección semántica.
- La memoria no borra chat o skill por antigüedad: `archive` es
  la única eliminación del contexto.
- La auditoría tiene rotación y retention (`max_files`), pero no compactación
  de las sesiones ni un anclaje externo de la cadena.
- `feed.read` valida las direcciones y los redirect, pero queda el caso DNS
  rebinding: `requests` resuelve el nombre una segunda vez en el momento
  de la conexión; hace falta un resolver pinnado.
- La calculadora no es un CAS: gestiona solo expresiones numéricas
  limitadas, no simbólicas.
- `stat().created_at` es `None` en Linux cuando falta `st_birthtime`; no
  se inventa una fecha de creación.
- Dos alias no pueden apuntar al mismo path físico: el alias
  identifica un mount y el output virtual debe seguir siendo unívoco.

## 6.1 Responsabilidad del usuario: hard link, mount y TOCTOU

**Hagar no controla los hard link, los mount/junction ni las race TOCTOU
dentro de los directorios allowed.** No es un defecto de Hagar: la sandbox es
path-based y no usa handle/file descriptor para toda la operación.

Un hard link es un segundo nombre del mismo inode, no tiene un target de
ruta y la sandbox no puede saber si existe otro nombre fuera. Un
mount o una junction puede exponer otro sistema de archivos aun permaneciendo dentro
del prefijo de la ruta. Una race TOCTOU puede cambiar un componente entre el
control de los symlink y la operación real: Hagar no usa `openat2`,
`O_NOFOLLOW` en cada componente ni handle de Windows, por lo que no garantiza
atomicidad entre check y acceso.

Los tool de filesystem de Hagar no crean hard link. Si un hard link o un
mount ya existe dentro de un directorio de la sandbox, Hagar lo trata como
un archivo o directorio normal y puede leerlo, modificarlo o borrar su
nombre interno.

La responsabilidad está, por tanto, dividida:

- **Hagar garantiza** que las rutas resueltas permanezcan dentro del alias en
  el momento del control, que los symlink sean invisibles, que los permisos
  `R`/`W`/`X` se apliquen y que las rutas reales no acaben
  en el output del modelo.
- **El usuario garantiza** que los directorios configurados en
  `filesystem.sandbox` no contengan hard link, mount o junction hacia
  contenidos que no deben ser accesibles, y que ningún proceso
  concurrente no fiable pueda modificar esos directorios durante
  la ejecución, si quiere aislamiento total.

Las race TOCTOU requieren un actor local concurrente con acceso de
escritura a los directorios de la sandbox: no son un caso accidental
del uso normal, sino un escenario malicioso o de entorno comprometido.
Para un aislamiento fuerte hacen falta un volumen dedicado, un usuario separado,
un mount namespace o un contenedor; no es tarea del resolver de rutas.

Los puntos se cierran como **responsabilidad del usuario**, no como deudas
técnicas de Hagar. Hard link, mount/junction y race TOCTOU no son
detectados ni bloqueados por esta versión.

---

# 7. Mapa de la documentación

- `MANUAL.md` — manual de usuario: comandos, configuración, policy, default.
- `ARCHITECTURE.md` — este documento: cómo es el sistema hoy.
- `ROADMAP.md` — qué hacer, decisiones tomadas y puntos abiertos.
- `PLUGINS.md` — contratos para tool y proveedores LLM plugin.
- `DOCUMENT_TOOL.md` — especificación del document tool, esquema del grafo y
  protocolo del host nativo.
- `SUBAGENTS.md` — MVP de subagentes y límites.
- `CHANGELOG.md` — historia de las versiones.
- `README.md` — inicio, configuración, test.
