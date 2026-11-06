# HAGAR — Manual de usuario

Versión: **0.3.0**

Este manual describe el comportamiento observable de Hagar: comandos,
opciones, configuración, políticas y casos de error. Para el diseño interno
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

## 1.1 Orden de arranque

1. Hagar lee la configuración.
2. Carga `policy.yaml`; si no es válido, aplica `DENY` a todo.
3. Construye el cliente LLM.
4. Inicializa el Vault y la memoria, si están configurados.
5. Construye la sandbox del sistema de archivos.
6. Registra las herramientas locales.
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
| `/tools [categoría]` | enumera las herramientas y las capability; el filtro es opcional |
| `/status` | muestra modelo, proyecto, memoria, auditoría y sandbox |
| `/mcp` | enumera servidores MCP, endpoint y herramientas importadas |
| `/audit [n]` | muestra los últimos `n` eventos; por defecto 10, máximo 50 |
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

En actividad libre no se lee ni se escribe memoria de proyecto; el chat,
el resumen y las skill siguen disponibles.

## 2.3 Memoria

| Comando | Comportamiento |
|---|---|
| `/memory` o `/memory help` o `/memory ?` | ayuda |
| `/memory list [candidate\|confirmed\|archived]` | enumera las skill y los recuentos |
| `/memory show <slug>` | muestra una skill |
| `/memory review` | revisión interactiva de las candidatas |
| `/memory confirm <slug>` | confirma una skill |
| `/memory archive <slug>` | archiva una skill |
| `/memory archive search <texto>` | busca en los transcript archivados |
| `/memory archive read <session> [offset] [limit]` | lee un transcript archivado |

Las palabras `search` y `read` están reservadas: un slug de skill llamado
exactamente `search` o `read` no se puede archivar con este comando.

No existe ningún comando de borrado: solo se archiva.

## 2.4 Qué no es un comando

Las herramientas (`filesystem.*`, `memory.*`, `mcp.*`, `clock.now`, ...) las
llama el modelo a través del registry. No se escriben como `/tool`.
La única excepción son los comandos informativos `/tools`, `/status`, `/mcp`,
`/audit`, que son de consola y no herramientas.

---

# 3. Línea de comandos

```text
hagar [opciones]
```

| Opción | Efecto |
|---|---|
| `--config PATH` | usa un archivo de configuración explícito |
| `--model NAME` | sobrescribe `model.name` |
| `--project NAME` | selecciona un proyecto activo al arrancar |
| `--free` | arranca en actividad libre |
| `--no-memory` | desactiva memoria y proyectos para la sesión |
| `--no-native-tools` | fuerza el protocolo JSON textual |
| `--version` | imprime la versión |

`--project` y `--free` son mutuamente excluyentes.

## 3.1 Búsqueda de la configuración

Orden:

1. `--config PATH`
2. variable `HAGAR_CONFIG`
3. `./hagar.yaml` en el directorio actual

Las rutas relativas dentro de `hagar.yaml` — auditoría, política, Vault — se
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
| `provider` | obligatorio | `ollama`, `deepseek`, `claude`, `gemini` |
| `name` | obligatorio | nombre del modelo en el proveedor |
| `host` | default del proveedor | URL base de la API |
| `native_tools` | `true` | si es `false`, usa el protocolo JSON textual |
| `max_tokens` | `1024` | usado solo por Claude |
| `api_key_env` | nombre estándar | variable de entorno de la clave |

Proveedores y claves:

| Proveedor | Clave estándar |
|---|---|
| `ollama` | ninguna |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `claude` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |

Las claves nunca deben escribirse en el YAML. Si falta una clave, el cliente
no se construye y el arranque falla con un error explícito.

Con el calling nativo activo, Hagar usa las herramientas estructuradas del
proveedor. Si el proveedor rechaza el esquema (HTTP 400/404/422), en el primer
paso pasa al protocolo JSON textual para esa sesión. El fallback
cubre el error técnico, no garantiza que el modelo elija bien la herramienta.

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
| `enabled` | `true` | activa/desactiva el registro |
| `path` | `logs/audit.jsonl` | archivo JSON Lines |
| `max_field_chars` | `2000` | trunca los campos |
| `max_bytes` | `5000000` | umbral de rotación |
| `max_files` | `100` | archivos rotados que se conservan |
| `include_outputs` | `true` | si es `false`, redacta la salida de las herramientas |

La auditoría contiene datos sensibles: salidas de archivos, respuestas y textos. Debe
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

- todas las políticas pasan a `DENY`;
- se registra `policy.failed`;
- Hagar sigue arrancado pero no se ejecuta ninguna herramienta;
- la consola muestra `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

Es la raíz de la memoria Markdown. Debe existir y ser escribible.
Si falta o no es escribible, la memoria se desactiva con un aviso;
el resto del harness continúa.

## 4.5 `memory`

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

| Campo | Default | Efecto |
|---|---|---|
| `enabled` | `true` | activa la memoria |
| `vault_subdir` | `Hagar` | subdirectorio dentro del Vault |
| `context_turns` | `10` | turnos recientes inyectados; `0` desactiva |
| `context_skills` | `3` | skill confirmadas inyectadas |
| `context_project_memories` | `10` | títulos de decisiones activas |
| `max_context_chars` | `6000` | presupuesto del bloque de memoria |
| `project_max_active` | `200` | umbral de mantenimiento del proyecto |
| `summary_max_chars` | `4000` | longitud máxima del resumen |
| `max_skill_chars` | `4000` | longitud máxima de una skill |

`vault_subdir` debe permanecer dentro del Vault: rutas absolutas, `..`,
`I:/...` y otras unidades de Windows se rechazan incluso en Linux.

El presupuesto está en **caracteres**, no en tokens. Cuando el bloque se
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

- alias y rutas duplicados detienen la configuración;
- una ruta inexistente detiene la configuración;
- las rutas físicas pueden contener espacios; los alias no;
- Hagar no crea directorios de la sandbox y no presupone un home dedicado.

Límites de escritura:

| Campo | Efecto |
|---|---|
| `max_write_bytes` | máximo por operación individual |
| `min_free_bytes` | espacio libre mínimo restante |
| `session_write_bytes` | máximo acumulado por sesión |
| `ask_over_bytes` | por encima de este umbral pide confirmación |

`0` desactiva el límite individual. Los límites son invariantes: un
exceso es un error de la herramienta, no un aviso.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
```

Son el **techo del sistema**. Default: `read=true`, los demás `false`.

| Campo | Concede |
|---|---|
| `read` | filesystem read, memory read |
| `write` | filesystem write/create/delete, memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |

`COMPUTE` y `MCP_CALL` están siempre dentro del techo, pero la política puede denegarlos.
Si el techo no concede una capability, la política no puede concederla.

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
| `namespace` | prefijo de las herramientas importadas: `mcp.<namespace>.*` |
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
la dynamic registration. Con `offline_access` se añade
`prompt=consent`. Los tokens están en un archivo local restringido y se
renuevan automáticamente.

Si falla un servidor MCP:

- se registra `mcp.failed`;
- el servidor se omite;
- los demás servidores y el resto del harness continúan;
- `/mcp` muestra cero herramientas para ese namespace.

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
| `allow` | la herramienta puede ejecutarse |
| `ask` | hace falta una confirmación humana |
| `deny` | la herramienta no se ejecuta |

Orden de gravedad: `DENY > ASK > ALLOW`. Con varias capability solicitadas
vale el AND: gana el efecto peor.

`ASK` sin canal de confirmación equivale a `DENY`. La confirmación por consola
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
| `MCP_CALL` | llamada a herramientas MCP |
| `COMPUTE` | cálculo local sin red ni sistema de archivos |

## 5.3 Reglas y especificidad

Una regla puede filtrar con:

- `tools`: glob sobre el nombre (`filesystem.*`, `mcp.atlassian.*`);
- `paths`: prefijos sobre la ruta escrita por el modelo;
- `namespaces`: prefijos sobre el namespace.

Gana la regla más específica: primero el número de filtros, después la
longitud del prefijo. A igualdad gana el efecto más restrictivo.
Sin reglas vale el `default` del sujeto; el default seguro es `deny`.

El ámbito `paths` compara la ruta **escrita por el modelo**, no la
resuelta tras `chdir`: una ruta absoluta o un cambio de directorio puede no
corresponder y produce `DENY` (fail closed).

## 5.4 Errores

Si `policy.yaml` no es válido, falta una capability o el sujeto no
existe:

- Hagar aplica `DENY` a todas las políticas;
- registra `policy.failed`;
- muestra un aviso;
- no ejecuta ninguna herramienta.

---

# 6. Comportamientos por defecto

| Situación | Comportamiento |
|---|---|
| Ningún `hagar.yaml` | error de configuración, salida 1 |
| YAML inválido | error de configuración, salida 1 |
| Política inválida | DENY total, harness arrancado |
| Vault ausente/no escribible | memoria desactivada, harness arrancado |
| `projects` no escribible | proyectos deshabilitados, memoria activa |
| Ningún proyecto activo | actividad libre |
| Arranque no interactivo | actividad libre, salvo `--project`/`--free` |
| `--project` inexistente | error, salida 1 |
| Servidor MCP inalcanzable | `mcp.failed`, servidor omitido |
| Modelo/Ollama inalcanzable | error del turno, el harness sigue activo |
| Clave API ausente | cliente no construido, error al arrancar |
| Herramienta denegada | resultado de error al modelo, sin ejecución |
| Herramienta en `ASK` sin confirmación | rechazo |
| Límite de escritura superado | error de la herramienta, sin escritura |
| Archivo de más de 4096 bytes con `read_file` | error, usar `read_chunk` |
| Página por encima del límite | `has_more`/`next_offset` |
| Symlink | invisible; operación como ruta inexistente |
| Hard links/mounts/junctions | no detectados; responsabilidad del usuario |
| Race TOCTOU | no controlada; responsabilidad del usuario |
| Memoria ausente durante el turno | `memory.failed`, el turno continúa |
| Fin de sesión con turnos | resumen, archivo, revisión del proyecto |
| Revisión rechazada | decisiones candidatas con `auto_saved: true` |
| Proyecto por encima de `project_max_active` | solicitud de archivado |
| Ctrl-C durante OAuth | callback cerrado, salida 130 |
| Comando `/` desconocido | mensaje, no enviado al modelo |

## 6.1 Fin de sesión

Al salir, si la memoria está activa y hay turnos:

1. el transcript se mueve a `archive/chat/`;
2. se genera un resumen (LLM, con fallback mecánico);
3. el resumen se guarda con enlace y hash;
4. si hay un proyecto, el LLM propone decisiones candidatas;
5. el usuario puede revisarlas; si rechaza, siguen siendo candidatas.

Si no hay turnos no se crea ningún resumen.

## 6.2 Qué no hace Hagar

- no ejecuta comandos de shell;
- no da al modelo rutas físicas;
- no garantiza aislamiento del SO: la sandbox está basada en rutas;
- no controla hard links, mounts, junctions ni TOCTOU;
- no borra chat ni skill por antigüedad;
- no cifra el Vault;
- no promueve automáticamente una skill o una decisión a verdad.

---

# 7. Seguridad operativa

- El modelo no es de confianza: las políticas y las confirmaciones son los controles.
- El Vault es Markdown en claro: puede contener conversaciones y decisiones.
- La auditoría puede contener salidas de archivos: debe protegerse.
- Las claves API están solo en el entorno.
- Los tokens MCP/OAuth están en cachés locales con permisos restringidos.
- No expongas Ollama o LM Studio en la red sin necesidad.
- Un hard link o un mount dentro de un directorio allowed puede exponer
  contenidos externos: Hagar no los detecta.

---

# 8. Solución de problemas

| Síntoma | Comprobación |
|---|---|
| `Policy: DENY ALL` | validar `policy.yaml` y `policy.path` |
| `Memory: disabled` | ¿existe `vault.path`? ¿es escribible? |
| `Projects: disabled` | ¿existe `vault.path/Hagar/projects`? |
| `Failed to load MCP server` | endpoint, token, `/mcp` |
| `MCP auth token missing` | variable indicada por `token_env` |
| `MCP HTTP 401` | credenciales/header Basic u OAuth |
| `MCP HTTP 400` | protocolo, sesión o parámetros del servidor |
| `read_file` demasiado grande | usar `read_chunk` |
| `PermissionError` | política, permisos `R/W/X`, ruta fuera de la sandbox |
| Herramienta no listada | servidor MCP fallido o herramienta no registrada |
| Comando no reconocido | `/help` |

Ante un error de configuración, Hagar sale con código 1 e imprime el
detalle en stderr. Ante un error de turno, el modelo recibe el
resultado de la herramienta y la auditoría conserva el evento.
