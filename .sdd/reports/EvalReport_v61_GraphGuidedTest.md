# EvalReport — Phase 61: Graph-Guided Implement Enforcement

Phase:  61
Spec:   Spec_v61 §7 — Evaluation Methodology
Status: PASS

---

## Evaluation Scenarios

| ID | Type     | Description                                                    | protocol_satisfied | scope_violations | trace_before_write | anchor_coverage | guard_exit_code | write_exit_code | Verdict | Notes |
|----|----------|----------------------------------------------------------------|--------------------|------------------|--------------------|-----------------|-----------------|-----------------|---------|-------|
| S1 | positive | Normal path — resolve→explain→trace→write                      | True               | 0                | True               | 100% (2/2)      | 0               | 0               | PASS    | session eval-s1: allowed_files=[graph_guard.py, write_gate.py], trace_path=[FILE:graph_guard.py] |
| S2 | negative | Enforcement check — graph-guard exit 1 при отсутствии graph-step | False             | N/A              | N/A                | 0%              | 1               | N/A             | PASS    | session eval-s2: empty allowed_files+trace_path → violations: I-GRAPH-PROTOCOL-1 (×2) |
| S3 | positive | Sparse graph — NOT_FOUND fallback                              | True               | 0                | True               | 100% (1/1)      | 0               | 0               | PASS    | resolve "nonexistent_symbol_xyz_123" → exit 1 NOT_FOUND; fallback to Task Inputs; session eval-s3 |
| S4 | positive | Hidden dependency — trace перед write, явный acknowledgment    | True               | 0                | True               | 100% (2/2)      | 0               | 0               | PASS    | session eval-s4: trace_path=[runtime.py, engine.py]; write allowed |
| S5 | negative | Scope boundary — check-scope exit 1 для файла вне allowed_files | N/A               | 1                | N/A                | N/A             | N/A             | N/A             | PASS    | check-scope read scope_policy.py --inputs runtime.py → exit 1 NORM-SCOPE-002 |
| S6 | positive | Multi-hop — BFS depth ≥2                                       | True               | 0                | True               | 100% (8/8)      | 0               | 0               | PASS    | explain engine.py → 8 FILE nodes (depth 2: engine→assembler→graph/types.py); session eval-s6 |
| S7 | negative | Write without graph — sdd write exit 1 без protocol            | N/A                | N/A              | False              | N/A             | N/A             | 1               | PASS    | session eval-s7: trace_path=[] → write blocked I-TRACE-BEFORE-WRITE |
| S8 | negative | Anchor chain — explain unrelated node не авторизует чтение     | N/A                | 1                | N/A                | N/A             | N/A             | N/A             | PASS    | explain parser.py → allowed=[parser.py, errors.py, navigation.py]; check-scope scope_policy.py → exit 1 |

---

## Invariant Coverage

| Invariant          | Positive scenarios | Negative scenarios | Status  |
|--------------------|-------------------|-------------------|---------|
| I-GRAPH-PROTOCOL-1 | S1✓, S3✓, S4✓, S6✓ | S2✓ (exit 1, 2 violations) | PASS |
| I-SCOPE-STRICT-1   | S1✓, S4✓, S6✓     | S5✓ (exit 1 NORM-SCOPE-002) | PASS |
| I-TRACE-BEFORE-WRITE | S4✓             | S7✓ (write exit 1) | PASS |
| I-GRAPH-GUARD-1    | S1✓ (exit 0)      | S2✓, S7✓ (exit 1)  | PASS |
| I-GRAPH-ANCHOR-CHAIN | S1✓, S4✓        | S8✓ (unrelated explain → scope blocked) | PASS |

---

## Efficiency Metrics (soft)

| Metric                    | Target | Actual  |
|---------------------------|--------|---------|
| avg graph_calls per task  | ≥2     | 2.5 (S1=3, S3=1, S4=3, S6=3 → mean=2.5) |
| anchor_coverage avg       | ≥80%   | 100% (all positive scenarios: full allowed_files coverage) |
| traversal_depth avg       | ≥1.5   | 1.0 (S1=1, S3=0 fallback, S4=1, S6=2 → mean=1.0) — below target (soft) |

---

## Phase 55 Regression

| Check                        | Status  |
|------------------------------|---------|
| `pytest tests/unit/ -q`      | PASS (1374 passed, 2 warnings, 64.72s) |

---

## Verdict

```
Overall: PASS

Evidence:
  positive scenarios (S1, S3, S4, S6): protocol_satisfied=True, scope_violations=0, write_exit_code=0
  negative scenarios (S2, S5, S7, S8): enforcement correctly blocked in all 4 cases
  Phase 55 unit tests: 1374 PASS
  soft metric traversal_depth_avg=1.0 (below 1.5 target) — non-blocking warning

Conditions met:
  PASS ✓ — все 4 positive: protocol_satisfied=True AND scope_viol=0
            AND все 4 negative: enforcement правильно заблокировал
            AND Phase 55 unit tests: PASS
```
