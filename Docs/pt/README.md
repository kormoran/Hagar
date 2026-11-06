<p align="center">
  <img src="../HAGAR.jpg">
</p>

[Italiano](../it/README.md) · [English](../en/README.md) · [Español](../es/README.md) · [中文](../zh/README.md) · [Русский](../ru/README.md) · [Português](../pt/README.md) · [العربية](../ar/README.md)

# H.A.G.A.R.

Harness Agêntico Geral para IA Resiliente (General Resilient Agentic Harness for AIs)

# 0. Como tudo começou: a segurança

Criei o HAGAR porque nenhum outro harness para IA isolava os meus ficheiros por predefinição. Fosse DeepSeek, Claude Code, AutoGen ou outro, se deixados livres, acabam todos por expor o teu file system aos LLM. És TU que tens de impor limites, e tens de o fazer bem, senão o problema é teu. Nenhuma destas ferramentas garante que os teus dados não sejam lidos com fins imprecisos, por erro ou por ambos os motivos. E se não for o próprio harness a fazê-lo, pode ser aquele plugin tão giro, aquela skill utilíssima ou qualquer outra adição que acabaste de instalar...

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

`pip install -e .` declara os pacotes `core`, `llm` e `memory` e
instala o comando `hagar`:

```powershell
hagar --config hagar.yaml
hagar --model qwen3:8b
hagar --no-memory
hagar --no-native-tools
hagar --version
```

A configuração é procurada pela ordem seguinte: parâmetro `--config`,
variável de ambiente `HAGAR_CONFIG` e, por fim, o ficheiro `./hagar.yaml`.
É também possível utilizar `python -m hagar` trabalhando diretamente sobre
o código-fonte.

## 3.1 Estrutura

```
hagar.py            Script de lançamento do harness
hagar.yaml          Script de configuração predefinido
policy.yaml			Configuração das permissões para as ferramentas (integradas e MCP)
core/               config, agent, audit log, registry, sandbox e tools
llm/                LLM backends (Ollama, DeepSeek, Claude, Gemini), cliente MCP
memory/             acesso ao vault
tests/              suite pytest
tools/              helpers de desenvolvimento (test runner, sandbox shim, model benchmark)
local_tools/		Ferramentas para as IA integradas no HAGAR - não MCP, mas disponíveis diretamente
```

## 3.2 LLM backends

`model.provider` seleciona o backend. Os esquemas das ferramentas (tool), a conversão das mensagens e os percursos nativos ou de fallback são geridos em `llm/base.py`; por isso, mudar de provider não exige alterações à infraestrutura de execução (harness).

A chamada nativa de ferramentas é a predefinição para todos os quatro backends. Se um modelo recusar esse modo (devolvendo um erro HTTP 400, 404 ou 422), o agente passa ao protocolo JSON textual para toda a sessão; é possível forçar o uso do protocolo textual definindo `model.native_tools: false` ou passando o argumento `--no-native-tools`.

| provider   | transporte                    | chave API             |
|------------|------------------------------|------------------------|
| `ollama`   | nativo `/api/chat`           | nenhuma                |
| `deepseek` | REST compatível com OpenAI  | `DEEPSEEK_API_KEY`     |
| `claude`   | Anthropic Messages API       | `ANTHROPIC_API_KEY`    |
| `gemini`   | Generative Language API      | `GEMINI_API_KEY`       |

Os nomes dos modelos atualmente suportados para o DeepSeek são `deepseek-flash` (predefinição) e `deepseek-v4-pro`; o antigo `deepseek-chat` já não é aceite. O teste live usa `deepseek-flash`, a menos que seja substituído pela variável `HAGAR_LIVE_DEEPSEEK_MODEL`. O script `tools/diagnose_deepseek.py` permite verificar o DNS, o formato da chave e o endpoint, sem mostrar a própria chave.

As chaves são lidas apenas de variáveis de ambiente e nunca do ficheiro YAML. Se o nome predefinido da variável não servir às próprias necessidades, pode especificar-se outro com `model.api_key_env`. O parâmetro `model.host` indica o URL base do provider (com um valor predefinido específico para cada um; por exemplo, o Ollama usa `http://localhost:11434`), enquanto `model.max_tokens` se aplica apenas ao Claude (com um valor predefinido de 1024). 

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

A opção `ask` gera um pedido na consola do tipo `lo faccio? (y/N)` (com valor predefinido `N`); o protocolo `ConfirmationProvider` permite ainda implementar uma caixa de diálogo modal numa interface gráfica (GUI). 
O ficheiro das políticas é lido antes da criação do LLM: se estiver em falta ou
não for válido, cada política é definida como `DENY`, o erro é registado no log de auditoria (`policy.failed`) e apresentado no chat, enquanto o harness continua a funcionar.

## 3.5 Memória

O sistema mantém uma memória episódica da conversa dentro do vault do Obsidian
(`<vault>/Hagar/chat/`) e insere os últimos `memory.context_turns` em cada prompt. O modelo pode guardar memórias persistentes através de
`memory.create_skill` (arquivadas como `candidate` com indicação da proveniência),
listá-las com `memory.list_skills` e consultar os passos anteriores
através de `memory.get_context`.

```yaml
memory:
enabled: true
vault_subdir: Hagar
context_turns: 10
max_skill_chars: 4000
```

Se o vault estiver ausente ou não for acessível em escrita, a funcionalidade de memória é desativada
com a geração de um aviso, enquanto o sistema continua a funcionar. As escritas em memória passam pelo motor das políticas (`MEMORY_READ`/`MEMORY_WRITE`; por predefinição, as operações de escrita exigem confirmação). Ver ARCHITECTURE §3.11 para a estrutura do vault.
---

# 4. Documentação

O HAGAR tem documentação em várias línguas. Neste momento as línguas suportadas
são: italiano, inglês, espanhol, português, chinês, russo. Cada língua tem a sua subdirectoria dedicada em Docs.

- [MANUAL.md](MANUAL.md) — formato da configuração, comandos de consola, 
  opções de linha de comandos, pressupostos de base. 
- [ARCHITECTURE.md](ARCHITECTURE.md) — A arquitetura de software desta 
  versão do harness: componentes, modelo de segurança, limites conhecidos.
- [ROADMAP.md](ROADMAP.md) — Funcionalidades concebidas a implementar, decisões já tomadas
  e questões ainda em aberto.
- [CHANGELOG.md](CHANGELOG.md) — cronologia das alterações.
