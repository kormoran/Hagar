# Subagentes — fase assíncrona

**Estado:** implementado
**Data:** 2026-11-07
**Ferramentas:** `agent.spawn`, `agent.status`, `agent.wait`, `agent.result`,
`agent.cancel`, `agent.run` (compatibilidade síncrona), `artifact.*`,
`mailbox.*`

## 1. O que fazem

O modelo pode arrancar até dois subagentes concorrentes:

```text
agent.spawn(task, reason, context?, inputs?) -> agent_id
agent.status(agent_id) -> estado
agent.wait(agent_id, timeout?) -> resultado
agent.result(agent_id) -> resultado
agent.cancel(agent_id) -> ok
```

`spawn` regressa imediatamente. O pai pode continuar a trabalhar e recolher
os resultados quando precisar. `agent.run` permanece como atalho
`spawn + wait` por compatibilidade.

`reason` é obrigatório: é registado na auditoria e é a motivação
pela qual o pai delega o trabalho. A ferramenta exige a capability
`AGENT_SPAWN`; o child não a recebe, pelo que não pode criar outros.
`permissions.agents: true` é o teto de sistema necessário.

A política do child tem de ser **estritamente mais restritiva** que
a do pai. O manager calcula:

```text
child_ceiling = parent_ceiling
              & (FILESYSTEM_READ | MEMORY_READ | COMPUTE | AGENT_DATA)
```

Se o resultado for igual ao teto do pai, `agent.spawn` falha com
`SubagentPolicyError`. Portanto também políticas idênticas são recusadas.
Se o pai não tiver um evaluator, o spawn é recusado.

Cada agente tem um timeout de parede de **5 minutos** (`300` segundos). O
limite é cooperativo: é controlado nos checkpoints do ciclo do agente;
não interrompe um pedido HTTP já em curso. Ao expirar o estado do
child é `timed_out` e a auditoria registra `agent.timed_out`.

Cada child:

- usa o mesmo modelo local do pai, mas um cliente LLM separado;
- tem um registry separado;
- vê apenas as ferramentas com capability `FILESYSTEM_READ`,
  `MEMORY_READ` e `COMPUTE`, mais `AGENT_DATA`;
- pode usar `vision.open` no próprio workspace, mas não
  `agent.*` nem `filesystem.chdir`;
- lê apenas o próprio workspace;
- não escreve na memória;
- encaminha os pedidos ASK ao utilizador através de uma bridge, com timeout de
  180 segundos e DENY na expiração.

O pai LLM não pode aprovar um ASK: o pedido vai sempre ao canal
humano (GUI ou consola). A bridge acrescenta `agent_id` e `parent_id` ao
pedido.

## 2. Workspace privado

Para cada child é criado um workspace temporário:

```text
<hagar-temp>/hagar-subagent-<id>/
```

O child vê-o como:

```text
/home/ai/workspace
```

O workspace é só de leitura. Antes do arranque, o manager copia os
input indicados pelo pai:

```text
agent.spawn(
    task="analisa o CSV",
    reason="os ficheiros são independentes e devem ser analisados em paralelo",
    inputs=["/home/ai/workspace/report.csv"]
)
```

Regras:

- os input têm de ser ficheiros na sandbox do pai;
- o pai tem de ter a permissão de leitura;
- o nome do ficheiro é preservado;
- dois input com o mesmo nome são um erro;
- o child não vê o caminho host;
- o workspace é eliminado no fim do turno.

O pai escreve apenas no próprio workspace. O workspace do child está
fora das raízes do pai, pelo que não é alcançável pelas suas ferramentas.

## 2.1 Outbox, artifact e mailbox

O child não escreve no workspace. Para produzir dados usa a outbox:

```text
artifact.put(text, kind?, mime_type?)       -> artifact_id
artifact.put_file(path, mime_type?)          -> artifact_id
mailbox.send(text, artifacts?)               -> message
```

`artifact.put_file` lê um ficheiro do workspace read-only do child e
copia-o para o store gerido pelo Hagar.

O pai lê com:

```text
artifact.list()
artifact.read(artifact_id, offset?, length?)
artifact.save_to(artifact_id, path, overwrite?)
mailbox.inbox(cursor?, limit?)
mailbox.read(message_id)
mailbox.ack(message_id)
```

`artifact.save_to` copia o artifact inteiro para um caminho escrevível da
sandbox do pai sem fazer passar o conteúdo pelo contexto. É
a operação a usar para artifact maiores do que a janela do modelo:
o modelo lê apenas os chunks de que precisa e guarda o ficheiro completo
com `save_to`.

`save_to` exige `AGENT_DATA`, `FILESYSTEM_WRITE` e
`FILESYSTEM_CREATE`; a política trata-o como uma escrita e pode
pedir confirmação. Não aceita paths host arbitrários.

Limites iniciais:

| Elemento | Limite |
|---|---|
| artifact individual | 50 MB |
| total de artifact por turno | 256 MB |
| artifact por turno | 200 |
| leitura por chamada | 256 KB |
| texto de uma mensagem | 64 KB |
| mensagens por mailbox | 100 |

Os artifact são ficheiros temporários fora do Vault, com hash SHA-256 e
metadados. A mailbox contém apenas texto e referências `artifact_id`.
No fim do turno store e mailbox são esvaziados.

## 3. Limites da implementação

- máximo **2** subagentes ativos (configurável no manager como
  `max_concurrent`);
- apenas modelos locais;
- sem aninhamento: o registry do child exclui `agent.*`;
- timeout de parede de 5 minutos, cooperativo;
- nenhum budget de tokens além de `max_tool_calls`;
- nenhuma GUI dedicada;
- nenhuma escrita de memória;
- ASK do child encaminhadas ao utilizador com timeout 180 segundos; na
  expiração DENY;
- artifact e mailbox são efémeros: desaparecem no fim do turno;
- os eventos internos do child (`turn.*`, `tool.*`) têm `agent_id` na
  auditoria.

No fim do turno do pai:

1. `finish_turn()` espera pelos filhos durante um timeout;
2. cancela os que ainda estão ativos;
3. elimina os workspace;
4. esquece os job.

## 4. Componentes isolados

| Componente | Pai | Child |
|---|---|---|
| LLM client | `harness.llm` | nova instância, mesmo modelo |
| Tool registry | completo | filtrado read-only |
| Filesystem | workspace do pai | workspace privado em só de leitura |
| Memória | `MemoryStore` | `memory=None`, nenhuma escrita |
| Artifact/mailbox | leitura | outbox do child |
| Confirmações | utilizador | bridge para o utilizador, timeout 180 |
| Usage | ledger do pai | ledger separado |
| Auditoria | partilhada, com lock | eventos `agent.*` |

O child não tem o contexto automático do pai: o pai tem de passar
`context`.

## 5. Ferramentas admitidas

O pai tem de ter as capability `AGENT_SPAWN` e `COMPUTE`; o child
não recebe `AGENT_SPAWN` e não pode, portanto, criar outros agentes.

O registry do child inclui as ferramentas cujas capability são um
subconjunto de:

```text
FILESYSTEM_READ
MEMORY_READ
COMPUTE
AGENT_DATA
```

O child recebe `artifact.put`, `artifact.put_file` e `mailbox.send`.
Não recebe `artifact.read`, `artifact.list`, `mailbox.inbox`,
`mailbox.read` ou `mailbox.ack`: esses são do pai.

São excluídos explicitamente:

```text
filesystem.chdir
agent.*
```

São excluídos por capability:

- escrita filesystem;
- criação, renomeação, cópia, eliminação;
- escrita de memória;
- rede;
- MCP;
- shell.

## 6. Auditoria

Eventos registados pelo manager:

```text
agent.spawned
agent.policy_rejected
agent.started
agent.finished
agent.timed_out
agent.cancelled
agent.failed
confirmation.timeout
artifact.discarded
```

Campos principais:

```text
agent_id
agent
parent
task
inputs
max_tool_calls
max_seconds
status
usage
duration_ms
error
artifact
owner
kind
size
sha256
read_count
reason
```

Todos os eventos do pai e dos filhos levam `agent_id`. Os eventos
do registry e do Agent usam o id do agente que executou
a ação; os eventos do manager acrescentam `agent_id` e `parent`.
`agent.policy_rejected` é emitido se o spawn não tiver uma política
estritamente mais restritiva.

`artifact.discarded` é emitido no fim do turno para cada artifact não
guardado com `artifact.save_to`:

```text
reason=unread                → nunca lido
reason=read_but_not_saved    → lido mas não exportado
```

`confirmation.timeout` é emitido se o ASK do child permanecer sem
resposta durante 180 segundos; o resultado é DENY. A GUI mostra o pedido com
`agent_id`/`parent_id` e o pai não o pode resolver.

Os artifact exportados não produzem o evento: o ficheiro já está no
workspace do pai. O conteúdo nunca é escrito na auditoria.

`AuditLog.record` está protegido por lock, para que as escritas concorrentes não
entrelacem a cadeia de hash.

## 7. Concorrência

- threads separadas para os filhos;
- limite `max_concurrent = 2`;
- lock no dicionário dos job;
- nenhuma condição de race no filesystem: workspace separados;
- nenhuma partilha de `MemoryStore`, sandbox ou cliente LLM;
- provider local com pedidos concorrentes;
- `agent.wait` bloqueia apenas o chamador, não os outros filhos.

## 8. Testes

`tests/test_subagents.py` cobre:

- execução com ferramentas read-only;
- exclusão de escrita e `agent.*`;
- passagem do contexto;
- cópia dos input no workspace privado;
- recusa acima de `max_concurrent`;
- dois subagentes concorrentes;
- erro de construção do provider;
- eventos de auditoria.

Teste live executado com LM Studio e `gemma-3-27b-it`: dois subagentes
concorrentes concluídos, cada um com usage separado.

## 9. Próximos passos

- export explícito dos artifact do workspace do child;
- budget de tokens/tempo e timeout de parede;
- aninhamento controlado, se pedido;
- `agent_id` em todos os eventos internos;
- confirmações delegadas ao pai ou à GUI;
- modelo escolhido pelo broker, não pelo manager.
