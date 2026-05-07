# Spec_v73 — Adaptive Evaluation & Protocol Optimization (Meta-Harness Derived)

Status: Draft  
Baseline: Spec_v71 (Meta-Harness), Spec_v72 (Scenario Generation), Spec_v64 (Audit)

---

## 0. Goal

Интегрировать ключевые идеи Meta-Harness в SDD как **adaptive evaluation loop**, который:
- автоматически выявляет слабые места агентов,
- генерирует стресс-сценарии,
- оптимизирует протоколы/нормы через controlled evolution,
- остаётся полностью детерминированным и event-sourced.

Фокус: не просто проверка (v71), а **активное улучшение через adversarial + coverage-driven evaluation**.

---

## 1. Core Idea (сжатое ядро)

SDD расширяется до цикла:

Execution → Audit → Harness Validation → Scenario Expansion → Protocol Optimization → Simulation → Guard

Ключевое отличие:
- раньше: проверка фиксированных сценариев  
- теперь: система **сама генерирует сценарии, где агент слаб**

---

## 2. New BCs

### BC-HARNESS-OPT (Optimization Layer)

```

src/sdd/harness_opt/  
weakness_miner.py # выявление слабых паттернов (из audit + M1–M9)  
scenario_mutator.py # генерация adversarial сценариев  
coverage.py # coverage model (по шагам, invariant'ам, файлам)  
optimizer.py # генерация LearningProposal  
replay_batch.py # массовый replay для сравнения версий протокола

```

---

## 3. Key Concepts

### 3.1 Weakness Mining

Источник:
- audit_report.md
- summary.json
- M1–M9

Выход:
```

WeaknessPattern:  
id: "W-001"  
type: "scope_leak" | "test_thrash" | "blind_write" | ...  
trigger: condition over metrics/events  
frequency: float  
severity: float

```

---

### 3.2 Scenario Mutation (главная идея Meta-Harness)

Из базового ScenarioSpec генерируются вариации:

```

Scenario' = mutate(Scenario)

mutations:

- input perturbation (missing files, corrupted inputs)
    
- constraint tightening (меньше allowed_files)
    
- ordering changes (другой порядок шагов)
    
- noise injection (лишние файлы/сигналы)
    
- adversarial edge cases
    

```

Цель:
→ заставить агента "сломаться" контролируемо

---

### 3.3 Coverage Model

```

Coverage:  
protocol_steps_covered: %  
invariants_triggered: %  
file_space_covered: %  
scenario_variants_executed: %

```

Инвариант:
→ система должна стремиться к росту coverage

---

### 3.4 Replay Batch Comparison

```

run(protocol_v1, scenarios) → metrics_v1  
run(protocol_v2, scenarios) → metrics_v2

Δ = compare(metrics_v1, metrics_v2)

```

Критерий:
- улучшение ≥ threshold
- без деградации критичных метрик

---

## 4. Metrics Extension

Добавляются:

```

M10 weakness_exposure_rate = выявленные слабости / сценарии  
M11 robustness_score = успешные прогоны / adversarial scenarios  
M12 coverage_score = coverage aggregate

```

Итого:
M1–M9 = поведение + correctness  
M10–M12 = robustness + learning quality

---

## 5. Invariants (ключевое)

### I-HARNESS-OPT-1 (No Direct Mutation)
Optimization MUST produce only LearningProposal  
→ прямое изменение протокола запрещено

### I-HARNESS-OPT-2 (Deterministic Mutation)
Scenario mutation MUST be deterministic given seed

### I-HARNESS-OPT-3 (Replay Consistency)
Replay MUST produce identical outputs for identical inputs

### I-HARNESS-OPT-4 (Isolation)
Все mutated scenarios выполняются только в sandbox

### I-HARNESS-OPT-5 (Coverage Monotonicity)
Coverage MUST NOT decrease across accepted protocol versions

### I-HARNESS-OPT-6 (Metric Safety)
Нельзя принимать изменения если:
- M9 ↓ (correctness)
- M2 ↓ (scope discipline)
- M8 ↓ (step correctness)

### I-HARNESS-OPT-7 (Weakness Grounding)
WeaknessPattern MUST быть основан только на:
- summary.json
- trace.jsonl
(никаких LLM hallucinations)

---

## 6. Flow (End-to-End)

### Step 1: Audit
→ M1–M9 + violations

### Step 2: Weakness Mining
→ выявление паттернов слабости

### Step 3: Scenario Expansion
→ генерация adversarial сценариев

### Step 4: Execution (Sandbox)
→ запуск агента на расширенном наборе

### Step 5: Validation
→ M9 + M10–M12

### Step 6: Proposal
→ LearningProposal:
  - изменение шага протокола
  - новая норма
  - изменение порядка действий

### Step 7: Simulation
→ replay_batch (A/B тест)

### Step 8: Guard + HumanGate
→ принятие/отклонение

---

## 7. Integration with SDD

| Layer | Integration |
|------|------------|
| L1 Execution | sandbox + scenario runner |
| L2 Evaluation | audit + M1–M12 |
| L3 Evolution | optimizer + replay_batch |

Важно:
→ Spec остаётся immutable  
→ изменения только через evolution pipeline

---

## 8. DoD (Definition of Done)

Система считается реализованной если:

1. Weakness mining работает на реальных audit данных
2. Scenario mutation генерирует ≥3 варианта на сценарий
3. Coverage считается и сохраняется
4. Replay batch сравнивает ≥2 версии протокола
5. M10–M12 корректно вычисляются
6. LearningProposal создаётся автоматически
7. Ни один invariant не нарушается
8. Все операции детерминированы (фиксированный seed)

---

## 9. Result

SDD получает новый уровень:

До:
→ система оценивает агента

После:
→ система:
  - находит слабости
  - генерирует тесты против агента
  - проверяет устойчивость
  - предлагает улучшения
  - валидирует их через replay

И всё это:
→ без потери детерминизма  
→ без прямой мутации системы  
→ с полным audit trail

Это и есть безопасный self-improving loop.