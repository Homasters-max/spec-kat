---
id: pattern/score-context
page_type: pattern
domain: sdd
layer: architecture
tags:
- validation
- pipeline
- read-only
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
---
# Score Context

## Summary

ScoreContext — read-only view, передаваемый в каждый [[metric-collector]] при вычислении AgentScore в [[audit-engine]]. Содержит всё необходимое для расчёта M1-M9: историю шагов, вывод sandbox, ScenarioSpec с critical checks, PolicyProjection. Изолирует collectors от прямых зависимостей на source компоненты — каждый Collector видит только ScoreContext, не трогает [[trace-projection]] или [[sandbox-manager]] напрямую.

## How It Works

**Структура:**

```text
ScoreContext:
    trace          : TraceReader        # история шагов агента (из trace-projection)
    sandbox_output : SandboxOutput      # stdout/stderr/exit codes из sandbox
    scenario_spec  : ScenarioSpec       # минимальная спека с critical checks (из TaskDefinition)
    policy         : PolicyProjection   # governance rules (из policy-kernel)
```

**Создание:** [[commit-discard-gate]] (L1) собирает ScoreContext перед вызовом `AuditEngine.score()`:
1. `trace` — из [[trace-projection]] (`TraceReader`)
2. `sandbox_output` — из замороженного [[sandbox-manager]] snapshot
3. `scenario_spec` — из State (TaskDefinition.scenario_spec, создана при `start-task`)
4. `policy` — из PolicyProjection ([[policy-kernel]])

**Использование в Collector:**

```text
# Пример ScopeAdherenceCollector (M2):
def collect(self, task_id: TaskId, context: ScoreContext) -> float:
    writes = context.trace.get_writes(task_id)
    violations = [w for w in writes if w.path not in context.policy.write_scope(task_id)]
    return 1.0 if not violations else max(0.0, 1.0 - len(violations) * 0.2)
```

**Immutability:** ScoreContext создаётся один раз, передаётся всем collectors. Collectors не должны модифицировать его состояние. `TraceReader` и `PolicyProjection` предоставляют read-only интерфейсы.

## When To Use

При реализации нового [[metric-collector]]. Если collector нуждается в данных не включённых в ScoreContext — это сигнал расширить ScoreContext (через явное изменение его структуры), а не добавлять прямую зависимость в collector.

## Trade-offs

**Плюсы:** collectors полностью изолированы от инфраструктуры — тестируются с mock ScoreContext; единая точка для DI зависимостей scoring; если collector нужны новые данные — видно в его сигнатуре.

**Минусы:** ScoreContext может разрастись если у разных collectors очень разные потребности; все поля создаются даже если конкретный collector использует только одно; изменение структуры ScoreContext требует проверки всех collectors.

**Расширение:** при добавлении нового [[metric-collector]] с нестандартными потребностями — сначала проверить можно ли обойтись существующими полями. Если нет — добавить поле в ScoreContext явно, не городить альтернативные пути передачи данных.

## See Also

- [[metric-collector]] — принимает ScoreContext как параметр `collect()`
- [[audit-engine]] — создаёт ScoreContext и передаёт в collectors
- [[commit-discard-gate]] — orchestrates создание ScoreContext перед scoring
- [[trace-projection]] — источник `trace` поля
- [[policy-kernel]] — источник `policy` поля
