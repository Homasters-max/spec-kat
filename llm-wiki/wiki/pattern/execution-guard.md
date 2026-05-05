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
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
- raw/Memory Layer and Invariant Management.md
---
# Execution Guard (L1)

L1 guard в SDD pipeline: enforces поведенческий протокол агента — нельзя писать без `resolve → explain → write` цикла. Pure function над externalized state — нет instance state, нет side effects.

## How It Works

**Сигнатура:**

```python
def check(
    cmd: Command,
    ctx: CommandContext,
    projection_reader: ProjectionReader,
    memory: L1MemoryLayer          # L2 API физически недоступен (ML-6)
) -> Result:
    state  = GraphSessionState.current(ctx.task_id, projection_reader)  # SELECT из L1
    policy = memory.read.policy()                                        # behavioral rules
```

State читается внутри через `GraphSessionState.current()` — guard не принимает state как аргумент и не мутирует его.

**Иерархия правил:**

```text
Axioms (hardcoded, code-enforced, ABORT):
  NO_EXPLAIN_BEFORE_WRITE   → hardcoded в guard
  GRAPH_FINGERPRINT         → hardcoded в guard
  NO_GRAPH_BEFORE_EXPLAIN   → hardcoded в guard
  TASK_ISOLATED             → hardcoded в guard

Structural (guard-enforced, RETRY/HUMAN_GATE):
  GL-6 Write Gate → ExecutionGuard + ScopeGuard (частично config)

Behavioral (policy-managed, из PolicyProjection):
  retry_limit, scope permissions, max_write_cycles_per_task
  → читаются через memory.read.policy()
```

**Алгоритм:**

```python
def check(cmd, ctx, projection_reader, memory: L1MemoryLayer) -> Result:
    state  = GraphSessionState.current(ctx.task_id, projection_reader)
    policy = memory.read.policy()

    if cmd.type == "resolve":
        return OK  # state обновится через проекцию после применения события

    if cmd.type == "explain":
        if not state.has_graph:
            return DENY("NO_GRAPH_BEFORE_EXPLAIN")      # axiom
        snapshot = query_engine.execute(explain_query(cmd.task_id))
        connected = any(
            e.kind in ("belongs_to", "depends_on", "writes")
            for e in snapshot.edges if e.from_ == cmd.task_id
        )
        if not connected:
            return DENY("TASK_ISOLATED")                 # axiom
        return OK

    if cmd.type == "write":
        if not (state.has_graph and state.has_explain):
            return DENY("NO_EXPLAIN_BEFORE_WRITE")       # axiom
        if current_fingerprint() != state.graph_fingerprint:
            return DENY("GRAPH_CHANGED_AFTER_EXPLAIN")   # axiom

        # behavioral rule (MAX_WRITE_CYCLES) — из policy, не hardcoded
        cycles = memory.read.trace(ctx.task_id).write_cycles
        limit  = policy.max_write_cycles_per_task
        if cycles >= limit:
            return DENY("MAX_WRITE_CYCLES_EXCEEDED")     # severity из policy

        return OK
```

Guard не мутирует state — state обновляется через [[graph-session-projection]] после применения события в WriteKernel.

## When To Use

Вызывается WriteKernel после L0 guard, до handler, на каждую команду в SDD task session.

## Trade-offs

- Pure function: создаётся и уничтожается без потери контекста; тестируется без моков state.
- Behavioral limits (cycle count) в [[policy-projection]] — изменяются через human gate без правки guard кода.
- Каждый вызов = SELECT к PostgreSQL (stateless read), небольшой latency tradeoff.

## See Also

- [[graph-session-projection]] — L1 проекция state (projection_reader source)
- [[policy-projection]] — источник behavioral rules
- [[memory-layer]] — фасад L1 API
- [[l1-l2-isolation]] — guard физически не имеет доступа к L2
- [[scope-guard]]
- [[trace-projection]]
