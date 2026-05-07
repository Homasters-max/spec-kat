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
version: 2
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD Meta Harness Core.md
- raw/Wiki Skill DocGraph Integration Plan.md
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

**Граф строится из трёх источников (Q6, Q16):**

```text
Graph = f(Code, EventLog, WikiProse)
```

- `CodeExtractor` → file nodes + code_depends edges (из кодовой базы)
- `EventExtractor` → структурные данные: phase/task nodes, status, deps (из EventLog; I-QE-ADAPTER-1)
- `WikiSemanticExtractor` → семантика: prose, intent, domain context (из WikiSnapshot через WikiSnapshotLoader; I-QE-ADAPTER-2)

Адаптеры не пересекаются по источникам: EventExtractor никогда не читает wiki, WikiSemanticExtractor никогда не читает структуру из EventLog.

**Fingerprint (I-QE-FINGERPRINT-1):**

```text
hash(event_offset + wiki_snapshot_version + code_hash)
```

`spec_hash` удалён — заменён на `wiki_snapshot_version` (Q16). Если fingerprint изменился после `explain` но до `write` — [[execution-guard]] блокирует write.

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

- Граф кэшируется под fingerprint.
- Разделение на три адаптера по источникам (Code/EventLog/WikiProse) предотвращает смешение SSOT ([[docgraph-dual-ssot]]).

## See Also

- [[context-snapshot]]
- [[execution-guard]]
- [[graph-session-state]]
- [[sdd-meta-harness]]
- [[wiki-semantic-extractor]]
- [[wiki-snapshot-loader]]
- [[docgraph-dual-ssot]]
