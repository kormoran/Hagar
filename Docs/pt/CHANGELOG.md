# HAGAR — Changelog

O formato é livre mas estável: versões por ordem decrescente, com
referência ao commit quando útil.

---

# 0.7.0 — 2026-11-12

## Resumo

Release de orquestração local: receitas `dev.run`, boxed transform,
DSL Hagar Flow e list comprehension. O modo container fica fora desta
release.

## Receitas dev.run

- Novos `dev.list` e `dev.run` para receitas de confiança de teste,
  debug e build; `DEV_EXEC` é DENY por predefinição.
- `recipes.yaml` fora da sandbox, carregado uma única vez no arranque,
  sem hot reload; qualquer alteração exige reinício.
- Parâmetros tipados, `cwd`, timeout, ambiente explícito, exit code,
  output limitado e auditoria.
- Execução no host sobre uma cópia temporária do projeto, sem shell e
  sem container.

## Boxed transform

- Novos `box.list` e `box.run` para `summarize`, `translate` e
  `extract_json`; `BOX_EXEC` é DENY por predefinição.
- Input/output na sandbox, prompt fixo, sem memória ou ferramenta,
  chunking para documentos longos e validação JSON.
- Output escrito com o gate read-before-write.

## Hagar Flow

- Novos `flow.reference`, `flow.validate` e `flow.run`; `FLOW_EXEC` é
  DENY por predefinição.
- DSL Python restrita com validador AST e interpretador sem
  `eval`/`exec`; sem import, class, def, lambda, try, dict/set
  comprehension ou acesso a objetos Python.
- List comprehension com um único `for` e `if` opcionais, com âmbito
  local e orçamento de iterações.
- Primitivas `fs.*`, `box.*`, `memory.search`, `memory.context`,
  `memory.skill` e `project.context`, com orçamento de step, tool call,
  iterações e timeout; erros com linha e coluna.

## Reparação explícita

- Novo `flow.repair`: propõe uma correção válida sem a executar.
- `flow.run` nunca modifica o código nem chama o modelo para o reparar.
- `flow.repair` não repara erros de runtime, policy, confirmação ou
  timeout.
- Cada tentativa é registada na auditoria e no resultado.

# 0.6.0 — 2026-11-09

## Resumo

Release de segurança runtime e interação controlada: Hi-Fi, edição
atómica, read-before-write, checkpoint, timeout, repeat guard, spill,
compaction, AIsh e text.transform.

## Breaking change

- `write_file`, `edit_file`, `delete_file` e `rename` exigem uma leitura
  prévia na mesma sandbox e recusam ficheiros alterados.
- `filesystem.write_file`, `write_bytes`, `create_file` e `edit_file`
  usam a escrita atómica.
- `tools.timeout` vale 120 segundos por predefinição; `tools.repeat_limit`
  bloqueia a terceira chamada idêntica do mesmo turno.
- O AIsh está presente, mas `AISH` é negada pela policy predefinida.

## Modalidade Hi-Fi

- Novo pré-passo `core/hifi.py`: o modelo propõe interpretações com
  probabilidades, o Hagar escolhe a mais provável se a margem ultrapassar
  o limiar ou pede esclarecimento.
- Ativação com `--hifi` ou `hifi.enabled: true`; `hifi.margin` e
  `hifi.interpretations` configuráveis.
- Eventos de auditoria `hifi.interpretations`, `hifi.resolved`,
  `hifi.clarification` e `hifi.failed`.

## Edição e observação do filesystem

- Novo `filesystem.edit_file`: substituição literal com correspondência
  única (ou `replace_all`), escrita atómica através de ficheiro
  temporário e `os.replace`.
- `read_file`, `read_chunk` e `read_bytes` registam a versão observada;
  `write_file`, `edit_file`, `delete_file` e `rename` exigem uma leitura
  prévia e recusam ficheiros alterados.
- `write_file`, `write_bytes`, `create_file` e `edit_file` usam a escrita
  atómica.

## Checkpoint, timeout, spill e compaction

- Checkpoint por turno dos ficheiros modificados, com `/undo` e
  `workspace.undo`.
- `tools.timeout` por cada tool call e `tool.timeout`; o timeout é best
  effort.
- Repeat guard `tools.repeat_limit` sobre o hash `tool + argumentos`, com
  auditoria `tool.repeat`.
- Spill de output para `ArtifactStore` acima de 12.000 caracteres, com
  `tool.spilled`.
- Compaction determinística do contexto acima de 24.000 caracteres, com
  `context.compacted`.

## AIsh

- Novo `aish.exec`: linguagem com whitelist (`pwd`, `ls`, `cat`, `grep`,
  pipelines de texto, mutações de ficheiros individuais) que compila cada
  comando nas ferramentas Hagar; sem subprocesso e sem caminho do host.
- Capability `AISH` com regra `DENY` predefinida; o utilizador tem de a
  ativar explicitamente em `policy.yaml`.
- Auditoria `aish.command`; os comandos internos mantêm a policy, o
  checkpoint e a auditoria das ferramentas subjacentes.
- Novo `text.transform` read-only com operações `grep`, `sort`, `uniq`,
  `cut`, `tr`, `wc`, `head`, `tail`, `sed_replace`; o AIsh usa a
  ferramenta para os comandos textuais e acrescenta `sed` restrito.

# 0.5.2 — 2026-11-08

## Resumo

Release de consolidação: memória SQLite, subagentes, vision, ferramentas
de decisão, fichas de modelo, import/export Markdown e input broker CLI.

## Breaking change

- a memória predefinida já não é o Vault Markdown: usa
  `%LOCALAPPDATA%/Hagar/memory.db` ou `HAGAR_MEMORY_DB`;
- o Vault não é importado automaticamente;
- o backend `markdown` permanece disponível apenas como legacy;
- `memory.database` e `decisions.*` são novas secções de configuração.

## Novos backends LLM

- Novo backend `lmstudio` para o servidor OpenAI-compatível local do
  LM Studio, default `http://localhost:1234/v1`, sem chave salvo
  configuração do servidor.
- Novo backend `openai` (alias `chatgpt`) para a API OpenAI Chat
  Completions, chave `OPENAI_API_KEY`, base URL configurável.
- Os dois backends partilham o cliente OpenAI-compatível, com native
  tool calling e fallback JSON textual em HTTP 400/404/422.
- `model.timeout` configurável (predefinição 120 s) e passado a todos os
  backends; útil para modelos locais grandes.
- `hagar.example.yaml` e a documentação italiana atualizada.

## Service layer

- Novo `core/service.py` com `HarnessService`: turnos, estado, projeto,
  fim de sessão e eventos estruturados (`ServiceEvent`).
- `hagar.py` usa o service para `ask`, seleção de projeto e fecho da
  sessão; a CLI permanece um adapter.
- Eventos `tool.call`, `tool.result`, `permission.decision` e
  `permission.confirmation` reencaminhados por `Agent` e `ToolRegistry`
  para o sink do service; o output das ferramentas é truncado nos eventos.
- Novo `CommandService` para `/help`, `/tools`, `/status`, `/mcp`,
  `/audit`, `/project` e `/memory`, com `CommandResult` estruturado.
- A CLI usa o command service para os comandos slash; `/memory review`
  permanece interativa.
- Novo `QueueConfirmationProvider`: confirmações ASK da GUI com fila,
  timeout e recusa explícita.
- Nova GUI web local (`hagar web`): chat, eventos SSE, estado, projetos,
  tool call e modal de confirmação; token local e bind `127.0.0.1`.
- As desconexões SSE do browser já não produzem traceback em
  Windows (`ConnectionAbortedError`/WinError 10053).
- Ctrl-C fecha imediatamente `hagar web`: nada de `shutdown()` da thread
  de `serve_forever`, nada de join das threads SSE e summary saltado no
  encerramento.
- Novo `core/usage.py`: parsing usage OpenAI/DeepSeek/LM Studio,
  Claude, Gemini e Ollama, com `UsageLedger` por sessão.
- A GUI mostra input, output e total de tokens na barra lateral,
  atualizados pelo evento `usage.updated`.
- HTML, CSS e JavaScript da GUI separados em `web/` e servidos como
  assets estáticos; `core/web.py` injeta apenas o token.
- Novo `memory/index.py`: índice SQLite/FTS5 incremental e
  reconstruível das memórias Markdown, com fallback lexical.
- Nova ferramenta `memory.search`; comandos `/memory search`, `reindex`,
  `stats`.
- Stop cooperativo do turno (`Agent.cancel`, `POST /api/stop`) com
  botão na GUI e evento `turn.cancelled`.
- Input de imagens vision (`core/images.py`) com validação data URL,
  MIME e limite 10 MB; adapter OpenAI/LM Studio, Claude e Gemini.
- Upload de imagens na GUI com pré-visualização e remoção; WebP
  convertido em PNG antes do envio. Nenhuma imagem guardada em memória
  ou auditoria.
- Body JSON da GUI até 64 MB, para aceitar imagens de alta resolução em
  base64.
- Histórico de chat no separador dedicado: lista de `chat/` e
  `archive/chat/`; um clique retoma a mesma sessão e os novos turnos
  continuam o transcript.
- Botão **+ Novo chat** com `MemoryStore.new_session()` e reset do
  contexto; os transcripts anteriores permanecem no Vault.
- Separadores GUI: Chat, Chat history, Tool output, Audit, Thinking,
  Memories.
- `SessionLog` em memória para tool call/resultados e timeline;
  `/api/tools`, `/api/audit`, `/api/thinking`.
- Browser de memórias em só de leitura: `/api/memories`,
  `/api/memory`.
- `/usage` na CLI para os tokens acumulados da sessão; mesmo ledger
  usado pela GUI.
- Ferramentas e providers LLM são plugins: built-in em
  `local_tools/plugins.py` e `llm/plugins.py`, externos via entry point
  `hagar.tools`/`hagar.llm`.
- Erros dos plugins isolados e registados na auditoria; política e
  sandbox permanecem no host.
- Documentada a conceção da document tool em `DOCUMENT_TOOL.md`:
  grafo estrutura/semântica, CSV MVP, contrato `FormatPlugin`, ABI C e
  protocolo JSON do host nativo.
- Subagentes assíncronos: `agent.spawn/status/wait/result/cancel`, até
  dois filhos concorrentes, cliente LLM separado, workspace privado com
  inputs copiados, registry read-only, memória sem escritas,
  confirmações negadas, usage e auditoria dedicados; cleanup no fim do
  turno.
- `reason` obrigatório no spawn e capability `AGENT_SPAWN` separada: o
  filho não pode criar outros; `permissions.agents` controla o teto de
  sistema.
- Política do subagente estritamente mais restritiva que a do pai;
  políticas iguais ou não mais limitadas são recusadas.
- Timeout de parede de 5 minutos por subagente, cooperativo, com estado
  `timed_out`; `agent_id` em todos os eventos de auditoria.
- ASK dos subagentes encaminhadas ao utilizador com
  `ParentBridgeConfirmation`, timeout 180 segundos e DENY na expiração;
  o pai LLM não aprova.
- `vision.open` carrega PNG/JPEG/WebP da sandbox e anexa-os ao turno;
  `ToolResult.images` e o ciclo Agent gerem o canal multimodal sem
  base64 no texto. Áudio no roadmap.
- Memória SQLite como fonte primária: `memory/sqlite_store.py`,
  `memory/database.py`, WAL e backup; comandos `/memory sessions`,
  `/memory chat` e `/memory backup`. Projetos e decisões na mesma base
  de dados; backend Markdown apenas legacy.
- Export Markdown da base de dados com `/memory export <path> [--force]`:
  chat, skill, summary, projetos e decisões, escrita atómica.
- Import Markdown com `/memory import <path> [--force]`; FTS5 na base
  de dados primária com `bm25`/`snippet` e fallback `LIKE`.
- CLI com `ConsoleInputBroker`: um único leitor de consola, título de
  atenção e confirmações ASK com `F5` allow / `F8` deny; fallback `y/N`.
  O broker guarda e restaura o terminal, também em Ctrl-C.
- Nova classe de ferramentas `decision.*` com `decision.choose`:
  provider LLM local/remoto e classificador linear local, probabilidades
  validadas, auditoria `decision.result` e capability `DECISION`.
- Fichas técnicas dos modelos e benchmarks:
  `/models list|show|test|hardware`, latência, JSON, tool calling, data
  do último teste e deteção CPU/RAM/GPU sem dependências obrigatórias.
- Artifact store temporário e mailbox interna: `artifact.put`,
  `artifact.put_file`, `mailbox.send` para o filho; `artifact.read`,
  `artifact.list`, `mailbox.inbox/read/ack` para o pai. Capability
  `AGENT_DATA`, quotas e cleanup no fim do turno.
- `artifact.save_to` copia o artifact inteiro para um caminho escrevível
  da sandbox do pai; exige `AGENT_DATA`, `FILESYSTEM_WRITE` e
  `FILESYSTEM_CREATE`, com eventual confirmação de política.
- Auditoria `artifact.discarded` no fim do turno para artifacts não
  exportados, com motivo `unread` ou `read_but_not_saved`; a persistência
  permanece adiada.
- Auditoria desativada: separador desativado com etiqueta `audit off`.
- Thinking mostra o reasoning exposto pelo provider, caso contrário a
  timeline dos eventos.
- Base para a futura GUI, sem `input()` ou `print()` no service.

# 0.3.0 — 2026-11-05

## Memória de projeto, summary e arquivo

- Nova memória de projeto separada das skills:
  `Hagar/projects/<id>/index.md` e `decisions/<data>-<slug>.md`, com
  estado `candidate`/`active`/`superseded`/`archived`, alternativas,
  motivação, provenance e `auto_saved`.
- No arranque, o Hagar mostra os projetos ativos e a “atividade livre”;
  comandos `/project list|new|select|free|status` e override
  `--project`/`--free`.
- No fim da sessão, o transcript é movido para `archive/chat/` e
  substituído por um summary com link e hash; fallback mecânico se o
  modelo não estiver disponível.
- As decisões de projeto são propostas como `candidate` e revistas no
  fim da sessão; se o utilizador recusar, ficam candidatas com
  `auto_saved: true`.
- Contexto por índice: summary e títulos das decisões ativas, não os
  corpos; detalhes com `memory.project_context`. Orçamento
  `max_context_chars` (caracteres, não tokens) e auditoria
  `memory.context_trimmed`.
- `project_max_active` faz disparar o pedido de arquivo do projeto; o
  arquivo é reversível e não apaga nada.
- Se a diretoria `projects` não for escrevível, a memória permanece
  ativa e os projetos são desativados com `project.disabled`.
- Consulta do arquivo: `memory.archive_search` e `memory.archive_read`,
  comandos `/memory archive search|read`, com filtro por projeto e
  transcript que conserva `project` no frontmatter. O arquivo nunca é
  injetado automaticamente.

## Comandos de consola e manual

- Novos comandos de chat: `/help`, `/tools [categoria]`, `/status`,
  `/mcp`, `/audit [n]`.
- `/tools` agrupa as ferramentas por categoria e mostra as capability.
- `/status` indica modelo, calling, projeto, memória, auditoria e
  filesystem.
- `/mcp` lista servidores configurados, endpoint e ferramentas
  importadas.
- `/audit` lê os últimos eventos do log corrente, sem expor os campos
  não selecionados.
- Os comandos `/` desconhecidos não são enviados ao modelo.
- Novo `Docs/it/MANUAL.md` com comandos, CLI, `hagar.yaml`,
  `policy.yaml`, default e comportamentos em caso de erro.

## MCP, OAuth e saída limpa

- Cliente MCP atualizado para `MCP-Protocol-Version` `2025-06-18` com
  fallback, reutilização de `Mcp-Session-Id` e corpo HTTP nos erros.
- OAuth: `audience` opcional, `prompt=consent` com `offline_access`,
  callback `http://localhost:<port>/oauth/callback`, scope na dynamic
  registration.
- Ctrl-C durante OAuth ou um turno fecha o callback local e sai com
  código 130, sem traceback.

## Ferramentas locais e filesystem v2

- Nova diretoria `local_tools/` para os providers locais: cálculo,
  estatística, conversão de unidades, hora/data e feed. Não são
  servidores MCP: registam `ToolDefinition` no registry.
- Ferramentas acrescentadas: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `clock.now`, `calendar.date`, `think.echo`,
  `text.diff`, `url.parse`, `feed.read`.
- Filesystem: `list_dir`, `read_chunk`, `rename`, `copy_file`, `search`.
- Novas capability `COMPUTE` (cálculos locais, sempre no teto) e
  `NETWORK` (ativada por `permissions.network: true`); `feed.read` exige
  `NETWORK`.
- `permissions.network` na configuração; política: `COMPUTE` allow para
  calculator/statistics/units, `NETWORK` ask para feed.
- `feedparser` entre as dependências; o feed é descarregado com
  `requests`, timeout e limite de 5 MB, e apenas de URL http/https.
- SSRF: resolução DNS obrigatória, apenas endereços globais (nada de
  loopback, redes privadas, link-local, multicast ou reservados),
  redirect manuais revalidados (máximo 3) e recusa dos URL com
  credenciais.
- Restaurada a permissão `rename` da sandbox, perdida durante a
  extensão; `filesystem.rename` exige `rename` na origem e `create` no
  destino.
- Renomeação `MCP_tools/` → `local_tools/`: são providers locais, não
  servidores MCP; package, import, testes e documentação atualizados.
- Filesystem com raiz virtual `/home/ai`: `stat`, `list_dir`, `search`,
  `read_chunk` e as mensagens das ferramentas já não expõem o percurso
  físico; os inputs `/home/ai/...` são aceites.
- `read_chunk` alinha os limites aos caracteres UTF-8 e devolve
  `next_offset`; já não parte caracteres multibyte.
- `read_file` recusa ficheiros acima de 4096 bytes e remete para
  `read_chunk()` para evitar carregar todo o ficheiro na context window.
- `list_dir` devolve no máximo 100 entradas por página e `search` 100
  resultados (máximo 500); ambos suportam `offset`, `next_offset`,
  `has_more` e a mensagem
  `voci: riportate X di Y; per continuare usa offset=Z`. Para árvores
  grandes convém restringir pattern/path em vez de iterar páginas.
- Novos limites de escrita `filesystem.limits`: `max_write_bytes` por
  operação, `min_free_bytes` como reserva, `session_write_bytes`
  cumulativo e `ask_over_bytes` para a confirmação. Os primeiros três
  são invariantes; `ask_over_bytes` passa pelo preflight de
  `ToolRegistry` e pergunta uma única vez, mesmo que a política seja
  `ASK`.
- Os symlinks não existem para a sandbox: não são mostrados, lidos,
  seguidos ou apagados; `chdir` sobre um link responde
  “Directory not found”. Decisão de projeto: permanecem invisíveis
  mesmo que o filesystem anfitrião os suporte.
- Hard link, mount e junction dentro das diretorias allowed não são
  controlados nem detetados pelo Hagar. Não é um defeito: um hard link
  é um segundo nome do mesmo inode e um mount pode expor outro
  filesystem mantendo-se dentro do prefixo. As ferramentas filesystem
  não criam hard link. Para isolamento total, o utilizador tem de
  garantir que nas diretorias da sandbox não existem. Responsabilidade
  do utilizador, ponto fechado.
- TOCTOU: esta versão não usa `openat2`, `O_NOFOLLOW` em cada
  componente ou handle Windows, pelo que não garante atomicidade entre
  check e operação. A race exige um processo local concorrente com
  acesso em escrita: cenário malicioso ou ambiente comprometido, não
  uso normal. Fechado como responsabilidade do utilizador; para
  isolamento total são necessários volume dedicado, utilizador separado,
  mount namespace ou container.
- `filesystem.allowed` substituído por `filesystem.sandbox`: cada
  entrada tem `alias`, `path` e permissões `R`/`W`/`X`. O agente vê
  `/home/ai/<alias>/...`; nada de `hdN`, nada de volumes ou diretorias
  intermédias sintéticas. `/home/ai` lista os alias mas não é um mount.
- Permissões por alias: `R` leitura/listagem/pesquisa/stat, `W`
  escrita/criação/renomeação/cópia/eliminação, `X` `chdir`; as
  permissões globais permanecem um teto.
- Alias obrigatório, segmento único, único sem distinção de maiúsculas,
  sem nomes reservados Windows; as entradas da sandbox permanecem
  caminhos do sistema anfitrião e o Hagar não cria diretorias. Os
  caminhos físicos e os nomes internos podem conter espaços; o alias
  não.
- Runner POSIX `tools/run_tests.sh`; `run_tests.ps1` e o shim permanecem
  específicos da sandbox Windows. Atualizados os comandos de benchmark.
- Fix multiplataforma da CI: `vault_subdir` recusa também os caminhos
  com drive Windows (`I:/...`) em POSIX; a recusa dos symlinks já não é
  engolida por `except OSError`, pelo que o percurso não é resolvido
  fora da sandbox.
- 832 testes aprovados, 2 ignorados no Windows; 834 aprovados, 0
  ignorados no Debian Linux (2026-11-06), incluindo os testes symlink.

## Lançamento e multiplataforma

- Versão `0.3.0` em `pyproject.toml` e `hagar.py`.
- CI GitHub Actions em Linux, macOS e Windows com Python 3.11, 3.12 e
  3.13; build do pacote, `twine check` e smoke test da wheel.
- Actions atualizadas para `checkout@v7`, `setup-python@v7` e
  `upload-artifact@v7`, todas em Node 24; removido o warning de
  deprecação do Node 20.
- Workflow de release em tag `v*`: build sdist/wheel, verificação de que
  a tag corresponde à versão e criação da release GitHub.
- `hagar.example.yaml` portável; `hagar.yaml` local e `testvault/` são
  ignorados pelo git.
- `MANIFEST.in`, `SECURITY.md`, `CONTRIBUTING.md` e `RELEASING.md` para o
  primeiro lançamento público.

# 0.2.0 — 2026-11-04

Primeira release com memória revisível, chamada nativa, MCP auth/OAuth,
retenção da auditoria e packaging instalável.

## Memória v2

- Ciclo de vida `candidate` → `confirmed` → `archived`: o LLM propõe,
  o utilizador promove da CLI.
- Comandos `/memory list`, `/memory show`, `/memory review`,
  `/memory confirm`, `/memory archive`.
- Injeção automática apenas das skills confirmadas, até
  `memory.context_skills` (predefinição 3), por match lexical; as
  candidatas e as arquivadas ficam de fora.
- `reviewed_at` no frontmatter; eventos de auditoria `memory.review` e
  `memory.status`.
- Retenção opção A: nenhuma eliminação automática; `archive` é
  reversível com `confirm`.
- `memory.context_skills` na configuração; 552 testes aprovados, 1
  ignorado.

## MCP OAuth interativo

- Fluxo authorization code + PKCE com callback em `127.0.0.1` e
  abertura do browser; fallback manual colando o URL.
- Discovery RFC 9728 (protected resource) e RFC 8414 (authorization
  server), com registo dinâmico do cliente se faltar `client_id`.
- Cache de token local com permissões `0600`, refresh automático e retry
  uma vez em `401`.
- Config `auth.type: oauth` com `authorization_server`, `client_id`,
  `client_secret_env`, `scopes`, `redirect_port`, `token_cache`,
  `timeout`.
- Limites: nada de device flow, DPoP, mTLS ou client assertion.
- 522 testes aprovados, 1 ignorado.

## Audit retention

- Rotação em `<file>.<timestamp>` acima de `audit.max_bytes`.
- `audit.max_files` (predefinição 100) limita o número de ficheiros de
  auditoria, incluindo o ativo; os backups mais antigos são eliminados.
- A cadeia de hash continua a partir do backup mais recente se o
  ficheiro ativo faltar.
- 504 testes aprovados, 1 ignorado.

## MCP auth

- `mcp_servers[].auth`: `type: bearer` ou `type: header`, com
  `token_env` e, para o header, o nome do header.
- O token lê-se apenas do ambiente: não vai no YAML, na auditoria ou
  nos logs.
- Token em falta ou não-ASCII: o servidor é ignorado com `mcp.failed` e
  o harness continua com os outros.
- 496 testes aprovados, 1 ignorado.

## Benchmark nativo vs texto

- `tools/bench_native.py`: 9 tarefas filesystem no mesmo registry,
  comparação entre `native_step()` e `request_tool_call()`, com
  acurácia, latência e reparações.
- Primeiras medições: `llama3.1` 4/5 vs 5/5, `qwen3:8b` 4/5 vs 5/5,
  `hermes3:8b` 4/5 vs 3/5, `deepseek-flash` 8/9 vs 9/9 (subset Ollama,
  suite completa DeepSeek).
- Nenhum vencedor universal: o default permanece nativo, com opt-out
  por modelo através de `model.native_tools` ou `--no-native-tools`.

## DeepSeek (live)

- Modelos atualizados: `deepseek-flash` (default) e `deepseek-v4-pro`;
  `deepseek-chat` já não é válido.
- Mensagens de erro com o corpo da resposta API; chaves não-ASCII
  recusadas com `ConfigError`.
- Nomes das ferramentas normalizados para as API que não admitem o
  ponto (`filesystem.read_file` → `filesystem__read_file`), com retorno
  ao nome interno.
- `tools/diagnose_deepseek.py` para rede, forma da chave e endpoint,
  sem imprimir a chave.
- Testes live: chat, chamada nativa e end-to-end no filesystem.
- 479 testes aprovados, 1 ignorado; 9 testes live com `--live`.

## Chamada nativa (v1)

- `LLMClient.native_step()` e `LLMReply`: chamada nativa para Ollama,
  DeepSeek, Claude e Gemini; esquema dos parâmetros de `ToolDefinition`.
- Mensagens canónicas `assistant` com `tool_calls` e `tool` com
  `tool_call_id`; cada backend tradu-las (`tool_calls`, `tool_use`/
  `tool_result`, `functionCall`/`functionResponse`).
- O Agent executa várias chamadas por turno, dentro do limite
  `max_tool_calls`.
- Fallback automático ao protocolo textual em HTTP 400/404/422 no
  primeiro passo, com evento `llm.native_fallback`;
  `model.native_tools: false` e `--no-native-tools` forçam-no.
- Auditoria: `turn.start` com `native`, `llm.tool_choice` com
  `mode=native`.
- 476 testes aprovados, 1 ignorado; 7 testes live com `--live`.

## Higiene (v1)

- **Packaging**: `pyproject.toml` completo (metadados, dependências,
  setuptools), entry point `hagar`, versão única (`hagar.__version__`);
  `pip install -e .` verificado.
- **CLI**: `--config`, `--model`, `--no-memory`, `--version`;
  configuração procurada em `--config` → `HAGAR_CONFIG` →
  `./hagar.yaml`.
- **Testes live**: marker `live`, excluídos da suite normal, `--live`
  para Ollama e providers remotos (ignorados sem chave).
- **MCP**: respostas `text/event-stream`, notificação
  `notifications/initialized`, normalização dos resultados em texto.
- **Auditoria**: cadeia de hash (`prev`/`hash`, `verify_chain`),
  rotação em `max_bytes`, redação do output das ferramentas com
  `include_outputs`.
- **URL base**: `model.host` usado por todos os providers.
- **Legacy**: removidos `tools/filesystem.py` e `llm/tool_result.py`.
- 442 testes aprovados, 1 ignorado; 6 testes live com `--live`.

## Memória (v1)

- `memory/store.py`: memória episódica (uma nota por sessão em
  `<vault>/Hagar/chat/`) e semântica
  (`<vault>/Hagar/skills/<slug>.md`);
- injeção automática dos últimos `memory.context_turns` turnos no
  prompt, com truncamento; um erro de memória não faz falhar o turno;
- ferramentas `memory.create_skill` (provenance e estado `candidate`),
  `memory.list_skills`, `memory.get_context` (pesquisa por palavra-chave);
- capability `MEMORY_READ`/`MEMORY_WRITE`, namespace `chat`/`skills`
  para as políticas;
- configuração `memory.*` e desativação com aviso se o vault faltar;
- eventos de auditoria `memory.enabled`, `memory.disabled`,
  `memory.context`, `memory.turn`, `memory.failed`;

## Permissões (PermissionEvaluator v1)

- novo `core/permissions.py`: `Capability` (IntFlag), `Effect`
  (`ALLOW` / `ASK` / `DENY`, com deny-overrides), `Rule` com scope por
  ferramenta, path e namespace, `Subject`, `Resource`, `Decision` e
  evaluator puro;
- `policy.yaml` separado, lido antes de construir o LLM: em caso de
  erro, todas as políticas passam a `DENY`, com evento `policy.failed`
  e warning no chat;
- teto de sistema derivado de `permissions.read/write/shell`;
- `ASK` com confirmação da consola (`lo faccio? (y/N)`, default N) e
  `ConfirmationProvider` para as futuras GUI;
- `ToolRegistry.execute` aplica a política e registra
  `permission.decision` e `permission.confirmation`;
- `ToolDefinition.capabilities` para todas as ferramentas (filesystem e
  MCP);
- `requires_confirmation` agora aplicado como piso de ASK;
- removido o stub incompleto `PolicyRule` de `core/models.py`;

## Filesystem v2, ferramentas matemáticas e feed

### Filesystem

- `filesystem.list_dir`: listagem não recursiva do conteúdo de uma
  diretoria.
- `filesystem.list_dir` devolve metadados completos através de `FileInfo`
  para cada elemento encontrado.
- `filesystem.read_chunk`: leitura incremental de ficheiros de grandes
  dimensões através de offset e comprimento.
- `filesystem.read_chunk` opera ao nível dos bytes e devolve `has_more`
  para permitir ao agente continuar a leitura.
- `filesystem.rename`: renomeia ou move ficheiros dentro da sandbox.
- `filesystem.copy_file`: copia ficheiros com verificação das permissões
  e do espaço disponível.
- `filesystem.search`: pesquisa recursiva através de pattern glob
  (`*.py`, `*.md`, etc.).
- `filesystem.search` devolve:
  - número total de resultados encontrados;
  - número de resultados devolvidos;
  - indicação de truncamento (`truncated`);
  - lista dos resultados como `FileInfo`.
- Melhorada a exploração autónoma da sandbox: o agente pode agora
  enumerar diretorias, procurar ficheiros e ler documentos muito grandes
  sem saturar a context window.

### Calculator

- Nova classe `local_tools/calculator.py`.
- Parsing através de AST seguro, sem utilização de `eval()`.
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

Parâmetro max_items com limite de segurança para evitar output
excessivo.

Extração estruturada de:

- título;
- link;
- data de publicação;
- autor;
- sumário.

Limpeza automática do HTML presente nos feeds e devolução dos metadados
do feed:

- título;
- descrição;
- link;
- tipo (rss, atom, etc.).

Devolução do número total de elementos disponíveis, número de elementos
devolvidos e indicação de truncamento.

### Notas

Esta iteração amplia de forma significativa as capacidades operativas do
agente. Além do filesystem sandboxed, o Hagar dispõe agora de
ferramentas fiáveis para:

explorar e pesquisar conteúdos;
ler ficheiros muito grandes de forma incremental;
executar cálculos matemáticos determinísticos;
efetuar análises estatísticas;
converter unidades de medida pertencentes a domínios diferentes;
consumir fontes informativas estruturadas através de feeds RSS e Atom.

O objetivo continua a ser privilegiar ferramentas determinísticas,
estruturadas e facilmente utilizáveis pelos modelos através de tool
calling nativo.


## Documentação

- `PROJECT_STATE.md` dividido em `ARCHITECTURE.md` (como é o sistema),
  `ROADMAP.md` (o que fazer e decisões tomadas) e este `CHANGELOG.md`.
- Roadmap atualizado com as decisões de 2026-11-03: memória no Vault,
  chamada nativa das ferramentas, `PermissionEvaluator`.

---

# 0.2.0 — 2026-11-03 (em desenvolvimento)

Commit: `137c985` — *Debug, suite de testes, audit log e backend múltiplos*

## Adicionado

- **Audit log** (`core/audit.py`): JSON Lines append-only com timestamp
  UTC, `session` e `turn` id. Eventos por sessão, turno, escolha da
  ferramenta, protocolo, execução, erros, MCP e provider. Escrita best
  effort, truncamento configurável, nenhuma chave API no log.
- **Backend múltiplos** (`llm/base.py`, `llm/factory.py`,
  `deepseek_client.py`, `claude_client.py`, `gemini_client.py`):
  `LLMClient` partilha seleção das ferramentas, parsing e reparação do
  JSON; cada backend implementa apenas o transporte e a conversão dos
  papéis.
- **`filesystem.stat`**: tipo, dimensão em bytes, datas ISO 8601 e
  permissões efetivas da sandbox, numa única medição.
- **Suite de testes**: 259 testes, 1 ignorado, sem rede (Ollama e MCP
  simulados), com `tools/run_tests.ps1` e shim para a sandbox Windows.
- **`tools/bench_models.py`**: comparação reproduzível dos modelos
  Ollama em leitura, metadados, criação e chat.

## Alterado

- `model.provider` seleciona realmente o backend (antes era ignorado e
  usava-se sempre o Ollama). Chaves API do ambiente, nunca do YAML.
- Modelo predefinido: `llama3.1:latest` em vez de `qwen3:8b`.
- Os resultados das ferramentas são turnos `user` e não `system`, para
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
- O parsing aceita o alias `parameters`; uma resposta em prosa produz
  uma única tentativa de reparação, depois erro explícito.

## Notas

Comparação de modelos Ollama (4 atividades, sandbox temporária, máx. 4
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

Primeira versão realmente funcional: o Hagar já não é uma interface
para o Ollama, é um agente operativo.

## Adicionado

- carregamento e validação da configuração YAML;
- `OllamaClient` com `generate`, `chat`, `request_tool_call`;
- `ToolRegistry`, `ToolDefinition`, `ToolCall`, `ToolResult`;
- `Agent` com ciclo multi-step, gestão de erros e limite às ferramentas;
- `FileSystemSandbox` com raízes, permissões herdáveis, proteção contra
  os symlinks e controlo do espaço em disco;
- ferramentas filesystem: leitura, escrita, criação, eliminação,
  criação de diretoria, mudança de diretoria, espaço livre;
- cliente MCP via HTTP com discovery automática das ferramentas e
  namespace;
- `Vault` inicial para os ficheiros Markdown.

## Notas

A v0.1 é a primeira versão capaz de dialogar com um LLM local, expor
ferramentas, fazer o modelo escolher quais usar, operar num filesystem
sandboxed e concatenar várias operações em autonomia.
