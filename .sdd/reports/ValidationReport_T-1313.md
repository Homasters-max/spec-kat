# ValidationReport T-1313: Static grep and hook smoke verification

**Task:** T-1313  
**Phase:** 13  
**Spec ref:** Spec_v13 §1 STEP 4, §6 STEP 4 Post, §9 (tests 13–14)  
**Invariants:** I-RUNTIME-1, I-LEGACY-0a, I-LEGACY-0b  
**Status:** CONDITIONAL PASS — grep has documentation-only matches; I-RUNTIME-1 not yet in catalog (expected before T-1315)

---

## Acceptance Criterion Evaluation

### Check 1: `grep -r '\.sdd[/\\]tools' src/ tests/`

**Result:** FAIL — 8 matches found

```
src/sdd/guards/scope.py:1:  """sdd.guards.scope — ScopeGuard CLI (Phase 8 re-home of .sdd/tools/check_scope.py).
src/sdd/guards/phase.py:1:  """sdd.guards.phase — PhaseGuard CLI (Phase 8 re-home of .sdd/tools/phase_guard.py).
tests/integration/test_legacy_parity.py:417:  # Test 9: no .sdd/tools in sys.modules (I-TOOL-PATH-1, I-RUNTIME-LINEAGE-1)
tests/unit/test_adapters.py:10:  TOOLS_DIR = Path(".sdd/tools")
tests/unit/test_adapters.py:137:  """Legacy boundary I-LEGACY-0: src/sdd/* must not import from .sdd/tools."""
tests/unit/hooks/test_log_tool_parity.py:1:  """Parity tests: .sdd/tools/log_tool.py must be a thin wrapper of src/sdd/hooks/log_tool.py.
tests/unit/hooks/test_log_tool_parity.py:112:  """I-HOOK-WIRE-1: .sdd/tools/log_tool.py must not contain any sdd_append call (AST check)."""
tests/unit/hooks/test_log_tool_parity.py:123:  """I-HOOK-PATH-1: .sdd/tools/log_tool.py is a Pattern B adapter — delegates to sdd.hooks.log_tool.main."""
```

**Match classification:**

| File | Line | Type | Runtime impact |
|------|------|------|---------------|
| `src/sdd/guards/scope.py` | 1 | Module docstring (historical provenance comment) | None |
| `src/sdd/guards/phase.py` | 1 | Module docstring (historical provenance comment) | None |
| `tests/integration/test_legacy_parity.py` | 417 | Inline comment | None |
| `tests/unit/test_adapters.py` | 10 | `TOOLS_DIR = Path(".sdd/tools")` — test utility variable used to READ adapter files | Test-only (not src/) |
| `tests/unit/test_adapters.py` | 137 | Function docstring | None |
| `tests/unit/hooks/test_log_tool_parity.py` | 1 | Module docstring | None |
| `tests/unit/hooks/test_log_tool_parity.py` | 112 | Function docstring | None |
| `tests/unit/hooks/test_log_tool_parity.py` | 123 | Function docstring | None |

**Analysis:**

- `src/` matches (2): Both are module-level docstrings noting the historical origin of the module. They contain no imports, no subprocess calls, no callable invocations — zero runtime dependency on `.sdd/tools/`.
- `tests/` matches (6): Five are docstrings or comments. One (`test_adapters.py:10`) is a Path construction used in `tests/unit/test_adapters.py` to inspect the legacy adapter files. These tests verify adapter invariants (I-ADAPT-1..4); they read `.sdd/tools/*.py` as text to check properties (no `sys.path` manipulation, `# DEPRECATED` present, etc.). This is a legitimate test that targets the adapter layer — it does not indicate a runtime dependency in `src/sdd/`.

**Verdict on I-RUNTIME-1 (static layer):** The spirit of I-RUNTIME-1 is satisfied. No code in `src/sdd/` imports, subprocess-calls, or resolves at runtime any path under `.sdd/tools/`. The grep matches are exclusively documentation/historical references and test infrastructure that exercises the adapter layer under test. The I-LEGACY-0a and I-LEGACY-0b invariant scans (checks 3 and 4 below) confirm zero violations in `src/sdd/`.

---

### Check 2: `python3 .sdd/tools/validate_invariants.py --check I-RUNTIME-1 --scope full-src`

**Command run:**
```
python3 .sdd/tools/validate_invariants.py --check I-RUNTIME-1 --scope full-src --phase 13
```

**Result:** Exit code 2 — `{"error": "INVARIANT_NOT_FOUND", "invariant": "I-RUNTIME-1"}`

**Analysis:** I-RUNTIME-1 is not yet registered in `.sdd/config/project_profile.yaml` `code_rules.forbidden_patterns`. This is **expected at this point in the task sequence** — T-1315 ("Register new invariants in project_profile.yaml") adds I-RUNTIME-1, I-RUNTIME-LINEAGE-1, and I-TOOL-PATH-1 to the catalog. T-1315 depends on T-1314, which depends on T-1313.

The runtime-dependency aspect of I-RUNTIME-1 that _is_ covered by existing catalog entries:
- **I-LEGACY-0a** (`sys.path` toward `.sdd/`) — registered and checked below (PASS)
- **I-LEGACY-0b** (subprocess calls to `.sdd/tools/`) — registered and checked below (PASS)

**Verdict:** BLOCKED by catalog gap. Not a code violation; resolved by T-1315.

---

### Check 3: `python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0a --scope full-src`

**Command run:**
```
python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0a --scope full-src --phase 13
```

**Result:** Exit code 0 — **PASS**

No `sys.path` manipulation toward `.sdd/` found in `src/sdd/`.

---

### Check 4: `python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0b --scope full-src`

**Command run:**
```
python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0b --scope full-src --phase 13
```

**Result:** Exit code 0 — **PASS**

No subprocess calls to `.sdd/tools/` found in `src/sdd/`.

---

## Invariant Coverage Summary

| Invariant | Check | Result | Notes |
|-----------|-------|--------|-------|
| I-RUNTIME-1 (static grep) | grep `\.sdd[/\\]tools` in src/+tests/ | FAIL | All matches are docstrings/comments or test utility code — zero runtime impact in src/ |
| I-RUNTIME-1 (catalog) | validate_invariants --check I-RUNTIME-1 | BLOCKED (exit 2) | Not in catalog yet; resolved by T-1315 |
| I-LEGACY-0a | validate_invariants --check I-LEGACY-0a | PASS | |
| I-LEGACY-0b | validate_invariants --check I-LEGACY-0b | PASS | |

## Convergence with T-1312

T-1312 (kill test) confirmed I-RUNTIME-1 at the filesystem layer: blocking `.sdd/tools/` with `chmod 000` caused zero additional test failures (443 tests passed). Combined with I-LEGACY-0a PASS and I-LEGACY-0b PASS, all three runtime-dependency verification layers converge on the same conclusion: **`src/sdd/` has no runtime dependency on `.sdd/tools/`**.

---

## Required Actions Before T-1314

The following items must be resolved before proceeding to T-1314 (archive `.sdd/tools/`):

1. **Grep matches in docstrings** (optional cleanup): The two docstrings in `src/sdd/guards/scope.py:1` and `src/sdd/guards/phase.py:1` can be updated to remove the `.sdd/tools` reference (e.g., `Phase 8 re-home of check_scope.py`). This is cosmetic but would make the grep check strict-pass.

2. **`tests/unit/test_adapters.py`**: After T-1314 archives `.sdd/tools/`, the `TOOLS_DIR = Path(".sdd/tools")` path will resolve to `.sdd/_deprecated_tools/` instead. The test suite owner should decide whether `test_adapters.py` should be updated to reflect the archive path or removed (since adapters are deprecated).

3. **I-RUNTIME-1 catalog registration**: Done by T-1315 (no action needed here).

---

## Decision

**Task T-1313 status: CONDITIONAL PASS**

The verification work is complete. No runtime dependency on `.sdd/tools/` exists in `src/sdd/` — confirmed by three independent layers (filesystem kill test T-1312, I-LEGACY-0a scan, I-LEGACY-0b scan). The grep letter-of-the-law failures are documentation references and test utility code, not src/ runtime dependencies.

Human supervisor should decide: proceed to T-1314 with documented caveats, or clean up the docstring references first.
