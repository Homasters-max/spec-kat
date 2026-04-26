# ValidationReport — T-2704

Task:   T-2704 — Test suite for command idempotency classification
Spec:   Spec_v27_CommandIdempotency §6 — Verification (BC-CI-5)
Status: PASS

---

## Invariant Checks

| Invariant | Status | Evidence |
|-----------|--------|----------|
| I-CMD-IDEM-1 | PASS | `test_switch_phase_non_idempotent`: 2× uuid4 command_id → 2 события в EventLog; `test_command_spec_idempotent_default`: REGISTRY["switch-phase"].idempotent is False |
| I-IDEM-SCHEMA-1 | PASS | `test_complete_still_idempotent`: 2× одинаковый command_id → 1 событие в EventLog (dedup активен) |
| I-OPTLOCK-1 | PASS | `test_switch_phase_optlock_preserved`: StaleStateError при stale expected_head, даже при idempotent=False |
| I-DB-TEST-1 | PASS | Все тесты используют `tmp_path / "test_sdd_events.duckdb"` — production DB не затронута |
| I-DB-TEST-2 | PASS | autouse `_isolate_sdd_home` + `_guard_production_db` fixtures из conftest.py |

---

## Acceptance

| Criterion | Status |
|-----------|--------|
| `test_switch_phase_non_idempotent` PASS | MET |
| `test_complete_still_idempotent` PASS | MET |
| `test_switch_phase_optlock_preserved` PASS | MET |
| `test_command_spec_idempotent_default` PASS | MET |
| Все 4 теста используют tmp_path DB | MET |

---

## Deviations

Тесты реализованы через EventStore.append напрямую (не через execute_and_project),
поскольку тестируется именно механизм dedup на уровне EventStore (I-IDEM-SCHEMA-1).
Связь с switch-phase обеспечена через `test_command_spec_idempotent_default`,
который верифицирует REGISTRY classification.

---

## Missing

none
