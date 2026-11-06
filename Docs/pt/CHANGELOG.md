# HAGAR — Changelog

O formato é livre mas estável: versões por ordem decrescente, com
referência ao commit quando útil.

---

# 0.3.0 — 2026-11-05

## Memória de projeto, resumo e arquivo

- Nova memória de projeto separada das skills:
  `Hagar/projects/<id>/index.md` e `decisions/<data>-<slug>.md`, com
  estado `candidate`/`active`/`superseded`/`archived`, alternativas,
  motivação, proveniência e `auto_saved`.
- No arranque o Hagar mostra os projetos ativos e a "atividade livre";
  comandos `/project list|new|select|free|status` e overrides
  `--project`/`--free`.
- No fim da sessão o transcript é movido para `archive/chat/` e
  substituído por um resumo com link e hash; fallback mecânico se o
  modelo não estiver disponível.
- As decisões de projeto são propostas como `candidate` e revistas no fim
  da sessão; se o utilizador recusar, permanecem candidatas com
  `auto_saved: true`.
- Contexto por índice: resumo e títulos das decisões ativas, não os
  corpos; detalhes com `memory.project_context`. Orçamento
  `max_context_chars` (caracteres, não tokens) e auditoria
  `memory.context_trimmed`.
- `project_max_active` desencadeia o pedido de arquivamento do projeto; o
  arquivamento é reversível e não apaga nada.
- Se o diretório `projects` não for escrevível, a memória permanece ativa
  e os projetos são desativados com `project.disabled`.
- Consulta do arquivo: `memory.archive_search` e
  `memory.archive_read`, comandos `/memory archive search|read`, com
  filtro por projeto e transcript que conserva `project` no frontmatter.
  O arquivo nunca é injetado automaticamente.

## Comandos de consola e manual

- Novos comandos de chat: `/help`, `/tools [categoria]`, `/status`, `/mcp`,
  `/audit [n]`.
- `/tools` agrupa as ferramentas por categoria e mostra as capabilities.
- `/status` indica modelo, chamada, projeto, memória, auditoria e
  filesystem.
- `/mcp` lista servidores configurados, endpoint e ferramentas
  importadas.
- `/audit` lê os últimos eventos do registo corrente, sem expor os campos
  não selecionados.
- Os comandos `/` desconhecidos não são enviados ao modelo.
- Novo `Docs/it/MANUAL.md` com comandos, CLI, `hagar.yaml`,
  `policy.yaml`, predefinições e comportamentos em caso de erro.

## MCP, OAuth e saída limpa

- Cliente MCP atualizado para `MCP-Protocol-Version` `2025-06-18` com
  fallback, reutilização de `Mcp-Session-Id` e corpo HTTP nos erros.
- OAuth: `audience` opcional, `prompt=consent` com `offline_access`,
  callback `http://localhost:<port>/oauth/callback`, scope no registo
  dinâmico.
- Ctrl-C durante o OAuth ou um turno fecha o callback local e sai com
  código 130, sem traceback.

## Ferramentas locais e filesystem v2

- Novo diretório `local_tools/` para os providers locais: cálculo,
  estatística, conversão de unidades, hora/data e feeds. Não são
  servidores MCP: registam `ToolDefinition` no registry.
- Ferramentas adicionadas: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `clock.now`, `calendar.date`, `think.echo`,
  `text.diff`, `url.parse`, `feed.read`.
- Filesystem: `list_dir`, `read_chunk`, `rename`, `copy_file`, `search`.
- Novas capabilities `COMPUTE` (cálculos locais, sempre no teto) e
  `NETWORK` (ativada por `permissions.network: true`); `feed.read` exige
  `NETWORK`.
- `permissions.network` na configuração; política: `COMPUTE` allow para
  calculator/statistics/units, `NETWORK` ask para feed.
- `feedparser` entre as dependências; o feed é descarregado com
  `requests`, timeout e limite de 5 MB, e apenas a partir de URL
  http/https.
- SSRF: resolução DNS obrigatória, apenas endereços globais (nada de
  loopback, redes privadas, link-local, multicast ou reservados),
  redirecionamentos manuais revalidados (máximo 3) e recusa dos URLs com
  credenciais.
- Restabelecida a permissão `rename` da sandbox, perdida durante a
  extensão; `filesystem.rename` exige `rename` na origem e `create` no
  destino.
- Renomeação `MCP_tools/` → `local_tools/`: são providers locais, não
  servidores MCP; pacote, imports, testes e documentação atualizados.
- Filesystem com raiz virtual `/home/ai`: `stat`, `list_dir`, `search`,
  `read_chunk` e as mensagens das ferramentas já não expõem o caminho
  físico; as entradas `/home/ai/...` são aceites.
- `read_chunk` alinha os limites nos caracteres UTF-8 e devolve
  `next_offset`; já não corta caracteres multibyte.
- `read_file` recusa ficheiros acima de 4096 bytes e remete para
  `read_chunk()` para evitar carregar o ficheiro inteiro para a context
  window.
- `list_dir` devolve no máximo 100 entradas por página e `search` 100
  resultados (máximo 500); ambos suportam `offset`, `next_offset`,
  `has_more` e a mensagem
  `voci: riportate X di Y; per continuare usa offset=Z`. Para árvores
  grandes convém restringir pattern/path em vez de iterar páginas.
- Novos limites de escrita `filesystem.limits`:
  `max_write_bytes` por operação, `min_free_bytes` como reserva,
  `session_write_bytes` cumulativo e `ask_over_bytes` para a confirmação.
  Os três primeiros são invariantes; `ask_over_bytes` passa pelo preflight
  do `ToolRegistry` e pergunta uma única vez, mesmo se a política for
  `ASK`.
- Os symlinks não existem para a sandbox: não são mostrados, lidos,
  seguidos ou apagados; `chdir` sobre um link responde
  "Directory not found". Decisão de projeto: permanecem invisíveis mesmo
  que o filesystem anfitrião os suporte.
- Hard links, mounts e junctions dentro dos diretórios allowed não são
  controlados nem detetados pelo Hagar. Não é um defeito: um hard link é
  um segundo nome do mesmo inode e um mount pode expor outro filesystem
  permanecendo dentro do prefixo. As ferramentas de filesystem não criam
  hard links. Para isolamento total o utilizador tem de garantir que não
  existam nos diretórios da sandbox. Responsabilidade do utilizador,
  ponto fechado.
- TOCTOU: esta versão não usa `openat2`, `O_NOFOLLOW` em cada componente
  ou handle Windows, pelo que não garante atomicidade entre verificação e
  operação. A corrida exige um processo local concorrente com acesso de
  escrita: cenário malicioso ou ambiente comprometido, não uso normal.
  Fechado como responsabilidade do utilizador; para isolamento total são
  necessários volume dedicado, utilizador separado, mount namespace ou
  container.
- `filesystem.allowed` substituído por `filesystem.sandbox`: cada entrada
  tem `alias`, `path` e permissões `R`/`W`/`X`. O agente vê
  `/home/ai/<alias>/...`; nada de `hdN`, nada de volumes ou diretórios
  intermédios sintéticos. `/home/ai` lista os alias mas não é um mount.
- Permissões por alias: `R` leitura/listagem/pesquisa/stat, `W`
  escrita/criação/renomeação/cópia/eliminação, `X` `chdir`; as permissões
  globais continuam a ser um teto.
- Alias obrigatório, segmento único, único case-insensitive, sem nomes
  reservados do Windows; as entradas da sandbox continuam a ser caminhos
  do sistema anfitrião e o Hagar não cria diretórios. Os caminhos físicos
  e os nomes internos podem conter espaços; o alias não.
- Runner POSIX `tools/run_tests.sh`; `run_tests.ps1` e o shim continuam
  específicos da sandbox Windows. Atualizados os comandos de benchmark.
- Correção multiplataforma a partir da CI: `vault_subdir` recusa também
  caminhos com drive Windows (`I:/...`) em POSIX; a recusa dos symlinks
  já não é engolida por `except OSError`, pelo que o caminho não é
  resolvido fora da sandbox.
- 691 testes aprovados, 2 ignorados em Windows; 693 aprovados, 0
  ignorados em Debian Linux (2026-11-06), incluindo os testes de
  symlink.

## Lançamento e multiplataforma

- Versão `0.3.0` em `pyproject.toml` e `hagar.py`.
- CI GitHub Actions em Linux, macOS e Windows com Python 3.11, 3.12 e
  3.13; build do pacote, `twine check` e smoke test do wheel.
- Actions atualizadas para `checkout@v7`, `setup-python@v7` e
  `upload-artifact@v7`, todas em Node 24; removido o warning de
  depreciação do Node 20.
- Workflow de release em tag `v*`: build sdist/wheel, verificação de que
  a tag corresponde à versão e criação da release GitHub.
- `hagar.example.yaml` portável; `hagar.yaml` local e `testvault/` são
  ignorados pelo git.
- `MANIFEST.in`, `SECURITY.md`, `CONTRIBUTING.md` e `RELEASING.md` para o
  primeiro lançamento público.

# 0.2.0 — 2026-11-04

Primeiro lançamento com memória revísivel, chamada nativa, autenticação
MCP/OAuth, retenção da auditoria e empacotamento instalável.

## Memória v2

- Ciclo de vida `candidate` → `confirmed` → `archived`: o LLM propõe, o
  utilizador promove a partir da CLI.
- Comandos `/memory list`, `/memory show`, `/memory review`,
  `/memory confirm`, `/memory archive`.
- Injeção automática apenas das skills confirmadas, até
  `memory.context_skills` (predefinição 3), por correspondência lexical;
  as candidatas e as arquivadas ficam de fora.
- `reviewed_at` no frontmatter; eventos de auditoria `memory.review` e
  `memory.status`.
- Retenção opção A: nenhuma eliminação automática; `archive` é reversível
  com `confirm`.
- `memory.context_skills` na configuração; 552 testes aprovados, 1
  ignorado.

## MCP OAuth interativo

- Fluxo authorization code + PKCE com callback em `127.0.0.1` e abertura
  do browser; fallback manual colando o URL.
- Discovery RFC 9728 (protected resource) e RFC 8414 (authorization
  server), com registo dinâmico do cliente se `client_id` faltar.
- Cache de token local com permissões `0600`, refresh automático e retry
  uma vez em caso de `401`.
- Config `auth.type: oauth` com `authorization_server`, `client_id`,
  `client_secret_env`, `scopes`, `redirect_port`, `token_cache`,
  `timeout`.
- Limites: nada de device flow, DPoP, mTLS ou client assertion.
- 522 testes aprovados, 1 ignorado.

## Retenção da auditoria

- Rotação em `<file>.<timestamp>` acima de `audit.max_bytes`.
- `audit.max_files` (predefinição 100) limita o número de ficheiros de
  auditoria, incluindo o ativo; as cópias mais antigas são eliminadas.
- A cadeia de hash continua a partir da cópia mais recente se o ficheiro
  ativo faltar.
- 504 testes aprovados, 1 ignorado.

## Autenticação MCP

- `mcp_servers[].auth`: `type: bearer` ou `type: header`, com
  `token_env` e, para o header, o nome do header.
- O token lê-se apenas do ambiente: não vai para o YAML, para a auditoria
  ou para os registos.
- Token em falta ou não-ASCII: o servidor é ignorado com `mcp.failed` e o
  harness continua com os outros.
- 496 testes aprovados, 1 ignorado.

## Benchmark nativo vs texto

- `tools/bench_native.py`: 9 tarefas de filesystem sobre o mesmo registry,
  comparação entre `native_step()` e `request_tool_call()`, com exatidão,
  latência e reparações.
- Primeiras medições: `llama3.1` 4/5 vs 5/5, `qwen3:8b` 4/5 vs 5/5,
  `hermes3:8b` 4/5 vs 3/5, `deepseek-flash` 8/9 vs 9/9 (subset Ollama,
  suite completa DeepSeek).
- Nenhum vencedor universal: a predefinição permanece nativa, com opt-out
  por modelo através de `model.native_tools` ou `--no-native-tools`.

## DeepSeek (live)

- Modelos atualizados: `deepseek-flash` (predefinição) e
  `deepseek-v4-pro`; `deepseek-chat` já não é válido.
- Mensagens de erro com o corpo da resposta da API; chaves não-ASCII
  recusadas com `ConfigError`.
- Nomes das ferramentas normalizados para as APIs que não admitem o ponto
  (`filesystem.read_file` → `filesystem__read_file`), com retorno ao nome
  interno.
- `tools/diagnose_deepseek.py` para rede, forma da chave e endpoint, sem
  imprimir a chave.
- Testes live: chat, chamada nativa e end-to-end sobre o filesystem.
- 479 testes aprovados, 1 ignorado; 9 testes live com `--live`.

## Chamada nativa (v1)

- `LLMClient.native_step()` e `LLMReply`: chamada nativa para Ollama,
  DeepSeek, Claude e Gemini; esquema dos parâmetros a partir de
  `ToolDefinition`.
- Mensagens canónicas `assistant` com `tool_calls` e `tool` com
  `tool_call_id`; cada backend tradu-las (`tool_calls`, `tool_use`/
  `tool_result`, `functionCall`/`functionResponse`).
- O Agent executa várias chamadas por turno, no limite `max_tool_calls`.
- Fallback automático para o protocolo textual em HTTP 400/404/422 no
  primeiro passo, com evento `llm.native_fallback`; `model.native_tools:
  false` e `--no-native-tools` forçam-no.
- Auditoria: `turn.start` com `native`, `llm.tool_choice` com
  `mode=native`.
- 476 testes aprovados, 1 ignorado; 7 testes live com `--live`.

## Higiene (v1)

- **Empacotamento**: `pyproject.toml` completo (metadados, dependências,
  setuptools), entry point `hagar`, versão única (`hagar.__version__`);
  `pip install -e .` verificado.
- **CLI**: `--config`, `--model`, `--no-memory`, `--version`;
  configuração procurada em `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml`.
- **Testes live**: marker `live`, excluídos da suite normal, `--live`
  para Ollama e providers remotos (ignorados sem chave).
- **MCP**: respostas `text/event-stream`, notificação
  `notifications/initialized`, normalização dos resultados em texto.
- **Auditoria**: cadeia de hash (`prev`/`hash`, `verify_chain`), rotação
  em `max_bytes`, mascaramento da saída das ferramentas com
  `include_outputs`.
- **URL base**: `model.host` usado por todos os providers.
- **Legacy**: removidos `tools/filesystem.py` e `llm/tool_result.py`.
- 442 testes aprovados, 1 ignorado; 6 testes live com `--live`.

## Memória (v1)

- `memory/store.py`: memória episódica (uma nota por sessão em
  `<vault>/Hagar/chat/`) e semântica
  (`<vault>/Hagar/skills/<slug>.md`);
- injeção automática dos últimos `memory.context_turns` turnos no prompt,
  com truncamento; um erro de memória não faz falhar o turno;
- ferramentas `memory.create_skill` (proveniência e estado `candidate`),
  `memory.list_skills`, `memory.get_context` (pesquisa por palavra-chave);
- capability `MEMORY_READ`/`MEMORY_WRITE`, namespace `chat`/`skills` para
  as políticas;
- configuração `memory.*` e desativação com aviso se o vault faltar;
- eventos de auditoria `memory.enabled`, `memory.disabled`,
  `memory.context`, `memory.turn`, `memory.failed`;

## Permissões (PermissionEvaluator v1)

- novo `core/permissions.py`: `Capability` (IntFlag), `Effect`
  (`ALLOW` / `ASK` / `DENY`, com deny-overrides), `Rule` com scope por
  ferramenta, path e namespace, `Subject`, `Resource`, `Decision` e
  evaluator puro;
- `policy.yaml` separado, lido antes de construir o LLM: em caso de erro
  todas as políticas passam a `DENY`, com evento `policy.failed` e
  aviso no chat;
- teto do sistema derivado de `permissions.read/write/shell`;
- `ASK` com confirmação na consola (`lo faccio? (y/N)`, predefinição N) e
  `ConfirmationProvider` para as futuras GUI;
- `ToolRegistry.execute` aplica a política e registra
  `permission.decision` e `permission.confirmation`;
- `ToolDefinition.capabilities` para todas as ferramentas (filesystem e
  MCP);
- `requires_confirmation` agora aplicado como piso de ASK;
- removido o stub incompleto `PolicyRule` de `core/models.py`;

## Filesystem v2, ferramentas matemáticas e feeds

### Filesystem

- `filesystem.list_dir`: listagem não recursiva do conteúdo de um
  diretório.
- `filesystem.list_dir` devolve metadados completos através de `FileInfo`
  para cada elemento encontrado.
- `filesystem.read_chunk`: leitura incremental de ficheiros de grandes
  dimensões através de offset e comprimento.
- `filesystem.read_chunk` opera ao nível dos bytes e devolve `has_more`
  para permitir ao agente continuar a leitura.
- `filesystem.rename`: renomeia ou move ficheiros dentro da sandbox.
- `filesystem.copy_file`: copia ficheiros com verificação das permissões e
  do espaço disponível.
- `filesystem.search`: pesquisa recursiva através de padrão glob (`*.py`,
  `*.md`, etc.).
- `filesystem.search` devolve:
  - número total de resultados encontrados;
  - número de resultados devolvidos;
  - indicação de truncamento (`truncated`);
  - lista dos resultados como `FileInfo`.
- Melhorada a exploração autónoma da sandbox: o agente pode agora
  enumerar diretórios, procurar ficheiros e ler documentos muito grandes
  sem saturar a context window.

### Calculadora

- Nova classe `local_tools/calculator.py`.
- Parsing através de AST segura, sem utilização de `eval()`.
- Suporte a:
  - `+`
  - `-`
  - `*`
  - `/`
  - `//`
  - `%`
  - `**`
  - parênteses.
- Constantes matemáticas:
  - `pi`
  - `e`
- Funções suportadas:
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
- Nova ferramenta MCP:

  `calculator.evaluate`
  
Todas as operações são validadas através de whitelist de nós AST,
operadores e funções permitidas.

### Estatística

Nova classe local_tools/statistics.py.

Nova ferramenta MCP:

`statistics.compute`

A classe é `Stats_calc`; a ferramenta exposta ao modelo é
`statistics.compute`. Operações suportadas:

- mean
- median
- stdev
- variance
- min
- max
- sum
- count

Resultados estruturados com:

- resultado da operação;
- tipo de estatística pedida;
- número de amostras processadas;
- resultado ou erro.

### Conversão de unidades

Nova classe `local_tools/unit_converter.py`.

Nova ferramenta MCP:

`units.convert`

Suporte às categorias:

Comprimento

- mm
- cm
- m
- km

Massa

- mg
- g
- kg
- t

Tempo

- ms
- s
- min
- hour
- day

Temperatura

- c
- f
- k

Ângulo

- deg
- rad

Dimensão de dados

- b
- kb
- mb
- gb
- tb

Sistema de alias e normalização das unidades:

meters → m
kilometers → km
hours → hour
celsius → c
fahrenheit → f
degrees → deg
etc.

Conversões dedicadas para:

temperatura (com offset);
ângulos (graus/radianos).

Conversões lineares para todas as outras categorias.

### Feed RSS e Atom

Nova classe `local_tools/feeder.py`.

Nova ferramenta MCP:

`feed.read`

Suporte transparente a feeds RSS e Atom através de uma única API.

Parâmetro max_items com limite de segurança para evitar saídas
excessivas.

Extração estruturada de:

- título;
- link;
- data de publicação;
- autor;
- resumo.

Limpeza automática do HTML presente nos feeds e devolução dos metadados do
feed:

- título;
- descrição;
- link;
- tipo (rss, atom, etc.).

Devolução do número total de elementos disponíveis, número de elementos
devolvidos e indicação de truncamento.

### Notas

Esta iteração amplia de forma significativa as capacidades operativas do
agente. Além do filesystem em sandbox, o Hagar dispõe agora de
ferramentas fiáveis para:

explorar e pesquisar conteúdos;
ler ficheiros muito grandes de forma incremental;
executar cálculos matemáticos determinísticos;
efetuar análises estatísticas;
converter unidades de medida pertencentes a domínios diferentes;
consumir fontes informativas estruturadas através de feeds RSS e Atom.

O objetivo continua a ser privilegiar ferramentas determinísticas,
estruturadas e facilmente utilizáveis pelos modelos através de chamada
nativa de ferramentas.


## Documentação

- `PROJECT_STATE.md` dividido em `ARCHITECTURE.md` (como é o sistema),
  `ROADMAP.md` (o que fazer e decisões tomadas) e este `CHANGELOG.md`.
- Roadmap atualizado com as decisões de 2026-11-03: memória no Vault,
  chamada nativa das ferramentas, `PermissionEvaluator`.

---

# 0.2.0 — 2026-11-03 (em desenvolvimento)

Commit: `137c985` — *Debug, suite de testes, registo de auditoria e
backends múltiplos*

## Adicionado

- **Registo de auditoria** (`core/audit.py`): JSON Lines append-only com
  timestamp UTC, `session` e id `turn`. Eventos por sessão, turno,
  escolha da ferramenta, protocolo, execução, erros, MCP e provider.
  Escrita best effort, truncamento configurável, nenhuma chave API no
  registo.
- **Backends múltiplos** (`llm/base.py`, `llm/factory.py`,
  `deepseek_client.py`, `claude_client.py`, `gemini_client.py`):
  `LLMClient` partilha a seleção das ferramentas, o parsing e a reparação
  do JSON; cada backend implementa apenas o transporte e a conversão dos
  papéis.
- **`filesystem.stat`**: tipo, tamanho em bytes, datas ISO 8601 e
  permissões efetivas da sandbox, numa única medição.
- **Suite de testes**: 259 testes, 1 ignorado, sem rede (Ollama e MCP
  simulados), com `tools/run_tests.ps1` e shim para a sandbox Windows.
- **`tools/bench_models.py`**: comparação reprodutível dos modelos Ollama
  em leitura, metadados, criação e chat.

## Alterado

- `model.provider` seleciona realmente o backend (antes era ignorado e
  usava-se sempre o Ollama). Chaves API do ambiente, nunca do YAML.
- Modelo predefinido: `llama3.1:latest` em vez de `qwen3:8b`.
- Os resultados das ferramentas são turnos `user` e não `system`, por
  compatibilidade com os backends remotos.
- Erros de configuração: saída limpa (`SystemExit 1`) com mensagem em
  stderr e evento `llm.failed` na auditoria.

## Corrigido

- `core/filesystem.py` estava truncado a meio de `mkdir`: faltavam
  `read_file`, `write_file`, `create_file`, `delete_file`,
  `free_space`. Cada ferramenta do filesystem falhava com
  `AttributeError`.
- `ToolDefinition.origin` era obrigatório mas nenhum provider o passava:
  o registo de qualquer ferramenta falhava com `TypeError`.
- `ToolResult` usava `tool` enquanto o `Agent` usava `tool_name`.
- `llm/ollama_client.py` usava `re` sem o importar e definia duas vezes
  `_tool_call_from_json`.
- `hagar.py` lia campos inexistentes de `AppConfig`: `main()` não
  arrancava.
- `ConfigLoader` não validava YAML vazio, raízes não-mapping, permissões
  não booleanas, `allowed` não lista.
- `write_file` podia criar ficheiros novos contornando a permissão
  `create`.
- O parsing aceita o alias `parameters`; uma resposta em prosa produz uma
  única tentativa de reparação, depois um erro explícito.

## Notas

Comparação de modelos Ollama (4 atividades, sandbox temporária, máximo 4
ferramentas por turno):

| modelo | read | stat | create | chat | reparações |
|---|---|---|---|---|---|
| `llama3.1:latest` | ok 10.9 s | ok 7.8 s | ok 8.1 s | ok 8.4 s | 1 |
| `qwen3:8b` | ok 34.2 s | ok 27.5 s | ok 15.9 s | ok 13.8 s | 1 |
| `hermes3:8b` | ok 13.6 s | loop, 4 ferramentas | ok 8.0 s | ok 5.2 s | 2 |
| `gemma:latest` | ferramenta errada | ficheiro errado | conteúdo errado | ok 6.4 s | 3 |

---

# 0.1.0 — 2026-11-02

Commit: `03b35bf` — *versão 0.1 alpha*

Primeira versão realmente funcional: o Hagar já não é uma interface para
o Ollama, é um agente operativo.

## Adicionado

- carregamento e validação da configuração YAML;
- `OllamaClient` com `generate`, `chat`, `request_tool_call`;
- `ToolRegistry`, `ToolDefinition`, `ToolCall`, `ToolResult`;
- `Agent` com ciclo multi-step, gestão de erros e limite de ferramentas;
- `FileSystemSandbox` com raízes, permissões herdáveis, proteção contra
  symlinks e verificação do espaço em disco;
- ferramentas de filesystem: leitura, escrita, criação, eliminação,
  criação de diretórios, mudança de diretório, espaço livre;
- cliente MCP via HTTP com discovery automática das ferramentas e
  namespace;
- `Vault` inicial para os ficheiros Markdown.

## Notas

A v0.1 é a primeira versão capaz de dialogar com um LLM local, expor
ferramentas, deixar o modelo escolher quais usar, operar sobre um
filesystem em sandbox e encadear várias operações de forma autónoma.
