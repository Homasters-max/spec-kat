# Plan_v51 — Phase 51: Context Kernel + Policy Layer

Status: DRAFT
Spec: specs/Spec_v51_ContextKernelPolicyLayer.md

---

## Logical Context

type: none
rationale: "Standard new phase. Реализует BC-36-P (Policy Layer) и BC-36-3 (Context Kernel) из разбивки Phase 36 на 50/51/52. Phase 50 (Graph Subsystem) завершён и заморожен."

---

## Milestones

### M1: Policy Layer — sdd.policy

```text
Spec:       §1 BC-36-P — Policy Layer
BCs:        BC-36-P
Invariants: I-POLICY-RESOLVER-1, I-POLICY-LAYER-1, I-POLICY-LAYER-PURE-1,
            I-CONTEXT-BUDGET-VALID-1, I-RAG-GLOBAL-V1-DISABLED-1
Depends:    — (no deps outside Phase 50 which is frozen)
Risks:      Budget validation (max_chars ≥ MIN_CONTEXT_SIZE) должна срабатывать
            при __post_init__ и при импорте PolicyResolver._DEFAULT (статический ассерт).
            Нарушение — DoD п.7.
Files:      src/sdd/policy/__init__.py
            src/sdd/policy/types.py         — Budget, RagMode, NavigationPolicy, MIN_CONTEXT_SIZE, BFS_OVERSELECT_FACTOR
            src/sdd/policy/resolver.py      — PolicyResolver._DEFAULT (5 intents), resolve()
            tests/unit/policy/test_resolver.py
```

### M2: Context Kernel — Intent & Selection

```text
Spec:       §2.2 QueryIntent, §2.3 RankedNode/RankedEdge/Selection
BCs:        BC-36-3
Invariants: I-INTENT-CANONICAL-1, I-INTENT-HEURISTIC-1, I-INTENT-SOURCE-OF-TRUTH-1,
            I-RANKED-NODE-BP-1, I-BFS-BUDGET-1, I-CONTEXT-SELECT-1, I-CONTEXT-SELECT-2,
            I-CONTEXT-EXPLAIN-KIND-1, I-SEARCH-CANDIDATE-1, I-SEARCH-AUTO-EXACT-1,
            I-SEARCH-NO-EMBED-1, I-SEARCH-MAX-EDGES-1
Depends:    M1 (Budget, RagMode нужны для BFS_OVERSELECT_FACTOR из policy/types.py)
Risks:      parse_query_intent MUST NOT infer EXPLAIN/TRACE (I-INTENT-HEURISTIC-1).
            BFS early-stop при max_nodes * BFS_OVERSELECT_FACTOR (I-BFS-BUDGET-1).
            I-RANKED-NODE-BP-1: global_importance_score = max(priority) по ВСЕМ incoming edges
            DeterministicGraph, не только по тем в текущей Selection.
            SEARCH auto-upgrade к RESOLVE_EXACT при единственном кандидате (I-SEARCH-AUTO-EXACT-1).
Files:      src/sdd/context_kernel/__init__.py
            src/sdd/context_kernel/intent.py     — QueryIntent (Enum), parse_query_intent(), SearchCandidate
            src/sdd/context_kernel/selection.py  — RankedNode, RankedEdge, Selection, _build_selection() BFS
            tests/unit/context_kernel/test_intent.py
            tests/unit/context_kernel/test_selection.py
```

### M3: Context Kernel — Documents & Context types

```text
Spec:       §2.4 DocumentChunk/Context, §3 BC-36-5 Legacy Migration
BCs:        BC-36-3, BC-36-5
Invariants: I-DOC-CHUNK-BOUNDARY-1, I-DOC-REFS-1, I-DOC-SI-ONLY-1, I-DOC-FS-IO-1,
            I-DOC-NON-FILE-1, I-DOC-2, I-CONTEXT-EXHAUSTED-1,
            I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4,
            I-LEGACY-FS-EXCEPTION-1
Depends:    M2 (Context использует QueryIntent; DocProvider использует node_id-ы из Selection)
Risks:      DocProvider единственная точка filesystem I/O в Context Kernel (I-DOC-FS-IO-1);
            non-FILE nodes возвращают пустой chunk, не суммаризацию (I-DOC-NON-FILE-1);
            references содержат только валидные node_id из DeterministicGraph (I-DOC-REFS-1).
            ContextAssembler НЕ должен импортировать build_context.py (I-CTX-MIGRATION-1).
Files:      src/sdd/context_kernel/documents.py    — DocumentChunk, ContentMapper (Protocol),
                                                     DefaultContentMapper, DocProvider
            src/sdd/context_kernel/context_types.py — Context dataclass
            tests/unit/context_kernel/test_doc_provider.py
```

### M4: Context Kernel — Assembler & RAG types

```text
Spec:       §2.5 ContextAssembler, §2.6 LightRAGClient/LightRAGProjection/NavigationResponse
BCs:        BC-36-3
Invariants: I-CONTEXT-BUDGET-1, I-CONTEXT-BUDGET-VALID-1, I-CONTEXT-TRUNCATE-1,
            I-CONTEXT-SEED-1, I-CONTEXT-ORDER-1, I-CONTEXT-LINEAGE-1,
            I-CONTEXT-DETERMINISM-1, I-NAV-RESPONSE-1, I-SEARCH-RESPONSE-1,
            I-RAG-POLICY-1, I-RAG-GROUNDING-1, I-RAG-KG-DEPENDENCY-1,
            I-RAG-DETACH-1, I-RAG-CLIENT-ISOLATION-1, I-RAG-NO-PERSISTENCE-1,
            I-RAG-NONDETERMINISTIC-1, I-RAG-LLM-CONFIG-1, I-LIGHTRAG-CANONICAL-1
Depends:    M1 (Budget, RagMode), M2 (Selection, SearchCandidate), M3 (Context, DocumentChunk)
Risks:      Детерминированный порядок в ContextAssembler: (hop ASC, -global_importance_score,
            node_id ASC) для nodes; (hop ASC, -priority, edge_id ASC) для edges;
            (node_rank, kind, hash(content)) для docs (I-CONTEXT-TRUNCATE-1, I-CONTEXT-ORDER-1).
            context_id для SEARCH = sha256(...:SEARCH:<query_hash>) отличается от non-SEARCH
            (I-CONTEXT-LINEAGE-1). LightRAGClient — Protocol, не import lightrag
            (R-LIGHTRAG-COUPLING fix). LightRAGProjection = stub; rag_client=None → None
            (graceful degradation). class LightRAGProjection в одном файле ровно один раз
            (I-LIGHTRAG-CANONICAL-1).
Files:      src/sdd/context_kernel/assembler.py   — ContextAssembler (deterministic truncation
                                                    + document ordering)
            src/sdd/context_kernel/rag_types.py   — LightRAGClient (Protocol), RAGResult,
                                                    LightRAGProjection (stub), NavigationResponse
            tests/unit/context_kernel/test_assembler.py
```

### M5: Context Kernel — Engine, Runtime & spatial/adapter

```text
Spec:       §2.7 ContextEngine, §2.8 ContextRuntime, §4 spatial/adapter.py
BCs:        BC-36-3
Invariants: I-ENGINE-PURE-1, I-ENGINE-INPUTS-1, I-ENGINE-POLICY-1,
            I-RUNTIME-BOUNDARY-1, I-RUNTIME-ORCHESTRATOR-1, I-CONTEXT-KERNEL-INPUT-1,
            I-INTENT-CANONICAL-1, I-PHASE-ISOLATION-1, I-ARCH-MODEL-1, I-ARCH-MODEL-2
Depends:    M1..M4
Risks:      ContextEngine НЕ импортирует SpatialIndex (I-ENGINE-INPUTS-1, grep-тест);
            ContextRuntime НЕ импортирует GraphService (I-RUNTIME-BOUNDARY-1, grep-тест);
            sdd.context_kernel НЕ импортирует из sdd.graph_navigation;
            sdd.policy НЕ импортирует из sdd.context_kernel (I-PHASE-ISOLATION-1);
            to_navigation_intent живёт только в spatial/adapter.py, не в CLI/ContextEngine
            (I-INTENT-CANONICAL-1).
Files:      src/sdd/context_kernel/engine.py    — ContextEngine (pure pipeline)
            src/sdd/context_kernel/runtime.py   — ContextRuntime (lifecycle orchestrator)
            src/sdd/spatial/adapter.py          — to_navigation_intent() (BC-18 compat)
            tests/unit/context_kernel/test_engine.py
            tests/unit/context_kernel/test_runtime.py
            tests/unit/spatial/test_adapter.py
```

### M6: Integration tests & DoD verification

```text
Spec:       §6 Verification (INT-1..3, 6, 8, 10), §7 DoD Phase 51
BCs:        BC-36-3, BC-36-P
Invariants: все из DoD §7 + I-PHASE-ISOLATION-1
Depends:    M1..M5
Risks:      mypy --strict может выявить несоответствия Protocol; запускать на
            sdd.policy.* + sdd.context_kernel.* изолированно.
            Phase 50 регрессия: все тесты tests/unit/graph/ должны проходить без изменений.
Files:      tests/unit/context_kernel/test_engine.py   (INT-level mock: graph+policy+index)
            tests/unit/context_kernel/test_runtime.py  (INT-level)
            + все тесты из M1..M5 (итого 32+ unit-тестов по DoD п.2)
Checks:     sdd.policy + sdd.context_kernel importable, zero circular imports   (DoD 1)
            32 unit-тесты pass                                                  (DoD 2)
            ContextEngine инстанциируем с mock graph/policy/index               (DoD 3)
            LightRAGProjection graceful degradation к OFF при rag_client=None   (DoD 4)
            grep: ContextRuntime не импортирует GraphService                    (DoD 5)
            grep: ContextAssembler не импортирует build_context.py              (DoD 6)
            PolicyResolver._DEFAULT покрывает все 5 QueryIntent                 (DoD 7)
            mypy --strict на sdd.policy.* + sdd.context_kernel.*               (DoD 8)
            Phase 50 тесты не регрессируют                                      (DoD 9)
```

---

## Risk Notes

- **R-RUNTIME-CONTRADICTION**: `ContextRuntime` НЕ держит `GraphService`. Граф строится CLI до вызова `query()`. Invariant: I-RUNTIME-BOUNDARY-1. Mitigation: grep-тест в M5 + DoD 5.
- **R-LIGHTRAG-COUPLING**: `LightRAGClient` — `Protocol` (structural typing), без `import lightrag`. Installability: `lightrag` не требуется для Phase 51. Mitigation: `LightRAGProjection` stub + graceful degradation (M4 + DoD 4).
- **R-FUZZY-ALGO**: SEARCH fuzzy score через BM25 (label + summary corpus). Embedding-based similarity FORBIDDEN (I-SEARCH-NO-EMBED-1). Mitigation: test_search_no_embeddings в M2.
- **R-IMPORT-DIRECTION**: `sdd.context_kernel` ↛ `sdd.graph_navigation`; `sdd.policy` ↛ `sdd.context_kernel`. Нарушение незаметно без tooling. Mitigation: `test_import_direction_phase51` в M5; запускается в CI.
- **R-CONTEXT-ID-SEARCH**: SEARCH `context_id` вычисляется через `raw_query` hash (нет единственного seed). Нарушение при упрощении логики приводит к коллизиям context_id. Mitigation: `test_context_id_deterministic` (test 52 в §6).
