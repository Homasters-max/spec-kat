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
sources: []
---
# SDD Vertical Slice

## Summary

Вертикальный разрез SDD-архитектуры делит систему на четыре функциональных домена: Core, Blueprint, Engine, Intelligence. Каждый домен владеет своей частью state и имеет чётко ограниченные ответственности.

## Домены

**Core** — владеет инфраструктурой: EventLog, write path, projections, идемпотентность. Фундамент, на котором стоит всё остальное. См. [[sdd-domain-core]].

**Blueprint** — владеет проектной моделью: specs, plans, phases, policy. Строгая последовательность фаз через FSM. См. [[sdd-domain-blueprint]].

**Engine** — владеет runtime исполнения: AgentLoop, execution context, task scheduling. Оркестрирует LLM-агента через [[agent-loop]]. См. [[sdd-domain-engine]].

**Intelligence** — владеет анализом: metrics, proposals, audit, embeddings. Только читает state, никогда не пишет напрямую. См. [[sdd-domain-intelligence]].

## Границы между доменами

Взаимодействие между доменами — только через события в EventLog или через явные команды. Прямые вызовы между доменами запрещены. Blueprint не импортирует Engine; Intelligence не импортирует Core напрямую — только через read-projections.

## Антипаттерны

- Blueprint-компонент напрямую вызывает Engine runtime → coupling через командную шину.
- Intelligence пишет в EventLog напрямую → нарушение read-only контракта L2.
- Компонент без sdd_domain в frontmatter → принадлежность домену неочевидна.

## See Also

- [[sdd-horizontal-slice]]
- [[sdd-domain-core]]
- [[sdd-domain-blueprint]]
- [[sdd-domain-engine]]
- [[sdd-domain-intelligence]]
- [[sdd-bounded-contexts]]
