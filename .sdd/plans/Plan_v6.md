# Plan_v6 — Phase 6: Query, Metrics & Reporting

Status: DRAFT
Spec: specs/Spec_v6_QueryMetrics.md

---

## Milestones

### M1: BC-QUERY — EventLog Query Layer

```text
Spec:       §2.2, §4.1, §4.2, §4.3 — QueryFilters, EventLogQuerier, QueryEventsHandler
BCs:        BC-QUERY
Invariants: I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-PROJ-CONST-1, I-PROJ-CONST-2
Tasks:      T-601, T-602, T-603, T-604
Depends:    — (baseline: BC-INFRA infra/db.py from Phase 5)
Risks:      EventLogQuerier is the foundation for BC-METRICS and BC-VALIDATION-EXT;
            if I-QE-1..4 are not solid, all downstream projections inherit wrong behaviour.
            QueryEventsHandler MUST conform to QueryHandler Protocol (NOT CommandHandler)
            to prevent CommandRunner registration error.
```

### M2: BC-METRICS — Metrics Domain & Reporting

```text
Spec:       §2.3, §4.4, §4.5, §4.6, §4.7 — MetricRecord, MetricsSummary, MetricsAggregator,
            MetricsReportHandler
BCs:        BC-METRICS
Invariants: I-MR-1, I-MR-2, I-CHAIN-1, I-ES-6, I-PROJ-CONST-1, I-PROJ-CONST-2, I-PROJ-CONST-3
Tasks:      T-605, T-606, T-607, T-608
Depends:    M1 (MetricsReportHandler calls EventLogQuerier directly — not via QueryEventsHandler)
Risks:      I-CHAIN-1 violation is silent at runtime — MetricsReportHandler calling
            QueryEventsHandler instead of EventLogQuerier breaks testability and future
            async correctness. Test test_no_query_handler_in_report is the gate.
            MetricsAggregator must be pure (no I/O) — verified by test_aggregator_pure_no_io.
```

### M3: BC-VALIDATION-EXT — I-M-1 Enforcement

```text
Spec:       §4.8, §5 (I-M-1-CHECK) — check_im1_invariant added to validate_invariants.py
BCs:        BC-COMMANDS (extension of validate_invariants.py)
Invariants: I-M-1-CHECK, I-CHAIN-1
Tasks:      T-609, T-610
Depends:    M1 (EventLogQuerier), M2 (MetricsAggregator)
Risks:      validate_invariants must call EventLogQuerier + MetricsAggregator directly;
            calling MetricsReportHandler would be an I-CHAIN-1 violation.
            Modifying existing validate_invariants.py — existing tests must remain green (CEP-3).
```

### M4: BC-HOOKS + C-1 Compliance — Hook Infrastructure & Event Registration

```text
Spec:       §2.4, §3, §4.9, §5 (I-HOOK-1..4, I-HOOKS-ISO, C-1) — log_tool.py, log_bash.py,
            new event types in core/events.py + reducer.py
BCs:        BC-HOOKS, BC-CORE (C-1 extension), BC-STATE (reducer extension)
Invariants: I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4, I-HOOKS-ISO, C-1 (3 new types)
Tasks:      T-611, T-612, T-613
Depends:    — (independent of M1..M3; uses only infra/event_log.py and core/events.py)
Risks:      C-1 import-time assertion: adding 3 new types to _KNOWN_NO_HANDLER +
            V1_L1_EVENT_TYPES must be done atomically in T-611; the assertion fires on
            import — any partial registration crashes the whole process.
            I-HOOKS-ISO: hooks must NOT be imported — only subprocess.run in tests.
            log_tool.py must always exit 0 — double-failure path (I-HOOK-2, I-HOOK-4)
            requires explicit test coverage.
```

### M5: Phase Integration Verification

```text
Spec:       §5 §PHASE-INV — all Phase 6 invariants must be PASS
BCs:        all Phase 6 BCs
Invariants: I-CHAIN-1, I-QE-1..4, I-MR-1..2, I-M-1-CHECK, I-HOOK-1..4, I-HOOKS-ISO,
            I-PROJ-CONST-1..3, C-1 (ToolUseStarted/ToolUseCompleted/HookError)
Tasks:      T-614
Depends:    M1, M2, M3, M4 (all tasks T-601..T-613 DONE)
Risks:      T-614 is a ValidationReport only — no code produced.
            Existing test_c1_assert_phase5_import must still pass after T-611 changes.
```

---

## Risk Notes

- R-1: **I-CHAIN-1 silent violation.** MetricsReportHandler and check_im1_invariant could
  call QueryEventsHandler instead of EventLogQuerier without a compile-time error. Mitigation:
  explicit tests `test_no_query_handler_in_report` and `test_no_command_handler_in_im1_check`
  (§9, rows 4–5) must be implemented in M2/M3 and run during Validate.

- R-2: **C-1 partial registration crash.** Adding ToolUseStarted/ToolUseCompleted/HookError
  incrementally (e.g., split across subtasks) would trigger the import-time assertion mid-phase.
  Mitigation: T-611 is a single task covering all three types atomically in core/events.py,
  reducer.py, and _KNOWN_NO_HANDLER.

- R-3: **BC-HOOKS isolation break.** If any module in commands/domain/infra imports from hooks/,
  the import graph test and project_profile.yaml grep rule fail. Mitigation: I-HOOKS-ISO grep
  rule added in T-611 ensures CI catches accidental imports.

- R-4: **log_tool.py double-failure path untested.** The sdd_append failure → HookError write
  failure → stderr traceback path is subtle. Mitigation: test_hook_exits_zero_on_double_failure
  and test_hook_logs_stderr_on_double_failure explicitly cover this path (§9, row 6).

- R-5: **M4 order relative to M1..M3.** M4 (BC-HOOKS) is independent of M1..M3 in terms of
  code dependencies. However, T-611 touches core/events.py and reducer.py — same files that
  M1..M3 may read. To avoid merge conflicts, implement M4 after M3 is DONE.
