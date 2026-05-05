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
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/Memory Layer and Invariant Management.md
- raw/orchestrator-agentloop-plan.md
---
# Policy Projection

L1-проекция в [[projection-registry]]: единственный источник behavioral rules в системе. Заменяет удалённую `InvariantProjection` для управляемых правил. Axioms (hardcoded guard invariants) — вне этой проекции.

## How It Works

**Обновление:** через PolicyKernel → [HUMAN_GATE] → `PolicyUpdated` event → EventLog → PolicyProjection rebuild.

**Bootstrap:** `norm_catalog.yaml` → `bootstrap-policy` command → `PolicyUpdated` events при первом запуске.

**API (через [[memory-layer]]):**

```python
memory.read.policy(scope=None) -> list[PolicyRule]     # глобальный список
memory.read.policy(scope=phase_id) -> PolicySnapshot   # phase-scoped (AgentLoop)
```

**Основные PolicyRule-ключи:**

```python
max_write_cycles_per_task: int   # лимит write-циклов на задачу (напр. 3)
retry_limit: int                  # backward compat scalar; AgentLoop читает как {"DEFAULT": retry_limit}
scope_permissions: dict[str, list[str]]  # разрешённые операции по scope
```

**Loop-specific keys (читаются [[agent-loop]] через [[loop-policy]]):**

```python
step_budget: int                     # макс. шагов за сессию (default: 50); hard stop
retry_budget: dict[str, int]         # error_type → макс. retry; fallback: "DEFAULT"
re_explain_budget: int               # макс. RE_EXPLAIN переходов за сессию (default: 2)
phase_write_allowed: bool            # false в VALIDATE-фазе → write tool_calls отклоняются
gate_freeze_ttl_hours: int           # TTL frozen Sandbox при GATE (default: 24)
```

**Lazy bootstrap:** при отсутствии записи для `scope=phase_id` возвращается `PolicySnapshot` с defaults и `policy_version = "0.0.0-bootstrap"`. Defaults документируются как контракт — см. [[loop-policy]].

**Guard check (behavioral rule через policy):**

```python
cycles = memory.read.trace(task_id).write_cycles
limit  = memory.read.policy().max_write_cycles_per_task
if cycles > limit:
    return DENY("MAX_WRITE_CYCLES_EXCEEDED")
```

**Иерархия правил:**

```text
Axioms (hardcoded в Guards, code-enforced, ABORT):
  NO_EXPLAIN_BEFORE_WRITE, GRAPH_FINGERPRINT, NO_GRAPH_BEFORE_EXPLAIN
  → не читаются из PolicyProjection, не меняются через PolicyKernel

Structural (guard-enforced, RETRY/HUMAN_GATE):
  GL-6 Write Gate → частично hardcoded, частично config

Behavioral (policy-managed, в PolicyProjection):
  retry_limit, scope permissions, max_write_cycles_per_task,
  step_budget, retry_budget, re_explain_budget, phase_write_allowed,
  gate_freeze_ttl_hours
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
- [[agent-loop]] — основной потребитель loop-specific policy keys
- [[loop-policy]] — справочник loop-specific ключей и их defaults
