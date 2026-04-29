# Plan_v49 — Phase 49: Session Dedup Fixes

Status: DRAFT
Spec: specs/Spec_v49_SessionDedupFixes.md

---

## Logical Context

type: patch
anchor_phase: 48
rationale: "Fixes three regressions found during smoke-verification of Phase 48 (T-4813): INFO-log dedup not visible in terminal (BC-49-A); sdd invalidate-event incorrectly rejects SessionDeclared via I-INVALID-4 (BC-49-B); RecordSessionHandler may veto the kernel's emit decision and violates I-HANDLER-PURE-1 (BC-49-C)."

---

## Milestones

### M1: CLI Logging — BC-49-A

```text
Spec:       §2 Architecture / BC-49-A, §6 Pre/Post BC-49-A
BCs:        BC-49-A
Invariants: I-CLI-LOG-LEVEL-1
Depends:    — (independent)
Risks:      logging.basicConfig() must be called in the cli() group callback before
            any subcommand dispatches; calling it inside a subcommand is too late.
```

Add `logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")`
to the `@click.group()` callback in `src/sdd/cli.py`. This makes INFO-level messages
emitted by `registry.py` via `_log.info(...)` appear in stderr.

Files: `src/sdd/cli.py`

### M2: EventReducer.is_invalidatable() — BC-49-B

```text
Spec:       §2 Architecture / BC-49-B, §4 Types & Interfaces BC-49-B, §6 Pre/Post BC-49-B
BCs:        BC-49-B
Invariants: I-INVALID-AUDIT-ONLY-1, I-AUDIT-ONLY-SSOT-1, I-INVALIDATABLE-INTERFACE-1
Depends:    — (independent)
Risks:      _AUDIT_ONLY_EVENTS must live in reducer.py only (I-AUDIT-ONLY-SSOT-1);
            state-mutating events (e.g. PhaseInitialized) must still be blocked by I-INVALID-4.
```

Two sub-steps:
1. In `src/sdd/infra/reducer.py`: add `_AUDIT_ONLY_EVENTS: ClassVar[frozenset[str]] = frozenset({"SessionDeclared"})` and classmethod `is_invalidatable(event_type: str) -> bool` to `EventReducer`. The method returns `True` if type is unknown or in `_AUDIT_ONLY_EVENTS`; `False` if in `_EVENT_SCHEMA` but NOT in `_AUDIT_ONLY_EVENTS` (state-mutating).
2. In `src/sdd/commands/invalidate_event.py`: replace the direct `_EVENT_SCHEMA` check (I-INVALID-4 guard) with a call to `EventReducer.is_invalidatable(target_type)`.

Files: `src/sdd/infra/reducer.py`, `src/sdd/commands/invalidate_event.py`

### M3: Pure Handler — BC-49-C

```text
Spec:       §2 Architecture / BC-49-C, §4 Types & Interfaces BC-49-C, §6 Pre/Post BC-49-C
BCs:        BC-49-C
Invariants: I-HANDLER-SESSION-PURE-1, I-DEDUP-KERNEL-AUTHORITY-1, I-HANDLER-PURE-1 (restored)
Depends:    — (independent of M2; kernel dedup path via build_sessions_view() already correct)
Risks:      After deletion of _session_declared_today(), dedup must rely entirely on kernel
            Step 2.5 (SessionDedupPolicy); verify projector.py:412-416 filters invalidated seqs.
```

In `src/sdd/commands/record_session.py`:
- Delete `_session_declared_today()` method entirely (lines ~53-73 per spec §4).
- Remove `from sdd.infra.db import open_sdd_connection` if no longer used.
- Simplify `handle()` to a pure function: always returns `[SessionDeclaredEvent(...)]` without IO.

Files: `src/sdd/commands/record_session.py`

### M4: Tests and Smoke Verification

```text
Spec:       §9 Verification
BCs:        BC-49-A, BC-49-B, BC-49-C
Invariants: all Phase 49 invariants
Depends:    M1, M2, M3
Risks:      UC-49-3 (re-emit after invalidation) requires both BC-49-B and BC-49-C;
            run it last after all BCs are implemented.
```

Unit tests (11 tests per §9 Verification table):
- `test_cli_basicconfig_called_before_subcommand` — I-CLI-LOG-LEVEL-1
- `test_cli_info_log_visible_in_stderr` — I-CLI-LOG-LEVEL-1
- `test_audit_only_events_in_reducer_contains_session_declared` — I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1
- `test_is_invalidatable_returns_true_for_session_declared` — I-INVALIDATABLE-INTERFACE-1, I-INVALID-AUDIT-ONLY-1
- `test_is_invalidatable_returns_false_for_state_mutating` — I-INVALID-4, I-INVALIDATABLE-INTERFACE-1
- `test_is_invalidatable_returns_true_for_unknown_type` — I-INVALIDATABLE-INTERFACE-1
- `test_invalidate_session_declared_succeeds` — I-INVALID-AUDIT-ONLY-1
- `test_invalidate_state_mutating_still_blocked` — I-INVALID-4 (preserved)
- `test_handler_handle_returns_event_without_io` — I-HANDLER-SESSION-PURE-1, I-HANDLER-PURE-1
- `test_handler_handle_is_pure_no_db_call` — I-HANDLER-SESSION-PURE-1
- `test_reemit_after_invalidation_creates_new_event` — I-DEDUP-KERNEL-AUTHORITY-1, I-SESSION-INVALIDATION-1

Smoke verification (3 scenarios per §9):
- UC-49-1: `sdd record-session ... 2>&1 | grep "Session deduplicated"` → exit 0
- UC-49-2: `sdd invalidate-event --seq <SessionDeclared_seq> --force` → exit 0
- UC-49-3: re-emit after invalidate → 2 SessionDeclared events in event_log

Files: `tests/unit/commands/test_record_session_dedup.py` (existing, extend),
       `tests/unit/infra/test_projector_sessions.py` (existing, extend),
       new test files as appropriate.

---

## Risk Notes

- R-1: **Audit-only SSOT** — `_AUDIT_ONLY_EVENTS` must exist only in `reducer.py`. Any future audit-only event type must be added there. Violation of I-AUDIT-ONLY-SSOT-1 creates silent divergence between dedup classification and invalidation logic.
- R-2: **Handler purity** — After BC-49-C, the only dedup path is kernel Step 2.5. If `build_sessions_view()` or `SessionDedupPolicy` has a bug, there is no handler-level safety net. This is intentional per the spec's architectural rationale; correctness of Step 2.5 was verified in Phase 48.
- R-3: **Logging side effect** — `logging.basicConfig()` is idempotent only if no handlers have been configured. In test environments, if pytest captures or pre-configures logging, the call may be a no-op. Tests for I-CLI-LOG-LEVEL-1 must account for this.
- R-4: **I-INVALID-4 regression** — BC-49-B changes the guard logic. Must verify that state-mutating events (e.g. `PhaseInitialized`, `TaskCompleted`) are still correctly blocked after the refactor.
