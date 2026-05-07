---
id: idea/idempotency-mode
page_type: idea
domain: sdd
layer: architecture
tags:
- dedup
- write-path
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/commandspec-deepening-plan.md
---
# IdempotencyMode

Enum-поле [[command-spec]], определяющее стратегию дедупликации в [[idempotency-middleware]]. Заменяет boolean-флаг `idempotent: bool` типизированной константой.

## How It Works

```python
class IdempotencyMode(Enum):
    EXACT = "EXACT"  # дублирующийся вызов возвращает кэшированный результат
    NONE  = "NONE"   # каждый вызов порождает новое событие
```

**EXACT:** IdempotencyMiddleware выполняет lookup по `command_id`. При совпадении — short-circuit, возврат сохранённого результата без повторного вызова WriteKernel.

**NONE:** команда не дедуплицируется; `CommandSpec.idempotent=False` → `execute_command` передаёт `command_id=uuid4()` (не None) в EventStore.append. Каждый вызов порождает уникальное событие (I-CMD-IDEM-1).

## When To Use

`EXACT` — для команд, где повторный вызов с теми же параметрами должен дать идентичный результат без side effects. `NONE` — для навигационных и state-changing команд, где каждый вызов семантически уникален.

## Trade-offs

`EXACT` предполагает стабильный `command_id` на стороне клиента. Если клиент генерирует новый UUID при каждом retry — дедупликация не сработает.

## See Also

- [[command-spec]] — содержит IdempotencyMode как поле
- [[idempotency-middleware]] — реализует lookup и short-circuit по IdempotencyMode
- [[command-bus]] — диспатчит команды через middleware pipeline
