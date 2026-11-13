<p align="center">
  <img src="../HAGAR.jpg">
</p>

[Italiano](../it/README.md) · [English](../en/README.md) · [Español](../es/README.md) · [中文](../zh/README.md) · [Русский](../ru/README.md) · [Português](../pt/README.md) · [العربية](../ar/README.md)

# H.A.G.A.R.

Harness Agêntico Geral para IA Resiliente (General Resilient Agentic Harness for AIs)

# 0. Como tudo começou: a segurança

Criei o HAGAR porque nenhum outro harness para IA isolava os meus ficheiros por predefinição. Fosse DeepSeek, Claude Code, AutoGen ou outro, se deixados livres, acabam todos por expor o teu file system aos LLM. És TU que tens de impor limites e tens de o fazer bem, senão o problema é teu. Nenhuma destas ferramentas garante que os teus dados não sejam lidos com fins imprecisos, por erro ou por ambos os motivos. E se não for o próprio harness a fazê-lo, pode ser aquele plugin tão giro, aquela skill utilíssima ou qualquer outra adição que acabaste de instalar...

**O HAGAR inverte esta abordagem: és TU que estabeleces o que os LLM podem ver, escrever ou procurar, e onde.** Nenhum LLM pode ler ou escrever nada fora dos diretórios que indicaste explicitamente como legíveis ou escrevíveis no ficheiro de configuração. Se um diretório não está na secção `[filesystem]` da configuração, não existe: para os LLM, é como se não existisse.

Durante o desenvolvimento do HAGAR, surgiu-me outra pergunta: porque é que um LLM precisaria de interagir com o sistema operativo? No mundo da inteligência artificial, o verdadeiro estrangulamento de desempenho são as chamadas ao modelo, que podem demorar segundos (às vezes MUITOS segundos). O acesso direto ao sistema operativo permite poupar apenas alguns milissegundos: vale a pena correr o risco? A minha resposta é não.

Por este motivo, **o HAGAR faz o possível para isolar o LLM do sistema operativo.** Cada interação com ficheiros, memórias ou com a própria máquina acontece através de ferramentas específicas (baseadas no protocolo MCP ou integradas diretamente no HAGAR). A IA não sabe em que sistema operativo está a correr, e nunca o deveria saber: se houvesse uma forma de uma IA perceber o sistema operativo onde corre apesar do isolamento do HAGAR, considerá-lo-ei uma falha de segurança e tratarei de a corrigir (ou, pelo menos, de documentar o problema para informar os utilizadores).

|Harness	|Vê o FS anfitrião	|Vê o SO		|Isolamento	  |
|-----------|---------------|---------------|-------------|
|Claude Code|Parcial		|Sim	 		|Permissões	  |
|Codex CLI	|Parcial		|Sim	 		|Sandbox	  |
|OpenHands	|Não				|Sim	 		|Docker		  |
|E2B		|Não				|Sim				|VM/Container |
|`HAGAR`	|`No`			|`No`			|`FS virtual`|

**Os outros harness tentam dar um computador aos LLM: o HAGAR diz aos LLM que o computador não existe.**
As IA deveriam concentrar-se na gestão do conhecimento mais do que nos detalhes técnicos (ainda que sejam muito boas em ambos). Quanto mais um framework consegue automatizar, menor é o raciocínio (e o número de tokens) exigido. Assim, até os modelos mais pequenos podem exprimir todo o seu potencial.

Ou, dito de outra forma: para um LLM, o HAGAR é a realidade.

# 1. Visão do projeto

O HAGAR é um harness para LLM, desenvolvido em Python, concebido para a execução segura de modelos de linguagem.

O objetivo não é fornecer apenas uma interface de chat para um LLM, mas criar um ambiente operativo ***seguro e protegido*** no qual o LLM possa utilizar ferramentas, consultar uma memória persistente e interagir com sistemas externos — tudo sem ter acesso direto aos recursos reais da máquina anfitriã — prevenindo ou pelo menos mitigando os erros mais comuns.

Por isso adotei princípios e metodologias provenientes tanto da segurança informática (princípio do menor privilégio, tríade CIA) como do âmbito HMI/HCI (interação/interface homem-máquina, típica das máquinas industriais) e da ergonomia cognitiva, aplicando-os à conceção do ambiente em que o LLM opera: como se faz com o trabalho dos humanos, o propósito adicional do HAGAR é criar um ambiente para LLM onde fazer bem é fácil e errar é difícil.

Com base no que foi exposto e com o objetivo de estabelecer uma regra de conduta geral para todo o desenvolvimento futuro deste software, enuncio aqui **as Quatro Leis de HAGAR**:

## 1.1 Primeira Lei de HAGAR
**Um LLM é, por definição, não fiável.** Tal não significa que seja malévolo ou inútil, mas que o seu funcionamento é de natureza probabilística. Consequentemente, cada uma das suas afirmações tem de ser verificada e cada uma das suas ações tem de estar sujeita a restrições.

## 1.2 Segunda Lei de HAGAR
**As ferramentas são mais fiáveis do que o LLM.** Se o file system indica que um ficheiro existe, então existe mesmo. Se uma ferramenta devolve a dimensão de um ficheiro, essa dimensão é real. O LLM interpreta, mas as ferramentas medem.

## 1.3 Terceira Lei de HAGAR
**O estado tem de existir fora da "mente" do LLM.** Implementando componentes como `ToolRegistry`, `MCP`, `FilesystemSandbox`, `Memory` e `PermissionEvaluator`, transferimos o conhecimento e o controlo para fora do próprio modelo. Isto está em linha com as práticas padrão para os sistemas em que a segurança é um requisito crítico.

## 1.4 Quarta Lei de HAGAR
**Cada ação tem de ser explicável a posteriori.** Por este motivo o HAGAR implementa um *log de auditoria*: quando algo corre mal — e mais cedo ou mais tarde acontecerá — a pergunta não deve ser "Porque é que o LLM enlouqueceu?", mas "Que pressupostos adotou?", "Que ferramenta usou?", "Que dado estava errado?". Por outras palavras, tem de ser possível conduzir uma análise de incidentes, exatamente como na aviação. O HAGAR reconhece esta necessidade e dará sempre as ferramentas para a fazer.

## 1.5 Arquitetura de software

Do ponto de vista estrutural, o HAGAR assenta em cinco princípios fundamentais:

- separação entre o modelo e o sistema operativo;
- segurança por predefinição (*security by default*);
- arquitetura de plugins;
- independência de qualquer fornecedor específico de LLM;
- extensibilidade através de ferramentas (*tools*) e do MCP (Model Context Protocol).

---

# 2. Proibições absolutas

Ao modelo é absolutamente proibido:

- aceder diretamente ao file system do anfitrião;
- executar comandos numa verdadeira shell do SO;
- obter privilégios superiores aos definidos na configuração;
- conhecer o sistema operativo real.

Todas as operações devem ocorrer apenas através de ferramentas registadas e controladas pelo harness.

---

# 3. Desenvolvimento

## 3.0 Instalação e CLI

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

`pip install -e .` declara os pacotes `core`, `llm`, `memory` e
`local_tools` e instala o comando `hagar`:

```powershell
hagar --config hagar.yaml
hagar --model qwen3:8b
hagar --no-memory
hagar --no-native-tools
hagar --version

# GUI web local
hagar web
hagar --config hagar.yaml web --port 8765
```

A GUI web usa `http://127.0.0.1:8765/`, um token aleatório para as API,
confirmações ASK modais, paragem do turno, upload de imagens, separadores de chat,
histórico, tool output, auditoria, thinking e memórias, e tokens acumulados
da sessão na barra lateral. Para os detalhes, ver `MANUAL.md` §3.0.

A configuração é procurada pela ordem seguinte: parâmetro `--config`,
variável de ambiente `HAGAR_CONFIG` e, por fim, o ficheiro `./hagar.yaml`.
É também possível utilizar `python -m hagar` trabalhando diretamente sobre
o código-fonte.

## 3.1 Estrutura

```
hagar.py            Script de lançamento do harness
hagar.yaml          Script de configuração predefinido
policy.yaml			Configuração das permissões para as ferramentas (integradas e MCP)
core/               config, agent, audit log, registry, sandbox, service e web server
llm/                LLM backends (Ollama, LM Studio, DeepSeek, OpenAI, Claude, Gemini), cliente MCP
memory/             memória SQLite (sqlite_store.py) e backend markdown legacy
web/                HTML, CSS e JavaScript da GUI local
tests/              suite pytest
tools/              helpers de desenvolvimento (test runner, sandbox shim, model benchmark)
local_tools/        ferramentas integradas; as built-in passam por local_tools/plugins.py
core/plugins.py     contratos e descoberta dos plugins (hagar.tools, hagar.llm)
core/subagents.py   manager do subagente MVP síncrono e read-only
llm/plugins.py      provider LLM built-in registados como plugins
```

## 3.2 LLM backends

`model.provider` seleciona o backend. Os esquemas das ferramentas (tool), a conversão das mensagens e os percursos nativos ou de fallback são geridos em `llm/base.py`; por isso, mudar de provider não exige alterações à infraestrutura de execução (harness).

A chamada nativa de ferramentas é a predefinição para todos os backends. Se um modelo recusar esse modo (devolvendo um erro HTTP 400, 404 ou 422), o agente passa ao protocolo JSON textual para toda a sessão; é possível forçar o uso do protocolo textual definindo `model.native_tools: false` ou passando o argumento `--no-native-tools`.

| provider   | transporte                    | chave API             |
|------------|------------------------------|------------------------|
| `ollama`   | nativo `/api/chat`           | nenhuma                |
| `lmstudio` | OpenAI-compatível local      | nenhuma (opcional)    |
| `deepseek` | REST compatível com OpenAI  | `DEEPSEEK_API_KEY`     |
| `openai`   | OpenAI Chat Completions      | `OPENAI_API_KEY`       |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

`chatgpt` é um alias de `openai`. A subscrição ChatGPT não dá acesso à API: são necessárias uma chave OpenAI e crédito API. O LM Studio tem de ter o servidor local ativo e um modelo carregado; o endpoint predefinido é `http://localhost:1234/v1`. Se o servidor LM Studio exigir uma chave, pode definir-se `LMSTUDIO_API_KEY` ou `model.api_key_env`; caso contrário, não é necessária.

Com o LM Studio, a chamada nativa de ferramentas depende do modelo e do seu template: alguns modelos aceitam o pedido mas respondem em texto em vez de emitir `tool_calls`. Nesse caso, usar `model.native_tools: false` (protocolo JSON textual) ou um modelo tool-capable.

Os nomes dos modelos atualmente suportados para o DeepSeek são `deepseek-flash` (predefinição) e `deepseek-v4-pro`; o antigo `deepseek-chat` já não é aceite. O teste live usa `deepseek-flash`, a menos que seja substituído pela variável `HAGAR_LIVE_DEEPSEEK_MODEL`. O script `tools/diagnose_deepseek.py` permite verificar o DNS, o formato da chave e o endpoint, sem mostrar a própria chave.

As chaves são lidas apenas de variáveis de ambiente e nunca do ficheiro YAML. Se o nome predefinido da variável não servir às próprias necessidades, pode especificar-se outro com `model.api_key_env`. O parâmetro `model.host` indica o URL base do provider (com um valor predefinido específico para cada um; por exemplo, o Ollama usa `http://localhost:11434` e o LM Studio `http://localhost:1234/v1`), `model.timeout` é o timeout HTTP em segundos (predefinição 120) e `model.max_tokens` aplica-se apenas ao Claude (com um valor predefinido de 1024).

```yaml
model:
provider: gemini
name: gemini-2.0-flash
```

Cada backend normaliza o diálogo segundo o próprio formato: o Claude recebe as mensagens de sistema no campo dedicado `system` e os turnos alternados, enquanto o Gemini recebe `systemInstruction` e o papel `model`. O protocolo partilhado entre o agente e o cliente utiliza exclusivamente os papéis `user` e `assistant`.

## 3.3 Log de auditoria

Cada sessão acrescenta entradas em formato JSON Lines no caminho especificado em `audit.path` (valor predefinido: `logs/audit.jsonl`, resolvido relativamente ao ficheiro de configuração):

```yaml
audit:
enabled: true
path: logs/audit.jsonl
max_field_chars: 2000
```

Eventos registados: `harness.start`, `turn.start`, `llm.tool_choice`, `llm.protocol_error`, `llm.repaired`, `llm.repair_failed`, `tool.call`, `tool.result`, `turn.answer`, `turn.error`, `turn.stop`, `mcp.loaded`, `mcp.failed`, `llm.failed`, `harness.stop`. A ausência de um evento `harness.stop` na última sessão indica que o processo foi terminado à força ou sofreu um crash.

Cada registo inclui um timestamp UTC, o ID da sessão e, quando pertinente, um ID do turno partilhado por todos os eventos relativos a um único pedido. O truncamento dos dados é regulado pelo parâmetro `audit.max_field_chars`; as chaves API nunca são escritas no log.

O log foi concebido para ser consultado na sequência de um incidente, não para ser lido pelo modelo. Como pode conter o conteúdo de ficheiros lidos através das ferramentas de acesso ao file system, tem de ser tratado com a mesma cautela reservada à própria área de trabalho (workspace).

## 3.4 Autorizações e `policy.yaml`

Cada chamada a uma ferramenta é autorizada antes da sua execução. Uma ferramenta declara as suas
**capability** (`FILESYSTEM_READ`, `FILESYSTEM_WRITE`,
`FILESYSTEM_CREATE`, `FILESYSTEM_DELETE`, `MEMORY_READ`,
`MEMORY_WRITE`, `MCP_CALL`, ...); um **sujeito** (o agente) define
regras que associam essas funcionalidades a `allow` (permitir), `ask` (perguntar) ou `deny` (negar),
eventualmente circunscritas com base no nome da ferramenta, no prefixo do caminho ou no espaço de nomes.

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

A opção `ask` gera um pedido na consola do tipo `lo faccio? (y/N)` (com valor predefinido `N`); o protocolo `ConfirmationProvider` permite ainda implementar uma janela de diálogo modal numa interface gráfica (GUI).
O ficheiro das políticas é lido antes da criação do LLM: se estiver em falta ou
for inválido, todas as políticas são definidas como `DENY`, o erro é registado no log de auditoria (`policy.failed`) e mostrado no chat, enquanto o harness continua a funcionar.

## 3.5 Memória

A memória é uma base de dados SQLite local e representa a fonte de verdade:
sessões, turnos, skills e summaries. O modelo pode guardar memórias com
`memory.create_skill`, listá-las com `memory.list_skills` e consultar os
turnos anteriores com `memory.get_context`.

```yaml
memory:
  enabled: true
  backend: sqlite
  context_turns: 10
  max_skill_chars: 4000
```

A base de dados predefinida é `%LOCALAPPDATA%/Hagar/memory.db` (ou
`HAGAR_MEMORY_DB`). O backend `markdown` mantém-se apenas por compatibilidade.
As escritas passam pelo motor das políticas. Os comandos `/memory` da CLI
permitem inspecionar chats, skills e estatísticas.

## 3.6 Decision tool

`decision.choose` coloca uma pergunta de escolha fixa e devolve label,
probabilidade e provider. Suporta um LLM decisor (local ou remoto) e um
classificador linear local. Detalhes em [DECISIONS.md](DECISIONS.md).

## 3.7 Fichas e benchmarks dos modelos

`/models test` mede latência, JSON estruturado e tool calling e guarda
uma ficha JSON com o hardware e a data do último teste. Detalhes em
[MODEL_CARDS.md](MODEL_CARDS.md).

## 3.8 Modo Hi-Fi

Com `--hifi` o Hagar pede ao modelo três interpretações do pedido
e, se as duas mais prováveis estiverem demasiado próximas, pede um esclarecimento
em vez de responder. Detalhes em [HIFI.md](HIFI.md).

## 3.9 Checkpoint, timeouts e contexto

O Hagar guarda um checkpoint dos ficheiros modificados no turno, limita as
chamadas às ferramentas, derrama os outputs grandes para disco e poda o contexto antigo.
Detalhes em [RUNTIME_GUARDS.md](RUNTIME_GUARDS.md).

## 3.10 AIsh

`aish.exec` é uma shell semântica restrita: os comandos são traduzidos
em ferramentas Hagar, não executados como programas. É **DENY por predefinição** e tem de ser
ativada explicitamente em `policy.yaml`. Detalhes em [AISH.md](AISH.md).
As transformações textuais usam [text.transform](TEXT_TRANSFORM.md).

## 3.11 Receitas de desenvolvimento

`dev.run` executa receitas fidedignas para testes, debug e build, sem shell e
sem comandos arbitrários. É **DENY por predefinição** e requer `DEV_EXEC`.
Detalhes em [DEV_RUN.md](DEV_RUN.md).

## 3.12 Boxed transform

`box.run` executa transformações LLM bounded (`summarize`, `translate`,
`extract_json`) sem memória, ferramentas ou prompt livre. É **DENY por predefinição**
e requer `BOX_EXEC`. Detalhes em [BOXES.md](BOXES.md).

## 3.13 Hagar Flow

`flow.run` executa um subconjunto linear de Python validado e
interpretado pelo Hagar, sem import, funções, try ou acesso a objetos
Python. É **DENY por predefinição** e requer `FLOW_EXEC`. Detalhes em
[FLOW.md](FLOW.md).

---

# 4. Documentação

O HAGAR tem documentação em várias línguas. Neste momento as línguas suportadas
são: italiano, inglês, espanhol, português, chinês, russo. Cada língua tem o seu próprio subdiretório dedicado em Docs.

- [MANUAL.md](MANUAL.md) — formato da configuração, comandos de consola,
  opções de linha de comandos, pressupostos de base.
- [ARCHITECTURE.md](ARCHITECTURE.md) — A arquitetura de software desta
  versão do harness: componentes, modelo de segurança, limites conhecidos.
- [ROADMAP.md](ROADMAP.md) — Funcionalidades planeadas por implementar, decisões já tomadas
  e questões ainda em aberto.
- [PLUGINS.md](PLUGINS.md) — contratos para ferramentas e providers LLM plugin.
- [HIFI.md](HIFI.md) — pré-passo de interpretação e esclarecimento.
- [RUNTIME_GUARDS.md](RUNTIME_GUARDS.md) — checkpoint, timeouts, spill e compaction.
- [AISH.md](AISH.md) — shell semântica restrita e policy DENY.
- [TEXT_TRANSFORM.md](TEXT_TRANSFORM.md) — transformações textuais bounded.
- [DEV_RUN.md](DEV_RUN.md) — receitas para testes, debug e build.
- [BOXES.md](BOXES.md) — transformações LLM bounded.
- [FLOW.md](FLOW.md) — DSL restrita e interpretador.
- [DECISIONS.md](DECISIONS.md) — ferramentas de decisão e providers.
- [MODEL_CARDS.md](MODEL_CARDS.md) — fichas, benchmarks e hardware.
- [DOCUMENT_TOOL.md](DOCUMENT_TOOL.md) — especificação da document tool,
  grafo semântico, plugins de formato e host nativo.
- [SUBAGENTS.md](SUBAGENTS.md) — MVP subagentes, isolamento e limites.
- [CHANGELOG.md](CHANGELOG.md) — histórico das alterações.
