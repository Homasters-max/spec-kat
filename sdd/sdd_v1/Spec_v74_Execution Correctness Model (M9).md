# Spec_v74 — Phase 74: Execution Correctness Model (M9)

Status: Draft
Baseline: Spec_v71 (Meta-Harness), Spec_v72 (Scenario Generation), Spec_v64 (Audit)

---

## 0. Goal

Ввести формальную, детерминированную метрику **M9 = execution_correctness**, которая
оценивает не поведение агента, а **фактическую корректность результата выполнения задачи**
в контролируемом ScenarioSpec + Sandbox окружении.

M9 становится обязательным сигналом в AgentScore и используется в Evolution.

---

## 1. Core Idea

```text
Correctness = passed_checks / total_checks
````

Где checks определены в ScenarioSpec и валидируются через Harness.

---

## 2. Architecture / BCs

### BC-HARNESS (from v71)

* ExecutionSandbox
* ReplayEngine
* Validator

### BC-AUDIT (extended)

* metrics.py → добавляет M9
* report.py → вывод correctness отдельно

### BC-SCENARIO (v72)

* ScenarioSpec = источник ground truth

---

## 3. Types

```python
@dataclass(frozen=True)
class ExecutionCheck:
    id: str
    type: str  # OUTPUT_MATCH | FILE_DIFF | EXIT_CODE | INVARIANT
    passed: bool
    weight: float  # default = 1.0

@dataclass(frozen=True)
class ExecutionResult:
    checks: tuple[ExecutionCheck, ...]
    total_checks: int
    passed_checks: int
    weighted_score: float  # Σ(weight_i * passed_i) / Σ(weight_i)

@dataclass(frozen=True)
class ExecutionCorrectness:
    m9_score: float
    passed: bool  # threshold-based
```

---

## 4. Check Types

```text
OUTPUT_MATCH   → stdout/stderr совпадает с expected_output
FILE_DIFF      → файлы совпадают с expected_files (hash/content)
EXIT_CODE      → exit_code == expected
INVARIANT      → domain-specific checks (e.g. JSON schema, DB state)
SIDE_EFFECT    → отсутствие запрещённых изменений
```

---

## 5. M9 Calculation

### Base formula

```text
M9 = Σ(weight_i * passed_i) / Σ(weight_i)
```

### Constraints

* если total_checks == 0 → ERROR (invalid scenario)
* если critical check failed → M9 = 0 (hard fail)

---

## 6. Invariants

### Correctness invariants

I-M9-DETERMINISTIC-1
→ ExecutionResult MUST be deterministic for same:

* ScenarioSpec
* seed
* inputs
* environment snapshot

I-M9-GROUND-TRUTH-1
→ M9 MUST be computed ONLY from ScenarioSpec checks
(trace и transcript запрещены)

I-M9-CHECK-COMPLETE-1
→ ScenarioSpec MUST define ≥1 check
иначе execution invalid

I-M9-CRITICAL-1
→ checks MAY be marked critical
если любой critical=false → M9=0

I-M9-ISOLATION-1
→ execution MUST run inside sandbox
внешние side-effects запрещены

I-M9-REPLAY-1
→ replay MUST produce identical ExecutionResult
иначе DATA_CORRUPTION

I-M9-WEIGHT-1
→ weights MUST be deterministic and fixed per scenario

---

## 7. Integration with AgentScore

```text
AgentScore =
  0.20 * M1 (protocol)
+ 0.20 * M2 (scope)
+ 0.20 * M3 (tests)
+ 0.10 * M4 (focus)
+ 0.10 * M5 (time)
+ 0.10 * M6 (behavior)
+ 0.05 * M7 (completion)
+ 0.05 * M8 (step_correctness)
+ 0.10 * M9 (execution_correctness)
```

### Constraint

I-AUDIT-SCORE-EXT-1
→ M9 MUST be included in AgentScore
→ BUT MAY be reported separately for debugging

---

## 8. Multi-Scenario Evaluation

Для задачи:

```text
M9_task = mean(M9_scenario_i)
```

Для фазы:

```text
M9_phase = mean(M9_task_j)
```

### Invariant

I-M9-DISTRIBUTION-1
→ evaluation MUST include ≥N scenarios (configurable, default=3)

---

## 9. Failure Semantics

| Condition       | Result      |
| --------------- | ----------- |
| No checks       | ERROR       |
| Sandbox failure | M9 = 0      |
| Replay mismatch | INVALID_RUN |
| Partial pass    | 0 < M9 < 1  |
| Full pass       | M9 = 1      |

---

## 10. Anti-Gaming Protection

I-M9-NO-OVERFIT-1
→ ScenarioSpec MUST NOT be static only
→ Scenario Generation (v72) REQUIRED

I-M9-SEMANTIC-1
→ checks MUST validate semantics, not formatting

I-M9-HIDDEN-1
→ часть checks MAY быть скрыта от агента

---

## 11. DoD (Definition of Done)

* [ ] ExecutionResult deterministic across 3 replays
* [ ] ≥1 check defined per scenario
* [ ] M9 computed and stored in audit
* [ ] AgentScore включает M9
* [ ] Replay == original execution
* [ ] Sandbox isolation verified
* [ ] ≥3 scenarios per task (default)
* [ ] critical checks enforced

---

## 12. Summary

```text
M9 = формальный сигнал "решена ли задача правильно"

M1–M8 → поведение агента
M9     → correctness результата

Без M9:
  система оценивает стиль

С M9:
  система оценивает результат

Именно M1–M9 вместе → делают SDD self-improving системой
```
