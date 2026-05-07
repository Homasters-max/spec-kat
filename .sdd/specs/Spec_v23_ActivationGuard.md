# Spec_v23 — Phase 23: Activation Guard

Status: Draft
Baseline: Spec_v15_KernelUnification.md, Spec_v22_ValidationRuntimeRefinement.md

---

## 0. Goal

Команда `sdd activate-phase N` допускала активацию фазы с `tasks_total=0`, если оператор не передавал флаг `--tasks`. Значение `0` фиксировалось в `PhaseInitializedEvent` — immutable событие, которое нельзя переиграть без нарушения I-PHASE-SEQ-1. Последствие: сломанный счётчик прогресса на всё время жизни фазы.

Корневая причина — CLI принимал `tasks_total` как пользовательский ввод, тогда как это **derived value**: оно детерминированно выводится из `TaskSet_v{N}.md`. Хранение derived data в EventLog без валидации нарушает принцип event sourcing.

Phase 23 закрывает дыру через два механизма:
1. **Auto-detect**: CLI вычисляет `tasks_total` из TaskSet если `--tasks` не передан.
2. **Guard**: `tasks_total <= 0` запрещён — команда завершается с ошибкой до записи события.

Дополнительно: `--tasks` помечается deprecated, добавляются три новых инварианта.

---

## 1. Scope

### In-Scope

- **BC-23-1**: `_resolve_tasks_total()` — single validation point в `src/sdd/commands/activate_phase.py`
- **BC-23-2**: `--tasks` deprecation — аргумент становится optional с DeprecationWarning

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-23-1: `_resolve_tasks_total`

```
src/sdd/commands/activate_phase.py
  _resolve_tasks_total(phase_id: int, tasks_arg: int | None) -> int
```

Единственная точка валидации для `tasks_total` перед записью `PhaseInitializedEvent`.

Алгоритм:
1. Вызвать `taskset_file(phase_id)` → путь к `TaskSet_v{phase_id}.md`
2. Вызвать `parse_taskset(str(path))` → `list[Task]`; raises `MissingContext` если файл отсутствует
3. `actual = len(tasks)`
4. `if actual <= 0` → raise `MissingContext` (I-PHASE-INIT-3)
5. `if tasks_arg is None` → return `actual`
6. `if tasks_arg != actual` → raise `Inconsistency` (I-PHASE-INIT-2)
7. return `actual`

Контракт: функция либо возвращает `int > 0`, либо поднимает `SDDError`. Caller (`main()`) не дублирует валидацию.

### BC-23-2: `--tasks` deprecation

```
src/sdd/commands/activate_phase.py
  --tasks: type=int, default=None  # было default=0
```

- `default=None`: если не передан → auto-detect через BC-23-1
- Если передан: `DeprecationWarning` + валидация через BC-23-1
- `--tasks 0` явный: вызовет `Inconsistency` (TaskSet не может быть пустым для активации)

### Dependencies

```text
BC-23-1 → sdd.infra.paths.taskset_file     : path resolution
BC-23-1 → sdd.domain.tasks.parser.parse_taskset : task counting
BC-23-1 → sdd.core.errors.MissingContext   : empty/absent TaskSet
BC-23-1 → sdd.core.errors.Inconsistency    : tasks_arg mismatch
```

---

## 3. Domain Events

Событийная модель не меняется. `PhaseInitializedEvent` сохраняет поле `tasks_total: int`.

Изменение: `tasks_total` теперь **гарантированно > 0** на момент записи события (I-PHASE-INIT-3).

---

## 4. Types & Interfaces

```python
def _resolve_tasks_total(phase_id: int, tasks_arg: int | None) -> int:
    """Single validation point for tasks_total before PhaseInitialized is emitted.

    I-PHASE-INIT-2: tasks_total MUST be consistent with TaskSet at activation time.
    I-PHASE-INIT-3: tasks_total MUST be > 0.

    Raises:
        MissingContext: TaskSet absent or contains no tasks.
        Inconsistency: tasks_arg provided but doesn't match actual TaskSet size.
    Returns:
        int > 0
    """
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-PHASE-INIT-2 | `tasks_total` in `PhaseInitialized` MUST be consistent with `TaskSet_v{phase_id}.md` at activation time. The CLI MUST auto-detect this value; if `--tasks N` is supplied, it MUST equal the actual TaskSet count. | 23 |
| I-PHASE-INIT-3 | `PhaseInitialized` MUST NOT be emitted with `tasks_total <= 0`. Activation fails with `MissingContext` if TaskSet is absent or empty. | 23 |
| I-TASKSET-IMMUTABLE-1 | `TaskSet_v{N}.md` MUST NOT be modified after `sdd activate-phase N` is called. Post-activation TaskSet changes invalidate `tasks_total` recorded in `PhaseInitialized` (I-PHASE-INIT-2 is checked at activation time only). | 23 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-PHASE-SEQ-1 | PhaseStarted with `phase_id <= phase_current` is skipped (soft guard). |
| I-HANDLER-PURE-1 | `handle()` methods return events only — no I/O. |
| I-1 | All SDD state = reduce(events); State_index.yaml is readonly snapshot. |

---

## 6. Pre/Post Conditions

### PhaseInitialized emission

**Pre:**
- `TaskSet_v{phase_id}.md` exists and contains at least one `T-NNN` task entry
- `tasks_total = len(parse_taskset(...)) > 0`
- If `--tasks N` supplied: `N == tasks_total`

**Post:**
- `PhaseInitializedEvent.tasks_total > 0`
- `state.tasks_total == PhaseInitializedEvent.tasks_total`
- `state.phase_status == "ACTIVE"`

---

## 7. Use Cases

### UC-23-1: Human activates phase without --tasks (happy path)

**Actor:** Human operator
**Trigger:** `sdd activate-phase N`
**Pre:** `TaskSet_vN.md` exists with ≥1 task
**Steps:**
1. CLI calls `_resolve_tasks_total(N, None)`
2. `parse_taskset` returns `k` tasks (`k > 0`)
3. `tasks_total = k`
4. `ActivatePhaseCommand(tasks_total=k)` constructed
5. `PhaseStartedEvent` + `PhaseInitializedEvent(tasks_total=k)` emitted atomically
6. `State_index.yaml` rebuilt: `tasks.total = k`
**Post:** `sdd show-state` shows `tasks.total = k`

### UC-23-2: Human activates phase with missing TaskSet

**Actor:** Human operator
**Trigger:** `sdd activate-phase N` (no `TaskSet_vN.md` on disk)
**Pre:** `TaskSet_vN.md` absent
**Steps:**
1. CLI calls `_resolve_tasks_total(N, None)`
2. `parse_taskset` raises `MissingContext`
3. `except SDDError: return 1` — no event written
**Post:** EventLog unchanged; CLI exits 1 with error message

### UC-23-3: Human passes --tasks with wrong count

**Actor:** Human operator
**Trigger:** `sdd activate-phase N --tasks M` where `M ≠ len(TaskSet)`
**Pre:** `TaskSet_vN.md` exists with `k` tasks, `M ≠ k`
**Steps:**
1. `DeprecationWarning` for `--tasks`
2. `_resolve_tasks_total(N, M)` → `Inconsistency`
3. CLI exits 1
**Post:** EventLog unchanged

---

## 8. Integration

### Dependencies on Other BCs

| BC / Module | Direction | Purpose |
|-------------|-----------|---------|
| `sdd.infra.paths.taskset_file` | BC-23-1 → | TaskSet path resolution (honours SDD_HOME) |
| `sdd.domain.tasks.parser.parse_taskset` | BC-23-1 → | Task counting from Markdown |
| `sdd.core.errors.{MissingContext,Inconsistency}` | BC-23-1 → | Structured error propagation |

### No Reducer Changes

`EventReducer` не изменяется. `PhaseInitializedEvent` schema не изменяется.
Изменение — на уровне CLI, до записи события.

---

## 9. Verification

| # | Test | Invariant(s) |
|---|------|--------------|
| 1 | `test_resolve_tasks_total_autodetect` — TaskSet 5 задач, arg=None → 5 | I-PHASE-INIT-2 |
| 2 | `test_resolve_tasks_total_explicit_match` — arg=5, TaskSet 5 → 5 | I-PHASE-INIT-2 |
| 3 | `test_resolve_tasks_total_mismatch` — arg=3, TaskSet 5 → Inconsistency | I-PHASE-INIT-2 |
| 4 | `test_resolve_tasks_total_missing_file` — нет файла → MissingContext | I-PHASE-INIT-3 |
| 5 | `test_resolve_tasks_total_empty_taskset` — 0 задач → MissingContext | I-PHASE-INIT-3 |
| 6 | `test_main_autodetect_happy_path` — TaskSet 4, no --tasks → exit 0, tasks_total=4 | I-PHASE-INIT-2/3 |
| 7 | `test_main_missing_taskset` — нет TaskSet → exit 1 | I-PHASE-INIT-3 |
| 8 | `test_main_mismatch` — --tasks 9, TaskSet 4 → exit 1 | I-PHASE-INIT-2 |
| 9 | `test_main_deprecated_tasks_arg` — --tasks 4, TaskSet 4 → exit 0 + DeprecationWarning | BC-23-2 |

Все тесты в `tests/unit/commands/test_activate_phase.py`.

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Полное удаление `--tasks` из CLI | Phase 24+ (после deprecation period) |
| Checksum TaskSet при активации для enforcement I-TASKSET-IMMUTABLE-1 | Phase 24+ |
| Хранение TaskSet checksum в PhaseInitializedEvent | Требует изменения event schema — отдельная спецификация |
