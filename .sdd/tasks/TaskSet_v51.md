# TaskSet_v51 — Phase 51: Context Kernel + Policy Layer

Spec: specs/Spec_v51_ContextKernelPolicyLayer.md
Plan: plans/Plan_v51.md

---

T-5101: Policy layer — types package

Status:               DONE
Spec ref:             Spec_v51 §1 BC-36-P — Policy types
Invariants Covered:   I-POLICY-LAYER-1, I-CONTEXT-BUDGET-VALID-1, I-RAG-GLOBAL-V1-DISABLED-1
spec_refs:            [Spec_v51 §1, I-POLICY-LAYER-1, I-CONTEXT-BUDGET-VALID-1, I-RAG-GLOBAL-V1-DISABLED-1]
produces_invariants:  [I-POLICY-LAYER-1, I-CONTEXT-BUDGET-VALID-1, I-RAG-GLOBAL-V1-DISABLED-1]
requires_invariants:  [—]
Inputs:               — (new package)
Outputs:              src/sdd/policy/__init__.py
                      src/sdd/policy/types.py
Acceptance:           `from sdd.policy import Budget, RagMode, NavigationPolicy, MIN_CONTEXT_SIZE, BFS_OVERSELECT_FACTOR` succeeds; Budget.__post_init__ raises AssertionError when max_chars < MIN_CONTEXT_SIZE
Depends on:           —

---

T-5102: Policy layer — PolicyResolver

Status:               DONE
Spec ref:             Spec_v51 §1 BC-36-P — PolicyResolver._DEFAULT, resolve()
Invariants Covered:   I-POLICY-RESOLVER-1, I-POLICY-LAYER-PURE-1
spec_refs:            [Spec_v51 §1, I-POLICY-RESOLVER-1, I-POLICY-LAYER-PURE-1]
produces_invariants:  [I-POLICY-RESOLVER-1, I-POLICY-LAYER-PURE-1]
requires_invariants:  [I-POLICY-LAYER-1]
Inputs:               src/sdd/policy/__init__.py
                      src/sdd/policy/types.py
Outputs:              src/sdd/policy/resolver.py
Acceptance:           PolicyResolver._DEFAULT maps all 5 QueryIntent values; resolve() returns NavigationPolicy; no side effects; no sdd.context_kernel imports
Depends on:           T-5101

---

T-5103: Policy layer — unit tests

Status:               DONE
Spec ref:             Spec_v51 §1 BC-36-P — Verification
Invariants Covered:   I-POLICY-RESOLVER-1, I-CONTEXT-BUDGET-VALID-1, I-RAG-GLOBAL-V1-DISABLED-1
spec_refs:            [Spec_v51 §1, I-POLICY-RESOLVER-1, I-CONTEXT-BUDGET-VALID-1]
produces_invariants:  []
requires_invariants:  [I-POLICY-RESOLVER-1, I-POLICY-LAYER-1]
Inputs:               src/sdd/policy/types.py
                      src/sdd/policy/resolver.py
Outputs:              tests/unit/policy/test_resolver.py
Acceptance:           pytest tests/unit/policy/test_resolver.py passes; all 5 intents covered; Budget validation (max_chars < MIN_CONTEXT_SIZE raises) tested; DoD 7 condition satisfied
Depends on:           T-5101, T-5102

---

T-5104: Context Kernel — package init

Status:               DONE
Spec ref:             Spec_v51 §2 BC-36-3 — Context Kernel package scaffold
Invariants Covered:   I-PHASE-ISOLATION-1
spec_refs:            [Spec_v51 §2, I-PHASE-ISOLATION-1]
produces_invariants:  [I-PHASE-ISOLATION-1]
requires_invariants:  [—]
Inputs:               src/sdd/policy/__init__.py
Outputs:              src/sdd/context_kernel/__init__.py
Acceptance:           `import sdd.context_kernel` succeeds; zero circular imports with sdd.policy; no sdd.graph_navigation imports present
Depends on:           T-5101

---

T-5105: Context Kernel — QueryIntent & SearchCandidate

Status:               DONE
Spec ref:             Spec_v51 §2.2 — QueryIntent, parse_query_intent(), SearchCandidate
Invariants Covered:   I-INTENT-CANONICAL-1, I-INTENT-HEURISTIC-1, I-INTENT-SOURCE-OF-TRUTH-1, I-SEARCH-CANDIDATE-1, I-SEARCH-AUTO-EXACT-1, I-SEARCH-NO-EMBED-1
spec_refs:            [Spec_v51 §2.2, I-INTENT-CANONICAL-1, I-INTENT-HEURISTIC-1, I-SEARCH-CANDIDATE-1]
produces_invariants:  [I-INTENT-CANONICAL-1, I-INTENT-HEURISTIC-1, I-INTENT-SOURCE-OF-TRUTH-1, I-SEARCH-CANDIDATE-1, I-SEARCH-AUTO-EXACT-1, I-SEARCH-NO-EMBED-1]
requires_invariants:  [—]
Inputs:               src/sdd/context_kernel/__init__.py
Outputs:              src/sdd/context_kernel/intent.py
Acceptance:           parse_query_intent() does NOT infer EXPLAIN or TRACE; SearchCandidate has score + node_id fields; auto-upgrade to RESOLVE_EXACT when single candidate (I-SEARCH-AUTO-EXACT-1); no embedding calls
Depends on:           T-5104

---

T-5106: Context Kernel — intent unit tests

Status:               DONE
Spec ref:             Spec_v51 §2.2 — Verification
Invariants Covered:   I-INTENT-HEURISTIC-1, I-SEARCH-NO-EMBED-1, I-SEARCH-AUTO-EXACT-1
spec_refs:            [Spec_v51 §2.2, I-INTENT-HEURISTIC-1, I-SEARCH-AUTO-EXACT-1]
produces_invariants:  []
requires_invariants:  [I-INTENT-CANONICAL-1, I-INTENT-HEURISTIC-1, I-SEARCH-AUTO-EXACT-1]
Inputs:               src/sdd/context_kernel/intent.py
Outputs:              tests/unit/context_kernel/test_intent.py
Acceptance:           pytest tests/unit/context_kernel/test_intent.py passes; explicit test that EXPLAIN/TRACE are NOT inferred; auto-upgrade to RESOLVE_EXACT with single candidate tested
Depends on:           T-5105

---

T-5107: Context Kernel — Selection & BFS

Status:               DONE
Spec ref:             Spec_v51 §2.3 — RankedNode, RankedEdge, Selection, _build_selection() BFS
Invariants Covered:   I-RANKED-NODE-BP-1, I-BFS-BUDGET-1, I-CONTEXT-SELECT-1, I-CONTEXT-SELECT-2, I-SEARCH-MAX-EDGES-1
spec_refs:            [Spec_v51 §2.3, I-RANKED-NODE-BP-1, I-BFS-BUDGET-1, I-CONTEXT-SELECT-1]
produces_invariants:  [I-RANKED-NODE-BP-1, I-BFS-BUDGET-1, I-CONTEXT-SELECT-1, I-CONTEXT-SELECT-2, I-SEARCH-MAX-EDGES-1]
requires_invariants:  [I-INTENT-CANONICAL-1, I-POLICY-LAYER-1]
Inputs:               src/sdd/context_kernel/__init__.py
                      src/sdd/context_kernel/intent.py
                      src/sdd/policy/types.py
Outputs:              src/sdd/context_kernel/selection.py
Acceptance:           BFS early-stops at max_nodes * BFS_OVERSELECT_FACTOR; global_importance_score = max(priority) across ALL incoming edges in DeterministicGraph (not only edges in current Selection); RankedNode, RankedEdge, Selection constructors importable
Depends on:           T-5104, T-5105, T-5101

---

T-5108: Context Kernel — selection unit tests

Status:               DONE
Spec ref:             Spec_v51 §2.3 — Verification
Invariants Covered:   I-RANKED-NODE-BP-1, I-BFS-BUDGET-1, I-CONTEXT-SELECT-1
spec_refs:            [Spec_v51 §2.3, I-RANKED-NODE-BP-1, I-BFS-BUDGET-1]
produces_invariants:  []
requires_invariants:  [I-RANKED-NODE-BP-1, I-BFS-BUDGET-1]
Inputs:               src/sdd/context_kernel/selection.py
                      src/sdd/policy/types.py
Outputs:              tests/unit/context_kernel/test_selection.py
Acceptance:           pytest tests/unit/context_kernel/test_selection.py passes; BFS budget early-stop tested with mock DeterministicGraph; global_importance_score max-over-all-incoming-edges case tested
Depends on:           T-5107

---

T-5109: Context Kernel — DocumentChunk & DocProvider

Status:               DONE
Spec ref:             Spec_v51 §2.4 — DocumentChunk, ContentMapper (Protocol), DefaultContentMapper, DocProvider
Invariants Covered:   I-DOC-CHUNK-BOUNDARY-1, I-DOC-REFS-1, I-DOC-SI-ONLY-1, I-DOC-FS-IO-1, I-DOC-NON-FILE-1, I-DOC-2
spec_refs:            [Spec_v51 §2.4, I-DOC-FS-IO-1, I-DOC-NON-FILE-1, I-DOC-REFS-1]
produces_invariants:  [I-DOC-CHUNK-BOUNDARY-1, I-DOC-REFS-1, I-DOC-FS-IO-1, I-DOC-NON-FILE-1, I-DOC-2]
requires_invariants:  [I-CONTEXT-SELECT-1]
Inputs:               src/sdd/context_kernel/__init__.py
                      src/sdd/context_kernel/selection.py
Outputs:              src/sdd/context_kernel/documents.py
Acceptance:           DocProvider is the ONLY filesystem I/O point in context_kernel (enforced by grep in test); non-FILE nodes return empty DocumentChunk (not summary); references contain only valid node_ids from DeterministicGraph
Depends on:           T-5104, T-5107

---

T-5110: Context Kernel — Context dataclass

Status:               DONE
Spec ref:             Spec_v51 §2.4 — Context dataclass, migration shims
Invariants Covered:   I-CONTEXT-EXHAUSTED-1, I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4, I-LEGACY-FS-EXCEPTION-1
spec_refs:            [Spec_v51 §2.4, I-CONTEXT-EXHAUSTED-1, I-CTX-MIGRATION-1]
produces_invariants:  [I-CONTEXT-EXHAUSTED-1, I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4]
requires_invariants:  [I-INTENT-CANONICAL-1, I-CONTEXT-SELECT-1, I-DOC-FS-IO-1]
Inputs:               src/sdd/context_kernel/intent.py
                      src/sdd/context_kernel/selection.py
                      src/sdd/context_kernel/documents.py
Outputs:              src/sdd/context_kernel/context_types.py
Acceptance:           Context dataclass importable; does NOT import build_context.py anywhere in context_types.py (grep assertion); exhausted flag semantics correct
Depends on:           T-5109

---

T-5111: Context Kernel — doc provider unit tests

Status:               DONE
Spec ref:             Spec_v51 §2.4 — Verification
Invariants Covered:   I-DOC-FS-IO-1, I-DOC-NON-FILE-1, I-DOC-REFS-1
spec_refs:            [Spec_v51 §2.4, I-DOC-FS-IO-1, I-DOC-NON-FILE-1]
produces_invariants:  []
requires_invariants:  [I-DOC-FS-IO-1, I-DOC-NON-FILE-1, I-CONTEXT-EXHAUSTED-1]
Inputs:               src/sdd/context_kernel/documents.py
                      src/sdd/context_kernel/context_types.py
Outputs:              tests/unit/context_kernel/test_doc_provider.py
Acceptance:           pytest tests/unit/context_kernel/test_doc_provider.py passes; non-FILE node → empty chunk case explicit; filesystem operations isolated via tmp_path; grep assertion that DocProvider is sole I/O point
Depends on:           T-5109, T-5110

---

T-5112: Context Kernel — RAG types

Status:               DONE
Spec ref:             Spec_v51 §2.6 — LightRAGClient (Protocol), RAGResult, LightRAGProjection, NavigationResponse
Invariants Covered:   I-RAG-CLIENT-ISOLATION-1, I-RAG-NO-PERSISTENCE-1, I-RAG-NONDETERMINISTIC-1, I-RAG-LLM-CONFIG-1, I-LIGHTRAG-CANONICAL-1, I-NAV-RESPONSE-1, I-SEARCH-RESPONSE-1
spec_refs:            [Spec_v51 §2.6, I-RAG-CLIENT-ISOLATION-1, I-LIGHTRAG-CANONICAL-1, I-NAV-RESPONSE-1]
produces_invariants:  [I-RAG-CLIENT-ISOLATION-1, I-LIGHTRAG-CANONICAL-1, I-NAV-RESPONSE-1, I-SEARCH-RESPONSE-1]
requires_invariants:  [I-INTENT-CANONICAL-1, I-CONTEXT-EXHAUSTED-1]
Inputs:               src/sdd/context_kernel/intent.py
                      src/sdd/context_kernel/context_types.py
Outputs:              src/sdd/context_kernel/rag_types.py
Acceptance:           LightRAGClient is a Protocol (NO `import lightrag`); LightRAGProjection defined exactly once in rag_types.py (I-LIGHTRAG-CANONICAL-1 grep); NavigationResponse fields match Spec; graceful degradation when rag_client=None (DoD 4)
Depends on:           T-5110

---

T-5113: Context Kernel — ContextAssembler

Status:               DONE
Spec ref:             Spec_v51 §2.5 — ContextAssembler (deterministic truncation + document ordering)
Invariants Covered:   I-CONTEXT-BUDGET-1, I-CONTEXT-BUDGET-VALID-1, I-CONTEXT-TRUNCATE-1, I-CONTEXT-SEED-1, I-CONTEXT-ORDER-1, I-CONTEXT-LINEAGE-1, I-CONTEXT-DETERMINISM-1, I-RAG-POLICY-1, I-RAG-GROUNDING-1, I-RAG-KG-DEPENDENCY-1, I-RAG-DETACH-1
spec_refs:            [Spec_v51 §2.5, I-CONTEXT-TRUNCATE-1, I-CONTEXT-ORDER-1, I-CONTEXT-LINEAGE-1, I-CONTEXT-DETERMINISM-1]
produces_invariants:  [I-CONTEXT-BUDGET-1, I-CONTEXT-TRUNCATE-1, I-CONTEXT-ORDER-1, I-CONTEXT-LINEAGE-1, I-CONTEXT-DETERMINISM-1, I-RAG-POLICY-1]
requires_invariants:  [I-POLICY-LAYER-1, I-CONTEXT-SELECT-1, I-DOC-CHUNK-BOUNDARY-1, I-RAG-CLIENT-ISOLATION-1, I-CONTEXT-EXHAUSTED-1]
Inputs:               src/sdd/policy/types.py
                      src/sdd/context_kernel/selection.py
                      src/sdd/context_kernel/documents.py
                      src/sdd/context_kernel/context_types.py
                      src/sdd/context_kernel/rag_types.py
Outputs:              src/sdd/context_kernel/assembler.py
Acceptance:           Deterministic order — nodes: (hop ASC, -global_importance_score, node_id ASC); edges: (hop ASC, -priority, edge_id ASC); docs: (node_rank, kind, hash(content)); SEARCH context_id uses sha256(...:SEARCH:<raw_query_hash>); assembler.py contains NO `import build_context` (DoD 6)
Depends on:           T-5110, T-5112

---

T-5114: Context Kernel — assembler unit tests

Status:               DONE
Spec ref:             Spec_v51 §2.5 — Verification
Invariants Covered:   I-CONTEXT-TRUNCATE-1, I-CONTEXT-ORDER-1, I-CONTEXT-LINEAGE-1, I-CONTEXT-DETERMINISM-1
spec_refs:            [Spec_v51 §2.5, I-CONTEXT-TRUNCATE-1, I-CONTEXT-ORDER-1]
produces_invariants:  []
requires_invariants:  [I-CONTEXT-TRUNCATE-1, I-CONTEXT-ORDER-1, I-CONTEXT-LINEAGE-1]
Inputs:               src/sdd/context_kernel/assembler.py
                      src/sdd/context_kernel/rag_types.py
                      src/sdd/policy/types.py
Outputs:              tests/unit/context_kernel/test_assembler.py
Acceptance:           pytest tests/unit/context_kernel/test_assembler.py passes; test_context_id_deterministic included (DoD — R-CONTEXT-ID-SEARCH); sort order for nodes/edges/docs tested explicitly; grep assertion: no build_context.py import in assembler.py
Depends on:           T-5113

---

T-5115: Context Kernel — ContextEngine

Status:               DONE
Spec ref:             Spec_v51 §2.7 — ContextEngine (pure pipeline)
Invariants Covered:   I-ENGINE-PURE-1, I-ENGINE-INPUTS-1, I-ENGINE-POLICY-1, I-ARCH-MODEL-1, I-ARCH-MODEL-2
spec_refs:            [Spec_v51 §2.7, I-ENGINE-PURE-1, I-ENGINE-INPUTS-1, I-ENGINE-POLICY-1]
produces_invariants:  [I-ENGINE-PURE-1, I-ENGINE-INPUTS-1, I-ENGINE-POLICY-1, I-ARCH-MODEL-1, I-ARCH-MODEL-2]
requires_invariants:  [I-POLICY-RESOLVER-1, I-CONTEXT-SELECT-1, I-CONTEXT-BUDGET-1, I-CONTEXT-TRUNCATE-1]
Inputs:               src/sdd/policy/resolver.py
                      src/sdd/context_kernel/intent.py
                      src/sdd/context_kernel/selection.py
                      src/sdd/context_kernel/assembler.py
Outputs:              src/sdd/context_kernel/engine.py
Acceptance:           ContextEngine does NOT import SpatialIndex (grep; DoD 3 + R-RUNTIME-CONTRADICTION); pure pipeline (no filesystem I/O, no state mutation); instantiable with mock graph + policy + index; no sdd.graph_navigation imports
Depends on:           T-5113

---

T-5116: Context Kernel — ContextRuntime

Status:               DONE
Spec ref:             Spec_v51 §2.8 — ContextRuntime (lifecycle orchestrator)
Invariants Covered:   I-RUNTIME-BOUNDARY-1, I-RUNTIME-ORCHESTRATOR-1, I-CONTEXT-KERNEL-INPUT-1
spec_refs:            [Spec_v51 §2.8, I-RUNTIME-BOUNDARY-1, I-RUNTIME-ORCHESTRATOR-1]
produces_invariants:  [I-RUNTIME-BOUNDARY-1, I-RUNTIME-ORCHESTRATOR-1, I-CONTEXT-KERNEL-INPUT-1]
requires_invariants:  [I-ENGINE-PURE-1, I-PHASE-ISOLATION-1]
Inputs:               src/sdd/context_kernel/engine.py
                      src/sdd/context_kernel/context_types.py
                      src/sdd/context_kernel/rag_types.py
Outputs:              src/sdd/context_kernel/runtime.py
Acceptance:           ContextRuntime does NOT import GraphService (grep; DoD 5); lifecycle orchestrator (graph built by caller before query()); LightRAGProjection degradation to OFF when rag_client=None (DoD 4)
Depends on:           T-5115

---

T-5117: spatial/adapter.py — to_navigation_intent

Status:               DONE
Spec ref:             Spec_v51 §4 — spatial/adapter.py, BC-18 compat
Invariants Covered:   I-INTENT-CANONICAL-1, I-PHASE-ISOLATION-1
spec_refs:            [Spec_v51 §4, I-INTENT-CANONICAL-1]
produces_invariants:  [I-INTENT-CANONICAL-1]
requires_invariants:  [I-INTENT-SOURCE-OF-TRUTH-1]
Inputs:               src/sdd/spatial/index.py
                      src/sdd/context_kernel/intent.py
Outputs:              src/sdd/spatial/adapter.py
Acceptance:           to_navigation_intent() defined only in spatial/adapter.py (not in CLI, not in ContextEngine); BC-18 compatibility preserved; grep confirms single definition site
Depends on:           T-5105

---

T-5118: Context Kernel — engine & runtime INT-level tests

Status:               DONE
Spec ref:             Spec_v51 §6 — INT-1, INT-2, INT-3
Invariants Covered:   I-ENGINE-PURE-1, I-RUNTIME-BOUNDARY-1, I-CONTEXT-DETERMINISM-1
spec_refs:            [Spec_v51 §6, I-ENGINE-PURE-1, I-RUNTIME-BOUNDARY-1]
produces_invariants:  []
requires_invariants:  [I-ENGINE-PURE-1, I-RUNTIME-BOUNDARY-1, I-CONTEXT-DETERMINISM-1]
Inputs:               src/sdd/context_kernel/engine.py
                      src/sdd/context_kernel/runtime.py
                      src/sdd/policy/resolver.py
Outputs:              tests/unit/context_kernel/test_engine.py
                      tests/unit/context_kernel/test_runtime.py
Acceptance:           Integration-level: mock DeterministicGraph + PolicyResolver + SpatialIndex; pytest tests/unit/context_kernel/test_engine.py tests/unit/context_kernel/test_runtime.py passes; DoD 3 condition (ContextEngine instantiable with mocks)
Depends on:           T-5115, T-5116

---

T-5119: spatial/adapter unit tests

Status:               DONE
Spec ref:             Spec_v51 §6 — INT-6 Verification
Invariants Covered:   I-INTENT-CANONICAL-1
spec_refs:            [Spec_v51 §6, I-INTENT-CANONICAL-1]
produces_invariants:  []
requires_invariants:  [I-INTENT-CANONICAL-1]
Inputs:               src/sdd/spatial/adapter.py
                      src/sdd/context_kernel/intent.py
Outputs:              tests/unit/spatial/test_adapter.py
Acceptance:           pytest tests/unit/spatial/test_adapter.py passes; to_navigation_intent mapping tested for all intent variants
Depends on:           T-5117

---

T-5120: Import direction + mypy strict + DoD verification

Status:               DONE
Spec ref:             Spec_v51 §7 DoD Phase 51 + §6 INT-8, INT-10
Invariants Covered:   I-PHASE-ISOLATION-1, I-ARCH-MODEL-1
spec_refs:            [Spec_v51 §7, I-PHASE-ISOLATION-1, I-ARCH-MODEL-1]
produces_invariants:  []
requires_invariants:  [I-ENGINE-INPUTS-1, I-RUNTIME-BOUNDARY-1, I-CTX-MIGRATION-1, I-POLICY-RESOLVER-1]
Inputs:               src/sdd/policy/
                      src/sdd/context_kernel/
                      tests/unit/context_kernel/
                      tests/unit/policy/
Outputs:              tests/unit/context_kernel/test_import_direction.py
Acceptance:           test_import_direction_phase51 passes: sdd.context_kernel ↛ sdd.graph_navigation; sdd.policy ↛ sdd.context_kernel (DoD 1 + R-IMPORT-DIRECTION); mypy --strict on sdd.policy.* + sdd.context_kernel.* passes (DoD 8); pytest tests/unit/graph/ passes without change (DoD 9 — Phase 50 no regression); all DoD 1–9 verified
Depends on:           T-5118, T-5119

---

<!-- Granularity: 20 tasks (TG-2: 10–30). -->
<!-- Every task is independently implementable and independently testable (TG-1). -->

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
