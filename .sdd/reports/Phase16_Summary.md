# Phase 16 Summary — Legacy Architecture Closure

Status: READY

Date: 2026-04-23  
Spec: Spec_v16_LegacyArchitectureClosure.md  
Metrics: [Metrics_Phase16.md](Metrics_Phase16.md)

---

## Tasks

| Task | Milestone | Description | Status |
|------|-----------|-------------|--------|
| T-1601 | M1 | Fix 4 hardcoded `.sdd/` paths in `cli.py` (I-PATH-1) | DONE |
| T-1602 | M2 | Rewrite `test_adapters.py` → `test_cli_contracts.py` | DONE |
| T-1603 | M2 | Rewrite `test_log_tool_parity.py` (remove deprecated AST checks) | DONE |
| T-1604 | M2 | Update `test_env_independence.py` (deprecated tool references) | DONE |
| T-1605 | M3 | Verify taskset parser — both format branches | DONE |
| T-1606 | M3 | Verify `atomic_write` crash simulation | DONE |
| T-1607 | M3 | Verify norm_catalog stdlib YAML fallback | DONE |
| T-1608 | M3 | Verify `sdd_latest_seq()` coverage in `infra/db.py` | DONE |
| T-1609 | M4 | Dep-audit grep gate (sdd_db, sdd_event_log, shim imports) | DONE |
| T-1610 | M5 | Delete 15 shim files from `_deprecated_tools/` | DONE |
| T-1611 | M5b | Delete 5 uncategorised files (show_state, init_state, norm_catalog, state_yaml, taskset_parser) | DONE |
| T-1612 | M6/M7 | Delete `_deprecated_tools/sdd_run.py` (Layer A adapter) | DONE |
| T-1613 | M6 | Delete `_deprecated_tools/derive_state.py` (covered by `sdd sync-state --dry-run`) | DONE |
| T-1614 | M6 | Add deprecation warning to `src/sdd/domain/state/init_state.py` | DONE |
| T-1615 | M7 | Delete legacy infra files (`sdd_db.py`, `sdd_event_log.py`, remaining) | DONE |
| T-1616 | M8 | Delete `_deprecated_tools/` directory | DONE |
| T-1617 | M9 | CLAUDE.md + `norm_catalog.yaml` cleanup (stale references) | DONE |
| T-1618 | M10 | CLI registration audit → `CLIAudit_Phase16.md` | DONE |
| T-1619 | — | Fix `I-EXEC-ISOL-1`: `event_log.py`, `log_tool.py`, `build_context.py` test isolation | DONE |

**Total: 19/19 DONE**

---

## Invariant Coverage

| Invariant | Statement | Status |
|-----------|-----------|--------|
| I-PATH-1 | No literal `.sdd/` in `src/sdd/**/*.py` except `infra/paths.py` | PASS |
| I-DEPRECATED-RM-1 | `.sdd/_deprecated_tools/` does not exist | PASS |
| I-DEPRECATED-RM-2 | No test imports from `_deprecated_tools/` | PASS* |
| I-DEP-AUDIT-1 | Zero live `sdd_db`/`sdd_event_log` references in `src/` | PASS |
| I-SHIM-CONTRACT-1 | Behavioural contracts covered by `test_cli_contracts.py` | PASS |
| I-LOGIC-COVER-1 | Taskset parser — both format branches tested | PASS |
| I-LOGIC-COVER-2 | `atomic_write` crash simulation tested | PASS |
| I-LOGIC-COVER-3 | `norm_catalog` stdlib YAML fallback tested | PASS |
| I-CLI-REG-1 | All `commands/*.py` with `main()` registered or documented exempt | PASS |
| I-EXEC-ISOL-1 | Tests use `tmp_path`-isolated DuckDB | PASS |
| SDD-11 | No stale `.sdd/tools` references in CLAUDE.md | PASS |

\* 6 test lines reference `_deprecated_tools` as a string constant in exemption logic or in the I-DEP-AUDIT-1 grep test itself — not live imports from the deleted directory. Directory is absent; references are historical guards.

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §0 Goal | covered — all 3 categories delivered (I-PATH-1, test debt, legacy removal) |
| §1 In-Scope (all BCs) | covered — BC-1, BC-TEST, BC-DEP-AUDIT, BC-SHIM-RM, BC-CLEANUP-RM, BC-LEGACY-RESOLVE, BC-LEGACY-RM, BC-DIR-RM, BC-DOCS, BC-CLI-REG, BC-LOGIC-VERIFY |
| §2 Architecture | covered — deletion order enforced (M2 → M3 → M4 → M5 → M5b → M6 → M7 → M8 → M9 → M10) |
| §5 Invariants (new) | covered — all 8 new invariants pass |
| §6 Pre/Post Conditions | covered — all gate conditions verified before each milestone |
| §8 Integration | covered — Phase 15 dependency preserved (`CommandRunner` retained) |
| §10 Out of Scope | respected — `CommandRunner` removal deferred to Phase 15 Step 4; `init_state.py` (src) retained with deprecation warning |

---

## Tests

| Test / Check | Invariant | Status |
|---|---|---|
| `pytest tests/ -q` | all | 493 passed, 0 failed |
| `grep -n '\.sdd/' src/sdd/cli.py` → 0 | I-PATH-1 | PASS |
| `test ! -d .sdd/_deprecated_tools` | I-DEPRECATED-RM-1 | PASS |
| `grep -c '_deprecated_tools' .sdd/norms/norm_catalog.yaml` → 0 | SDD-11 | PASS |
| `grep -c '\.sdd/tools' CLAUDE.md` → 0 | SDD-11 | PASS |
| `sdd validate-invariants --phase 16` | all | exit 0 |
| `CLIAudit_Phase16.md` produced | I-CLI-REG-1 | PASS |

---

## EventLog (Phase 16)

| Event type | Count |
|---|---|
| TaskImplemented | 19 |
| TestRunCompleted | 9 |
| MetricRecorded | 28 |
| StateSynced | 1 |
| **Total** | **57** |

---

## Risks

- R-1: **`_deprecated_tools` string residue in tests.** 6 lines in `test_task_output_invariant.py`, `test_legacy_parity.py`, and `test_db.py` reference `_deprecated_tools` as a string constant — not as import paths. The directory is deleted; these references are guard logic and test infrastructure, not live dependencies. No action required.
- R-2: **`CommandRunner` deferred.** `src/sdd/commands/sdd_run.py` retains `CommandRunner` class and `run_guard_pipeline`. Per Decision 1 (BC-LEGACY-RESOLVE), removal is Phase 15 Step 4 scope. I-SDDRUN-DEAD-1 is NOT a Phase 16 invariant.
- R-3: **`init_state.py` DeprecationWarning.** 3 tests emit `DeprecationWarning` — expected per Decision 3. Full removal deferred to Phase 17+.
- R-4: **`show-spec --phase 16` CLI bug.** `sdd show-spec --phase 16` resolves spec path in `specs_draft/` instead of `specs/`. Spec content read directly from `specs/` per §0.9 (operationally approved). Bug to be fixed in Phase 17.

---

## Decision

READY

All 19 tasks DONE. All Phase 16 invariants PASS. Full test suite green (493 passed). `_deprecated_tools/` directory deleted. `src/sdd` is now the sole runtime with zero I-PATH-1 violations. Phase 16 is complete pending human gate.
