# Plan_v3 — Phase 3: Norm, Guards & Scheduler

Status: DRAFT
Spec: specs/Spec_v3_Guards.md

---

## Milestones

### M1: C-1 Core Extensions (BLOCKING)

```text
Spec:       §2 BC-CORE extensions, §3 Domain Events, §8 Integration §C-1
BCs:        BC-CORE
Invariants: I-ST-10
Depends:    — (prerequisite for all other milestones)
Risks:      C-1 constraint — core/events.py, core/events dataclasses, and
            domain/state/reducer.py MUST be modified in a single task.
            Splitting triggers import-time AssertionError → entire process
            fails to start. This task must not be split.
```

Outputs:
- `src/sdd/core/errors.py` — add `CyclicDependency(SDDError)`, `ParallelGroupConflict(SDDError)`
- `src/sdd/core/events.py` — add `NormViolatedEvent`, `TaskStartGuardRejectedEvent` dataclasses;
  add both types to `V1_L1_EVENT_TYPES`
- `src/sdd/domain/state/reducer.py` — add `"NormViolated"`, `"TaskStartGuardRejected"` to
  `_KNOWN_NO_HANDLER`

### M2: BC-NORMS — Norm Catalog

```text
Spec:       §2 BC-NORMS, §4.8, §5 I-NRM-1..3, §6 load_catalog pre/post
BCs:        BC-NORMS
Invariants: I-NRM-1, I-NRM-2, I-NRM-3
Depends:    M1 (MissingContext from core/errors.py; NormViolatedEvent shape for NormGuard later)
Risks:      strict=False default must not be changed — backwards compat (I-NRM-2).
            Frozen dataclass ensures strict flag immutable after construction (I-NRM-3).
```

Outputs:
- `src/sdd/domain/norms/catalog.py` — `NormEntry`, `NormCatalog`, `load_catalog`
- `src/sdd/domain/norms/__init__.py` — re-exports: `NormEntry`, `NormCatalog`, `load_catalog`
- `tests/unit/domain/norms/test_catalog.py` — 9 test cases (§9 row 7)

### M3: BC-TASKS Extension — Task Dataclass + Parser

```text
Spec:       §2 BC-SCHEDULER (BC-TASKS extension), §4.9
BCs:        BC-TASKS
Invariants: I-TS-1 (extended)
Depends:    M1 (no hard dep, but M1 errors needed for scheduler in M4)
            Can be parallelised with M2.
Risks:      Backwards compatibility: existing TaskSet fixtures omit new fields →
            defaults must be () and None. Existing tests must continue to pass.
```

Outputs:
- `src/sdd/domain/tasks/parser.py` — extend `Task` dataclass: add `depends_on: tuple[str, ...]`,
  `parallel_group: str | None`; update `parse_taskset` to populate new fields from markdown
- `tests/unit/domain/tasks/test_parser.py` — extend with 3 new test cases (§9 row 9)

### M4: BC-SCHEDULER — DAG Builder & Topological Order

```text
Spec:       §2 BC-SCHEDULER, §4.10, §5 I-SCH-1..6, §6 build_dag/topological_order pre/post
BCs:        BC-SCHEDULER
Invariants: I-SCH-1, I-SCH-2, I-SCH-3, I-SCH-4, I-SCH-5, I-SCH-6
Depends:    M1 (CyclicDependency, ParallelGroupConflict, MissingContext from core/errors.py)
            M3 (Task.depends_on, Task.parallel_group consumed by build_dag)
Risks:      ParallelGroupConflict must NOT be confused with CyclicDependency (I-SCH-5, I-SCH-6).
            topological_order must run a post-check verifying I-SCH-1 even after
            successful Kahn iteration, to guard against implementation bugs.
```

Outputs:
- `src/sdd/domain/tasks/scheduler.py` — `TaskNode`, `build_dag`, `topological_order`
- `src/sdd/domain/tasks/__init__.py` — add re-exports: `TaskNode`, `build_dag`, `topological_order`
- `tests/unit/domain/tasks/test_scheduler.py` — 11 test cases (§9 row 8)

### M5: Guard Infrastructure — runner.py

```text
Spec:       §4.0 EmitFn + GuardContext, §4.1 GuardOutcome + GuardResult, §4.7 run_guard_pipeline
BCs:        BC-GUARDS (runner.py)
Invariants: I-GRD-4
Depends:    M1 (event types for GuardContext.emit type; SDDError for guards)
            M2 (NormCatalog — GuardContext.catalog field type)
            Phase 2 BC-STATE (SDDState — GuardContext.state field type)
Risks:      GuardContext must be frozen dataclass — no mutations (I-GRD-9).
            EmitFn must never be None per interface contract — tests should verify
            that passing None as emit raises immediately.
            run_guard_pipeline is pure orchestration; it must not interpret guard results.
```

Outputs:
- `src/sdd/guards/runner.py` — `EmitFn`, `GuardContext`, `GuardOutcome`, `GuardResult`,
  `run_guard_pipeline`
- `tests/unit/guards/test_runner.py` — 5 test cases (§9 row 6)

### M6: Integrity Guards — ScopeGuard + TaskGuard

```text
Spec:       §2.1 Guard Behavioral Contract, §4.2 ScopeGuard, §4.4 TaskGuard,
            §5 I-GRD-1, I-GRD-2, I-GRD-5, I-GRD-9, §6 pre/post
BCs:        BC-GUARDS (scope.py, task.py)
Invariants: I-GRD-1, I-GRD-2, I-GRD-5, I-GRD-9 (integrity side)
Depends:    M5 (GuardContext, GuardResult, GuardOutcome)
            M3 (parse_taskset used by TaskGuard)
Risks:      Integrity guards MUST NOT emit — no ctx.emit call anywhere (I-GRD-9).
            ScopeGuard.check_write ALWAYS denies .sdd/specs/** regardless of config
            (I-GRD-2); this is not configurable.
            TaskGuard raises two different error types: InvalidState (DONE) vs
            MissingContext (not found) — must not swap them.
```

Outputs:
- `src/sdd/guards/scope.py` — `ScopeGuard` (check_read, check_write)
- `src/sdd/guards/task.py` — `TaskGuard` (check)
- `tests/unit/guards/test_scope.py` — 5 test cases (§9 row 1)
- `tests/unit/guards/test_task.py` — 4 test cases (§9 row 3)

### M7: Policy Guards + guards package

```text
Spec:       §2.1, §3, §4.3 PhaseGuard, §4.5 TaskStartGuard (incl. §4.5.1), §4.6 NormGuard,
            §5 I-GRD-3, I-GRD-6, I-GRD-7, I-GRD-8, I-GRD-10, §6 pre/post, §8 integration
BCs:        BC-GUARDS (phase.py, task_start.py, norm.py, __init__.py)
Invariants: I-GRD-3, I-GRD-6, I-GRD-7, I-GRD-8, I-GRD-9 (policy side), I-GRD-10, I-EL-9
Depends:    M5 (GuardContext, EmitFn, GuardResult)
            M6 (integrity guards — __init__.py re-exports both sets together)
            M1 (NormViolatedEvent, TaskStartGuardRejectedEvent, SDDEventRejected)
            M2 (NormCatalog — NormGuard uses ctx.catalog)
            Phase 2 BC-STATE (read_state — PhaseGuard)
Risks:      I-GRD-8 (emit BEFORE return) is the most commonly violated invariant —
            tests must assert call order explicitly.
            TaskStartGuard §4.5.1 parsing contract is strict: must use exact line patterns,
            not ad-hoc parsing. Tests must provide canonical fixture files.
            I-EL-9: no direct duckdb.connect in any guard module — verified by test mocks
            and grep in validation.
            SDDEventRejected payload fields (§3) must match exactly.
```

Outputs:
- `src/sdd/guards/phase.py` — `PhaseGuard` (check, emits SDDEventRejected)
- `src/sdd/guards/task_start.py` — `TaskStartGuard` (check_requires_invariants, §4.5.1 contract)
- `src/sdd/guards/norm.py` — `NormGuard` (check, emits NormViolatedEvent)
- `src/sdd/guards/__init__.py` — re-exports all: EmitFn, GuardContext, GuardOutcome, GuardResult,
  run_guard_pipeline, ScopeGuard, PhaseGuard, TaskGuard, TaskStartGuard, NormGuard
- `tests/unit/guards/test_phase.py` — 8 test cases (§9 row 2)
- `tests/unit/guards/test_task_start.py` — 9 test cases (§9 row 4)
- `tests/unit/guards/test_norm.py` — 7 test cases (§9 row 5)

---

## Risk Notes

- R-1: **C-1 split risk** — M1 modifies three files atomically. If this task is split during
  decomposition (e.g. errors.py vs events.py vs reducer.py separated), the import-time assert
  in EventReducer fires on any import. Decompose must keep all three files in T-3xx-M1.
- R-2: **emit-before-return (I-GRD-8)** — Policy guards must call ctx.emit before returning
  GuardResult(DENY). Test suites for PhaseGuard, TaskStartGuard, NormGuard must assert
  call ordering via mock side effects, not just assert-called.
- R-3: **§4.5.1 parsing contract fragility** — TaskStartGuard uses exact regex patterns to
  locate ValidationReport files. Any deviation from the canonical format (e.g. extra whitespace,
  different casing) causes silent DENY. Fixture files in tests must use the exact canonical format.
- R-4: **I-EL-9 no direct DB calls** — All guards receive an injected emit callable; none
  may call duckdb.connect directly. This must be verified both by test mocks and by a
  grep check in validate_invariants.
- R-5: **BC-TASKS backwards compatibility** — Existing TaskSet fixtures do not declare
  depends_on or parallel_group. The extended parse_taskset must default these to () and None
  without modifying existing test fixtures.
