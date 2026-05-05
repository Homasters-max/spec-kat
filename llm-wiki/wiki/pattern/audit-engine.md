---
id: pattern/audit-engine
page_type: pattern
domain: sdd
layer: architecture
tags:
- validation
- automation
- pipeline
- ssot
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# AuditEngine

L1-компонент: детерминированный расчёт AgentScore из метрик M1–M9 по завершению каждого TaskRun.

## How It Works

```python
AgentScore =
  0.20 * M1  # protocol compliance (resolve→explain→write соблюдён?)
+ 0.20 * M2  # scope adherence (writes только в write_scope?)
+ 0.20 * M3  # tests (тесты прошли?)
+ 0.10 * M4  # focus (задача решена без drift?)
+ 0.10 * M5  # time (в пределах бюджета шагов?)
+ 0.10 * M6  # behavior (guard violations count?)
+ 0.05 * M7  # completion (задача DONE?)
+ 0.05 * M8  # step_correctness (каждый шаг корректен?)
+ 0.10 * M9  # execution_correctness (ScenarioSpec checks прошли?)
```

**M9 — особая метрика:**

- Вычисляется только из [[scenario-gen]] ScenarioSpec checks
- Если любой `critical=true` check failed → M9 = 0 (hard fail)
- Детерминирован: одинаковые inputs → одинаковый M9
- Фильтрация через [[test-catalog-projection]]: только релевантные ScenarioSpecs запускаются при расчёте M9 (AD-9)
- Adversarial failures ([[adversarial-scenario-mutator]]) — sub-метрика M9 в Tier 3 Regression Suite
- Tier 3 встроен в Session Orchestrator flow — не отдельный процесс

**Источники данных:**

- TraceStore → M1, M2, M4, M6, M8
- EventLog projections (ReadModel) → M3, M5, M7
- ScenarioSpec → M9

**Output:** `summary.json` с AgentScore + breakdown по каждой метрике. Хранится как `AuditCompleted` event в EventLog.

## When To Use

Вызывается Session Orchestrator'ом после `SandboxManager.commit()/discard()`. Результат используется [[meta-optimization]] для анализа трендов.

## Trade-offs

- M9 требует ScenarioSpec — если ScenarioGen не сгенерировал spec для задачи, M9 = null.
- AgentScore агрегирует очень разные метрики — высокий score ≠ идеальная задача.

## See Also

- [[scenario-gen]]
- [[trace-store]]
- [[meta-optimization]]
- [[session-orchestrator]]
- [[replay-based-testing]]
