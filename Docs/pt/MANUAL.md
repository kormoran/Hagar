# HAGAR — Manual do utilizador

Versão: **0.3.0**

Este manual descreve o comportamento observável do Hagar: comandos,
opções, configuração, política e casos de erro. Para o projeto interno
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

Em Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item hagar.example.yaml hagar.yaml
New-Item -ItemType Directory -Force vault, logs
hagar --config hagar.yaml
```

`hagar.yaml`, `testvault/` e `logs/` são locais e não devem ser
versionados.

## 1.1 Ordem de arranque

1. O Hagar lê a configuração.
2. Carrega `policy.yaml`; se não for válido, aplica `DENY` a tudo.
3. Constrói o cliente LLM.
4. Inicializa o Vault e a memória, se configurados.
5. Constrói a sandbox de filesystem.
6. Registra as ferramentas locais.
7. Tenta carregar os servidores MCP; um servidor falhado não para os
   outros.
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
| `/tools [categoria]` | lista as ferramentas e as capabilities; o filtro é opcional |
| `/status` | mostra modelo, projeto, memória, auditoria e sandbox |
| `/mcp` | lista servidores MCP, endpoint e ferramentas importadas |
| `/audit [n]` | mostra os últimos `n` eventos; predefinição 10, máximo 50 |
| `exit` | sai |
| `quit` | sai |
| `Ctrl-D` | sai |
| `Ctrl-C` | interrompe; durante o OAuth sai com código 130 |

`/status` e `/audit` são comandos humanos: não passam pelo modelo e não
consomem chamadas de ferramentas.

## 2.2 Projeto

| Comando | Comportamento |
|---|---|
| `/project` ou `/project list` ou `/project ls` | lista os projetos ativos |
| `/project new <nome>` | cria um projeto e seleciona-o |
| `/project select <id>` ou `/project use <id>` | seleciona um projeto ativo |
| `/project free` ou `/project none` | passa a atividade livre |
| `/project status` ou `/project current` | mostra o projeto corrente |
| `/project archive <id>` | arquiva um projeto |
| `/project unarchive <id>` | reativa um projeto arquivado |
| `/project help` | ajuda |

`select` e `archive` usam o **id** do projeto, não o título.

Em atividade livre não é lida nem escrita memória de projeto; chat, resumo
e skills permanecem disponíveis.

## 2.3 Memória

| Comando | Comportamento |
|---|---|
| `/memory` ou `/memory help` ou `/memory ?` | ajuda |
| `/memory list [candidate\|confirmed\|archived]` | lista as skills e as contagens |
| `/memory show <slug>` | mostra uma skill |
| `/memory review` | revisão interativa das candidatas |
| `/memory confirm <slug>` | confirma uma skill |
| `/memory archive <slug>` | arquiva uma skill |
| `/memory archive search <texto>` | pesquisa nos transcripts arquivados |
| `/memory archive read <session> [offset] [limit]` | lê um transcript arquivado |

As palavras `search` e `read` são reservadas: um slug de skill chamado
exatamente `search` ou `read` não é arquivável com este comando.

Não existe um comando de eliminação: apenas se arquiva.

## 2.4 O que não é um comando

As ferramentas (`filesystem.*`, `memory.*`, `mcp.*`, `clock.now`, ...) são
chamadas pelo modelo através do registry. Não se escrevem como `/tool`.
A única exceção são os comandos informativos `/tools`, `/status`, `/mcp`,
`/audit`, que são de consola e não ferramentas.

---

# 3. Linha de comandos

```text
hagar [opções]
```

| Opção | Efeito |
|---|---|
| `--config PATH` | usa um ficheiro de configuração explícito |
| `--model NAME` | substitui `model.name` |
| `--project NAME` | seleciona um projeto ativo no arranque |
| `--free` | arranca em atividade livre |
| `--no-memory` | desativa memória e projetos para a sessão |
| `--no-native-tools` | força o protocolo JSON textual |
| `--version` | imprime a versão |

`--project` e `--free` são mutuamente exclusivos.

## 3.1 Procura da configuração

Ordem:

1. `--config PATH`
2. variável `HAGAR_CONFIG`
3. `./hagar.yaml` no diretório corrente

Os caminhos relativos dentro de `hagar.yaml` — auditoria, política, Vault —
são resolvidos em relação ao diretório do ficheiro de configuração, não ao
diretório a partir do qual lança o Hagar.

## 3.2 Códigos de saída

| Código | Significado |
|---|---|
| `0` | saída normal ou `--version` |
| `1` | erro de configuração ou projeto inválido |
| `130` | interrupção com Ctrl-C |

Um erro MCP não altera o código de saída: é registado e o harness
continua.

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

| Campo | Predefinição | Notas |
|---|---|---|
| `provider` | obrigatório | `ollama`, `deepseek`, `claude`, `gemini` |
| `name` | obrigatório | nome do modelo no provider |
| `host` | predefinição do provider | base URL da API |
| `native_tools` | `true` | se `false`, usa o protocolo JSON textual |
| `max_tokens` | `1024` | usado apenas pelo Claude |
| `api_key_env` | nome padrão | variável de ambiente da chave |

Provider e chaves:

| Provider | Chave padrão |
|---|---|
| `ollama` | nenhuma |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `claude` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |

As chaves nunca devem ser escritas no YAML. Se faltar uma chave, o cliente
não é construído e o arranque falha com um erro explícito.

Com a chamada nativa ativa, o Hagar usa as ferramentas estruturadas do
provider. Se o provider recusar o esquema (HTTP 400/404/422), no primeiro
passo passa ao protocolo JSON textual para essa sessão. O fallback cobre o
erro técnico, não garante que o modelo escolha bem a ferramenta.

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

| Campo | Predefinição | Efeito |
|---|---|---|
| `enabled` | `true` | ativa/desativa o registo |
| `path` | `logs/audit.jsonl` | ficheiro JSON Lines |
| `max_field_chars` | `2000` | trunca os campos |
| `max_bytes` | `5000000` | limiar de rotação |
| `max_files` | `100` | ficheiros rodados a conservar |
| `include_outputs` | `true` | se `false`, mascara a saída das ferramentas |

A auditoria contém dados sensíveis: saídas de ficheiros, respostas e
textos. Tem de ser protegida como o workspace. `/audit` mostra apenas os
eventos do ficheiro corrente, não os rodados.

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
- o Hagar permanece em execução mas nenhuma ferramenta é executada;
- a consola mostra `Policy: DENY ALL`.

## 4.4 `vault`

```yaml
vault:
  path: ./vault
```

É a raiz da memória Markdown. Tem de existir e ser escrevível.
Se faltar ou não for escrevível, a memória é desativada com um aviso; o
resto do harness continua.

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

| Campo | Predefinição | Efeito |
|---|---|---|
| `enabled` | `true` | ativa a memória |
| `vault_subdir` | `Hagar` | subdiretório dentro do Vault |
| `context_turns` | `10` | turnos recentes injetados; `0` desativa |
| `context_skills` | `3` | skills confirmadas injetadas |
| `context_project_memories` | `10` | títulos de decisões ativas |
| `max_context_chars` | `6000` | orçamento do bloco de memória |
| `project_max_active` | `200` | limiar de manutenção do projeto |
| `summary_max_chars` | `4000` | comprimento máximo do resumo |
| `max_skill_chars` | `4000` | comprimento máximo de uma skill |

`vault_subdir` tem de permanecer dentro do Vault: caminhos absolutos, `..`,
`I:/...` e outros drives Windows são recusados também em Linux.

O orçamento é em **caracteres**, não em tokens. Quando o bloco é cortado,
a auditoria registra `memory.context_trimmed`.

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
| `alias` | sim | um único segmento, único case-insensitive |
| `path` | sim | diretório existente do sistema anfitrião |
| `permissions` | não | predefinição `R`; letras `R`, `W`, `X` |

Permissões:

| Letra | Cobre |
|---|---|
| `R` | ler, listar, pesquisar, `stat` |
| `W` | escrever, criar, renomear, copiar, eliminar |
| `X` | `chdir` para o diretório |

O agente vê `/home/ai/<alias>/...`. `/home/ai` lista os alias mas não é um
diretório físico e não é possível entrar nele com `chdir`.

Restrições:

- alias e paths duplicados param a configuração;
- um path em falta para a configuração;
- os paths físicos podem conter espaços; os alias não;
- o Hagar não cria diretórios da sandbox e não assume uma home dedicada.

Limites de escrita:

| Campo | Efeito |
|---|---|
| `max_write_bytes` | máximo por operação individual |
| `min_free_bytes` | espaço livre mínimo restante |
| `session_write_bytes` | máximo cumulativo por sessão |
| `ask_over_bytes` | acima deste limiar pede confirmação |

`0` desativa o limite individual. Os limites são invariantes: um
excedimento é um erro da ferramenta, não um aviso.

## 4.7 `permissions`

```yaml
permissions:
  read: true
  write: false
  shell: false
  network: false
```

São o **teto do sistema**. Predefinição: `read=true`, os outros `false`.

| Campo | Concede |
|---|---|
| `read` | filesystem read, memory read |
| `write` | filesystem write/create/delete, memory write |
| `shell` | `FILESYSTEM_EXEC` |
| `network` | `NETWORK` |

`COMPUTE` e `MCP_CALL` estão sempre no teto, mas a política pode negá-los.
Se o teto não conceder uma capability, a política não a pode conceder.

## 4.8 `rag`

```yaml
rag:
  top_k: 8
```

Valor previsto para a recuperação documental. Não altera o contexto da
memória nesta versão.

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

O valor lido do ambiente é enviado **tal como está**: para Basic tem de já
ser `Basic <base64>`, não apenas o token.

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
`http://localhost:<port>/oauth/callback`. Se `client_id` faltar tenta-se o
registo dinâmico. Com `offline_access` é adicionado `prompt=consent`.
Os tokens ficam num ficheiro local restrito e são renovados
automaticamente.

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

Ordem de gravidade: `DENY > ASK > ALLOW`. Com várias capabilities pedidas
vale o AND: vence o efeito pior.

`ASK` sem canal de confirmação equivale a `DENY`. A confirmação na consola
mostra `lo faccio? (y/N)` e a predefinição é `N`.

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
| `NETWORK` | acesso à rede |
| `MCP_CALL` | chamada a ferramenta MCP |
| `COMPUTE` | cálculo local sem rede/filesystem |

## 5.3 Regras e especificidade

Uma regra pode filtrar com:

- `tools`: glob sobre o nome (`filesystem.*`, `mcp.atlassian.*`);
- `paths`: prefixos sobre o caminho escrito pelo modelo;
- `namespaces`: prefixos sobre o namespace.

Vence a regra mais específica: primeiro o número de filtros, depois o
comprimento do prefixo. Em caso de igualdade vence o efeito mais
restritivo. Sem regras vale o `default` do sujeito; a predefinição segura
é `deny`.

O scope `paths` compara o caminho **escrito pelo modelo**, não o resolvido
após `chdir`: um caminho absoluto ou uma mudança de diretório pode não
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
| Vault ausente/não escrevível | memória desativada, harness em execução |
| `projects` não escrevível | projetos desativados, memória ativa |
| Nenhum projeto ativo | atividade livre |
| Arranque não interativo | atividade livre, salvo `--project`/`--free` |
| `--project` inexistente | erro, saída 1 |
| Servidor MCP inalcançável | `mcp.failed`, servidor ignorado |
| Modelo/Ollama inalcançável | erro do turno, harness permanece ativo |
| Chave API ausente | cliente não construído, erro no arranque |
| Ferramenta negada | resultado de erro ao modelo, nenhuma execução |
| Ferramenta em `ASK` sem confirmação | recusa |
| Limite de escrita excedido | erro da ferramenta, nenhuma escrita |
| Ficheiro acima de 4096 bytes com `read_file` | erro, usar `read_chunk` |
| Página acima do limite | `has_more`/`next_offset` |
| Symlink | invisível; operação como caminho inexistente |
| Hard link/mount/junction | não detetados; responsabilidade do utilizador |
| Corrida TOCTOU | não controlada; responsabilidade do utilizador |
| Memória ausente durante o turno | `memory.failed`, o turno continua |
| Fim de sessão com turnos | resumo, arquivo, revisão do projeto |
| Revisão recusada | decisões candidatas com `auto_saved: true` |
| Projeto acima de `project_max_active` | pedido de arquivamento |
| Ctrl-C durante o OAuth | callback fechado, saída 130 |
| Comando `/` desconhecido | mensagem, não enviado ao modelo |

## 6.1 Fim de sessão

Na saída, se a memória estiver ativa e houver turnos:

1. o transcript é movido para `archive/chat/`;
2. é gerado um resumo (LLM, com fallback mecânico);
3. o resumo é guardado com link e hash;
4. se houver um projeto, o LLM propõe decisões candidatas;
5. o utilizador pode revê-las; se recusar permanecem candidatas.

Se não houver turnos não é criado nenhum resumo.

## 6.2 O que o Hagar não faz

- não executa comandos de shell;
- não dá ao modelo caminhos físicos;
- não garante isolamento de SO: a sandbox é path-based;
- não controla hard links, mounts, junctions ou TOCTOU;
- não apaga chats ou skills por antiguidade;
- não cifra o Vault;
- não promove automaticamente uma skill ou uma decisão a verdade.

---

# 7. Segurança operativa

- O modelo não é fidedigno: a política e as confirmações são os controlos.
- O Vault é Markdown em claro: pode conter conversas e decisões.
- A auditoria pode conter saídas de ficheiros: tem de ser protegida.
- As chaves API estão apenas no ambiente.
- Os tokens MCP/OAuth estão em caches locais com permissões restritas.
- Não exponha o Ollama ou o LM Studio na rede sem necessidade.
- Um hard link ou um mount dentro de um diretório allowed pode expor
  conteúdos externos: o Hagar não os deteta.

---

# 8. Resolução de problemas

| Sintoma | Verificação |
|---|---|
| `Policy: DENY ALL` | validar `policy.yaml` e `policy.path` |
| `Memory: disabled` | existe `vault.path`? é escrevível? |
| `Projects: disabled` | existe `vault.path/Hagar/projects`? |
| `Failed to load MCP server` | endpoint, token, `/mcp` |
| `MCP auth token missing` | variável indicada por `token_env` |
| `MCP HTTP 401` | credenciais/header Basic ou OAuth |
| `MCP HTTP 400` | protocolo, sessão ou parâmetros do servidor |
| `read_file` demasiado grande | usar `read_chunk` |
| `PermissionError` | política, permissões `R/W/X`, caminho fora da sandbox |
| Ferramenta não listada | servidor MCP falhado ou ferramenta não registada |
| Comando não reconhecido | `/help` |

Para um erro de configuração, o Hagar sai com código 1 e imprime o detalhe
em stderr. Para um erro de turno, o modelo recebe o resultado da ferramenta
e a auditoria conserva o evento.
