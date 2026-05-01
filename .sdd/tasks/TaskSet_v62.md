# TaskSet_v62 — Phase 62: Execution Trace Layer (L-TRACE) + Graph Semantic Hardening

Spec: specs/Spec_v62_ExecutionTraceLayer.md
Plan: plans/Plan_v62.md

---

T-6201: TraceEvent dataclass + append_event() writer

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-L1), §5 Types & Interfaces — TraceEvent dataclass
Invariants:           I-TRACE-ORDER-1
spec_refs:            [Spec_v62 §1, Spec_v62 §5, I-TRACE-ORDER-1]
produces_invariants:  [I-TRACE-ORDER-1]
requires_invariants:  []
Inputs:               pyproject.toml
Outputs:              src/sdd/tracing/__init__.py, src/sdd/tracing/trace_event.py, src/sdd/tracing/writer.py
Acceptance:           TraceEvent可以实例化并追加到 .sdd/reports/T-NNN/trace.jsonl; 事件按 ts 排序 (I-TRACE-ORDER-1 pass)
Depends on:           —
Navigation:
    resolve_keywords: GraphCallLog, GraphSessionState
    write_scope:      src/sdd/tracing/__init__.py, src/sdd/tracing/trace_event.py, src/sdd/tracing/writer.py

---

T-6202: sdd-trace-hook — PostToolUse hook script

Status:               DONE
Spec ref:             Spec_v62 §2 Architecture — Hook-механизм, §6 CLI Interface — Hook-конфигурация
Invariants:           I-TRACE-COMPLETE-1
spec_refs:            [Spec_v62 §2, Spec_v62 §6, I-TRACE-COMPLETE-1]
produces_invariants:  [I-TRACE-COMPLETE-1]
requires_invariants:  [I-TRACE-ORDER-1]
Inputs:               src/sdd/tracing/writer.py, src/sdd/hooks/log_tool.py, pyproject.toml
Outputs:              src/sdd/hooks/trace_tool.py, pyproject.toml
Acceptance:           `sdd-trace-hook` console_script зарегистрирован; на Read-событие пишет FILE_READ запись в trace.jsonl; на `sdd resolve` — GRAPH_CALL
Depends on:           T-6201
Navigation:
    resolve_keywords: GraphCallLog
    write_scope:      src/sdd/hooks/trace_tool.py

---

T-6203: record-session --task T-NNN — расширение current_session.json

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-L3), §6 CLI Interface — sdd record-session
Invariants:           I-SESSION-DECLARED-1
spec_refs:            [Spec_v62 §1, Spec_v62 §6, I-SESSION-DECLARED-1]
produces_invariants:  [I-SESSION-DECLARED-1]
requires_invariants:  []
Inputs:               src/sdd/commands/record_session.py
Outputs:              src/sdd/commands/record_session.py
Acceptance:           `sdd record-session --type IMPLEMENT --phase 62 --task T-6201` добавляет `"task_id": "T-6201"` в current_session.json; не-IMPLEMENT типы — task_id отсутствует (backward compat)
Depends on:           —
Navigation:
    resolve_keywords: SessionDeclaredEvent, complete
    write_scope:      src/sdd/commands/record_session.py

---

T-6204: sdd trace-summary T-NNN — команда анализа трейса

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-L4), §2 Architecture — Вычисление allowed_files, §5 Types & Interfaces — TraceSummary, §6 CLI Interface — sdd trace-summary
Invariants:           I-TRACE-COMPLETE-1, I-TRACE-SCOPE-1, I-TRACE-ORDER-1
spec_refs:            [Spec_v62 §1, Spec_v62 §2, Spec_v62 §5, Spec_v62 §6, I-TRACE-COMPLETE-1, I-TRACE-SCOPE-1, I-TRACE-ORDER-1]
produces_invariants:  [I-TRACE-COMPLETE-1, I-TRACE-SCOPE-1, I-TRACE-ORDER-1]
requires_invariants:  [I-TRACE-ORDER-1]
Inputs:               src/sdd/tracing/writer.py, src/sdd/tracing/trace_event.py, src/sdd/graph_navigation/session_state.py, src/sdd/cli.py, src/sdd/commands/registry.py
Outputs:              src/sdd/tracing/summary.py, src/sdd/commands/trace_summary.py, src/sdd/cli.py, src/sdd/commands/registry.py
Acceptance:           `sdd trace-summary T-NNN` → exit 0 без hard violations; FILE_WRITE без предшествующего GRAPH_CALL → exit 1 с I-TRACE-COMPLETE-1 в stderr; SCOPE_VIOLATION → stdout, exit 0; summary.json создаётся в .sdd/reports/T-NNN/
Depends on:           T-6201, T-6202, T-6203
Navigation:
    resolve_keywords: GraphSessionState, GraphCallLog
    write_scope:      src/sdd/tracing/summary.py, src/sdd/commands/trace_summary.py, src/sdd/cli.py, src/sdd/commands/registry.py

---

T-6205: sdd complete интегрирует trace-summary

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-L5), §6 CLI Interface — sdd complete
Invariants:           I-TRACE-COMPLETE-1
spec_refs:            [Spec_v62 §1, Spec_v62 §6, I-TRACE-COMPLETE-1]
produces_invariants:  [I-TRACE-COMPLETE-1]
requires_invariants:  [I-TRACE-COMPLETE-1]
Inputs:               src/sdd/commands/complete.py, src/sdd/commands/trace_summary.py
Outputs:              src/sdd/commands/complete.py
Acceptance:           `sdd complete T-NNN` вызывает trace-summary как внутренний шаг; violations выводятся в stdout; complete не блокируется при наличии violations (Phase 62 — informative only)
Depends on:           T-6204
Navigation:
    resolve_keywords: complete, _check_deps
    write_scope:      src/sdd/commands/complete.py

---

T-6206: Unit tests для tracing/ модуля

Status:               DONE
Spec ref:             Spec_v62 §7 Evaluation Methodology — Часть 1 (L-TRACE smoke-тесты)
Invariants:           I-TRACE-ORDER-1, I-TRACE-COMPLETE-1, I-TRACE-SCOPE-1
spec_refs:            [Spec_v62 §7, I-TRACE-ORDER-1, I-TRACE-COMPLETE-1, I-TRACE-SCOPE-1]
produces_invariants:  [I-TRACE-ORDER-1, I-TRACE-COMPLETE-1, I-TRACE-SCOPE-1]
requires_invariants:  [I-TRACE-COMPLETE-1, I-TRACE-SCOPE-1, I-TRACE-ORDER-1]
Inputs:               src/sdd/tracing/trace_event.py, src/sdd/tracing/writer.py, src/sdd/tracing/summary.py, src/sdd/hooks/trace_tool.py
Outputs:              tests/unit/tracing/__init__.py, tests/unit/tracing/test_trace_event.py, tests/unit/tracing/test_writer.py, tests/unit/tracing/test_summary.py, tests/unit/tracing/test_hook.py
Acceptance:           `pytest tests/unit/tracing/ -q` — все тесты PASS; покрывает I-TRACE-ORDER-1 (порядок событий по ts), I-TRACE-COMPLETE-1 (hard violation detection), I-TRACE-SCOPE-1 (soft SCOPE_VIOLATION)
Depends on:           T-6201, T-6202, T-6203, T-6204, T-6205
Navigation:
    resolve_keywords: GraphCallLog, scope_policy
    write_scope:      tests/unit/tracing/__init__.py, tests/unit/tracing/test_trace_event.py, tests/unit/tracing/test_writer.py, tests/unit/tracing/test_summary.py, tests/unit/tracing/test_hook.py

---

T-6207: GraphSessionState — 5 новых полей с backward-compatible дефолтами

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-G1), §5 Types & Interfaces — GraphSessionState расширение
Invariants:           I-TRACE-RELEVANCE-1, I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1, I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1
spec_refs:            [Spec_v62 §1, Spec_v62 §5, I-TRACE-RELEVANCE-1]
produces_invariants:  [I-TRACE-RELEVANCE-1, I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1, I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1]
requires_invariants:  [I-TRACE-COMPLETE-1]
Inputs:               src/sdd/graph_navigation/session_state.py, src/sdd/graph_navigation/cli/graph_guard.py, src/sdd/graph_navigation/cli/write_gate.py
Outputs:              src/sdd/graph_navigation/session_state.py
Acceptance:           GraphSessionState содержит 5 новых полей: traversal_depth_max=0, fallback_used=False, explain_nodes=frozenset(), write_targets=frozenset(), depth_justification=""; Phase 61 GraphSessionState JSON файлы загружаются без ошибок (backward compat, R-2)
Depends on:           T-6206
Navigation:
    resolve_keywords: GraphSessionState
    write_scope:      src/sdd/graph_navigation/session_state.py

---

T-6208: I-TRACE-RELEVANCE-1 в write_gate.py

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-G2), §4 New Invariants — I-TRACE-RELEVANCE-1
Invariants:           I-TRACE-RELEVANCE-1
spec_refs:            [Spec_v62 §1, Spec_v62 §4, I-TRACE-RELEVANCE-1]
produces_invariants:  [I-TRACE-RELEVANCE-1]
requires_invariants:  [I-TRACE-RELEVANCE-1]
Inputs:               src/sdd/graph_navigation/cli/write_gate.py, src/sdd/graph_navigation/session_state.py
Outputs:              src/sdd/graph_navigation/cli/write_gate.py
Acceptance:           `write_target ∉ state.trace_path` → exit 1 c I-TRACE-RELEVANCE-1; `write_target ∈ trace_path` → exit 0; S1–S8 Phase 61 позитивные сценарии не регрессируют
Depends on:           T-6207
Navigation:
    anchor_nodes:      FILE:src/sdd/graph_navigation/cli/write_gate.py, FILE:src/sdd/graph_navigation/session_state.py
    allowed_traversal: imports, guards
    write_scope:       src/sdd/graph_navigation/cli/write_gate.py

---

T-6209: I-FALLBACK-STRICT-1 + I-GRAPH-DEPTH-1 в graph_guard.py

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-G3, BC-62-G4), §4 New Invariants
Invariants:           I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1
spec_refs:            [Spec_v62 §1, Spec_v62 §4, I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1]
produces_invariants:  [I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1]
requires_invariants:  [I-TRACE-RELEVANCE-1]
Inputs:               src/sdd/graph_navigation/cli/graph_guard.py, src/sdd/graph_navigation/session_state.py
Outputs:              src/sdd/graph_navigation/cli/graph_guard.py
Acceptance:           I-FALLBACK-STRICT-1: fallback_used=True + allowed_files пусто → exit 1; fallback_used=True + task_inputs заданы → exit 0 (S15); I-GRAPH-DEPTH-1: traversal_depth_max=1 + depth_justification="" → exit 1 (S11); depth_max≥2 → exit 0
Depends on:           T-6208
Navigation:
    anchor_nodes:      FILE:src/sdd/graph_navigation/cli/graph_guard.py, FILE:src/sdd/graph_navigation/session_state.py
    allowed_traversal: imports, guards
    write_scope:       src/sdd/graph_navigation/cli/graph_guard.py

---

T-6210: I-GRAPH-COVERAGE-REQ-1 + I-EXPLAIN-USAGE-1 в graph_guard.py

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-G5), §4 New Invariants
Invariants:           I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1
spec_refs:            [Spec_v62 §1, Spec_v62 §4, I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1]
produces_invariants:  [I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1]
requires_invariants:  [I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1]
Inputs:               src/sdd/graph_navigation/cli/graph_guard.py, src/sdd/graph_navigation/session_state.py
Outputs:              src/sdd/graph_navigation/cli/graph_guard.py
Acceptance:           I-GRAPH-COVERAGE-REQ-1: write_target ∉ trace_path ∪ explain_nodes → exit 1 (S12); I-EXPLAIN-USAGE-1: explain_node ∉ trace_path ∪ write_targets → exit 1 (S13); S14 позитивный сценарий → exit 0
Depends on:           T-6209
Navigation:
    anchor_nodes:      FILE:src/sdd/graph_navigation/cli/graph_guard.py, FILE:src/sdd/graph_navigation/session_state.py
    allowed_traversal: imports, guards
    write_scope:       src/sdd/graph_navigation/cli/graph_guard.py

---

T-6211: Eval сценарии S9–S15 + EvalReport_v62

Status:               DONE
Spec ref:             Spec_v62 §1 Scope (BC-62-G6), §7 Evaluation Methodology — Часть 2, §9 Acceptance Criteria
Invariants:           I-TRACE-RELEVANCE-1, I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1, I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1
spec_refs:            [Spec_v62 §7, Spec_v62 §9, I-TRACE-RELEVANCE-1, I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1, I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1]
produces_invariants:  [I-TRACE-RELEVANCE-1, I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1, I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1]
requires_invariants:  [I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1]
Inputs:               src/sdd/graph_navigation/cli/graph_guard.py, src/sdd/graph_navigation/cli/write_gate.py, src/sdd/graph_navigation/session_state.py, tests/integration/test_eval_s1.py
Outputs:              tests/integration/test_eval_s9_s15.py, .sdd/reports/EvalReport_v62.md
Acceptance:           `pytest tests/integration/test_eval_s9_s15.py -q` — S9–S15 все PASS; `pytest tests/unit/ -q` — ≥1374 PASS (Phase 61 regression); EvalReport_v62.md не содержит PENDING строк
Depends on:           T-6210
Navigation:
    resolve_keywords: GraphCallLog, TaskNavigationSpec
    write_scope:      tests/integration/test_eval_s9_s15.py

---

<!-- Granularity: 11 tasks (TG-2: 10–30). Все задачи независимо реализуемы и тестируемы (TG-1). -->
<!-- Every task declares Inputs, Outputs, Invariants Covered (TG-3). -->

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
