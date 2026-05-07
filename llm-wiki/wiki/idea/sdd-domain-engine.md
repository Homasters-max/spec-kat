---
page_type: idea
domain: sdd
layer: architecture
sdd_layer: null
sdd_domain: null
tags:
- sdd/engine
- pipeline
- llm
- domain/sdd
updated: '2026-05-06'
sources: []
---
# SDD Domain — Engine

## Summary

Engine-домен владеет runtime исполнения: AgentLoop, execution context, tool call scheduling. Engine оркестрирует LLM-агента через сессии, используя Blueprint для принятия решений и Core для записи результатов.

## Назначение и границы

Engine отвечает за **выполнение работы**: запуск агента, обработку tool calls, управление контекстом сессии. Engine знает, как исполнять, но не знает, что планировать (Blueprint) и как анализировать (Intelligence).

Владеет: AgentLoop lifecycle, tool call routing, session execution context.

Не владеет: физикой записи (Core), структурой планирования (Blueprint), аналитикой (Intelligence).

## L1 Engine компоненты

[[agent-loop]] — основной цикл LLM-агента; оркестрирует tool calls в рамках сессии

## Взаимодействие с другими доменами

Engine читает Blueprint-контекст (план, задачи) через проекции. Записывает результаты через Core (CommandBus). Engine не вызывает Intelligence — только оставляет данные для её анализа в EventLog.

## Антипаттерны

- Engine хранит session state вне EventLog (нарушение replay-safety).
- AgentLoop напрямую вызывает EventStore (минуя CommandBus).
- Engine зависит от Intelligence (обратная зависимость L2→L1).

## See Also

- [[sdd-vertical-slice]]
- [[sdd-domain-blueprint]]
- [[sdd-domain-intelligence]]
- [[agent-loop]]
- [[sdd-layer-l1]]
