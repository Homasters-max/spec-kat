# TaskSet_v52 — Phase 52: CLI + LightRAG + Migration Window Close

Spec: specs/Spec_v52_CLIMigrationLightRAG.md
Plan: plans/Plan_v52.md

---

T-5201: ImplementsEdgeExtractor — реализация класса

Status:               TODO
Spec ref:             Spec_v52 §4.2 — Known Graph Gap COMMAND ↔ FILE
Invariants:           I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2
spec_refs:            [Spec_v52 §4.2, I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2]
produces_invariants:  [I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2]
requires_invariants:  []
Inputs:               src/sdd/graph/types.py, src/sdd/graph/extractors/ast_edges.py
Outputs:              src/sdd/graph/extractors/implements_edges.py
Acceptance:           test_command_nodes_have_implements_edges PASS
Depends on:           —

---

T-5202: ImplementsEdgeExtractor — регистрация в pipeline + тест fallback

Status:               TODO
Spec ref:             Spec_v52 §4.2 — Known Graph Gap COMMAND ↔ FILE
Invariants:           I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2
spec_refs:            [Spec_v52 §4.2, I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2]
produces_invariants:  [I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2]
requires_invariants:  [I-GRAPH-IMPLEMENTS-1]
Inputs:               src/sdd/graph/extractors/implements_edges.py, src/sdd/graph/builder.py
Outputs:              src/sdd/graph/builder.py
Acceptance:           test_explain_command_fallback_to_file_seed PASS
Depends on:           T-5201

---

T-5203: graph_navigation package scaffold — IndexBuilder + GraphService + query intent wiring

Status:               TODO
Spec ref:             Spec_v52 §1 — BC-36-7 CLI, canonical handler pattern
Invariants:           I-RUNTIME-ORCHESTRATOR-1, I-PHASE-ISOLATION-1
spec_refs:            [Spec_v52 §1, I-RUNTIME-ORCHESTRATOR-1, I-PHASE-ISOLATION-1]
produces_invariants:  [I-RUNTIME-ORCHESTRATOR-1, I-PHASE-ISOLATION-1]
requires_invariants:  [I-GRAPH-IMPLEMENTS-1]
Inputs:               src/sdd/context_kernel/, src/sdd/graph/cache.py, src/sdd/graph/builder.py
Outputs:              src/sdd/graph_navigation/__init__.py
Acceptance:           test_import_direction_phase52 PASS (graph_navigation не импортирует sdd.graph.cache/builder напрямую)
Depends on:           T-5202

---

T-5204: sdd resolve + sdd trace CLI handlers

Status:               TODO
Spec ref:             Spec_v52 §1 — BC-36-7 CLI (resolve, trace)
Invariants:           I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-CLI-TRANSPARENCY-1, I-RUNTIME-ORCHESTRATOR-1
spec_refs:            [Spec_v52 §1, I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-CLI-TRANSPARENCY-1]
produces_invariants:  [I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-CLI-TRANSPARENCY-1]
requires_invariants:  [I-RUNTIME-ORCHESTRATOR-1, I-PHASE-ISOLATION-1]
Inputs:               src/sdd/graph_navigation/__init__.py, src/sdd/context_kernel/
Outputs:              src/sdd/graph_navigation/cli/resolve.py, src/sdd/graph_navigation/cli/trace.py, src/sdd/graph_navigation/cli/formatting.py
Acceptance:           tests/unit/* test 28 PASS; INT-1, INT-2 PASS
Depends on:           T-5203

---

T-5205: sdd explain CLI handler (uses implements-edges fallback)

Status:               TODO
Spec ref:             Spec_v52 §1 — BC-36-7 CLI (explain)
Invariants:           I-CLI-FORMAT-1, I-CLI-TRANSPARENCY-2, I-RUNTIME-ORCHESTRATOR-1, I-GRAPH-IMPLEMENTS-1
spec_refs:            [Spec_v52 §1, I-CLI-FORMAT-1, I-CLI-TRANSPARENCY-2, I-GRAPH-IMPLEMENTS-1]
produces_invariants:  [I-CLI-TRANSPARENCY-2]
requires_invariants:  [I-GRAPH-IMPLEMENTS-2, I-RUNTIME-ORCHESTRATOR-1]
Inputs:               src/sdd/graph_navigation/cli/formatting.py, src/sdd/graph/extractors/implements_edges.py
Outputs:              src/sdd/graph_navigation/cli/explain.py
Acceptance:           tests/unit/* tests 46, 47, 48, 49 PASS; INT-3 PASS
Depends on:           T-5204

---

T-5206: sdd invariant CLI handler + tool_definitions.py

Status:               TODO
Spec ref:             Spec_v52 §1 — BC-36-7 CLI (invariant)
Invariants:           I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-TOOL-DEF-1
spec_refs:            [Spec_v52 §1, I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-TOOL-DEF-1]
produces_invariants:  [I-TOOL-DEF-1]
requires_invariants:  [I-RUNTIME-ORCHESTRATOR-1]
Inputs:               src/sdd/graph_navigation/__init__.py, src/sdd/graph_navigation/cli/formatting.py
Outputs:              src/sdd/graph_navigation/cli/invariant.py, src/sdd/graph_navigation/tool_definitions.py
Acceptance:           test_cli_handler_no_business_logic_beyond_pipeline PASS; INT-4 PASS
Depends on:           T-5203

---

T-5207: Регистрация graph_navigation команд в cli.py + integration tests INT-5..7

Status:               TODO
Spec ref:             Spec_v52 §1 — BC-36-7 CLI
Invariants:           I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-PHASE-ISOLATION-1
spec_refs:            [Spec_v52 §1, I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-PHASE-ISOLATION-1]
produces_invariants:  [I-CLI-ERROR-CODES-1]
requires_invariants:  [I-CLI-TRANSPARENCY-1, I-CLI-TRANSPARENCY-2, I-TOOL-DEF-1]
Inputs:               src/sdd/cli.py, src/sdd/graph_navigation/cli/resolve.py, src/sdd/graph_navigation/cli/explain.py, src/sdd/graph_navigation/cli/trace.py, src/sdd/graph_navigation/cli/invariant.py
Outputs:              src/sdd/cli.py
Acceptance:           INT-5, INT-6, INT-7 PASS
Depends on:           T-5204, T-5205, T-5206

---

T-5208: LightRAGRegistry

Status:               TODO
Spec ref:             Spec_v52 §2 — BC-36-4 LightRAGRegistry
Invariants:           I-RAG-REGISTRY-PURE-1, I-RAG-GLOBAL-V1-DISABLED-1, I-RAG-1
spec_refs:            [Spec_v52 §2, I-RAG-REGISTRY-PURE-1, I-RAG-GLOBAL-V1-DISABLED-1, I-RAG-1]
produces_invariants:  [I-RAG-REGISTRY-PURE-1, I-RAG-GLOBAL-V1-DISABLED-1]
requires_invariants:  [I-LIGHTRAG-CANONICAL-1]
Inputs:               src/sdd/context_kernel/rag_types.py
Outputs:              src/sdd/graph_navigation/rag/registry.py
Acceptance:           tests/unit/* test 59, 60 PASS
Depends on:           T-5203

---

T-5209: LightRAGExporter + sdd rag-export CLI

Status:               TODO
Spec ref:             Spec_v52 §2 — BC-36-4 LightRAGExporter, sdd rag-export
Invariants:           I-RAG-EXPORT-FRESHNESS-1, I-RAG-EXPORT-NOT-IN-QUERY-1, I-RAG-CHUNK-1, I-RAG-EXPORT-TASK-MODE-1
spec_refs:            [Spec_v52 §2, I-RAG-EXPORT-FRESHNESS-1, I-RAG-EXPORT-NOT-IN-QUERY-1, I-RAG-CHUNK-1, I-RAG-EXPORT-TASK-MODE-1]
produces_invariants:  [I-RAG-EXPORT-FRESHNESS-1, I-RAG-EXPORT-TASK-MODE-1, I-RAG-CHUNK-1]
requires_invariants:  [I-RAG-REGISTRY-PURE-1]
Inputs:               src/sdd/graph_navigation/rag/registry.py, src/sdd/graph/cache.py
Outputs:              src/sdd/graph_navigation/rag/lightrag_exporter.py, src/sdd/graph_navigation/cli/rag_export.py
Acceptance:           tests/unit/* tests 61, 62 PASS; sdd rag-export --rebuild выполняется идемпотентно
Depends on:           T-5208

---

T-5210: rag-export — task-mode exclusion + grep-test 68 + integration test

Status:               TODO
Spec ref:             Spec_v52 §2 — BC-36-4, task mode exclusion
Invariants:           I-RAG-EXPORT-NOT-IN-QUERY-1, I-RAG-EXPORT-TASK-MODE-1, I-TASK-MODE-1
spec_refs:            [Spec_v52 §2, I-RAG-EXPORT-NOT-IN-QUERY-1, I-RAG-EXPORT-TASK-MODE-1, I-TASK-MODE-1]
produces_invariants:  [I-RAG-EXPORT-NOT-IN-QUERY-1]
requires_invariants:  [I-RAG-EXPORT-FRESHNESS-1, I-RAG-EXPORT-TASK-MODE-1]
Inputs:               src/sdd/graph_navigation/rag/lightrag_exporter.py, src/sdd/cli.py, tests/integration/
Outputs:              tests/integration/test_lightrag_export.py
Acceptance:           test 67, test 68 (grep-тест: LightRAGExporter не вызывается из query-пути) PASS; INT-9 PASS
Depends on:           T-5209, T-5207

---

T-5211: LightRAGProjection — полная деградация GLOBAL/HYBRID → LOCAL → OFF

Status:               TODO
Spec ref:             Spec_v52 §2 — LightRAGProjection, деградация
Invariants:           I-RAG-DEGRADE-LOCAL-1, I-RAG-NO-PERSISTENCE-1, I-LIGHTRAG-CANONICAL-1
spec_refs:            [Spec_v52 §2, I-RAG-DEGRADE-LOCAL-1, I-RAG-NO-PERSISTENCE-1, I-LIGHTRAG-CANONICAL-1]
produces_invariants:  [I-RAG-DEGRADE-LOCAL-1, I-RAG-NO-PERSISTENCE-1]
requires_invariants:  [I-RAG-REGISTRY-PURE-1, I-LIGHTRAG-CANONICAL-1]
Inputs:               src/sdd/context_kernel/rag_types.py, src/sdd/graph_navigation/rag/registry.py
Outputs:              src/sdd/context_kernel/rag_types.py
Acceptance:           tests/unit/* tests 63, 64, 65, 66 PASS; INT-8 PASS; NavigationResponse.rag_mode отражает фактический режим после деградации
Depends on:           T-5208

---

T-5212: migration.py + migration_complete()

Status:               TODO
Spec ref:             Spec_v52 §3 — BC-36-5, legacy migration close
Invariants:           I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4
spec_refs:            [Spec_v52 §3, I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4]
produces_invariants:  [I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4]
requires_invariants:  [I-RUNTIME-ORCHESTRATOR-1]
Inputs:               src/sdd/graph_navigation/__init__.py, src/sdd/context/
Outputs:              src/sdd/graph_navigation/migration.py
Acceptance:           test_migration_complete_returns_true PASS
Depends on:           T-5207

---

T-5213: context_legacy restructure — переименование build_context + deprecation adapter

Status:               TODO
Spec ref:             Spec_v52 §3 — BC-36-5, context_legacy
Invariants:           I-LEGACY-FS-EXCEPTION-1, I-GRAPH-FS-ROOT-1, I-CTX-MIGRATION-1
spec_refs:            [Spec_v52 §3, I-LEGACY-FS-EXCEPTION-1, I-GRAPH-FS-ROOT-1]
produces_invariants:  [I-LEGACY-FS-EXCEPTION-1, I-GRAPH-FS-ROOT-1]
requires_invariants:  [I-CTX-MIGRATION-1, I-CTX-MIGRATION-2]
Inputs:               src/sdd/context/build_context.py, src/sdd/graph_navigation/migration.py
Outputs:              src/sdd/context_legacy/build_context.py, src/sdd/context/build_context.py (deprecation adapter)
Acceptance:           INT-10 PASS; migration_complete() == True после переименования; deprecation warning при импорте старого пути
Depends on:           T-5212

---

T-5214: Full test suite — unit + integration + regression Phase 50/51 + mypy

Status:               TODO
Spec ref:             Spec_v52 §6 — Verification
Invariants:           I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2, I-CLI-FORMAT-1, I-RAG-DEGRADE-LOCAL-1, I-CTX-MIGRATION-1..4
spec_refs:            [Spec_v52 §6, все invariants M1..M5]
produces_invariants:  []
requires_invariants:  [I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2, I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-CLI-TRANSPARENCY-1, I-CLI-TRANSPARENCY-2, I-RUNTIME-ORCHESTRATOR-1, I-PHASE-ISOLATION-1, I-TOOL-DEF-1, I-RAG-EXPORT-FRESHNESS-1, I-RAG-REGISTRY-PURE-1, I-RAG-EXPORT-NOT-IN-QUERY-1, I-RAG-GLOBAL-V1-DISABLED-1, I-RAG-EXPORT-TASK-MODE-1, I-RAG-1, I-RAG-CHUNK-1, I-RAG-DEGRADE-LOCAL-1, I-RAG-NO-PERSISTENCE-1, I-LIGHTRAG-CANONICAL-1, I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4, I-LEGACY-FS-EXCEPTION-1, I-GRAPH-FS-ROOT-1]
Inputs:               tests/unit/, tests/integration/, src/sdd/graph_navigation/
Outputs:              — (read-only verification)
Acceptance:           pytest tests/unit tests/integration PASS; mypy --strict src/sdd/graph_navigation/ — 0 errors; Phase 50 + 51 regression tests PASS
Depends on:           T-5201, T-5202, T-5203, T-5204, T-5205, T-5206, T-5207, T-5208, T-5209, T-5210, T-5211, T-5212, T-5213

---

T-5215: DoD verification — sdd validate-invariants + 14 DoD checklist

Status:               TODO
Spec ref:             Spec_v52 §7 — DoD Phase 52
Invariants:           I-PHASES-INDEX-1, все выше
spec_refs:            [Spec_v52 §7, I-PHASES-INDEX-1]
produces_invariants:  []
requires_invariants:  []
Inputs:               — (requires T-5214 PASS)
Outputs:              — (read-only DoD check)
Acceptance:           sdd validate-invariants --check I-PHASES-INDEX-1 PASS; все 14 пунктов DoD Phase 52 подтверждены
Depends on:           T-5214

---

<!-- Granularity: 15 tasks (TG-2 compliant: 10–30). Each task independently implementable and testable (TG-1). -->
<!-- Every task references exactly one Spec section + ≥1 invariant (SDD-2). -->
<!-- TaskSet covers all Plan milestones M1..M6 (SDD-3). -->

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
