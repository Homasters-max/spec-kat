---
id: pattern/graph-query-engine
page_type: pattern
domain: sdd
layer: architecture
tags:
- search
- pipeline
- automation
- ssot
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# Graph Query Engine

Единственный интерфейс навигации по графу зависимостей задач/файлов в SDD. Заменяет строковый DSL — принимает только типизированный `Query`.

## How It Works

```python
@dataclass
class Query:
    source: str      # "graph"
    selector: str    # "node" | "edge"
    filters: dict    # {"type": "task", "phase_id": 3}
    traversal: dict  # {"edge_kinds": ["depends_on"], "direction": "out", "max_hops": 2}
    limit: int
    order_by: str    # обязательно — для детерминизма

class QueryEngine:
    def execute(self, query: Query) -> ContextSnapshot: ...
```

**Граф строится из трёх источников:**

```text
Graph = f(Code, Specs, EventLog)
```

- `CodeExtractor` → file nodes + code_depends edges
- `SpecExtractor` → phase/task/spec nodes + belongs_to/depends_on/writes edges
- `EventExtractor` → актуализирует статус узлов

**Предустановленные стратегии:**

```yaml
resolve:   edge_kinds: [depends_on, belongs_to],         direction: out
explain:   edge_kinds: [depends_on, belongs_to, writes], direction: out
trace:     edge_kinds: [depends_on],                     direction: in
invariant: edge_kinds: [belongs_to],                     direction: out
```

**Детерминизм:** `order_by` обязателен — одинаковый граф + Query → одинаковый результат.

## When To Use

При `explain` и `resolve` командах в SDD task session. [[execution-guard]] использует QueryEngine для проверки связности задачи с графом перед write.

## Trade-offs

- Граф кэшируется под fingerprint `hash(code_hash + spec_hash + event_offset)`.
- Если fingerprint изменился после `explain` но до `write` — [[execution-guard]] блокирует write.

## See Also

- [[context-snapshot]]
- [[execution-guard]]
- [[graph-session-state]]
- [[sdd-meta-harness]]
