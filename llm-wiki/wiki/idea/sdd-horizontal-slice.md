---
page_type: idea
domain: sdd
layer: architecture
sdd_layer: null
sdd_domain: null
tags:
- bounded-contexts
- navigation
- domain/sdd
updated: '2026-05-06'
sources:
- raw/sdd-wiki-navigation-slices-plan.md
version: 1
---
# SDD Horizontal Slice

## Summary

Горизонтальный разрез SDD-архитектуры делит систему на три уровня зрелости исполнения: L0 (физика), L1 (исполнение), L2 (интеллект). Каждый уровень строго зависит только от нижестоящих — L2 никогда не пишет напрямую в EventLog.

## Уровни

**L0 — Core Physics.** Определяет физику системы: EventLog, WriteKernel, CommandBus, Guards, ProjectionRegistry. Полностью детерминирован, нет зависимости от L1/L2. Любой write-путь проходит через L0. См. [[sdd-layer-l0]].

**L1 — Execution.** Исполняет задачи детерминированно через L0-примитивы. Ephemeral, replay-safe, session-scoped. SessionOrchestrator, ScopeGuard, ContextKernel живут здесь. См. [[sdd-layer-l1]].

**L2 — Intelligence.** Анализирует, предлагает, оптимизирует. Eventual consistency. Не мутирует state напрямую — только через L1/L0 команды. См. [[sdd-layer-l2]].

## SDDNAV-1 — Алгоритм навигации для LLM

Пять шагов для ориентирования в SDD при работе с незнакомым компонентом:

1. **Определи слой** — это L0 (физика), L1 (исполнение) или L2 (анализ)? Подсказка: мутирует ли компонент EventLog напрямую → L0; исполняет задачи → L1; анализирует/предлагает → L2.
2. **Определи домен** — Core, Blueprint, Engine или Intelligence? [[sdd-component-inventory]] — авторитетный источник.
3. **Найди derived view** — `derived/views/by-sdd-layer.md` для слоя, `derived/views/by-sdd-domain.md` для домена.
4. **Найди связанные страницы** — через wikilinks в странице компонента и через [[sdd-bounded-contexts]].
5. **Проверь инварианты** — CLAUDE.md §INV и соответствующие I-* инварианты для домена.

## Антипаттерны

- L2 компонент напрямую вызывает EventStore → нарушение изоляции слоёв.
- L1 компонент зависит от L2 (обратная зависимость) → нарушение I-L1-L2-ISOLATION-1.
- Компонент без sdd_layer в frontmatter → LLM navigates blind.

## See Also

- [[sdd-vertical-slice]]
- [[sdd-layer-l0]]
- [[sdd-layer-l1]]
- [[sdd-layer-l2]]
- [[sdd-bounded-contexts]]
- [[sdd-component-inventory]]
