# HAGAR — Arquitectura

Versión: 0.2.0 (en desarrollo)
Última actualización: 2026-11-03

---

# 1. Qué es Hagar

Hagar es un harness para LLM escrito en Python, diseñado para la ejecución
resiliente de modelos lingüísticos.

El objetivo no es un chat con un modelo, sino un entorno operativo
**seguro** en el que un LLM pueda usar herramientas, consultar una memoria
persistente e interactuar con sistemas externos sin acceder directamente
a los recursos reales de la máquina anfitriona.

Para ello el proyecto aplica principios de HMI/HCI y de ergonomía
cognitiva al diseño del entorno en el que opera el modelo.

## 1.1 Las Cuatro Leyes de HAGAR

**Primera ley — El LLM no es fiable por definición.**
No porque sea malo o inútil: porque es probabilístico. Toda afirmación suya
debe verificarse y toda acción suya debe limitarse.

**Segunda ley — Las herramientas son más fiables que el LLM.**
Si el sistema de archivos dice que un archivo existe, existe. Si la herramienta devuelve
un tamaño, ese tamaño es real. El LLM interpreta, las herramientas
miden.

**Tercera ley — El estado debe existir fuera de la mente del LLM.**
ToolRegistry, MCP, FileSystemSandbox y (en perspectiva)
PermissionEvaluator trasladan conocimiento y control fuera del modelo,
como en los sistemas safety-critical.

**Cuarta ley — Toda acción debe poder explicarse después.**
El registro de auditoría responde a la pregunta correcta: no "¿por qué se ha vuelto loco el LLM?"
sino "¿qué suposición ha hecho?", "¿qué herramienta ha usado?", "¿qué dato era
erróneo?". Investigación de incidentes, como en la aviación.

## 1.2 Prohibiciones absolutas

El modelo no debe nunca:

- acceder directamente al sistema de archivos del host;
- ejecutar comandos en la shell real;
- obtener privilegios superiores a los definidos por la configuración;
- conocer la organización efectiva del sistema operativo.

Todas las operaciones pasan exclusivamente por herramientas registradas y
controladas por el harness.

## 1.3 Principios arquitectónicos

- separación entre modelo y sistema operativo;
- seguridad por defecto;
- arquitectura de plugins;
- independencia del proveedor de LLM;
- extensibilidad mediante herramientas y protocolo MCP.

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
  │     ├── DeepSeekClient
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
| `model` | sí | provider, nombre, host, max_tokens, api_key_env, native_tools |
| `vault` | sí | ruta del vault Obsidian |
| `filesystem` | sí | `sandbox`: lista de `{alias, path, permissions}`; `limits`: presupuesto de escritura |
| `permissions` | no | read, write, shell, network (default `true/false/false/false`) |
| `rag` | no | `top_k` (default 8) |
| `mcp_servers` | no | endpoint, namespace, auth (bearer/header/oauth) |
| `audit` | no | enabled, path, max_field_chars, max_bytes, max_files, include_outputs |
| `policy` | no | ruta del archivo policy, subject |
| `memory` | no | enabled, vault_subdir, context_turns, context_skills, max_skill_chars |

Los errores de validación producen siempre `ConfigError`, con un mensaje que
indica el campo. La ruta de la auditoría, si es relativa, se resuelve
respecto al archivo de configuración.

## 3.2 Interfaz LLM y backends (`llm/`)

`LLMClient` tiene dos rutas:

- **calling nativo** (por defecto): `native_step()` envía los esquemas de las
  herramientas en el formato del proveedor y lee las llamadas de la respuesta;
- **protocolo JSON textual** (fallback): `request_tool_call()` pide un
  JSON con `tool`/`arguments`, con parsing robusto y un intento de
  reparación.

El esquema de los parámetros se construye a partir de `ToolDefinition`:
OpenAI/Ollama usan `tools[].function`, Claude `tools[].input_schema`,
Gemini `functionDeclarations`. La conversación canónica usa los roles
`user`/`assistant`/`tool`; cada cliente la traduce (OpenAI `tool_calls`,
Claude bloques `tool_use`/`tool_result`, Gemini `functionCall`/
`functionResponse`). Un rechazo HTTP 400/404/422 produce
`NativeToolsUnavailable`: el Agent pasa al protocolo textual solo si aún
no ha ejecutado herramientas.

Los nombres de las herramientas se normalizan para las API que no admiten el
punto (`filesystem.read_file` → `filesystem__read_file`) y se devuelven al
nombre interno en la respuesta: la política, la auditoría y los test ven siempre el nombre
original.

El texto sigue siendo el fallback para modelos que no soportan las herramientas nativas;
`model.native_tools: false` lo fuerza (o `--no-native-tools` desde la CLI).

| proveedor | API | clave | notas |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | host default `localhost:11434` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system separado, turnos alternos |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, rol `model` |

La clave se lee solo del entorno; `model.api_key_env` sobrescribe el
nombre por defecto. `model.host` es la base URL de todos los proveedores (con un
default por proveedor), `model.max_tokens` lo usa solo Claude.
`llm/factory.py` construye el cliente y rechaza proveedores desconocidos o
claves ausentes. DeepSeek: los modelos actuales son `deepseek-flash` y
`deepseek-v4-pro`; `deepseek-chat` ya no se acepta.

Estado actual: **calling nativo v1** con fallback textual automático
(véase ROADMAP).

## 3.3 Modelo de las herramientas (`core/tool_*.py`)

`ToolDefinition` describe nombre, descripción, categoría, parámetros,
handler, `origin` (`local` o `mcp.<namespace>`), las `capabilities`
declaradas, el estado de habilitación y `requires_confirmation`
(suelo de ASK aplicado por el registry).

`ToolCall` es la petición del modelo (`tool`, `arguments`, `id`);
`ToolResult` es el resultado estructurado (`tool_name`, `success`, `output`,
`error`).

`ToolRegistry` registra, busca, habilita/deshabilita y ejecuta las herramientas;
expone los metadatos al modelo y es el único punto de ejecución.

## 3.4 Agent (`core/agent.py`)

Ciclo agéntico multi-step, con dos rutas:

- **nativa**: una respuesta puede contener varias llamadas; el Agent reencola
  el mensaje `assistant` y un mensaje `tool` con el id para cada
  resultado;
- **textual**: una llamada por vez, con el resultado enviado como
  turno `user`.

En ambas:

1. el modelo decide si hace falta una herramienta;
2. si no hace falta, la respuesta final cierra el turno;
3. si hace falta, la herramienta se ejecuta y el resultado vuelve al modelo;
4. el límite `max_tool_calls` vale para todo el turno. Si el modelo
   insiste, el turno se cierra con `Agent stopped after N tool calls`
   (protección contra bucles).

Si el primer paso nativo falla con `NativeToolsUnavailable`, el Agent
pasa al protocolo textual (`llm.native_fallback`); un error después de que
se haya ejecutado una herramienta cierra el turno con `turn.error`, sin
fallback.

Cada paso se registra en la auditoría: pregunta, elección de la herramienta, argumentos,
resultado, duración y respuesta final. Una auditoría rota no detiene al agente: el
fallo se señala en stderr.

El `Agent` recibe el `Vault` pero aún no lo usa.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

Sistema de archivos virtual del agente. Cada petición:

1. se resuelve contra el directorio actual (`resolve_path`);
2. se verifica contra las raíces concedidas (`effective_permissions`);
3. se filtra por los permisos efectivos, con las raíces más específicas que
   sobrescriben las más externas;
4. se controla contra los symlink y el espacio de disco disponible
   (`FS_Guardian`, nombre legacy).

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
muestran solo rutas virtuales: la ruta física no aparece nunca
en la salida del modelo. Una entrada `/home/ai/<alias>/...` se resuelve
contra el directorio físico del alias; las rutas relativas siguen
relativas al directorio actual.

`/home/ai` es un directorio sintético: se puede listar y hacer stat, pero no
es un mount y no es posible hacer `chdir` en él. Las entradas de
`filesystem.sandbox` siguen siendo rutas del sistema anfitrión, absolutas o con
`~` si el usuario lo elige: puede ser cualquier directorio existente y
accesible. Hagar no crea directorios y no presupone un home
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

## 3.6 Herramientas del sistema de archivos (`core/filesystem_tools.py`)

```text
filesystem.read_file
filesystem.write_file
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
`chdir` requiere `X` en el alias.

`list_dir` devuelve como máximo 100 entradas por página (`limit` máximo
500) con `offset`, `next_offset` y `has_more`; si hay más entradas el
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
  está integrado en `ToolRegistry`: si también la política dice `ASK`, la
  confirmación es una sola.

`0` desactiva el límite individual. Superar `max_write_bytes`,
`session_write_bytes` o la reserva produce un error, no una confirmación:
son invariantes, no preguntas. `ask_over_bytes` es el único nivel que
pregunta al usuario.

`filesystem.stat` devuelve JSON con `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. Una ruta inexistente no es un error:
`exists: false` con los permisos aplicables.

## 3.7 MCP (`llm/mcp_client.py`)

Cliente MCP vía HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
conversión automática de las herramientas en `ToolDefinition` y registro con
namespace `mcp.<namespace>`.

También soporta respuestas `text/event-stream` (streamable HTTP) y envía
la notificación `notifications/initialized` tras el handshake. Usa
`MCP-Protocol-Version` (default `2025-06-18`, con fallback) y reutiliza
`Mcp-Session-Id` cuando el servidor lo devuelve. Los errores HTTP
incluyen el cuerpo de la respuesta para hacer diagnosticables los 400.
Los resultados de las herramientas se normalizan a texto: bloques `text`,
si no `structuredContent` o JSON; un resultado con `isError`
se convierte en un error de la herramienta.

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
usa la registración dinámica. Los tokens están en un archivo local con
permisos restringidos (`0600` donde el sistema los soporta), con refresh
automático y retry una vez ante `401`.

Ctrl-C durante la espera del callback cierra el servidor local y sale
con código 130, sin traceback.

Límites: nada de device flow, DPoP, mTLS ni client assertion; el navegador debe
poder alcanzar el callback local. Si el callback no llega, el
terminal pide pegar la URL de redirección.

## 3.8 Vault (`memory/vault.py`)

Acceso al vault Obsidian con rutas relativas a la raíz y
protección contra la salida del vault. Ofrece lectura, escritura, append,
listado de archivos y `load_all` para la lectura recursiva. La semántica
de la memoria vive en `memory/store.py` (§3.11).

## 3.9 Registro de auditoría (`core/audit.py`)

Archivo JSON Lines append-only. Cada línea tiene marca de tiempo UTC, `session` y
`event`; los eventos de una misma pregunta comparten un id de `turn`.

```text
harness.start      proveedor, modelo, raíces, permisos, herramientas, vault
turn.start         pregunta, límite de herramientas, modo nativo
llm.tool_choice    elección del modelo, argumentos, mode=native
llm.native_fallback proveedor sin herramientas nativas, paso al texto
llm.protocol_error respuesta no conforme (texto íntegro, truncado)
llm.repaired       reparación correcta
llm.repair_failed  reparación fallida
tool.call          herramienta, argumentos, índice
tool.result        resultado, output/error, duración en ms
turn.answer        respuesta final, número de herramientas usadas
turn.error         fase y mensaje
turn.stop          límite alcanzado
mcp.loaded         namespace y herramientas importadas
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
- truncado configurable (`audit.max_field_chars`, default 2000);
- cadena de hash (`prev`/`hash`) verificable con `verify_chain`;
- rotación en `<file>.<timestamp>` por encima de `audit.max_bytes` (0 desactiva);
- retención: `audit.max_files` (default 100) mantiene como máximo N archivos,
  incluido el activo; las copias de seguridad más antiguas se eliminan;
- con `audit.include_outputs: false` la salida de las herramientas se registra
  solo como tamaño;
- los valores no JSON se hacen serializables;
- ninguna clave API en el registro;
- el registro contiene también la salida de las herramientas (por tanto, contenidos de archivos):
  debe protegerse como el workspace.

## 3.10 Permisos (`core/permissions.py`)

El modelo es una matriz sujeto × objeto:

- **Capability** (`IntFlag`): qué puede hacer una operación
  (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`, `FILESYSTEM_CREATE`,
  `FILESYSTEM_DELETE`, `FILESYSTEM_EXEC`, `MEMORY_READ`,
  `MEMORY_WRITE`, `NETWORK`, `MCP_CALL`, `COMPUTE`). Se combinan con `|`;
  la verificación es siempre de subconjunto.
- **Effect** (`IntEnum`): `ALLOW`, `ASK`, `DENY`. En caso de conflicto
  gana el valor más alto (`DENY > ASK > ALLOW`).
- **Rule**: capability + efecto + filtros opcionales `tools` (glob),
  `paths` y `namespaces` (prefijos) + `reason`.
- **Subject**: quién pide (agente, usuario, sistema), con reglas y
  default (`DENY` si no se especifica).
- **Resource**: el objeto de la decisión (por ahora una herramienta con sus
  capability; en el futuro también notas y rutas).
- **Decision**: efecto, motivo y regla aplicada.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. el recurso debe ofrecer las capability solicitadas;
2. el **techo del sistema** (derivado de `permissions.read/write/shell`)
   debe concederlas;
3. para cada capability se aplican las reglas del sujeto: gana la
   más específica (número de filtros y luego longitud del prefijo), a
   igualdad el efecto más restrictivo; sin reglas vale el default;
4. con varias capability solicitadas vale el AND: gana el efecto peor.

`ASK` no es una decisión: es una pregunta a un humano. El
`ConfirmationProvider` la plantea — `ConsoleConfirmation` pide
`lo faccio? (y/N)` con default N — y sin canal de confirmación vale
`DENY`. Una GUI podrá implementar el mismo protocolo con un diálogo
modal.

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
legible o no es válido, el harness aplica `DENY` a todas las políticas,
lo registra en la auditoría (`policy.failed`) y lo señala en el chat; el resto
del harness sigue funcionando. También un sujeto ausente degrada a
`DENY`.

El control se realiza en `ToolRegistry.execute`, único punto de
ejecución, y produce los eventos `permission.decision` y
`permission.confirmation`.

El ámbito `paths` compara la ruta **escrita por el modelo**
(normalizada), no la resuelta por la sandbox: una ruta absoluta o
un `chdir` pueden no corresponder a un prefijo relativo, y el
resultado sigue siendo `DENY` (fail closed).

## 3.11 Memoria (`memory/store.py`, `memory/tools.py`)

**Episódica.** El harness encola cada turno concluido en una nota por
sesión:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter con `session`, `type: chat`, `created`; cuerpo con una
sección por turno (`## <timestamp> · <turn>`), pregunta y respuesta. No
se guardan las salidas de las herramientas: esas quedan en la auditoría.

Al inicio de cada turno el Agent inyecta en el prompt los últimos
`memory.context_turns` turnos (0 desactiva la inyección), truncando
pregunta y respuesta. Con `memory.context_skills > 0` añade hasta N
**skill confirmadas** pertinentes a la pregunta, por match léxico en
título, tags y contenido; las candidatas y las archivadas no entran nunca.
El bloque se etiqueta como datos, no como instrucciones. Un error de memoria
no detiene el turno: se registra `memory.failed`.

**Semántica.** El modelo puede proponer una memoria con tres herramientas:

| herramienta | capability | namespace |
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
El LLM crea solo candidatas; la transición es humana, desde la CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` muestra una candidata por vez con provenance y
contenido, y después pide `y/N/a/s/q` (confirmar, dejar, archivar, saltar,
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

Cada proyecto tiene un `index.md` con estado, última actividad, resumen y
recuento de las decisiones activas. Cada decisión tiene estado
`candidate`/`active`/`superseded`/`archived`, alternativas, motivación,
provenance y `auto_saved`. Las decisiones no se reescriben: una nueva
decisión puede sustituir a una antigua.

Al arrancar Hagar muestra los proyectos activos y "actividad libre":

```text
/project list
/project new <nombre>
/project select <nombre>
/project free
/project status
/project archive <nombre>
/project unarchive <nombre>
```

Los overrides no interactivos son `--project <nombre>` y `--free`.

Al final de la sesión:

1. el transcript se mueve a `archive/chat/`;
2. se genera un resumen con el modelo, con fallback mecánico;
3. el resumen se guarda con enlace y hash del transcript;
4. si hay un proyecto, el LLM propone decisiones `candidate`;
5. el usuario puede revisarlas; si rechaza, siguen siendo `candidate` con
   `auto_saved: true`.

El contexto inyectado usa el **índice** del proyecto: resumen, títulos
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
/memory archive search <texto>
/memory archive read <session> [offset] [limit]
```

Las mismas herramientas se exponen como `memory.archive_search` y
`memory.archive_read`; la búsqueda devuelve session, turn, timestamp,
proyecto y snippet, la lectura pagina los turnos. No hay inyección
automática del archivo en el prompt: el resumen sigue siendo el índice, el
transcript es la fuente que consultar cuando hace falta.

Si `vault.path` no existe o no es escribible, la memoria se
desactiva con un aviso en el chat y `memory.disabled` en la auditoría; los
demás componentes siguen funcionando. Las escrituras de memoria están
sujetas a las políticas (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.12 Arranque y packaging

El proyecto se instala con `pip install -e .` y declara los paquetes en
`pyproject.toml`. El entry point es `hagar = "hagar:main"`. La versión
actual es `0.3.0`.

La configuración de ejemplo es `hagar.example.yaml`; `hagar.yaml` es un
archivo local ignorado por git. El Vault por defecto del ejemplo es
`./vault` y debe crearse antes del arranque.

```text
hagar --config PATH       archivo de configuración
hagar --model NAME        sobrescribe model.name
hagar --project NAME      selecciona un proyecto activo
hagar --free              arranca en actividad libre
hagar --no-memory         desactiva la memoria para la sesión
hagar --no-native-tools   usa el protocolo JSON textual
hagar --version
```

La configuración se busca en este orden: `--config`, variable
`HAGAR_CONFIG`, `./hagar.yaml`. `python -m hagar` funciona desde la
carpeta del proyecto.

La CI de GitHub Actions ejecuta la suite en Linux, macOS y Windows con
Python 3.11/3.12/3.13, construye sdist y wheel, ejecuta `twine check` y
prueba la instalación del wheel. El workflow `Release` parte de un tag
`v*`, verifica que el tag corresponda a la versión del paquete y
crea la release de GitHub con los artefactos.

Los test live están excluidos de la suite normal y se habilitan con
`--live`: verifican Ollama y los proveedores remotos (estos últimos solo si
la clave API está presente).

## 3.13 Herramientas locales (`local_tools/`)

No son servidores MCP: son proveedores locales que registran `ToolDefinition`
en el registry y viven fuera del core, en un paquete separado.

| módulo | herramienta | capability |
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
- `calendar.date` convierte la fecha local, o una fecha ISO opcional, en el
  calendario juliano proléptico o en el islámico tabular
  (algoritmo kuwaití). El calendario islámico tabular puede diferir en
  un día de los basados en la observación o en Umm al-Qura.
- `think.echo` devuelve exactamente la cadena recibida; sirve para
  externalizar un pasaje intermedio en las cadenas de razonamiento.
- `text.diff` devuelve un diff unificado entre dos textos, con entrada
  máxima de 20000 caracteres, salida máxima de 20000 y `context` 0..10. No
  aplica el diff.
- `url.parse` descompone scheme, host, puerto, path, query y fragment sin
  DNS ni red; limita la URL a 4096 caracteres y los parámetros a 100. Si
  la URL contiene credenciales, las redacta en la salida.
- `clock`, `calendar`, `think`, `text` y `url` no acceden al sistema de archivos
  ni a la red, y recaen en la regla `COMPUTE` allow.
- La calculadora usa una whitelist AST, no `eval()`, con límites en
  expresión, número de nodos y exponente.
- `feed.read` descarga con `requests` (timeout 15 s, máximo 5 MB), acepta
  solo URL http/https y usa `feedparser`; la política `NETWORK` es `ask`.
- SSRF: cada host se resuelve con `getaddrinfo` y cada dirección debe
  ser global; loopback, redes privadas, link-local, multicast y
  reservadas se rechazan. Los redirects no son automáticos: cada
  `Location` se revalida y se detienen tras 3 saltos. Una URL con
  credenciales se rechaza.
- `permissions.network: true` es necesario para que el techo del sistema
  conceda `NETWORK`; `COMPUTE` está siempre en el techo pero la política puede denegarlo.
- `local_tools` está declarado en `pyproject.toml` y se instala con el
  proyecto.

---

# 4. Modelo de seguridad

- El agente no ve el sistema de archivos real: solo rutas resueltas dentro de la
  sandbox.
- Las operaciones pasan solo por el `ToolRegistry`; ninguna shell del host.
- Los permisos se declaran en la configuración y en las políticas, y los
  aplican la sandbox y `PermissionEvaluator`; las raíces anidadas
  pueden restringir los permisos.
- Los errores son datos: un rechazo se devuelve al modelo como
  resultado de la herramienta, no se oculta.
- Cada acción deja un rastro en la auditoría, con sesión y turno.

---

# 5. Desarrollo

- Suite: `./tools/run_tests.sh` (Linux/macOS) o
  `.\tools\run_tests.ps1` (Windows). En Windows: 691 superados, 2 skip
  (symlink no disponibles sin Developer Mode). En Debian Linux
  (2026-11-06): todos los test en verde, incluidos los symlink (693 superados, 0
  skip). Detalles y motivación del shim en README §3.1.
- Test live: `./tools/run_tests.sh --live` (Linux/macOS) o
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
  `tools/pytest_shim` solo sirven a la sandbox de Windows con token
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
- El calling nativo depende del modelo: algunos ignoran las herramientas o
  devuelven varias llamadas; el fallback textual cubre los errores, no
  la calidad de la elección.
- El cliente MCP soporta bearer/header y OAuth authorization code; no
  gestiona device flow, DPoP, mTLS ni client assertion.
- La revisión de las skill es manual desde la CLI; falta una GUI.
- La búsqueda en la memoria es por palabra clave, sin índice ni
  embedding.
- El contexto inyectado usa turnos recientes globales y hasta 3 skill
  confirmadas por match léxico, sin selección semántica.
- La memoria no borra chats ni skill por antigüedad: `archive` es
  la única retirada del contexto.
- La auditoría tiene rotación y retención (`max_files`), pero no compactación
  de las sesiones ni un anclaje externo de la cadena.
- `feed.read` valida las direcciones y los redirects, pero queda el caso DNS
  rebinding: `requests` resuelve el nombre una segunda vez en el momento
  de la conexión; hace falta un resolver fijado.
- La calculadora no es un CAS: gestiona solo expresiones numéricas
  limitadas, no simbólicas.
- `stat().created_at` es `None` en Linux cuando falta `st_birthtime`; no
  se inventa una fecha de creación.
- Dos alias no pueden apuntar al mismo path físico: el alias
  identifica un mount y la salida virtual debe seguir siendo unívoca.

## 6.1 Responsabilidad del usuario: hard link, mount y TOCTOU

**Hagar no controla los hard links, los mounts/junctions ni las race TOCTOU
dentro de los directorios allowed.** No es un defecto de Hagar: la sandbox es
path-based y no usa handles/file descriptors para toda la operación.

Un hard link es un segundo nombre del mismo inode, no tiene un target de
ruta y la sandbox no puede saber si existe otro nombre fuera. Un
mount o una junction puede exponer otro sistema de archivos aun permaneciendo dentro
del prefijo de la ruta. Una race TOCTOU puede cambiar un componente entre el
control de los symlink y la operación real: Hagar no usa `openat2`,
`O_NOFOLLOW` en cada componente ni handles de Windows, por lo que no garantiza
atomicidad entre check y acceso.

Las herramientas del sistema de archivos de Hagar no crean hard links. Si un hard link o un
mount ya existe dentro de un directorio de la sandbox, Hagar lo trata como
un archivo o directorio normal y puede leerlo, modificarlo o borrar su
nombre interno.

La responsabilidad está, por tanto, dividida:

- **Hagar garantiza** que las rutas resueltas permanezcan dentro del alias en
  el momento del control, que los symlink sean invisibles, que los permisos
  `R`/`W`/`X` se apliquen y que las rutas reales no terminen
  en la salida del modelo.
- **El usuario garantiza** que los directorios configurados en
  `filesystem.sandbox` no contengan hard links, mounts o junctions hacia
  contenidos que no deben ser accesibles, y que ningún proceso
  concurrente no fiable pueda modificar esos directorios durante
  la ejecución, si quiere un aislamiento total.

Las race TOCTOU requieren un actor local concurrente con acceso de
escritura a los directorios de la sandbox: no son un caso accidental
del uso normal, sino un escenario malicioso o de entorno comprometido.
Para un aislamiento fuerte hacen falta un volumen dedicado, un usuario separado,
un mount namespace o un contenedor; no es tarea del resolver de rutas.

Los puntos se cierran como **responsabilidad del usuario**, no como deudas
técnicas de Hagar. Los hard links, los mounts/junctions y las race TOCTOU no son
detectados ni bloqueados por esta versión.

---

# 7. Mapa de la documentación

- `MANUAL.md` — manual de usuario: comandos, configuración, políticas, defaults.
- `ARCHITECTURE.md` — este documento: cómo es el sistema hoy.
- `ROADMAP.md` — qué hacer, decisiones tomadas y puntos abiertos.
- `CHANGELOG.md` — historia de las versiones.
- `README.md` — arranque, configuración, test.
