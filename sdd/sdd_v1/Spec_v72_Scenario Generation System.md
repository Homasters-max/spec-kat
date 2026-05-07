# Spec_v72 — Phase 72: Scenario Generation System (Auto Ground Truth Builder)

Status: Draft  
Baseline: Spec_v71 (Meta-Harness), Spec_v64 (Audit), Spec_v65–70 (Protocol + Guard)

---

## 0. Goal

Автоматически генерировать ScenarioSpec из реальных SDD-задач (trace + summary + outputs),
чтобы:

1) масштабировать покрытие Meta-Harness без ручного описания сценариев  
2) превращать production-задачи в ground truth regression suite  
3) замкнуть цикл: execution → audit → scenario → harness → evolution  

Ключевая идея:
ScenarioSpec больше не пишется вручную → он **детерминированно извлекается** из завершённых задач.

---

## 1. Scope

### In-Scope

- BC-SCENARIO-GEN: генерация ScenarioSpec из Task artifacts
- Extraction pipeline: trace.jsonl + summary.json + FS diff
- Output normalization (детерминизация)
- Filtering (валидные/невалидные сценарии)
- CLI: `sdd gen-scenarios`
- Версионирование сценариев

### Out of Scope

- Генерация сложных property-based сценариев (Phase 73+)
- ML/LLM генерация (только deterministic rules)

---

## 2. Architecture / BCs

### BC-SCENARIO-GEN

```

src/sdd/scenario_gen/
extractor.py       # извлечение inputs/outputs из задачи
normalizer.py      # детерминизация outputs
builder.py         # сборка ScenarioSpec
filter.py          # отбор валидных сценариев
versioning.py      # version + hash
commands/
gen_scenarios.py

```

### Dependencies

```

BC-SCENARIO-GEN → BC-TRACE   (trace.jsonl)
BC-SCENARIO-GEN → BC-AUDIT   (summary.json)
BC-SCENARIO-GEN → FS         (файловые изменения)

````

---

## 3. Core Concepts

### 3.1 Scenario Extraction Model

```python
@dataclass(frozen=True)
class ExtractedScenario:
    task_id: str
    inputs: dict
    outputs: dict
    allowed_files: frozenset[str]
    invariants: tuple[str, ...]
    quality_score: float
````

---

### 3.2 Sources of Truth

| Source       | Role                        |
| ------------ | --------------------------- |
| trace.jsonl  | последовательность действий |
| summary.json | violations + метрики        |
| FS diff      | реальные outputs            |
| TaskSet      | allowed scope               |

---

## 4. Extraction Pipeline

### Step 1: Input Extraction

* команды (CLI)
* исходные файлы (Task inputs)
* параметры запуска

---

### Step 2: Output Extraction

* изменённые файлы (git diff / snapshot diff)
* stdout/stderr команд
* финальное состояние файлов

---

### Step 3: Normalization (CRITICAL)

Удаляются:

* timestamps
* random ids
* temp paths
* non-deterministic ordering

---

### Step 4: Validation Filter

Сценарий принимается если:

* task.status = DONE
* нет CRITICAL violations
* M7 (completion) = success
* outputs детерминируемы

---

### Step 5: Build ScenarioSpec

```python
ScenarioSpec(
  id = hash(task_id + outputs),
  inputs = ...,
  expected_outputs = normalized_outputs,
  allowed_files = task.inputs,
  invariants = extracted_invariants
)
```

---

## 5. Invariants

### Extraction Correctness

I-SCENARIO-GEN-1
Scenario MUST be derived only from:

* trace.jsonl
* summary.json
* filesystem state

(no external inference)

---

### Determinism

I-SCENARIO-GEN-2
Same task artifacts → identical ScenarioSpec

---

### Filtering

I-SCENARIO-GEN-3
Scenario MUST NOT be generated if:

* CRITICAL violations present
* outputs non-deterministic

---

### Normalization

I-SCENARIO-GEN-4
All outputs MUST be normalized:

* no timestamps
* no random ids
* no absolute temp paths

---

### Isolation

I-SCENARIO-GEN-5
Scenario MUST NOT depend on external state

---

### Versioning

I-SCENARIO-VERSION-1
ScenarioSpec MUST include:

* version
* hash(inputs + outputs)

---

### Audit Compatibility

I-SCENARIO-AUDIT-1
Scenario MUST be runnable by Meta-Harness without modification

---

### Boundary Protection

I-SCENARIO-BOUNDARY-1
Scenario generation MUST NOT modify:

* EventStore
* Spec
* State_index.yaml

---

## 6. CLI

```bash
sdd gen-scenarios --task T-6305
sdd gen-scenarios --phase 63
sdd gen-scenarios --all
```

Output:

```
.sdd/scenarios/
  S-<hash>.json
```

---

## 7. Data Models

```python
@dataclass(frozen=True)
class ScenarioMeta:
    scenario_id: str
    source_task: str
    created_at: int
    version: int
    quality_score: float
```

---

## 8. Quality Scoring

Scenario quality:

```text
quality_score =
  + completion_success (M7)
  + low violations (M2)
  + high determinism
  + stable outputs
```

Используется для:

* фильтрации
* приоритизации в harness

---

## 9. Integration with Harness

Flow:

```
Tasks → ScenarioGen → ScenarioSpec → Harness → ExecutionResult → Audit
```

---

## 10. Verification

| Test                             | Invariant          |
| -------------------------------- | ------------------ |
| test_deterministic_generation    | I-SCENARIO-GEN-2   |
| test_filter_invalid_tasks        | I-SCENARIO-GEN-3   |
| test_normalization_removes_noise | I-SCENARIO-GEN-4   |
| test_no_external_dependency      | I-SCENARIO-GEN-5   |
| test_harness_compatibility       | I-SCENARIO-AUDIT-1 |

---

## 11. DoD

Phase COMPLETE если:

1. ScenarioSpec генерируется из ≥90% DONE задач
2. Повторная генерация даёт identical результат
3. Harness успешно выполняет ≥95% сценариев
4. Нет зависимости от внешнего состояния
5. Все invariants PASS

---

## 12. Key Insight

Spec_v72 замыкает цикл:

```
Real Execution
   ↓
Trace + Summary
   ↓
Scenario Generation
   ↓
Harness Validation
   ↓
Audit (M1–M9)
   ↓
Evolution
```

Система начинает учиться **на собственных задачах**, а не на вручную заданных тестах.

Это превращает SDD в:

→ self-training инженерную систему
→ с контролируемым, детерминированным обучением
→ без потери архитектурной строгости