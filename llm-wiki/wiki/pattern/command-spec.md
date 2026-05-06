---
created: '2026-05-05'
domain: sdd
id: pattern/command-spec
layer: architecture
page_type: pattern
sdd_domain: Core
sdd_layer: L0
sources:
- raw/commandspec-deepening-plan.md
tags:
- cli
- ssot
- write-path
- automation
- domain/sdd
- sdd/l0
- sdd/core
updated: '2026-05-06'
version: 2
---
# CommandSpec

Типизированный дескриптор команды в [[command-bus]]. Заменяет три разрозненных boolean-флага (`affects_trace`, `graph_structural`, `idempotent`) на три typed enum-поля, которые инфраструктурный слой (L0/L1) использует для маршрутизации, кэширования и трассировки.

## How It Works

```python
@dataclass(frozen=True)
class CommandSpec:
    command_name:  str
    command_type:  Type[Command]
    trace_scope:   TraceScope      # TASK_SCOPED | NONE
    graph_impact:  GraphImpact     # STRUCTURAL | NONE
    dedup:         IdempotencyMode # EXACT | NONE
```

**[[trace-scope]]** определяет, записывается ли команда в trace текущего task:
- `TASK_SCOPED` — шаг попадает в [[trace-projection]] (resolve, explain, write)
- `NONE` — команда не затрагивает trace (activate-phase, complete, record-session)

**[[graph-impact]]** определяет, изменяет ли команда структуру графа через EventLog:
- `STRUCTURAL` — событие меняет граф (activate-phase, complete, define-invariant, update-policy, bootstrap-policy)
- `NONE` — команда не влияет на структуру графа (resolve, explain, record-session, switch-phase, write)

**[[idempotency-mode]]** определяет стратегию дедупликации в [[idempotency-middleware]]:
- `EXACT` — дублирующийся вызов возвращает кэшированный результат
- `NONE` — каждый вызов порождает новое событие

**God Object Guard:** В CommandSpec попадают ONLY enum-ы, используемые инфраструктурным слоем (L0/L1) для маршрутизации. Компонент-специфичная логика запрещена — она принадлежит конкретному компоненту (например, `CONTEXT_EVENT_TYPES` в [[task-event-slice]], а не флаг в CommandSpec).

**Routing через CommandRegistry:**

```python
# TraceProjection фильтрует только нужные команды:
trace_commands = registry.filter(lambda s: s.trace_scope == TraceScope.TASK_SCOPED)

# GraphQueryEngine определяет структурные события:
structural_specs = registry.filter(lambda s: s.graph_impact == GraphImpact.STRUCTURAL)
```

## When To Use

При добавлении новой команды в SDD: создать `CommandSpec` с тремя enum-полями. Инфраструктурные компоненты (TraceProjection, GraphQueryEngine, IdempotencyMiddleware) автоматически получают корректное поведение через запрос к CommandRegistry — без ручной синхронизации флагов.

## Trade-offs

**Плюсы:** единственная точка декларации маршрутизационного контракта; добавить команду = один файл; compile-time safety вместо runtime boolean-drift; [[command-bus]] и его middleware не знают о деталях отдельных команд.

**Минусы:** добавление нового routing-concern требует нового enum и изменения CommandSpec; нельзя выразить неоднородные эффекты одной команды (Command→Event 1:many — именно поэтому context_boundary не вошёл в CommandSpec).

## Open Questions

- [ ] (P1) Q104: Где валидируется command schema — до guards (middleware) или внутри handler? Кто отвечает за well-formedness input?
- [ ] (P1) Q106: Формально гарантируется: одинаковый input command + одинаковый State → одинаковые output events? Где доказательство?

## See Also

- [[trace-scope]] — enum для трассировки
- [[graph-impact]] — enum для кэша GraphQueryEngine
- [[idempotency-mode]] — enum для дедупликации
- [[command-bus]] — использует CommandSpec через CommandRegistry
- [[middleware-pipeline]] — middleware фильтруют команды по полям CommandSpec
- [[task-event-slice]] — пример того, что НЕ входит в CommandSpec
