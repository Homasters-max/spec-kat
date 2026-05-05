---
id: idea/graph-impact
page_type: idea
domain: sdd
layer: architecture
tags:
- ssot
- automation
- pipeline
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/commandspec-deepening-plan.md
---
# GraphImpact

Enum-поле [[command-spec]], определяющее влияние команды на структуру зависимостного графа через EventLog. Заменяет boolean-флаг `graph_structural: bool` и отделяет EventLog-канал инвалидации кэша от FS-канала (`code_hash`).

## How It Works

```python
class GraphImpact(Enum):
    STRUCTURAL = "STRUCTURAL"  # команда порождает событие, меняющее граф
    NONE       = "NONE"        # команда не влияет на граф через EventLog
```

**Два независимых канала инвалидации кэша GraphQueryEngine:**

```
cache_fingerprint = hash(code_hash + max_structural_event_offset)
```

- `max_structural_event_offset` — вычисляется из EventLog по командам с `graph_impact == STRUCTURAL`
- `code_hash` — вычисляется из файловой системы при каждом cache miss, **независимо от командного флага**

`CODE_HASH` не входит в GraphImpact: изменение `code_hash` — побочный эффект записи в FS, это всегда верно для `write` и не является routing decision. GraphQueryEngine пересчитывает `code_hash` при cache miss независимо от команды.

**Примеры значений:**

| Значение | Примеры команд |
|----------|---------------|
| `STRUCTURAL` | activate-phase, complete, define-invariant, update-policy, bootstrap-policy |
| `NONE` | resolve, explain, record-session, switch-phase, write |

## When To Use

Декларируется в [[command-spec]]. Команды, порождающие события, которые меняют структуру зависимостного графа (задачи завершены, фазы активированы, инварианты определены) — `STRUCTURAL`. Навигационные и read-like команды — `NONE`.

## Trade-offs

Разделение каналов инвалидации (EventLog vs FS) — ключевое архитектурное решение: смешение их через единый флаг создаёт ложную зависимость и усложняет reasoning о кэше.

## See Also

- [[command-spec]] — содержит GraphImpact как поле
- [[graph-structural-offset]] — использует STRUCTURAL команды для вычисления offset
