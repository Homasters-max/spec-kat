---
page_type: idea
domain: sdd
layer: architecture
sdd_layer: null
sdd_domain: null
tags:
- sdd/core
- ssot
- write-path
- domain/sdd
updated: '2026-05-06'
sources: []
---
# SDD Domain — Core

## Summary

Core-домен владеет инфраструктурой SDD: EventLog, write path, projections, идемпотентность. Это фундамент всей системы — Blueprint, Engine и Intelligence опираются на Core, но не наоборот.

## Назначение и границы

Core отвечает за **гарантии сохранности данных**: каждое событие записывается ровно один раз, в правильном порядке, с проверкой всех guard-условий. Core не знает о бизнес-логике — только о надёжности хранения и воспроизведения.

Владеет: EventLog, WriteKernel, CommandBus, Guards, ProjectionRegistry, UpcasterRegistry, Reducer.

Не владеет: бизнес-правилами (Blueprint), runtime исполнения (Engine), аналитикой (Intelligence).

## L0 Core компоненты

[[event-sourcing]], [[write-kernel]], [[command-bus]], [[command-spec]], [[command-context]], [[eventstore-guard]], [[projection-registry]], [[upcaster-registry]], [[reducer]], [[error-event]], [[global-laws]], [[cqrs-boundary]], [[optimistic-concurrency-control]], [[observability-events]], [[replay-engine]]

## L1 Core компоненты

[[execution-guard]], [[scope-guard]], [[trace-store]], [[error-classifier]], [[session-orchestrator]], [[context-kernel]], [[input-port]], [[agent-handle]], [[sandbox-manager]], [[idempotency-middleware]], [[idempotency-projection]], [[memory-layer]], [[middleware-pipeline]], [[l1-l2-isolation]], [[sdd-actor-model]]

## Ключевые инварианты

- I-DB-1: db_path MUST be explicit non-empty str
- I-SPEC-EXEC-1: CLI содержит только REGISTRY lookup + execute_and_project
- I-RRL-1..3: rule resolution детерминирован, silent override запрещён

## See Also

- [[sdd-vertical-slice]]
- [[sdd-domain-blueprint]]
- [[sdd-layer-l0]]
- [[sdd-layer-l1]]
