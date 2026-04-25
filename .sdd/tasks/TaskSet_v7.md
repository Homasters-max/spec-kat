# TaskSet_v7 — Phase 7: Hardening

Spec: specs/Spec_v7_Hardening.md
Plan: plans/Plan_v7.md

---

T-701: Reducer pre-filter — named constants + _pre_filter()

Status:               DONE
Spec ref:             Spec_v7 §2.1 — BC-STATE Extension (I-REDUCER-1); §4.6 — reducer pre-filter interface
Invariants:           I-REDUCER-1, I-REDUCER-WARN
spec_refs:            [Spec_v7 §2.1, Spec_v7 §4.6, I-REDUCER-1, I-REDUCER-WARN]
produces_invariants:  [I-REDUCER-1, I-REDUCER-WARN]
requires_invariants:  [I-ST-2, I-EL-3]
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/infra/db.py, src/sdd/core/events.py
Outputs:              src/sdd/domain/state/reducer.py
Acceptance:           Module-level constants _REDUCER_REQUIRES_SOURCE and _REDUCER_REQUIRES_LEVEL exist; _pre_filter() is called at the top of EventReducer.reduce() before any dispatch; SDDState is unchanged when meta or L2/L3 events are passed alongside runtime L1 events.
Depends on:           —

---

T-702: Tests — test_reducer_hardening.py (7 tests)

Status:               DONE
Spec ref:             Spec_v7 §5 — I-REDUCER-1 / I-REDUCER-WARN invariant table; §9 — Verification row 1
Invariants:           I-REDUCER-1, I-REDUCER-WARN
spec_refs:            [Spec_v7 §5, Spec_v7 §9, I-REDUCER-1, I-REDUCER-WARN]
produces_invariants:  []
requires_invariants:  [I-REDUCER-1, I-REDUCER-WARN]
Inputs:               src/sdd/domain/state/reducer.py
Outputs:              tests/unit/domain/state/test_reducer_hardening.py
Acceptance:           All 7 tests pass: test_meta_events_filtered, test_l2_events_filtered, test_l3_events_filtered, test_only_runtime_l1_dispatched, test_pre_filter_constants_named, test_state_identical_with_without_meta, test_misclassified_l1_event_type_warns.
Depends on:           T-701

---

T-703: BC-INFRA — batch_id column + sdd_append_batch uuid injection

Status:               DONE
Spec ref:             Spec_v7 §2.2 — BC-INFRA Extension (I-EL-12); §4.1 EventRecord update; §4.2 sdd_append_batch update
Invariants:           I-EL-12
spec_refs:            [Spec_v7 §2.2, Spec_v7 §4.1, Spec_v7 §4.2, I-EL-12]
produces_invariants:  [I-EL-12]
requires_invariants:  [I-EL-9, I-EL-11, I-PK-1]
Inputs:               src/sdd/infra/db.py, src/sdd/infra/event_log.py
Outputs:              src/sdd/infra/db.py, src/sdd/infra/event_log.py
Acceptance:           ALTER TABLE events ADD COLUMN IF NOT EXISTS batch_id TEXT DEFAULT NULL is present in open_sdd_connection(); sdd_append_batch generates one uuid4() per call and stamps it on all events in the batch; sdd_append sets batch_id=NULL.
Depends on:           —

---

T-704: BC-INFRA — QueryFilters batch_id + is_batched + SQL WHERE clauses

Status:               DONE
Spec ref:             Spec_v7 §2.2 — BC-INFRA Extension (I-EL-12 query side); §4.3 QueryFilters update
Invariants:           I-EL-12
spec_refs:            [Spec_v7 §2.2, Spec_v7 §4.3, I-EL-12]
produces_invariants:  [I-EL-12]
requires_invariants:  [I-QE-1, I-QE-2, I-QE-3, I-QE-4, I-EL-12]
Inputs:               src/sdd/infra/event_query.py, src/sdd/infra/db.py
Outputs:              src/sdd/infra/event_query.py
Acceptance:           QueryFilters has batch_id: str | None = None and is_batched: bool | None = None fields; EventLogQuerier.query() generates AND batch_id = ? for exact match, AND batch_id IS NOT NULL for is_batched=True, AND batch_id IS NULL for is_batched=False, and no clause for None.
Depends on:           T-703

---

T-705: Tests — test_batch_id.py (9 tests)

Status:               DONE
Spec ref:             Spec_v7 §5 — I-EL-12 invariant table; §9 — Verification row 2
Invariants:           I-EL-12
spec_refs:            [Spec_v7 §5, Spec_v7 §9, I-EL-12]
produces_invariants:  []
requires_invariants:  [I-EL-12]
Inputs:               src/sdd/infra/db.py, src/sdd/infra/event_log.py, src/sdd/infra/event_query.py
Outputs:              tests/unit/infra/test_batch_id.py
Acceptance:           All 9 tests pass: test_batch_id_column_exists, test_batch_id_set_on_batch_append, test_batch_id_null_on_single_append, test_batch_id_uuid_unique_per_call, test_batch_id_same_within_one_call, test_batch_id_filter_exact, test_is_batched_true_filter, test_is_batched_false_filter, test_is_batched_none_no_filter.
Depends on:           T-703, T-704

---

T-706: BC-CORE — register_l1_event_type + _check_c1_consistency + SDD_C1_MODE

Status:               DONE
Spec ref:             Spec_v7 §2.3 — BC-CORE Extension (I-REG-1 + I-C1-MODE-1); §4.4 register_l1_event_type; §4.5 _check_c1_consistency
Invariants:           I-REG-1, I-REG-STATIC-1, I-C1-MODE-1
spec_refs:            [Spec_v7 §2.3, Spec_v7 §4.4, Spec_v7 §4.5, I-REG-1, I-REG-STATIC-1, I-C1-MODE-1]
produces_invariants:  [I-REG-1, I-REG-STATIC-1, I-C1-MODE-1]
requires_invariants:  [C-1]
Inputs:               src/sdd/core/events.py
Outputs:              src/sdd/core/events.py
Acceptance:           register_l1_event_type() atomically updates V1_L1_EVENT_TYPES + exactly one of _EVENT_SCHEMA or _KNOWN_NO_HANDLER and calls _check_c1_consistency(); bare import-time assert replaced by _check_c1_consistency() call at module level; SDD_C1_MODE env var controls strict (AssertionError) vs warn (logging.warning) behavior.
Depends on:           —

---

T-707: Tests — test_event_registry.py (9 tests)

Status:               DONE
Spec ref:             Spec_v7 §5 — I-REG-1 / I-REG-STATIC-1 / I-C1-MODE-1 invariant table; §9 — Verification row 3
Invariants:           I-REG-1, I-REG-STATIC-1, I-C1-MODE-1
spec_refs:            [Spec_v7 §5, Spec_v7 §9, I-REG-1, I-REG-STATIC-1, I-C1-MODE-1]
produces_invariants:  []
requires_invariants:  [I-REG-1, I-REG-STATIC-1, I-C1-MODE-1]
Inputs:               src/sdd/core/events.py
Outputs:              tests/unit/core/test_event_registry.py
Acceptance:           All 9 tests pass: test_register_with_handler, test_register_without_handler, test_register_duplicate_raises, test_c1_consistent_after_registration, test_c1_strict_mode_raises, test_c1_warn_mode_does_not_raise, test_existing_c1_assert_replaced, test_module_import_does_not_raise_in_warn_mode, test_register_only_at_import_time_convention.
Depends on:           T-706

---

T-708: BC-HOOKS — src/sdd/hooks/log_tool.py canonical stdin-JSON implementation

Status:               DONE
Spec ref:             Spec_v7 §2.4 — BC-HOOKS Hardening (I-HOOK-WIRE-1 + I-HOOK-PARITY-1); §4.x hook interfaces; UC-7-4
Invariants:           I-HOOK-WIRE-1, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4
spec_refs:            [Spec_v7 §2.4, I-HOOK-WIRE-1, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4]
produces_invariants:  [I-HOOK-WIRE-1, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4]
requires_invariants:  [I-HOOKS-ISO, I-EL-9]
Inputs:               src/sdd/hooks/log_tool.py, src/sdd/infra/event_log.py, src/sdd/infra/db.py, src/sdd/core/events.py
Outputs:              src/sdd/hooks/log_tool.py
Acceptance:           src/sdd/hooks/log_tool.py reads json.load(sys.stdin); contains canonical _extract_inputs() and _extract_output() logic per-tool; handles HookErrorEvent on failure (I-HOOK-4); exits 0 unconditionally (I-HOOK-2); uses event_source="meta" (I-HOOK-1); ToolUseStarted/Completed at L2, HookError at L3 (I-HOOK-3).
Depends on:           T-703, T-706

---

T-709: BC-HOOKS — .sdd/tools/log_tool.py thin wrapper + test_log_tool_parity.py (7 tests)

Status:               DONE
Spec ref:             Spec_v7 §2.4 — BC-HOOKS Hardening (I-HOOK-WIRE-1 + I-HOOK-PATH-1 + I-HOOK-PARITY-1); §9 — Verification row 4
Invariants:           I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1
spec_refs:            [Spec_v7 §2.4, Spec_v7 §9, I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1]
produces_invariants:  [I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1]
requires_invariants:  [I-HOOK-WIRE-1, I-HOOK-2]
Inputs:               .sdd/tools/log_tool.py, src/sdd/hooks/log_tool.py
Outputs:              .sdd/tools/log_tool.py, tests/unit/hooks/test_log_tool_parity.py
Acceptance:           .sdd/tools/log_tool.py contains no sdd_append call (AST check); path resolved via Path(__file__).resolve().parents[2] / "src" (I-HOOK-PATH-1); all 7 parity tests pass asserting equal row count and identical fields (event_type, event_source, level, tool_name, payload excl. timestamp_ms): test_tools_hook_is_thin_wrapper, test_tools_hook_path_resolution, test_parity_pre_bash, test_parity_post_bash, test_parity_pre_read, test_parity_pre_write, test_parity_failure_path.
Depends on:           T-708

---

T-710: Phase validation — ValidationReport_T-710.md covering §PHASE-INV ×9

Status:               DONE
Spec ref:             Spec_v7 §5 — §PHASE-INV (all 9 invariants must be PASS); §9 — Verification summary
Invariants:           I-REDUCER-1, I-REDUCER-WARN, I-EL-12, I-REG-1, I-REG-STATIC-1, I-C1-MODE-1, I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1
spec_refs:            [Spec_v7 §5, Spec_v7 §9]
produces_invariants:  []
requires_invariants:  [I-REDUCER-1, I-REDUCER-WARN, I-EL-12, I-REG-1, I-REG-STATIC-1, I-C1-MODE-1, I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1]
Inputs:               src/sdd/domain/state/reducer.py, tests/unit/domain/state/test_reducer_hardening.py, src/sdd/infra/db.py, src/sdd/infra/event_log.py, src/sdd/infra/event_query.py, tests/unit/infra/test_batch_id.py, src/sdd/core/events.py, tests/unit/core/test_event_registry.py, src/sdd/hooks/log_tool.py, .sdd/tools/log_tool.py, tests/unit/hooks/test_log_tool_parity.py
Outputs:              .sdd/reports/ValidationReport_T-710.md
Acceptance:           ValidationReport confirms all 9 §PHASE-INV invariants PASS; full test suite passes (pytest exit 0); no lint violations in task outputs; report covers each invariant with test evidence.
Depends on:           T-701, T-702, T-703, T-704, T-705, T-706, T-707, T-708, T-709

---

T-711: Fix tests/unit/hooks/test_log_tool.py — sync to stdin JSON protocol + I-HOOK-API-1

Status:               DONE
Spec ref:             Spec_v7 §2.4 — BC-HOOKS Hardening; I-HOOK-WIRE-1, I-HOOK-PARITY-1
Invariants:           I-HOOK-API-1, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4
spec_refs:            [Spec_v7 §2.4, I-HOOK-WIRE-1, I-HOOK-PARITY-1, I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4]
produces_invariants:  [I-HOOK-API-1]
requires_invariants:  [I-HOOK-1, I-HOOK-2, I-HOOK-3, I-HOOK-4]
Inputs:               tests/unit/hooks/test_log_tool.py, src/sdd/hooks/log_tool.py
Outputs:              tests/unit/hooks/test_log_tool.py
Acceptance:           _run() uses input=json.dumps(payload) with no positional args; all 10 existing tests pass; test_hook_rejects_argv added and passes (returncode==0, no events in DB — I-HOOK-API-1); pytest tests/unit/hooks/test_log_tool.py -q exits 0; no changes to src/sdd/hooks/log_tool.py.
Depends on:           T-710

---

T-712: Lint fix — 4 auto-fixable violations in Phase 7 source files

Status:               DONE
Spec ref:             Spec_v7 §2.1, §2.3, §2.2 (code quality)
Invariants:           —
spec_refs:            []
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/core/events.py, src/sdd/domain/state/reducer.py, src/sdd/infra/event_log.py
Outputs:              src/sdd/core/events.py, src/sdd/domain/state/reducer.py, src/sdd/infra/event_log.py
Acceptance:           ruff check src/sdd/core/events.py src/sdd/domain/state/reducer.py src/sdd/infra/event_log.py exits 0; existing tests still pass; no logic changes.
Depends on:           T-711
