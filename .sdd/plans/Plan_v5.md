# Plan_v5 — Phase 5: Critical Fixes

Status: DRAFT
Spec: specs/Spec_v5_CriticalFixes.md

---

## Milestones

### M1: Core Events & Activation Commands

```text
Spec:       §3 — Domain Events; §4.1–4.3 — Commands & Handlers; §8 — Norm Catalog Updates
BCs:        BC-CORE (core/events.py, core/errors.py),
            BC-COMMANDS (commands/activate_phase.py, commands/activate_plan.py),
            BC-STATE (domain/state/reducer.py — PhaseActivated/PlanActivated handlers)
Invariants: C-1, I-ACT-1, I-DOMAIN-1, I-REDUCER-2, I-SCHEMA-1 (partial)
Depends:    — (foundation; all other milestones depend on this)
Risks:      C-1 requires simultaneous changes to V1_L1_EVENT_TYPES, _EVENT_SCHEMA, and
            dataclass definitions — must be a single atomic task or import fails.
            If PhaseActivatedEvent / PlanActivatedEvent are added without reducer handlers,
            replay of new EventLogs will produce incorrect state (Q1 broken).
```

### M2: Error Path Consolidation (I-ES-1 final form)

```text
Spec:       §2.1 — Canonical Write Path; §4.4 — error_event_boundary; §4.5 — CommandRunner
BCs:        BC-COMMANDS (commands/_base.py, commands/sdd_run.py)
Invariants: I-ES-1 (final), I-ES-6, I-CMD-3
Depends:    M1 (CommandRunner calls EventStore.append on error_events from new event types)
Risks:      error_event_boundary currently writes directly to DB via sdd_append — removing
            that path BEFORE CommandRunner catches the attached events would silently drop
            ErrorEvents. Changes to _base.py and sdd_run.py must land together.
            If EventStore.append itself raises, logging.error must fire — not a bare suppress.
```

### M3: GuardContext Deduplication

```text
Spec:       §2.3 — GuardContext Deduplication; removal protocol (mandatory order)
BCs:        BC-GUARDS (guards/runner.py → imports from domain/guards/context)
Invariants: deduplication (no stale GuardContext class in guards/runner.py)
Depends:    M1 (domain/guards/context.py is the canonical source; must be stable first)
Risks:      Any test or production code that imports GuardContext from guards.runner will
            break at import time if the class is removed without updating all import sites.
            Mandatory: grep -r "guards.runner" src/ tests/ BEFORE removal.
```

### M4: Reducer Unknown Event Invariant (I-REDUCER-1)

```text
Spec:       §2.4 — Reducer Invariant I-REDUCER-1; §4.7 — _handle_unknown policy; §4.6 — UnknownEventType
BCs:        BC-STATE (domain/state/reducer.py), BC-CORE (core/errors.py)
Invariants: I-REDUCER-1
Depends:    M1 (reducer already has PhaseActivated/PlanActivated handlers; unknown-event path
            can be added independently but should not conflict with new handlers)
Risks:      If _KNOWN_NO_HANDLER set is not populated correctly, legitimate no-handler events
            (e.g. MetricRecorded) will emit spurious warnings on every replay.
            strict_mode must default to False — changing the default breaks production replay.
```

### M5: Test Suite — Full Coverage of Phase 5 Invariants

```text
Spec:       §9 — Verification table (9 test files, ~30 named tests)
BCs:        tests/unit/core/, tests/unit/domain/state/, tests/unit/commands/,
            tests/unit/guards/, tests/unit/infra/, tests/integration/
Invariants: I-ES-1 (final), I-ES-6, I-REDUCER-1, I-REDUCER-2, I-SCHEMA-1,
            I-ACT-1, I-DOMAIN-1, I-PROJ-1, I-PROJ-2, I-CMD-3, Q1, Q3
Depends:    M1, M2, M3, M4 (all implementation tasks complete)
Risks:      tautological test (reduce(sdd_replay()) == read_state_from_yaml()) must be
            REPLACED not supplemented — if old tautological check survives, Q3 remains unmet.
            Integration test (test_full_chain.py) requires a real temp DuckDB — test isolation
            is mandatory to avoid polluting the project EventLog.
```

---

## Risk Notes

- R-1: **C-1 atomicity** — `PhaseActivatedEvent` / `PlanActivatedEvent` must be added to
  `V1_L1_EVENT_TYPES`, `_EVENT_SCHEMA`, and as dataclasses in a single task (T-5-01).
  Partial addition triggers `AssertionError` on import. Mitigation: T-5-01 scope is
  deliberately narrow — one task, one atomic change.

- R-2: **Error path race** — removing `sdd_append` from `error_event_boundary` before
  `CommandRunner` is updated to catch `_sdd_error_events` creates a window where ErrorEvents
  are silently dropped. Mitigation: T-5-02 covers both files (_base.py + sdd_run.py) as a
  single task; do not split.

- R-3: **GuardContext import breakage** — grepping for import sites is MANDATORY (per §2.3
  removal protocol) before removing the class. Any missed import site fails at runtime, not
  at test time (dynamic import). Mitigation: T-5-03 starts with the grep step.

- R-4: **_KNOWN_NO_HANDLER population** — if the set of known-no-handler event types is
  incomplete, production replay will emit spurious warnings (I-REDUCER-1 noise). Mitigation:
  audit _EVENT_SCHEMA and all event types in existing EventLogs before finalising the set.

- R-5: **Integration test isolation** — `test_full_chain.py` must use a temporary DuckDB
  (`tmp_path` fixture), never the project's `.sdd/state/sdd_events.duckdb`. Mitigation:
  test fixture is specified in Spec §7 UC-5-4 (fresh temporary DuckDB).
