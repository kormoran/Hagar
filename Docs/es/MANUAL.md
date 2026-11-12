# HAGAR — Manual de usuario

Versión: **0.7.0**

Este manual describe el comportamiento observable de Hagar: comandos,
opciones, configuración, policy y casos de error. Para el proyecto interno
véase [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

# 1. Inicio rápido

Requisitos: Python 3.11 o superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

cp hagar.example.yaml hagar.yaml
mkdir -p vault logs

hagar --config hagar.yaml
```

En Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item hagar.example.yaml hagar.yaml
New-Item -ItemType Directory -Force vault, logs
hagar --config hagar.yaml
```

`hagar.yaml`, `testvault/` y `logs/` son locales y no deben versionarse.

## 1.1 Orden de inicio

1. Hagar lee la configuración.
2. Carga `policy.yaml`; si no es válido, aplica `DENY` a todo.
3. Construye el cliente LLM.
4. Inicializa el Vault y la memoria, si están configurados.
5. Construye la sandbox del sistema de archivos.
6. Registra los tool locales.
7. Intenta cargar los servidores MCP; un servidor fallido no detiene a los demás.
8. Muestra la elección del proyecto.
9. Entra en el bucle de chat.

---

# 2. Comandos de chat

Los comandos empiezan por `/`. Un comando desconocido **no se envía al
modelo**: Hagar responde `Comando sconosciuto` y sugiere `/help`.

## 2.1 Comandos globales

| Comando | Comportamiento |
|---|---|
| `/help` o `/?` | enumera los comandos disponibles |
| `/tools [categoría]` | enumera los tool y las capability; el filtro es opcional |
| `/status` | muestra modelo, proyecto, memoria, auditoría y sandbox |
| `/usage` | muestra los tokens consumidos en la sesión |
| `/models ...` | fichas, benchmarks y hardware para el broker |
| `/models hardware` | detecta CPU, RAM y GPU de la máquina |
| `/undo` | anula las modificaciones del último turno |
| `/mcp` | enumera servidores MCP, endpoints y tool importados |
| `/audit [n]` | muestra los últimos `n` eventos; default 10, máximo 50 |
| `exit` | sale |
| `quit` | sale |
| `Ctrl-D` | sale |
| `Ctrl-C` | interrumpe; durante OAuth sale con código 130 |

`/status` y `/audit` son comandos humanos: no pasan por el modelo y no
consumen tool call.

## 2.2 Proyecto

| Comando | Comportamiento |
|---|---|
| `/project` o `/project list` o `/project ls` | enumera los proyectos activos |
| `/project new <nombre>` | crea un proyecto y lo selecciona |
| `/project select <id>` o `/project use <id>` | selecciona un proyecto activo |
| `/project free` o `/project none` | pasa a actividad libre |
| `/project status` o `/project current` | muestra el proyecto actual |
| `/project archive <id>` | archiva un proyecto |
| `/project unarchive <id>` | reactiva un proyecto archivado |
| `/project help` | ayuda |

`select` y `archive` usan el **id** del proyecto, no el título.

En actividad libre no se lee ni se escribe memoria de proyecto; chat,
summary y skill siguen disponibles.

## 2.3 Memoria

| Comando | Comportamiento |
|---|---|
| `/memory` o `/memory help` o `/memory ?` | ayuda |
| `/memory list [candidate\|confirmed\|archived]` | enumera las skill y los recuentos |
| `/memory show <slug>` | muestra una skill |
| `/memory search <texto>` | busca en las memorias SQLite |
| `/memory sessions` | enumera los chats registrados |
| `/memory chat <session>` | muestra los turnos de un chat |
| `/memory reindex` | optimiza/reconstruye los índices SQLite |
| `/memory stats` | estado y recuentos de la base de datos |
| `/memory backup <path>` | copia consistente de la base de datos |
| `/memory export <path> [--force]` | exporta chat, skill, summary y proyectos a Markdown |
| `/memory import <path> [--force]` | importa una estructura Markdown en la base de datos |
| `/memory review` | revisión interactiva de las candidate |
| `/memory confirm <slug>` | confirma una skill |
| `/memory archive <slug>` | archiva una skill |
| `/memory archive search <texto>` | busca en los transcript archivados |
| `/memory archive read <session> [offset] [limit]` | lee un transcript archivado |

Las palabras `search` y `read` están reservadas: un slug de skill llamado
exactamente `search` o `read` no se puede archivar con este comando.

No existe un comando de borrado: solo se archiva.

El backend predeterminado es SQLite (`memory.backend: sqlite`). La base de datos
está en los datos locales de la app, no en el Vault:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

o bien `HAGAR_MEMORY_DB`. El backend `markdown` se mantiene solo por
compatibilidad. El Vault ya no se actualiza desde el backend SQLite.

## 2.4 Qué no es un comando

Los tool (`filesystem.*`, `memory.*`, `mcp.*`, `clock.now`, ...) los
llama el modelo a través del registry. No se escriben como `/tool`.
La única excepción son los comandos informativos `/tools`, `/status`, `/models`, `/mcp`,
`/audit`, que son de consola y no tool.

---

# 3. Línea de comandos

```text
hagar [opciones]
hagar web [opciones]
```

| Opción | Efecto |
|---|---|
| `--config PATH` | usa un archivo de configuración explícito |
| `--model NAME` | sobrescribe `model.name` |
| `--project NAME` | selecciona un proyecto activo al inicio |
| `--free` | inicia en actividad libre |
| `--no-memory` | desactiva memoria y proyectos para la sesión |
| `--no-native-tools` | fuerza el protocolo JSON textual |
| `--hifi` | activa el pre-paso de interpretación y aclaración |
| `--host HOST` | host de la GUI web (default `127.0.0.1`) |
| `--port PORT` | puerto de la GUI web (default `8765`) |
| `--version` | imprime la versión |

`--project` y `--free` son mutuamente excluyentes.

## 3.0 GUI web

```bash
hagar web
hagar --config hagar.yaml web --port 8765
```

Abre una GUI local en `http://127.0.0.1:8765/`.

- El servidor está pensado para un único usuario local: default `127.0.0.1`.
- El navegador recibe un token aleatorio en la página; las API lo requieren
  en el header `X-Hagar-Token`.
- El chat muestra turnos, tool call, resultados y confirmaciones ASK.
- Arriba están las pestañas **Chat**, **Chat history**, **Tool output**,
  **Audit** y **Thinking**.
- **Chat history** enumera los chats pasados, una línea por chat; un clic
  reanuda el chat: el transcript se recarga desde la base de datos y los nuevos
  turnos se añaden a la misma sesión.
- El botón **+ Nuova chat** abre una nueva sesión y reinicia el
  contexto; el chat anterior queda en el historial.
- **Memories** es un navegador de solo lectura de las notas indexadas
  (skill, proyectos, decisiones); permite búsqueda y apertura del texto.
- **Tool output** muestra los tool call y los resultados de la sesión.
- **Audit** muestra los eventos del log; si la auditoría está desactivada la pestaña está
  deshabilitada y muestra `audit off`.
- **Thinking** muestra el reasoning expuesto por el proveedor, si existe; en
  su defecto la timeline de los eventos del agente.
- **Memories** muestra memorias y skill de la base de datos en solo lectura, con búsqueda.
- El botón **Stop** interrumpe el turno de forma cooperativa.
- El botón **Immagine** adjunta PNG/JPEG/WebP (máx. 4, 10 MB cada una)
  para los modelos vision. WebP se convierte a PNG en la GUI porque LM
  Studio no lo acepta directamente. Las imágenes no se guardan
  en la memoria ni en la auditoría: al modelo le llega el data URL, no el
  path del host.
- La barra lateral inferior muestra los tokens acumulados de la sesión: input,
  output y total.
- El modelo puede cargar imágenes desde la sandbox con `vision.open`;
  la imagen se adjunta al turno, no se devuelve como base64 en el
  contexto.
- Las confirmaciones ASK son modales: el turno queda en espera y el servidor
  sigue respondiendo. Un timeout equivale a rechazo. Las peticiones de los
  subagentes muestran `agent_id` y `parent_id`; el padre LLM no puede
  aprobarlas. El timeout del subagente es de 180 segundos.
- En CLI un solo hilo posee el input. Cuando hay una confirmación activa,
  el título del terminal reclama atención y se aceptan `F5` =
  allow, `F8` = deny, además de `y/N`. Si el terminal no admite las teclas
  de función, quedan `y/N` y la GUI.
- Ctrl-C en CLI restablece el modo normal del terminal antes de
  salir.
- La GUI aún no es multiusuario y no expone modificaciones directas de la memoria.
- Ctrl-C cierra el servidor e intenta el fin de sesión.

No usar `--host 0.0.0.0` en una red no fiable: la GUI expone los tool
del harness a cualquiera que pueda alcanzar el puerto.

## 3.1 Búsqueda de la configuración

Orden:

1. `--config PATH`
2. variable `HAGAR_CONFIG`
3. `./hagar.yaml` en el directorio actual

Las rutas relativas dentro de `hagar.yaml` — auditoría, policy, Vault — se
resuelven respecto al directorio del archivo de configuración, no al
directorio desde el que lanzas Hagar.

## 3.2 Códigos de salida

| Código | Significado |
|---|---|
| `0` | salida normal o `--version` |
| `1` | error de configuración o proyecto no válido |
| `130` | interrupción con Ctrl-C |

Un error MCP no cambia el código de salida: se registra y el
harness continúa.

---

# 4. `hagar.yaml`

Ejemplo mínimo:

```yaml
model:
  provider: ollama
  name: llama3.1:latest

vault:
  path: ./vault

filesystem:
  sandbox:
    - alias: workspace
      path: .
      permissions: RX
```

## 4.1 `model`

| Campo | Default | Notas |
|---|---|---|
| `provider` | obligatorio | `ollama`, `lmstudio`, `deepseek`, `openai` (`chatgpt`), `claude`, `gemini` |
| `name` | obligatorio | nombre del modelo en el proveedor |
| `host` | default del proveedor | URL base de la API |
| `native_tools` | `true` | si `false`, usa el protocolo JSON textual |
| `max_tokens` | `1024` | usado solo por Claude |
| `timeout` | `120` | timeout HTTP en segundos para cada llamada |
| `api_key_env` | nombre estándar | variable de entorno de la clave |

Proveedores y claves:

| Proveedor | Clave estándar | Default |
|---|---|---|
| `ollama` | ninguna | `http://localhost:11434` |
| `lmstudio` | ninguna, opcional `LMSTUDIO_API_KEY` | `http://localhost:1234/v1` |
| `deepseek` | `DEEPSEEK_API_KEY` | API DeepSeek |
| `openai` / `chatgpt` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `claude` | `ANTHROPIC_API_KEY` | API Anthropic |
| `gemini` | `GEMINI_API_KEY` | API Gemini |

Las claves nunca deben escribirse en el YAML. Si falta una clave, el cliente
no se construye y el inicio falla con un error explícito. LM Studio
no requiere clave, salvo que el servidor local esté configurado para
pedirla. `chatgpt` es un alias de `openai`: la suscripción de ChatGPT no
da acceso a la API, hacen falta una clave de OpenAI y crédito de API.

Con LM Studio el tool calling nativo depende del modelo y de su
plantilla. Si el modelo acepta la petición pero responde en texto en lugar
de emitir `tool_calls`, Hagar no puede ejecutar el tool: usar
`model.native_tools: false` o un modelo tool-capable.

Con el calling nativo activo, Hagar usa los instrumentos estructurados del
proveedor. Si el proveedor rechaza el esquema (HTTP 400/404/422), en el primer
paso pasa al protocolo JSON textual para esa sesión. El fallback
cubre el error técnico, no garantiza que el modelo elija bien el tool.

## 4.2 `audit`

```yaml
audit:
  enabled: true
  path: logs/audit.jsonl
  max_field_chars: 2000
  max_bytes: 5000000
  max_files: 100
  include_outputs: true
```

| Campo | Default | Efecto |
|---|---|---|
| `enabled` | `true` | activa/desactiva el log |
| `path` | `logs/audit.jsonl` | archivo JSON Lines |
| `max_field_chars` | `2000` | trunca los campos |
| `max_bytes` | `5000000` | umbral de rotación |
| `max_files` | `100` | archivos rotados que se conservan |
| `include_outputs` | `true` | si `false`, redacta el output de los tool |

La auditoría contiene datos sensibles: output de archivos, respuestas y textos. Debe
protegerse como el workspace. `/audit` muestra solo los eventos del archivo
actual, no los rotados.

Eventos principales: `harness.start`, `turn.start`, `llm.tool_choice`,
`tool.call`, `tool.result`, `turn.answer`, `permission.decision`,
`permission.confirmation`, `memory.*`, `mcp.loaded`, `mcp.failed`,
`harness.stop`.

## 4.3 `policy`

```yaml
policy:
  path: policy.yaml
  subject: assistant
```

`path` es relativo a la configuración. Si el archivo no es legible o no es
válido:

- todas las policy pasan a `DENY`;
- se registra `policy.failed`;
- Hagar sigue iniciado pero no se ejecuta ningún tool;
- la consola muestra `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

Con el backend SQLite solo lo usan el backend Markdown heredado y los
proyectos heredados. Con `memory.backend: sqlite` puede incluso no existir.

## 4.5 `memory`

```yaml
memory:
  enabled: true
  backend: sqlite
  database: ./hagar-memory.db
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  context_project_memories: 10
  max_context_chars: 6000
  project_max_active: 200
  summary_max_chars: 4000
  max_skill_chars: 4000
```

| Campo | Default | Efecto |
|---|---|---|
| `enabled` | `true` | activa la memoria |
| `backend` | `sqlite` | `sqlite` o `markdown` heredado |
| `database` | datos locales | path explícito de la base de datos SQLite |
| `vault_subdir` | `Hagar` | subdirectorio del Vault heredado |
| `context_turns` | `10` | turnos recientes inyectados; `0` desactiva |
| `context_skills` | `3` | skill confirmadas inyectadas |
| `context_project_memories` | `10` | títulos de decisiones activas |
| `max_context_chars` | `6000` | presupuesto del bloque de memoria |
| `project_max_active` | `200` | umbral de mantenimiento de proyecto |
| `summary_max_chars` | `4000` | longitud máxima del summary |
| `max_skill_chars` | `4000` | longitud máxima de una skill |

`vault_subdir` debe permanecer dentro del Vault: las rutas absolutas, `..`,
`I:/...` y otras unidades de Windows se rechazan incluso en Linux.

Con `backend: sqlite` la base de datos predeterminada es:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

o `HAGAR_MEMORY_DB`. SQLite usa WAL, transacciones y `VACUUM INTO` para el
backup; el Vault no se actualiza.

El presupuesto es en **caracteres**, no en tokens. Cuando el bloque se
recorta, la auditoría registra `memory.context_trimmed`.

## 4.6 `filesystem`

```yaml
filesystem:
  sandbox:
    - alias: documenti
      path: C:\Users\pippo\Documenti
      permissions: RWX
  limits:
    max_write_bytes: 0
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

Cada entrada:

| Campo | Obligatorio | Notas |
|---|---|---|
| `alias` | sí | un solo segmento, único sin distinguir mayúsculas |
| `path` | sí | directorio existente del sistema anfitrión |
| `permissions` | no | default `R`; letras `R`, `W`, `X` |

Permisos:

| Letra | Cubre |
|---|---|
| `R` | leer, listar, buscar, `stat` |
| `W` | escribir, crear, renombrar, copiar, borrar |
| `X` | `chdir` en el directorio |

El agente ve `/home/ai/<alias>/...`. `/home/ai` enumera los alias pero no
es un directorio físico y no es posible entrar en él con `chdir`.

Restricciones:

- los alias y las rutas duplicados detienen la configuración;
- una ruta inexistente detiene la configuración;
- las rutas físicas pueden contener espacios; los alias no;
- Hagar no crea directorios de la sandbox ni asume un home dedicado.

Límites de escritura:

| Campo | Efecto |
|---|---|
| `max_write_bytes` | máximo por operación individual |
| `min_free_bytes` | espacio libre mínimo restante |
| `session_write_bytes` | máximo acumulado por sesión |
| `ask_over_bytes` | por encima de este umbral pide confirmación |

`0` deshabilita el límite individual. Los límites son invariantes: una
superación es un error del tool, no un aviso.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
  agents: false
```

Son el **techo del sistema**. Default: `read=true`, los demás `false`.

| Campo | Concede |
|---|---|
| `read` | filesystem read, memory read |
| `write` | filesystem write/create/delete, memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |
| `agents` | `AGENT_SPAWN` y `AGENT_DATA`, para `agent.*`/`artifact.*`/`mailbox.*` |

`COMPUTE` y `MCP_CALL` están siempre en el techo, pero la policy puede denegarlos.
Si el techo no concede una capability, la policy no puede concederla.
`agents: true` no basta por sí solo: la policy debe tener una regla
`AGENT_SPAWN` para `agent.*`.

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

Valor previsto para la recuperación documental. No modifica el contexto
de la memoria en esta versión.

## 4.9 `mcp_servers`

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer
      token_env: MCP_EXAMPLE_TOKEN
```

Campos:

| Campo | Notas |
|---|---|
| `endpoint` | URL HTTP/JSON-RPC del servidor MCP |
| `namespace` | prefijo de los tool importados: `mcp.<namespace>.*` |
| `auth` | opcional: `bearer`, `header` u `oauth` |

Bearer/header:

```yaml
auth:
  type: header
  header: Authorization
  token_env: ATLASSIAN_BASIC
```

El valor leído del entorno se envía **tal cual**: para Basic
debe ser ya `Basic <base64>`, no solo el token.

OAuth:

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    client_id: ...
    client_secret_env: MCP_CLIENT_SECRET
    scopes: [read:me, offline_access]
    audience: api.atlassian.com
    redirect_port: 8765
    token_cache: .hagar/oauth/example.json
    timeout: 300
```

El flujo es authorization code + PKCE con callback local
`http://localhost:<port>/oauth/callback`. Si falta `client_id` se intenta
el dynamic registration. Con `offline_access` se añade
`prompt=consent`. Los tokens están en un archivo local restringido y se
renuevan automáticamente.

Si un servidor MCP falla:

- se registra `mcp.failed`;
- el servidor se omite;
- los demás servidores y el resto del harness continúan;
- `/mcp` muestra cero tool para ese namespace.

## 4.10 `hifi`

```yaml
hifi:
  enabled: true
  margin: 0.20
  interpretations: 3
```

`margin` es la distancia mínima, en puntos porcentuales, entre la primera y la
segunda interpretación. Por debajo de ese umbral Hagar pide aclaración.
`interpretations` es el número de interpretaciones solicitadas al modelo.
La modalidad añade una llamada LLM por cada turno.

## 4.11 `tools`

```yaml
tools:
  timeout: 120
  repeat_limit: 3
```

`timeout` es el límite en segundos para una sola tool call; `0` lo
deshabilita. `repeat_limit` bloquea la tercera llamada idéntica en el mismo
turno; `0` deshabilita el bloqueo. El timeout de un handler Python ya en
ejecución es best effort: el worker puede terminar después del límite.

## 4.12 `dev`

```yaml
dev:
  enabled: false
  recipes: recipes.yaml
  copy_workspace: true
  max_output_chars: 100000
```

Habilita `dev.list` y `dev.run`, que ejecutan recetas fiables para tests,
debug y build. `recipes.yaml` debe estar fuera de la sandbox y se lee solo
al inicio. También hace falta la capability `DEV_EXEC` en policy.
Detalles en `DEV_RUN.md`.

## 4.13 `boxes`

```yaml
boxes:
  enabled: false
  max_input_chars: 200000
  max_output_chars: 20000
  chunk_chars: 8000
  max_calls: 20
```

Habilita `box.list` y `box.run`, transformaciones LLM bounded sobre archivos
de la sandbox. No tienen memoria, tool ni prompt libre. Hace falta `BOX_EXEC`
en policy. Detalles en `BOXES.md`.

## 4.14 `flow`

```yaml
flow:
  enabled: false
  max_source_chars: 20000
  max_steps: 10000
  max_tool_calls: 50
  max_loop_iterations: 1000
  timeout: 120
  max_output_chars: 20000
  repair_attempts: 2
```

Habilita `flow.reference`, `flow.validate` y `flow.run`, el DSL lineal
`Hagar Flow`. No es Python completo: nada de import, class, def, lambda,
try, comprensión de dict/set ni acceso a objetos Python; se admiten
list comprehension con un solo `for`. Hace falta `FLOW_EXEC` en policy; las
primitivas `fs.*` usan las capability de filesystem.

`repair_attempts` es el número máximo de intentos de `flow.repair`;
`0` deshabilita la reparación. `flow.run` nunca repara el código por sí
solo: devuelve el error y el llamador decide si usar `flow.repair`.
Con la memoria activa están disponibles `memory.search`, `memory.context`
y `memory.skill`; con un proyecto activo `project.context`.
Detalles en `FLOW.md`.

---

# 5. `policy.yaml`

Ejemplo:

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
        tools: ["filesystem.*"]

      - capabilities: [COMPUTE]
        effect: allow
        tools: ["calculator.*", "statistics.*", "units.*",
                "clock.*", "calendar.*", "think.*", "text.*", "url.*"]

      - capabilities: [MCP_CALL]
        effect: ask
        tools: ["mcp.*"]

      - capabilities: [MEMORY_READ]
        effect: allow
        tools: ["memory.*"]

      - capabilities: [MEMORY_WRITE]
        effect: ask
        tools: ["memory.*"]
```

## 5.1 Efectos

| Efecto | Significado |
|---|---|
| `allow` | el tool puede ejecutarse |
| `ask` | hace falta una confirmación humana |
| `deny` | el tool no se ejecuta |

Orden de gravedad: `DENY > ASK > ALLOW`. Con varias capability solicitadas
vale el AND: vence el efecto peor.

`ASK` sin canal de confirmación equivale a `DENY`. La confirmación desde consola
muestra `lo faccio? (y/N)` y el default es `N`.

## 5.2 Capability

| Nombre | Uso |
|---|---|
| `FILESYSTEM_READ` | lectura, listado, búsqueda, stat |
| `FILESYSTEM_WRITE` | modificación |
| `FILESYSTEM_CREATE` | creación, copia, rename en destino |
| `FILESYSTEM_DELETE` | borrado |
| `FILESYSTEM_EXEC` | entrada/ejecución en la sandbox |
| `MEMORY_READ` | lectura de memoria |
| `MEMORY_WRITE` | escritura de memoria |
| `NETWORK` | acceso de red |
| `MCP_CALL` | llamada a tool MCP |
| `COMPUTE` | cálculo local sin red/sistema de archivos |
| `AISH` | ejecución del lenguaje AIsh |
| `DEV_EXEC` | ejecución de recetas dev.run |
| `BOX_EXEC` | ejecución de boxed transform |
| `FLOW_EXEC` | ejecución del DSL Hagar Flow |

## 5.3 Reglas y especificidad

Una regla puede filtrar con:

- `tools`: glob sobre el nombre (`filesystem.*`, `mcp.atlassian.*`);
- `paths`: prefijos sobre la ruta escrita por el modelo;
- `namespaces`: prefijos sobre el namespace.

Vence la regla más específica: primero el número de filtros, después la
longitud del prefijo. En caso de empate vence el efecto más restrictivo.
Sin reglas vale el `default` del sujeto; el default seguro es `deny`.

`AISH` está denegada por la regla predefinida `aish.*`. Para habilitar AIsh
el usuario debe cambiar esa regla a `allow`; los comandos internos
siguen sujetos a las reglas de sus respectivos tool.

El scope `paths` compara la ruta **escrita por el modelo**, no la
resuelta tras `chdir`: una ruta absoluta o un cambio de directorio puede no
corresponder y produce `DENY` (fail closed).

## 5.4 Errores

Si `policy.yaml` es inválido, falta una capability o el sujeto no
existe:

- Hagar aplica `DENY` a todas las policy;
- registra `policy.failed`;
- muestra un aviso;
- no ejecuta ningún tool.

---

# 6. Comportamientos predeterminados

| Situación | Comportamiento |
|---|---|
| Ningún `hagar.yaml` | error de configuración, salida 1 |
| YAML inválido | error de configuración, salida 1 |
| Policy inválida | DENY total, harness iniciado |
| Memoria desactivada | comprueba `memory.database` y los permisos del directorio |
| `Projects: disabled` | comprueba la base de datos SQLite o `vault.path` en el backend heredado |
| Ningún proyecto activo | actividad libre |
| Inicio no interactivo | actividad libre, salvo `--project`/`--free` |
| `--project` inexistente | error, salida 1 |
| Servidor MCP inalcanzable | `mcp.failed`, servidor omitido |
| Modelo/Ollama inalcanzable | error del turno, harness sigue activo |
| Clave API ausente | cliente no construido, error al inicio |
| Tool denegado | resultado de error al modelo, ninguna ejecución |
| Tool en `ASK` sin confirmación | rechazo |
| Límite de escritura superado | error del tool, ninguna escritura |
| Archivo de más de 4096 bytes con `read_file` | error, usar `read_chunk` |
| `write_file`/`edit_file`/`delete_file`/`rename` sobre un archivo no leído | error: leer primero el archivo |
| Archivo cambiado después de la lectura | error: releer antes de modificarlo |
| `edit_file` con `old_string` ambiguo | error: usar `replace_all` o una cadena más específica |
| `edit_file` con `old_string` ausente | error, ninguna modificación |
| Página por encima del límite | `has_more`/`next_offset` |
| Symlink | invisible; operación como ruta inexistente |
| Hard link/mount/junction | no detectados; responsabilidad del usuario |
| Race TOCTOU | no controlada; responsabilidad del usuario |
| Memoria ausente durante el turno | `memory.failed`, el turno continúa |
| Fin de sesión con turnos | summary, archivo, review de proyecto |
| Review rechazada | decisiones candidate con `auto_saved: true` |
| Proyecto por encima de `project_max_active` | petición de archivado |
| Ctrl-C durante OAuth | callback cerrado, salida 130 |
| Comando `/` desconocido | mensaje, no enviado al modelo |

## 6.1 Fin de sesión

Al salir, si la memoria está activa y hay turnos:

1. el transcript se traslada a `archive/chat/`;
2. se genera un summary (LLM, con fallback mecánico);
3. el summary se guarda con enlace y hash;
4. si hay un proyecto, el LLM propone decisiones candidate;
5. el usuario puede revisarlas; si las rechaza quedan candidate.

Si no hay turnos no se crea ningún summary.

## 6.2 Qué no hace Hagar

- no ejecuta comandos de shell;
- no da al modelo rutas físicas;
- no garantiza aislamiento del SO: la sandbox está basada en rutas;
- no controla hard link, mount, junction ni TOCTOU;
- no borra chat o skill por antigüedad;
- no cifra el Vault;
- no promueve automáticamente una skill o una decisión a verdad.

---

# 7. Seguridad operativa

- El modelo no es fiable: las policy y las confirmaciones son los controles.
- La base de datos SQLite contiene conversaciones y decisiones: debe protegerse.
- La auditoría puede contener output de archivos: debe protegerse.
- Las claves API están solo en el entorno.
- Los tokens MCP/OAuth están en cachés locales con permisos restringidos.
- No exponer Ollama o LM Studio en la red sin necesidad.
- Un hard link o un mount dentro de un directorio allowed puede exponer
  contenidos externos: Hagar no los detecta.

---

# 8. Troubleshooting

| Síntoma | Comprobación |
|---|---|
| `Policy: DENY ALL` | validar `policy.yaml` y `policy.path` |
| `Memory: disabled` | comprueba `memory.database` y los permisos |
| `Projects: disabled` | comprueba la base de datos SQLite |
| `Failed to load MCP server` | endpoint, token, `/mcp` |
| `MCP auth token missing` | variable indicada por `token_env` |
| `MCP HTTP 401` | credenciales/header Basic u OAuth |
| `MCP HTTP 400` | protocolo, sesión o parámetros del servidor |
| `read_file` demasiado grande | usar `read_chunk` |
| `PermissionError` | policy, permisos `R/W/X`, ruta fuera de la sandbox |
| Tool no enumerado | servidor MCP fallido o tool no registrado |
| Comando no reconocido | `/help` |

Para un error de configuración, Hagar sale con código 1 e imprime el
detalle en stderr. Para un error de turno, el modelo recibe el
resultado del tool y la auditoría conserva el evento.
