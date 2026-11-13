# HAGAR — Arquitetura

Versão: 0.7.0
Última atualização: 2026-11-03

---

# 1. O que é o Hagar

O Hagar é um harness para LLM escrito em Python, concebido para a execução
resiliente de modelos de linguagem.

O objetivo não é uma conversa com um modelo, mas um ambiente operativo
**seguro** no qual um LLM possa usar ferramentas, consultar uma memória
persistente e interagir com sistemas externos sem aceder diretamente
aos recursos reais da máquina anfitriã.

Para este efeito, o projeto aplica princípios de HMI/HCI e de Ergonomia
Cognitiva à conceção do ambiente em que o modelo opera.

## 1.1 As Quatro Leis de HAGAR

**Primeira lei — O LLM não é fiável por definição.**
Não porque seja malévolo ou inútil: porque é probabilístico. Cada uma das
suas afirmações tem de ser verificada e cada uma das suas ações tem de ser
limitada.

**Segunda lei — As ferramentas são mais fiáveis do que o LLM.**
Se o filesystem diz que um ficheiro existe, ele existe. Se a ferramenta
devolve um tamanho, esse tamanho é real. O LLM interpreta, as ferramentas
medem.

**Terceira lei — O estado tem de existir fora da mente do LLM.**
ToolRegistry, MCP, FileSystemSandbox e (em perspetiva)
PermissionEvaluator deslocam conhecimento e controlo para fora do modelo,
como nos sistemas safety-critical.

**Quarta lei — Cada ação tem de poder ser explicada depois.**
O registo de auditoria responde à pergunta certa: não "porque é que o LLM
enlouqueceu?" mas "que pressuposto assumiu?", "que ferramenta usou?",
"que dado estava errado?". Investigação de incidentes, como na aviação.

## 1.2 Proibições absolutas

O modelo nunca deve:

- aceder diretamente ao filesystem anfitrião;
- executar comandos na shell real;
- obter privilégios superiores aos definidos pela configuração;
- conhecer a organização efetiva do sistema operativo.

Todas as operações passam exclusivamente por ferramentas registadas e
controladas pelo harness.

## 1.3 Princípios arquiteturais

- separação entre modelo e sistema operativo;
- segurança por predefinição;
- arquitetura de plugins;
- independência do provider LLM;
- extensibilidade através de ferramentas e do protocolo MCP.

---

# 2. Arquitetura

```text
Utilizador
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
  │     ├── memory.*        (planeado)
  │     └── mcp.*
  │
  ├── FileSystemSandbox
  │
  ├── MCPClient
  │
  └── Vault (Obsidian)
```

Fluxo de execução:

```text
Utilizador
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
Resposta final     turn.answer
```

---

# 3. Componentes

## 3.1 Config (`core/config.py`)

Carrega e valida um ficheiro YAML (`hagar.yaml`) num `AppConfig`.

Secções:

| secção | obrigatória | conteúdo |
|---|---|---|
| `model` | sim | provider, nome, host, timeout, max_tokens, api_key_env, native_tools |
| `vault` | sim | caminho do vault Obsidian |
| `filesystem` | sim | `sandbox`: lista de `{alias, path, permissions}`; `limits`: budget de escrita |
| `permissions` | não | read, write, shell, network (predefinição `true/false/false/false`) |
| `rag` | não | `top_k` (predefinição 8) |
| `mcp_servers` | não | endpoint, namespace, auth (bearer/header/oauth) |
| `audit` | não | enabled, path, max_field_chars, max_bytes, max_files, include_outputs |
| `policy` | não | caminho do ficheiro policy, subject |
| `memory` | não | enabled, vault_subdir, context_turns, context_skills, max_skill_chars |

Erros de validação produzem sempre `ConfigError`, com uma mensagem que
indica o campo. O caminho da auditoria, se relativo, é resolvido
relativamente ao ficheiro de configuração.

## 3.2 Interface LLM e backend (`llm/`)

`LLMClient` tem dois percursos:

- **chamada nativa** (predefinição): `native_step()` envia os esquemas das
  ferramentas no formato do provider e lê as chamadas da resposta;
- **protocolo JSON textual** (fallback): `request_tool_call()` pede um
  JSON com `tool`/`arguments`, com parsing robusto e uma tentativa de
  reparação.

O esquema dos parâmetros é construído por `ToolDefinition`:
OpenAI/Ollama usam `tools[].function`, Claude `tools[].input_schema`,
Gemini `functionDeclarations`. A conversa canónica usa os papéis
`user`/`assistant`/`tool`; cada cliente tradu-la (OpenAI `tool_calls`,
Claude blocos `tool_use`/`tool_result`, Gemini `functionCall`/
`functionResponse`). Uma recusa HTTP 400/404/422 produz
`NativeToolsUnavailable`: o Agent passa ao protocolo textual apenas se
ainda não executou ferramentas.

Os nomes das ferramentas são normalizados para as API que não admitem o
ponto (`filesystem.read_file` → `filesystem__read_file`) e repostos no
nome interno na resposta: política, auditoria e testes veem sempre o nome
original.

O texto continua a ser o fallback para modelos que não suportam as
ferramentas nativas; `model.native_tools: false` força-o (ou
`--no-native-tools` da CLI).

| provider | API | chave | notas |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | host predefinido `localhost:11434` |
| `lmstudio` | `/v1/chat/completions` (OpenAI) | opcional `LMSTUDIO_API_KEY` | host predefinido `localhost:1234/v1` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `openai` / `chatgpt` | `/v1/chat/completions` | `OPENAI_API_KEY` | ChatGPT via API, não subscrição |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system separado, turnos alternados |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, papel `model` |

A chave lê-se apenas do ambiente; `model.api_key_env` substitui o
nome predefinido. `model.host` é o base URL de todos os providers (com um
default por provider), `model.timeout` é o timeout HTTP (predefinição 120),
`model.max_tokens` é usado apenas pelo Claude.
`llm/factory.py` constrói o cliente e recusa providers desconhecidos ou
chaves em falta. Os providers built-in são spec em `llm/plugins.py`; um
provider externo registra-se com o entry point `hagar.llm` e uma factory
`(config, audit) -> LLMClient` (ver `PLUGINS.md`). O LM Studio não
exige chave salvo configuração do servidor; a OpenAI exige uma
chave API, não uma subscrição ChatGPT.
DeepSeek: os modelos correntes são `deepseek-flash` e
`deepseek-v4-pro`; `deepseek-chat` já não é aceite.

Estado atual: **chamada nativa v1** com fallback textual automático
(ver ROADMAP).

## 3.3 Modelo das ferramentas (`core/tool_*.py`)

`ToolDefinition` descreve nome, descrição, categoria, parâmetros,
handler, `origin` (`local` ou `mcp.<namespace>`), as `capabilities`
declaradas, o estado de ativação e `requires_confirmation`
(piso de ASK aplicado pelo registry).

`ToolCall` é o pedido do modelo (`tool`, `arguments`, `id`);
`ToolResult` é o resultado estruturado (`tool_name`, `success`, `output`,
`error`).

`ToolRegistry` registra, procura, ativa/desativa e executa as ferramentas;
expõe os metadados ao modelo e é o único ponto de execução.

## 3.4 Agent (`core/agent.py`)

Ciclo agêntico multi-step, com dois percursos:

- **nativo**: uma resposta pode conter várias chamadas; o Agent reenfileira
  a mensagem `assistant` e uma mensagem `tool` com o id para cada
  resultado;
- **textual**: uma chamada de cada vez, com o resultado enviado como
  turno `user`.

Em ambos:

1. o modelo decide se é necessária uma ferramenta;
2. se não for necessária, a resposta final fecha o turno;
3. se for necessária, a ferramenta é executada e o resultado volta ao modelo;
4. o limite `max_tool_calls` vale para todo o turno. Se o modelo
   insistir, o turno fecha com `Agent stopped after N tool calls`
   (proteção contra loops).

Se o primeiro passo nativo falhar com `NativeToolsUnavailable`, o Agent
passa ao protocolo textual (`llm.native_fallback`); um erro depois de
uma ferramenta ter sido executada fecha o turno com `turn.error`, sem
fallback.

Cada passo é registado na auditoria: pergunta, escolha da ferramenta, argumentos,
resultado, duração e resposta final. Uma auditoria quebrada não para o agente: a
falha é assinalada em stderr.

O `Agent` recebe o `Vault` mas ainda não o usa.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

Filesystem virtual do agente. Cada pedido é:

1. resolvido contra a diretoria atual (`resolve_path`);
2. verificado contra as raízes concedidas (`effective_permissions`);
3. filtrado pelas permissões efetivas, com as raízes mais específicas a
   substituir as mais externas;
4. controlado contra os symlinks e o espaço em disco disponível
   (`FS_Guardian`, nome legacy).

`DirectoryPermissions` modela `read`, `write`, `create`, `rename`,
`delete`, `execute`; `None` significa "herda da raiz externa".
Um percurso fora das raízes é sempre `PermissionError`.

`FileInfo` / `stat()` devolvem tipo, dimensão em bytes, datas de
criação/modificação/acesso (ISO 8601 com offset local) e as permissões
**efetivas da sandbox**, não as ACL do sistema operativo.

**Os symlinks não existem para a sandbox.** O Hagar não os mostra, não os
lê, não os segue e não os apaga: `stat`, `list_dir` e `search` ignoram-nos;
`read_file`, `read_chunk` e `delete_file` respondem "not
found"; `chdir` sobre um symlink responde "Directory not found". Um link
quebrado ou para o exterior é indistinguível de um percurso inexistente.

A raiz virtual da sandbox é `/home/ai`; cada diretoria configurada
é exposta como `/home/ai/<alias>`. `stat`, `list_dir`, `search`,
`read_chunk`, as mensagens de `write`/`create`/`mkdir`/`delete` e `chdir`
mostram apenas percursos virtuais: o percurso físico nunca aparece
no output do modelo. Um input `/home/ai/<alias>/...` é resolvido
contra a diretoria física do alias; os percursos relativos permanecem
relativos à diretoria atual.

`/home/ai` é uma diretoria sintética: pode ser listada e consultada com stat, mas não
é um mount e não é possível fazer `chdir` para lá. As entradas de
`filesystem.sandbox` continuam a ser caminhos do sistema anfitrião, absolutos ou com
`~` se o utilizador o escolher: pode ser qualquer diretoria existente e
alcançável. O Hagar não cria diretorias e não assume uma home
dedicada.

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

Não existe um flag `enabled`: cada entrada válida de `filesystem.sandbox`
é montada. Alias ou permissões inválidas, caminho em falta ou caminho duplicado
param a configuração. Os caminhos físicos e os nomes internos podem
conter espaços; o alias não, porque tem de permanecer um único segmento
virtual.

`R` cobre leitura, listagem, pesquisa e `stat`; `W` cobre escrita,
criação, renomeação, cópia e eliminação; `X` cobre `chdir`. As
permissões globais `permissions.read`/`write` continuam a ser um teto: um alias
`RWX` não as pode ultrapassar.

## 3.6 Ferramentas filesystem (`core/filesystem_tools.py`)

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

`list_dir` devolve metadados `FileInfo`; `read_chunk` lê por bytes
com `has_more`, `next_offset` e limites UTF-8 completos; `search` usa um
glob recursivo com limite de resultados; `copy_file` exige `create`;
`rename` exige `rename` na origem e `create` no destino.
Os percursos devolvidos são sempre virtuais (`/home/ai/<alias>/...`).
`chdir` exige `X` no alias.

`list_dir` devolve no máximo 100 entradas por página (`limit` máximo
500) com `offset`, `next_offset` e `has_more`; se houver outras entradas o
`message` diz `voci: riportate X di Y; per continuare usa offset=Z`.
`search` usa a mesma paginação: `max_results` é o limite de página
(predefinição 100, máximo 500), `offset` percorre os resultados. Para árvores
grandes convém restringir `pattern`/`path` em vez de iterar muitas
páginas. `read_file` aceita apenas ficheiros até `CHUNK_SIZE` (4096 bytes);
acima disso, o erro remete para `read_chunk()` porque ler todo o ficheiro
ultrapassaria a context window. `read_chunk` devolve `next_offset` e
limites UTF-8 completos.

`list_dir` e `search` não mostram os symlinks; `read_file` e `read_chunk`
tratam-nos como ficheiros inexistentes.

`write_file` sobrescreve apenas ficheiros existentes; a criação passa por
`create_file`, que exige a permissão `create`. Não é possível
contornar a proibição de criação escrevendo um percurso novo.

`read_file`, `read_chunk` e `read_bytes` registam uma versão observada
do ficheiro. `write_file`, `edit_file`, `delete_file` e `rename` exigem
que o ficheiro tenha sido lido na mesma sandbox e que a versão não tenha
mudado entretanto. A versão é `(st_mtime_ns, st_size)`: é uma
proteção cooperativa contra overwrite cego, não um CAS contra race
TOCTOU.

`edit_file` substitui literalmente `old_string` por `new_string`. Por
predefinição a string tem de aparecer uma única vez; `replace_all` permite
várias substituições. A escrita usa um ficheiro temporário na mesma
diretoria e `os.replace`, pelo que o conteúdo nunca é visto a meio.
O mesmo mecanismo atómico é usado por `write_file`, `write_bytes` e
`create_file`.

### Limites de escrita

```yaml
filesystem:
  limits:
    max_write_bytes: 0       # 0 = desativado
    min_free_bytes: 0
    session_write_bytes: 0
    ask_over_bytes: 0
```

- `max_write_bytes` é o máximo por operação individual de
  `write_file`, `create_file` ou `copy_file`;
- `min_free_bytes` é a reserva de espaço que tem de permanecer depois
  da operação;
- `session_write_bytes` é o budget cumulativo da sessão;
- `ask_over_bytes` eleva a `ASK` as operações acima do limiar. O preflight
  está integrado em `ToolRegistry`: se também a política disser `ASK`, a
  confirmação é uma só.

`0` desativa o limite individual. Ultrapassar `max_write_bytes`,
`session_write_bytes` ou a reserva produz um erro, não uma confirmação:
são invariantes, não perguntas. `ask_over_bytes` é o único nível que
pergunta ao utilizador.

`filesystem.stat` devolve JSON com `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. Um percurso inexistente não é um erro:
`exists: false` com as permissões aplicáveis.

## 3.7 MCP (`llm/mcp_client.py`)

Cliente MCP via HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
conversão automática das ferramentas em `ToolDefinition` e registo com
namespace `mcp.<namespace>`.

Suporta também respostas `text/event-stream` (streamable HTTP) e envia
a notificação `notifications/initialized` após o handshake. Usa
`MCP-Protocol-Version` (predefinição `2025-06-18`, com fallback) e reutiliza
`Mcp-Session-Id` quando o servidor o devolve. Os erros HTTP
incluem o corpo da resposta para tornar diagnosticáveis os 400.
Os resultados das ferramentas são normalizados para texto: blocos `text`,
caso contrário `structuredContent` ou JSON; um resultado com `isError`
torna-se um erro da ferramenta.

Autenticação por servidor:

```yaml
mcp_servers:
  - endpoint: https://mcp.example.com/mcp
    namespace: example
    auth:
      type: bearer          # ou "header"
      token_env: MCP_EXAMPLE_TOKEN
      # header: X-API-Key  # apenas com type: header
```

O token lê-se apenas do ambiente e não aparece na auditoria. Se faltar,
o servidor é ignorado com `mcp.failed` e o harness continua; os outros
servidores permanecem disponíveis.

### OAuth interativo

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # sem, dynamic registration
    # client_secret_env: MCP_CLIENT_SECRET
    scopes: [mcp.read]
    audience: api.atlassian.com  # opcional, para provider 3LO
    redirect_port: 8765       # 0 = porta aleatória
    token_cache: ~/.hagar/oauth/example.json
    timeout: 300
```

Fluxo authorization code + PKCE, com callback em
`http://localhost:<port>/oauth/callback` e abertura do browser. Se o
scope contiver `offline_access`, é adicionado `prompt=consent`.
Os metadados são descobertos a partir de `.well-known` (RFC 9728 para a
recurso, RFC 8414 para o authorization server); se faltar `client_id`
usa-se o registo dinâmico. Os tokens ficam num ficheiro local com
permissões restritas (`0600` onde o sistema as suporta), com refresh
automático e retry uma vez em `401`.

Ctrl-C durante a espera do callback fecha o servidor local e sai
com código 130, sem traceback.

Limites: sem device flow, DPoP, mTLS ou client assertion; o browser tem de
poder alcançar o callback local. Se o callback não chegar, o
terminal pede para colar o URL de redirecionamento.

## 3.8 Vault (`memory/vault.py`)

Acesso ao vault Obsidian com percursos relativos à raiz e
proteção contra a saída do vault. Oferece leitura, escrita, append,
listagem dos ficheiros e `load_all` para a leitura recursiva. A semântica
da memória vive em `memory/store.py` (§3.11).

## 3.9 Audit log (`core/audit.py`)

Ficheiro JSON Lines append-only. Cada linha tem timestamp UTC, `session` e
`event`; os eventos de uma mesma pergunta partilham um id `turn`.

```text
harness.start      provider, modelo, raízes, permissões, ferramentas, vault
turn.start         pergunta, limite de ferramentas, modo nativo
llm.tool_choice    escolha do modelo, argumentos, mode=native
llm.native_fallback provider sem ferramentas nativas, passagem ao texto
llm.protocol_error resposta não conforme (texto integral, truncado)
llm.repaired       reparação bem-sucedida
llm.repair_failed  reparação falhada
tool.call          ferramenta, argumentos, índice
tool.result        resultado, output/erro, duração em ms
turn.answer        resposta final, número de ferramentas usadas
turn.error         fase e mensagem
turn.stop          limite atingido
mcp.loaded         namespace e ferramentas importadas
mcp.failed         namespace e erro
llm.failed         provider não construível (ex. chave em falta)
harness.stop       saída limpa (se faltar, o processo foi morto)
memory.enabled     raiz, subdir, turnos de contexto
memory.disabled    motivo da desativação
memory.context     turnos e skills injetados no prompt
memory.turn        turno guardado no vault
memory.failed      fase e erro
```

Propriedades:

- escrita best effort: um erro de I/O não para o harness e é
  assinalado uma única vez em stderr;
- truncamento configurável (`audit.max_field_chars`, predefinição 2000);
- cadeia de hash (`prev`/`hash`) verificável com `verify_chain`;
- rotação em `<file>.<timestamp>` acima de `audit.max_bytes` (0 desativa);
- retention: `audit.max_files` (predefinição 100) mantém no máximo N ficheiros,
  incluindo o ativo; os backups mais antigos são eliminados;
- com `audit.include_outputs: false` o output das ferramentas é registado
  apenas como dimensão;
- valores não JSON tornados serializáveis;
- nenhuma chave API no log;
- o log contém também o output das ferramentas (portanto conteúdos de ficheiros):
  tem de ser protegido como o workspace.

## 3.10 Permissões (`core/permissions.py`)

O modelo é uma matriz sujeito × objeto:

- **Capability** (`IntFlag`): o que uma operação pode fazer
  (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`, `FILESYSTEM_CREATE`,
  `FILESYSTEM_DELETE`, `FILESYSTEM_EXEC`, `MEMORY_READ`,
  `MEMORY_WRITE`, `NETWORK`, `MCP_CALL`, `COMPUTE`). Combinam-se com `|`;
  a verificação é sempre de subconjunto.
- **Effect** (`IntEnum`): `ALLOW`, `ASK`, `DENY`. Em caso de conflito
  vence o valor mais alto (`DENY > ASK > ALLOW`).
- **Rule**: capability + efeito + filtros opcionais `tools` (glob),
  `paths` e `namespaces` (prefixos) + `reason`.
- **Subject**: quem pede (agente, utilizador, sistema), com regras e
  default (`DENY` se não especificado).
- **Resource**: o objeto da decisão (para já uma ferramenta com as suas
  capability; no futuro também notas e percursos).
- **Decision**: efeito, motivo e regra aplicada.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. o recurso tem de oferecer as capability pedidas;
2. o **teto de sistema** (derivado de `permissions.read/write/shell`)
   tem de as conceder;
3. para cada capability aplicam-se as regras do sujeito: vence a
   mais específica (número de filtros, depois longitude do prefixo), em
   caso de empate o efeito mais restritivo; sem regras vale o default;
4. com várias capability pedidas vale o AND: vence o efeito pior.

`ASK` não é uma decisão: é uma pergunta a um humano. O
`ConfirmationProvider` coloca-a — `ConsoleConfirmation` pergunta
`lo faccio? (y/N)` com default N — e sem canal de confirmação vale
`DENY`. Uma GUI pode implementar o mesmo protocolo com um diálogo
modal.

Na CLI `core/input_broker.py` é o único proprietário da consola:
distribui prompts, confirmações e as teclas `F5`/`F8`, define o título do
terminal como sinal de atenção e restaura o modo normal no
fim. Em stdin não interativo recai sobre `input()`.

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

`policy.yaml` é lido **antes** de construir o LLM. Se não for
legível ou não for válido, o harness aplica `DENY` a todas as políticas,
registra-o na auditoria (`policy.failed`) e assinala-o no chat; o resto
do harness continua a funcionar. Também um sujeito ausente degrada para
`DENY`.

O controlo ocorre em `ToolRegistry.execute`, único ponto de
execução, e produz os eventos `permission.decision` e
`permission.confirmation`.

O scope `paths` compara o percurso **escrito pelo modelo**
(normalizado), não o resolvido pela sandbox: um percurso absoluto ou
um `chdir` podem não corresponder a um prefixo relativo, e o
resultado permanece `DENY` (fail closed).

## 3.11 Memória (`memory/store.py`, `memory/tools.py`)

**Backend predefinido: SQLite.** `memory/sqlite_store.py` e
`memory/database.py` usam uma base de dados local (`%LOCALAPPDATA%/Hagar/memory.db`
ou `HAGAR_MEMORY_DB`) como fonte de verdade para sessões, turnos, skills e
summaries. O SQLite usa WAL, transações e `busy_timeout`; o backup é
`VACUUM INTO`. O backend `markdown` descrito abaixo permanece disponível
apenas por compatibilidade e já não é o default.

**Episódica.** O harness enfileira cada turno concluído numa nota por
sessão:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter com `session`, `type: chat`, `created`; corpo com uma
secção por turno (`## <timestamp> · <turn>`), pergunta e resposta. Não
são guardados os outputs das ferramentas: esses ficam na auditoria.

No início de cada turno o Agent injeta no prompt os últimos
`memory.context_turns` turnos (0 desativa a injeção), truncando
pergunta e resposta. Com `memory.context_skills > 0` acrescenta até N
**skills confirmadas** pertinentes à pergunta, por match lexical em
título, tags e conteúdo; as candidatas e as arquivadas nunca entram.
O bloco está etiquetado como dados, não instruções. Um erro de memória
não para o turno: é registado `memory.failed`.

**Semântica.** O modelo pode propor uma memória com três ferramentas:

| tool | capability | namespace |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

`create_skill` escreve `<vault>/Hagar/skills/<slug>.md` com frontmatter
`id`, `title`, `kind` (`fact`/`procedure`), `status: candidate`, `tags`,
`source_session`, `source_turn`, `model`, `created_at`. O slug é
seguro (apenas ASCII, nenhum percurso); um título já existente não é
sobrescrito e devolve `duplicate: true`.

`get_context` devolve os últimos turnos ou procura por palavra-chave
nas sessões passadas; `list_skills` filtra por `kind` e `status`.

**Ciclo de vida.** Os estados são `candidate`, `confirmed`, `archived`.
O LLM cria apenas candidatas; a transição é humana, da CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` mostra uma candidata de cada vez com provenance e
conteúdo, depois pede `y/N/a/s/q` (confirma, deixa, arquiva, salta,
sai). A confirmação escreve `reviewed_at`; `archive` é reversível com
`confirm`. Cada transição produz `memory.status` ou `memory.review`
na auditoria. As notas permanecem ficheiros Obsidian: modificar `status` no
frontmatter tem o mesmo efeito.

**Configuração**:

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

### Memória de projeto

A memória de projeto é separada das skills:

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

Cada projeto tem um `index.md` com estado, última atividade, summary e
contagem das decisões ativas. Cada decisão tem estado
`candidate`/`active`/`superseded`/`archived`, alternativas, motivação,
provenance e `auto_saved`. As decisões não se reescrevem: uma nova
decisão pode substituir uma antiga.

Com `memory.backend: sqlite` projetos e decisões usam as tabelas
`projects` e `decisions` da mesma base de dados; o backend Markdown
legacy continua a usar o Vault.

No arranque o Hagar mostra os projetos ativos e "atividade livre":

```text
/project list
/project new <nome>
/project select <nome>
/project free
/project status
/project archive <nome>
/project unarchive <nome>
```

Os override não interativos são `--project <nome>` e `--free`.

No fim da sessão:

1. o transcript é movido para `archive/chat/`;
2. é gerado um summary com o modelo, com fallback mecânico;
3. o summary é guardado com link e hash do transcript;
4. se houver um projeto, o LLM propõe decisões `candidate`;
5. o utilizador pode revê-las; se recusar, ficam `candidate` com
   `auto_saved: true`.

O contexto injetado usa o **índice** do projeto: summary, títulos
das decisões ativas e contagem, não todos os corpos. Os detalhes leem-se
com `memory.project_context(query=..., limit=...)`. O bloco
global é limitado por `max_context_chars`; se for cortado,
a auditoria registra `memory.context_trimmed`. Não é uma estimativa de tokens: é
um budget em caracteres, determinístico.

Quando um projeto ultrapassa `project_max_active`, o Hagar pergunta se
o deve arquivar. O arquivo é reversível e não apaga nada.

**Consulta do arquivo.** Os transcripts arquivados têm o `project`
no frontmatter. A pesquisa e a leitura são on demand:

```text
/memory archive search <texto>
/memory archive read <session> [offset] [limit]
```

As mesmas ferramentas são expostas como `memory.archive_search` e
`memory.archive_read`; a pesquisa devolve session, turn, timestamp,
projeto e snippet, a leitura pagina os turnos. Não há injeção
automática do arquivo no prompt: o summary continua a ser o índice, o
transcript é a fonte a consultar quando necessário.

Se `vault.path` não existir ou não for escrevível, a memória é
desativada com um aviso no chat e `memory.disabled` na auditoria; os
outros componentes continuam a funcionar. As escritas de memória estão
sujeitas às políticas (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.11.1 Service layer (`core/service.py`)

`HarnessService` é a API estável por cima do `Harness`: não lê de
`input()`, não escreve em stdout e não conhece a CLI. Expõe:

- `ask(question)` com eventos `turn.start`, `turn.answer`, `turn.error`;
- eventos de ferramentas e permissões reencaminhados por `Agent` e `ToolRegistry`:
  `tool.call`, `tool.result`, `permission.decision`,
  `permission.confirmation`;
- `status()` com modelo, projeto, memória, auditoria, política e ferramentas;
- `list_projects()`, `current_project()`, `set_project()`,
  `clear_project()`, `create_project()`;
- `finish_session()`.

Os eventos são `ServiceEvent(type, data, ts)` e podem ser consumidos
por um sink (CLI, GUI, testes). A CLI atual usa o service para os turnos, a
seleção de projeto e o fecho da sessão.

## 3.11.2 Command service (`core/command_service.py`)

`CommandService` transforma os comandos slash em `CommandResult`:

```text
command, ok, lines, data, error, requires_input
```

Gere `/help`, `/tools`, `/status`, `/mcp`, `/audit`, `/project` e
`/memory` sem escrever em stdout. A CLI imprime `lines`; a GUI usará
`data`. A revisão interativa de `/memory` continua confiada ao `MemoryCLI`
porque exige input humano. A CLI usa o command service para todos os
comandos slash, exceto `/memory review`.

## 3.11.3 Web GUI (`core/web.py`)

`hagar web` arranca um `ThreadingHTTPServer` local com:

- `GET /` página de chat;
- `GET /static/style.css` e `/static/app.js` (assets em `web/`);
- `GET /api/events` stream SSE;
- `POST /api/message`, `/api/confirm`, `/api/project`, `/api/stop`,
  `/api/new-chat`, `/api/resume`;
- `GET /api/status`, `/api/projects`, `/api/pending`;
- `GET /api/history`, `/api/history/<session>`;
- `GET /api/tools`, `/api/audit`, `/api/thinking`;
- `GET /api/memories`, `/api/memory?path=...`.

Os separadores da GUI são Chat, Chat history, Tool output, Audit, Thinking e
Memories. A barra lateral mantém projeto, estado e tokens; o histórico está no
separador dedicado. `SessionLog` conserva os eventos da sessão para Tool
output e timeline; Audit lê o JSONL; Thinking privilegia o
reasoning exposto pelo provider e, caso contrário, mostra a timeline. Memories
lê o índice, excluindo chat, arquivo e summary.

Um clique num chat passado chama `POST /api/resume`: o transcript
é recarregado e a sessão de auditoria/memória volta a esse id, para que os
novos turnos continuem o mesmo chat. `POST /api/new-chat` chama
`MemoryStore.new_session()` e muda a sessão, sem tocar nos
transcripts anteriores.

Os assets estáticos vivem em `web/` (`index.html`, `style.css`,
`app.js`). `render_index()` injeta apenas o token; o resto é servido
verbatim com whitelist e `importlib.resources`.

A GUI é um adapter: usa `HarnessService`, `CommandService` e
`QueueConfirmationProvider`. As confirmações ASK bloqueiam a thread do turno
num `threading.Event`; o servidor permanece livre e desbloqueia o pedido com
`POST /api/confirm`. Um timeout vale como recusa.

A barra lateral mostra os tokens acumulados da sessão: `UsageLedger` recebe
o usage de cada chamada LLM através de `usage_sink` e publica
`usage.updated` em SSE.

**Stop:** `POST /api/stop` chama `Agent.cancel()`; o agente controla
o evento entre um passo e outro e lança `AgentCancelled`. O turno
interrompe-se de forma cooperativa, não aborta um pedido HTTP já
em curso.

**Vision:** `POST /api/message` aceita `images` como data URL
PNG/JPEG/WebP (máx. 4, 10 MB cada); o body JSON pode chegar a
64 MB. `core/images.py` valida e converte; `Agent.ask(question,
images=...)` constrói content multimodal. Os adapter
OpenAI-compatíveis/LM Studio usam `image_url`; Claude usa blocos
`image`; Gemini usa `inlineData`. O LM Studio não aceita WebP
diretamente: a GUI converte-o em PNG. A imagem não entra na
memória Markdown nem na auditoria.

Segurança: bind predefinido `127.0.0.1`, token aleatório injetado na
página, cabeçalho `X-Hagar-Token` para as API e `?token=` para SSE. Não é
multiutilizador e ainda não expõe a modificação do Vault.

## 3.11.6 Vision input (`core/images.py`)

`ImageInput` valida data URL, MIME e dimensão; `Agent.ask` usa partes
canónicas (`text`, `image`) e cada backend tradu-las no seu próprio
formato. O texto do stop e das imagens é separado do conteúdo
persistente: a memória conserva apenas a pergunta e a resposta.

`vision.open` lê uma imagem da sandbox, valida-a com magic number
e devolve-a como `ToolResult.images`. O ciclo `Agent` anexa
a imagem a uma mensagem de utilizador sintética antes da chamada
seguinte, para que o modelo a veja sem receber base64 no texto da
ferramenta. Limites: 4 imagens por turno, 10 MB por imagem, PNG/JPEG/WebP.
O child pode usar `vision.open` no seu próprio workspace read-only.

O áudio não está implementado. O canal de anexos seria reutilizável, mas
são necessários um contrato provider audio-native diferente, formatos/decoder e uma
escolha explícita entre ASR e compreensão de áudio; está no roadmap sem
timeline.

`memory/export.py` exporta a base de dados SQLite em Markdown:
`Hagar/chat/`, `Hagar/skills/`, `Hagar/summaries/`,
`Hagar/projects/<id>/index.md` e `decisions/`. A escrita é atómica
(temp + `os.replace`) e o comando recusa um destino não vazio
sem `--force`.

`memory_fts` é uma tabela FTS5 na mesma base de dados, com colunas
`entity`, `entity_id`, `kind`, `project`, `status`, `title`, `body`.
`SqliteMemoryIndex.search` usa `MATCH`, `bm25()` e `snippet()`; se o FTS5
não estiver disponível recai sobre `LIKE`. `memory/import_markdown.py` importa
a mesma estrutura com upsert e reconstrói o índice FTS.

## 3.11.4 Token usage (`core/usage.py`)

`TokenUsage` normaliza input, output, cache e reasoning. As funções
`usage_from_openai`, `usage_from_anthropic`, `usage_from_gemini` e
`usage_from_ollama` leem os campos nativos das respostas.

`LLMClient._set_usage()` atualiza `last_usage` e chama o `usage_sink`
do cliente. `HarnessService` possui o `UsageLedger`, liga-o ao
cliente e publica `usage.updated`; a GUI usa-o na barra lateral e `/usage`
lê-o da CLI. O usage do provider é a
verdade; uma estimativa local permanece apenas como fallback.

## 3.11.5 Memory index (`memory/index.py`)

`MemoryIndex` é um índice SQLite derivado do Vault Markdown:

- tabelas `documents`, `meta` e `documents_fts` (FTS5);
- sync incremental por hash/mtime/size;
- `rebuild()` reconstrói de zero;
- pesquisa com filtros `project`, `kind`, `status`;
- fallback `LIKE` se o FTS5 não estiver disponível;
- base de dados nos dados locais da aplicação, não no Vault sincronizado.

A ferramenta `memory.search` usa o índice; `/memory reindex` e `/memory stats`
expõem manutenção e estado. Com o backend predefinido SQLite a
fonte de verdade é `memory.db`; o antigo `MemoryIndex` permanece apenas para o
backend Markdown legacy.

## 3.11.7 Decision tools (`core/decisions.py`)

`DecisionRegistry` seleciona um `DecisionProvider` e `decision.choose`
expõe a escolha ao modelo. Os providers built-in são:

- `llm`: pede ao cliente LLM um JSON com `choice` e `probabilities`,
  valida as label e normaliza as probabilidades;
- `linear`: carrega um modelo JSON local com label, pesos e bias e usa
  softmax para produzir as probabilidades.

A capability `DECISION` é separada de `COMPUTE`, `NETWORK` e
`FILESYSTEM_*`; os detalhes e o formato do modelo estão em
`DECISIONS.md`. Jev/Kev ainda não são adapter nativos.

## 3.11.8 Hi-Fi (`core/hifi.py`)

`HiFiResolver` executa um pré-passo antes do ciclo agêntico:

1. pede ao modelo as interpretações com probabilidades;
2. normaliza e ordena as probabilidades;
3. se a margem entre a primeira e a segunda ultrapassar `hifi.margin`,
   substitui o pedido pela interpretação escolhida mais o texto original;
4. caso contrário, pede ao modelo uma pergunta de esclarecimento.

O evento `hifi.interpretations` registra as probabilidades e o eventual
esclarecimento. Um JSON inválido produz `hifi.failed` e o turno
prossegue sem pré-passo.

## 3.11.9 Checkpoint (`core/checkpoints.py`)

`HarnessService.ask` abre um `WorkspaceCheckpoint` na sandbox. O
checkpoint não copia o workspace: anota apenas os ficheiros que uma mutação
está prestes a alterar. `delete_file`, `rename` e `copy_file` registam também
o destino. `/undo` restaura o último checkpoint concluído.

Limite: 32 MB de snapshot, apenas ficheiros regulares, apenas o último turno.
Se o checkpoint estiver incompleto, o undo é recusado.

## 3.11.10 Guardas de runtime e contexto (`core/tool_registry.py`, `core/context.py`)

`ToolRegistry` aplica:

- `tools.timeout` por chamada individual, através de worker daemon;
- `tools.repeat_limit` sobre o hash `tool + argumentos` por turno.

O timeout é best effort: um handler Python já iniciado não é
morto. O repeat guard repõe a zero a contagem em cada `Agent.ask`.

`OutputSpiller` move os outputs acima de 12.000 caracteres
para o `ArtifactStore` e devolve um resumo com `artifact_id`.
`ContextCompactor` substitui as mensagens mais antigas quando o contexto
ultrapassa 24.000 caracteres, preservando as últimas 8 e as mensagens system.

## 3.11.11 AIsh (`core/aish.py`, `local_tools/aish_tool.py`)

`aish.exec` implementa uma linguagem de comando, não uma shell host.
`AishExecutor` faz parsing com `shlex`, recusa redirecionamentos, operadores,
variáveis e command substitution, e traduz cada comando numa chamada
ao `ToolRegistry`. A capability `AISH` é negada pela política predefinida;
ativá-la exige uma modificação explícita:

```yaml
- capabilities: [AISH]
  effect: allow
  tools: ["aish.*"]
```

Os comandos internos conservam as regras das ferramentas subjacentes: ativar
`aish.exec` não ativa `filesystem.delete_file`.

## 3.11.12 `text.transform` (`local_tools/text_transform_tool.py`)

Ferramenta read-only com operações enumeradas: `grep`, `sort`, `uniq`, `cut`,
`tr`, `wc`, `head`, `tail`, `sed_replace`. Aceita um path da sandbox
ou texto inline; aplica limites de input, output, pattern e match.

Capability:

```text
FILESYSTEM_READ | COMPUTE
```

Não escreve ficheiros. AIsh usa-a para os comandos textuais; o salvamento do
resultado passa por `filesystem.write_file`/`create_file` com o gate
read-before-write.

## 3.11.13 `dev.run` (`core/dev_recipes.py`, `core/dev_runner.py`)

`DevRecipeLoader` lê `recipes.yaml` uma única vez no arranque e
conserva um snapshot imutável com hash. O ficheiro tem de estar fora da
sandbox escrevível.

`DevRunner` executa uma receita:

- valida parâmetros tipados e `cwd`;
- copia o projeto para uma diretoria temporária;
- executa um único argv com `shell=False`;
- usa um ambiente mínimo;
- aplica timeout e kill do process group;
- separa stdout/stderr;
- limita o output;
- registra auditoria.

A capability `DEV_EXEC` é DENY por predefinição. `dev.run` não aceita comandos
arbitrários e não usa containers: as receitas são fidedignas; a sandbox não
isola o processo host. O container fica congelado para um futuro
acesso direto a filesystem/programas reais.

## 3.11.14 Boxed transform (`core/boxes.py`)

As box são funções LLM bounded com prompt fixo, input/output em ficheiro
e nenhuma memória, ferramenta ou autonomia.

Ferramentas:

```text
box.list
box.run
```

Box iniciais:

```text
summarize
translate
extract_json
```

`BoxRunner` lê o input da sandbox, aplica chunking onde é necessário,
chama o cliente LLM, valida o output JSON e escreve o resultado com o
gate read-before-write. `BOX_EXEC` é DENY por predefinição.

## 3.11.15 Hagar Flow (`core/flow/`)

`validate()` faz parsing do código com `ast.parse`, recusa imports, classes,
funções, lambda, try, dict/set comprehension, comprehension com mais de
um `for`, dunder e chamadas dinâmicas, e verifica as primitivas
disponíveis. As list comprehension com um único `for` e `if` opcionais
são suportadas.

`FlowRunner` interpreta a AST validada sem `eval`/`exec`:

- scope linear;
- budget de steps, iterações, tool call e timeout;
- primitivas `fs.*`, `box.*`, `memory.*` e `project.context` passadas por
  um registry interno;
- política e confirmações para cada primitiva;
- erros com linha e coluna.

`FLOW_EXEC` é DENY por predefinição. `flow.run` nunca repara o código:
`flow.repair` propõe um candidato válido sem o executar, com um
máximo de `flow.repair_attempts` tentativas. Erros de runtime, política,
confirmação e timeout não são reparados. O HIR ainda não existe:
a AST validada é o IR do MVP.

## 3.12 Arranque e packaging

O projeto instala-se com `pip install -e .` e declara os pacotes em
`pyproject.toml`. O entry point é `hagar = "hagar:main"`. A versão
corrente é `0.7.0`.

A configuração de exemplo é `hagar.example.yaml`; `hagar.yaml` é um
ficheiro local ignorado pelo git. O Vault predefinido do exemplo é
`./vault` e tem de ser criado antes do arranque.

```text
hagar --config PATH       ficheiro de configuração
hagar --model NAME        substitui model.name
hagar --project NAME      seleciona um projeto ativo
hagar --free              arranca em atividade livre
hagar --no-memory         desativa a memória para a sessão
hagar --no-native-tools   usa o protocolo JSON textual
hagar --version
```

A configuração procura-se nesta ordem: `--config`, variável
`HAGAR_CONFIG`, `./hagar.yaml`. `python -m hagar` funciona a partir da
diretoria do projeto.

A CI GitHub Actions executa a suite em Linux, macOS e Windows com
Python 3.11/3.12/3.13, constrói sdist e wheel, executa `twine check` e
testa a instalação da wheel. O workflow `Release` parte de uma tag
`v*`, verifica que a tag corresponde à versão do pacote e
cria a release GitHub com os artefactos.

Os testes live estão excluídos da suite normal e ativam-se com
`--live`: verificam o Ollama e os providers remotos (estes últimos apenas se
a chave API estiver presente).

## 3.13 Ferramentas locais (`local_tools/`)

Não são servidores MCP: são providers locais que registam `ToolDefinition`
no registry e vivem fora do core, num pacote separado.

| módulo | ferramenta | capability |
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

- `clock.now` devolve hora local, data, fuso, offset UTC e epoch.
- `calendar.date` converte a data local, ou uma data ISO opcional, no
  calendário juliano prolético ou no calendário islâmico tabular
  (Kuwaiti algorithm). O calendário islâmico tabular pode diferir em
  um dia dos baseados na observação ou em Umm al-Qura.
- `think.echo` devolve exatamente a string recebida; serve para
  externalizar uma passagem intermédia nas cadeias de raciocínio.
- `text.diff` devolve um diff unificado entre dois textos, com input
  máximo de 20000 caracteres, output máximo de 20000 e `context` 0..10. Não
  aplica o diff.
- `url.parse` decompõe scheme, host, porta, path, query e fragment sem
  DNS ou rede; limita o URL a 4096 caracteres e os parâmetros a 100. Se
  o URL contiver credenciais, redige-as no output.
- `clock`, `calendar`, `think`, `text` e `url` não acedem ao filesystem
  nem à rede, e recaem na regra `COMPUTE` allow.
- A calculadora usa uma whitelist AST, não `eval()`, com limites sobre
  expressão, número de nós e expoente.
- `feed.read` descarrega com `requests` (timeout 15 s, máximo 5 MB), aceita
  apenas URL http/https e usa `feedparser`; a política `NETWORK` é `ask`.
- SSRF: cada host é resolvido com `getaddrinfo` e cada endereço tem de
  ser global; loopback, redes privadas, link-local, multicast e
  reservados são recusados. Os redirects não são automáticos: cada
  `Location` é revalidado e param após 3 saltos. Um URL com
  credenciais é recusado.
- `permissions.network: true` é necessário para que o teto de sistema
  conceda `NETWORK`; `COMPUTE` está sempre no teto mas a política pode negá-lo.
- `permissions.agents: true` é necessário para `AGENT_SPAWN`; a política
  tem ainda de permitir `agent.*`.
- `local_tools` está declarado em `pyproject.toml` e é instalado com o
  projeto.

As ferramentas built-in são registadas por `local_tools/plugins.py` através
do mesmo contrato `ToolPlugin` dos plugins externos. Os plugins externos
descobrem-se com o entry point `hagar.tools` e recebem um `PluginContext`.
Política e sandbox permanecem no registry: um plugin não pode conceder
permissões. Um plugin avariado é ignorado e registado na auditoria, sem
parar os outros.

## 3.14 Plugin

`core/plugins.py` define:

- `ToolPlugin` + `PluginContext` para as ferramentas;
- `LLMProvider` para os providers LLM;
- descoberta via `importlib.metadata.entry_points`;
- isolamento dos erros e auditoria `plugin.loaded`/`plugin.error`.

Os providers built-in estão em `llm/plugins.py` e são registados antes
dos externos. Um provider externo não pode substituir um nome built-in.
Os plugins Python são trusted e correm in-process; para extensões não
fidedignas a fronteira permanece o MCP ou um processo separado. O contrato completo
está em `PLUGINS.md`.

## 3.15 Subagentes assíncronos

`core/subagents.py` implementa:

- `agent.spawn/status/wait/result/cancel` e `agent.run` síncrono;
- `reason` obrigatório no spawn, registado na auditoria;
- capability `AGENT_SPAWN` separada: o child não a recebe e não pode
  criar outros agentes;
- política do child estritamente mais restritiva; políticas iguais ou mais
  amplas são recusadas com `SubagentPolicyError`;
- timeout de parede de 5 minutos, cooperativo, com estado `timed_out`;
- `agent_id` em todos os eventos de auditoria do pai, do child e do
  registry;
- até dois subagentes concorrentes;
- mesmo modelo local mas cliente LLM separado;
- workspace temporário privado para cada child;
- input copiados do workspace do pai;
- outbox `artifact.put`/`artifact.put_file` e `mailbox.send` para o
  child;
- artifact store temporário (máx. 50 MB por artifact, 256 MB por turno)
  e mailbox em memória (máx. 64 KB por mensagem);
- leitura bounded do pai com `artifact.read`, `artifact.list`,
  `mailbox.inbox/read/ack`;
- `artifact.save_to` copia o artifact inteiro para um caminho escrevível da
  sandbox do pai, sem passar pelo contexto;
- capability `AGENT_DATA`;
- registry filtrado a `FILESYSTEM_READ`, `MEMORY_READ`, `COMPUTE` e
  `AGENT_DATA`;
- exclusão de `filesystem.chdir` e `agent.*`;
- nenhuma escrita de memória;
- ASK do child encaminhadas ao utilizador pelo `ParentBridgeConfirmation`,
  timeout de 180 segundos e DENY na expiração; o pai LLM não aprova;
- usage separado;
- auditoria `agent.spawned/started/finished/cancelled/failed`;
- no fim do turno, `artifact.discarded` para artifact não exportado, com
  motivo `unread` ou `read_but_not_saved` e metadados sem conteúdo;
- cleanup de workspace e job no fim do turno.

`AuditLog.record` é serializado com lock para as escritas concorrentes.
Ainda não há export de artifact, budget de tokens/tempo, aninhamento ou
GUI dedicada. Os detalhes estão em `SUBAGENTS.md`.

---

# 4. Modelo de segurança

- O agente não vê o filesystem real: apenas percursos resolvidos dentro da
  sandbox.
- As operações passam apenas pelo `ToolRegistry`; nenhuma shell host.
- As permissões são declaradas na configuração e nas políticas, e são
  aplicadas pela sandbox e pelo `PermissionEvaluator`; as raízes aninhadas
  podem restringir as permissões.
- Os erros são dados: uma recusa é devolvida ao modelo como
  resultado da ferramenta, não escondida.
- Cada ação deixa um rasto na auditoria, com sessão e turno.

---

# 5. Desenvolvimento

- Suite: `./tools/run_tests.sh` (Linux/macOS) ou
  `.\tools\run_tests.ps1` (Windows). No Windows: 892 passed, 2 skipped
  (symlink não disponíveis sem Developer Mode). Em Debian Linux
  (2026-11-12): todos os testes verdes, incluindo os symlink (894 passed, 0
  skipped). Detalhes e motivação do shim em README §3.1.
- Testes live: `./tools/run_tests.sh --live` (Linux/macOS) ou
  `.\tools\run_tests.ps1 --live` (Windows) — mais 9 testes (Ollama;
  providers remotos se as chaves estiverem presentes).
- Comparação de modelos: `python tools/bench_models.py` (README §3.5).
- Comparação de protocolos: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- A suite normal não toca na rede: Ollama e MCP são simulados.

## 5.1 Multiplataforma

- Os percursos internos usam `pathlib.Path`; os mostrados ao agente
  usam sempre `/` e a raiz virtual `/home/ai`.
- `filesystem.sandbox` contém caminhos do sistema anfitrião, absolutos ou com
  `~` se o utilizador o escolher: `Path.expanduser()` resolve a home apenas
  quando o caminho a usa. Não se assume que exista uma home dedicada.
- Cada mount tem um alias explícito e único (sem distinção de maiúsculas); o
  percurso físico pode estar em qualquer volume.
- `tools/run_tests.sh` é o runner POSIX; `tools/run_tests.ps1` e
  `tools/pytest_shim` servem apenas à sandbox Windows com token
  restrito.
- O único ramo explicitamente Windows que resta é a data de criação em
  `stat`: `st_birthtime` onde disponível, caso contrário `st_ctime` em
  Windows; em Linux `created_at` pode ser `None`.
- As API externas (OAuth, MCP, LLM) usam HTTP e `webbrowser`, não
  comandos de sistema.
- A CI GitHub Actions cobre Linux, macOS e Windows com Python
  3.11/3.12/3.13; symlink, permissões dos tokens OAuth e callback loopback
  permanecem por verificar com testes live, não na suite offline.

---

# 6. Limites conhecidos e dívida técnica

- `PermissionEvaluator` cobre a v1: faltam os sujeitos dinâmicos, as
  confirmações GUI e as capability MCP atribuídas pela configuração.
- A chamada nativa depende do modelo: alguns ignoram as ferramentas ou
  devolvem várias chamadas; o fallback textual cobre os erros, não
  a qualidade da escolha.
- O cliente MCP suporta bearer/header e OAuth authorization code; não
  gere device flow, DPoP, mTLS ou client assertion.
- A revisão das skills é manual na CLI; falta uma GUI.
- A pesquisa na memória é por palavra-chave, sem índice nem
  embedding.
- O contexto injetado usa turnos recentes globais e até 3 skills
  confirmadas por match lexical, sem seleção semântica.
- A memória não apaga chats ou skills por antiguidade: `archive` é
  a única remoção do contexto.
- A auditoria tem rotação e retention (`max_files`), mas não compactação
  das sessões nem uma ancoragem externa da cadeia.
- `feed.read` valida os endereços e os redirects, mas permanece o caso DNS
  rebinding: `requests` resolve o nome uma segunda vez no momento
  da ligação; é necessário um resolver fixado (pinned).
- A calculadora não é um CAS: gere apenas expressões numéricas
  limitadas, não simbólicas.
- `stat().created_at` é `None` em Linux quando falta `st_birthtime`; não
  é inventada uma data de criação.
- Dois alias não podem apontar para o mesmo caminho físico: o alias
  identifica um mount e o output virtual tem de permanecer unívoco.

## 6.1 Responsabilidade do utilizador: hard link, mount e TOCTOU

**O Hagar não controla os hard link, os mount/junction e as race TOCTOU
dentro das diretorias permitidas.** Não é um defeito do Hagar: a sandbox é
path-based e não usa handle/file descriptor para toda a operação.

Um hard link é um segundo nome do mesmo inode, não tem um target de
percurso e a sandbox não pode saber se existe outro nome fora. Um
mount ou uma junction pode expor outro filesystem mantendo-se dentro
do prefixo do percurso. Uma race TOCTOU pode mudar um componente entre o
controlo dos symlinks e a operação real: o Hagar não usa `openat2`,
`O_NOFOLLOW` em cada componente ou handle Windows, pelo que não garante
atomicidade entre check e acesso.

As ferramentas filesystem do Hagar não criam hard link. Se um hard link ou um
mount já existir dentro de uma diretoria da sandbox, o Hagar trata-o como
um ficheiro ou diretoria normal e pode lê-lo, modificá-lo ou apagar o seu
nome interno.

A responsabilidade é, portanto, dividida:

- **O Hagar garante** que os percursos resolvidos permanecem dentro do alias no
  momento do controlo, que os symlink são invisíveis, que as permissões
  `R`/`W`/`X` são aplicadas e que os caminhos reais não entram
  no output do modelo.
- **O utilizador garante** que as diretorias configuradas em
  `filesystem.sandbox` não contêm hard link, mount ou junction para
  conteúdos que não devem ser acessíveis, e que nenhum processo
  concorrente não fidedigno pode modificar essas diretorias durante
  a execução, se quiser isolamento total.

As race TOCTOU exigem um ator local concorrente com acesso em
escrita às diretorias da sandbox: não são um caso acidental
do uso normal, mas um cenário malicioso ou de ambiente comprometido.
Para um isolamento forte são necessários um volume dedicado, um utilizador separado,
um mount namespace ou um container; não é tarefa do resolver de paths.

Os pontos estão fechados como **responsabilidade do utilizador**, não como dívidas
técnicas do Hagar. Hard link, mount/junction e race TOCTOU não são
detetados nem bloqueados por esta versão.

---

# 7. Mapa da documentação

- `MANUAL.md` — manual do utilizador: comandos, configuração, política, default.
- `ARCHITECTURE.md` — este documento: como é o sistema hoje.
- `ROADMAP.md` — o que fazer, decisões tomadas e pontos abertos.
- `PLUGINS.md` — contratos para ferramentas e providers LLM plugin.
- `DOCUMENT_TOOL.md` — especificação da document tool, esquema do grafo e
  protocolo do host nativo.
- `SUBAGENTS.md` — MVP subagentes e limites.
- `CHANGELOG.md` — história das versões.
- `README.md` — arranque, configuração, testes.
