---
page_type: idea
domain: sdd
layer: architecture
sdd_layer: null
sdd_domain: null
tags:
- sdd/l2
- validation
- automation
- domain/sdd
updated: '2026-05-06'
sources: []
---
# SDD Layer L2 — Intelligence

## Summary

L2 анализирует, предлагает, оптимизирует. Eventual consistency — L2-компоненты читают state из проекций, но НИКОГДА не мутируют state напрямую. Все изменения передаются через команды в L1/L0.

## Ключевые компоненты L2

**Blueprint:**
- [[spec-manager]] — управление lifecycle спецификаций; анализирует draft vs approved
- [[plan-manager]] — генерация и валидация планов фаз
- [[phase-orchestrator]] — DoD-проверка, переходы между фазами
- [[constitution-parser]] — парсинг и валидация CLAUDE.md / norm_catalog.yaml

**Intelligence:**
- [[audit-engine]] — аудит событий на соответствие инвариантам
- [[meta-optimization]] — предложения по улучшению процесса
- [[scenario-gen]] — генерация adversarial-сценариев для тестирования
- [[embedding-projection]] — семантические эмбеддинги для навигации по wiki

## Ключевые инварианты

- L2 НИКОГДА не вызывает EventStore.append напрямую.
- L2 НИКОГДА не вызывает rebuild_state или sync_projections.
- L2 читает state только через read-projections (eventual consistency допустима).
- Proposals от L2 — не команды; они только предлагают, не применяют.

## Антипаттерны

- L2 компонент эмитит события напрямую → нарушение изоляции.
- L2 хранит mutable state между запросами → нарушение replay-safety.
- L2 компонент зависит от L1 (допустимо только read-only через projection).

## See Also

- [[sdd-layer-l1]]
- [[sdd-horizontal-slice]]
- [[l1-l2-isolation]]
- [[sdd-domain-intelligence]]
- [[sdd-domain-blueprint]]
