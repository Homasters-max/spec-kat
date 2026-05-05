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
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
---
# Metric Collector

## Summary

MetricCollector — интерфейс-seam между [[audit-engine]] и источниками метрик M1-M9. Каждый collector реализует один метрик, живёт рядом со своим Bounded Context, регистрируется в AuditEngine через dependency injection. AuditEngine становится чистым агрегатором: `AgentScore = Σ(weight_i × collector_i.collect())`. Добавление новой метрики не требует изменений AuditEngine.

## How It Works

**Интерфейс:**

```text
protocol MetricCollector:
    metric_id : MetricId    # M1..M9, расширяемо
    weight    : float       # сумма весов всех collectors = 1.0

    collect(task_id: TaskId, context: ScoreContext) -> float  # 0.0..1.0
```

**ScoreContext** — read-only view, передаётся всем collectors:

```text
ScoreContext:
    trace          : TraceReader
    sandbox_output : SandboxOutput
    scenario_spec  : ScenarioSpec
    policy         : PolicyProjection
```

**Агрегация в AuditEngine:**

```python
samples = [c.collect(task_id, context) for c in collectors]
critical_passed = all(s > 0 for c, s in zip(collectors, samples) if c.metric_id == M9)
total = sum(c.weight * s for c, s in zip(collectors, samples))
return AgentScore(total=total, samples=samples, critical_passed=critical_passed)
```

**Валидация при инициализации:**

```python
def __init__(self, collectors):
    total_weight = sum(c.weight for c in collectors)
    if abs(total_weight - 1.0) > 1e-9:
        raise SystemInitializationError(
            f"MetricCollector weights must sum to 1.0, got {total_weight}"
        )
    self.collectors = collectors
```

Это hard failure при старте — система не запускается с невалидной конфигурацией аудита.

**Locality Collectors по Bounded Context:**

```text
ProtocolComplianceCollector (M1, 0.20) — рядом с execution-guard
ScopeAdherenceCollector     (M2, 0.20) — рядом с scope-guard
TestPassCollector           (M3, 0.20) — рядом с sandbox-manager
FocusCollector              (M4, 0.10) — рядом с trace-projection
TimeCollector               (M5, 0.10) — рядом с session-orchestrator
GuardViolationCollector     (M6, 0.10) — рядом с error-classifier
CompletionCollector         (M7, 0.05) — рядом с task state projection
StepCorrectnessCollector    (M8, 0.05) — рядом с trace-projection
ExecutionCorrectnessCollector(M9, 0.10) — рядом с audit-engine / harness
```

## When To Use

Любое добавление метрики в AuditEngine. Вместо правки AuditEngine — создать новый класс реализующий `MetricCollector`, задать `weight` (скорректировав остальные), зарегистрировать при сборке. Несогласованные веса → `SystemInitializationError`.

## Trade-offs

**Плюсы:** AuditEngine не знает о внутренних структурах источников; каждый Collector тестируется независимо (mock ScoreContext); добавление M10 — новый класс без правки агрегатора; `SystemInitializationError` при неверных весах — fail-fast.

**Минусы:** dependency injection при сборке требует явного wire-up; риск "weight drift" при командной работе — нужен тест суммы весов; `ScoreContext` должен содержать всё что может понадобиться любому Collector (может разрастись).

**Регистрация:** каждый Collector регистрируется при сборке явно, не через autodiscovery — порядок и состав контролируемы.

## See Also

- [[audit-engine]] — агрегатор, принимает collectors при инициализации
- [[score-context]] — read-only view, передаётся в каждый collector
- [[commit-discard-gate]] — использует `critical_passed` из AgentScore
- [[execution-guard]] — источник данных для M1
- [[scope-guard]] — источник данных для M2
- [[trace-projection]] — источник данных для M4, M8
