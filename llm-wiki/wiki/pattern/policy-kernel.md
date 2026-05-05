---
id: pattern/policy-kernel
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- ssot
- write-path
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# PolicyKernel

L2-компонент: governance rules через EventLog. `PolicyUpdated` events. `norm_catalog.yaml` → EventLog.

## How It Works

Правила governance (scope permissions, actor permissions, mutation guards) хранятся не в файлах, а в EventLog как `PolicyUpdated` events.

```python
@dataclass
class PolicyUpdated:
    policy_id: str
    rule_type: str          # "scope" | "actor" | "mutation" | "retry_limit"
    rule_definition: dict
    approved_by: str        # human actor ID
    previous_version: str   # для audit trail
```

**Lifecycle изменения правила:**

```text
1. MetaOptimization генерирует proposal
2. Human review (HUMAN_GATE)
3. Human approves → PolicyUpdated event в EventLog
4. ProjectionRegistry.sync() → policy_rules table обновляется
5. L0/L1 guards читают через ReadModel → новое правило активно
```

**Bootstrapping:** `norm_catalog.yaml` → при init читается и конвертируется в `PolicyUpdated` events. После этого YAML — только backup, EventLog — SSOT.

**L0 ядро** (ключевые инварианты типа "Reducer must be pure") остаётся code-enforced и не подлежит declarative override.

## When To Use

Когда нужно изменить governance правило без code change: лимиты retry, scope permissions, actor permissions. Любое изменение требует human approval.

## Trade-offs

- Изменение правила = event в EventLog = полный audit trail с кем/когда изменил.
- Нет изменения правил без human approval — intentional design, не ограничение.
- L0 ядро не переопределяется через PolicyKernel — это намеренно.

## See Also

- [[error-classifier]]
- [[meta-optimization]]
- [[sdd-actor-model]]
- [[scope-guard]]
- [[event-sourcing]]
