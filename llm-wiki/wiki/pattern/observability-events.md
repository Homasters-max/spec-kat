---
created: '2026-05-06'
domain: sdd
id: pattern/observability-events
layer: architecture
page_type: pattern
sdd_domain: Core
sdd_layer: L0
sources:
- raw/SDD_Bounded_Contexts_Plan.md
tags:
- enforcement
- write-path
- ssot
- automation
- domain/sdd
- sdd/l0
- sdd/core
updated: '2026-05-06'
version: 1
---
# Observability Events

Закрытая категория событий, производимых L1 Runtime напрямую — в обход WriteKernel — для фиксации FSM-переходов AgentLoop без мутации domain state.

Отличие от Domain Events:

| Аспект | Domain Events | Observability Events |
|--------|--------------|----------------------|
| Производитель | CommandHandler | L1 Runtime (AgentLoop) |
| Путь записи | WriteKernel + OCC | EventStoreGuard (прямо) |
| Мутирует проекции | Да (ProjectionRegistry.sync()) | Нет |
| Reducer | Обрабатывает | Игнорирует |
| Whitelist | Нет | Да, закрытый |

## How It Works

Закрытый список (добавление требует явного протокольного решения, не inline в код):

- `LoopStepRecorded` — фиксация FSM-перехода AgentLoop (один per FSM transition, не per LLM call)
- `HumanGateReached` — AgentLoop достиг точки, требующей human input
- `ErrorEvent` — L1 Runtime сигнализирует об ошибке

Путь записи:

```text
L1 Runtime
  → EventStoreGuard.validate_observability(event)
      ├─ Level 1: call-stack check (вызов из L1 Runtime module)
      └─ whitelist check (event_type ∈ {LoopStepRecorded, HumanGateReached, ErrorEvent})
  → EventLog.append(event)   ← без WriteKernel
  → НЕ вызывает ProjectionRegistry.sync()
```

Порядок в EventLog (I-OBS-5): Domain Event THEN Observability Event в рамках одного шага. Enforced через append order в `WriteKernel.execute_and_project()`. Гарантирует идентичный trace при replay.

**Уточнение GL-7**: "event_store.append() только из Command handlers" — применяется к Domain Events. Observability Events — легальное исключение, медиируемое [[eventstore-guard]].

**Уточнение I-BC-1**: "Runtime MUST NOT mutate EventStore directly" — "напрямую" = в обход EventStoreGuard. Observability Events идут через EventStoreGuard → I-BC-1 не нарушается.

## Invariants

- **I-OBS-1**: Observability Events MUST NOT appear in Reducer's event-to-state map; projections MUST ignore them
- **I-OBS-2**: The list of Observability Events is closed (exhaustive); adding new ones requires explicit protocol decision
- **I-OBS-3**: EventStoreGuard MUST validate Observability Event origin (call-stack: L1 Runtime module) AND event type (whitelist)
- **I-OBS-4**: Observability Events do NOT trigger ProjectionRegistry.sync()
- **I-OBS-5**: Ordering: Domain Event THEN Observability Event within same step; enforced by append order
- **I-EVENT-GRAIN-2**: Observability Events represent AgentLoop FSM transitions, not computation steps. One per FSM transition, not one per LLM call or tool invocation.

## When To Use

Когда L1 Runtime нужно зафиксировать переход состояния AgentLoop (FSM transition), ошибку или достижение human gate, не изменяя domain state. Не использовать для промежуточных вычислительных шагов.

## Trade-offs

- Закрытый whitelist предотвращает EventLog explosion и нарушения I-OBS-1, но требует протокольного решения для добавления новых типов.
- Ordering guarantee (I-OBS-5) делает replay детерминированным и предотвращает расхождение trace.

## See Also

- [[eventstore-guard]] — реализует двухуровневый enforcement
- [[sdd-bounded-contexts]] — context: разрешение конфликта GL-7 / AgentLoop / I-BC-1
- [[global-laws]] — GL-7 применяется к Domain Events; Observability Events — исключение
- [[event-sourcing]]
- [[agent-loop]]
