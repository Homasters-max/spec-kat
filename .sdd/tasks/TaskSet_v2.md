# TaskSet_v2 — Phase 2: State & Context

Spec: specs/Spec_v2_State.md
Plan: plans/Plan_v2.md

---

## T-201: Task dataclass + parse_taskset() implementation

Status:               DONE
Spec ref:             Spec_v2 §4.7 — Task dataclass and parse_taskset
Invariants:           I-TS-1, I-TS-2, I-TS-3
spec_refs:            [Spec_v2 §4.7, I-TS-1, I-TS-2, I-TS-3]
produces_invariants:  [I-TS-1, I-TS-2, I-TS-3]
requires_invariants:  []
Inputs:               src/sdd/core/errors.py
Outputs:              src/sdd/domain/tasks/parser.py
Checks:               ruff check src/sdd/domain/tasks/parser.py, mypy src/sdd/domain/tasks/parser.py
Acceptance:           mypy src/sdd/domain/tasks/parser.py exits 0; Task dataclass is frozen with all 10 fields; parse_taskset raises MissingContext on absent file and on no ## T-NNN headers
Depends on:           —

---

## T-202: domain/tasks/__init__.py + test_parser.py

Status:               DONE
Spec ref:             Spec_v2 §4.7, §9 verification row 5 — parser tests
Invariants:           I-TS-1, I-TS-2, I-TS-3
spec_refs:            [Spec_v2 §4.7, §9]
produces_invariants:  []
requires_invariants:  [I-TS-1, I-TS-2, I-TS-3]
Inputs:               src/sdd/domain/tasks/parser.py
Outputs:              src/sdd/domain/tasks/__init__.py, tests/unit/domain/tasks/__init__.py, tests/unit/domain/tasks/test_parser.py
Checks:               pytest tests/unit/domain/tasks/test_parser.py -q
Acceptance:           pytest tests/unit/domain/tasks/test_parser.py -q: all 6 tests PASS (test_parse_task_has_spec_fields, test_parse_missing_optional_fields_default_empty, test_parse_is_deterministic, test_parse_missing_file_raises, test_parse_malformed_no_headers_raises, test_parse_done_status)
Depends on:           T-201

---

## T-203: reducer.py — SDDState, ReducerDiagnostics, EventReducer (complete)

Status:               DONE
Spec ref:             Spec_v2 §4.1, §4.2, §4.3 — SDDState, ReducerDiagnostics, EventReducer
Invariants:           I-ST-1, I-ST-2, I-ST-7, I-ST-8, I-ST-9, I-ST-10, I-ST-11, I-EL-3, I-EL-13
spec_refs:            [Spec_v2 §4.1, §4.2, §4.3, I-ST-1, I-ST-2, I-ST-7, I-ST-8, I-ST-9, I-ST-10, I-ST-11, I-EL-3, I-EL-13]
produces_invariants:  [I-ST-1, I-ST-2, I-ST-7, I-ST-9, I-ST-10, I-ST-11, I-EL-3, I-EL-13]
requires_invariants:  []
Inputs:               src/sdd/core/errors.py, src/sdd/core/events.py
Outputs:              src/sdd/domain/state/reducer.py
Checks:               ruff check src/sdd/domain/state/reducer.py, mypy src/sdd/domain/state/reducer.py
Acceptance:           mypy src/sdd/domain/state/reducer.py exits 0; SDDState is frozen dataclass; reduce([])==EMPTY_STATE; (a) strict_mode=True raises UnknownEventType on unrecognised event_type — verified structurally by asserting UnknownEventType is subclass of SDDError and is raised before state mutation; (b) _EVENT_SCHEMA validation fires before handler dispatch — missing required payload field in strict_mode raises UnknownEventType (schema error extension per Spec_v2 §4.3); (c) dedup: repeated TaskImplemented for same task_id increments tasks_completed exactly once and tasks_done_ids contains no duplicates — set-based internal accumulator, not list append; (d) EventReducer._KNOWN_NO_HANDLER | frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES — completeness identity holds as class invariant
Depends on:           —

---

## T-204: tests/unit/domain/state/test_reducer.py

Status:               DONE
Spec ref:             Spec_v2 §9 verification row 1 — reducer tests (16 tests)
Invariants:           I-EL-3, I-EL-13, I-ST-1, I-ST-2, I-ST-7, I-ST-9, I-ST-10
spec_refs:            [Spec_v2 §9, I-EL-3, I-EL-13, I-ST-1, I-ST-2, I-ST-7, I-ST-9, I-ST-10]
produces_invariants:  []
requires_invariants:  [I-ST-1, I-ST-2, I-ST-7, I-ST-9, I-ST-10, I-EL-3, I-EL-13]
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/core/events.py
Outputs:              tests/unit/domain/state/__init__.py, tests/unit/domain/state/test_reducer.py
Checks:               pytest tests/unit/domain/state/test_reducer.py -q
Acceptance:           pytest tests/unit/domain/state/test_reducer.py -q: all 16 tests PASS (test_reduce_empty_returns_empty_state, test_reduce_filters_meta_events, test_reduce_filters_non_l1, test_reduce_state_derivation_has_no_handler, test_reduce_task_implemented_deduplicates, test_reduce_task_implemented_increments_count, test_reduce_phase_completed_sets_status, test_reduce_is_deterministic, test_reduce_unknown_type_counted_in_diagnostics, test_reduce_strict_mode_raises_on_unknown, test_reduce_strict_mode_raises_on_missing_schema_field, test_reduce_incremental_equivalent_to_full, test_all_l1_events_classified, test_reduce_assumes_sorted_input, test_state_hash_excludes_human_fields, test_state_hash_includes_reducer_version)
Depends on:           T-203

---

## T-205: core/events.py — PhaseInitializedEvent + StateDerivationCompletedEvent dataclasses

Status:               DONE
Spec ref:             Spec_v2 §3 — domain events; §4.1 (StateDerivationCompletedEvent payload)
Invariants:           I-EL-3
spec_refs:            [Spec_v2 §3, §4.1]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/core/events.py
Outputs:              src/sdd/core/events.py
Checks:               ruff check src/sdd/core/events.py, mypy src/sdd/core/events.py
Acceptance:           PhaseInitializedEvent(frozen dataclass, fields: phase_id, tasks_total, plan_version, actor, timestamp) and StateDerivationCompletedEvent(frozen dataclass, fields: phase_id, tasks_total, tasks_completed, derived_from, timestamp) are importable from sdd.core.events; mypy exits 0
Depends on:           —

---

## T-206: yaml_state.py — read_state + write_state

Status:               DONE
Spec ref:             Spec_v2 §4.4, §6 pre/post conditions — read_state, write_state
Invariants:           I-ST-3, I-ST-8, I-ST-11
spec_refs:            [Spec_v2 §4.4, §6, I-ST-3, I-ST-8, I-ST-11]
produces_invariants:  [I-ST-3, I-ST-8, I-ST-11]
requires_invariants:  [I-ST-11]
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/infra/audit.py, src/sdd/core/errors.py
Outputs:              src/sdd/domain/state/yaml_state.py
Checks:               ruff check src/sdd/domain/state/yaml_state.py, mypy src/sdd/domain/state/yaml_state.py
Acceptance:           mypy src/sdd/domain/state/yaml_state.py exits 0; write_state uses atomic_write; read_state recomputes and verifies state_hash; raises MissingState on absent file; raises Inconsistency on hash mismatch
Depends on:           T-203

---

## T-207: tests/unit/domain/state/test_yaml_state.py

Status:               DONE
Spec ref:             Spec_v2 §9 verification row 2 — yaml_state tests (8 tests)
Invariants:           I-ST-3, I-ST-8, I-ST-11
spec_refs:            [Spec_v2 §9, I-ST-3, I-ST-8, I-ST-11]
produces_invariants:  []
requires_invariants:  [I-ST-3, I-ST-8, I-ST-11]
Inputs:               src/sdd/domain/state/yaml_state.py, src/sdd/domain/state/reducer.py
Outputs:              tests/unit/domain/state/test_yaml_state.py
Checks:               pytest tests/unit/domain/state/test_yaml_state.py -q
Acceptance:           pytest tests/unit/domain/state/test_yaml_state.py -q: all 8 tests PASS (test_read_write_roundtrip, test_read_missing_raises_missing_state, test_write_uses_atomic_write, test_state_hash_verified_on_read, test_state_hash_mismatch_raises_inconsistency, test_state_hash_excludes_human_fields, test_state_hash_includes_reducer_version, test_human_fields_preserved_in_roundtrip)
Depends on:           T-206

---

## T-208: sync.py — sync_state algorithm

Status:               DONE
Spec ref:             Spec_v2 §4.5, §6 pre/post conditions — sync_state
Invariants:           I-ST-4, I-ST-6, I-EL-9
spec_refs:            [Spec_v2 §4.5, §6, I-ST-4, I-ST-6, I-EL-9]
produces_invariants:  [I-ST-4, I-ST-6, I-EL-9]
requires_invariants:  [I-ST-3, I-TS-1, I-TS-2]
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/domain/state/yaml_state.py, src/sdd/domain/tasks/parser.py, src/sdd/core/events.py, src/sdd/infra/event_log.py, src/sdd/core/errors.py
Outputs:              src/sdd/domain/state/sync.py
Checks:               ruff check src/sdd/domain/state/sync.py, mypy src/sdd/domain/state/sync.py
Acceptance:           mypy src/sdd/domain/state/sync.py exits 0; (a) EventLog is the SOLE authoritative source: tasks_completed and tasks_done_ids in new_state are derived exclusively from reduce(replay_fn()) — NOT from TaskSet DONE count; TaskSet is used only for tasks_total and cross-validation (I-ST-4, I-ST-6); (b) emit callable called exactly once with a StateDerivationCompletedEvent(derived_from="eventlog") — verified by inspecting call_count and event payload, not by string search; (c) no direct duckdb.connect call in sync.py (grep confirms — I-EL-9); (d) replay_fn has injectable signature with default=sdd_replay; raises Inconsistency when TaskSet DONE count diverges from EventLog tasks_completed
Depends on:           T-201, T-203, T-205, T-206

---

## T-209: tests/unit/domain/state/test_sync.py

Status:               DONE
Spec ref:             Spec_v2 §9 verification row 3 — sync tests (7 tests)
Invariants:           I-ST-4, I-ST-6, I-EL-9
spec_refs:            [Spec_v2 §9, I-ST-4, I-ST-6, I-EL-9]
produces_invariants:  []
requires_invariants:  [I-ST-4, I-ST-6, I-EL-9]
Inputs:               src/sdd/domain/state/sync.py, src/sdd/domain/state/reducer.py, src/sdd/domain/state/yaml_state.py
Outputs:              tests/unit/domain/state/test_sync.py
Checks:               pytest tests/unit/domain/state/test_sync.py -q
Acceptance:           pytest tests/unit/domain/state/test_sync.py -q: all 7 tests PASS (test_sync_uses_eventlog_for_task_counts, test_sync_raises_inconsistency_on_divergence, test_sync_preserves_phase_fields, test_sync_emits_state_derivation_event, test_sync_no_direct_db_calls, test_sync_replay_fn_injectable, test_sync_absent_yaml_uses_reducer_defaults)
Depends on:           T-208

---

## T-210: init_state.py — init_state algorithm

Status:               DONE
Spec ref:             Spec_v2 §4.6, §6 pre/post conditions — init_state
Invariants:           I-ST-5, I-EL-9
spec_refs:            [Spec_v2 §4.6, §6, I-ST-5, I-EL-9]
produces_invariants:  [I-ST-5]
requires_invariants:  [I-TS-1, I-ST-3]
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/domain/state/yaml_state.py, src/sdd/domain/tasks/parser.py, src/sdd/core/events.py, src/sdd/core/errors.py
Outputs:              src/sdd/domain/state/init_state.py
Checks:               ruff check src/sdd/domain/state/init_state.py, mypy src/sdd/domain/state/init_state.py
Acceptance:           mypy src/sdd/domain/state/init_state.py exits 0; no sdd_replay call in file; raises InvalidState if state_path exists; emits PhaseInitializedEvent then StateDerivationCompletedEvent exactly once each
Depends on:           T-201, T-203, T-205, T-206

---

## T-211: tests/unit/domain/state/test_init_state.py + domain/state/__init__.py

Status:               DONE
Spec ref:             Spec_v2 §9 verification row 4, §2 BC-STATE __init__.py re-exports
Invariants:           I-ST-5, I-EL-9
spec_refs:            [Spec_v2 §9, §2, I-ST-5, I-EL-9]
produces_invariants:  []
requires_invariants:  [I-ST-5, I-EL-9]
Inputs:               src/sdd/domain/state/init_state.py, src/sdd/domain/state/reducer.py, src/sdd/domain/state/yaml_state.py, src/sdd/domain/state/sync.py
Outputs:              tests/unit/domain/state/test_init_state.py, src/sdd/domain/state/__init__.py
Checks:               pytest tests/unit/domain/state/test_init_state.py -q
Acceptance:           pytest tests/unit/domain/state/test_init_state.py -q: all 5 tests PASS (test_init_state_creates_yaml, test_init_state_raises_if_exists, test_init_state_counts_match_taskset, test_init_state_emits_phase_initialized_then_derivation, test_init_state_no_db_calls); domain/state/__init__.py re-exports all public symbols including StateDerivationCompletedEvent
Depends on:           T-207, T-209, T-210

---

## T-212: build_context.py — staged context builder (complete)

Status:               DONE
Spec ref:             Spec_v2 §4.8, §5 I-CTX-1..6 — build_context layers, hash, budget
Invariants:           I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6
spec_refs:            [Spec_v2 §4.8, §5, I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6]
produces_invariants:  [I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6]
requires_invariants:  [I-ST-3, I-TS-1]
Inputs:               src/sdd/domain/state/yaml_state.py, src/sdd/domain/tasks/parser.py, src/sdd/infra/config_loader.py, src/sdd/core/errors.py
Outputs:              src/sdd/context/build_context.py
Checks:               ruff check src/sdd/context/build_context.py, mypy src/sdd/context/build_context.py
Acceptance:           mypy src/sdd/context/build_context.py exits 0; (a) context_hash: output first line is structurally a <!-- context_hash: {64-hex-chars} --> comment — verified by parsing the line and asserting len(hexdigest)==64, not by regex on arbitrary strings; (b) budget: len(output.split()) <= EFFECTIVE_BUDGET[depth] holds for all three depth values — verified arithmetically against the constant, not against a hardcoded number; (c) coder isolation: the parsed output contains exactly one task block whose task_id matches the requested id — verified by counting Task objects reconstructable from output, not by scanning for T-NNN substrings; (d) planner isolation: no layer-3 data present — verified by asserting the output contains no block parseable as a task row (inputs/outputs/status fields), not by header string match; (e) layer order: layers 0–8 are appended strictly ascending — verified by recording layer index at each append call and asserting the sequence is monotone
Depends on:           T-201, T-203, T-206

---

## T-213: context/__init__.py + tests/unit/context/test_build_context.py

Status:               DONE
Spec ref:             Spec_v2 §9 verification row 6, §2 BC-CONTEXT __init__.py re-exports
Invariants:           I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6
spec_refs:            [Spec_v2 §9, §2, I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6]
produces_invariants:  []
requires_invariants:  [I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6]
Inputs:               src/sdd/context/build_context.py
Outputs:              src/sdd/context/__init__.py, tests/unit/context/__init__.py, tests/unit/context/test_build_context.py
Checks:               pytest tests/unit/context/test_build_context.py -q
Acceptance:           pytest tests/unit/context/test_build_context.py -q: all 12 tests PASS (test_build_context_is_deterministic, test_build_context_pure_no_io_writes, test_context_within_token_budget_all_depths, test_coder_context_includes_task_row, test_coder_context_excludes_other_tasks, test_planner_context_includes_spec_and_plan, test_planner_context_excludes_task_rows, test_context_hash_present_in_output, test_context_hash_changes_on_file_change, test_context_hash_sorted_file_paths, test_layer_order_is_ascending, test_truncation_at_paragraph_boundary); context/__init__.py re-exports build_context, ContextDepth, TOKEN_BUDGET, EFFECTIVE_BUDGET
Depends on:           T-212

---

## T-214: domain/tasks/__init__.py validation + domain/state integration smoke

Status:               DONE
Spec ref:             Spec_v2 §1 scope, §8 integration — 80%+ coverage check for M1..M4 modules
Invariants:           I-TS-1, I-ST-1, I-CTX-1
spec_refs:            [Spec_v2 §1, §8]
produces_invariants:  []
requires_invariants:  [I-TS-1, I-TS-2, I-TS-3, I-ST-1, I-ST-2, I-CTX-1]
Inputs:               src/sdd/domain/tasks/__init__.py, src/sdd/domain/state/__init__.py, src/sdd/context/__init__.py
Outputs:              src/sdd/domain/__init__.py
Checks:               pytest tests/unit/ -q --co -q, ruff check src/sdd/, mypy src/sdd/
Acceptance:           (a) public API importable — python -c "from sdd.domain.state import SDDState, reduce, sync_state, init_state, StateDerivationCompletedEvent; from sdd.domain.tasks import Task, parse_taskset; from sdd.context import build_context, ContextDepth, TOKEN_BUDGET, EFFECTIVE_BUDGET" exits 0 with no ImportError; (b) BC boundary: grep -n "from sdd.infra" src/sdd/domain/tasks/parser.py returns empty — BC-TASKS has no infra dependency; grep -n "from sdd.context" src/sdd/domain/state/ returns empty — BC-STATE does not import BC-CONTEXT; (c) ruff check src/sdd/ exits 0; mypy src/sdd/ exits 0; (d) pytest tests/unit/ --co -q lists all Phase 2 test functions without collection errors — verified by exit code 0 and non-zero collected count
Depends on:           T-202, T-211, T-213

---

## T-215: pytest coverage run + §PHASE-INV report

Status:               DONE
Spec ref:             Spec_v2 §5 §PHASE-INV, §9 verification — all invariants PASS + coverage >= 80%
Invariants:           I-EL-3, I-EL-13, I-ST-1, I-ST-2, I-ST-3, I-ST-4, I-ST-5, I-ST-6, I-ST-7, I-ST-8, I-ST-9, I-ST-10, I-ST-11, I-TS-1, I-TS-2, I-TS-3, I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6
spec_refs:            [Spec_v2 §5, §9]
produces_invariants:  [I-EL-3, I-EL-13, I-ST-1, I-ST-2, I-ST-3, I-ST-4, I-ST-5, I-ST-6, I-ST-7, I-ST-8, I-ST-9, I-ST-10, I-ST-11, I-TS-1, I-TS-2, I-TS-3, I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6]
requires_invariants:  [I-EL-3, I-EL-13, I-ST-1, I-ST-2, I-ST-3, I-ST-4, I-ST-5, I-ST-6, I-ST-7, I-ST-8, I-ST-9, I-ST-10, I-ST-11, I-TS-1, I-TS-2, I-TS-3, I-CTX-1, I-CTX-2, I-CTX-3, I-CTX-4, I-CTX-5, I-CTX-6]
Inputs:               tests/unit/domain/tasks/test_parser.py, tests/unit/domain/state/test_reducer.py, tests/unit/domain/state/test_yaml_state.py, tests/unit/domain/state/test_sync.py, tests/unit/domain/state/test_init_state.py, tests/unit/context/test_build_context.py
Outputs:              .sdd/reports/ValidationReport_T-215.md
Checks:               pytest tests/unit/domain/ tests/unit/context/ -q --cov=src/sdd --cov-report=term-missing
Acceptance:           pytest exits 0; coverage for src/sdd/domain/tasks/, src/sdd/domain/state/, src/sdd/context/ >= 80%; all §PHASE-INV invariants PASS; ValidationReport_T-215.md written with PASS for all 22 invariants
Depends on:           T-204, T-207, T-209, T-211, T-213, T-214

---

<!-- Granularity: 15 tasks (TG-2 range 10–30). Each task independently implementable and testable (TG-1). -->
<!-- Milestone mapping: T-201..T-202 → M1 | T-203..T-204 → M2 | T-205..T-211 → M3 | T-212..T-213 → M4 | T-214..T-215 → M5 -->
