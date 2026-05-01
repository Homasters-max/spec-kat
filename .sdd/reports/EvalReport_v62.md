# EvalReport — Phase 62: Graph Semantic Hardening

Phase:  62
Spec:   Spec_v62 §7 — Evaluation Methodology (Часть 2), §9 Acceptance Criteria
Status: PASS

---

## Evaluation Scenarios (S9–S15)

| ID  | Invariant              | Type     | Description                                                   | guard_exit_code | write_exit_code | Verdict | Notes |
|-----|------------------------|----------|---------------------------------------------------------------|-----------------|-----------------|---------|-------|
| S9  | I-TRACE-RELEVANCE-1    | negative | write_target ∉ trace_path → write_gate exit 1                | N/A             | 1               | PASS    | write_gate: file "eval_deep.py" not in trace_path → I-TRACE-RELEVANCE-1 blocked |
| S10 | I-FALLBACK-STRICT-1    | negative | fallback_used + allowed_files пусто → graph_guard exit 1      | 1               | N/A             | PASS    | graph_guard: fallback_used=True, allowed_files=∅ → I-FALLBACK-STRICT-1 + I-GRAPH-PROTOCOL-1 violations |
| S11 | I-GRAPH-DEPTH-1        | negative | traversal_depth_max=1, depth_justification="" → exit 1        | 1               | N/A             | PASS    | graph_guard: depth=1, no justification → I-GRAPH-DEPTH-1 violation |
| S12 | I-GRAPH-COVERAGE-REQ-1 | negative | write_target ∉ trace_path ∪ explain_nodes → exit 1            | 1               | N/A             | PASS    | graph_guard: write_target="eval_deep.py" not in trace ∪ explain → I-GRAPH-COVERAGE-REQ-1 |
| S13 | I-EXPLAIN-USAGE-1      | negative | explain_node ∉ trace_path ∪ write_targets → exit 1            | 1               | N/A             | PASS    | graph_guard: explain_node="eval_deep.py" not in trace ∪ write_targets → I-EXPLAIN-USAGE-1 |
| S14 | all                    | positive | depth=2, targets covered, explain used, no fallback → exit 0  | 0               | N/A             | PASS    | graph_guard: all invariants satisfied, single node covers trace+explain+write |
| S15 | I-FALLBACK-STRICT-1    | positive | fallback_used + task_inputs (allowed_files) заданы → exit 0   | 0               | N/A             | PASS    | graph_guard: fallback_used=True, allowed_files non-empty → no violation |

---

## Invariant Coverage

| Invariant              | Positive scenarios | Negative scenarios | Status |
|------------------------|--------------------|--------------------|--------|
| I-TRACE-RELEVANCE-1    | S14✓ (implicit)    | S9✓ (exit 1)       | PASS   |
| I-FALLBACK-STRICT-1    | S15✓ (exit 0)      | S10✓ (exit 1)      | PASS   |
| I-GRAPH-DEPTH-1        | S14✓ (depth=2)     | S11✓ (exit 1)      | PASS   |
| I-GRAPH-COVERAGE-REQ-1 | S14✓ (target in trace) | S12✓ (exit 1) | PASS   |
| I-EXPLAIN-USAGE-1      | S14✓ (explain in trace) | S13✓ (exit 1) | PASS   |

---

## Test Execution

| Command                                         | Result              |
|-------------------------------------------------|---------------------|
| `pytest tests/integration/test_eval_s9_s15.py` | 7 passed in 0.42s   |

---

## Verdict

```
Overall: PASS

Evidence:
  negative scenarios (S9–S13): enforcement correctly returned exit 1 in all 5 cases
  positive scenarios (S14–S15): correct protocol → exit 0 in both cases
  No PENDING items

Conditions met:
  PASS ✓ — S9–S13: all 5 enforcement checks blocked correctly (exit 1)
            AND S14–S15: full protocol + fallback-with-inputs → exit 0
```
