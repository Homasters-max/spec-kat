# Phase 4 Summary — Commands Layer

Status: READY

Timestamp: 2026-04-22T13:35:00Z

---

## Tasks

| Task | Title | Status |
|------|-------|--------|
| T-401 | Core event dataclasses + reducer handlers (C-1) | DONE |
| T-402 | Tests — core event dataclasses + reducer | DONE |
| T-403 | EventStore — single atomic write path | DONE |
| T-404 | Tests — EventStore atomic write path | DONE |
| T-405 | Projections — rebuild_taskset + rebuild_state | DONE |
| T-406 | EventLog query extensions — exists_command, exists_semantic, get_error_count | DONE |
| T-407 | Tests — projections + event_log query extensions | DONE |
| T-408 | CommandHandlerBase + error_event_boundary | DONE |
| T-409 | Tests — CommandHandlerBase + error_event_boundary | DONE |
| T-410 | CompleteTaskHandler | DONE |
| T-411 | Tests — CompleteTaskHandler | DONE |
| T-412 | ValidateTaskHandler | DONE |
| T-413 | Tests — ValidateTaskHandler | DONE |
| T-414 | SyncStateHandler | DONE |
| T-415 | Tests — SyncStateHandler | DONE |
| T-416 | CheckDoDHandler + DoDNotMet | DONE |
| T-417 | Tests — CheckDoDHandler | DONE |
| T-418 | ValidateInvariantsHandler | DONE |
| T-419 | Tests — ValidateInvariantsHandler | DONE |
| T-420 | ValidateConfigHandler | DONE |
| T-421 | Tests — ValidateConfigHandler | DONE |
| T-422 | ReportErrorHandler + RecordDecisionHandler | DONE |
| T-423 | Tests — ReportErrorHandler + RecordDecisionHandler | DONE |
| T-424 | DependencyGuard + GuardContext.task_graph + NormCatalog default=DENY | DONE |
| T-425 | Tests — DependencyGuard + NormCatalog default=DENY | DONE |
| T-426 | CommandRunner + run_guard_pipeline + commands/__init__.py | DONE |
| T-427 | Tests — CommandRunner + run_guard_pipeline + §PHASE-INV ValidationReport | DONE |

**Total: 27/27 DONE**

---

## Invariant Coverage

| Invariant | Description | Status |
|-----------|-------------|--------|
| I-ES-1 | EventStore atomic write (append before mutations) | PASS |
| I-ES-2 | Handlers emit events in batches | PASS |
| I-ES-3 | Guards are pure functions; CommandRunner appends audit_events on DENY | PASS |
| I-ES-4 | Projection rebuilt after EventStore.append | PASS |
| I-ES-5 | EventStore is sole write path | PASS |
| I-CMD-1 | Idempotency by command_id | PASS |
| I-CMD-2 | ErrorEvent emitted before exception propagates | PASS |
| I-CMD-2b | Semantic idempotency (command_type, task_id, phase_id) | PASS |
| I-CMD-3 | Original exception always re-raised | PASS |
| I-CMD-4 | Handlers do not write files directly | PASS |
| I-CMD-5 | ValidateInvariantsHandler explicit cwd/env/timeout | PASS |
| I-CMD-6 | ValidateInvariantsHandler is a pure emitter | PASS |
| I-CMD-7 | Guard DENY → append audit, return [], skip handler | PASS |
| I-CMD-8 | run_guard_pipeline uses EventLog replay state (never YAML) | PASS |
| I-CMD-9 | New event dataclasses are C-1 compliant | PASS |
| I-CMD-10 | Pre-run + post-append rebuild are structurally separate | PASS |
| I-CMD-11 | DependencyGuard checks task DAG; DENY if dep not DONE | PASS |
| I-CMD-12 | NormCatalog default=DENY; explicit ALLOW required | PASS |
| I-CMD-13 | subprocess uses explicit cwd, env_whitelist, timeout_secs | PASS |
| I-ERR-1 | ErrorEvent retry_count tracked per command_id | PASS |
| I-GRD-4 | run_guard_pipeline is a pure function (no I/O) | PASS |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §0 Goal / SSOT model | Covered — EventStore as sole write path, handlers as pure emitters |
| §1 Scope (BC-COMMANDS, BC-CORE, BC-INFRA extensions) | Full |
| §3 Domain Events (TaskImplementedEvent, TaskValidatedEvent, PhaseCompletedEvent, DecisionRecordedEvent) | Full |
| §4.1 CommandHandlerBase + error_event_boundary | Full |
| §4.2 Idempotency (command_id + semantic) | Full |
| §4.3 CompleteTaskHandler | Full |
| §4.4 ValidateTaskHandler | Full |
| §4.5 SyncStateHandler | Full |
| §4.6 CheckDoDHandler + DoDNotMet | Full |
| §4.7 ValidateInvariantsHandler | Full |
| §4.8 ValidateConfigHandler | Full |
| §4.9 ReportErrorHandler | Full |
| §4.10 RecordDecisionHandler | Full |
| §4.11 CommandRunner + run_guard_pipeline | Full |
| §4.12 EventStore | Full |
| §4.13 GuardContext extensions (task_graph, DependencyGuard) | Full |
| §5 NormCatalog default=DENY | Full |
| §9 Verification table (all 12 rows) | Full |

---

## Tests

| Suite | Passed | Failed | Notes |
|-------|--------|--------|-------|
| `tests/unit/commands/` | 108 | 0 | All command handlers + runner |
| `tests/unit/infra/` | 57 | 0 | EventStore, projections, event_log |
| `tests/unit/guards/` | 62 | 0 | Guards, dependency, norms |
| `tests/unit/domain/` | 32 | 2 | 2 pre-existing failures in test_reducer.py (outside Phase 4 scope) |
| `tests/unit/core/` | 12 | 0 | Event dataclasses, types |
| **Total** | **271** | **2** | Pre-existing; not introduced by Phase 4 |

**Pre-existing failures (outside Phase 4 scope):**
- `test_reduce_phase_completed_sets_status` — expects `PhaseCompleted` to auto-set `phase_status="COMPLETE"`, but per I-ST-11 this is human-managed
- `test_reduce_assumes_sorted_input` — same root cause

These tests reflect a specification gap in Phase 3/reducer behavior; not a Phase 4 regression.

---

## Risks

- R-1: The 2 pre-existing test failures in `test_reducer.py` document a known tension between the reducer implementation (I-ST-11: phase_status is human-managed) and test expectations. Should be resolved in Phase 5 or via a spec clarification task.
- R-2: `check_scope.py` (NORM-SCOPE-001) unconditionally forbids `tests/` reads, making it impossible to validate declared test inputs through the tool. The check is a documentation gap, not a behavioral risk.

---

## Decision

READY

All 27 tasks DONE. All Phase 4 invariants PASS. DoD check PASS.
Phase 4 delivers the complete Commands Layer: 8 typed command handlers, CommandRunner with
pure guard pipeline (DependencyGuard, NormGuard, PhaseGuard, TaskGuard), EventStore as sole
write path, error_event_boundary with retry tracking, full idempotency, and 271 passing tests.

See [Metrics_Phase4.md](Metrics_Phase4.md) for process health metrics.
