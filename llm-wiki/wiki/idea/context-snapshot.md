---
id: idea/context-snapshot
page_type: idea
domain: sdd
layer: architecture
tags:
- search
- read-only
- ssot
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# Context Snapshot

Return type `QueryEngine.execute(Query)` — неизменяемый снимок подграфа, полученного в ответ на запрос.

## How It Works

```python
@dataclass
class ContextSnapshot:
    id: str            # hash(nodes + edges + params)
    nodes: list[Node]
    edges: list[Edge]
    params: QueryParams  # start_nodes, budget, graph_version
```

- `id` = `hash(nodes + edges + params)` — уникальный идентификатор снимка.
- Отдельного persistent хранилища нет — кэширование внутри [[graph-query-engine]] (dict по fingerprint).
- В [[trace-store]] пишется только `snapshot.id` (hash) — для аудита.
- [[execution-guard]] использует `snapshot.id` при `explain` команде.

## When To Use

Передаётся от [[graph-query-engine]] к [[execution-guard]] при проверке связности задачи. Используется для аудита в [[trace-store]].

## Trade-offs

- Snapshot не персистируется — нельзя восстановить nodes/edges по id без повторного запроса.
- id уникален только в пределах жизни процесса.

## See Also

- [[graph-query-engine]]
- [[execution-guard]]
- [[trace-store]]
