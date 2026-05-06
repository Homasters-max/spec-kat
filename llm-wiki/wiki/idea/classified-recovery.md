---
id: idea/classified-recovery
page_type: idea
domain: sdd
layer: architecture
tags:
- enforcement
- pipeline
- validation
- automation
- domain/sdd
version: 3
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/error-model-architecture.md
---
# Classified Recovery

> **Deprecated.** Концепция поглощена [[error-registry]] + [[error-event]] (Unified Error Model, 2026-05-05). `ErrorClassified` event упразднён; audit переносится в расширенный `LoopStepRecorded`. Эта страница сохранена как исторический контекст.

Стратегия обработки ошибок в SDD: разные типы ошибок → разные стратегии восстановления.

## Summary

Вместо единого "hard stop" или "бесконечный retry" — детерминированная классификация каждой ошибки в одну из четырёх стратегий. Реализуется через [[error-classifier]] в L1, опираясь на [[error-registry]] как единственный источник severity/layer.

## How It Works (историческое)

```text
RETRY         → протокольные нарушения, которые агент должен исправить сам
RE_EXPLAIN    → граф изменился после explain
HUMAN_GATE    → превышение budget, scope violations
ABORT         → CORE_ABORT (structural) или PROTOCOL_ABORT (policy/guard/unknown)
```

В актуальной архитектуре классификация возвращает [[classification-result]] (не голую `RecoveryStrategy`), а `ErrorClassified` event заменён на поля в `LoopStepRecorded`.

## Trade-offs

- RETRY без лимита → агент застрянет. Budget через `retry_budget` в PolicyProjection.
- HUMAN_GATE для всего → human overload. Только scope violations и budget exhaustion.

## Open Questions

- [ ] (P0) Q30 PARTIAL: Как восстановиться после process crash? EventLog цел, но in-flight команда потеряна. Автоматическое обнаружение незавершённых сессий?
- [ ] (P0) Q31 PARTIAL: Как обнаружить desync между EventLog и State_index? Checksumming projections? Periodic verify?
- [ ] (P0) Q32: Команда всегда падает. Circuit breaker? DLQ? Как изолировать от влияния на другие команды?
- [ ] (P0) Q33: Где задаются timeouts для handler execution? Кто их enforces? Что если handler завис?

## Decisions

- [x] (P0) Q27: Error classification — RETRY/RE_EXPLAIN/HUMAN_GATE/ABORT → [[error-classifier]]
- [x] (P0) Q28: Error events — все ошибки пишутся как ErrorEvent → [[error-event]]
- [x] (P0) Q29: Human intervention trigger — GATE outcome → [[session-orchestrator]]

## See Also

- [[error-registry]]
- [[error-event]]
- [[error-classifier]]
- [[classification-result]]
- [[session-orchestrator]]
