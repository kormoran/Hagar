# HAGAR — Roadmap

Versão corrente: 0.7.0 (em desenvolvimento)
Última atualização: 2026-11-09

As decisões tomadas são indicadas como tal; os pontos ainda em aberto são
elencados no fim de cada área. As secções 1–9 são o histórico até
à 0.6.0; o plano operativo corrente é a secção 0.

---

# 0. Plano corrente (post-0.6.0)

## 0.1 Ordem das próximas releases

| Release | Objetivo | Estado |
|---|---|---|
| **0.6.0** | Runtime safety + AIsh | lançada |
| **0.7.0** | dev.run + box + Hagar Flow | em desenvolvimento |
| **0.8.0** | Broker LLM | próximo |
| **0.9.0** | Ferramenta SQL read-only | congelado |

A ordem pode mudar, mas a restrição é: **nada de subagentes sem usage e
limites; nada de broker sem subagentes e model registry.**

## 0.1.1 0.7.0 — Orquestração local

- `dev.run` com receitas fidedignas fora da sandbox;
- `box.list` e `box.run` para transformações LLM bounded;
- `flow.run`, `flow.validate` e `flow.reference`;
- list comprehension com um único `for`;
- primitivas de memória read-only: `memory.search`, `memory.context`,
  `memory.skill` e `project.context`;
- repair explícito com `flow.repair`;
- nada de container mode nesta release.

## 0.2 0.8.0 — Broker LLM

- fichas técnicas JSON e benchmarks dos modelos (`/models test`);
- deteção de hardware CPU/RAM/GPU (`/models hardware`);
- `ModelRegistry` com context window, tool calling, preços, latência e
  localidade;
- `TaskProfile` com ferramentas exigidas, sensibilidade dos dados, budget e contexto;
- routing por regras/pontuação, não "um LLM escolhe o modelo";
- proposta de `AgentSpec` validada pelo host;
- o broker nunca concede permissões: só pode propor um subconjunto;
- override humano e auditoria `broker.decision`.

## 0.3 0.8.0 — Ferramenta SQL

- apenas leitura na primeira versão;
- SQLite `mode=ro`, `PRAGMA query_only`, uma única instrução;
- nada de `ATTACH`, `PRAGMA` de escrita ou `load_extension`;
- timeout, limite de linhas/bytes e auditoria da query;
- alias de base de dados configurados, nunca paths arbitrários;
- capability `DATABASE_READ`;
- escrita e base de dados de rede apenas numa fase posterior, com
  `DATABASE_WRITE` e `NETWORK`.

## 0.4 Pontos em aberto

- workflow de release idempotente se a release já existir;
- PyPI: adiado;
- MCP OAuth Atlassian: Basic funciona, o fluxo OAuth falta validar;
- testes live MCP/OAuth e providers remotos;
- manutenção das traduções: regeneram-se apenas na release, não a
  cada commit;
- document tool: contrato e protocolo definidos em `DOCUMENT_TOOL.md`;
  MVP CSV ainda por implementar.

## 0.4.1 Versão completa filesystem — congelada

Implementado agora:

- `edit_file` com escrita atómica;
- checkpoint do turno e `/undo`;
- timeout por ferramenta e repeat guard;
- output spill e compaction do contexto.

O MVP implementado cobre `edit_file`, escrita atómica,
read-before-overwrite/delete/rename e versão `mtime_ns+size`.
A versão completa está congelada; não entra na próxima release:

- `edit_file` com patch de vários hunks e diff;
- hash do conteúdo além de `mtime_ns`/`size`;
- escrita atómica com controlo CAS ao nível do filesystem;
- observação por agente individual com isolamento explícito entre pai e
  subagentes;
- auditoria `fs.observed`, `fs.guard_denied`, `fs.stale`;
- cobertura de rename/delete de diretorias;
- integração GUI e mensagens de recuperação guiada.

## 0.4.2 AIsh — implementada na 0.6.0

`aish.exec` é uma shell semântica sobre as ferramentas Hagar, com política
`DENY` predefinida. Comandos implementados: navegação, leitura, texto puro,
pipeline e mutações de ficheiros individuais. Não executa programas host,
redirecionamentos, variáveis ou command substitution.
`text.transform` fornece as operações textuais bounded usadas pela AIsh.

## 0.4.3 dev.run — implementado

`dev.list` e `dev.run` executam receitas fidedignas para testes, debug e build.
O `recipes.yaml` está fora da sandbox, é lido no arranque e não tem
hot reload. `DEV_EXEC` é DENY por predefinição; o backend é apenas host.

O container continua congelado para um futuro acesso direto a
filesystem/programas reais, nunca dentro da sandbox.

## 0.4.4 Boxed transform — implementadas

`box.list` e `box.run` executam `summarize`, `translate` e
`extract_json` com prompt fixo, input/output em ficheiro e nenhuma memória
ou ferramenta. `BOX_EXEC` é DENY por predefinição.

São as primitivas do futuro DSL.

## 0.4.5 Hagar Flow — MVP

`flow.run` executa um subconjunto linear de Python com validador AST e
interpretador Hagar, sem `eval`/`exec`. Primitivas `fs.*` e `box.*`, limites
de step e tool call. `FLOW_EXEC` é DENY por predefinição.

HIR, paralelismo e subagentes ficam fora do MVP.

## 0.5 Documentação

`Docs/it` é a única fonte mantida durante o desenvolvimento. As diretorias
`Docs/en`, `Docs/es`, `Docs/zh`, `Docs/ru`, `Docs/pt` e `Docs/ar` são
regeneradas apenas quando se prepara uma release.

---

## 1.0 Estado: v2 implementada (2026-11-04)

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

## 1.1 Decisões tomadas

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

## 1.2 Ferramentas previstas

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

## 1.3 Estrutura no Vault

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

## 1.4 Configuração

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

## 1.5 Comportamento do harness

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

## 1.6 Pontos em aberto

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

## 1.7 Não objetivos (para já)

- escrita de memórias no filesystem real;
- modificação de notas existentes do utilizador;
- embedding / ChromaDB / pesquisa semântica (depois, se os volumes o
  justificarem);
- escrita autónoma de memórias fora do fluxo explícito.

---

## 2 Objetivo

Eliminar a fragilidade do protocolo JSON textual: fim das reparações,
argumentos validados pelo esquema do provider, resultados estruturados.

## 2.1 Abordagem

- Manter o protocolo textual como **fallback** para os modelos que
  não suportam a chamada nativa ou que o fazem mal.
- Acrescentar ao `LLMClient` uma capacidade declarada
  (`supports_native_tools`) e um percurso nativo.
- O `Agent` tem de gerir ambos: `ToolCall` textual ou chamada
  nativa com id; o resultado volta no formato esperado pelo provider.
- O benchmark mede a melhoria (reparações por turno,
  correção dos argumentos).

## 2.2 Transporte por provider

| provider | pedido | resultado da ferramenta |
|---|---|---|
| `ollama` | `tools` em `/api/chat` | mensagem com papel `tool` |
| `deepseek` | `tools` (OpenAI) | papel `tool` + `tool_call_id` |
| `claude` | `tools` + blocos `tool_use` | bloco `tool_result` |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 2.3 Riscos

- Os modelos locais pequenos muitas vezes não usam bem a chamada nativa:
  é necessário o fallback automático.
- Muda o plumbing das mensagens: testes por provider e para o percurso de
  fallback são obrigatórios.
- Alguns modelos devolvem várias chamadas no mesmo turno: o Agent
  executa-as todas, dentro do limite do turno.

---

# 3. Prioridade 3 — PermissionEvaluator

Estado: v1 implementada

## 3.1 Restam por fazer

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
- **URL base**: `model.host` vale para todos os providers.

Faltam:

- device flow / DPoP para MCP OAuth;
- compactação das sessões de auditoria;
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

Pontos em aberto:

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
