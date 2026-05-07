---
id: pattern/metric-collector
page_type: pattern
domain: sdd
layer: architecture
tags:
- validation
- automation
- pipeline
- enforcement
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
- raw/commandspec-deepening-plan.md
---
# Metric Collector

## Summary

MetricCollector — интерфейс-seam между [[audit-engine]] и источниками метрик M1-M9. Каждый collector реализует одну метрику, живёт рядом со своим Bounded Context, регистрируется в AuditEngine через dependency injection. AuditEngine нормализует приоритеты: `weight_i = collector.priority / Σ(priorities)`. Добавление новой метрики не требует изменений AuditEngine и не нарушает балансировку остальных.

## How It Works

**Интерфейс:**

```python
class MetricCollector(Protocol):
    metric_id : str      # M1..M9, расширяемо
    priority  : int      # относительный вес; AuditEngine нормализует

    def collect(self, task_id: str, context: ScoreContext) -> float: ...  # 0.0..1.0
```

**ScoreContext** — read-only view, передаётся всем collectors:

```python
# ScoreContext:
#   trace          : TraceReader
#   sandbox_output : SandboxOutput
#   scenario_spec  : ScenarioSpec
#   policy         : PolicyProjection
```

**Нормализация в AuditEngine:**

```python
total = sum(c.priority for c in collectors)
samples = [c.collect(task_id, context) for c in collectors]
score = sum((c.priority / total) * s for c, s in zip(collectors, samples))
```

`sum(weights) == 1.0` — математическая гарантия, не invariant check.

**Начальные приоритеты (производные от прежних весов × 100):**

```text
ProtocolComplianceCollector  (M1, priority=20) — рядом с execution-guard
ScopeAdherenceCollector      (M2, priority=20) — рядом с scope-guard
TestPassCollector            (M3, priority=20) — рядом с sandbox-manager
FocusCollector               (M4, priority=10) — рядом с trace-projection
TimeCollector                (M5, priority=10) — рядом с session-orchestrator
GuardViolationCollector      (M6, priority=10) — рядом с error-classifier
CompletionCollector          (M7, priority=5)  — рядом с task state projection
StepCorrectnessCollector     (M8, priority=5)  — рядом с trace-projection
ExecutionCorrectnessCollector(M9, priority=10) — рядом с audit-engine / harness
```

## When To Use

Любое добавление метрики в AuditEngine. Вместо правки AuditEngine — создать новый класс, реализующий `MetricCollector`, задать `priority` (остальные веса автоматически пересчитаются), зарегистрировать при сборке.

Пример добавления M10: `priority=15` → AuditEngine пересчитывает все веса из `total = 115`.

## Trade-offs

**Плюсы:** AuditEngine не знает о внутренних структурах источников; каждый Collector тестируется независимо (mock ScoreContext); добавление M10 — новый класс без правки агрегатора; нет риска "weight drift" (priority — целые числа, нормализация математически гарантирована).

**Минусы:** dependency injection при сборке требует явного wire-up; `ScoreContext` должен содержать всё что может понадобиться любому Collector (может разрастись).

**Регистрация:** каждый Collector регистрируется при сборке явно, не через autodiscovery — порядок и состав контролируемы.

## See Also

- [[audit-engine]] — агрегатор, нормализует приоритеты collectors
- [[score-context]] — read-only view, передаётся в каждый collector
- [[commit-discard-gate]] — использует `critical_passed` из AgentScore
- [[execution-guard]] — источник данных для M1
- [[scope-guard]] — источник данных для M2
- [[trace-projection]] — источник данных для M4, M8
