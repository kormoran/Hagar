# HAGAR — Manual do utilizador

Versão: **0.5.2**

Este manual descreve o comportamento observável do Hagar: comandos,
opções, configuração, políticas e casos de erro. Para o projeto interno,
ver [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

# 1. Arranque rápido

Requisitos: Python 3.11 ou superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

cp hagar.example.yaml hagar.yaml
mkdir -p vault logs

hagar --config hagar.yaml
```

No Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item hagar.example.yaml hagar.yaml
New-Item -ItemType Directory -Force vault, logs
hagar --config hagar.yaml
```

`hagar.yaml`, `testvault/` e `logs/` são locais e não devem ser versionados.

## 1.1 Ordem de arranque

1. O Hagar lê a configuração.
2. Carrega `policy.yaml`; se não for válido, aplica `DENY` a tudo.
3. Constrói o cliente LLM.
4. Inicializa o Vault e a memória, se configurados.
5. Constrói a sandbox do file system.
6. Regista as ferramentas locais.
7. Tenta carregar os servidores MCP; um servidor com falha não para os outros.
8. Mostra a escolha do projeto.
9. Entra no ciclo de chat.

---

# 2. Comandos de chat

Os comandos começam por `/`. Um comando desconhecido **não é enviado ao
modelo**: o Hagar responde `Comando sconosciuto` e sugere `/help`.

## 2.1 Comandos globais

| Comando | Comportamento |
|---|---|
| `/help` ou `/?` | lista os comandos disponíveis |
| `/tools [categoria]` | lista as ferramentas e as capability; o filtro é opcional |
| `/status` | mostra modelo, projeto, memória, auditoria e sandbox |
| `/usage` | mostra os tokens consumidos na sessão |
| `/models ...` | fichas, benchmarks e hardware para o broker |
| `/models hardware` | deteta CPU, RAM e GPU da máquina |
| `/mcp` | lista servidores MCP, endpoints e ferramentas importadas |
| `/audit [n]` | mostra os últimos `n` eventos; predefinição 10, máximo 50 |
| `exit` | sai |
| `quit` | sai |
| `Ctrl-D` | sai |
| `Ctrl-C` | interrompe; durante OAuth sai com código 130 |

`/status` e `/audit` são comandos humanos: não passam pelo modelo e não
consomem tool calls.

## 2.2 Projeto

| Comando | Comportamento |
|---|---|
| `/project` ou `/project list` ou `/project ls` | lista os projetos ativos |
| `/project new <nome>` | cria um projeto e seleciona-o |
| `/project select <id>` ou `/project use <id>` | seleciona um projeto ativo |
| `/project free` ou `/project none` | passa para atividade livre |
| `/project status` ou `/project current` | mostra o projeto atual |
| `/project archive <id>` | arquiva um projeto |
| `/project unarchive <id>` | reativa um projeto arquivado |
| `/project help` | ajuda |

`select` e `archive` usam o **id** do projeto, não o título.

Em atividade livre não é lida nem escrita memória de projeto; chat,
summary e skill continuam disponíveis.

## 2.3 Memória

| Comando | Comportamento |
|---|---|
| `/memory` ou `/memory help` ou `/memory ?` | ajuda |
| `/memory list [candidate\|confirmed\|archived]` | lista as skills e as contagens |
| `/memory show <slug>` | mostra uma skill |
| `/memory search <texto>` | procura nas memórias SQLite |
| `/memory sessions` | lista os chats registados |
| `/memory chat <session>` | mostra os turnos de um chat |
| `/memory reindex` | otimiza/reconstrói os índices SQLite |
| `/memory stats` | estado e contagens da base de dados |
| `/memory backup <path>` | cópia consistente da base de dados |
| `/memory export <path> [--force]` | exporta chats, skills, summaries e projetos em Markdown |
| `/memory import <path> [--force]` | importa uma estrutura Markdown para a base de dados |
| `/memory review` | revisão interativa das candidatas |
| `/memory confirm <slug>` | confirma uma skill |
| `/memory archive <slug>` | arquiva uma skill |
| `/memory archive search <texto>` | procura nos transcripts arquivados |
| `/memory archive read <session> [offset] [limit]` | lê um transcript arquivado |

As palavras `search` e `read` são reservadas: um slug de skill chamado
exatamente `search` ou `read` não é arquivável com este comando.

Não existe um comando de eliminação: apenas se arquiva.

O backend predefinido é SQLite (`memory.backend: sqlite`). A base de dados
fica nos dados locais da aplicação, não no Vault:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

ou `HAGAR_MEMORY_DB`. O backend `markdown` mantém-se apenas por
compatibilidade. O Vault já não é atualizado pelo backend SQLite.

## 2.4 O que não é um comando

As ferramentas (`filesystem.*`, `memory.*`, `mcp.*`, `clock.now`, ...) são
chamadas pelo modelo através do registry. Não se escrevem como `/tool`.
A única exceção são os comandos informativos `/tools`, `/status`, `/models`, `/mcp`,
`/audit`, que são de consola e não ferramentas.

---

# 3. Linha de comandos

```text
hagar [opções]
hagar web [opções]
```

| Opção | Efeito |
|---|---|
| `--config PATH` | usa um ficheiro de configuração explícito |
| `--model NAME` | substitui `model.name` |
| `--project NAME` | seleciona um projeto ativo no arranque |
| `--free` | arranca em atividade livre |
| `--no-memory` | desativa memória e projetos para a sessão |
| `--no-native-tools` | força o protocolo JSON textual |
| `--host HOST` | host da GUI web (predefinição `127.0.0.1`) |
| `--port PORT` | porta da GUI web (predefinição `8765`) |
| `--version` | imprime a versão |

`--project` e `--free` são mutuamente exclusivos.

## 3.0 GUI web

```bash
hagar web
hagar --config hagar.yaml web --port 8765
```

Abre uma GUI local em `http://127.0.0.1:8765/`.

- O servidor foi pensado para um único utilizador local: predefinição `127.0.0.1`.
- O browser recebe um token aleatório na página; as API exigem-no
  no cabeçalho `X-Hagar-Token`.
- O chat mostra turnos, tool call, resultados e confirmações ASK.
- No topo estão os separadores **Chat**, **Chat history**, **Tool output**,
  **Audit** e **Thinking**.
- **Chat history** lista os chats anteriores, uma linha por chat; um clique
  retoma o chat: o transcript é recarregado da base de dados e os novos
  turnos são acrescentados à mesma sessão.
- O botão **+ Novo chat** abre uma nova sessão e limpa o
  contexto; o chat anterior permanece no histórico.
- **Memories** é um browser só de leitura das notas indexadas
  (skill, projetos, decisões); permite pesquisa e abertura do texto.
- **Tool output** mostra os tool call e os resultados da sessão.
- **Audit** mostra os eventos do log; se a auditoria estiver desativada o separador fica
  desativado e mostra `audit off`.
- **Thinking** mostra o reasoning exposto pelo provider, se existir; em
  alternativa a timeline dos eventos do agente.
- **Memories** mostra memórias e skills da base de dados em só de leitura, com pesquisa.
- O botão **Stop** interrompe o turno de forma cooperativa.
- O botão **Imagem** anexa PNG/JPEG/WebP (máx. 4, 10 MB cada)
  para os modelos vision. O WebP é convertido em PNG na GUI porque o LM
  Studio não o aceita diretamente. As imagens não são guardadas
  na memória nem na auditoria: ao modelo chega o data URL, não o
  caminho host.
- A barra lateral em baixo mostra os tokens acumulados da sessão: input,
  output e total.
- O modelo pode carregar imagens da sandbox com `vision.open`;
  a imagem é anexada ao turno, não devolvida como base64 no
  contexto.
- As confirmações ASK são modais: o turno fica à espera e o servidor
  continua a responder. Um timeout equivale a recusa. Os pedidos dos
  subagentes mostram `agent_id` e `parent_id`; o pai LLM não as pode
  aprovar. O timeout do subagente é de 180 segundos.
- Na CLI só uma thread possui o input. Quando está ativa uma confirmação,
  o título do terminal pede atenção e são aceites `F5` =
  allow, `F8` = deny, além de `y/N`. Se o terminal não suportar as teclas
  de função, restam `y/N` e a GUI.
- Ctrl-C na CLI restaura o modo normal do terminal antes de
  sair.
- A GUI ainda não é multiutilizador e não expõe alterações diretas à memória.
- Ctrl-C fecha o servidor e tenta terminar a sessão.

Não usar `--host 0.0.0.0` numa rede não fidedigna: a GUI expõe as ferramentas
do harness a quem conseguir alcançar a porta.

## 3.1 Procura da configuração

Ordem:

1. `--config PATH`
2. variável `HAGAR_CONFIG`
3. `./hagar.yaml` na diretoria atual

Os caminhos relativos dentro de `hagar.yaml` — auditoria, política, Vault — são
resolvidos relativamente à diretoria do ficheiro de configuração, não à
diretoria a partir da qual lanças o Hagar.

## 3.2 Códigos de saída

| Código | Significado |
|---|---|
| `0` | saída normal ou `--version` |
| `1` | erro de configuração ou projeto inválido |
| `130` | interrupção com Ctrl-C |

Um erro MCP não altera o código de saída: é registado e o
harness continua.

---

# 4. `hagar.yaml`

Exemplo mínimo:

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
| `provider` | obrigatório | `ollama`, `lmstudio`, `deepseek`, `openai` (`chatgpt`), `claude`, `gemini` |
| `name` | obrigatório | nome do modelo no provider |
| `host` | default do provider | base URL da API |
| `native_tools` | `true` | se `false`, usa o protocolo JSON textual |
| `max_tokens` | `1024` | usado apenas pelo Claude |
| `timeout` | `120` | timeout HTTP em segundos para cada chamada |
| `api_key_env` | nome padrão | variável de ambiente da chave |

Providers e chaves:

| Provider | Chave padrão | Default |
|---|---|---|
| `ollama` | nenhuma | `http://localhost:11434` |
| `lmstudio` | nenhuma, opcional `LMSTUDIO_API_KEY` | `http://localhost:1234/v1` |
| `deepseek` | `DEEPSEEK_API_KEY` | API DeepSeek |
| `openai` / `chatgpt` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| `claude` | `ANTHROPIC_API_KEY` | API Anthropic |
| `gemini` | `GEMINI_API_KEY` | API Gemini |

As chaves nunca devem ser escritas no YAML. Se faltar uma chave, o cliente
não é construído e o arranque falha com um erro explícito. O LM Studio
não exige chave, a menos que o servidor local esteja configurado para
a exigir. `chatgpt` é um alias de `openai`: a subscrição ChatGPT não
dá acesso à API, são necessários uma chave OpenAI e crédito API.

Com o LM Studio, a chamada nativa de ferramentas depende do modelo e do seu
template. Se o modelo aceitar o pedido mas responder em texto em vez
de emitir `tool_calls`, o Hagar não consegue executar a ferramenta: usar
`model.native_tools: false` ou um modelo tool-capable.

Com a chamada nativa ativa, o Hagar usa as ferramentas estruturadas do
provider. Se o provider recusar o esquema (HTTP 400/404/422), no primeiro
passo passa ao protocolo JSON textual para essa sessão. O fallback
cobre o erro técnico, não garante que o modelo escolha bem a ferramenta.

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

| Campo | Default | Efeito |
|---|---|---|
| `enabled` | `true` | ativa/desativa o log |
| `path` | `logs/audit.jsonl` | ficheiro JSON Lines |
| `max_field_chars` | `2000` | trunca os campos |
| `max_bytes` | `5000000` | limiar de rotação |
| `max_files` | `100` | ficheiros rodados a conservar |
| `include_outputs` | `true` | se `false`, redige o output das ferramentas |

A auditoria contém dados sensíveis: output de ficheiros, respostas e textos. Tem de
ser protegida como o workspace. `/audit` mostra apenas os eventos do ficheiro
atual, não os rodados.

Eventos principais: `harness.start`, `turn.start`, `llm.tool_choice`,
`tool.call`, `tool.result`, `turn.answer`, `permission.decision`,
`permission.confirmation`, `memory.*`, `mcp.loaded`, `mcp.failed`,
`harness.stop`.

## 4.3 `policy`

```yaml
policy:
  path: policy.yaml
  subject: assistant
```

`path` é relativo à configuração. Se o ficheiro não for legível ou não for
válido:

- todas as políticas passam a `DENY`;
- é registado `policy.failed`;
- o Hagar mantém-se em execução mas nenhuma ferramenta é executada;
- a consola mostra `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

Com o backend SQLite só é usado pelo backend Markdown legacy e pelos
projetos legacy. Com `memory.backend: sqlite` pode até não existir.

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

| Campo | Default | Efeito |
|---|---|---|
| `enabled` | `true` | ativa a memória |
| `backend` | `sqlite` | `sqlite` ou `markdown` legacy |
| `database` | dados locais | caminho explícito da base de dados SQLite |
| `vault_subdir` | `Hagar` | subdiretório do Vault legacy |
| `context_turns` | `10` | turnos recentes injetados; `0` desativa |
| `context_skills` | `3` | skills confirmadas injetadas |
| `context_project_memories` | `10` | títulos de decisões ativas |
| `max_context_chars` | `6000` | budget do bloco de memória |
| `project_max_active` | `200` | limiar de manutenção do projeto |
| `summary_max_chars` | `4000` | comprimento máximo do summary |
| `max_skill_chars` | `4000` | comprimento máximo de uma skill |

`vault_subdir` tem de permanecer dentro do Vault: caminhos absolutos, `..`,
`I:/...` e outras drives Windows são recusados mesmo em Linux.

Com `backend: sqlite` a base de dados predefinida é:

```text
%LOCALAPPDATA%/Hagar/memory.db
```

ou `HAGAR_MEMORY_DB`. O SQLite usa WAL, transações e `VACUUM INTO` para o
backup; o Vault não é atualizado.

O budget é em **caracteres**, não em tokens. Quando o bloco é
cortado, a auditoria registra `memory.context_trimmed`.

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

| Campo | Obrigatório | Notas |
|---|---|---|
| `alias` | sim | um único segmento, único sem distinção de maiúsculas |
| `path` | sim | diretoria existente do sistema anfitrião |
| `permissions` | não | predefinição `R`; letras `R`, `W`, `X` |

Permissões:

| Letra | Cobre |
|---|---|
| `R` | ler, listar, procurar, `stat` |
| `W` | escrever, criar, renomear, copiar, apagar |
| `X` | `chdir` na diretoria |

O agente vê `/home/ai/<alias>/...`. `/home/ai` lista os alias mas não
é uma diretoria física e não é possível entrar nela com `chdir`.

Restrições:

- alias e caminhos duplicados bloqueiam a configuração;
- um caminho em falta bloqueia a configuração;
- os caminhos físicos podem conter espaços; os alias não;
- o Hagar não cria diretorias da sandbox e não assume uma home dedicada.

Limites de escrita:

| Campo | Efeito |
|---|---|
| `max_write_bytes` | máximo por operação individual |
| `min_free_bytes` | espaço livre mínimo residual |
| `session_write_bytes` | máximo cumulativo por sessão |
| `ask_over_bytes` | acima deste limiar pede confirmação |

`0` desativa o limite individual. Os limites são invariantes: uma
ultrapassagem é um erro da ferramenta, não um aviso.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
  agents: false
```

São o **teto de sistema**. Default: `read=true`, os outros `false`.

| Campo | Concede |
|---|---|
| `read` | file system read, memory read |
| `write` | file system write/create/delete, memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |
| `agents` | `AGENT_SPAWN` e `AGENT_DATA`, para `agent.*`/`artifact.*`/`mailbox.*` |

`COMPUTE` e `MCP_CALL` estão sempre no teto, mas a política pode negá-los.
Se o teto não concede uma capability, a política não a pode conceder.
`agents: true` não basta por si só: a política tem de ter uma regra
`AGENT_SPAWN` para `agent.*`.

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

Valor previsto para a recuperação documental. Não altera o contexto
da memória nesta versão.

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
| `endpoint` | URL HTTP/JSON-RPC do servidor MCP |
| `namespace` | prefixo das ferramentas importadas: `mcp.<namespace>.*` |
| `auth` | opcional: `bearer`, `header` ou `oauth` |

Bearer/header:

```yaml
auth:
  type: header
  header: Authorization
  token_env: ATLASSIAN_BASIC
```

O valor lido do ambiente é enviado **tal como está**: para Basic
tem de ser já `Basic <base64>`, não apenas o token.

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

O fluxo é authorization code + PKCE com callback local
`http://localhost:<port>/oauth/callback`. Se faltar `client_id` tenta-se
o dynamic registration. Com `offline_access` é adicionado
`prompt=consent`. Os tokens ficam num ficheiro local restrito e são
renovados automaticamente.

Se um servidor MCP falhar:

- é registado `mcp.failed`;
- o servidor é ignorado;
- os outros servidores e o resto do harness continuam;
- `/mcp` mostra zero ferramentas para esse namespace.

---

# 5. `policy.yaml`

Exemplo:

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

## 5.1 Efeitos

| Efeito | Significado |
|---|---|
| `allow` | a ferramenta pode ser executada |
| `ask` | é necessária uma confirmação humana |
| `deny` | a ferramenta não é executada |

Ordem de gravidade: `DENY > ASK > ALLOW`. Com várias capability pedidas
vale o AND: vence o efeito pior.

`ASK` sem canal de confirmação equivale a `DENY`. A confirmação da consola
mostra `lo faccio? (y/N)` e o default é `N`.

## 5.2 Capability

| Nome | Uso |
|---|---|
| `FILESYSTEM_READ` | leitura, listagem, pesquisa, stat |
| `FILESYSTEM_WRITE` | modificação |
| `FILESYSTEM_CREATE` | criação, cópia, rename no destino |
| `FILESYSTEM_DELETE` | eliminação |
| `FILESYSTEM_EXEC` | entrada/execução na sandbox |
| `MEMORY_READ` | leitura de memória |
| `MEMORY_WRITE` | escrita de memória |
| `NETWORK` | acesso de rede |
| `MCP_CALL` | chamada a ferramenta MCP |
| `COMPUTE` | cálculo local sem rede/file system |

## 5.3 Regras e especificidade

Uma regra pode filtrar com:

- `tools`: glob sobre o nome (`filesystem.*`, `mcp.atlassian.*`);
- `paths`: prefixos sobre o caminho escrito pelo modelo;
- `namespaces`: prefixos sobre o namespace.

Vence a regra mais específica: primeiro o número de filtros, depois a
longitude do prefixo. Em caso de empate vence o efeito mais restritivo.
Sem regras vale o `default` do sujeito; o default seguro é `deny`.

O scope `paths` compara o caminho **escrito pelo modelo**, não o
resolvido após `chdir`: um caminho absoluto ou uma mudança de diretoria pode não
corresponder e produz `DENY` (fail closed).

## 5.4 Erros

Se `policy.yaml` for inválido, faltar uma capability ou o sujeito não
existir:

- o Hagar aplica `DENY` a todas as políticas;
- registra `policy.failed`;
- mostra um aviso;
- não executa nenhuma ferramenta.

---

# 6. Comportamentos predefinidos

| Situação | Comportamento |
|---|---|
| Nenhum `hagar.yaml` | erro de configuração, saída 1 |
| YAML inválido | erro de configuração, saída 1 |
| Política inválida | DENY total, harness em execução |
| Memória desativada | verifica `memory.database` e as permissões da diretoria |
| `Projects: disabled` | verifica a base de dados SQLite ou `vault.path` no backend legacy |
| Nenhum projeto ativo | atividade livre |
| Arranque não interativo | atividade livre, salvo `--project`/`--free` |
| `--project` inexistente | erro, saída 1 |
| Servidor MCP inalcançável | `mcp.failed`, servidor ignorado |
| Modelo/Ollama inalcançável | erro do turno, harness mantém-se ativo |
| Chave API ausente | cliente não construído, erro no arranque |
| Ferramenta negada | resultado de erro ao modelo, nenhuma execução |
| Ferramenta em `ASK` sem confirmação | recusa |
| Limite de escrita ultrapassado | erro da ferramenta, nenhuma escrita |
| Ficheiro acima de 4096 bytes com `read_file` | erro, usar `read_chunk` |
| Página acima do limite | `has_more`/`next_offset` |
| Symlink | invisível; operação como caminho inexistente |
| Hard link/mount/junction | não detetados; responsabilidade do utilizador |
| Race TOCTOU | não controlada; responsabilidade do utilizador |
| Memória ausente durante o turno | `memory.failed`, o turno continua |
| Fim de sessão com turnos | summary, arquivo, review do projeto |
| Review recusada | decisões candidatas com `auto_saved: true` |
| Projeto acima de `project_max_active` | pedido de arquivo |
| Ctrl-C durante OAuth | callback fechado, saída 130 |
| Comando `/` desconhecido | mensagem, não enviado ao modelo |

## 6.1 Fim de sessão

Na saída, se a memória estiver ativa e houver turnos:

1. o transcript é movido para `archive/chat/`;
2. é gerado um summary (LLM, com fallback mecânico);
3. o summary é guardado com link e hash;
4. se houver um projeto, o LLM propõe decisões candidatas;
5. o utilizador pode revê-las; se recusar, ficam candidatas.

Se não houver turnos não é criado nenhum summary.

## 6.2 O que o Hagar não faz

- não executa comandos de shell;
- não dá ao modelo caminhos físicos;
- não garante isolamento de SO: a sandbox é path-based;
- não controla hard link, mount, junction ou TOCTOU;
- não apaga chats ou skills por antiguidade;
- não cifra o Vault;
- não promove automaticamente uma skill ou uma decisão a verdade.

---

# 7. Segurança operacional

- O modelo não é fidedigno: políticas e confirmações são os controlos.
- A base de dados SQLite contém conversas e decisões: tem de ser protegida.
- A auditoria pode conter output de ficheiros: tem de ser protegida.
- As chaves API ficam apenas no ambiente.
- Os tokens MCP/OAuth ficam em caches locais com permissões restritas.
- Não expor o Ollama ou o LM Studio na rede sem necessidade.
- Um hard link ou um mount dentro de uma diretoria allowed pode expor
  conteúdos externos: o Hagar não os deteta.

---

# 8. Troubleshooting

| Sintoma | Controlo |
|---|---|
| `Policy: DENY ALL` | validar `policy.yaml` e `policy.path` |
| `Memory: disabled` | verifica `memory.database` e as permissões |
| `Projects: disabled` | verifica a base de dados SQLite |
| `Failed to load MCP server` | endpoint, token, `/mcp` |
| `MCP auth token missing` | variável indicada por `token_env` |
| `MCP HTTP 401` | credenciais/cabeçalho Basic ou OAuth |
| `MCP HTTP 400` | protocolo, sessão ou parâmetros do servidor |
| `read_file` demasiado grande | usar `read_chunk` |
| `PermissionError` | política, permissões `R/W/X`, caminho fora da sandbox |
| Ferramenta não listada | servidor MCP com falha ou ferramenta não registada |
| Comando não reconhecido | `/help` |

Para um erro de configuração, o Hagar sai com código 1 e imprime o
detalhe em stderr. Para um erro de turno, o modelo recebe o
resultado da ferramenta e a auditoria conserva o evento.
