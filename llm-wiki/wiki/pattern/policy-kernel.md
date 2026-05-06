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
version: 3
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# PolicyKernel

**L1-компонент, Blueprint-домен**: governance rules через EventLog. `PolicyUpdated` events. `norm_catalog.yaml` → EventLog.

Применяет governance rules в runtime — это execution, не decision. [[meta-optimization]] (L2, Intelligence) *генерирует* proposal на изменение policy — это разные компоненты с разными интерфейсами.

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

## Open Questions

- [ ] (P2) Q149: Role = set[Permissions]. Уровни: project:read, spec:write, phase:approve, policy:update. Где задаётся — PolicyKernel или hardcoded?
- [ ] (P2) Q150: Откуда берётся actor_id и role при старте AgentLoop? JWT? Конфиг? EventLog?
- [ ] (P2) Q151: Что входит в constitution.md? Tech stack, linter rules, архитектурные принципы. Как попадает в ContextKernel?
- [ ] (P2) Q152: Как ContextKernel экранирует файлы от prompt injection? Sanitization strategy?
- [ ] (P2) Q153: Как credentials (DB passwords, API keys) передаются агенту? Никогда в EventLog?
- [ ] (P2) Q197: Какие параметры configurable в runtime (через PolicyKernel), а какие требуют rebuild/restart?
- [ ] (P2) Q198: Как изменение конфига влияет на детерминизм EventLog replay? Конфиг — часть reproducible environment?
- [ ] (P2) Q199: Записывается ли config state как событие при изменении (ConfigUpdated)? Как гарантировать reproducibility?
- [ ] (P2) Q200: Можно ли replay старого EventLog с новой конфигурацией? Ожидаемый результат — тот же или undefined behavior?
- [ ] (P2) Q201: Где граница между системным конфигом (.yaml) и policy (PolicyKernel EventLog-events)?
- [ ] (P2) Q202: Как откатить конфигурацию к предыдущей версии? Git revert достаточен или нужен ConfigRolledBack event?
- [ ] (P2) Q209: Можно ли подделать event_id или command_id? Нужна ли cryptographic signing?
- [ ] (P2) Q210: Есть ли подпись событий (HMAC/Ed25519 на payload)? Как проверяется при replay и backup restore?
- [ ] (P2) Q211: Как защититься от прямой INSERT в EventLog в обход системы? Row-level security?
- [ ] (P2) Q212: Кто имеет физический write-доступ к EventLog DB? Минимальные привилегии service account?
- [ ] (P2) Q213: Есть ли audit trail на уровне DB — кто и когда SELECT/INSERT к EventLog таблицам? pg_audit?
- [ ] (P2) Q214: Как обнаружить прямой доступ в обход системы? DB triggers на direct insert? Anomaly detection?

## See Also

- [[error-classifier]]
- [[meta-optimization]]
- [[sdd-actor-model]]
- [[scope-guard]]
- [[event-sourcing]]
