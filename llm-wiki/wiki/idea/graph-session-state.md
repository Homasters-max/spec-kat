---
id: idea/graph-session-state
page_type: idea
domain: sdd
layer: architecture
tags:
- enforcement
- pipeline
- write-path
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# Graph Session State

Структура состояния исполнения одной task session в SDD. Отслеживает, прошёл ли агент обязательный цикл `resolve → explain → write`.

## How It Works

```yaml
GraphSessionState:
  task_id: string
  graph_fingerprint: string  # зафиксирован после explain
  has_graph: bool
  has_explain: bool
  writes_count: int
```

**Lifecycle:**

```text
start-task     → создаётся: has_graph=F, has_explain=F, writes_count=0
resolve        → has_graph = True
explain        → has_explain = True, graph_fingerprint = current
write-команда  → проверка + reset: has_graph=F, has_explain=F, writes_count=0
```

`graph_fingerprint` фиксируется при `explain` и верифицируется при `write` — если граф изменился после explain, write блокируется.

[[execution-guard]] читает и мутирует этот объект при каждой команде.

## When To Use

Создаётся автоматически при `sdd start-task`. Живёт в памяти в течение task session.

## Trade-offs

- Reset после write означает: каждый write требует нового `resolve → explain`.
- Не персистируется — при перезапуске процесса сессия начинается заново.

## See Also

- [[execution-guard]]
- [[graph-query-engine]]
- [[sdd-meta-harness]]
