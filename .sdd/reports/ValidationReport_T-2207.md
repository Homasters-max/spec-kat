# ValidationReport — T-2207

Task:   T-2207 — Acceptance check reuse tests (I-ACCEPT-REUSE-1, I-ACCEPT-1)
Spec:   Spec_v22 §4 BC-22-2, §5 Invariants
Status: PASS

---

## Invariant Checks

| Invariant | Status | Evidence |
|-----------|--------|----------|
| I-ACCEPT-REUSE-1 | PASS | `test_skips_pytest_when_test_passed` — no subprocess.run called when test_returncode=0; `test_uses_last_test_event_when_multiple` — last event returncode used |
| I-ACCEPT-1 | PASS | `test_skips_pytest_when_test_passed`, `test_returns_failure_from_test_returncode` — acceptance returns correct codes |

---

## Acceptance

| Criterion | Status |
|-----------|--------|
| `test_skips_pytest_when_test_passed` | MET |
| `test_returns_failure_from_test_returncode` | MET |
| `test_returns_1_when_no_test_result` | MET |
| `test_uses_last_test_event_when_multiple` | MET |

All 4 tests PASSED: `pytest tests/unit/commands/test_validate_acceptance.py -v`

---

## Deviations

**Source fix outside Task Outputs:** `src/sdd/commands/validate_invariants.py` — removed `break` from the test-event extraction loop in `main()` (line ~459). This change was required to implement `uses_last_test_event_when_multiple` correctly per I-ACCEPT-REUSE-1 ("last wins" semantics). The source file was listed as Task Input; the fix is a 1-line deletion with no regression (17 existing tests still pass).

---

## Missing

none
