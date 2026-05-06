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
version: 5
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/commandspec-deepening-plan.md
---
# AuditEngine

**L2-компонент, Intelligence-домен**: детерминированный расчёт AgentScore из метрик M1–M9 по завершению каждого TaskRun. Нормализует приоритеты [[metric-collector]] в веса: `weight_i = collector.priority / Σ(priorities)`.

Вычисляет AgentScore — это analysis, не execution. Тот факт, что AuditEngine вызывается L1 SessionOrchestrator, не делает его L1-компонентом: being called from L1 ≠ being L1. Классификация по роли компонента, не по местонахождению вызова.

## How It Works

**Нормализация приоритетов:**

```python
total = sum(c.priority for c in collectors)
samples = [c.collect(task_id, context) for c in collectors]
critical_passed = all(s > 0 for c, s in zip(collectors, samples) if c.metric_id == "M9")
score = sum((c.priority / total) * s for c, s in zip(collectors, samples))
return AgentScore(total=score, samples=samples, critical_passed=critical_passed)
```

`sum(weights) == 1.0` — математическая гарантия нормализации, не отдельный invariant test.

**Начальное распределение (priority → effective weight):**

```text
M1 (priority=20) → 0.20   M2 (priority=20) → 0.20   M3 (priority=20) → 0.20
M4 (priority=10) → 0.10   M5 (priority=10) → 0.10   M6 (priority=10) → 0.10
M7 (priority=5)  → 0.05   M8 (priority=5)  → 0.05   M9 (priority=10) → 0.10
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

Добавление M10: создать новый [[metric-collector]] с `priority=N`, зарегистрировать при сборке — AuditEngine автоматически пересчитает все веса без изменения агрегатора.

## Trade-offs

- M9 требует ScenarioSpec — если ScenarioGen не сгенерировал spec для задачи, M9 = null.
- AgentScore агрегирует очень разные метрики — высокий score ≠ идеальная задача.
- Locality взвешивания концентрируется в AuditEngine, не размазана по 9 коллекторам.

## Open Questions

- [ ] (P2) Q164: Какие метрики нужны human-оператору в реальном времени? (активные TaskRuns, queue depth, AgentScore trend, error rate)
- [ ] (P2) Q165: Нужен ли real-time stream событий для monitoring? SSE, WebSocket, или poll?
- [ ] (P2) Q166: Как traced запрос от CLI команды до EventLog append? OpenTelemetry?
- [ ] (P2) Q167: Как связать log lines с конкретным TaskRun/event_id?
- [ ] (P2) Q168: `sdd debug-task T-NNN` — step-by-step воспроизведение с инспекцией каждого состояния?
- [ ] (P2) Q169: Какие условия → alert? (ABORT loop, state corruption, EventLog gap, projection lag)
- [ ] (P2) Q170: Как человек просматривает audit_log.jsonl? CLI, web UI, grep?
- [ ] (P2) Q171: Как измерить "хорошесть" спеки перед запуском фазы? (completeness, ambiguity score)
- [ ] (P2) Q172: Как убедиться что спека покрывает все требования? Checklist? Automated analysis?
- [ ] (P2) Q173: Автоматические проверки спеки — нет ли противоречий, неопределённостей, пустых секций?
- [ ] (P2) Q174: Все ли секции спеки отражены в TaskSet? Как обнаружить uncovered spec items?
- [ ] (P2) Q175: Как обнаружить что спека устарела (код изменился, спека не обновлялась)?

## See Also

- [[metric-collector]] — интерфейс collectors, содержит priority
- [[scenario-gen]]
- [[trace-store]]
- [[meta-optimization]]
- [[session-orchestrator]]
- [[replay-based-testing]]
