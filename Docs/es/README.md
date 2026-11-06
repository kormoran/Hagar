<p align="center">
  <img src="../HAGAR.jpg">
</p>

[Italiano](../it/README.md) · [English](../en/README.md) · [Español](../es/README.md) · [中文](../zh/README.md) · [Русский](../ru/README.md) · [Português](../pt/README.md) · [العربية](../ar/README.md)

# H.A.G.A.R.

Harness Agéntico General para IA Resiliente (General Resilient Agentic Harness for AIs)

# 0. Cómo empezó todo: la seguridad

Creé HAGAR porque ningún otro harness para IA aislaba mis archivos por defecto. Ya fuera DeepSeek, Claude Code, AutoGen u otro, si se dejan libres, todos acaban exponiendo tu sistema de archivos a los LLM. Eres TÚ quien debe imponer límites, y debes hacerlo bien, porque si no el problema es tuyo. Ninguna de estas herramientas garantiza que tus datos no sean leídos con fines indeterminados, por error o por ambos motivos. Y si no lo hace el propio harness, podría hacerlo ese plugin tan chulo, esa skill tan útil o cualquier otra incorporación que acabas de instalar...

**HAGAR invierte este planteamiento: eres TÚ quien establece qué pueden ver, escribir o buscar los LLM, y dónde.** Ningún LLM puede leer ni escribir nada fuera de los directorios que hayas indicado explícitamente como legibles o escribibles en el archivo de configuración. Si un directorio no aparece en la sección `[filesystem]` de la configuración, no existe: para los LLM es como si no estuviera.

Durante el desarrollo de HAGAR me surgió otra pregunta: ¿por qué un LLM debería necesitar interactuar con el sistema operativo? En el mundo de la inteligencia artificial, el verdadero cuello de botella de rendimiento son las llamadas al modelo, que pueden tardar segundos (a veces MUCHOS segundos). El acceso directo al sistema operativo solo permite ahorrar unos pocos milisegundos: ¿vale la pena correr el riesgo? Mi respuesta es no.

Por este motivo, **HAGAR hace lo posible por aislar al LLM del sistema operativo.** Toda interacción con archivos, memorias o la propia máquina se realiza mediante herramientas específicas (basadas en el protocolo MCP o integradas directamente en HAGAR). La IA no sabe sobre qué sistema operativo está ejecutándose, y nunca debería saberlo: si existiera una forma de que una IA pudiera deducir el sistema operativo en el que corre pese al aislamiento de HAGAR, lo consideraré un fallo de seguridad y me encargaré de corregirlo (o, como mínimo, de documentar el problema para informar a los usuarios).

|Harness	|Ve el FS del host	|Ve el SO		|Aislamiento	  |
|-----------|---------------|---------------|-------------|
|Claude Code|Parcial		|Sí 	 		|Permisos	  |
|Codex CLI	|Parcial		|Sí 	 		|Sandbox	  |
|OpenHands	|No				|Sí 	 		|Docker		  |
|E2B		|No				|Sí				|VM/Contenedor |
|`HAGAR`	|`No`			|`No`			|`FS virtual`|

**Los otros harness intentan dar a los LLM un ordenador: HAGAR les dice a los LLM que el ordenador no existe.** 
Las IA deberían centrarse en la gestión del conocimiento más que en los detalles técnicos (aunque son muy buenas en ambas cosas). Cuanto más puede automatizar un framework, menor es el razonamiento (y el número de tokens) que se requiere. Así también los modelos más pequeños pueden expresar todo su potencial.

O, dicho de otro modo: para un LLM, HAGAR es la realidad.

# 1. Visión del proyecto

HAGAR es un harness para LLM, desarrollado en Python, diseñado para la ejecución segura de modelos lingüísticos.

El objetivo no es solo ofrecer una interfaz de chat para un LLM, sino crear un entorno operativo ***seguro y protegido*** en el que el LLM pueda utilizar herramientas, consultar una memoria persistente e interactuar con sistemas externos — todo ello sin tener acceso directo a los recursos reales de la máquina anfitriona — previniendo o al menos mitigando los errores más comunes.

Por eso he adoptado principios y metodologías procedentes tanto de la seguridad informática (principio de mínimo privilegio, tríada CIA) como del ámbito HMI/HCI (interacción/interfaz hombre-máquina, típica de la maquinaria industrial) y de la ergonomía cognitiva, aplicándolos al diseño del entorno en el que opera el LLM: igual que se hace con el trabajo de las personas, el propósito adicional de HAGAR es crear un entorno para LLM donde hacer lo correcto sea fácil y equivocarse sea difícil.

Sobre la base de lo expuesto y con el fin de establecer una regla de conducta general para todo desarrollo futuro de este software, enuncio aquí **las Cuatro Leyes de HAGAR**:

## 1.1 Primera Ley de HAGAR
**Un LLM es, por definición, poco fiable.** Esto no significa que sea malévolo o inútil, sino que su funcionamiento es de naturaleza probabilística. En consecuencia, toda afirmación suya debe verificarse y toda acción suya debe estar sujeta a restricciones.

## 1.2 Segunda Ley de HAGAR
**Las herramientas son más fiables que el LLM.** Si el sistema de archivos indica que un archivo existe, entonces existe de verdad. Si una herramienta devuelve el tamaño de un archivo, ese tamaño es real. El LLM interpreta, pero las herramientas miden. 

## 1.3 Tercera Ley de HAGAR
**El estado debe existir fuera de la "mente" del LLM.** Al implementar componentes como `ToolRegistry`, `MCP`, `FilesystemSandbox`, `Memory` y `PermissionEvaluator`, trasladamos el conocimiento y el control fuera del propio modelo. Esto está en línea con las prácticas estándar para sistemas en los que la seguridad es un requisito crítico.

## 1.4 Cuarta Ley de HAGAR
**Toda acción debe poder explicarse a posteriori.** Por este motivo HAGAR implementa un *registro de auditoría*: cuando algo vaya mal — y antes o después sucederá — la pregunta no debe ser "¿Por qué se ha vuelto loco el LLM?", sino "¿Qué supuestos ha adoptado?", "¿Qué herramienta ha usado?", "¿Qué dato era erróneo?". En otras palabras, debe ser posible realizar un análisis de incidentes, exactamente como en la aviación. HAGAR reconoce esta necesidad y siempre dará las herramientas para hacerlo.

## 1.5 Arquitectura de software

Desde el punto de vista estructural, HAGAR se basa en cinco principios fundamentales:

- separación entre el modelo y el sistema operativo;
- seguridad por defecto (*security by default*);
- arquitectura de plugins;
- independencia de cualquier proveedor específico de LLM;
- extensibilidad mediante herramientas (*tools*) y el MCP (Model Context Protocol).

---

# 2. Prohibiciones absolutas

Al modelo le está terminantemente prohibido:

- acceder directamente al sistema de archivos del host;
- ejecutar comandos en una shell real del SO;
- obtener privilegios superiores a los definidos en la configuración;
- conocer el sistema operativo real.

Todas las operaciones deben realizarse solo a través de herramientas registradas y controladas por el harness.

---

# 3. Desarrollo

## 3.0 Instalación y CLI

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

`pip install -e .` declara los paquetes `core`, `llm` y `memory` e
instala el comando `hagar`:

```powershell
hagar --config hagar.yaml
hagar --model qwen3:8b
hagar --no-memory
hagar --no-native-tools
hagar --version
```

La configuración se busca en el orden siguiente: el parámetro `--config`,
la variable de entorno `HAGAR_CONFIG` y, por último, el archivo `./hagar.yaml`.
También es posible usar `python -m hagar` trabajando directamente sobre el código fuente.

## 3.1 Estructura

```
hagar.py            Script de lanzamiento del harness
hagar.yaml          Script de configuración por defecto
policy.yaml			Configuración de los permisos para las herramientas (integradas y MCP)
core/               config, agent, registro de auditoría, registry, sandbox y tools
llm/                LLM backends (Ollama, DeepSeek, Claude, Gemini), cliente MCP
memory/             acceso al vault
tests/              suite de pytest
tools/              helpers de desarrollo (test runner, shim de sandbox, benchmark de modelos)
local_tools/		Herramientas para las IA integradas en HAGAR - no MCP, pero disponibles directamente
```

## 3.2 LLM backends

`model.provider` selecciona el backend. Los esquemas de las herramientas (tool), la conversión de los mensajes y las rutas nativas o de fallback se gestionan en `llm/base.py`; por lo tanto, cambiar de proveedor no requiere modificaciones en la infraestructura de ejecución (harness).

El native tool calling es la configuración por defecto para los cuatro backends. Si un modelo rechaza ese modo (devolviendo un error HTTP 400, 404 o 422), el agente pasa al protocolo sobre JSON textual para toda la sesión; se puede forzar el uso del protocolo textual estableciendo `model.native_tools: false` o pasando el argumento `--no-native-tools`.

| proveedor   | transporte                    | clave API             |
|------------|------------------------------|------------------------|
| `ollama`   | nativo `/api/chat`           | ninguna                |
| `deepseek` | REST compatible con OpenAI  | `DEEPSEEK_API_KEY`     |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

Los nombres de modelos actualmente admitidos para DeepSeek son `deepseek-flash` (por defecto) y `deepseek-v4-pro`; el antiguo `deepseek-chat` ya no se acepta. El live test usa `deepseek-flash`, a menos que se sobrescriba con la variable `HAGAR_LIVE_DEEPSEEK_MODEL`. El script `tools/diagnose_deepseek.py` permite verificar el DNS, el formato de la clave y el endpoint, sin mostrar la propia clave.

Las claves se leen solo de variables de entorno y nunca del archivo YAML. Si el nombre por defecto de la variable no se ajusta a las propias necesidades, se puede especificar otro con `model.api_key_env`. El parámetro `model.host` indica la URL base del proveedor (con un valor por defecto específico para cada uno; por ejemplo, Ollama usa `http://localhost:11434`), mientras que `model.max_tokens` se aplica solo a Claude (con un valor por defecto de 1024). 

```yaml
model:
provider: gemini
name: gemini-2.0-flash
```

Cada backend normaliza el diálogo según su propio formato: Claude recibe los mensajes de sistema en el campo dedicado `system` y los turnos alternos, mientras que Gemini recibe `systemInstruction` y el rol `model`. El protocolo compartido entre el agente y el cliente utiliza exclusivamente los roles `user` y `assistant`.

## 3.3 Registro de auditoría

Cada sesión añade entradas en formato JSON Lines en la ruta especificada en `audit.path` (valor por defecto: `logs/audit.jsonl`, resuelto relativamente al archivo de configuración):

```yaml
audit:
enabled: true
path: logs/audit.jsonl
max_field_chars: 2000
```

Eventos registrados: `harness.start`, `turn.start`, `llm.tool_choice`, `llm.protocol_error`, `llm.repaired`, `llm.repair_failed`, `tool.call`, `tool.result`, `turn.answer`, `turn.error`, `turn.stop`, `mcp.loaded`, `mcp.failed`, `llm.failed`, `harness.stop`. La ausencia de un evento `harness.stop` en la última sesión indica que el proceso se ha terminado forzosamente o se ha colapsado.

Cada registro incluye una marca de tiempo UTC, el ID de la sesión y, cuando corresponde, un ID del turno compartido por todos los eventos relativos a una única petición. El truncado de los datos está regulado por el parámetro `audit.max_field_chars`; las claves API nunca se escriben en el registro.

El registro está pensado para consultarse tras un incidente, no para que lo lea el modelo. Dado que puede contener el contenido de archivos leídos mediante las herramientas de acceso al sistema de archivos, debe tratarse con la misma cautela que se dedica al propio espacio de trabajo (workspace).

## 3.4 Autorizaciones y `policy.yaml`

Cada llamada a una herramienta se autoriza antes de su ejecución. Una herramienta declara sus
**capabilities** (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`,
`FILESYSTEM_CREATE`, `FILESYSTEM_DELETE`, `MEMORY_READ`,
`MEMORY_WRITE`, `MCP_CALL`, ...); un **sujeto** (el agente) define
reglas que asocian esas funcionalidades a `allow` (permitir), `ask` (preguntar) o `deny` (denegar),
eventualmente acotadas según el nombre de la herramienta, el prefijo de la ruta o el espacio de nombres.

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
```

La opción `ask` genera una petición en la consola del tipo `lo faccio? (y/N)` (con valor por defecto `N`); el protocolo `ConfirmationProvider` permite además implementar una ventana de diálogo modal en una interfaz gráfica (GUI). 
El archivo de políticas se lee antes de la creación del LLM: si falta o
no es válido, cada política se establece en `DENY`, el error se registra en el registro de auditoría (`policy.failed`) y se muestra en el chat, mientras el harness sigue funcionando.

## 3.5 Memoria

El sistema mantiene una memoria episódica de la conversación dentro del vault de Obsidian
(`<vault>/Hagar/chat/`) e inserta los últimos `memory.context_turns` en cada prompt. El modelo puede guardar memorias persistentes mediante
`memory.create_skill` (archivadas como `candidate` con indicación de la procedencia),
listarlas con `memory.list_skills` y consultar los pasajes anteriores
mediante `memory.get_context`.

```yaml
memory:
enabled: true
vault_subdir: Hagar
context_turns: 10
max_skill_chars: 4000
```

Si el vault está ausente o no es accesible en escritura, la funcionalidad de memoria se desactiva
generando un aviso, mientras el sistema sigue funcionando. Las escrituras en memoria pasan por el motor de políticas (`MEMORY_READ`/`MEMORY_WRITE`; por defecto, las operaciones de escritura requieren una confirmación). Véase ARCHITECTURE §3.11 para la estructura del vault.
---

# 4. Documentación

HAGAR tiene documentación en varios idiomas. Por ahora los idiomas admitidos
son: italiano, inglés, español, portugués, chino y ruso. Cada idioma tiene su propia subcarpeta dedicada en Docs.

- [MANUAL.md](MANUAL.md) — formato de la configuración, comandos de consola, 
  opciones de línea de comandos, supuestos básicos. 
- [ARCHITECTURE.md](ARCHITECTURE.md) — La arquitectura de software de esta 
  versión del harness: componentes, modelo de seguridad, límites conocidos.
- [ROADMAP.md](ROADMAP.md) — Funciones proyectadas por implementar, decisiones ya tomadas
  y cuestiones aún abiertas.
- [CHANGELOG.md](CHANGELOG.md) — historial de cambios.
