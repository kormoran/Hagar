# HAGAR — Arquitetura

Versão: 0.2.0 (em desenvolvimento)
Última atualização: 2026-11-03

---

# 1. O que é o Hagar

O Hagar é um harness para LLM escrito em Python, concebido para a execução
resiliente de modelos de linguagem.

O objetivo não é uma conversa com um modelo, mas um ambiente operativo
**seguro** no qual um LLM possa usar ferramentas, consultar uma memória
persistente e interagir com sistemas externos sem aceder diretamente aos
recursos reais da máquina anfitriã.

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
  │     ├── DeepSeekClient
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
| `model` | sim | provider, nome, host, max_tokens, api_key_env, native_tools |
| `vault` | sim | caminho do Vault Obsidian |
| `filesystem` | sim | `sandbox`: lista de `{alias, path, permissions}`; `limits`: orçamento de escrita |
| `permissions` | não | read, write, shell, network (predefinição `true/false/false/false`) |
| `rag` | não | `top_k` (predefinição 8) |
| `mcp_servers` | não | endpoint, namespace, auth (bearer/header/oauth) |
| `audit` | não | enabled, path, max_field_chars, max_bytes, max_files, include_outputs |
| `policy` | não | caminho do ficheiro de política, subject |
| `memory` | não | enabled, vault_subdir, context_turns, context_skills, max_skill_chars |

Os erros de validação produzem sempre `ConfigError`, com uma mensagem que
indica o campo. O caminho da auditoria, se for relativo, é resolvido em
relação ao ficheiro de configuração.

## 3.2 Interface LLM e backend (`llm/`)

`LLMClient` tem dois percursos:

- **chamada nativa** (predefinida): `native_step()` envia os esquemas das
  ferramentas no formato do provider e lê as chamadas da resposta;
- **protocolo JSON textual** (fallback): `request_tool_call()` pede um
  JSON com `tool`/`arguments`, com parsing robusto e uma tentativa de
  reparação.

O esquema dos parâmetros é construído a partir de `ToolDefinition`:
OpenAI/Ollama usam `tools[].function`, Claude `tools[].input_schema`,
Gemini `functionDeclarations`. A conversa canónica usa os papéis
`user`/`assistant`/`tool`; cada cliente tradu-la (OpenAI `tool_calls`,
Claude blocos `tool_use`/`tool_result`, Gemini `functionCall`/
`functionResponse`). Uma recusa HTTP 400/404/422 produz
`NativeToolsUnavailable`: o Agent passa ao protocolo textual apenas se
ainda não executou ferramentas.

Os nomes das ferramentas são normalizados para as APIs que não admitem o
ponto (`filesystem.read_file` → `filesystem__read_file`) e repostos no
nome interno na resposta: a política, a auditoria e os testes veem sempre
o nome original.

O texto continua a ser o fallback para modelos que não suportam as
ferramentas nativas; `model.native_tools: false` força-o (ou
`--no-native-tools` a partir da CLI).

| provider | API | chave | notas |
|---|---|---|---|
| `ollama` | `/api/chat`, `/api/generate` | — | host predefinido `localhost:11434` |
| `deepseek` | `/chat/completions` (OpenAI) | `DEEPSEEK_API_KEY` | system inline |
| `claude` | `/v1/messages` | `ANTHROPIC_API_KEY` | system separado, turnos alternados |
| `gemini` | `models/{model}:generateContent` | `GEMINI_API_KEY` | `systemInstruction`, papel `model` |

A chave lê-se apenas do ambiente; `model.api_key_env` substitui o nome
predefinido. `model.host` é a base URL de todos os providers (com um
valor predefinido por provider), `model.max_tokens` é usado apenas pelo
Claude. `llm/factory.py` constrói o cliente e recusa providers
desconhecidos ou chaves em falta. DeepSeek: os modelos atuais são
`deepseek-flash` e `deepseek-v4-pro`; `deepseek-chat` já não é aceite.

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
3. se for necessária, a ferramenta é executada e o resultado volta ao
   modelo;
4. o limite `max_tool_calls` aplica-se ao turno inteiro. Se o modelo
   insistir, o turno fecha com `Agent stopped after N tool calls`
   (proteção contra ciclos).

Se o primeiro passo nativo falhar com `NativeToolsUnavailable`, o Agent
passa ao protocolo textual (`llm.native_fallback`); um erro depois de uma
ferramenta ter sido executada fecha o turno com `turn.error`, sem
fallback.

Cada passo é registado na auditoria: pergunta, escolha da ferramenta,
argumentos, resultado, duração e resposta final. Uma auditoria quebrada
não para o agente: a falha é assinalada em stderr.

O `Agent` recebe o `Vault` mas ainda não o usa.

## 3.5 FileSystemSandbox (`core/filesystem.py`)

Filesystem virtual do agente. Cada pedido é:

1. resolvido contra o diretório corrente (`resolve_path`);
2. verificado contra as raízes concedidas (`effective_permissions`);
3. filtrado pelas permissões efetivas, com as raízes mais específicas a
   sobrepor-se às mais exteriores;
4. controlado contra os symlinks e o espaço em disco disponível
   (`FS_Guardian`, nome legado).

`DirectoryPermissions` modela `read`, `write`, `create`, `rename`,
`delete`, `execute`; `None` significa "herda da raiz exterior".
Um caminho fora das raízes é sempre `PermissionError`.

`FileInfo` / `stat()` devolvem tipo, tamanho em bytes, datas de
criação/modificação/acesso (ISO 8601 com offset local) e as permissões
**efetivas da sandbox**, não as ACL do sistema operativo.

**Os symlinks não existem para a sandbox.** O Hagar não os mostra, não os
lê, não os segue e não os apaga: `stat`, `list_dir` e `search` ignoram-nos;
`read_file`, `read_chunk` e `delete_file` respondem "not found"; `chdir`
sobre um symlink responde "Directory not found". Um link quebrado ou
dirigido ao exterior é indistinguível de um caminho inexistente.

A raiz virtual da sandbox é `/home/ai`; cada diretório configurado é
exposto como `/home/ai/<alias>`. `stat`, `list_dir`, `search`,
`read_chunk`, as mensagens de `write`/`create`/`mkdir`/`delete` e `chdir`
mostram apenas caminhos virtuais: o caminho físico nunca aparece na saída
do modelo. Uma entrada `/home/ai/<alias>/...` é resolvida contra o
diretório físico do alias; os caminhos relativos permanecem relativos ao
diretório corrente.

`/home/ai` é um diretório sintético: pode ser listado e consultado com
`stat`, mas não é um mount e não é possível fazer `chdir` para lá. As entradas de
`filesystem.sandbox` continuam a ser caminhos do sistema anfitrião,
absolutos ou com `~` se o utilizador o escolher: pode ser qualquer
diretório existente e alcançável. O Hagar não cria diretórios e não
pressupõe uma home dedicada.

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
é montada. Alias ou permissões inválidas, caminho em falta ou caminho
duplicado param a configuração. Os caminhos físicos e os nomes internos
podem conter espaços; o alias não, porque tem de continuar a ser um único
segmento virtual.

`R` cobre leitura, listagem, pesquisa e `stat`; `W` cobre escrita,
criação, renomeação, cópia e eliminação; `X` cobre `chdir`. As permissões
globais `permissions.read`/`write` continuam a ser um teto: um alias
`RWX` não as pode exceder.

## 3.6 Ferramentas do filesystem (`core/filesystem_tools.py`)

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

`list_dir` devolve metadados `FileInfo`; `read_chunk` lê por bytes com
`has_more`, `next_offset` e limites UTF-8 completos; `search` usa um glob
recursivo com limite de resultados; `copy_file` exige `create`;
`rename` exige `rename` na origem e `create` no destino.
Os caminhos devolvidos são sempre virtuais (`/home/ai/<alias>/...`).
`chdir` exige `X` sobre o alias.

`list_dir` devolve no máximo 100 entradas por página (`limit` máximo
500) com `offset`, `next_offset` e `has_more`; se houver mais entradas, o
`message` diz `voci: riportate X di Y; per continuare usa offset=Z`.
`search` usa a mesma paginação: `max_results` é o limite de página
(predefinição 100, máximo 500), `offset` percorre os resultados. Para
árvores grandes convém restringir `pattern`/`path` em vez de iterar
muitas páginas. `read_file` aceita apenas ficheiros até `CHUNK_SIZE`
(4096 bytes); acima disso, o erro remete para `read_chunk()` porque ler
todo o ficheiro excederia a context window. `read_chunk` devolve
`next_offset` e limites UTF-8 completos.

`list_dir` e `search` não mostram os symlinks; `read_file` e `read_chunk`
tratam-nos como ficheiros inexistentes.

`write_file` substitui apenas ficheiros existentes; a criação passa por
`create_file`, que exige a permissão `create`. Não é possível contornar a
proibição de criação escrevendo um caminho novo.

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
- `min_free_bytes` é a reserva de espaço que tem de restar depois da
  operação;
- `session_write_bytes` é o orçamento cumulativo da sessão;
- `ask_over_bytes` eleva a `ASK` as operações acima do limiar. O
  preflight está integrado no `ToolRegistry`: se também a política disser
  `ASK`, a confirmação é apenas uma.

`0` desativa o limite individual. Exceder `max_write_bytes`,
`session_write_bytes` ou a reserva produz um erro, não uma confirmação:
são invariantes, não perguntas. `ask_over_bytes` é o único nível que
pergunta ao utilizador.

`filesystem.stat` devolve JSON com `path`, `exists`, `kind`
(`file`/`directory`/`other`), `size_bytes`, `created_at`, `modified_at`,
`accessed_at`, `permissions`. Um caminho inexistente não é um erro:
`exists: false` com as permissões aplicáveis.

## 3.7 MCP (`llm/mcp_client.py`)

Cliente MCP via HTTP/JSON-RPC: `initialize`, `tools/list`, `tools/call`,
conversão automática das ferramentas em `ToolDefinition` e registo com
namespace `mcp.<namespace>`.

Suporta também respostas `text/event-stream` (streamable HTTP) e envia a
notificação `notifications/initialized` após o handshake. Usa
`MCP-Protocol-Version` (predefinição `2025-06-18`, com fallback) e reusa
`Mcp-Session-Id` quando o servidor o devolve. Os erros HTTP incluem o
corpo da resposta para tornar diagnosticáveis os 400.
Os resultados das ferramentas são normalizados em texto: blocos `text`,
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

O token lê-se apenas do ambiente e não aparece na auditoria. Se faltar, o
servidor é ignorado com `mcp.failed` e o harness continua; os outros
servidores permanecem disponíveis.

### OAuth interativo

```yaml
auth:
  type: oauth
  oauth:
    authorization_server: https://auth.example.com
    # client_id: ...          # sem este, registo dinâmico
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
Os metadados são descobertos a partir de `.well-known` (RFC 9728 para o
recurso, RFC 8414 para o authorization server); se `client_id` faltar,
usa-se o registo dinâmico. Os tokens ficam num ficheiro local com
permissões restritas (`0600` onde o sistema as suporta), com refresh
automático e retry uma vez em caso de `401`.

Ctrl-C durante a espera do callback fecha o servidor local e sai com
código 130, sem traceback.

Limites: nada de device flow, DPoP, mTLS ou client assertion; o browser
tem de conseguir alcançar o callback local. Se o callback não chegar, o
terminal pede para colar o URL de redirecionamento.

## 3.8 Vault (`memory/vault.py`)

Acesso ao Vault Obsidian com caminhos relativos à raiz e proteção contra a
saída do Vault. Oferece leitura, escrita, append, listagem dos ficheiros
e `load_all` para a leitura recursiva. A semântica da memória vive em
`memory/store.py` (§3.11).

## 3.9 Registo de auditoria (`core/audit.py`)

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

- escrita best effort: um erro de I/O não para o harness e é assinalado
  uma única vez em stderr;
- truncamento configurável (`audit.max_field_chars`, predefinição 2000);
- cadeia de hash (`prev`/`hash`) verificável com `verify_chain`;
- rotação em `<file>.<timestamp>` acima de `audit.max_bytes` (0 desativa);
- retenção: `audit.max_files` (predefinição 100) mantém no máximo N
  ficheiros, incluindo o ativo; as cópias mais antigas são eliminadas;
- com `audit.include_outputs: false` a saída das ferramentas é registada
  apenas como tamanho;
- valores não JSON tornados serializáveis;
- nenhuma chave API no registo;
- o registo contém também a saída das ferramentas (portanto conteúdos de
  ficheiros): tem de ser protegido como o workspace.

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
  `default` (`DENY` se não especificado).
- **Resource**: o objeto da decisão (por agora uma ferramenta com as suas
  capabilities; no futuro também notas e caminhos).
- **Decision**: efeito, motivo e regra aplicada.

`PermissionEvaluator.evaluate(subject, resource, scope)`:

1. o recurso tem de oferecer as capabilities pedidas;
2. o **teto do sistema** (derivado de `permissions.read/write/shell`)
   tem de as conceder;
3. para cada capability aplicam-se as regras do sujeito: vence a mais
   específica (número de filtros, depois comprimento do prefixo), em caso
   de igualdade o efeito mais restritivo; sem regras vale o default;
4. com várias capabilities pedidas vale o AND: vence o efeito pior.

`ASK` não é uma decisão: é uma pergunta a um humano. O
`ConfirmationProvider` coloca-a — `ConsoleConfirmation` pergunta
`lo faccio? (y/N)` com predefinição N — e sem canal de confirmação vale
`DENY`. Uma GUI poderá implementar o mesmo protocolo com uma caixa de
diálogo modal.

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

`policy.yaml` é lido **antes** de construir o LLM. Se não for legível ou
não for válido, o harness aplica `DENY` a todas as políticas, registra-o
na auditoria (`policy.failed`) e assinala-o no chat; o resto do harness
continua a funcionar. Também um sujeito ausente degrada para `DENY`.

O controlo ocorre em `ToolRegistry.execute`, único ponto de execução, e
produz os eventos `permission.decision` e `permission.confirmation`.

O scope `paths` compara o caminho **escrito pelo modelo** (normalizado),
não o resolvido pela sandbox: um caminho absoluto ou um `chdir` podem não
corresponder a um prefixo relativo, e o resultado permanece `DENY` (fail
closed).

## 3.11 Memória (`memory/store.py`, `memory/tools.py`)

**Episódica.** O harness acrescenta cada turno concluído a uma nota por
sessão:

```text
<vault>/Hagar/chat/YYYY-MM-DD-<session>.md
```

Frontmatter com `session`, `type: chat`, `created`; corpo com uma secção
por turno (`## <timestamp> · <turn>`), pergunta e resposta. Não são
guardadas as saídas das ferramentas: essas ficam na auditoria.

No início de cada turno o Agent injeta no prompt os últimos
`memory.context_turns` turnos (0 desativa a injeção), truncando pergunta
e resposta. Com `memory.context_skills > 0` acrescenta até N **skills
confirmadas** pertinentes à pergunta, por correspondência lexical no
título, tags e conteúdo; as candidatas e as arquivadas nunca entram.
O bloco é rotulado como dados, não como instruções. Um erro de memória
não para o turno: é registado `memory.failed`.

**Semântica.** O modelo pode propor uma memória com três ferramentas:

| ferramenta | capability | namespace |
|---|---|---|
| `memory.create_skill` | `MEMORY_WRITE` | `skills` |
| `memory.list_skills` | `MEMORY_READ` | `skills` |
| `memory.get_context` | `MEMORY_READ` | `chat` |

`create_skill` escreve `<vault>/Hagar/skills/<slug>.md` com frontmatter
`id`, `title`, `kind` (`fact`/`procedure`), `status: candidate`, `tags`,
`source_session`, `source_turn`, `model`, `created_at`. O slug é seguro
(apenas ASCII, sem caminho); um título já existente não é substituído e
devolve `duplicate: true`.

`get_context` devolve os últimos turnos ou pesquisa por palavra-chave nas
sessões passadas; `list_skills` filtra por `kind` e `status`.

**Ciclo de vida.** Os estados são `candidate`, `confirmed`, `archived`.
O LLM cria apenas candidatas; a transição é humana, a partir da CLI:

```text
/memory list [candidate|confirmed|archived]
/memory show <slug>
/memory review
/memory confirm <slug>
/memory archive <slug>
```

`/memory review` mostra uma candidata de cada vez com proveniência e
conteúdo, e depois pergunta `y/N/a/s/q` (confirma, deixa, arquiva, salta,
sai). A confirmação escreve `reviewed_at`; `archive` é reversível com
`confirm`. Cada transição produz `memory.status` ou `memory.review` na
auditoria. As notas continuam a ser ficheiros Obsidian: alterar `status`
no frontmatter tem o mesmo efeito.

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

A memória de projeto está separada das skills:

```text
<vault>/Hagar/projects/<id>/index.md
<vault>/Hagar/projects/<id>/decisions/<data>-<slug>.md
<vault>/Hagar/summaries/<data>-<session>.md
<vault>/Hagar/archive/chat/<data>-<session>.md
```

Cada projeto tem um `index.md` com estado, última atividade, resumo e
contagem das decisões ativas. Cada decisão tem estado
`candidate`/`active`/`superseded`/`archived`, alternativas, motivação,
proveniência e `auto_saved`. As decisões não se reescrevem: uma nova
decisão pode substituir uma antiga.

No arranque o Hagar mostra os projetos ativos e a "atividade livre":

```text
/project list
/project new <nome>
/project select <nome>
/project free
/project status
/project archive <nome>
/project unarchive <nome>
```

Os overrides não interativos são `--project <nome>` e `--free`.

No fim da sessão:

1. o transcript é movido para `archive/chat/`;
2. é gerado um resumo com o modelo, com fallback mecânico;
3. o resumo é guardado com link e hash do transcript;
4. se houver um projeto, o LLM propõe decisões `candidate`;
5. o utilizador pode revê-las; se recusar, permanecem `candidate` com
   `auto_saved: true`.

O contexto injetado usa o **índice** do projeto: resumo, títulos das
decisões ativas e contagem, não todos os corpos. Os detalhes leem-se com
`memory.project_context(query=..., limit=...)`. O bloco global é limitado
por `max_context_chars`; se for cortado, a auditoria registra
`memory.context_trimmed`. Não é uma estimativa de tokens: é um orçamento
em caracteres, determinístico.

Quando um projeto excede `project_max_active`, o Hagar pergunta se deve
ser arquivado. O arquivamento é reversível e não apaga nada.

**Consulta do arquivo.** Os transcripts arquivados têm o `project` no
frontmatter. A pesquisa e a leitura são on demand:

```text
/memory archive search <texto>
/memory archive read <session> [offset] [limit]
```

As mesmas ferramentas são expostas como `memory.archive_search` e
`memory.archive_read`; a pesquisa devolve sessão, turno, timestamp,
projeto e excerto, a leitura pagina os turnos. Não há injeção automática
do arquivo no prompt: o resumo continua a ser o índice, o transcript é a
fonte a consultar quando necessário.

Se `vault.path` não existir ou não for escrevível, a memória é desativada
com um aviso no chat e `memory.disabled` na auditoria; os outros
componentes continuam a funcionar. As escritas de memória estão sujeitas
às políticas (`MEMORY_READ`/`MEMORY_WRITE`).

## 3.12 Arranque e empacotamento

O projeto instala-se com `pip install -e .` e declara os pacotes em
`pyproject.toml`. O entry point é `hagar = "hagar:main"`. A versão atual é
`0.3.0`.

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

A configuração é procurada nesta ordem: `--config`, variável
`HAGAR_CONFIG`, `./hagar.yaml`. `python -m hagar` funciona a partir do
diretório do projeto.

A CI GitHub Actions executa a suite em Linux, macOS e Windows com
Python 3.11/3.12/3.13, constrói sdist e wheel, executa `twine check` e
testa a instalação do wheel. O workflow `Release` parte de uma tag `v*`,
verifica que a tag corresponde à versão do pacote e cria a release GitHub
com os artefactos.

Os testes live estão excluídos da suite normal e ativam-se com `--live`:
verificam o Ollama e os providers remotos (estes últimos apenas se a
chave API estiver presente).

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
  calendário juliano proléptico ou no calendário islâmico tabular
  (Kuwaiti algorithm). O calendário islâmico tabular pode diferir num dia
  dos que se baseiam na observação ou em Umm al-Qura.
- `think.echo` devolve exatamente a cadeia recebida; serve para
  externalizar um passo intermédio nas cadeias de raciocínio.
- `text.diff` devolve um diff unificado entre dois textos, com input
  máximo de 20000 caracteres, output máximo de 20000 e `context` 0..10.
  Não aplica o diff.
- `url.parse` decompõe scheme, host, porta, path, query e fragment sem
  DNS ou rede; limita o URL a 4096 caracteres e os parâmetros a 100. Se o
  URL contiver credenciais, mascara-as na saída.
- `clock`, `calendar`, `think`, `text` e `url` não acedem ao filesystem
  nem à rede, e recaem na regra `COMPUTE` allow.
- O calculador usa uma whitelist de AST, não `eval()`, com limites na
  expressão, no número de nós e no expoente.
- `feed.read` descarrega com `requests` (timeout 15 s, máximo 5 MB),
  aceita apenas URLs http/https e usa `feedparser`; a política `NETWORK`
  é `ask`.
- SSRF: cada host é resolvido com `getaddrinfo` e cada endereço tem de
  ser global; loopback, redes privadas, link-local, multicast e
  reservados são recusados. Os redirecionamentos não são automáticos:
  cada `Location` é revalidado e para-se após 3 saltos. Um URL com
  credenciais é recusado.
- `permissions.network: true` é necessário para que o teto do sistema
  conceda `NETWORK`; `COMPUTE` está sempre no teto, mas a política pode
  negá-la.
- `local_tools` é declarado em `pyproject.toml` e instalado com o
  projeto.

---

# 4. Modelo de segurança

- O agente não vê o filesystem real: apenas caminhos resolvidos dentro da
  sandbox.
- As operações passam apenas pelo `ToolRegistry`; nenhuma shell
  anfitriã.
- As permissões são declaradas na configuração e nas políticas, e são
  aplicadas pela sandbox e pelo `PermissionEvaluator`; as raízes
  aninhadas podem restringir as permissões.
- Os erros são dados: uma recusa é devolvida ao modelo como resultado da
  ferramenta, não escondida.
- Cada ação deixa um rasto na auditoria, com sessão e turno.

---

# 5. Desenvolvimento

- Suite: `./tools/run_tests.sh` (Linux/macOS) ou
  `.\tools\run_tests.ps1` (Windows). Em Windows: 691 aprovados, 2
  ignorados (symlinks não disponíveis sem Developer Mode). Em Debian
  Linux (2026-11-06): todos os testes verdes, incluindo os symlinks (693
  aprovados, 0 ignorados). Detalhes e justificação do shim em README
  §3.1.
- Testes live: `./tools/run_tests.sh --live` (Linux/macOS) ou
  `.\tools\run_tests.ps1 --live` (Windows) — mais 9 testes (Ollama;
  providers remotos se as chaves estiverem presentes).
- Comparação de modelos: `python tools/bench_models.py` (README §3.5).
- Comparação de protocolos: `python tools/bench_native.py --provider ollama`
  (README §3.5).
- A suite normal não toca na rede: o Ollama e o MCP são simulados.

## 5.1 Multiplataforma

- Os caminhos internos usam `pathlib.Path`; os mostrados ao agente usam
  sempre `/` e a raiz virtual `/home/ai`.
- `filesystem.sandbox` contém caminhos do sistema anfitrião, absolutos ou
  com `~` se o utilizador o escolher: `Path.expanduser()` resolve a home
  apenas quando o caminho a usa. Não se pressupõe que exista uma home
  dedicada.
- Cada mount tem um alias explícito e único (case-insensitive); o
  caminho físico pode estar em qualquer volume.
- `tools/run_tests.sh` é o runner POSIX; `tools/run_tests.ps1` e
  `tools/pytest_shim` servem apenas a sandbox Windows com token
  restrito.
- O único ramo explicitamente Windows que resta é a data de criação em
  `stat`: `st_birthtime` onde disponível, caso contrário `st_ctime` em
  Windows; em Linux `created_at` pode ser `None`.
- As APIs externas (OAuth, MCP, LLM) usam HTTP e `webbrowser`, não
  comandos de sistema.
- A CI GitHub Actions cobre Linux, macOS e Windows em Python
  3.11/3.12/3.13; symlinks, permissões dos tokens OAuth e callback
  loopback continuam por verificar com testes live, não na suite offline.

---

# 6. Limites conhecidos e dívida técnica

- O `PermissionEvaluator` cobre a v1: faltam os sujeitos dinâmicos, as
  confirmações GUI e as capabilities MCP atribuídas pela configuração.
- A chamada nativa depende do modelo: alguns ignoram as ferramentas ou
  devolvem várias chamadas; o fallback textual cobre os erros, não a
  qualidade da escolha.
- O cliente MCP suporta bearer/header e OAuth authorization code; não
  gere device flow, DPoP, mTLS ou client assertion.
- A revisão das skills é manual a partir da CLI; falta uma GUI.
- A pesquisa na memória é por palavra-chave, sem índice nem embedding.
- O contexto injetado usa turnos recentes globais e até 3 skills
  confirmadas por correspondência lexical, sem seleção semântica.
- A memória não apaga chats ou skills por antiguidade: `archive` é a
  única remoção do contexto.
- A auditoria tem rotação e retenção (`max_files`), mas não compactação
  das sessões nem uma ancoragem externa da cadeia.
- `feed.read` valida os endereços e os redirecionamentos, mas subsiste o
  caso de DNS rebinding: `requests` resolve o nome uma segunda vez no
  momento da ligação; é necessário um resolver fixado.
- O calculador não é um CAS: trata apenas expressões numéricas
  limitadas, não simbólicas.
- `stat().created_at` é `None` em Linux quando falta `st_birthtime`; não
  é inventada uma data de criação.
- Dois alias não podem apontar para o mesmo caminho físico: o alias
  identifica um mount e a saída virtual tem de permanecer unívoca.

## 6.1 Responsabilidade do utilizador: hard link, mount e TOCTOU

**O Hagar não controla os hard links, os mounts/junctions e as corridas
TOCTOU dentro dos diretórios allowed.** Não é um defeito do Hagar: a
sandbox é path-based e não usa handles/file descriptors para a operação
inteira.

Um hard link é um segundo nome do mesmo inode, não tem um alvo de
caminho e a sandbox não pode saber se existe outro nome fora. Um mount ou
uma junction podem expor outro filesystem permanecendo dentro do prefixo
do caminho. Uma corrida TOCTOU pode alterar um componente entre o
controlo dos symlinks e a operação real: o Hagar não usa `openat2`,
`O_NOFOLLOW` em cada componente ou handle Windows, pelo que não garante
atomicidade entre verificação e acesso.

As ferramentas de filesystem do Hagar não criam hard links. Se um hard
link ou um mount já existir dentro de um diretório da sandbox, o Hagar
trata-o como um ficheiro ou diretório normal e pode lê-lo, modificá-lo ou
apagar o seu nome interno.

A responsabilidade é, portanto, dividida:

- **O Hagar garante** que os caminhos resolvidos permanecem dentro do
  alias no momento da verificação, que os symlinks são invisíveis, que as
  permissões `R`/`W`/`X` são aplicadas e que os caminhos reais não vão
  parar à saída do modelo.
- **O utilizador garante** que os diretórios configurados em
  `filesystem.sandbox` não contêm hard links, mounts ou junctions para
  conteúdos que não devem ser acessíveis, e que nenhum processo
  concorrente não fidedigno pode modificar esses diretórios durante a
  execução, se quiser isolamento total.

As corridas TOCTOU exigem um ator local concorrente com acesso de escrita
aos diretórios da sandbox: não são um caso acidental do uso normal, mas
um cenário malicioso ou de ambiente comprometido. Para um isolamento
forte são necessários um volume dedicado, um utilizador separado, um
mount namespace ou um container; não é tarefa do resolver de caminhos.

Os pontos estão fechados como **responsabilidade do utilizador**, não como
dívidas técnicas do Hagar. Hard links, mounts/junctions e corridas TOCTOU
não são detetados nem bloqueados por esta versão.

---

# 7. Mapa da documentação

- `MANUAL.md` — manual do utilizador: comandos, configuração, política,
  predefinições.
- `ARCHITECTURE.md` — este documento: como é o sistema hoje.
- `ROADMAP.md` — o que fazer, decisões tomadas e pontos em aberto.
- `CHANGELOG.md` — história das versões.
- `README.md` — arranque, configuração, testes.
