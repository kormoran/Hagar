# HAGAR — Roadmap

Versão corrente: 0.2.0 (em desenvolvimento)
Última atualização: 2026-11-03

As decisões tomadas são indicadas como tal; os pontos ainda em aberto são
listados no fim de cada área.

---

# 1. Direção

O Hagar passou de "ideia" a "sistema funcional" (v0.1) e depois a um
harness com auditoria, backends múltiplos e suite de testes (v0.2 em
curso). O próximo salto não é acrescentar ferramentas: é dar ao sistema
uma **memória** e uma forma de chamar as ferramentas menos frágil do que o
JSON textual.

Ordem decidida:

1. memória no Vault;
2. chamada nativa para os providers que a suportam;
3. PermissionEvaluator — **v1 feita** (policy.yaml, ASK, auditoria);
4. higiene (auditoria, MCP, empacotamento, testes live).

---

# 2. Prioridade 1 — Memória no Vault

## 2.0 Estado: v2 implementada (2026-11-04)

Realizado:

- episódica escrita pelo harness, uma nota por sessão;
- injeção automática dos últimos `context_turns` turnos;
- ferramentas `memory.create_skill`, `memory.list_skills`,
  `memory.get_context`;
- proveniência (`source_session`, `source_turn`, `model`), estado
  `candidate`, deduplicação por slug;
- política `MEMORY_READ`/`MEMORY_WRITE` e namespace `chat` / `skills`;
- vault ausente → memória desativada com aviso, harness ativo;
- ciclo de vida `candidate` → `confirmed` → `archived` com revisão humana
  a partir da CLI (`/memory review`, `confirm`, `archive`);
- injeção automática apenas das skills confirmadas, top 3 por
  correspondência lexical;
- retenção opção A: nenhuma eliminação automática, apenas arquivo;
- memória de projeto separada das skills: decisões, alternativas,
  motivações, estado e proveniência;
- seleção de projeto no arranque, `--project`/`--free`, comandos
  `/project`;
- resumo de fim de sessão com fallback, transcript em `archive/chat/` e
  link/hash no resumo;
- revisão das decisões no fim da sessão; se recusada, permanecem
  `candidate` com `auto_saved: true`;
- contexto por índice com orçamento `max_context_chars` (caracteres, não
  tokens) e `memory.project_context` para os detalhes;
- `project_max_active` para o pedido de arquivamento do projeto;
- consulta do arquivo com `memory.archive_search`,
  `memory.archive_read`, `/memory archive search|read`, filtro por
  projeto e transcript com `project` no frontmatter.

Faltam: retenção dos chats, pesquisa semântica, GUI.

## 2.1 Decisões tomadas

- **Episódica escrita pelo harness.** Os turnos de chat são registados
  pelo harness por predefinição: é uma ata mecânica, não um juízo do
  modelo. Nenhum turno em falta, nenhuma memória inventada.
- **Semântica escrita pelo LLM, a pedido.** O modelo pode propor uma
  memória (skill) apenas através de uma ferramenta dedicada. A proposta é
  explícita, atribuível e revísivel — a Primeira Lei proíbe tratá-la como
  verdade.
- **Apenas Vault Obsidian.** Nenhuma escrita no filesystem real para a
  memória (por agora). A `filesystem.sandbox` continua a ser a sandbox
  operativa.
- **O Vault não se reescreve.** As ferramentas acrescentam notas ou
  secções; não substituem notas cuidadas pelo utilizador.
- **Projetos explícitos.** O projeto escolhe-se no arranque a partir da
  lista dos projetos ativos, ou com `--project`; `--free` e "atividade
  livre" não têm memória de projeto.
- **Decisões de projeto.** Estão separadas das skills: registam decisões,
  alternativas e motivações. Propõem-se como `candidate` e revêem-se no
  fim da sessão; se a revisão for recusada permanecem candidatas com
  `auto_saved: true`, não se tornam verdades automáticas.
- **Nada de quotas de tokens.** O contexto é limitado por construção:
  índice do projeto, títulos das decisões, resumo e `max_context_chars` em
  caracteres. Não se mede a context window do modelo.
- **Arquivo, não eliminação.** Transcripts e decisões arquivadas
  permanecem no Vault; o arquivamento de um projeto é reversível.

## 2.2 Ferramentas previstas

Nomes implementados no namespace `memory.*`:

| ferramenta | quem a chama | o que faz |
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

- `create_skill`: slug a partir do título, deduplicação por slug, limite
  de comprimento (`max_skill_chars`), frontmatter com `status: candidate`,
  `source_session`, `source_turn`, `model`, `created_at`; se já existir um
  slug igual devolve o id existente em vez de duplicar.
- `list_skills`: lê frontmatter e corpo (serve ao recall), filtrável por
  `kind` (`fact` / `procedure`) e `status`.
- `get_context`: sem `session` pesquisa em todas as sessões; com `query`
  pesquisa por palavras-chave nos turnos passados; `limit` é limitado a
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
  conversa, **não** saída das ferramentas: essas ficam na auditoria).
- No início do turno: injeta os últimos `context_turns` turnos e até
  `context_skills` skills **confirmadas** pertinentes (correspondência
  lexical), sem esperar que o modelo chame `get_context`.
- Cada escrita ou revisão de memória produz um evento de auditoria
  (`memory.enabled`, `memory.disabled`, `memory.context`, `memory.turn`,
  `memory.review`, `memory.status`, `memory.failed`); um Vault ausente ou
  não escrevível não para o harness.
- A memória episódica está separada da auditoria: a auditoria permanece
  forense e contém também os dados das ferramentas.

## 2.6 Pontos em aberto

- **Retenção de chat**: quantas sessões conservar, se resumir as antigas;
  a 0.2.0 não apaga nada.
- **Pesquisa**: índice (SQLite FTS) ou embedding quando os volumes
  crescerem; hoje é por palavra-chave.
- **GUI**: confirmação ASK com caixa de diálogo modal também para as
  escritas de memória e para a revisão.
- **Seleção do contexto**: hoje turnos recentes globais, índice do
  projeto e top 3 skills confirmadas por correspondência lexical, sem
  relevância semântica.
- **Consolidação de decisões**: o projeto pode exceder
  `project_max_active`; hoje o Hagar propõe o arquivamento, não a fusão
  das decisões duplicadas.

## 2.7 Não objetivos (por agora)

- escrita de memórias no filesystem real;
- modificação de notas existentes do utilizador;
- embedding / ChromaDB / pesquisa semântica (depois, se os volumes o
  justificarem);
- escrita autónoma de memórias fora do fluxo explícito.

---

# 3. Prioridade 2 — Chamada nativa (v1, feita)

**Estado:** implementado em 2026-11-03. `native_step()` para os quatro
providers, esquema dos parâmetros a partir de `ToolDefinition`, mensagens
canónicas `tool`, várias chamadas por turno, fallback automático em HTTP
400/404/422 e `--no-native-tools`. Verificado live no Ollama e no
DeepSeek; Claude e Gemini continuam por testar. Medido com
`tools/bench_native.py`: nenhum protocolo vence em todos os modelos
(nativo mais rápido, texto por vezes mais preciso). Continua por afinar
para os modelos locais que ignoram as ferramentas.

## 3.1 Objetivo

Eliminar a fragilidade do protocolo JSON textual: chega de reparações,
argumentos validados pelo esquema do provider, resultados estruturados.

## 3.2 Abordagem

- Manter o protocolo textual como **fallback** para os modelos que não
  suportam a chamada nativa ou que a fazem mal.
- Acrescentar ao `LLMClient` uma capacidade declarada
  (`supports_native_tools`) e um percurso nativo.
- O `Agent` tem de gerir ambos: `ToolCall` textual ou chamada nativa com
  id; o resultado volta no formato esperado pelo provider.
- O benchmark mede a melhoria (reparações por turno, correção dos
  argumentos).

## 3.3 Transporte por provider

| provider | pedido | resultado da ferramenta |
|---|---|---|
| `ollama` | `tools` em `/api/chat` | mensagem com papel `tool` |
| `deepseek` | `tools` (OpenAI) | papel `tool` + `tool_call_id` |
| `claude` | `tools` + blocos `tool_use` | bloco `tool_result` |
| `gemini` | `tools.functionDeclarations` | `functionResponse` |

## 3.4 Riscos

- Os modelos locais pequenos muitas vezes não usam bem a chamada nativa: é
  necessário o fallback automático.
- Muda o plumbing das mensagens: testes por provider e para o percurso de
  fallback são obrigatórios.
- Alguns modelos devolvem várias chamadas no mesmo turno: o Agent executa-
  as todas, no limite do turno.

---

# 4. Prioridade 3 — PermissionEvaluator

## 4.1 Estado: v1 implementada

Realizado:

- `Capability`, `Effect`, `Rule`, `Subject`, `Resource`, `Decision` e
  `PermissionEvaluator` em `core/permissions.py`;
- `policy.yaml` lido **antes** do LLM, com fallback a `DENY` total e
  aviso na auditoria e no chat;
- teto do sistema derivado de `permissions.read/write/shell`;
- scope por `tools` (glob), `paths` e `namespaces` (prefixos);
- `ASK` com `ConsoleConfirmation` (`lo faccio? (y/N)`, predefinição N);
- aplicação em `ToolRegistry.execute` e auditoria de
  `permission.decision` / `permission.confirmation`;
- `ToolDefinition.capabilities` para todas as ferramentas (filesystem e
  MCP);
- `requires_confirmation` aplicado como piso de ASK;
- 347 testes recolhidos, 1 ignorado.

## 4.2 Fica por fazer

- `ConfirmationProvider` para a GUI (caixa de diálogo modal) e para a
  execução não interativa (deny por predefinição);
- políticas dinâmicas por tarefa/papel, com apenas redução em runtime (um
  agente pode reduzir as suas permissões, nunca alargá-las sozinho);
- capabilities das ferramentas MCP atribuídas pela configuração, não
  declaradas pelo servidor;
- vários sujeitos em execução simultânea (vários agentes com políticas
  diferentes);
- objetos-recurso para memória e caminhos, não apenas ferramentas.

---

# 5. Prioridade 4 — AIsh

Shell dedicada aos LLM, conceptualmente semelhante ao Bash mas sem
qualquer acesso à shell real:

- nenhuma execução de comandos anfitriões;
- utilização exclusiva de ferramentas registadas;
- filesystem simulado e caminhos virtuais (`workspace://`);
- integração com ferramentas MCP;
- pipes e comandos virtuais.

```text
ls workspace://
cat workspace://project/readme.md
find *.py
```

Os caminhos virtuais resolveriam também a exposição dos caminhos
absolutos da sandbox.

---

# 6. Higiene e robustez

Feito (2026-11-03):

- **MCP**: respostas `text/event-stream`, notificação
  `notifications/initialized`, normalização dos resultados em texto
  (blocos `text`, `structuredContent`, erros `isError`).
- **Autenticação MCP**: bearer ou header personalizado, token apenas do
  ambiente, servidor ignorado com `mcp.failed` se o token faltar.
- **MCP OAuth**: fluxo authorization code + PKCE com browser, discovery
  RFC 9728/8414, registo dinâmico, cache de token, refresh e retry 401.
- **Auditoria**: rotação em `max_bytes`, cadeia de hash verificável com
  `verify_chain`, mascaramento da saída das ferramentas com
  `include_outputs: false`.
- **Retenção da auditoria**: cópias com timestamp e `audit.max_files`
  (predefinição 100, inclui o ficheiro ativo) com poda das mais antigas.
- **Testes live**: marker `live`, excluídos por predefinição, `--live`
  para Ollama e providers remotos (estes últimos ignorados sem chave).
- **Empacotamento**: metadados completos, entry point `hagar`,
  `--config`, `--model`, `--no-memory`, `--version`, versão única.
- **URL base**: `model.host` vale para todos os providers.
- **Legacy**: removidos `tools/filesystem.py` e `llm/tool_result.py`.

Faltam:

- device flow / DPoP para MCP OAuth;
- compactação das sessões de auditoria;
- confirmações GUI para `ASK`;
- alinhamento contínuo da documentação.

---

# 7. Mais adiante

- pesquisa semântica no Vault (índice, depois eventualmente ChromaDB);
- RAG sobre os documentos;
- gestão de atividades e scratchpad persistente;
- observação do vault (notas modificadas pelo utilizador);
- agente pessoal permanente;
- providers adicionais (a OpenAI é quase gratuita: o mesmo cliente do
  DeepSeek com um base URL diferente).

---

# 8. Ordem de trabalho

1. Memória v2: feita (ciclo de vida, revisão por CLI, injeção das
   confirmadas); faltam retenção de chat, pesquisa semântica e GUI.
2. PermissionEvaluator: v1 feita; faltam confirmações GUI e políticas
   dinâmicas.
3. Higiene: feita (empacotamento, testes live, autenticação MCP/OAuth,
   auditoria com retenção, base URL, legacy).
4. Chamada nativa: v1 feita; falta a medição com o benchmark.
5. Release 0.3.0: preparada para o GitHub, com CI multiplataforma e
   workflow de release.

---

# 9. Ferramentas locais

Estado em 2026-11-05:

- filesystem v2: `list_dir`, `read_chunk`, `rename`, `copy_file`,
  `search`, além das ferramentas existentes;
- `local_tools/`: `calculator.evaluate`, `statistics.compute`,
  `units.convert`, `feed.read` (providers locais, não servidores MCP);
- capability `COMPUTE` sempre no teto, `NETWORK` controlada por
  `permissions.network` e pela política (feed em `ask`);
- limites de escrita: `max_write_bytes`, `min_free_bytes`,
  `session_write_bytes` e `ask_over_bytes` com preflight único;
- `feed.read` com política SSRF: apenas endereços globais,
  redirecionamentos revalidados, nada de credenciais no URL;
- filesystem com raiz virtual `/home/ai`, alias obrigatórios e permissões
  por mount (`R`/`W`/`X`);
- runner POSIX `tools/run_tests.sh` ao lado do runner Windows.

Pontos em aberto:

- DNS rebinding: a resolução é validada, mas `requests` resolve de novo o
  nome no momento da ligação; é necessário um resolver fixado ou um
  adapter dedicado para fechar o caso;
- o calculador é voluntariamente limitado (nada de álgebra simbólica);
- avaliar um limite de dimensão também para as outras saídas das
  ferramentas.

Fechado como responsabilidade do utilizador:

- hard links, mounts e junctions dentro dos diretórios allowed não são
  controlados pelo Hagar. Para isolamento total o utilizador tem de
  garantir que não existam; o Hagar não os cria nem os deteta;
- corrida TOCTOU: o Hagar não usa `openat2`, `O_NOFOLLOW` em cada
  componente ou handle Windows e não garante atomicidade entre
  verificação e operação. A corrida exige um processo local concorrente
  com acesso de escrita; é um cenário malicioso ou de ambiente
  comprometido, não uso normal. Para isolamento total são necessários
  volume dedicado, utilizador separado, mount namespace ou container.
