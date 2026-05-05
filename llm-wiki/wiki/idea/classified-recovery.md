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
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# Classified Recovery

Стратегия обработки ошибок в SDD: разные типы ошибок → разные стратегии восстановления.

## Summary

Вместо единого "hard stop" или "бесконечный retry" — детерминированная классификация каждой ошибки в одну из четырёх стратегий. Реализуется через [[error-classifier]] в L1.

## How It Works

```text
RETRY         → протокольные нарушения, которые агент должен исправить сам
                (NO_EXPLAIN_BEFORE_WRITE → агент делает explain и повторяет)

RE_EXPLAIN    → граф изменился после explain
                (GRAPH_CHANGED_AFTER_EXPLAIN → обязателен новый resolve+explain)

HUMAN_GATE    → state corruption, unknown errors, превышение retry limit
                (loop паузируется, Session Orchestrator уведомляет через EventLog)

ABORT         → критические инварианты L0, неустранимые ошибки WriteKernel
                (TaskRun завершается, Sandbox discards, ErrorEvent в EventLog)
```

**Правила классификации:**

```python
if error_type in PROTOCOL_VIOLATIONS:     → RETRY (max N attempts)
if error_type == "GRAPH_CHANGED":         → RE_EXPLAIN
if retry_count >= MAX_RETRIES:            → HUMAN_GATE
if error_type in L0_INVARIANT_VIOLATIONS: → ABORT
if error_type == "UNKNOWN":               → HUMAN_GATE
```

Каждая ошибка записывается как `ErrorClassified` event в EventLog — полный аудит recovery-решений.

## When To Use

При любом guard failure в execution pipeline. [[error-classifier]] вызывается автоматически после каждого rejected action.

## Trade-offs

- RETRY без лимита → агент застрянет в бесконечном цикле. Лимит обязателен.
- HUMAN_GATE для всего → человек перегружен тривиальными сбоями.

## See Also

- [[error-classifier]]
- [[execution-guard]]
- [[session-orchestrator]]
- [[sdd-meta-harness]]
