# Plan_v15 — Phase 15: Kernel Unification & Event-Sourced Control Plane

Status: DRAFT
Spec: specs/Spec_v15_KernelUnification.md

---

## Milestones

### M1: Event & Reducer Foundation — Add Core Infrastructure

```text
Spec:       §2 BC-1 core/events.py; §2 BC-2 reducer.py + projections.py;
            §2 BC-15-REGISTRY (CommandSpec, execute_command);
            §2 BC-15-GUARDS-PIPELINE; §3 Domain Events; §4 Types & Interfaces
BCs:        BC-1, BC-2, BC-15-REGISTRY, BC-15-GUARDS-PIPELINE
Invariants: I-C1-ATOMIC-1, I-PHASE-RESET-1, I-PHASE-STARTED-1, I-PHASE-COMPLETE-1,
            I-PHASE-SEQ-1, I-ES-REPLAY-1, I-REBUILD-STRICT-1, I-REBUILD-EMERGENCY-1,
            I-REBUILD-EMERGENCY-2, I-PIPELINE-HOME-1, I-ATOMICITY-1,
            I-ERROR-1, I-DIAG-1, I-ERROR-L2-1, I-ERROR-SINGLE-TYPE-1,
            I-IDEM-1, I-IDEM-SCHEMA-1, I-IDEM-LOG-1, I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1,
            I-RETRY-POLICY-1, I-PHASE-ORDER-1, I-TRACE-FALLBACK-1,
            I-CONTEXT-HASH-SENTINEL-1, I-TASKSET-ORDER-1
Depends:    — (prerequisite for all subsequent milestones)
Risks:      T-1501 is the highest-risk task — C-1 atomicity rule requires events.py
            and reducer.py to be committed together; partial commit yields ImportError
            at import time; never split T-1501 across two commits.
            T-1506 (registry.py) has the largest surface area — must test execute_command
            in full isolation (tmp_path DuckDB) before any main() wiring.
```

Seven independent tasks build the complete infrastructure without wiring any existing
`main()` call to the new kernel. `pytest tests/ -q` MUST be green after each task.

**T-1501** — `core/events.py` + `domain/state/reducer.py` (single atomic commit):
Add `PhaseStartedEvent`, `TaskSetDefinedEvent`, `ErrorEvent` to `V1_L1_EVENT_TYPES`
(except `ErrorEvent` → `_KNOWN_NO_HANDLER`). Add 4 reducer handlers: PhaseCompleted
(move from `_KNOWN_NO_HANDLER`), PhaseStarted (new, with A-8 soft ordering guard),
TaskSetDefined (new, with A-19 soft ordering guard), PhaseInitialized backward-compat
tasks-reset. C-1 atomicity: both files in one commit.

**T-1502** — `infra/projections.py`:
Add `RebuildMode(STRICT|EMERGENCY)` enum. Simplify `rebuild_state` to pure-reduce
path with STRICT default (YAML not read). Add A-12 env-var gate for EMERGENCY.
Add graceful `rebuild_taskset` missing-file guard (I-ES-REPLAY-1).

**T-1503** — `core/errors.py` (new):
SDDError subclass hierarchy: `GuardViolationError` (1), `InvariantViolationError` (2),
`ExecutionError` (3), `CommitError` (4), `ProjectionError` (5), `StaleStateError` (6),
`KernelInvariantError` (7). `SDDError.error_code: int = 1` backward-compatible field.

**T-1504** — `core/events.py` + `domain/guards/context.py`:
Add `compute_command_id` (32 hex, dataclasses.asdict, payload-only — A-7, A-13, A-22),
`compute_trace_id` (16 hex, head_seq-aware, A-9 None fallback), `compute_context_hash`
(32 hex, A-22). Extend `GuardResult` with optional fields `reason`, `human_reason`,
`violated_invariant` (all `str | None = None` — §0.15(a) backward-compatible).

**T-1505** — `guards/pipeline.py` (new):
Copy `run_guard_pipeline` and `_fetch_events_for_reduce` from `sdd_run.py` into the
new permanent home. `sdd_run.py` retains its copy during this step — deletion is Step 4.
Verify `from sdd.guards.pipeline import run_guard_pipeline` is importable (I-PIPELINE-HOME-1).

**T-1506** — `commands/registry.py` (new):
`CommandSpec` dataclass (frozen), `ProjectionType` enum, `REGISTRY` dict with 6 entries
(`complete`, `validate`, `check-dod`, `activate-phase`, `sync-state`, `record-decision`).
`execute_command` (steps 0–5 per spec §2, including A-7..A-22 hardening).
`project_all` (STRICT only — I-REBUILD-EMERGENCY-1). `execute_and_project` (A-16
PROJECT-stage ErrorEvent). `_make_error_event`, `_write_error_to_audit_log` helpers.
DuckDB schema: add `command_id TEXT` column + `UNIQUE(command_id, event_index)` index
to `events` table (I-IDEM-SCHEMA-1).

**T-1507** — `commands/_base.py`:
Add `NoOpHandler(CommandHandlerBase)` returning `[]`.

---

### M2: Command Routing — Switch Each Command Through the Kernel

```text
Spec:       §2 BC-4 Commands; §2 BC-4 Guards (YAML fallback removal — A-4);
            §7 UC-15-1, UC-15-2, UC-15-5
BCs:        BC-4 Commands (existing)
Invariants: I-2, I-3, I-HANDLER-PURE-1, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1,
            I-SPEC-EXEC-1, I-READ-ONLY-EXCEPTION-1, I-GUARD-CLI-1,
            I-SYNC-NO-PHASE-GUARD-1, I-CMD-PAYLOAD-PHASE-1,
            I-CMD-PHASE-RESOLVE-1, I-HANDLER-BATCH-PURE-1
Depends:    M1 (registry.py must exist and be tested before any main() wiring)
Risks:      Each switch task must leave ALL existing tests green — use existing test suite
            as the safety net. Never purify a handler and wire its main() in the same task
            (I-TASK-SCOPE-1). Step boundary: pytest green required before T-1517/T-1518.
```

Nine tasks, each switching or purifying exactly one command or guard. Tasks within M2
are ordered but independent of tasks in M3/M4.

**T-1510** — `commands/update_state.py` — `sync-state`:
Replace `SyncStateHandler` with `NoOpHandler`; route `update_state.main()` for sync-state
through `execute_and_project(REGISTRY["sync-state"], ...)`.

**T-1511** — `commands/update_state.py` — `complete`:
Purify `CompleteTaskHandler.handle()`: remove `EventStore.append(...)` and
`sync_projections(...)` — return events only. Route `complete` through
`execute_and_project(REGISTRY["complete"], ...)`.

**T-1512** — `commands/update_state.py` — `validate`:
Purify `ValidateTaskHandler.handle()`: remove `EventStore.append(...)` and
`rebuild_state(...)` — return events only. Route `validate` through
`execute_and_project(REGISTRY["validate"], ...)`.

**T-1513** — `commands/update_state.py` — `check-dod`:
Purify `CheckDoDHandler.handle()`: remove `EventStore.append(...)` — return events only.
Route `check-dod` through `execute_and_project(REGISTRY["check-dod"], ...)`.

**T-1514** — `commands/activate_phase.py`:
Emit `PhaseStartedEvent` + optional `TaskSetDefinedEvent(--tasks N)` from
`ActivatePhaseHandler.handle()`. Remove direct `EventStore.append` from `main()`.
Remove `_check_idempotent` (A-14, I-HANDLER-BATCH-PURE-1). Route through
`execute_and_project(REGISTRY["activate-phase"], ...)`.

**T-1515** — `commands/record_decision.py` + `cli.py` (Amendment A-1):
Purify `RecordDecisionHandler.handle()`: remove `EventStore(self._db_path).append(...)`;
return `[DecisionRecordedEvent]`. Add `DecisionRecordedEvent` to `_KNOWN_NO_HANDLER`.
Wire `cli.py record-decision` → `execute_and_project(REGISTRY["record-decision"], ...)`.

**T-1516** — `commands/validate_config.py` + `cli.py` + `commands/__init__.py` + `core/payloads.py` (Amendment A-2):
Delete `ValidateConfigHandler` class and `ValidateConfigCommand` dataclass. Add plain
function `validate_project_config(phase_id: int, config_path: str) -> None`.
Remove `ValidateConfig` from `COMMAND_REGISTRY` in `payloads.py`.
Wire `cli.py validate-config` → direct `validate_project_config(...)` call (no `.handle()`).

**T-1517** — `guards/phase.py` (Amendment A-4):
Remove YAML fallback block (lines 59–65). Missing `--state` arg → exit 1 with JSON error
(CLI-layer error; no ErrorEvent emitted). Guard pipeline itself MUST NOT call `sys.exit`
(I-GUARD-CLI-1).

**T-1518** — `guards/task.py` (Amendment A-4):
Remove YAML fallback block (lines 98–105). Same pattern as T-1517.

---

### M3: CI Enforcement — Grep Rules, AST Tests, Deprecation

```text
Spec:       §2 CI grep-rules (Makefile); §9 checks #17–18, #21–23, #41;
            §8 Integration — CLAUDE.md changes
BCs:        BC-15-REGISTRY (enforcement layer)
Invariants: I-CI-PURITY-1, I-CI-PURITY-2, I-CI-PURITY-3, I-PHASE16-MIGRATION-STRICT-1,
            I-REGISTRY-COMPLETE-1, I-DECISION-AUDIT-1, I-SDDRUN-DEAD-1 (prep),
            I-IMPL-ORDER-1
Depends:    M2 (all commands switched; grep-rules can now enforce the clean state)
Risks:      Whitelist in Makefile MUST contain exactly 2 files (validate_invariants.py,
            report_error.py) — no more; adding a 3rd violates I-PHASE16-MIGRATION-STRICT-1.
            AST test is the primary enforcement; grep rules are secondary — if they disagree,
            AST takes precedence and grep rules MUST be tightened.
```

**T-1519** — `Makefile`:
Add `check-handler-purity` target with 3 grep-rules (I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1,
I-HANDLER-PURE-1). Whitelist = exactly `validate_invariants.py` and `report_error.py`.
Target fails on any violation. Add to default `make` or `make ci` target.

**T-1520** — `tests/unit/test_handler_purity.py` + `tests/unit/test_registry_contract.py` (new):
AST-based purity test: verify no `EventStore` / `rebuild_state` / `.handle(` calls inside
any `handle()` method body (primary enforcement — import-safe, alias-safe).
Registry contract test: `test_registry_write_commands_complete` (I-REGISTRY-COMPLETE-1),
`test_spec_event_schema_matches_handler_types` (I-2), `test_validate_config_is_not_in_registry`
(I-READ-ONLY-EXCEPTION-1), `test_ci_purity_whitelist_count_at_most_two`
(I-PHASE16-MIGRATION-STRICT-1), `test_activate_phase_handler_has_no_check_idempotent` (A-14).

**T-1521** — `commands/sdd_run.py`:
Add structured deprecation comment above `CommandRunner` class:
`# DEPRECATED — Phase 15: superseded by execute_command in commands/registry.py.`
`# Deleted in T-1522. Do not add new callers.`
This is the last touch of `sdd_run.py` before deletion.

---

### M4: Dead Code Deletion + CLAUDE.md Governance

```text
Spec:       §11 Step 4 — Delete; §8 Integration — CLAUDE.md changes
BCs:        BC-15-REGISTRY (cleanup), Governance (docs)
Invariants: I-SDDRUN-DEAD-1, I-1, I-2, I-3
Depends:    M3 (enforcement green; deprecation comment in place)
Risks:      Precondition: grep -rn "CommandRunner" src/sdd/ must return 0 lines.
            If Phase 16 already removed sdd_run.py, verify by ls — task becomes no-op
            for the file but test deletion still applies. CLAUDE.md changes are load-bearing
            for future LLM sessions — §0.5 Status Transition Table changes affect the human
            workflow protocol; must be precise.
```

**T-1522** — `commands/sdd_run.py` (deleted), `commands/__init__.py` (remove imports),
`tests/unit/commands/test_sdd_run.py` (deleted):
Precondition: `grep -rn "CommandRunner" src/sdd/ | wc -l == 0`.
Delete `sdd_run.py` entirely. Remove any import of `CommandRunner` or `run_guard_pipeline`
from `sdd_run` in `__init__.py` or other files. Delete `test_sdd_run.py`.
Run `pytest tests/ -q` → must be green (I-SDDRUN-DEAD-1).
Then update `CLAUDE.md` per §8: §0 add I-1/I-2/I-3/I-SPEC-EXEC-1 above §0.1; §0.5
remove "Direct YAML edit" entries (replace with `sdd activate-phase N`); §0.8 add SEM-10
and SEM-11; §0.10 add `activate-phase --tasks N` row, note all write commands use REGISTRY;
§0.15 add `commands/registry.py`, `guards/pipeline.py`, `core/errors.py` frozen rows;
§0.16 add all Phase 15 invariants; §0.17 (new) Phase FSM + YAML-free transition table;
§0.18 (new) Responsibility Matrix from REGISTRY.actor; §0.19 (new) Error Semantics
quick-reference (error_code table, stage taxonomy, trace_id/context_hash definitions).

---

## Risk Notes

- **R-1: Phase 16 already complete** — Phase 16 (Legacy Architecture Closure) was implemented before Phase 15. Before implementing any M2 tasks, verify which Phase 15 changes are already present in the codebase (e.g., `registry.py` may already exist from Phase 16 work). If so, mark the corresponding task DONE immediately via `sdd complete T-NNNN` without re-implementing.
- **R-2: C-1 atomicity on T-1501** — `PhaseStartedEvent`/`TaskSetDefinedEvent` added to `V1_L1_EVENT_TYPES` without simultaneously adding their reducer handlers causes `ImportError` at import time. T-1501 MUST be a single atomic commit of both `events.py` and `reducer.py`.
- **R-3: State_index.yaml shows phase.current = 0** — The current state snapshot is inconsistent with Phase 15 ACTIVE in Phases_index. The `sdd show-state` output may be unreliable. Human must resolve via `sdd sync-state` or direct YAML correction before any `sdd complete` commands are run.
- **R-4: I-IMPL-ORDER-1 boundary gates** — `pytest tests/ -q` must be green at each Step boundary (after M1, after M2, after M3). Never begin M2 tasks with M1 tests failing; never begin M3 with M2 tests failing.
- **R-5: Whitelist cap** — The CI purity whitelist MUST contain exactly 2 files (`validate_invariants.py`, `report_error.py`). Adding any 3rd file violates I-PHASE16-MIGRATION-STRICT-1 and blocks Phase 16 completion (which is already marked COMPLETE — this is a retroactive constraint; verify Phase 16 TaskSet handled these 2 files).
- **R-6: DuckDB schema migration** — Adding `command_id TEXT` column + `UNIQUE(command_id, event_index)` index (T-1506) to an existing `sdd_events.duckdb` requires an ALTER TABLE or recreate. Must not break existing event data. Legacy rows get `command_id = NULL` (I-IDEM-SCHEMA-1).
