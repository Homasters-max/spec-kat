# TaskSet_v61 — Phase 61: Graph-Guided Implement Enforcement + Evaluation

Spec: specs/Spec_v61_GraphEnforcement.md
Plan: plans/Plan_v61.md

---

## M1: Patches & Environment

---

T-6101: Add --edge-types flag to sdd trace

Status:               DONE
Spec ref:             Spec_v61 §1 Scope — BC-61-P1
Invariants:           I-ENGINE-EDGE-FILTER-1
spec_refs:            [Spec_v61 §1, BC-61-P1, I-ENGINE-EDGE-FILTER-1]
produces_invariants:  [I-ENGINE-EDGE-FILTER-1]
requires_invariants:  []
Inputs:               src/sdd/cli.py, src/sdd/graph_navigation/cli/trace.py
Outputs:              src/sdd/cli.py, src/sdd/graph_navigation/cli/trace.py
Acceptance:           `sdd trace --edge-types imports calls --path X` filters edges by type;
                      without --edge-types output is identical to current behavior (backward compat)
Depends on:           —

---

T-6102: Fix actor="any" → actor="llm" in CommandSpec["sync-state"]

Status:               DONE
Spec ref:             Spec_v61 §1 Scope — BC-61-P2
Invariants:           I-RRL-1
spec_refs:            [Spec_v61 §1, BC-61-P2, I-RRL-1]
produces_invariants:  []
requires_invariants:  [I-RRL-1]
Inputs:               src/sdd/commands/registry.py
Outputs:              src/sdd/commands/registry.py
Acceptance:           `registry.py:274` has `actor="llm"`; `sdd sync-state` executes without VALID_ACTORS error;
                      audit: no other CommandSpec with actor="any" exists (grep confirms)
Depends on:           —

---

T-6103: Extend session docs with Step 0 pre-check preconditions

Status:               DONE
Spec ref:             Spec_v61 §1 Scope — BC-61-P3
Invariants:           I-GRAPH-PROTOCOL-1
spec_refs:            [Spec_v61 §1, BC-61-P3]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/docs/sessions/check-dod.md, .sdd/docs/sessions/summarize-phase.md
Outputs:              .sdd/docs/sessions/check-dod.md, .sdd/docs/sessions/summarize-phase.md
Acceptance:           Both session files contain "Step 0: sdd graph-guard check" precondition block
                      before existing Step 1; text matches Spec_v61 §6 prescribed wording
Depends on:           —

---

T-6104: Complete pytest-cov configuration in pyproject.toml

Status:               DONE
Spec ref:             Spec_v61 §1 Scope — BC-61-P4
Invariants:           I-ENGINE-EDGE-FILTER-1
spec_refs:            [Spec_v61 §1, BC-61-P4]
produces_invariants:  []
requires_invariants:  []
Inputs:               pyproject.toml
Outputs:              pyproject.toml
Acceptance:           pyproject.toml addopts includes `--cov=sdd --cov-report=term-missing`;
                      `pytest tests/unit/ -q` runs and reports coverage without extra flags;
                      fail_under=80 already present (verify, do not duplicate)
Depends on:           —

---

## M2: GraphSessionState + Deterministic Anchor

---

T-6105: Create GraphSessionState + sessions/ runtime directory support

Status:               DONE
Spec ref:             Spec_v61 §2, §5 — BC-61-E1
Invariants:           I-SEARCH-DIRECT-1
spec_refs:            [Spec_v61 §2, §5, BC-61-E1, I-SEARCH-DIRECT-1]
produces_invariants:  [I-SEARCH-DIRECT-1]
requires_invariants:  []
Inputs:               src/sdd/graph_navigation/__init__.py
Outputs:              src/sdd/graph_navigation/session_state.py,
                      src/sdd/graph_navigation/sessions/.gitkeep
Acceptance:           GraphSessionState dataclass with fields: session_id, phase_id, allowed_files, trace_path;
                      load(session_id) / save() use atomic_write from Phase 55 M6;
                      `tests/unit/graph_navigation/test_session_state.py` PASS (load/save round-trip)
Depends on:           —

---

T-6106: Add --node-id flag to sdd resolve (bypass BM25)

Status:               DONE
Spec ref:             Spec_v61 §2 — BC-61-E5
Invariants:           I-SEARCH-DIRECT-1
spec_refs:            [Spec_v61 §2, BC-61-E5, I-SEARCH-DIRECT-1]
produces_invariants:  []
requires_invariants:  [I-SEARCH-DIRECT-1]
Inputs:               src/sdd/cli.py, src/sdd/graph_navigation/cli/resolve.py
Outputs:              src/sdd/cli.py, src/sdd/graph_navigation/cli/resolve.py
Acceptance:           `sdd resolve --node-id <id>` returns exact node without BM25 ranking;
                      without --node-id behavior unchanged;
                      `tests/unit/graph_navigation/test_resolve_node_id.py` PASS
Depends on:           T-6105

---

## M3: Enforcement Gates

---

T-6107: Create graph_guard.py + register sdd graph-guard check

Status:               DONE
Spec ref:             Spec_v61 §2, §6 — BC-61-E2
Invariants:           I-GRAPH-PROTOCOL-1, I-GRAPH-GUARD-1
spec_refs:            [Spec_v61 §2, §6, BC-61-E2, I-GRAPH-PROTOCOL-1, I-GRAPH-GUARD-1]
produces_invariants:  [I-GRAPH-PROTOCOL-1, I-GRAPH-GUARD-1]
requires_invariants:  [I-SEARCH-DIRECT-1]
Inputs:               src/sdd/graph_navigation/session_state.py,
                      src/sdd/graph_navigation/cli/
Outputs:              src/sdd/graph_navigation/cli/graph_guard.py
Acceptance:           `sdd graph-guard check --session-id <id>` exits 0 when session valid,
                      exits 1 + JSON stderr when guard fails;
                      `tests/unit/graph_navigation/test_graph_guard.py` PASS (valid + invalid cases)
Depends on:           T-6105

---

T-6108: Create write_gate.py + register sdd write

Status:               DONE
Spec ref:             Spec_v61 §2, §6 — BC-61-E3
Invariants:           I-TRACE-BEFORE-WRITE
spec_refs:            [Spec_v61 §2, §6, BC-61-E3, I-TRACE-BEFORE-WRITE]
produces_invariants:  [I-TRACE-BEFORE-WRITE]
requires_invariants:  [I-GRAPH-PROTOCOL-1, I-SEARCH-DIRECT-1]
Inputs:               src/sdd/graph_navigation/session_state.py,
                      src/sdd/graph_navigation/cli/
Outputs:              src/sdd/graph_navigation/cli/write_gate.py
Acceptance:           `sdd write <file> --session-id <id>` exits 0 when trace_path set in session,
                      exits 1 + JSON stderr (I-TRACE-BEFORE-WRITE violation) when trace absent;
                      `tests/unit/graph_navigation/test_write_gate.py` PASS
Depends on:           T-6105

---

T-6109: Update scope_policy.py — resolve_scope() accepts session_id

Status:               DONE
Spec ref:             Spec_v61 §2 — BC-61-E4
Invariants:           I-SCOPE-STRICT-1, I-RRL-1, I-RRL-2, I-RRL-3
spec_refs:            [Spec_v61 §2, BC-61-E4, I-SCOPE-STRICT-1, I-RRL-1, I-RRL-3]
produces_invariants:  [I-SCOPE-STRICT-1]
requires_invariants:  [I-RRL-1, I-SEARCH-DIRECT-1]
Inputs:               src/sdd/guards/scope_policy.py,
                      src/sdd/graph_navigation/session_state.py
Outputs:              src/sdd/guards/scope_policy.py
Acceptance:           resolve_scope(task, session_id=None) loads GraphSessionState when session_id given,
                      restricts allowed_files to state.allowed_files;
                      override metadata emitted in JSON output (I-RRL-3);
                      existing check-scope tests PASS (backward compat when session_id=None)
Depends on:           T-6105

---

T-6110: Register M3 commands in cli.py + pyproject.toml

Status:               DONE
Spec ref:             Spec_v61 §6 — CLI Interface
Invariants:           I-GRAPH-PROTOCOL-1, I-TRACE-BEFORE-WRITE
spec_refs:            [Spec_v61 §6, BC-61-E2, BC-61-E3]
produces_invariants:  []
requires_invariants:  [I-GRAPH-PROTOCOL-1, I-TRACE-BEFORE-WRITE]
Inputs:               src/sdd/cli.py, pyproject.toml,
                      src/sdd/graph_navigation/cli/graph_guard.py,
                      src/sdd/graph_navigation/cli/write_gate.py
Outputs:              src/sdd/cli.py, pyproject.toml
Acceptance:           `sdd graph-guard --help` and `sdd write --help` work end-to-end;
                      `sdd --help` lists both commands;
                      `tests/integration/test_graph_navigation_cli.py` extended with smoke tests PASS
Depends on:           T-6107, T-6108

---

## M4: Eval Infrastructure

---

T-6111: Create eval fixtures + eval_deep.py

Status:               DONE
Spec ref:             Spec_v61 §2 — BC-61-T1
Invariants:           I-GRAPH-PROTOCOL-1
spec_refs:            [Spec_v61 §2, BC-61-T1]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/graph_navigation/session_state.py
Outputs:              src/sdd/eval/__init__.py,
                      src/sdd/eval/eval_fixtures.py,
                      src/sdd/eval/eval_deep.py
Acceptance:           eval_fixtures.py creates deterministic test graph artifacts marked `# EVAL ONLY`;
                      eval_deep.py exposes BM25-indexable symbols with rich docstrings;
                      `import sdd.eval` succeeds with no side effects
Depends on:           T-6105

---

T-6112: Create eval_harness.py (ScenarioResult + run_graph_cmd)

Status:               DONE
Spec ref:             Spec_v61 §2, §7 — BC-61-T2
Invariants:           I-GRAPH-PROTOCOL-1
spec_refs:            [Spec_v61 §2, §7, BC-61-T2]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/eval/__init__.py
Outputs:              src/sdd/eval/eval_harness.py
Acceptance:           ScenarioResult dataclass has fields: scenario_id, status, stdout, stderr, exit_code;
                      run_graph_cmd(cmd, args) returns ScenarioResult;
                      `tests/unit/eval/test_harness.py` PASS (mock subprocess)
Depends on:           T-6111

---

T-6113: Create EvalReport_v61 scaffold

Status:               DONE
Spec ref:             Spec_v61 §2 — BC-61-T3
Invariants:           I-GRAPH-PROTOCOL-1
spec_refs:            [Spec_v61 §2, BC-61-T3]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/templates/
Outputs:              .sdd/reports/EvalReport_v61_GraphGuidedTest.md
Acceptance:           File contains S1–S8 rows each with status PENDING;
                      header section documents eval methodology per Spec_v61 §7;
                      no PASS/FAIL entries (scaffold only)
Depends on:           —

---

## M5: Evaluation Scenarios + DoD Closure

---

T-6114: Implement eval scenarios S1–S4 (positive / basic flows)

Status:               DONE
Spec ref:             Spec_v61 §2, §7, §9 — BC-61-T4 (S1–S4)
Invariants:           I-GRAPH-PROTOCOL-1, I-SCOPE-STRICT-1
spec_refs:            [Spec_v61 §7, §9, BC-61-T4, I-GRAPH-PROTOCOL-1]
produces_invariants:  []
requires_invariants:  [I-GRAPH-PROTOCOL-1, I-TRACE-BEFORE-WRITE, I-SEARCH-DIRECT-1]
Inputs:               src/sdd/eval/eval_harness.py,
                      src/sdd/eval/eval_fixtures.py,
                      src/sdd/graph_navigation/cli/graph_guard.py,
                      src/sdd/graph_navigation/cli/write_gate.py
Outputs:              tests/integration/test_eval_s1.py,
                      tests/integration/test_eval_s2.py,
                      tests/integration/test_eval_s3.py,
                      tests/integration/test_eval_s4.py
Acceptance:           All 4 test files PASS; S1–S4 ScenarioResult.status = PASS in each test;
                      tests use --node-id for deterministic anchor (R-4)
Depends on:           T-6110, T-6111, T-6112, T-6113

---

T-6115: Implement eval scenarios S5–S8 (negative / enforcement flows)

Status:               DONE
Spec ref:             Spec_v61 §2, §7, §9 — BC-61-T4 (S5–S8)
Invariants:           I-GRAPH-GUARD-1, I-TRACE-BEFORE-WRITE, I-SCOPE-STRICT-1, I-GRAPH-ANCHOR-CHAIN
spec_refs:            [Spec_v61 §7, §9, BC-61-T4, I-GRAPH-GUARD-1, I-TRACE-BEFORE-WRITE]
produces_invariants:  []
requires_invariants:  [I-GRAPH-PROTOCOL-1, I-GRAPH-GUARD-1, I-TRACE-BEFORE-WRITE, I-SCOPE-STRICT-1]
Inputs:               src/sdd/eval/eval_harness.py,
                      src/sdd/eval/eval_fixtures.py,
                      src/sdd/graph_navigation/cli/graph_guard.py,
                      src/sdd/graph_navigation/cli/write_gate.py,
                      src/sdd/guards/scope_policy.py
Outputs:              tests/integration/test_eval_s5.py,
                      tests/integration/test_eval_s6.py,
                      tests/integration/test_eval_s7.py,
                      tests/integration/test_eval_s8.py
Acceptance:           S5–S8 ScenarioResult.exit_code = 1 and JSON stderr contains expected error_type;
                      enforcement gates reject invalid sessions as specified in Spec_v61 §9
Depends on:           T-6114

---

T-6116: Fill EvalReport_v61 with scenario results

Status:               DONE
Spec ref:             Spec_v61 §2, §7 — BC-61-T4 (report fill)
Invariants:           I-GRAPH-PROTOCOL-1
spec_refs:            [Spec_v61 §7, BC-61-T4]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/reports/EvalReport_v61_GraphGuidedTest.md,
                      tests/integration/test_eval_s1.py .. test_eval_s8.py
Outputs:              .sdd/reports/EvalReport_v61_GraphGuidedTest.md
Acceptance:           No PENDING lines remain; S1–S8 each show PASS or FAIL with evidence;
                      summary section present with aggregate counts
Depends on:           T-6114, T-6115

---

T-6117: DoD closure Phase 55 + final unit regression

Status:               DONE
Spec ref:             Spec_v61 §2, §9 — BC-61-T5
Invariants:           I-GRAPH-PROTOCOL-1, I-SCOPE-STRICT-1, I-TRACE-BEFORE-WRITE, I-GRAPH-GUARD-1
spec_refs:            [Spec_v61 §9, BC-61-T5]
produces_invariants:  []
requires_invariants:  [I-GRAPH-PROTOCOL-1, I-GRAPH-GUARD-1, I-TRACE-BEFORE-WRITE, I-SCOPE-STRICT-1]
Inputs:               .sdd/runtime/State_index.yaml (phase 55 invariants.status)
Outputs:              — (CLI state mutation only)
Acceptance:           `sdd validate T-5521 --result PASS` succeeds (if Phase 55 invariants.status=UNKNOWN);
                      `pytest tests/unit/ -q` exits 0 (Phase 55 regression check);
                      `sdd show-state` shows invariants.status=PASS for phase 61
Depends on:           T-6116
Navigation:
    resolve_keywords: GraphSessionState, I-GRAPH-PROTOCOL-1
    write_scope:

---

<!-- Granularity: 17 tasks (TG-2: 10–30 range ✓). Each task independently implementable and testable (TG-1). -->

---

### Event-Addition Rule (I-EREG-SCOPE-1)

Если Task добавляет новый event type:

THEN Outputs MUST include:
  - src/sdd/core/events.py              (V1_L1_EVENT_TYPES — всегда)
  - src/sdd/domain/state/reducer.py    (ТОЛЬКО если тип имеет handler:
                                        _EVENT_SCHEMA + _fold())

DoD MUST include:
  - test_i_st_10_all_event_types_classified PASS
  - test_i_ereg_1_known_no_handler_is_derived PASS

NOTE: reducer.py НЕ нужен в Outputs для no-handler событий.
Это основной эффект Spec_v39.
