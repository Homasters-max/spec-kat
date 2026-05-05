# Spec_v71 — Phase 71: Meta-Harness + Deterministic Execution Sandboxing

Status: Draft
Baseline: Spec_v65–70 (Execution Isolation + Audit + Protocol Formalization)

---

## 0. Goal

Добавить детерминированный слой исполнения и тестирования (Meta-Harness),
который:

1) изолирует выполнение задач (sandboxed execution)
2) делает поведение агента воспроизводимым (replayable)
3) вводит ground-truth проверку корректности через controlled scenarios
4) превращает SDD в self-evaluating систему (агент → выполняет → система проверяет)

Ключевая идея:
SDD больше не только логирует и анализирует → он валидирует поведение агента
через контролируемое окружение выполнения.

---

## 1. Scope

### In-Scope

- BC-HARNESS: sandbox execution layer
- BC-SCENARIO: описание воспроизводимых сценариев
- Deterministic execution (env snapshot + FS isolation)
- Replay engine (trace → re-execution)
- Ground truth validation (expected vs actual)
- Integration с Audit (M8 расширяется)
- Command: `sdd run-harness`, `sdd replay`

### Out of Scope

- Full containerization (Phase 75+)
- Distributed execution
- External CI/CD integration

---

## 2. Architecture / BCs

### BC-HARNESS (Execution Sandbox)

```

src/sdd/harness/
executor.py        # запуск команд в sandbox
sandbox_fs.py      # изолированная FS (tmp root)
env_snapshot.py    # capture + restore env
replay.py          # replay trace.jsonl
validator.py       # expected vs actual diff

```

### BC-SCENARIO (Ground Truth)

```

src/sdd/scenario/
model.py           # ScenarioSpec
loader.py          # загрузка сценариев
generator.py       # генерация тест-кейсов

````

### BC-AUDIT (расширение)

- добавляется M9: execution_correctness
- интеграция с validator output

---

## 3. Core Concepts

### 3.1 ScenarioSpec (ground truth)

```python
@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    inputs: dict
    expected_outputs: dict
    allowed_files: frozenset[str]
    invariants: tuple[str, ...]
````

---

### 3.2 Execution Sandbox

Каждый run:

* isolated FS root (tmp dir)
* controlled env vars
* deterministic seed
* no external side effects

---

### 3.3 Replay Model

```
trace.jsonl → COMMAND events → re-execute → compare outputs
```

---

## 4. Execution Flow

### UC-71-1: Harness Run

1. load ScenarioSpec
2. create sandbox FS
3. inject inputs
4. run agent commands
5. capture outputs
6. validate against expected_outputs
7. produce execution_report.json

---

### UC-71-2: Replay

1. load trace.jsonl
2. re-run commands in same order
3. compare:

   * outputs
   * side effects
4. detect divergence

---

## 5. Invariants

### Execution Isolation

I-HARNESS-ISO-1
Sandbox MUST isolate FS (no writes outside root)

I-HARNESS-ISO-2
Environment MUST be deterministic (no external env leakage)

---

### Determinism

I-HARNESS-DET-1
Same trace + same inputs → identical outputs

I-HARNESS-DET-2
Randomness MUST be seeded

---

### Replay Integrity

I-HARNESS-REPLAY-1
Replay MUST execute commands in exact original order

I-HARNESS-REPLAY-2
Replay divergence MUST be detected and reported

---

### Validation

I-HARNESS-VAL-1
Each scenario MUST define expected_outputs

I-HARNESS-VAL-2
Validator MUST compare:

* file outputs
* command outputs
* side effects

---

### Integration with Audit

I-AUDIT-GROUND-2
Execution correctness MUST be computed only from harness validation

I-AUDIT-METRIC-1
M9 execution_correctness = passed_checks / total_checks

---

### Boundary Protection (CRITICAL)

I-HARNESS-BOUNDARY-1
Harness MUST NOT mutate:

* EventStore
* State_index.yaml
* specs/

I-HARNESS-BOUNDARY-2
Harness is read-only relative to SDD core

---

## 6. Metrics Extension

Добавляется:

M9 execution_correctness (вес 0.10)

```
total_score = M1..M8 (0.90) + M9 (0.10)
```

---

## 7. Data Models

```python
@dataclass(frozen=True)
class ExecutionResult:
    scenario_id: str
    success: bool
    checks_passed: int
    checks_total: int
    diffs: tuple[str, ...]

@dataclass(frozen=True)
class ReplayResult:
    trace_id: str
    deterministic: bool
    divergences: tuple[str, ...]
```

---

## 8. CLI

```
sdd run-harness --scenario S-001
sdd replay T-6305
```

---

## 9. Verification

| Test                        | Invariant            |
| --------------------------- | -------------------- |
| test_sandbox_isolation      | I-HARNESS-ISO-1      |
| test_env_determinism        | I-HARNESS-DET-2      |
| test_replay_same_output     | I-HARNESS-DET-1      |
| test_replay_divergence      | I-HARNESS-REPLAY-2   |
| test_validation_correctness | I-HARNESS-VAL-2      |
| test_no_core_mutation       | I-HARNESS-BOUNDARY-1 |

---

## 10. DoD

Phase COMPLETE если:

1. Harness выполняет сценарии изолированно
2. Replay воспроизводит trace без расхождений
3. Validation корректно сравнивает outputs
4. M9 считается детерминированно
5. Нет мутаций core SDD
6. Все invariants PASS

---

## Key Insight

Spec_v71 делает SDD:

Было:
→ анализ поведения агента

Стало:
→ проверка поведения агента против ground truth

Это переход от:
"agent behaved correctly?"
к:
"agent produced correct result under controlled conditions?"

Это критический шаг к self-evolving системе.
