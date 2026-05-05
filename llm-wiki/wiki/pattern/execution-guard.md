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
version: 3
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
- raw/Memory Layer and Invariant Management.md
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
---
# Execution Guard (L1)

Guard pipeline в SDD: три типа guard'ов (Structural, Runtime, Policy), пять middleware слотов в фиксированном порядке. Pure function над externalized state.

## Guard Taxonomy

| Guard Type | Enforcement | Failure | Configurable | Bypass |
|------------|-------------|---------|--------------|--------|
| Structural | hardcoded constants | ABORT | No | Never |
| Runtime | call-stack assertion | RuntimeError → ABORT | No | Never |
| Policy | PolicyProjection (EventLog-sourced) | RETRY / HUMAN_GATE | Yes, via human gate | No |

**Structural Guards:**

- `L1ExecutionGuardMiddleware`: 4 hardcoded axioms — `NO_EXPLAIN_BEFORE_WRITE`, `GRAPH_FINGERPRINT`, `NO_GRAPH_BEFORE_EXPLAIN`, `TASK_ISOLATED`
- `L1ScopeGuardMiddleware`: `write_scope` из TraceStore (фиксирован при создании задачи, ABORT)

**Runtime Guard:**

- `L0GuardMiddleware`: call-stack assertion — EventStore.append() вызван только из WriteKernel (GL-7)

**Policy Guard:**

- `L1PolicyGuardMiddleware`: читает из [[policy-projection]]
  - `max_write_cycles_per_task` (изменяемый через human gate)
  - actor permissions
  - retry_limit

## Middleware Pipeline

Фиксированный порядок слотов:

```text
slot 0:   ErrorClassifierMiddleware   ← перехват всех GuardError/RuntimeError
slot 0.5: IdempotencyMiddleware        ← dedup команды по idempotency_key (до guards)
slot 1:   L0GuardMiddleware           ← Runtime Guard: EventStore call-stack (GL-7)
slot 2a:  L1ExecutionGuardMiddleware  ← Structural: 4 axioms, hardcoded
slot 2b:  L1ScopeGuardMiddleware      ← Structural: write_scope, ABORT
slot 2c:  L1PolicyGuardMiddleware     ← Policy: PolicyProjection, RETRY/HUMAN_GATE
terminal: WriteKernel.execute_and_project(snapshot, expected_version)
```

**Инварианты pipeline:**

```text
I-GUARD-PIPELINE-1: порядок слотов (0, 0.5, 1, 2a, 2b, 2c, terminal) фиксирован;
                    тест на порядок обязателен в CI
I-GUARD-PIPELINE-2: Structural Guards (2a, 2b) MUST run before Policy Guard (2c)
I-GUARD-PIPELINE-3: L1PolicyGuardMiddleware читает ТОЛЬКО из PolicyProjection;
                    прямые DB-reads запрещены
```

## Execution Guard Logic

`L1ExecutionGuardMiddleware` — pure function:

```python
def check(
    cmd: Command,
    ctx: CommandContext,
    projection_reader: ProjectionReader,
) -> Result:
    state = GraphSessionState.current(ctx.task_id, projection_reader)

    if cmd.type == "resolve":
        return OK

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
        return OK
```

`max_write_cycles_per_task` проверяется в `L1PolicyGuardMiddleware` (slot 2c), не здесь.

Guard не мутирует state — state обновляется через [[graph-session-projection]] после применения события в WriteKernel.

## When To Use

Pipeline вызывается WriteKernel на каждую команду в SDD task session. `IdempotencyMiddleware` (slot 0.5) обрабатывает дубликаты до guard chain.

## Trade-offs

- Structural Guards — ABORT без конфигурации: невозможно случайно ослабить через human gate
- Policy Guards — RETRY/HUMAN_GATE: изменяемые лимиты без правки кода
- Каждый вызов = SELECT к PostgreSQL (stateless read), небольшой latency tradeoff

## See Also

- [[graph-session-projection]]
- [[policy-projection]]
- [[l1-l2-isolation]]
- [[cqrs-boundary]]
- [[write-kernel]]
- [[scope-guard]]
- [[trace-projection]]
