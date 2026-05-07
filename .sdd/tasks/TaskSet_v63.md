# TaskSet_v63 — Phase 63: Behavioral Trace Analysis (L-TRACE Phase 2)

Spec: specs/Spec_v63_BehavioralTraceAnalysis.md
Plan: plans/Plan_v63.md

---

T-6301: Add transcript_ref to COMMAND payload in hook

Status:               DONE
Spec ref:             Spec_v63 §2 — COMMAND payload schema; §1 BC-63-C1
Invariants:           I-TRACE-REF-1, I-TRACE-CMD-1
spec_refs:            [Spec_v63 §2, I-TRACE-REF-1, I-TRACE-CMD-1]
produces_invariants:  [I-TRACE-REF-1]
requires_invariants:  [I-HOOK-2]
Inputs:               src/sdd/hooks/trace_tool.py
Outputs:              src/sdd/hooks/trace_tool.py
Acceptance:           COMMAND payload в trace.jsonl содержит поле transcript_ref (dict или null); fuzzy match по тексту команды — отсутствует
Depends on:           —
Navigation:
    resolve_keywords: TraceEvent, TraceSummary
    write_scope:      src/sdd/hooks/trace_tool.py

---

T-6302: ConversationParser module

Status:               DONE
Spec ref:             Spec_v63 §5 — Types & Interfaces (ToolPair, TranscriptSession); §6 — ConversationParser API
Invariants:           I-TRANSCRIPT-1, I-TRANSCRIPT-2, I-TRANSCRIPT-3, I-TRACE-REF-1
spec_refs:            [Spec_v63 §5, I-TRANSCRIPT-2, I-TRANSCRIPT-3, I-TRACE-REF-1]
produces_invariants:  [I-TRANSCRIPT-2, I-TRANSCRIPT-3]
requires_invariants:  —
Inputs:               — (новый модуль)
Outputs:              src/sdd/transcript/__init__.py, src/sdd/transcript/parser.py
Acceptance:           parse_session() возвращает TranscriptSession с tool_pairs; find_tool_result() по tool_use_id точная связка (не fuzzy); project_dir_from_cwd() и latest_transcript() работают корректно
Depends on:           —
Navigation:
    anchor_nodes:      FILE:src/sdd/hooks/trace_tool.py
    allowed_traversal: imports
    write_scope:       src/sdd/transcript/parser.py

---

T-6303: Session anchoring in record-session

Status:               DONE
Spec ref:             Spec_v63 §2 — Session anchoring (BC-63-P2); §6 — sdd record-session changes
Invariants:           I-TRANSCRIPT-1, I-TRANSCRIPT-2, I-SESSION-DECLARED-1
spec_refs:            [Spec_v63 §2 BC-63-P2, I-TRANSCRIPT-1, I-TRANSCRIPT-2]
produces_invariants:  [I-TRANSCRIPT-1]
requires_invariants:  [I-TRANSCRIPT-2]
Inputs:               src/sdd/commands/record_session.py, src/sdd/transcript/parser.py
Outputs:              src/sdd/commands/record_session.py
Acceptance:           После sdd record-session --type IMPLEMENT ..., файл current_session.json содержит поля transcript_path и transcript_offset; transcript_offset = размер файла в байтах на момент старта
Depends on:           T-6302

---

T-6304: sdd enrich-trace command

Status:               DONE
Spec ref:             Spec_v63 §6 — sdd enrich-trace T-NNN; §2 — Storage layout
Invariants:           I-TRACE-RAW-1, I-TRACE-CMD-1, I-TRACE-CMD-2, I-TRANSCRIPT-3
spec_refs:            [Spec_v63 §6, I-TRACE-RAW-1, I-TRACE-CMD-1, I-TRACE-CMD-2]
produces_invariants:  [I-TRACE-RAW-1]
requires_invariants:  [I-TRANSCRIPT-2, I-TRACE-REF-1]
Inputs:               src/sdd/transcript/parser.py, src/sdd/tracing/writer.py, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/enrich_trace.py, src/sdd/commands/registry.py
Acceptance:           sdd enrich-trace T-NNN: создаёт trace_enriched.jsonl; trace.jsonl — не изменён; exit 0 всегда; "Enriched N/M COMMAND events" в stdout
Depends on:           T-6302, T-6303
Navigation:
    resolve_keywords: TraceSummary, TraceEvent
    write_scope:      src/sdd/commands/enrich_trace.py, src/sdd/commands/registry.py

---

T-6305: trace-summary: prefer trace_enriched.jsonl + behavioral output

Status:               DONE
Spec ref:             Spec_v63 §6 — sdd trace-summary (existing command, changes)
Invariants:           I-TRACE-RAW-1, I-BEHAV-NONBLOCK-1
spec_refs:            [Spec_v63 §6, I-TRACE-RAW-1, I-BEHAV-NONBLOCK-1]
produces_invariants:  [I-BEHAV-NONBLOCK-1]
requires_invariants:  [I-TRACE-RAW-1]
Inputs:               src/sdd/commands/trace_summary.py, src/sdd/tracing/summary.py, src/sdd/tracing/writer.py
Outputs:              src/sdd/commands/trace_summary.py, src/sdd/tracing/writer.py
Acceptance:           sdd trace-summary T-NNN использует trace_enriched.jsonl если он существует, иначе trace.jsonl; вывод содержит "Command failures: N" и "Behavioral violations: [...]" (informational)
Depends on:           T-6304
Navigation:
    resolve_keywords: TraceSummary, TraceEvent
    write_scope:      src/sdd/commands/trace_summary.py, src/sdd/tracing/writer.py

---

T-6306: FALSE_SUCCESS behavioral rule

Status:               DONE
Spec ref:             Spec_v63 §6 — Behavioral rules (6th rule); §4 — I-BEHAV-FALSE-SUCCESS-1
Invariants:           I-BEHAV-FALSE-SUCCESS-1, I-BEHAV-WINDOW-1
spec_refs:            [Spec_v63 §6, I-BEHAV-FALSE-SUCCESS-1]
produces_invariants:  [I-BEHAV-FALSE-SUCCESS-1]
requires_invariants:  [I-TRACE-CMD-1]
Inputs:               src/sdd/tracing/summary.py
Outputs:              src/sdd/tracing/summary.py
Acceptance:           detect_behavioral_violations(): COMMAND с exit_code==0 и "FAILED" или "ERROR" в output_snippet → "FALSE_SUCCESS" в violations; exit_code==0 без этих слов → нет нарушения
Depends on:           T-6304
Navigation:
    resolve_keywords: TraceSummary, TraceEvent
    write_scope:      src/sdd/tracing/summary.py

---

T-6307: enrich-trace integration in sdd complete

Status:               DONE
Spec ref:             Spec_v63 §6 — sdd complete T-NNN изменения
Invariants:           I-TRACE-CMD-1, I-BEHAV-NONBLOCK-1
spec_refs:            [Spec_v63 §6, I-TRACE-CMD-1]
produces_invariants:  [I-TRACE-CMD-1]
requires_invariants:  [I-TRACE-RAW-1]
Inputs:               src/sdd/commands/complete.py, src/sdd/commands/enrich_trace.py
Outputs:              src/sdd/commands/complete.py
Acceptance:           sdd complete T-NNN вызывает enrich-trace перед trace-summary; если enrich-trace падает — complete продолжает (не блокируется)
Depends on:           T-6304, T-6305
Navigation:
    anchor_nodes:      COMMAND:complete
    allowed_traversal: imports
    write_scope:       src/sdd/commands/complete.py

---

T-6308: Tests — ConversationParser (5 tests)

Status:               DONE
Spec ref:             Spec_v63 §9 — тесты 1, 2, 3, 4, 12
Invariants:           I-TRANSCRIPT-2, I-TRACE-REF-1, I-TRANSCRIPT-3
spec_refs:            [Spec_v63 §9, I-TRANSCRIPT-2, I-TRACE-REF-1]
produces_invariants:  [I-TRANSCRIPT-2, I-TRACE-REF-1]
requires_invariants:  [I-TRANSCRIPT-3]
Inputs:               src/sdd/transcript/parser.py
Outputs:              tests/unit/transcript/__init__.py, tests/unit/transcript/test_parser.py
Acceptance:           pytest tests/unit/transcript/ -v: все 5 тестов PASS — test_parse_session_extracts_tool_pairs, test_find_tool_result_by_command, test_project_dir_from_cwd, test_latest_transcript_returns_newest, test_find_tool_result_by_tool_use_id
Depends on:           T-6302
Navigation:
    anchor_nodes:      FILE:src/sdd/transcript/parser.py
    allowed_traversal: imports
    write_scope:       tests/unit/transcript/test_parser.py

---

T-6309: Tests — enrich-trace (2 tests)

Status:               DONE
Spec ref:             Spec_v63 §9 — тесты 5, 13
Invariants:           I-TRACE-CMD-1, I-TRACE-RAW-1
spec_refs:            [Spec_v63 §9, I-TRACE-CMD-1, I-TRACE-RAW-1]
produces_invariants:  [I-TRACE-CMD-1, I-TRACE-RAW-1]
requires_invariants:  [I-TRANSCRIPT-2]
Inputs:               src/sdd/commands/enrich_trace.py, src/sdd/transcript/parser.py, src/sdd/tracing/writer.py
Outputs:              tests/unit/tracing/test_enrich_trace.py
Acceptance:           pytest tests/unit/tracing/test_enrich_trace.py -v: PASS — test_enrich_trace_updates_exit_code, test_enrich_trace_writes_enriched_not_raw
Depends on:           T-6304
Navigation:
    anchor_nodes:      FILE:src/sdd/commands/enrich_trace.py
    allowed_traversal: imports
    write_scope:       tests/unit/tracing/test_enrich_trace.py

---

T-6310: Tests — FALSE_SUCCESS + I-BEHAV-EXPLAIN-1 edge case (2 tests)

Status:               DONE
Spec ref:             Spec_v63 §9 — тест 11; §4 — I-BEHAV-EXPLAIN-1
Invariants:           I-BEHAV-FALSE-SUCCESS-1, I-BEHAV-EXPLAIN-1
spec_refs:            [Spec_v63 §9, I-BEHAV-FALSE-SUCCESS-1, I-BEHAV-EXPLAIN-1]
produces_invariants:  [I-BEHAV-FALSE-SUCCESS-1, I-BEHAV-EXPLAIN-1]
requires_invariants:  [I-BEHAV-WINDOW-1]
Inputs:               src/sdd/tracing/summary.py, tests/unit/tracing/test_summary.py
Outputs:              tests/unit/tracing/test_summary.py
Acceptance:           pytest tests/unit/tracing/test_summary.py -v: PASS — test_detect_false_success, test_explain_not_used_not_applied_to_graph_call_in_last_5
Depends on:           T-6306
Navigation:
    resolve_keywords: TraceSummary, TraceEvent
    write_scope:      tests/unit/tracing/test_summary.py

---

T-6311: I-TRACE-LINK-1 — backfill assistant_uuid + TRANSCRIPT_LINK_MISSING violation in enrich-trace

Status:               DONE
Spec ref:             Spec_v63 §2 — Linking strategy (transcript ↔ trace.jsonl); §4 — I-TRACE-REF-1
Invariants:           I-TRACE-LINK-1, I-TRACE-REF-1
spec_refs:            [Spec_v63 §2, I-TRACE-REF-1]
produces_invariants:  [I-TRACE-LINK-1]
requires_invariants:  [I-TRACE-REF-1, I-TRACE-RAW-1]
Decision:             I-TRACE-LINK-1 (post-decompose): (1) COMMAND MUST contain transcript_ref.tool_use_id non-null. (2) transcript_ref.assistant_uuid MAY be null in raw trace.jsonl — hook payload limitation confirmed (all 27 COMMAND events in T-6302 trace had assistant_uuid=null). (3) enrich-trace MUST backfill assistant_uuid from ToolPair.assistant_uuid when match found. (4) If tool_use_id present but no ToolPair found → emit TRANSCRIPT_LINK_MISSING in violations (data integrity, not behavioral). Verified: tool_use_id reliably provided by Claude Code (Variant A).
Inputs:               src/sdd/commands/enrich_trace.py
Outputs:              src/sdd/commands/enrich_trace.py
Acceptance:           (a) При найденном ToolPair: trace_enriched.jsonl event содержит transcript_ref.assistant_uuid != null; (b) При tool_use_id без совпадения в транскрипте: summary.json violations содержит "TRANSCRIPT_LINK_MISSING: tool_use_id=<id>"; (c) TRANSCRIPT_LINK_MISSING попадает в violations, не в behavioral_violations
Depends on:           T-6304
Navigation:
    anchor_nodes:      FILE:src/sdd/commands/enrich_trace.py
    allowed_traversal: imports
    write_scope:       src/sdd/commands/enrich_trace.py

---

T-6312: Fix trace analyzer false positives — THRASHING skip-prefixes + SCOPE_VIOLATION outputs

Status:               DONE
Spec ref:             post-decompose bugfix — обнаружено при анализе трейса T-6305
Invariants:           I-TRACE-SCOPE-1, I-BEHAV-WINDOW-1
spec_refs:            [I-TRACE-SCOPE-1, I-BEHAV-WINDOW-1]
produces_invariants:  [I-TRACE-SCOPE-1, I-BEHAV-WINDOW-1]
requires_invariants:  [I-BEHAV-WINDOW-1]
Decision:             (A) python3 -m pytest и INPUTS=... shell-batch не должны засчитываться как reasoning commands (THRASHING false positive). (B) task.outputs включать в allowed_files наравне с task.inputs (SCOPE_VIOLATION false positive). (C) INPUTS="..." && sdd check-scope ... shell-batch должен парситься как check-scope grant.
Inputs:               src/sdd/tracing/summary.py, tests/unit/tracing/test_summary.py
Outputs:              src/sdd/tracing/summary.py, tests/unit/tracing/test_summary.py
Acceptance:           pytest tests/unit/tracing/test_summary.py -v: PASS — test_thrashing_not_triggered_by_python3_m_pytest, test_thrashing_not_triggered_by_inputs_batch, test_check_scope_shell_batch_grants_all_paths, test_load_task_inputs_includes_outputs; sdd trace-summary T-6305: THRASHING = 0 violations
Depends on:           T-6305, T-6306
Navigation:
    resolve_keywords: _THRASHING_SKIP_PREFIXES, _load_task_inputs, build_context
    write_scope:      src/sdd/tracing/summary.py, tests/unit/tracing/test_summary.py

---

<!-- Granularity: 12 tasks (TG-2). All tasks are independently implementable and testable (TG-1). -->
