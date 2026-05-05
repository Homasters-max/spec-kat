---
id: pattern/execution-guard
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- pipeline
- validation
- write-path
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# Execution Guard (L1)

L1 guard в SDD pipeline: enforces поведенческий протокол агента — нельзя писать без `resolve → explain → write` цикла.

## How It Works

Работает с [[graph-session-state]] и [[trace-store]]. Алгоритм:

```python
def check(trace: TraceReader, state: GraphSessionState, cmd: Command) -> Result:
    if cmd.type == "resolve":
        state.has_graph = True
        return OK

    if cmd.type == "explain":
        if not state.has_graph:
            return DENY("NO_GRAPH_BEFORE_EXPLAIN")
        snapshot = query_engine.execute(explain_query(cmd.task_id))
        connected = any(
            e.kind in ("belongs_to", "depends_on", "writes")
            for e in snapshot.edges if e.from_ == cmd.task_id
        )
        if not connected:
            return DENY("TASK_ISOLATED")
        state.has_explain = True
        state.graph_fingerprint = current_fingerprint()
        return OK

    if cmd.type == "write":
        if not (state.has_graph and state.has_explain):
            return DENY("NO_EXPLAIN_BEFORE_WRITE")
        if current_fingerprint() != state.graph_fingerprint:
            return DENY("GRAPH_CHANGED_AFTER_EXPLAIN — repeat explain")
        if state.writes_count > 0:
            return DENY("THRASHING")
        # reset после write
        state.has_graph = False; state.has_explain = False; state.writes_count = 0
        return OK
```

**Правила enforcement:**

```text
NO_GRAPH_BEFORE_EXPLAIN
NO_EXPLAIN_BEFORE_WRITE
GRAPH_CHANGED_AFTER_EXPLAIN  → повторный explain обязателен
THRASHING (> 1 write per cycle)
TASK_ISOLATED                → задача не связана с графом
```

L1 guard всегда вызывается **после** L0 guard, оба — **до** handler.

## When To Use

Всегда в SDD task session — является частью execution flow на каждую команду.

## Trade-offs

- После каждой write-команды `GraphSessionState` сбрасывается — следующий write требует нового цикла `resolve → explain`.
- Fingerprint guard защищает от write на устаревшем графе.

## See Also

- [[graph-session-state]]
- [[graph-query-engine]]
- [[trace-store]]
- [[scope-guard]]
- [[sdd-meta-harness]]
