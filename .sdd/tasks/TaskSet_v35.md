# TaskSet_v35 — Phase 35: Test Harness Elevation

Spec: specs/Spec_v35_TestHarnessElevation.md
Plan: plans/Plan_v35.md

---

T-3501: Refactor test_validate_invariants.py — patch.object → execute_sequence

Status:               DONE
Spec ref:             Spec_v35 §2 BC-35-1 — Idempotency Tests → execute_sequence Double-Call
Invariants:           I-TEST-IDEM-1, I-TEST-BOUNDARY-1
spec_refs:            [Spec_v35 §2 BC-35-1, §5 I-TEST-IDEM-1, §5 I-TEST-BOUNDARY-1]
produces_invariants:  [I-TEST-IDEM-1]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               tests/unit/commands/test_validate_invariants.py
                      tests/harness/api.py (execute_sequence — уже реализован)
                      src/sdd/commands/registry.py (REGISTRY)
Outputs:              tests/unit/commands/test_validate_invariants.py
Acceptance:           grep -rn 'patch.object.*_check_idempotent' tests/unit/commands/test_validate_invariants.py → пусто
                      grep -rn 'execute_sequence' tests/unit/commands/test_validate_invariants.py → непусто
                      pytest tests/unit/commands/test_validate_invariants.py -v → green
Depends on:           —

---

T-3502: Refactor test_check_dod.py — patch.object → execute_sequence

Status:               DONE
Spec ref:             Spec_v35 §2 BC-35-1 — Idempotency Tests → execute_sequence Double-Call
Invariants:           I-TEST-IDEM-1, I-TEST-BOUNDARY-1
spec_refs:            [Spec_v35 §2 BC-35-1, §5 I-TEST-IDEM-1, §5 I-TEST-BOUNDARY-1]
produces_invariants:  [I-TEST-IDEM-1]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               tests/unit/commands/test_check_dod.py
                      tests/harness/api.py
                      src/sdd/commands/registry.py (REGISTRY)
Outputs:              tests/unit/commands/test_check_dod.py
Acceptance:           grep -n 'patch.object.*_check_idempotent' tests/unit/commands/test_check_dod.py → пусто
                      grep -n 'execute_sequence' tests/unit/commands/test_check_dod.py → непусто
                      pytest tests/unit/commands/test_check_dod.py -v → green
Depends on:           T-3501

---

T-3503: Refactor test_validate_timeout.py — patch.object → execute_sequence

Status:               DONE
Spec ref:             Spec_v35 §2 BC-35-1 — Idempotency Tests → execute_sequence Double-Call
Invariants:           I-TEST-IDEM-1, I-TEST-BOUNDARY-1
spec_refs:            [Spec_v35 §2 BC-35-1, §5 I-TEST-IDEM-1, §5 I-TEST-BOUNDARY-1]
produces_invariants:  [I-TEST-IDEM-1]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               tests/unit/commands/test_validate_timeout.py
                      tests/harness/api.py
                      src/sdd/commands/registry.py (REGISTRY)
Outputs:              tests/unit/commands/test_validate_timeout.py
Acceptance:           grep -n 'patch.object.*_check_idempotent' tests/unit/commands/test_validate_timeout.py → пусто
                      grep -n 'execute_sequence' tests/unit/commands/test_validate_timeout.py → непусто
                      grep -n 'subprocess boundary.*intentional' tests/unit/commands/test_validate_timeout.py → непусто
                      pytest tests/unit/commands/test_validate_timeout.py -v → green
Depends on:           T-3501

---

T-3504: Refactor test_amend_plan.py — patch.object → execute_sequence

Status:               DONE
Spec ref:             Spec_v35 §2 BC-35-1 — Idempotency Tests → execute_sequence Double-Call
Invariants:           I-TEST-IDEM-1, I-TEST-BOUNDARY-1
spec_refs:            [Spec_v35 §2 BC-35-1, §5 I-TEST-IDEM-1, §5 I-TEST-BOUNDARY-1]
produces_invariants:  [I-TEST-IDEM-1]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               tests/unit/commands/test_amend_plan.py
                      tests/harness/api.py
                      src/sdd/commands/registry.py (REGISTRY)
Outputs:              tests/unit/commands/test_amend_plan.py
Acceptance:           grep -n 'patch.object.*_check_idempotent' tests/unit/commands/test_amend_plan.py → пусто
                      grep -n 'execute_sequence' tests/unit/commands/test_amend_plan.py → непусто
                      pytest tests/unit/commands/test_amend_plan.py -v → green
Depends on:           T-3501

---

T-3505: Refactor test_validate_invariants_v31.py — patch.object → execute_sequence

Status:               DONE
Spec ref:             Spec_v35 §2 BC-35-1 — Idempotency Tests → execute_sequence Double-Call
Invariants:           I-TEST-IDEM-1, I-TEST-BOUNDARY-1
spec_refs:            [Spec_v35 §2 BC-35-1, §5 I-TEST-IDEM-1, §5 I-TEST-BOUNDARY-1]
produces_invariants:  [I-TEST-IDEM-1]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               tests/unit/commands/test_validate_invariants_v31.py
                      tests/harness/api.py
                      src/sdd/commands/registry.py (REGISTRY)
Outputs:              tests/unit/commands/test_validate_invariants_v31.py
Acceptance:           grep -n 'patch.object.*_check_idempotent' tests/unit/commands/test_validate_invariants_v31.py → пусто
                      grep -n 'execute_sequence' tests/unit/commands/test_validate_invariants_v31.py → непусто
                      pytest tests/unit/commands/test_validate_invariants_v31.py -v → green
Depends on:           T-3501

---

T-3506: Refactor test_sync_state.py — patch.object → execute_sequence

Status:               DONE
Spec ref:             Spec_v35 §2 BC-35-1 — Idempotency Tests → execute_sequence Double-Call (R-3 file)
Invariants:           I-TEST-IDEM-1, I-TEST-BOUNDARY-1
spec_refs:            [Spec_v35 §2 BC-35-1, §5 I-TEST-IDEM-1, §5 I-TEST-BOUNDARY-1]
produces_invariants:  [I-TEST-IDEM-1]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               tests/unit/commands/test_sync_state.py
                      tests/harness/api.py
                      src/sdd/commands/registry.py (REGISTRY)
Outputs:              tests/unit/commands/test_sync_state.py
Acceptance:           grep -n 'patch.object.*_check_idempotent' tests/unit/commands/test_sync_state.py → пусто
                      grep -n 'execute_sequence' tests/unit/commands/test_sync_state.py → непусто
                      pytest tests/unit/commands/test_sync_state.py -v → green
Depends on:           T-3501

---

T-3507: Refactor test_metrics.py — raw SQL assertions → EventLogQuerier

Status:               DONE
Spec ref:             Spec_v35 §2 BC-35-2 — Direct SQL State Assertions → Public EventLog API
Invariants:           I-TEST-STATE-1, I-TEST-BOUNDARY-1
spec_refs:            [Spec_v35 §2 BC-35-2, §5 I-TEST-STATE-1, §5 I-TEST-BOUNDARY-1]
produces_invariants:  [I-TEST-STATE-1]
requires_invariants:  [I-DB-TEST-1]
Inputs:               tests/unit/infra/test_metrics.py
                      src/sdd/infra/event_query.py (EventLogQuerier)
                      src/sdd/infra/projections.py (get_current_state — для справки)
Outputs:              tests/unit/infra/test_metrics.py
Acceptance:           grep -n 'conn.execute.*SELECT.*event_type.*FROM.*events' tests/unit/infra/test_metrics.py → пусто
                      grep -n 'EventLogQuerier\|get_current_state' tests/unit/infra/test_metrics.py → непусто
                      grep -n 'atomicity test.*intentional' tests/unit/infra/test_metrics.py → непусто
                      pytest tests/unit/infra/test_metrics.py -v → green
Depends on:           —

---

T-3508: Final verification — grep checks + full test suite + git diff src/

Status:               DONE
Spec ref:             Spec_v35 §9 Verification — все 9 проверок
Invariants:           I-TEST-IDEM-1, I-TEST-STATE-1, I-TEST-BOUNDARY-1
spec_refs:            [Spec_v35 §9, §6 Post Conditions]
produces_invariants:  [I-TEST-IDEM-1, I-TEST-STATE-1, I-TEST-BOUNDARY-1]
requires_invariants:  [I-TEST-IDEM-1, I-TEST-STATE-1, I-TEST-BOUNDARY-1]
Inputs:               tests/unit/commands/ (все 6 refactored файлов)
                      tests/unit/infra/test_metrics.py
Outputs:              (нет файловых изменений — только верификация)
Acceptance:           grep -rn 'patch.object.*_check_idempotent' tests/unit/commands/ → пусто
                      grep -n 'conn.execute.*SELECT.*event_type.*FROM.*events' tests/unit/infra/test_metrics.py → пусто
                      pytest tests/unit/commands/ tests/unit/infra/test_metrics.py -v → all green
                      git diff src/ → пусто
Depends on:           T-3501, T-3502, T-3503, T-3504, T-3505, T-3506, T-3507

---

<!-- Granularity: 10–30 tasks per phase (TG-2). Regroup if exceeded (TG-3). -->
<!-- Every task must be independently implementable and independently testable (TG-1). -->

---

### Event-Addition Rule (I-EREG-SCOPE-1)

Если Task добавляет новый event type:

THEN Outputs MUST include:
  - src/sdd/core/events.py              (V1_L1_EVENT_TYPES — всегда)
  - src/sdd/domain/state/reducer.py    (ТОЛЬКО если тип имеет handler:
                                        _EVENT_SCHEMA + _fold())

DoD MUST include:
  - test_i_st_10_all_event_types_classified PASS
  - test_i_ereg_1_known_no_handler_is_derived PASS

NOTE: reducer.py НЕ нужен в Outputs для no-handler событий (Spec_v39).
