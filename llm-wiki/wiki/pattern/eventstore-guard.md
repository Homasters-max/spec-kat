---
id: pattern/eventstore-guard
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- write-path
- ssot
- validation
- domain/sdd
version: 3
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# EventStore Guard

L0-компонент: физически запрещает `event_store.append()` в обход Command handlers (I-CMD-ONLY-1, GL-7).

## How It Works

Проблема: ничто не мешает коду вызвать `event_store.append()` напрямую, минуя CommandBus → Guards → Handler pipeline. EventStore Guard закрывает эту дыру.

```python
class EventStoreGuard:
    _allowed_callers = {"CommandHandler"}

    def check_caller(self, frame: FrameInfo) -> None:
        caller = frame.f_locals.get("__class__", None)
        if caller.__name__ not in self._allowed_callers:
            raise DirectEventStoreAccessError(
                f"event_store.append() called outside handler: {caller}"
            )
```

**Механизм**: `EventStore.append()` содержит call-stack check при каждом вызове. Прямой вызов вне `CommandHandler` → `DirectEventStoreAccessError` → `ErrorEvent` → ABORT.

**Альтернативный механизм**: Python module-level `__all__` + import restrictions — но call-stack check надёжнее т.к. работает в runtime.

**Тест:** `test_direct_eventstore_access` проверяет что вызов вне handler поднимает ошибку.


## Level 2: Domain-Origin Check

**[proposed]** Поверх call-stack check (Level 1) — проверка domain ownership события.

```text
Механика Level 2:
  1. Из executing CommandContext получаем command_type
  2. CommandRegistry.lookup(command_type) → domain
  3. Appended event.domain MUST == lookup result
  4. Нарушение → DomainOriginViolation → ErrorEvent → ABORT
```

- **I-GUARD-DOMAIN-1**: EventStoreGuard Level 2 MUST use CommandRegistry (not inline domain map) as single source of command→domain mapping

## Observability Events

[[observability-events]] (LoopStepRecorded, HumanGateReached, ErrorEvent) проходят через EventStoreGuard иначе:

```text
Level 1: call-stack check (вызов из L1 Runtime module) + event_type в whitelist
Level 2: не применяется (Observability Events не domain-scoped)
EventStoreGuard.validate_observability(event) проверяет: whitelist + call-stack origin
```

Ordering guarantee (I-OBS-5): Domain Event THEN Observability Event в рамках одного step. Enforced через append order в WriteKernel.execute_and_project().

- **I-GUARD-OBS-1**: Observability Events bypass domain-origin check but MUST pass origin whitelist check

## When To Use

Всегда активен — прозрачный guard на `EventStore.append()`. Не требует явного вызова.

## Trade-offs

- Call-stack inspection = небольшой overhead на каждый append.
- В тестах нужно использовать CommandHandler wrapper, не вызывать append напрямую.

## Open Questions

- [ ] (P0) Q40: Как гарантируется durability EventLog? Есть ли fsync/fdatasync после каждого append или полагаемся на PostgreSQL WAL?
- [ ] (P0) Q41: Есть ли checksums на уровне каждого события (payload integrity)? Как обнаружить silent data corruption?
- [ ] (P0) Q42: Как обнаружить corruption на уровне storage? Периодический re-hash всех событий EventLog?
- [ ] (P0) Q43: Есть ли двойная запись (WAL + EventLog) или EventLog IS the WAL? Что если они расходятся?
- [ ] (P0) Q44: Как делается backup EventLog без потери порядка events? Гарантируется ли сохранение event_index sequence?
- [ ] (P0) Q45: Поддерживается ли восстановление к конкретному event_index? Что нужно кроме EventLog?
- [ ] (P0) Q46: Как тестируется: backup → restore → full replay → State == original State? Автоматически в CI?
- [ ] (P0) Q47: Что происходит при partial write (OS crash mid-row-append)? Достаточна ли PostgreSQL транзакционность?
- [ ] (P0) Q48: JSON, MessagePack или Protobuf для canonical event format? Критерии и текущий выбор?
- [ ] (P0) Q49: Как гарантируется deterministic key ordering в JSON? sorted_keys? custom encoder?
- [ ] (P0) Q50: Есть ли schema_version или schema_hash в каждом событии для обнаружения schema drift?
- [ ] (P0) Q51: Как обрабатываются отсутствующие поля при replay новым reducer? Default values? Strict validation?
- [ ] (P0) Q52: Есть ли canonical hash для State snapshot и ContextPacket для integrity verification?
- [ ] (P0) Q53: Можно ли получить bit-identical dump всего состояния для cross-environment comparison?
- [ ] (P0) Q54: Как избежать расхождения если разные версии кода читают одни события? Serializer compatibility matrix?

## See Also

- [[event-sourcing]]
- [[command-bus]]
- [[global-laws]]
- [[sdd-component-inventory]]
- [[observability-events]]
- [[sdd-bounded-contexts]]
