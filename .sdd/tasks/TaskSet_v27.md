# TaskSet_v27 — Phase 27: Command Idempotency Classification

Spec: specs/Spec_v27_CommandIdempotency.md
Plan: plans/Plan_v27.md

---

T-2701: CommandSpec.idempotent field + switch-phase REGISTRY entry

Status:               DONE
Spec ref:             Spec_v27 §3 — CommandSpec расширение (BC-CI-1); §3 switch-phase REGISTRY entry (BC-CI-3)
Invariants:           I-CMD-IDEM-1, I-IDEM-SCHEMA-1
spec_refs:            [Spec_v27 §3 BC-CI-1, Spec_v27 §3 BC-CI-3, I-CMD-IDEM-1]
produces_invariants:  [I-CMD-IDEM-1]
requires_invariants:  [I-KERNEL-EXT-1, I-IDEM-SCHEMA-1]
Inputs:               src/sdd/commands/registry.py
Outputs:              src/sdd/commands/registry.py
Acceptance:           `CommandSpec` содержит поле `idempotent: bool = True`; `REGISTRY["switch-phase"]` имеет `idempotent=False`; все остальные REGISTRY entries имеют `idempotent=True` (явно или по default); `SwitchPhaseHandler` не содержит `_check_idempotent`-логики, которая нарушала бы I-CMD-IDEM-2
Depends on:           —

---

T-2702: execute_command — effective_command_id для non-idempotent команд

Status:               DONE
Spec ref:             Spec_v27 §3 — execute_command Step 5 (BC-CI-2); §5 BC-CI-2 Pre/Post
Invariants:           I-CMD-IDEM-1, I-CMD-NAV-1, I-OPTLOCK-1, I-KERNEL-WRITE-1
spec_refs:            [Spec_v27 §3 BC-CI-2, Spec_v27 §5, I-CMD-IDEM-1, I-OPTLOCK-1]
produces_invariants:  [I-CMD-IDEM-1, I-CMD-NAV-1]
requires_invariants:  [I-CMD-IDEM-1, I-OPTLOCK-1, I-KERNEL-WRITE-1]
Inputs:               src/sdd/commands/registry.py
Outputs:              src/sdd/commands/registry.py
Acceptance:           В `execute_command` Step 5: `effective_command_id = command_id if spec.idempotent else str(uuid4())`; `EventStore.append` вызывается с `command_id=effective_command_id` (никогда не None); `expected_head=head_seq` передаётся без изменений
Depends on:           T-2701

---

T-2703: CLAUDE.md §INV — регистрация новых инвариантов

Status:               DONE
Spec ref:             Spec_v27 §4 — Новые инварианты (BC-CI-4); §4 Temporal semantics
Invariants:           I-CMD-IDEM-1, I-CMD-IDEM-2, I-CMD-NAV-1
spec_refs:            [Spec_v27 §4 BC-CI-4, I-CMD-IDEM-1, I-CMD-IDEM-2, I-CMD-NAV-1]
produces_invariants:  [I-CMD-IDEM-2, I-CMD-NAV-1]
requires_invariants:  [I-CMD-IDEM-1]
Inputs:               CLAUDE.md
Outputs:              CLAUDE.md
Acceptance:           В CLAUDE.md §INV добавлены три строки: I-CMD-IDEM-1, I-CMD-IDEM-2, I-CMD-NAV-1 — формулировки дословно совпадают со Spec_v27 §4; инварианты добавлены после I-PHASE-SNAPSHOT-4
Depends on:           T-2702

---

T-2704: Test suite — 4 теста покрытия I-CMD-IDEM-1, I-IDEM-SCHEMA-1, I-OPTLOCK-1

Status:               DONE
Spec ref:             Spec_v27 §6 — Verification (BC-CI-5); §5 BC-CI-5 Pre/Post
Invariants:           I-CMD-IDEM-1, I-IDEM-SCHEMA-1, I-OPTLOCK-1, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v27 §6 BC-CI-5, I-CMD-IDEM-1, I-IDEM-SCHEMA-1, I-OPTLOCK-1]
produces_invariants:  [I-CMD-IDEM-1]
requires_invariants:  [I-CMD-IDEM-1, I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/commands/registry.py, tests/conftest.py
Outputs:              tests/unit/commands/test_command_idempotency.py
Acceptance:           Файл содержит 4 теста: `test_switch_phase_non_idempotent` (2× switch-phase(A→B) → 2 события в EventLog), `test_complete_still_idempotent` (2× complete → 1 событие), `test_switch_phase_optlock_preserved` (optimistic lock активен при idempotent=False), `test_command_spec_idempotent_default` (все REGISTRY entries кроме switch-phase имеют idempotent=True); все 4 теста PASS; тесты используют tmp_path DB (I-DB-TEST-1)
Depends on:           T-2701, T-2702

---

<!-- Granularity: 10–30 tasks per phase (TG-2). Regroup if exceeded (TG-3). -->
<!-- Every task must be independently implementable and independently testable (TG-1). -->
