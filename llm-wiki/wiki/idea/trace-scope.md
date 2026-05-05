---
id: idea/trace-scope
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
# TraceScope

Enum-поле [[command-spec]], определяющее включение команды в trace текущего TaskRun. Заменяет boolean-флаг `affects_trace: bool` типизированной константой, устраняя ручную синхронизацию с [[trace-projection]].

## How It Works

```python
class TraceScope(Enum):
    TASK_SCOPED = "TASK_SCOPED"  # шаг записывается в trace текущего task
    NONE        = "NONE"         # команда не затрагивает trace
```

**Routing:** [[trace-projection]] подписывается через CommandRegistry только на команды с `trace_scope == TASK_SCOPED` — фильтр перемещается из ручного флага в типизированный запрос.

**Почему не INHERIT:** В SDD нет иерархии команд. CommandBus диспатчит независимые команды без parent-контекста. INHERIT — несуществующий концепт в этой модели.

**Примеры значений:**

| Значение | Примеры команд |
|----------|---------------|
| `TASK_SCOPED` | resolve, explain, write |
| `NONE` | activate-phase, complete, record-session, switch-phase |

## When To Use

Декларируется в [[command-spec]] при регистрации команды. Если команда является шагом агента (resolve/explain/write), она должна попасть в trace — `TASK_SCOPED`. Если команда инфраструктурная — `NONE`.

## Trade-offs

Два значения достаточны для текущей модели. Расширение потребует нового значения enum и явного решения по routing в TraceProjection.

## See Also

- [[command-spec]] — содержит TraceScope как поле
- [[trace-projection]] — фильтрует по TraceScope
