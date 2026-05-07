---
source: Phase Acceptance Protocol for Phases 53-58
last_synced: 2026-04-30
update_trigger: when new phases are planned or acceptance criteria change
---

# Ref: Phase Acceptance Protocol

Методология безопасного перехода между фазами 53–58.
Каждая фаза содержит: Universal DoD → Phase-specific DoD → Regression Guard → Transition Gate → Rollback Triggers.

---

## §1 Принципы

| # | Принцип | Следствие |
|---|---------|-----------|
| PA-1 | Фаза COMPLETE = необратимо | Plan_vN.md frozen, нельзя откатить без новой фазы |
| PA-2 | Gate = команда, не утверждение | Каждый gate — конкретный CLI вызов с ожидаемым выходом |
| PA-3 | Regression guard обязателен | Нельзя перейти если существующая функциональность сломана |
| PA-4 | Silent success = failure | `count: 0` там где ожидается `> 0` — ошибка, не успех |
| PA-5 | Transition gate = человеческий gate | Верифицируется человеком перед `sdd activate-phase N+1` |
| PA-6 | Rollback trigger = STOP сразу | При любом rollback trigger → `sdd report-error`, не продолжать |

---

## §2 Universal DoD (применяется к каждой фазе)

Выполнить последовательно (SEM-13):

```bash
# Step U-1: все задачи DONE
sdd show-state
# → tasks_completed == tasks_total

# Step U-2: formal DoD check
sdd validate --check-dod --phase N
# → exit 0

# Step U-3: test suite
python3 -m pytest tests/unit/ -q
# → 0 failures, 0 errors
```

Нарушение любого шага → фаза не может быть COMPLETE.

---

## §3 Шаблон Phase Acceptance Checklist

Каждый спек Phase N содержит секцию:

```
## M. Phase Acceptance Checklist

### Part 1 — In-Phase DoD

Шаги U-1..U-3 (Universal DoD) +
Phase-specific acceptance commands (ожидаемый вывод указан)

### Part 2 — Regression Guard

Команды, которые НЕ ДОЛЖНЫ изменить поведение по сравнению с Phase N-1.
Если хоть одна команда даёт неожиданный результат → STOP.

### Part 3 — Transition Gate (for Phase N+1)

Команды, которые человек запускает перед sdd activate-phase N+1.
Каждая — с ожидаемым выходом. Несоответствие → N+1 BLOCKED.

### Part 4 — Rollback Triggers

Условия, при которых немедленно: STOP → sdd report-error → recovery.md
```

---

## §4 Dependency Chain (53–58)

```
[52 COMPLETE]
    │
    ├─► 53: TestedByEdgeExtractor ──────────────────────────────┐
    │                                                            │
    └─► 55: Graph-Guided Implement ─────────────────────────────┤
                                                                 ▼
                                              56: Graph-First  (gate: 53 + 55 + config)
                                                  │
                                                  ▼
                                              57: SSOT  (gate: BC/LAYER coverage)
                                                  │
                                                  ▼
                                              58: Module API  (gate: arch-check functional)
```

---

## §5 Config Pre-flight (перед Phase 56)

Обязательно до `sdd activate-phase 56`:

```yaml
# .sdd/config/sdd_config.yaml — добавить секции:
bounded_contexts:
  graph:        "src/sdd/graph/"
  context:      "src/sdd/context_kernel/"
  spatial:      "src/sdd/spatial/"
  infra:        "src/sdd/infra/"
  commands:     "src/sdd/commands/"
  tasks:        "src/sdd/tasks/"
  cli:          "src/sdd/cli.py"

layers:
  application:  ["src/sdd/cli.py", "src/sdd/commands/"]
  domain:       ["src/sdd/graph/", "src/sdd/context_kernel/", "src/sdd/spatial/"]
  infra:        ["src/sdd/infra/"]

arch_check:
  enabled_checks:
    - bc-cycles
    - layer-purity
    - layer-direction
    - bc-cross-dependencies
    - module-cohesion
  coverage_full_threshold: 0.9
  module_cohesion_max_external_imports: 10
  guard_reachability_max_hops: 3
  ignore_patterns:
    - "src/sdd/cli.py"
```

Без этих секций Phase 56 не запустится (BoundedContextEdgeExtractor, LayerEdgeExtractor).

---

## §6 Phase 57 Gate Semantics

**Уточнение:** Phase Gate перед Phase 57 = `sdd arch-check --check all → tool functional (exit 0)`.

Это НЕ означает "codebase без violations". Означает:
- arch-check успешно строит граф
- ViolatesEdgeExtractor корректно запускается
- Violations reporting работает (exit 1 при нарушениях — ожидаемо и нормально)

Фактические violations в SDD codebase фиксируются в ValidationReport Phase 57, не блокируют Phase 57.

---

## §6b Phase 53 Acceptance Checklist (spec immutable — DoD здесь)

Spec_v53 находится в `.sdd/specs/` (approved, immutable). DoD определяется здесь.

### Part 1 — In-Phase DoD

```bash
# Step U (Universal)
sdd show-state                          # tasks_completed == tasks_total
sdd validate --check-dod --phase 53     # exit 0
python3 -m pytest tests/unit/ -q        # 0 failures

# Step 53-A: TEST node kind зарегистрирован
python3 -c "from sdd.spatial.nodes import VALID_KINDS; assert 'TEST' in VALID_KINDS; print('TEST kind OK')"
# → TEST kind OK

# Step 53-B: TestedByEdgeExtractor строит edges
sdd graph-stats --edge-type tested_by --format json
# → {"count": N}, N > 0

# Step 53-C: направление edges корректное (src → tested_by → TEST)
sdd explain FILE:src/sdd/commands/complete.py --edge-types tested_by --format json
# → destination nodes имеют kind=TEST (не FILE), т.е. tested_by → TEST

sdd explain COMMAND:complete --edge-types tested_by --format json
# → destination: TEST:tests/unit/commands/test_complete.py

# Step 53-D: нет фантомных edges
python3 -m pytest tests/unit/graph/test_tested_by_extractor.py::test_tested_by_no_phantom_edges -v
# → PASSED

# Step 53-E: sdd test-filter работает
sdd test-filter --node COMMAND:complete
# → запускает pytest tests/unit/commands/test_complete.py (не весь suite)
```

### Part 2 — Regression Guard

```bash
# tested_by: 0.80 уже в EDGE_KIND_PRIORITY до Phase 53 — не должно измениться
python3 -c "from sdd.graph.types import EDGE_KIND_PRIORITY; assert EDGE_KIND_PRIORITY['tested_by'] == 0.80"
# → exit 0

# sdd explain существующих nodes — не затронут
sdd explain COMMAND:complete --format json  # те же results что в Phase 52
```

### Part 3 — Transition Gate (as Phase Gate for Phase 56)

Это доводится до Phase 56 как gate:

```bash
sdd graph-stats --edge-type tested_by --format json
# Expected: {"count": N}, N > 0
# Если 0 → Phase 56 BLOCKED
```

### Part 4 — Rollback Triggers

- `sdd explain FILE:X --edge-types tested_by` возвращает nodes с kind=FILE (неверное направление)
- `sdd graph-stats --edge-type tested_by` → `count: 0`
- `sdd test-filter` запускает весь test suite вместо targeted (fallback без warn)

---

## §7 Quick Reference: все transition gates

| Переход | Gate команда | Ожидаемый результат |
|---------|-------------|---------------------|
| 52→53 | `sdd show-state` | phase_current=52, status=COMPLETE |
| 52→55 | `sdd show-state` | phase_current=52, status=COMPLETE |
| 55+53→56 | `sdd graph-stats --edge-type tested_by --format json` | `count > 0` |
| 55+53→56 | `sdd explain MODULE:sdd.graph --edge-types contains` | ≥1 FILE node |
| 55+53→56 | `cat .sdd/config/sdd_config.yaml` | `bounded_contexts:` секция присутствует |
| 56→57 | `sdd graph-stats --node-type BOUNDED_CONTEXT --format json` | `count > 0` |
| 56→57 | `sdd graph-stats --node-type LAYER --format json` | `count > 0` |
| 56→57 | `sdd arch-check --check bc-cross-dependencies --format json` | exit 0 |
| 57→58 | `sdd arch-check --check all --format json` | exit 0 (tool functional) |
| 57→58 | `cat src/sdd/graph/extractors/invariant_edges.py` | понять схему INVARIANT (ручная проверка) |
