# Subagents — fase assíncrona

**Estado:** implementado
**Data:** 2026-11-07  
**Tool:** `agent.spawn`, `agent.status`, `agent.wait`, `agent.result`,
`agent.cancel`, `agent.run` (compatibilidade síncrona), `artifact.*`,
`mailbox.*`

## 1. O que fazem

O modelo pode lançar até dois subagents concorrentes:

```text
agent.spawn(task, reason, context?, inputs?) -> agent_id
agent.status(agent_id) -> estado
agent.wait(agent_id, timeout?) -> resultado
agent.result(agent_id) -> resultado
agent.cancel(agent_id) -> ok
```

`spawn` devolve imediatamente. O pai pode continuar a trabalhar e recolher
os resultados quando forem necessários. `agent.run` mantém-se como atalho
`spawn + wait` por compatibilidade.

`reason` é obrigatório: fica registado no audit e é a justificação
pela qual o pai delega o trabalho. O tool exige a capability
`AGENT_SPAWN`; o subagent não a recebe, pelo que não pode criar outros.
`permissions.agents: true` é o teto de sistema necessário.

A policy do subagent tem de ser **estritamente mais restritiva** do que
a do pai. O manager calcula:

```text
child_ceiling = parent_ceiling
              & (FILESYSTEM_READ | MEMORY_READ | COMPUTE | AGENT_DATA)
```

Se o resultado for igual ao teto do pai, `agent.spawn` falha com
`SubagentPolicyError`. Por isso, também as policies idênticas são rejeitadas.
Se o pai não tiver um evaluator, o spawn é rejeitado.

Cada agente tem um timeout de parede de **5 minutos** (`300` segundos). O
limite é cooperativo: é verificado nos checkpoints do ciclo do agente;
não interrompe um pedido HTTP já em curso. Ao expirar, o estado do
subagent é `timed_out` e o audit regista `agent.timed_out`.

Cada subagent:

- usa o mesmo modelo local do pai, mas um cliente LLM separado;
- tem um registry separado;
- vê apenas os tools com capability `FILESYSTEM_READ`,
  `MEMORY_READ` e `COMPUTE`, mais `AGENT_DATA`;
- pode usar `vision.open` no próprio workspace, mas não
  `agent.*` nem `filesystem.chdir`;
- lê apenas o próprio workspace;
- não escreve na memory;
- encaminha os pedidos ASK ao utilizador através de uma bridge, com timeout de
  180 segundos e DENY ao expirar.

O pai LLM não pode aprovar um ASK: o pedido vai sempre para o canal
humano (GUI ou consola). A bridge acrescenta `agent_id` e `parent_id` ao
pedido.

## 2. Workspace privado

Para cada subagent é criado um workspace temporário:

```text
<hagar-temp>/hagar-subagent-<id>/
```

O subagent vê-o como:

```text
/home/ai/workspace
```

O workspace é só de leitura. Antes do arranque, o manager copia os
inputs indicados pelo pai:

```text
agent.spawn(
    task="analizza il CSV",
    reason="i file sono indipendenti e vanno analizzati in parallelo",
    inputs=["/home/ai/workspace/report.csv"]
)
```

Regras:

- os inputs têm de ser ficheiros na sandbox do pai;
- o pai tem de ter permissão de leitura;
- o nome do ficheiro é preservado;
- dois inputs com o mesmo nome são um erro;
- o subagent não vê o caminho host;
- o workspace é eliminado no fim do turno.

O pai escreve apenas no próprio workspace. O workspace do subagent está
fora das raízes do pai, pelo que não é alcançável pelos tools dele.

## 2.1 Outbox, artifact e mailbox

O subagent não escreve no workspace. Para produzir dados usa a outbox:

```text
artifact.put(text, kind?, mime_type?)       -> artifact_id
artifact.put_file(path, mime_type?)          -> artifact_id
mailbox.send(text, artifacts?)               -> message
```

`artifact.put_file` lê um ficheiro do workspace read-only do subagent e
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

`artifact.save_to` copia o artifact completo para um caminho com permissão
de escrita na sandbox do pai sem fazer passar o conteúdo pelo contexto. É
a operação a usar para artifacts maiores do que a janela do modelo:
o modelo lê apenas os chunks de que precisa e guarda o ficheiro completo
com `save_to`.

`save_to` exige `AGENT_DATA`, `FILESYSTEM_WRITE` e
`FILESYSTEM_CREATE`; a policy trata-o como uma escrita e pode
pedir confirmação. Não aceita caminhos host arbitrários.

Limites iniciais:

| Elemento | Limite |
|---|---|
| artifact individual | 50 MB |
| total de artifacts por turno | 256 MB |
| artifacts por turno | 200 |
| leitura por chamada | 256 KB |
| texto de uma mensagem | 64 KB |
| mensagens por mailbox | 100 |

Os artifacts são ficheiros temporários fora do Vault, com hash SHA-256 e
metadados. A mailbox contém apenas texto e referências `artifact_id`.
No fim do turno, o store e a mailbox são esvaziados.

## 3. Limites da implementação

- máximo de **2** subagents ativos (configurável no manager como
  `max_concurrent`);
- apenas modelos locais;
- sem aninhamento: o registry do subagent exclui `agent.*`;
- timeout de parede de 5 minutos, cooperativo;
- nenhum budget de tokens além de `max_tool_calls`;
- nenhuma GUI dedicada;
- nenhuma escrita na memory;
- ASK do subagent encaminhados ao utilizador com timeout de 180 segundos; ao
  expirar, DENY;
- artifacts e mailbox são efémeros: desaparecem no fim do turno;
- os eventos internos do subagent (`turn.*`, `tool.*`) têm `agent_id` no
  audit.

No fim do turno do pai:

1. `finish_turn()` espera pelos subagents durante um timeout;
2. cancela os que ainda estão ativos;
3. elimina os workspaces;
4. esquece os jobs.

## 4. Componentes isolados

| Componente | Pai | Subagent |
|---|---|---|
| LLM client | `harness.llm` | nova instância, mesmo modelo |
| Tool registry | completo | filtrado read-only |
| Filesystem | workspace do pai | workspace privado só de leitura |
| Memory | `MemoryStore` | `memory=None`, nenhuma escrita |
| Artifact/mailbox | leitura | outbox do subagent |
| Confirmações | utilizador | bridge para o utilizador, timeout 180 |
| Usage | ledger do pai | ledger separado |
| Audit | partilhado, com lock | eventos `agent.*` |

O subagent não tem o contexto automático do pai: o pai tem de passar
`context`.

## 5. Tools permitidos

O pai tem de ter as capabilities `AGENT_SPAWN` e `COMPUTE`; o subagent
não recebe `AGENT_SPAWN` e não pode, por isso, criar outros agentes.

O registry do subagent inclui os tools cujas capabilities são um
subconjunto de:

```text
FILESYSTEM_READ
MEMORY_READ
COMPUTE
AGENT_DATA
```

O subagent recebe `artifact.put`, `artifact.put_file` e `mailbox.send`.
Não recebe `artifact.read`, `artifact.list`, `mailbox.inbox`,
`mailbox.read` ou `mailbox.ack`: esses são do pai.

São excluídos explicitamente:

```text
filesystem.chdir
agent.*
```

São excluídos por capability:

- escrita no filesystem;
- criação, renomeação, cópia, eliminação;
- escrita na memory;
- rede;
- MCP;
- shell.

## 6. Audit

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

Todos os eventos do pai e dos subagents levam `agent_id`. Os eventos
do registry e do Agent usam o id do agente que executou
a ação; os eventos do manager acrescentam `agent_id` e `parent`.
`agent.policy_rejected` é emitido se o spawn não tiver uma policy
estritamente mais restritiva.

`artifact.discarded` é emitido no fim do turno para cada artifact não
guardado com `artifact.save_to`:

```text
reason=unread                → nunca lido
reason=read_but_not_saved    → lido mas não exportado
```

`confirmation.timeout` é emitido se o ASK do subagent ficar sem
resposta durante 180 segundos; o resultado é DENY. A GUI mostra o pedido com
`agent_id`/`parent_id` e o pai não o pode resolver.

Os artifacts exportados não produzem o evento: o ficheiro já está no
workspace do pai. O conteúdo nunca é escrito no audit.

`AuditLog.record` está protegido por lock, para que as escritas concorrentes
não entrelacem a cadeia de hash.

## 7. Concorrência

- threads separadas para os subagents;
- limite `max_concurrent = 2`;
- lock no dicionário de jobs;
- nenhuma condição de race no filesystem: workspaces separados;
- nenhuma partilha de `MemoryStore`, sandbox ou cliente LLM;
- provider local com pedidos concorrentes;
- `agent.wait` bloqueia apenas o chamador, não os outros subagents.

## 8. Testes

`tests/test_subagents.py` cobre:

- execução com tools read-only;
- exclusão de escrita e `agent.*`;
- passagem do contexto;
- cópia dos inputs no workspace privado;
- rejeição acima de `max_concurrent`;
- dois subagents concorrentes;
- erro de construção do provider;
- eventos de audit.

Teste live executado com LM Studio e `gemma-3-27b-it`: dois subagents
concorrentes concluídos, cada um com usage separado.

## 9. Próximos passos

- export explícito dos artifacts do workspace do subagent;
- budget de tokens/tempo e timeout de parede;
- aninhamento controlado, se solicitado;
- `agent_id` em todos os eventos internos;
- confirmações delegadas ao pai ou à GUI;
- modelo escolhido pelo broker, não pelo manager.
