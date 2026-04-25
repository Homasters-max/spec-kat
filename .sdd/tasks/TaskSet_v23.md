# TaskSet_v23 — Phase 23: Activation Guard

Spec: specs/Spec_v23_ActivationGuard.md
Plan: plans/Plan_v23.md

---

T-2301: Implement `_resolve_tasks_total` (BC-23-1)

Status:               DONE
Spec ref:             Spec_v23 §2 — BC-23-1, §4 Types & Interfaces, §5 Invariants, §6 Pre/Post
Invariants:           I-PHASE-INIT-2, I-PHASE-INIT-3
spec_refs:            [Spec_v23 §2 BC-23-1, Spec_v23 §4, I-PHASE-INIT-2, I-PHASE-INIT-3]
produces_invariants:  [I-PHASE-INIT-2, I-PHASE-INIT-3]
requires_invariants:  [I-HANDLER-PURE-1, I-1]
Inputs:               src/sdd/commands/activate_phase.py
                      src/sdd/infra/paths.py (taskset_file — existing, read-only)
                      src/sdd/domain/tasks/parser.py (parse_taskset — existing, read-only)
                      src/sdd/core/errors.py (MissingContext, Inconsistency — existing, read-only)
Outputs:              src/sdd/commands/activate_phase.py
Acceptance:           `_resolve_tasks_total` function present in activate_phase.py;
                      imports of taskset_file, parse_taskset, MissingContext, Inconsistency added;
                      function signature matches Spec_v23 §4 exactly;
                      algorithm steps 1-7 from §2 BC-23-1 implemented
Depends on:           —

---

T-2302: Deprecate `--tasks` and wire `_resolve_tasks_total` in `main()` (BC-23-2)

Status:               DONE
Spec ref:             Spec_v23 §2 — BC-23-2, §7 UC-23-1..3
Invariants:           I-PHASE-INIT-2, I-PHASE-INIT-3
spec_refs:            [Spec_v23 §2 BC-23-2, Spec_v23 §7, I-PHASE-INIT-2, I-PHASE-INIT-3]
produces_invariants:  [I-PHASE-INIT-2, I-PHASE-INIT-3]
requires_invariants:  [I-PHASE-INIT-2, I-PHASE-INIT-3]
Inputs:               src/sdd/commands/activate_phase.py (with T-2301 applied)
Outputs:              src/sdd/commands/activate_phase.py
Acceptance:           `--tasks` argument has `default=None` (was `default=0`);
                      if `--tasks` is supplied, DeprecationWarning is emitted before validation;
                      `main()` calls `_resolve_tasks_total(phase_id, parsed.tasks)` and uses
                      result as `tasks_total`; caller does not duplicate validation logic
Depends on:           T-2301

---

T-2303: Unit tests for `_resolve_tasks_total` — §9 tests 1-5

Status:               DONE
Spec ref:             Spec_v23 §9 — Verification tests 1-5
Invariants:           I-PHASE-INIT-2, I-PHASE-INIT-3
spec_refs:            [Spec_v23 §9, I-PHASE-INIT-2, I-PHASE-INIT-3]
produces_invariants:  [I-PHASE-INIT-2, I-PHASE-INIT-3]
requires_invariants:  [I-PHASE-INIT-2, I-PHASE-INIT-3]
Inputs:               src/sdd/commands/activate_phase.py (with T-2301, T-2302 applied)
                      tests/unit/commands/test_activate_phase.py
Outputs:              tests/unit/commands/test_activate_phase.py
Acceptance:           All five tests pass:
                      test_resolve_tasks_total_autodetect (TaskSet 5 tasks, arg=None → 5);
                      test_resolve_tasks_total_explicit_match (arg=5, TaskSet 5 → 5);
                      test_resolve_tasks_total_mismatch (arg=3, TaskSet 5 → Inconsistency);
                      test_resolve_tasks_total_missing_file (no file → MissingContext);
                      test_resolve_tasks_total_empty_taskset (0 tasks → MissingContext)
Depends on:           T-2301

---

T-2304: Integration tests for `main()` — §9 tests 6-9

Status:               DONE
Spec ref:             Spec_v23 §9 — Verification tests 6-9
Invariants:           I-PHASE-INIT-2, I-PHASE-INIT-3, I-TASKSET-IMMUTABLE-1
spec_refs:            [Spec_v23 §9, I-PHASE-INIT-2, I-PHASE-INIT-3, I-TASKSET-IMMUTABLE-1]
produces_invariants:  [I-PHASE-INIT-2, I-PHASE-INIT-3, I-TASKSET-IMMUTABLE-1]
requires_invariants:  [I-PHASE-INIT-2, I-PHASE-INIT-3]
Inputs:               src/sdd/commands/activate_phase.py (with T-2301, T-2302 applied)
                      tests/unit/commands/test_activate_phase.py
Outputs:              tests/unit/commands/test_activate_phase.py
Acceptance:           All four tests pass:
                      test_main_autodetect_happy_path (TaskSet 4 tasks, no --tasks → exit 0, tasks_total=4);
                      test_main_missing_taskset (no TaskSet → exit 1);
                      test_main_mismatch (--tasks 9, TaskSet 4 → exit 1);
                      test_main_deprecated_tasks_arg (--tasks 4, TaskSet 4 → exit 0 + DeprecationWarning)
Depends on:           T-2302, T-2303

---

<!-- Granularity: 4 tasks — phase scope is narrow (single function + CLI wiring + 9 tests). TG-2 recommends 10–30; count is below range but justified by spec focus (two BCs, one file). -->
<!-- Every task is independently implementable and independently testable (TG-1). -->
