# Plan_v4 — Phase 4: Commands Layer

Status: DRAFT
Spec: specs/Spec_v4_Commands.md

---

## Milestones

### M1: Core Event Types + Reducer (C-1 atomic)

```text
Spec:       §3 Domain Events, §8 C-1 Compliance
BCs:        BC-CORE (core/events.py, domain/state/reducer.py, core/errors.py)
Invariants: I-CMD-9, C-1
Tasks:      T-401 (impl), T-402 (tests)
Depends:    Phase 3 baseline (BC-GUARDS, BC-INFRA, BC-STATE already present)
Risks:      C-1 constraint is BLOCKING — events.py + reducer.py MUST be in a single task (T-401);
            splitting causes import-time AssertionError in all downstream modules.
            Also: TaskImplemented / TaskValidated may already be in _EVENT_SCHEMA from Phase 2 —
            verify before writing to avoid duplicate registration.
```

### M2: INFRA Write Path + Projections + EventLog Query Extensions

```text
Spec:       §2.0 Canonical Data Flow, §4.12 EventStore, §4.14 exists_command/exists_semantic/get_error_count,
            §2 BC-INFRA extensions, I-ES-1..5, I-CMD-10, I-CMD-2b
BCs:        BC-INFRA (infra/event_store.py NEW, infra/projections.py NEW, infra/event_log.py extension)
Invariants: I-ES-1, I-ES-2, I-ES-4, I-ES-5, I-CMD-10, I-CMD-2b
Tasks:      T-403 (EventStore), T-404 (tests), T-405 (projections + tests),
            T-406 (event_log extensions), T-407 (tests)
Depends:    M1 (event dataclasses needed for append type signatures)
Risks:      EventStore must use sdd_append_batch internally — direct duckdb.connect is forbidden (I-EL-9);
            projections crash-recovery test (I-ES-5) is mandatory before handlers can depend on rebuild_*.
            exists_semantic payload_hash: canonical_json MUST be stable (sorted keys, no whitespace,
            ISO8601 UTC datetimes, no scientific notation) — property-based test recommended.
```

### M3: CommandHandlerBase + error_event_boundary

```text
Spec:       §4.1 error_event_boundary, §4.2 CommandHandlerBase, I-ERR-1, I-CMD-1..3
BCs:        BC-COMMANDS (commands/_base.py)
Invariants: I-ERR-1, I-CMD-1, I-CMD-2, I-CMD-2b, I-CMD-3
Tasks:      T-408 (impl), T-409 (tests)
Depends:    M2 (exists_command, get_error_count, sdd_append path confirmed)
Risks:      error_event_boundary calls sdd_append(self._db_path, ...) directly — MUST reuse the same
            low-level sdd_append as EventStore.append() internally; any divergence violates I-ERR-1
            and creates a second write path with different transaction semantics.
            Idempotency check MUST run BEFORE the try/except — test this ordering explicitly (T-409).
            If emit itself raises: original exception must survive; fallback_log must fire (I-CMD-3).
```

### M4: State Handlers (CompleteTask, ValidateTask, SyncState, CheckDoD)

```text
Spec:       §4.3–4.6, §6 Pre/Post Conditions, §7 UC-4-1..4, I-CMD-4, I-CMD-5, I-CMD-8
BCs:        BC-COMMANDS (commands/update_state.py), BC-CORE (core/errors.py + DoDNotMet)
Invariants: I-CMD-1, I-CMD-4, I-CMD-5, I-CMD-8, I-ES-2, I-ES-4
Tasks:      T-410 (CompleteTaskHandler), T-411 (tests),
            T-412 (ValidateTaskHandler), T-413 (tests),
            T-414 (SyncStateHandler), T-415 (tests),
            T-416 (CheckDoDHandler + DoDNotMet), T-417 (tests)
Depends:    M1, M2, M3
Risks:      Emit-first invariant (I-ES-1) must be tested with a crash-simulation between append
            and rebuild — handler MUST NOT write files before EventStore.append() (I-ES-2).
            CheckDoDHandler reads state from YAML projection (read-only) — if projection is stale,
            DoD check may pass prematurely; mitigated by pre-run rebuild in CommandRunner (M8).
            DoDNotMet must be in core/errors.py; verify it doesn't conflict with existing SDDError
            subclasses from Phase 1/2.
```

### M5: ValidateInvariants + ValidateConfig Handlers

```text
Spec:       §4.7–4.8, I-CMD-6, I-CMD-13
BCs:        BC-COMMANDS (commands/validate_invariants.py, commands/validate_config.py)
Invariants: I-CMD-1, I-CMD-6, I-CMD-13
Tasks:      T-418 (ValidateInvariantsHandler), T-419 (tests),
            T-420 (ValidateConfigHandler), T-421 (tests)
Depends:    M1, M2, M3
Risks:      ValidateInvariantsHandler is deterministic WITHIN a fixed environment snapshot only —
            cross-environment reproducibility is NOT guaranteed; tests must stub subprocesses to
            avoid environment-dependent test failures.
            env_whitelist MUST NOT fall back to os.environ — test explicitly (I-CMD-13).
            ValidateConfigHandler emits no events — its idempotency is behavioral only; _check_idempotent
            will always return False (by design); re-running is always safe.
```

### M6: ReportError + RecordDecision Handlers

```text
Spec:       §4.9–4.10, §7 UC-4-6, §3 DecisionRecordedEvent usage constraints
BCs:        BC-COMMANDS (commands/report_error.py, commands/record_decision.py)
Invariants: I-CMD-1, I-CMD-9, I-ERR-1
Tasks:      T-422 (both handlers), T-423 (tests)
Depends:    M1, M2, M3
Risks:      ReportErrorHandler sets retry_count=0 always (manual reports are NOT retries); must not
            call get_error_count here.
            RecordDecisionHandler: decision_id MUST match a D-* pattern; summary ≤ 500 chars;
            semantic idempotency keyed on decision_id + phase_id — verify exists_semantic covers this.
```

### M7: DependencyGuard + GuardContext.task_graph + NormCatalog default=DENY

```text
Spec:       §4.13 GuardContext, §4.11 guard pipeline step 3, I-CMD-11, I-CMD-12, I-ES-3
BCs:        BC-GUARDS (domain/guards/dependency_guard.py NEW, domain/guards/context.py extension),
            BC-NORMS (domain/norms/catalog.py — default=DENY enforcement)
Invariants: I-CMD-11, I-CMD-12, I-ES-3, I-GRD-4
Tasks:      T-424 (DependencyGuard + GuardContext.task_graph + NormCatalog DENY default),
            T-425 (tests)
Depends:    M1, Phase 3 guard infrastructure (I-GRD-1..9)
Risks:      DependencyGuard MUST be pure — returns (GuardResult, audit_events), NO I/O (I-ES-3);
            any accidental write from inside the guard bypasses EventStore and violates I-ES-1.
            GuardContext.state must be built from EventLog replay (not YAML projection) for
            DependencyGuard to see authoritative DONE status (I-CMD-11 stale-state fix).
            NormCatalog default=DENY: every currently-passing guard test from Phase 3 may break
            if they relied on implicit ALLOW; audit all Phase 3 guard tests before T-424.
```

### M8: CommandRunner + __init__.py (Integration Milestone)

```text
Spec:       §4.11 CommandRunner, §4.11 run_guard_pipeline, §7 UC-4-5, §8 Integration
BCs:        BC-COMMANDS (commands/sdd_run.py, commands/__init__.py)
Invariants: I-CMD-7, I-ES-3, I-ES-5, I-GRD-4, I-CMD-11, I-CMD-12
Tasks:      T-426 (CommandRunner + __init__.py), T-427 (tests + §PHASE-INV coverage report)
Depends:    M1, M2, M3, M4, M5, M6, M7 (all handlers and guards must exist)
Risks:      Pre-run rebuild (step 1) and post-append rebuild (step 7) serve distinct roles — MUST NOT
            be merged; step 2 builds GuardContext.state from EventLog replay (authoritative), not YAML.
            Full replay is O(N) — acceptable now; snapshot + tail replay is architecturally permitted
            in a future phase but MUST NOT be introduced here (spec §4.11 optimization note).
            run_guard_pipeline MUST be a standalone module-level function for independent testing.
            T-427 must produce ValidationReport_T-427.md covering §PHASE-INV
            [I-ES-1..5, I-CMD-1..13, I-ERR-1].
```

---

## Risk Notes

- R-1: **C-1 atomicity** — `DecisionRecordedEvent` is a new L1 type; `core/events.py` + `domain/state/reducer.py` must be updated in a single task (T-401). Splitting causes import-time `AssertionError`. Mitigated: T-401 explicitly lists both files in Outputs.

- R-2: **error_event_boundary write path** — must call the same low-level `sdd_append` as `EventStore.append()`. A divergent implementation would create a second write path with different transaction semantics, silently breaking the I-ES-1 SSOT guarantee. Mitigated: I-ERR-1 now mandates this explicitly; T-408 must test it at the implementation level.

- R-3: **payload_hash canonical_json** — cross-platform instability (key order, datetime format, floats) produces phantom non-idempotent commands. Mitigated: `canonical_json` spec is locked in §4.14 and I-CMD-2b (sorted keys, no whitespace, ISO8601 UTC, no sci notation); property-based tests in T-407.

- R-4: **Projection staleness in DependencyGuard** — if GuardContext.state is built from a stale YAML projection, DependencyGuard may allow a task whose dependency was just completed. Mitigated: I-CMD-11 mandates EventLog replay for state construction; explicit test in T-425.

- R-5: **NormCatalog default=DENY impact on Phase 3 tests** — adding explicit DENY default may break existing guard tests that relied on implicit ALLOW. Mitigated: audit Phase 3 guard tests before T-424; add explicit ALLOW entries as needed.

- R-6: **ValidateConfigHandler idempotency gap** — handler emits no events, so `_check_idempotent` always returns False. Re-running is safe (pure read-only), but callers must not assume EventLog contains evidence of a prior run. Mitigated: documented in §4.8 as behavioral idempotency by design.
