---
id: idea/causal-linkage
page_type: idea
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- ssot
- write-path
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
---
# Causal Linkage

Три поля Event для полной трассируемости: `command_id` (provenance), `causation_event_id` (event DAG), `correlation_id` (flow grouping). Реконструкция истории сессии без внешних индексов.

## How It Works

```python
@dataclass(frozen=True)
class Event:
    event_id:           UUID      # uuid5(command_id:position) — детерминирован
    command_id:         UUID      # provenance: какая команда породила событие
    causation_event_id: UUID | None  # event DAG: предыдущее событие (None если первое)
    correlation_id:     UUID      # flow grouping: неизменен по всей сессии
    sequence_no:        int
    occurred_at:        datetime
    payload:            dict
```

**Семантика полей:**

| Поле | Вопрос | Задаётся |
|------|--------|---------|
| `command_id` | Какая команда создала событие? | CommandContext |
| `causation_event_id` | Из какого события выросло следующее? | WriteKernel (event DAG) |
| `correlation_id` | К какой сессии принадлежит? | SessionOrchestrator (один id на сессию) |

**`correlation_id` lifecycle:**

```python
# SessionOrchestrator при старте сессии:
correlation_id = uuid4()  # один id на всю сессию

# CommandContext несёт его через весь pipeline:
ctx = CommandContext(actor=..., session_id=..., task_id=..., correlation_id=correlation_id)

# WriteKernel копирует в каждый Event:
event.correlation_id = ctx.correlation_id
```

**Реконструкция истории сессии:**

```sql
SELECT * FROM event_log
WHERE correlation_id = 'X'
ORDER BY sequence_no;
```

**Event DAG через causation_event_id:**

```text
Event A (causation=None) → Event B (causation=A.event_id) → Event C (causation=B.event_id)
```

## When To Use

Применяется в [[event-sourcing]] для: аудитабельности, debugging causal chains, реконструкции контекста сессии. Поля обязательны для всех Event в EventStore.

## Trade-offs

- `causation_event_id` строит DAG событий, не линейный лог — сложнее для анализа при ветвлении
- `correlation_id` охватывает сессию целиком — нужен дополнительный индекс в PostgreSQL
- `command_id` дублирует информацию о команде, но устраняет JOIN с таблицей команд

## See Also

- [[event-sourcing]]
- [[cqrs-boundary]]
- [[write-kernel]]
- [[sdd-actor-model]]
