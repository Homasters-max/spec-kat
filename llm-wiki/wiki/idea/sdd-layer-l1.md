---
page_type: idea
domain: sdd
layer: architecture
sdd_layer: null
sdd_domain: null
tags:
- sdd/l1
- pipeline
- automation
- domain/sdd
updated: '2026-05-06'
sources: []
---
# SDD Layer L1 — Execution

## Summary

L1 исполняет задачи детерминированно через L0-примитивы. Все L1-компоненты ephemeral и replay-safe: их состояние можно восстановить из EventLog без потерь. L1 не имеет прямого доступа к EventStore — только через CommandBus.

## Ключевые компоненты L1

**Core:**
- [[execution-guard]] — gate перед исполнением команды
- [[scope-guard]] — проверка scope-ограничений; scope override через scope_policy.py
- [[trace-store]] — запись трейсов исполнения; read-only для L2
- [[error-classifier]] — классификация ошибок по типу и стадии
- [[session-orchestrator]] — оркестрация сессий; маршрутизация по routing table
- [[context-kernel]] — сборка контекстного пакета для LLM-запроса
- [[input-port]] — точка входа внешних команд в систему
- [[agent-handle]] — хендл LLM-агента; изолирует агента от прямого доступа к системе
- [[sandbox-manager]] — управление изолированными средами исполнения
- [[idempotency-middleware]] — дедупликация команд на уровне middleware
- [[idempotency-projection]] — проекция для проверки idempotency key
- [[memory-layer]] — персистентная память между сессиями
- [[middleware-pipeline]] — цепочка middleware для обработки команды
- [[l1-l2-isolation]] — граница изоляции между L1 и L2
- [[sdd-actor-model]] — модель акторов для SDD-компонентов

**Blueprint:**
- [[policy-kernel]] — исполнение policy-правил; детерминированный интерпретатор

**Engine:**
- [[agent-loop]] — основной цикл LLM-агента; orchestrates tool calls

## Ключевые инварианты

- I-HANDLER-PURE-1: handle() возвращает только events — нет side-effects
- I-RRL-1: scope override через scope_policy.py; inline exceptions запрещены
- I-SESSION-DECLARED-1: LLM обязан эмитить SessionDeclared в начале каждой сессии

## Антипаттерны

- L1 компонент напрямую зависит от L2 (обратная зависимость).
- Handler с side-effects (не pure).
- Session state хранится вне EventLog.

## See Also

- [[sdd-layer-l0]]
- [[sdd-layer-l2]]
- [[sdd-horizontal-slice]]
- [[l1-l2-isolation]]
