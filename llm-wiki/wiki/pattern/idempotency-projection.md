---
id: pattern/idempotency-projection
page_type: pattern
domain: sdd
layer: architecture
tags:
- dedup
- write-path
- ssot
- validation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/CommandBus — Idempotency, Dedup, Middleware Pipeline.md
---
# IdempotencyProjection

L1-проекция: PostgreSQL-таблица для хранения кеша успешных `CommandResult` по `idempotency_key`. Используется [[idempotency-middleware]].

## Summary

Не регистрируется в `ProjectionRegistry` — это операционный кеш, а не read-model. Запись происходит **вне EventLog-транзакции**, после успешного `commit` через `INSERT ... ON CONFLICT DO NOTHING`. Семантика хранения: **at-least-once**.

## How It Works

### Схема

```sql
CREATE TABLE command_idempotency (
    idempotency_key UUID        PRIMARY KEY,
    result_json     JSONB       NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

### Интерфейс

```python
class IdempotencyProjection:
    def lookup(self, key: UUID) -> CommandResult | None:
        row = db.fetchone(
            "SELECT result_json FROM command_idempotency WHERE idempotency_key = $1",
            key
        )
        return CommandResult.from_json(row["result_json"]) if row else None

    def store(self, key: UUID, result: CommandResult) -> None:
        db.execute(
            "INSERT INTO command_idempotency(idempotency_key, result_json)"
            " VALUES ($1, $2) ON CONFLICT DO NOTHING",
            key, result.to_json()
        )
```

**`ON CONFLICT DO NOTHING`** — гарантирует идемпотентность самой записи.

### Позиция в pipeline

Пишется из `IdempotencyMiddleware` **после** успешного `next(cmd)` — т.е. после того как WriteKernel зафиксировал событие в EventLog. Это означает малое окно гонки: если процесс упал между commit и store — retry пройдёт повторно (at-least-once, не exactly-once на уровне EventLog).

## When To Use

Как read-side кеш для [[idempotency-middleware]]. Не подходит для хранения бизнес-данных или событий — только для дедупликации результатов команд.

## Trade-offs

- Не является частью EventLog и не участвует в replay — это чисто операционный кеш.
- At-least-once: потеря записи = допустимый retry, не corruption.
- При очистке таблицы retry проходят повторно (безопасно, EventLog остаётся SSOT).

## See Also

- [[idempotency-middleware]]
- [[middleware-pipeline]]
- [[projection-registry]]
- [[eventstore-guard]]
