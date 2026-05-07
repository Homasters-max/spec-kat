Spec_v83 — Harness-Centric Architecture Refinement (уточнение Phase 77–82)

Status: Draft (refinement layer, НЕ новая функциональность)
Depends on: Spec_v64 (Audit), v71 (Meta-Harness), v76–82 (Memory Layer)

---

## 0. Goal

Переформулировать архитектуру SDD в harness-centric модель без изменения ядра:

- зафиксировать Harness как **первоклассный слой системы**
- отделить:
  - стабильное ядро (EventLog, Memory, Spec)
  - оптимизируемую стратегию (Harness Strategy)
- подготовить систему к Meta-Harness как outer-loop оптимизатору

Ключевая идея:
SDD = stable deterministic core + optimizable harness layer

---

## 1. Core Separation (новая архитектурная рамка)

### 1.1 Stable Core (immutable / guarded)

НЕ изменяется Meta-Harness:

- EventLog (SSOT)
- Specs (immutable)
- Memory Layer (Spec_v76–82)
- Invariants (global guarantees)
- Guard / Safety

### 1.2 Harness Layer (optimizable)

МОЖЕТ изменяться:

- Context strategy (что читать из Memory)
- Tool usage strategy
- Agent roles / orchestration
- Prompt assembly logic
- Execution policies

---

## 2. New BC — BC-HARNESS

```

src/sdd/harness/
runtime/
executor.py        # выполнение run (фиксированная логика)
context_bridge.py  # связь с ContextEngine
tool_router.py
strategy/
policy.py          # стратегии (что оптимизируется)
roles.py           # роли агентов
planner.py         # orchestration rules
spec/
harness_spec.md    # declarative описание (NLAH-style)

````

---

## 3. Harness Decomposition

### 3.1 BC-HARNESS-RUNTIME (deterministic)

Фиксированная логика выполнения:

- принимает:
  - Spec
  - Task
  - HarnessStrategy
- выполняет:
  - Context assembly
  - Tool calls
  - Trace recording

Invariants:

- I-HARNESS-RUNTIME-1: runtime детерминирован при фиксированной strategy
- I-HARNESS-RUNTIME-2: runtime не содержит эвристик/оптимизаций
- I-HARNESS-RUNTIME-3: все решения → trace events

---

### 3.2 BC-HARNESS-STRATEGY (optimizable)

Переменная часть:

- context selection policy
- tool selection heuristics
- retry / branching logic
- agent coordination

Формат:

```yaml
strategy:
  context:
    sources: [task, agent, project]
    depth: medium
  tools:
    allow: [read, write, test]
  execution:
    retries: 1
    branching: disabled
````

Invariants:

* I-HARNESS-STRATEGY-1: strategy = pure config (no side-effects)
* I-HARNESS-STRATEGY-2: strategy versioned
* I-HARNESS-STRATEGY-3: strategy не может обходить Guard

---

## 4. Integration with Memory (refinement v76–82)

Изменение: Memory теперь используется только через Harness.

Old:
ContextEngine → Memory

New:
HarnessStrategy → MemoryQuery → ContextEngine

Invariants:

* I-MEM-HARNESS-ONLY-1: Memory.read вызывается только из Harness
* I-MEM-NO-DIRECT-1: LLM не имеет прямого доступа к Memory
* I-CTX-HARNESS-1: Context = f(strategy, Memory)

---

## 5. DiagnosticFS как интерфейс Meta-Harness (усиление Phase 79)

Расширение:

```
/harnesses/
  run_001/
    candidate_A/
      strategy.yaml
      trace.jsonl
      metrics.json
      result.json
```

Meta-Harness использует:

* strategy.yaml → что тестируется
* trace.jsonl → как выполнялось
* metrics.json → результат

Invariants:

* I-FS-HARNESS-1: каждый candidate run полностью воспроизводим
* I-FS-HARNESS-2: strategy + trace → replayable execution
* I-FS-HARNESS-3: FS = единственный интерфейс outer-loop

---

## 6. Meta-Harness Integration Boundary (критично)

### Что МОЖНО менять:

* HarnessStrategy
* Context policies
* Tool selection rules
* Agent orchestration

### Что НЕЛЬЗЯ менять:

* EventLog
* Spec
* Memory invariants
* Guard rules

Invariants:

* I-MH-BOUNDARY-1: Meta-Harness не может мутировать core
* I-MH-BOUNDARY-2: изменения только через strategy
* I-MH-BOUNDARY-3: все эксперименты sandboxed

---

## 7. Anti-Complexity Rule (новый принцип)

Проблема из видео:

> больше логики ≠ лучше результат

Решение:

### Rule:

Любая сложная логика:

* multi-agent branching
* retry loops
* search strategies
* verifier chains

→ НЕ встраивается в core

→ оформляется как HarnessStrategy variant

Invariants:

* I-COMPLEXITY-1: core не содержит search/branching логики
* I-COMPLEXITY-2: сложные стратегии = только strategy layer
* I-COMPLEXITY-3: каждая сложность должна быть отключаемой

---

## 8. Artifact Re-definition (важное изменение мышления)

Старая модель:
"модель решает задачу"

Новая модель:
"strategy + harness решают задачу"

Формально:

```text
Result = f(Spec, Task, HarnessStrategy, Model)
```

Где:

* Model → interchangeable
* HarnessStrategy → основной объект оптимизации

Invariants:

* I-ARTIFACT-1: стратегия важнее модели
* I-ARTIFACT-2: смена модели не ломает систему
* I-ARTIFACT-3: улучшения фиксируются в strategy, не в коде

---

## 9. Relation to Phase 77–82

| Phase | Уточнение                                      |
| ----- | ---------------------------------------------- |
| 77    | governance применяется к Memory, НЕ к strategy |
| 78    | contracts теперь включают HarnessStrategy      |
| 79    | DiagnosticFS = основной интерфейс для harness  |
| 80    | ContextEngine подчинён strategy                |
| 81    | Safety применяется к strategy execution        |
| 82    | Meta-Memory анализирует strategy performance   |

---

## 10. DoD (Definition of Done)

* [ ] BC-HARNESS введён
* [ ] runtime / strategy разделены
* [ ] Memory доступен только через Harness
* [ ] DiagnosticFS содержит strategy + trace + metrics
* [ ] Meta-Harness boundary зафиксирован
* [ ] complex logic вынесена из core

---

## 11. Итоговая модель

SDD теперь:

L0: Spec (immutable)
L1: Execution (Harness Runtime)
L2: Evaluation (Audit + Metrics)
L3: Evolution (Meta-Harness)

НО:

HarnessStrategy = главный объект эволюции

---

## 12. Ключевой эффект

Без переписывания системы ты получаешь:

* переносимость между моделями
* управляемую сложность
* безопасную оптимизацию
* совместимость с Meta-Harness

---

## Final Insight

Ты уже построил правильную систему.

Этот spec НЕ добавляет новую функциональность.

Он делает одну критичную вещь:
→ **фиксирует границы между тем, что можно менять, и тем, что нельзя**

И именно это делает систему устойчивой к self-evolution.