---
page_type: idea
domain: sdd
layer: architecture
sdd_layer: null
sdd_domain: null
tags:
- sdd/intelligence
- validation
- domain/sdd
updated: '2026-05-06'
sources: []
---
# SDD Domain — Intelligence

## Summary

Intelligence-домен владеет анализом: metrics, proposals, audit, embeddings. Только читает state через проекции, никогда не пишет напрямую в EventLog. Eventual consistency допустима. Proposals — это предложения, не команды.

## Назначение и границы

Intelligence отвечает за **рефлексию над системой**: что пошло не так, как улучшить процесс, какие паттерны аномальны. Intelligence не знает, как исполнять (Engine) и не управляет планированием (Blueprint).

Владеет: audit trail analysis, metric aggregation, scenario generation, semantic search.

Не владеет: write path (Core), планированием (Blueprint), исполнением (Engine).

## L2 Intelligence компоненты

- [[audit-engine]] — аудит событий на соответствие инвариантам; выдаёт report, не команды
- [[meta-optimization]] — предложения по улучшению процесса на основе исторических данных
- [[scenario-gen]] — генерация adversarial-сценариев для стресс-тестирования системы
- [[embedding-projection]] — семантические эмбеддинги страниц wiki для навигации LLM

## Контракт read-only

Все L2-компоненты Intelligence обязаны:
1. Читать state только через read-projections.
2. Возвращать proposals/reports, но не применять изменения самостоятельно.
3. Не хранить mutable state между запросами.

## Антипаттерны

- Intelligence компонент эмитит события напрямую → нарушение L2-изоляции.
- AuditEngine останавливает pipeline вместо репортинга → нарушение read-only контракта.
- MetaOptimization применяет предложения без human review.

## See Also

- [[sdd-vertical-slice]]
- [[sdd-domain-core]]
- [[sdd-layer-l2]]
- [[l1-l2-isolation]]
