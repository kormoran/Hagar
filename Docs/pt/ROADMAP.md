# HAGAR — Roadmap

Versão corrente: 0.5.2 (em preparação)
Última atualização: 2026-11-07

As decisões tomadas são indicadas como tal; os pontos ainda em aberto são
listados no fim de cada área. As secções 1–9 são o histórico até
à 0.5.2; o plano operativo corrente é a secção 0.

---

# 0. Plano corrente (post-0.5.2)

## 0.1 Estado

Publicado:

- release GitHub `v0.3.0`;
- CI Linux/macOS/Windows com Python 3.11, 3.12 e 3.13;
- actions atualizadas para Node 24;
- documentação italiana mais traduções em inglês, espanhol, chinês,
  russo, português e árabe;
- backend `lmstudio`, `openai`/`chatgpt` e `model.timeout`.

Concluído depois da release, ainda não lançado:

- `HarnessService`: turnos, estado, projetos, eventos e fim de sessão sem
  `input()`/`stdout`;
- `CommandService`: `/help`, `/tools`, `/status`, `/mcp`, `/audit`,
  `/project`, `/memory` com `CommandResult` estruturado;
- event bridge `Agent`/`ToolRegistry` → `tool.call`, `tool.result`,
  `permission.*`;
- GUI web local `hagar web` com SSE, chat, projetos, estado e confirmações
  ASK modais;
- `QueueConfirmationProvider` com timeout e resolução pela GUI;
- `core/usage.py`: parsing de tokens para OpenAI/LM Studio/DeepSeek, Claude,
  Gemini e Ollama; `UsageLedger` por sessão;
- barra lateral da GUI com tokens input/output/total atualizados via
  `usage.updated`;
- `MemoryIndex`: índice SQLite/FTS5 incremental e reconstruível;
- memória SQLite como fonte primária: sessões, turnos, skills e summary;
- comandos `/memory sessions`, `/memory chat`, `/memory backup`;
- ferramenta `memory.search`, `/memory search`, `/memory reindex`,
  `/memory stats`;
- assets da GUI separados em `web/index.html`, `web/style.css`, `web/app.js`.

## 0.2 Ordem das próximas releases

| Release | Objetivo | Estado |
|---|---|---|
| **0.4.0** | Índice SQLite das memórias | integrado na 0.5.2 |
| **0.4.x** | GUI: stop do turno, histórico, vision | integrado na 0.5.2 |
| **0.5.0** | Subagentes | integrado na 0.5.2 |
| **0.5.2** | Release corrente | em preparação |
| **0.6.0** | Broker LLM | próximo |
| **0.7.0** | Ferramenta SQL read-only | congelado |

A ordem pode mudar, mas a restrição é: **nada de subagentes sem usage e
limites; nada de broker sem subagentes e model registry.**

## 0.3 0.4.0 — Índice SQLite das memórias

Estado: implementado; falta a verificação no Vault real e a eventual
medição das prestações.

- posição: dados locais da aplicação, não dentro do Vault sincronizado;
- esquema: notas, skills, decisões, sessões, tags, FTS5;
- sync incremental por path/hash/mtime;
- `rebuild()` atómico, índice apagável e reconstruível;
- fallback à pesquisa lexical se o FTS5 não estiver disponível;
- ferramenta `memory.search` com filtros projeto/kind/status;
- `/memory reindex` e `/memory stats`;
- nenhum caminho real exposto ao modelo.

Critério de saída: apagar a BD não perde memória; reconstruí-la
devolve os mesmos resultados.

## 0.4 0.4.x — GUI

- botão **Stop** do turno — implementado;
- vision: upload de imagem no composer, com adapter por provider —
  implementado (OpenAI/LM Studio, Claude, Gemini);
- histórico de chat visível depois de um refresh — implementado como lista
  dos chats anteriores com recarga do Vault, retoma da sessão e
  **+ Novo chat**;
- separadores Chat, Chat history, Tool output, Audit, Thinking e Memories —
  implementados; Audit desativa-se se o log estiver desligado, Thinking usa o
  reasoning se disponível e, caso contrário, a timeline;
- browser de memórias em só de leitura — implementado;
- comando `/usage` do lado da CLI — implementado;
- ferramentas e providers LLM como plugins com entry point — implementado;
  audit sink adiado.

A vision não deve entrar na memória como base64: apenas hash e
descrição.

## 0.5 0.5.x — Subagentes e consolidação

- [x] MVP síncrono: `AgentSpec`, `agent.run`, ferramentas read-only, memória
  read-only, confirmações negadas, auditoria `agent.*`, usage separado;
- [x] `agent.spawn/status/wait/result/cancel` com threads e até dois
  subagentes concorrentes;
- [x] registry e workspace privado por child, input copiados e cleanup;
- [x] auditoria serializada com lock;
- [x] `reason` obrigatório e capability `AGENT_SPAWN` separada;
- [x] artifact store, mailbox e outbox `artifact.put`/`mailbox.send`,
  com capability `AGENT_DATA` e cleanup;
- [x] auditoria `artifact.discarded` para artifact não exportados;
- [ ] persistência/orphan retention (apenas se necessária);
- [x] projetos e decisões na mesma base de dados SQLite;
- [x] export Markdown da base de dados (`/memory export`);
- [x] import Markdown para a base de dados (`/memory import`);
- [x] FTS5 na base de dados primária com ranking e snippet;
- [x] timeout de parede de 5 minutos por subagente;
- [x] política do child estritamente mais restritiva que a do pai;
- [x] `agent_id` nos eventos de pai, filhos e registry;
- [x] ASK dos filhos encaminhadas ao utilizador com timeout 180 segundos e DENY;
- [x] ferramenta `decision.choose` com provider LLM e classificador linear;
- [ ] adapter Jev/Kev e treino automático de classificadores;
- [ ] budget de tokens/custo;
- [ ] `parent_id` em cada evento interno do child;
- [ ] `audio.open`/`AudioInput`: o canal de anexos é partilhado com as
  imagens, mas são necessários providers audio-native, formatos e semântica ASR
  diferentes; sem timeline;
- [x] confirmações ASK da consola com input broker, F5/F8 e fallback GUI;

## 0.6 0.6.0 — Broker LLM

- fichas técnicas JSON e benchmarks dos modelos (`/models test`);
- deteção de hardware CPU/RAM/GPU (`/models hardware`);
- `ModelRegistry` com context window, tool calling, preços, latência e
  localidade;
- `TaskProfile` com ferramentas exigidas, sensibilidade dos dados, budget e contexto;
- routing por regras/pontuação, não "um LLM escolhe o modelo";
- proposta de `AgentSpec` validada pelo host;
- o broker nunca concede permissões: só pode propor um subconjunto;
- override humano e auditoria `broker.decision`.

## 0.7 0.7.0 — Ferramenta SQL

- apenas leitura na primeira versão;
- SQLite `mode=ro`, `PRAGMA query_only`, uma única instrução;
- nada de `ATTACH`, `PRAGMA` de escrita ou `load_extension`;
- timeout, limite de linhas/bytes e auditoria da query;
- alias de base de dados configurados, nunca paths arbitrários;
- capability `DATABASE_READ`;
- escrita e base de dados de rede apenas numa fase posterior, com
  `DATABASE_WRITE` e `NETWORK`.

## 0.8 Pontos abertos

- workflow de release idempotente se a release já existir;
- PyPI: adiado, não bloqueia a 0.4;
- MCP OAuth Atlassian: Basic funciona, o fluxo OAuth falta
  validar;
- testes live MCP/OAuth e providers remotos;
- manutenção das traduções: regeneram-se apenas na release, não a
  cada commit;
- concorrência e escritas atómicas do Vault: a avaliar antes de
  subagentes com memória partilhada;
- document tool: contrato e protocolo definidos em `DOCUMENT_TOOL.md`;
  MVP CSV ainda por implementar.

## 0.9 Documentação

`Docs/it` é a única fonte mantida durante o desenvolvimento. As diretorias
`Docs/en`, `Docs/es`, `Docs/zh`, `Docs/ru`, `Docs/pt` e `Docs/ar` são
regeneradas apenas quando se prepara uma release.

---

# 1. Direção

O Hagar passou de "ideia" a "sistema funcional" (v0.1) e depois a um
harness com auditoria, backend múltiplos e suite de testes (v0.2 em curso). O
próximo salto não é acrescentar ferramentas: é dar ao sistema uma **memória** e
uma forma de chamar as ferramentas menos frágil do que o JSON textual.

Ordem decidida:

1. memória no Vault;
2. chamada nativa para os providers que a suportam;
3. PermissionEvaluator — **v1 feita** (policy.yaml, ASK, auditoria);
4. higiene (auditoria, MCP, packaging, testes live).

---

# 2. Prioridade 1 — Memória no Vault

## 2.0 Estado: v2 implementada (2026-11-04)

Realizado:

- episódica escrita pelo harness, uma nota por sessão;
- injeção automática dos últimos `context_turns` turnos;
- ferramentas `memory.create_skill`, `memory.list_skills`, `memory.get_context`;
- provenance (`source_session`, `source_turn`, `model`), estado
  `candidate`, deduplicação por slug;
- política `MEMORY_READ`/`MEMORY_WRITE` e namespace `chat` / `skills`;
- vault ausente → memória desativada com aviso, harness ativo;
- ciclo de vida `candidate` → `confirmed` → `archived` com revisão
  humana da CLI (`/memory review`, `confirm`, `archive`);
- injeção automática apenas das skills confirmadas, top 3 por match
  lexical;
- retention opção A: nenhuma eliminação automática, apenas arquivo;
- memória de projeto separada das skills: decisões, alternativas,
  motivações, estado e provenance;
- seleção de projeto no arranque, `--project`/`--free`, comandos
  `/project`;
- summary de fim de sessão com fallback, transcript em `archive/chat/`
  e link/hash no summary;
- review das decisões no fim de sessão; se recusada, ficam
  `candidate` com `auto_saved: true`;
- contexto por índice com budget `max_context_chars` (caracteres, não
  tokens) e `memory.project_context` para os detalhes;
- `project_max_active` para o pedido de arquivo do projeto;
- consulta do arquivo com `memory.archive_search`,
  `memory.archive_read`, `/memory archive search|read`, filtro por
  projeto e transcript com `project` no frontmatter.

Faltam: retention dos chats, pesquisa semântica, GUI.

## 2.1 Decisões tomadas

- **Episódica escrita pelo harness.** Os turnos de chat são registados
  pelo harness por predefinição: é um registo mecânico, não um juízo do
  modelo. Nenhum turno em falta, nenhuma memória inventada.
- **Semântica escrita pelo LLM, a pedido.** O modelo pode propor
  uma memória (skill) apenas através de uma ferramenta dedicada. A proposta é
  explícita, atribuível e revisível — a Primeira Lei proíbe
  tratá-la como verdade.
- **Apenas Vault Obsidian.** Nenhuma escrita no filesystem real para a
  memória (para já). A `filesystem.sandbox` continua a ser a sandbox operativa.
- **O Vault não se reescreve.** As ferramentas acrescentam notas ou secções; não
  sobrescrevem notas cuidadas pelo utilizador.
- **Projetos explícitos.** O projeto escolhe-se no arranque a partir da lista
  dos projetos ativos, ou com `--project`; `--free` e "atividade
  livre" não têm memória de projeto.
- **Decisões de projeto.** São separadas das skills: registam
  decisões, alternativas e motivações. Propõem-se como `candidate`
  e revêem-se no fim da sessão; se a review for recusada ficam
  candidatas com `auto_saved: true`, não se tornam verdades automáticas.
- **Nenhuma quota de tokens.** O contexto é limitado por construção:
  índice do projeto, títulos das decisões, summary e
  `max_context_chars` em caracteres. Não se mede a context window do
  modelo.
- **Arquivo, não eliminação.** Transcripts e decisões arquivadas
  permanecem no Vault; o arquivo de um projeto é reversível.

## 2.2 Ferramentas previstas

Nomes implementados no namespace `memory.*`:

| tool | quem a chama | o que faz |
|---|---|---|
| `memory.create_skill` | LLM | cria uma memória semântica **candidata** |
| `memory.list_skills` | LLM | lista as memórias disponíveis |
| `memory.get_context` | LLM | recupera turnos de chat passados |

Assinaturas implementadas:

```text
memory.create_skill(title, content, kind="procedure", tags=None)
    -> {id, title, kind, status, tags, created_at, source_*, path, duplicate}

memory.list_skills(kind=None, status=None, limit=20)
    -> [{id, title, kind, status, tags, created_at, source_*}]

memory.get_context(limit=5, query=None, session=None)
    -> [{session, turn, timestamp, question, answer}]
```

Comportamentos:

- `create_skill`: slug a partir do título, deduplicação por slug, limite de
  comprimento (`max_skill_chars`), frontmatter com `status: candidate`,
  `source_session`, `source_turn`, `model`, `created_at`; se já existir
  um slug igual devolve o id existente em vez de duplicar.
- `list_skills`: lê frontmatter e corpo (serve ao recall), filtrável
  por `kind` (`fact` / `procedure`) e `status`.
- `get_context`: sem `session` procura em todas as sessões; com `query`
  procura por palavras-chave nos turnos passados; `limit` é limitado a
  1..50 para não despejar todo o Vault no contexto.

## 2.3 Estrutura no Vault

```text
<Vault>/Hagar/
  chat/2026-11-03-<session>.md      # uma nota por sessão, turnos em append
  skills/<slug>.md                  # uma nota por memória
```

Episódica (uma nota por sessão, turnos acrescentados no fim):

```markdown
---
session: a1b2c3d4
type: chat
created: 2026-11-03T00:12:44+01:00
---

# Chat 2026-11-03

## 2026-11-03T00:12:44+01:00 · 7f3a

**Utilizador:** ...
**Hagar:** ...
```

Semântica (uma nota por skill):

```markdown
---
id: usa-uv-per-python
title: Usar uv para os projetos Python
kind: procedure
status: candidate
tags: [python, tooling]
source_session: a1b2c3d4
source_turn: 7f3a
model: llama3.1:latest
created_at: 2026-11-03T00:15:02+01:00
---

Passos / conteúdo proposto pelo modelo.
```

## 2.4 Configuração

```yaml
vault:
  path: <caminho real>

memory:
  enabled: true
  vault_subdir: Hagar
  context_turns: 10
  context_skills: 3
  max_skill_chars: 4000
```

## 2.5 Comportamento do harness

- No fim do turno: acrescenta pergunta e resposta à nota de sessão (apenas
  conversa, **não** output das ferramentas: esses ficam na auditoria).
- No início do turno: injeta os últimos `context_turns` turnos e até
  `context_skills` skills **confirmadas** pertinentes (match lexical),
  sem esperar que o modelo chame `get_context`.
- Cada escrita ou revisão de memória produz um evento de auditoria
  (`memory.enabled`, `memory.disabled`, `memory.context`, `memory.turn`,
  `memory.review`, `memory.status`, `memory.failed`); um Vault ausente ou
  não escrevível não para o harness.
- A memória episódica é separada da auditoria: a auditoria permanece forense e
  contém também os dados das ferramentas.

## 2.6 Pontos abertos

- **Retention chat**: quantas sessões conservar, se resumir as
  antigas; a 0.2.0 não apaga nada.
- **Pesquisa**: índice (SQLite FTS) ou embedding quando os volumes
  crescerem; hoje é por palavra-chave.
- **GUI**: confirmação ASK com diálogo modal também para as escritas de
  memória e para a review.
- **Seleção do contexto**: hoje turnos recentes globais, índice do
  projeto e top 3 skills confirmadas por match lexical, sem
  relevância semântica.
- **Consolidação de decisões**: o projeto pode ultrapassar
  `project_max_active`; hoje o Hagar propõe o arquivo, não o
  merge das decisões duplicadas.

## 2.7 Não objetivos (para já)

- escrita de memórias no filesystem real;
- modificação de notas existentes do utilizador;
- embedding / ChromaDB / pesquisa semântica (depois, se os volumes o
  justificarem);
- escrita autónoma de memórias fora do fluxo explícito.

---

# 3. Prioridade 2 — Chamada nativa (v1, feita)

**Estado:** implementado em 2026-11-03. `native_step()` para os quatro
providers, esquema dos parâmetros de `ToolDefinition`, mensagens canónicas
`tool`, várias chamadas por turno, fallback automático em HTTP 400/404/422
e `--no-native-tools`. Verificado live em Ollama e DeepSeek; Claude e
Gemini faltam testar. Medido com `tools/bench_native.py`: nenhum
protocolo vence em todos os modelos (nativo mais rápido, texto por vezes mais
preciso). Falta afinar para os modelos locais que ignoram as ferramentas.

## 3.1 Objetivo

Eliminar a fragilidade do protocolo JSON textual: fim das
reparações, argumentos validados pelo esquema do provider, resultados
estruturados.

## 3.2 Abordagem

- Manter o protocolo textual como **fallback** para os modelos que
  não suportam a chamada nativa ou que o fazem mal.
- Acrescentar ao `LLMClient` uma capacidade declarada
  (`supports_native_tools`) e um percurso nativo.
- O `Agent` tem de gerir ambos: `ToolCall` textual ou chamada
  nativa com id; o resultado volta no formato esperado pelo provider.
- O benchmark mede a melhoria (reparações por turno,
  correção dos argumentos).

## 3.3 Transporte por provider

| provider | pedido | resultado da ferramenta |
|---|---|---|
| `ollama` | `tools` em `/api/chat` | mensagem com papel `tool` |
| `deepseek` | `tools` (OpenAI) | papel `tool` + `tool_call_id` |
| `claude` | `tools` + blocos `tool_use` | bloco `tool_result` |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 3.4 Riscos

- Os modelos locais pequenos muitas vezes não usam bem a chamada nativa:
  é necessário o fallback automático.
- Muda o plumbing das mensagens: testes por provider e para o percurso de
  fallback são obrigatórios.
- Alguns modelos devolvem várias chamadas no mesmo turno: o Agent
  executa-as todas, dentro do limite do turno.

---

# 4. Prioridade 3 — PermissionEvaluator

## 4.1 Estado: v1 implementada

Realizado:

- `Capability`, `Effect`, `Rule`, `Subject`, `Resource`, `Decision` e
  `PermissionEvaluator` em `core/permissions.py`;
- `policy.yaml` lido **antes** do LLM, com fallback a `DENY` total e
  warning na auditoria e no chat;
- teto de sistema derivado de `permissions.read/write/shell`;
- scope para `tools` (glob), `paths` e `namespaces` (prefixos);
- `ASK` com `ConsoleConfirmation` (`lo faccio? (y/N)`, default N);
- aplicação em `ToolRegistry.execute` e auditoria de
  `permission.decision` / `permission.confirmation`;
- `ToolDefinition.capabilities` para todas as ferramentas (filesystem e MCP);
- `requires_confirmation` aplicado como piso de ASK;
- 347 testes recolhidos, 1 skip.

## 4.2 Faltam fazer

- `ConfirmationProvider` para a GUI (diálogo modal) e para a execução
  não interativa (deny por predefinição);
- políticas dinâmicas por tarefa/papel, com apenas redução em runtime (um
  agente pode reduzir as suas permissões, nunca alargá-las sozinho);
- capability das ferramentas MCP atribuídas pela configuração, não
  declaradas pelo servidor;
- mais sujeitos em execução simultânea (mais agentes com políticas
  diferentes);
- objetos-recurso para memória e percursos, não apenas ferramentas.

---

# 5. Prioridade 4 — AIsh

Shell dedicada aos LLM, concetualmente semelhante a Bash mas sem qualquer
acesso à shell real:

- nenhuma execução de comandos host;
- utilização exclusiva de ferramentas registadas;
- filesystem simulado e percursos virtuais (`workspace://`);
- integração com ferramentas MCP;
- pipes e comandos virtuais.

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```

Os percursos virtuais resolveriam também a exposição dos percursos
absolutos da sandbox.

---

# 6. Higiene e robustez

Feita (2026-11-03):

- **MCP**: respostas `text/event-stream`, notificação
  `notifications/initialized`, normalização dos resultados em texto
  (blocos `text`, `structuredContent`, erros `isError`).
- **MCP auth**: bearer ou header personalizado, token apenas do ambiente,
  servidor ignorado com `mcp.failed` se o token faltar.
- **MCP OAuth**: fluxo authorization code + PKCE com browser, discovery
  RFC 9728/8414, dynamic registration, cache de token, refresh e retry 401.
- **Auditoria**: rotação em `max_bytes`, cadeia de hash verificável com
  `verify_chain`, redação do output das ferramentas com
  `include_outputs: false`.
- **Audit retention**: backups com timestamp e `audit.max_files` (predefinição
  100, inclui o ficheiro ativo) com pruning dos mais antigos.
- **Testes live**: marker `live`, excluídos por predefinição, `--live` para Ollama
  e providers remotos (estes últimos skipped sem chave).
- **Packaging**: metadados completos, entry point `hagar`, `--config`,
  `--model`, `--no-memory`, `--version`, versão única.
- **URL base**: `model.host` vale para todos os providers.
- **Legacy**: removidos `tools/filesystem.py` e `llm/tool_result.py`.

Faltam:

- device flow / DPoP para MCP OAuth;
- compactação das sessões de auditoria;
- confirmações GUI para `ASK`;
- alinhamento contínuo da documentação.

---

# 7. Mais à frente

- pesquisa semântica no Vault (índice, depois eventualmente ChromaDB);
- RAG sobre os documentos;
- gestão de atividades e scratchpad persistente;
- observação do vault (notas modificadas pelo utilizador);
- agente pessoal permanente;
- providers adicionais (OpenAI é quase gratuito: mesmo cliente do DeepSeek
  com um base URL diferente).

---

# 8. Ordem de trabalho

1. Memória v2: feita (ciclo de vida, review CLI, injeção de confirmadas);
   faltam retention de chat, pesquisa semântica e GUI.
2. PermissionEvaluator: v1 feita; faltam confirmações GUI e políticas
   dinâmicas.
3. Higiene: feita (packaging, testes live, MCP auth/OAuth, auditoria com
   retention, base URL, legacy).
4. Chamada nativa: v1 feita; falta a medição com o benchmark.
5. Release 0.3.0: preparada para GitHub, com CI multiplataforma e
   workflow de release.

---

# 9. Ferramentas locais

Estado a 2026-11-05:

- filesystem v2: `list_dir`, `read_chunk`, `rename`, `copy_file`,
  `search`, além das ferramentas existentes;
- `local_tools/`: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `feed.read` (providers locais, não servidores MCP);
- capability `COMPUTE` sempre no teto, `NETWORK` controlada por
  `permissions.network` e pela política (feed em `ask`);
- limites de escrita: `max_write_bytes`, `min_free_bytes`,
  `session_write_bytes` e `ask_over_bytes` com preflight único;
- `feed.read` com política SSRF: apenas endereços globais, redirect
  revalidados, nada de credenciais no URL;
- filesystem com raiz virtual `/home/ai`, alias obrigatórios e
  permissões por mount (`R`/`W`/`X`);
- runner POSIX `tools/run_tests.sh` ao lado do do Windows.

Pontos abertos:

- DNS rebinding: a resolução é validada, mas `requests` resolve
  de novo o nome no momento da ligação; é necessário um resolver
  fixado (pinned) ou um adapter dedicado para fechar o caso;
- a calculadora é voluntariamente limitada (nada de álgebra simbólica);
- avaliar um limite de dimensão também para os outros outputs das ferramentas.

Fechado como responsabilidade do utilizador:

- hard link, mount e junction dentro das diretorias allowed não são
  controlados pelo Hagar. Para isolamento total o utilizador tem de garantir
  que não existem; o Hagar não os cria e não os deteta;
- race TOCTOU: o Hagar não usa `openat2`, `O_NOFOLLOW` em cada componente ou
  handle Windows e não garante atomicidade entre check e operação. A
  race exige um processo local concorrente com acesso em escrita;
  é um cenário malicioso ou de ambiente comprometido, não uso normal.
  Para isolamento total são necessários volume dedicado, utilizador separado, mount
  namespace ou container.
