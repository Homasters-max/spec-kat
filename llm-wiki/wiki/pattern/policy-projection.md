---
id: pattern/policy-projection
page_type: pattern
domain: sdd
layer: architecture
tags:
- ssot
- enforcement
- write-path
- pipeline
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/Memory Layer and Invariant Management.md
---
# Policy Projection

L1-проекция в [[projection-registry]]: единственный источник behavioral rules в системе. Заменяет удалённую `InvariantProjection` для управляемых правил. Axioms (hardcoded guard invariants) — вне этой проекции.

## How It Works

**Обновление:** через PolicyKernel → [HUMAN_GATE] → `PolicyUpdated` event → EventLog → PolicyProjection rebuild.

**Bootstrap:** `norm_catalog.yaml` → `bootstrap-policy` command → `PolicyUpdated` events при первом запуске.

**API (через [[memory-layer]]):**

```python
memory.read.policy(scope=None) -> list[PolicyRule]
# scope зарезервирован для v2; сейчас всегда глобальный список
```

**Содержимое PolicyRule (примеры):**

```python
max_write_cycles_per_task: int   # лимит write-циклов на задачу (напр. 3)
retry_limit: int                  # лимит retry для RETRY-severity нарушений
scope_permissions: dict[str, list[str]]  # разрешённые операции по scope
```

**Guard check (behavioral rule через policy):**

```python
cycles = memory.read.trace(task_id).write_cycles
limit  = memory.read.policy().max_write_cycles_per_task
if cycles > limit:
    return DENY("MAX_WRITE_CYCLES_EXCEEDED")  # severity: RETRY / HUMAN_GATE из policy
```

**Иерархия правил:**

```text
Axioms (hardcoded в Guards, code-enforced, ABORT):
  NO_EXPLAIN_BEFORE_WRITE, GRAPH_FINGERPRINT, NO_GRAPH_BEFORE_EXPLAIN
  → не читаются из PolicyProjection, не меняются через PolicyKernel

Structural (guard-enforced, RETRY/HUMAN_GATE):
  GL-6 Write Gate → частично hardcoded, частично config

Behavioral (policy-managed, в PolicyProjection):
  retry_limit, scope permissions, max_write_cycles_per_task
  → управляются через PolicyKernel → [HUMAN_GATE] → PolicyUpdated
```

**Feedback loop:**

```text
Guard violation → ErrorClassified + guard_rule_id
  → TraceProjection: violation count per rule_id per phase
  → MetaOptimization: анализ трендов
  → proposal: "GL-6 нарушается в 40% задач фазы 28"
  → [HUMAN_GATE]
  → PolicyKernel.emit(PolicyUpdated)
  → EventLog → PolicyProjection обновляется
```

Axioms (GL-1, GL-7, NO_EXPLAIN_BEFORE_WRITE) — вне этого цикла. Не меняются.

## When To Use

Используется всеми L1-Guards для чтения behavioral rules. Обновляется только через PolicyKernel (с human gate). Не используется для hardcoded axioms — только для managed behavioral constraints.

## Trade-offs

- Centralises all mutable rules in one projection — нет scattered config files.
- Human gate на изменение PolicyProjection защищает от автоматической деградации Guards.
- Аксиомы не в ProjectionRegistry — нет риска их случайной перезаписи через PolicyUpdated.

## See Also

- [[memory-layer]] — фасад, через который читается policy
- [[execution-guard]] — основной потребитель behavioral rules
- [[trace-projection]] — фидит violation counts в feedback loop
- [[projection-registry]] — инфраструктура проекций
- [[graph-session-projection]] — читает policy для MAX_WRITE_CYCLES check
