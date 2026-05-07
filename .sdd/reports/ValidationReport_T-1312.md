# ValidationReport T-1312: Run filesystem kill test (chmod 000 → pytest → restore)

**Task:** T-1312  
**Phase:** 13  
**Spec ref:** Spec_v13 §1 STEP 4, §6 STEP 4 Post, §9 (test 12)  
**Invariants:** I-RUNTIME-1  
**Status:** PASS (kill test confirms I-RUNTIME-1)

---

## Acceptance Criterion Evaluation

### Step 1: chmod -R 000 .sdd/tools/ && pytest tests/ --tb=short

**Result:** Exit code 1 (4 pre-existing failures, none caused by chmod 000)

**Kill test verdict: PASS** — blocking `.sdd/tools/` at filesystem level caused zero additional test failures.

Baseline comparison (same 4 tests fail with chmod 000 restored):
| Test | Fails with chmod 000 | Fails without chmod 000 |
|------|---------------------|------------------------|
| `test_hook_error_event_level_l3` | YES | YES |
| `test_hook_emits_error_event_on_failure` | YES | YES |
| `test_hook_logs_stderr_on_double_failure` | YES | YES |
| `test_cli_is_pure_router` | YES | YES |

**Conclusion:** `.sdd/tools/` has zero runtime dependency. I-RUNTIME-1 is satisfied at the filesystem layer.

### Pre-existing failures (not caused by T-1312)

**443 tests pass. 4 pre-existing failures:**

1. `tests/unit/hooks/test_log_tool.py::test_hook_error_event_level_l3`  
   Assertion: `len(errors) == 1` but got 0. Hook error event not emitted.

2. `tests/unit/hooks/test_log_tool.py::test_hook_emits_error_event_on_failure`  
   Assertion: `len(errors) == 1` but got 0. Same root cause.

3. `tests/unit/hooks/test_log_tool.py::test_hook_logs_stderr_on_double_failure`  
   Assertion: `"double failure" in result.stderr` — stderr contains DuckDB error, not the expected string.

4. `tests/unit/test_cli.py::test_cli_is_pure_router`  
   Forbidden import `sdd.infra.projections` at line 40 of `cli.py`. Introduced by T-1311 (added projection support to CLI).

These 4 failures are independent of the filesystem kill test and pre-date T-1312.

### Step 2: chmod -R 755 .sdd/tools/ (restore)

**Result:** DONE. `.sdd/tools/` permissions restored immediately after pytest run.

### Step 3: sdd query-events --event ToolUseStarted --limit 1

**Result:** 
```
87	ToolUseStarted	None	runtime
```
Recent events confirmed in DuckDB. Event logging operational.

---

## Invariant Verification

| Invariant | Verified | Result |
|-----------|----------|--------|
| I-RUNTIME-1 | chmod 000 .sdd/tools/ — no additional test failures | **PASS** |

---

## Summary

T-1312 is complete. The filesystem kill test confirms that `src/sdd/` is the sole runtime — blocking `.sdd/tools/` at the OS level has zero effect on the test suite. I-RUNTIME-1 holds. The 4 pre-existing failures are unrelated to this task and were present before T-1312 execution.
