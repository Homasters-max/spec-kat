# TaskSet_v55 — Phase 55: Graph-Guided Implement

Spec: specs/Spec_v55_GraphGuidedImplement.md
Plan: plans/Plan_v55.md

---

## M1: Engine Threading — `--edge-types` (BC-55-P2)

T-5501: Add `allowed_kinds` to `_expand_explain` / `_expand_trace` + thread through `ContextEngine.query()`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P2 — Engine Threading; §4 ContextEngine interfaces
Invariants:           I-ENGINE-EDGE-FILTER-1
spec_refs:            [Spec_v55 §2 BC-55-P2, Spec_v55 §4, I-ENGINE-EDGE-FILTER-1]
produces_invariants:  [I-ENGINE-EDGE-FILTER-1]
requires_invariants:  [I-HANDLER-PURE-1, I-ENGINE-PURE-1, I-INTENT-HEURISTIC-1]
Inputs:               src/sdd/context_kernel/engine.py
Outputs:              src/sdd/context_kernel/engine.py
Acceptance:           `_expand_explain(graph, node, 0, allowed_kinds=frozenset({"implements"}))` — hop=1 nodes reachable only via implements; `allowed_kinds=None` → uses `_EXPLAIN_OUT_KINDS` default (backward compat); `ContextEngine.query()` accepts `edge_types: frozenset[str] | None = None`
Depends on:           —

---

T-5502: Thread `edge_types` through `ContextRuntime.query()`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P2 — Engine Threading; §4 ContextRuntime interface
Invariants:           I-ENGINE-EDGE-FILTER-1
spec_refs:            [Spec_v55 §2 BC-55-P2, Spec_v55 §4, I-ENGINE-EDGE-FILTER-1]
produces_invariants:  [I-ENGINE-EDGE-FILTER-1]
requires_invariants:  [I-ENGINE-EDGE-FILTER-1]
Inputs:               src/sdd/context_kernel/runtime.py,
                      src/sdd/context_kernel/engine.py
Outputs:              src/sdd/context_kernel/runtime.py
Acceptance:           `ContextRuntime.query()` accepts `edge_types: frozenset[str] | None = None` and forwards to `ContextEngine.query()`
Depends on:           T-5501

---

T-5503: Add `--edge-types` CLI arg to `explain.py` and `trace.py`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P2 — CLI parsing; §4 CLI interface
Invariants:           I-ENGINE-EDGE-FILTER-1
spec_refs:            [Spec_v55 §2 BC-55-P2, Spec_v55 §4]
produces_invariants:  [I-ENGINE-EDGE-FILTER-1]
requires_invariants:  [I-ENGINE-EDGE-FILTER-1]
Inputs:               src/sdd/graph_navigation/cli/explain.py,
                      src/sdd/graph_navigation/cli/trace.py,
                      src/sdd/context_kernel/runtime.py
Outputs:              src/sdd/graph_navigation/cli/explain.py,
                      src/sdd/graph_navigation/cli/trace.py
Acceptance:           `sdd explain NODE --edge-types implements,guards` parses to `frozenset({"implements","guards"})` and passes to runtime; `--edge-types ""` → non-zero exit with error message (not silent empty result); no `--edge-types` → None (backward compat)
Depends on:           T-5502

---

T-5504: Tests for edge_types BFS filter correctness

Status:               DONE
Spec ref:             Spec_v55 §9 Verification #1–4
Invariants:           I-ENGINE-EDGE-FILTER-1
spec_refs:            [Spec_v55 §9 Verification #1-4, I-ENGINE-EDGE-FILTER-1]
produces_invariants:  [I-ENGINE-EDGE-FILTER-1]
requires_invariants:  [I-ENGINE-EDGE-FILTER-1]
Inputs:               src/sdd/context_kernel/engine.py,
                      src/sdd/context_kernel/runtime.py,
                      tests/unit/context_kernel/test_engine.py,
                      tests/unit/context_kernel/test_runtime.py
Outputs:              tests/unit/context_kernel/test_engine.py,
                      tests/unit/context_kernel/test_runtime.py
Acceptance:           (1) BFS filter test: graph where node reachable via non-allowed edge at hop=1 — verify excluded; (2) backward compat: `allowed_kinds=None` matches pre-Phase-55 output; (3) `_expand_trace(graph, node, 0, allowed_kinds=frozenset({"imports"}))` — only imports in-edges; (4) `ContextRuntime.query(..., edge_types=frozenset())` → ValueError raised
Depends on:           T-5503

---

## M2: TaskNavigationSpec (BC-55-P3)

T-5505: Create `src/sdd/domain/tasks/navigation.py` — `ResolveKeyword` + `TaskNavigationSpec`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P3 — TaskNavigationSpec; §4 Types
Invariants:           I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2
spec_refs:            [Spec_v55 §2 BC-55-P3, Spec_v55 §4, I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
produces_invariants:  [I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
requires_invariants:  [—]
Inputs:               src/sdd/domain/tasks/parser.py
Outputs:              src/sdd/domain/tasks/navigation.py
Acceptance:           `python3 -c "from sdd.domain.tasks.navigation import TaskNavigationSpec, ResolveKeyword; print('OK')"` → OK; frozen dataclass with `write_scope`, `resolve_keywords`, `anchor_nodes`, `allowed_traversal`; `is_anchor_mode()` returns True only when `anchor_nodes` non-empty; `parse()` classmethod accepts dict
Depends on:           —

---

T-5506: Update `src/sdd/domain/tasks/parser.py` — parse `Navigation:` section → `Task.navigation`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P3 — parser backward compat; §6 BC-55-P3 Post Conditions
Invariants:           I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2
spec_refs:            [Spec_v55 §2 BC-55-P3, I-DECOMPOSE-RESOLVE-1]
produces_invariants:  [I-DECOMPOSE-RESOLVE-1]
requires_invariants:  [I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
Inputs:               src/sdd/domain/tasks/parser.py,
                      src/sdd/domain/tasks/navigation.py
Outputs:              src/sdd/domain/tasks/parser.py
Acceptance:           TaskSet with `Navigation:` section → `task.navigation` is `TaskNavigationSpec` instance; TaskSet without `Navigation:` section → `task.navigation is None` (no exception); existing TaskSet parsing unchanged
Depends on:           T-5505

---

T-5507: Tests for TaskNavigationSpec parsing

Status:               DONE
Spec ref:             Spec_v55 §9 Verification #5–6
Invariants:           I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2
spec_refs:            [Spec_v55 §9 Verification #5-6, I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
produces_invariants:  [I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
requires_invariants:  [I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
Inputs:               src/sdd/domain/tasks/navigation.py,
                      src/sdd/domain/tasks/parser.py
Outputs:              tests/unit/domain/test_task_navigation.py
Acceptance:           (5) TaskSet markdown with `resolve_keywords` + `write_scope` → `TaskNavigationSpec` parsed correctly; (6) TaskSet without Navigation section → `task.navigation = None` without exception; `is_anchor_mode()` returns False for v55 tasks; `is_anchor_mode()` returns True when `anchor_nodes` non-empty
Depends on:           T-5506

---

## M3: NORM-GRAPH-001 + NORM-SCOPE-002 Update (BC-55-P4, BC-55-P6)

T-5508: Add `NORM-GRAPH-001` to `.sdd/norms/norm_catalog.yaml`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P4 — NORM-GRAPH-001
Invariants:           I-RRL-1, I-RRL-2, I-RRL-3
spec_refs:            [Spec_v55 §2 BC-55-P4, I-RRL-1, I-RRL-2, I-RRL-3]
produces_invariants:  [I-RRL-1, I-RRL-2, I-RRL-3]
requires_invariants:  [I-RRL-1, I-RRL-2, I-RRL-3]
Inputs:               .sdd/norms/norm_catalog.yaml
Outputs:              .sdd/norms/norm_catalog.yaml
Acceptance:           `sdd norm-guard check --actor llm --action graph_resolve` → exit 0; `NORM-GRAPH-001` entry present with `actor: llm`, `allowed_actions: [graph_resolve, graph_explain, graph_trace]`, `applies_to_sessions: [IMPLEMENT, DECOMPOSE]`, `enforcement: hard`
Depends on:           —

---

T-5509: Update `NORM-SCOPE-002` + add `GRAPH_NAVIGATION_OVERRIDE` to `.sdd/norms/norm_catalog.yaml`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P6 — NORM-SCOPE-002 Update
Invariants:           I-RRL-1, I-RRL-2, I-RRL-3, I-IMPLEMENT-GRAPH-1
spec_refs:            [Spec_v55 §2 BC-55-P6, I-RRL-1, I-RRL-2, I-RRL-3, I-IMPLEMENT-GRAPH-1]
produces_invariants:  [I-IMPLEMENT-GRAPH-1]
requires_invariants:  [I-RRL-1, I-RRL-2, I-RRL-3]
Inputs:               .sdd/norms/norm_catalog.yaml
Outputs:              .sdd/norms/norm_catalog.yaml
Acceptance:           `NORM-SCOPE-002.exception` includes both Task Inputs AND graph-justified read clauses; `norm_resolution_policy.overrides` contains `GRAPH_NAVIGATION_OVERRIDE` with `allowed_norms: [NORM-SCOPE-002]` and `requires_norm: NORM-GRAPH-001`; existing `TASK_INPUT_OVERRIDE` preserved
Depends on:           T-5508

---

## M4: RAGPolicy Declaration (BC-55-P9)

T-5510: Verify `RAGPolicy` type + `rag_policy` field in `src/sdd/policy/__init__.py`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P9 — RAGPolicy Declaration; §4 RAGPolicy type; §5 I-ARCH-LAYER-SEPARATION-1
Invariants:           I-ARCH-LAYER-SEPARATION-1, I-RAG-1, I-RAG-SCOPE-1, I-RAG-SCOPE-ENTRY-1, I-RAG-QUERY-1, I-BM25-SINGLETON-1
spec_refs:            [Spec_v55 §2 BC-55-P9, Spec_v55 §4, I-ARCH-LAYER-SEPARATION-1, I-RAG-1, I-RAG-SCOPE-1]
produces_invariants:  [I-ARCH-LAYER-SEPARATION-1, I-RAG-1, I-RAG-SCOPE-1, I-RAG-SCOPE-ENTRY-1, I-RAG-QUERY-1, I-BM25-SINGLETON-1]
requires_invariants:  [—]
Inputs:               src/sdd/policy/__init__.py
Outputs:              src/sdd/policy/__init__.py
Acceptance:           `python3 -c "from sdd.policy import RAGPolicy, NavigationPolicy; p=RAGPolicy(); assert p.allow_global_search is False; print('OK')"` → OK; `NavigationPolicy(budget=..., rag_mode=...)` instantiates without `rag_policy` kwarg (default_factory); frozen dataclass with `max_documents=20`, `allow_global_search=False`, `min_graph_hops=0`; existing callers of `NavigationPolicy` unchanged (backward compat check — no positional arg breakage)
Depends on:           —

---

## M5: MODULE Nodes + contains edges (BC-55-P7)

T-5511: Add `"contains": 0.45` to `EDGE_KIND_PRIORITY` + `"module_path"` to `ALLOWED_META_KEYS` in `graph/types.py`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P7 — MODULE Nodes; ALLOWED_META_KEYS update
Invariants:           I-MODULE-COHESION-1
spec_refs:            [Spec_v55 §2 BC-55-P7, I-MODULE-COHESION-1]
produces_invariants:  [I-MODULE-COHESION-1]
requires_invariants:  [—]
Inputs:               src/sdd/graph/types.py
Outputs:              src/sdd/graph/types.py
Acceptance:           `EDGE_KIND_PRIORITY["contains"] == 0.45`; `"module_path" in ALLOWED_META_KEYS`; existing keys and values in `EDGE_KIND_PRIORITY` unchanged; `tests/unit/graph/test_types.py` passes
Depends on:           —

---

T-5512: Add `_collect_modules()` to `IndexBuilder` in `src/sdd/spatial/index.py`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P7 — IndexBuilder._collect_modules() logic; §6 BC-55-P7 Pre/Post Conditions
Invariants:           I-MODULE-COHESION-1
spec_refs:            [Spec_v55 §2 BC-55-P7, Spec_v55 §6, I-MODULE-COHESION-1]
produces_invariants:  [I-MODULE-COHESION-1]
requires_invariants:  [I-MODULE-COHESION-1]
Inputs:               src/sdd/spatial/index.py,
                      src/sdd/graph/types.py
Outputs:              src/sdd/spatial/index.py
Acceptance:           `_collect_modules()` scans `src/sdd/*/` for `__init__.py` packages; returns `SpatialNode` per sub-package with `node_id=MODULE:<dotted.path>`, `kind="MODULE"`, `meta.path=<rel-path>`; nested packages: most specific module wins (sort by dotted-path length desc); purely path-based, no heuristics
Depends on:           T-5511

---

T-5513: Create `src/sdd/graph/extractors/module_edges.py` — `ModuleEdgeExtractor`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P7 — ModuleEdgeExtractor
Invariants:           I-MODULE-COHESION-1
spec_refs:            [Spec_v55 §2 BC-55-P7, I-MODULE-COHESION-1]
produces_invariants:  [I-MODULE-COHESION-1]
requires_invariants:  [I-MODULE-COHESION-1]
Inputs:               src/sdd/graph/types.py,
                      src/sdd/spatial/index.py
Outputs:              src/sdd/graph/extractors/module_edges.py
Acceptance:           `ModuleEdgeExtractor.EXTRACTOR_VERSION = "1.0.0"`; `extract(index)` maps each FILE node to most specific MODULE via path prefix → `contains` edge with `priority=0.45`; FILE nodes with no matching MODULE skipped gracefully; `sdd explain MODULE:sdd.graph --edge-types contains` (after rebuild) returns FILE nodes in `src/sdd/graph/`
Depends on:           T-5512

---

T-5514: Register `ModuleEdgeExtractor` in `src/sdd/graph/extractors/__init__.py`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P7 — extractor registration
Invariants:           I-MODULE-COHESION-1
spec_refs:            [Spec_v55 §2 BC-55-P7, I-MODULE-COHESION-1]
produces_invariants:  [I-MODULE-COHESION-1]
requires_invariants:  [I-MODULE-COHESION-1]
Inputs:               src/sdd/graph/extractors/__init__.py,
                      src/sdd/graph/extractors/module_edges.py
Outputs:              src/sdd/graph/extractors/__init__.py
Acceptance:           `ModuleEdgeExtractor` appears in extractor registry; existing extractors (`AstEdgeExtractor`, `ImplementsEdgeExtractor`, `TestedByEdgeExtractor` etc.) remain registered; no import errors
Depends on:           T-5513

---

T-5515: Tests for MODULE nodes and `contains` edges

Status:               DONE
Spec ref:             Spec_v55 §9 Verification #8–9; §11 Step 55-B
Invariants:           I-MODULE-COHESION-1
spec_refs:            [Spec_v55 §9 Verification #8-9, Spec_v55 §11, I-MODULE-COHESION-1]
produces_invariants:  [I-MODULE-COHESION-1]
requires_invariants:  [I-MODULE-COHESION-1]
Inputs:               src/sdd/graph/extractors/module_edges.py,
                      src/sdd/spatial/index.py,
                      tests/unit/graph/test_extractors.py,
                      tests/unit/spatial/test_index.py
Outputs:              tests/unit/graph/test_extractors.py,
                      tests/unit/spatial/test_index.py
Acceptance:           (8) `MODULE:sdd.graph` node exists in SpatialIndex after nav-rebuild; (9) `ModuleEdgeExtractor.extract()` produces `contains` edges from `MODULE:sdd.graph` to FILE nodes in `src/sdd/graph/`; nested path collision test: `src/sdd/graph/extractors/module_edges.py` maps to `MODULE:sdd.graph.extractors` (most specific, not `MODULE:sdd.graph`)
Depends on:           T-5514

---

## M6: Session Context infrastructure (BC-55-P8)

T-5516: Create `src/sdd/infra/session_context.py` — `get_current_session_id()` + `set_current_session()`

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P8 — Session Context; §4 Session Context interfaces
Invariants:           I-SESSION-CONTEXT-1
spec_refs:            [Spec_v55 §2 BC-55-P8, Spec_v55 §4, I-SESSION-CONTEXT-1]
produces_invariants:  [I-SESSION-CONTEXT-1]
requires_invariants:  [—]
Inputs:               src/sdd/infra/audit.py,
                      src/sdd/infra/paths.py
Outputs:              src/sdd/infra/session_context.py
Acceptance:           `get_current_session_id()` returns `None` if `.sdd/runtime/current_session.json` absent or malformed — MUST NOT raise; `set_current_session(session_id, session_type, phase_id)` writes atomically via `atomic_write` from `infra/audit.py`; output JSON schema matches `{session_id, session_type, phase_id, declared_at}` (ISO 8601)
Depends on:           —

---

T-5517: Update `src/sdd/commands/record_session.py` — call `set_current_session()` atomically

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P8 — who writes current_session.json; §11 Step 55-D
Invariants:           I-SESSION-CONTEXT-1
spec_refs:            [Spec_v55 §2 BC-55-P8, Spec_v55 §11, I-SESSION-CONTEXT-1]
produces_invariants:  [I-SESSION-CONTEXT-1]
requires_invariants:  [I-SESSION-CONTEXT-1]
Inputs:               src/sdd/commands/record_session.py,
                      src/sdd/infra/session_context.py
Outputs:              src/sdd/commands/record_session.py
Acceptance:           After `sdd record-session --type IMPLEMENT --phase 55`: `.sdd/runtime/current_session.json` exists with correct `session_id` (UUID), `session_type="IMPLEMENT"`, `phase_id=55`; `I-SESSION-CONTEXT-1`: no other command path writes `current_session.json`
Depends on:           T-5516

---

T-5518: Tests for session_context (None when absent, write + read via record-session)

Status:               DONE
Spec ref:             Spec_v55 §9 Verification #10–11; §11 Step 55-D
Invariants:           I-SESSION-CONTEXT-1
spec_refs:            [Spec_v55 §9 Verification #10-11, Spec_v55 §11, I-SESSION-CONTEXT-1]
produces_invariants:  [I-SESSION-CONTEXT-1]
requires_invariants:  [I-SESSION-CONTEXT-1]
Inputs:               src/sdd/infra/session_context.py,
                      src/sdd/commands/record_session.py
Outputs:              tests/unit/infra/test_session_context.py
Acceptance:           (10) `get_current_session_id()` returns `None` when file absent; returns `None` when file contains invalid JSON (no exception); (11) after `set_current_session(uuid, "IMPLEMENT", 55)`: `get_current_session_id()` returns that UUID; `declared_at` is valid ISO 8601 timestamp
Depends on:           T-5517

---

## M7: Graph-Guided Implement Protocol + Documentation (BC-55-P1, BC-55-P5)

T-5519: Update `.sdd/docs/sessions/implement.md` — add STEP 4.5 Graph Discovery

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P1 — STEP 4.5; §6 STEP 4.5 Pre/Post Conditions; §7 UC-55-1
Invariants:           I-IMPLEMENT-GRAPH-1, I-IMPLEMENT-TRACE-1, I-IMPLEMENT-SCOPE-1, I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2
spec_refs:            [Spec_v55 §2 BC-55-P1, Spec_v55 §6, Spec_v55 §7 UC-55-1, I-IMPLEMENT-GRAPH-1, I-IMPLEMENT-TRACE-1, I-IMPLEMENT-SCOPE-1]
produces_invariants:  [I-IMPLEMENT-GRAPH-1, I-IMPLEMENT-TRACE-1, I-IMPLEMENT-SCOPE-1]
requires_invariants:  [I-ENGINE-EDGE-FILTER-1, I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2, I-SESSION-CONTEXT-1]
Inputs:               .sdd/docs/sessions/implement.md,
                      src/sdd/context_kernel/engine.py,
                      src/sdd/domain/tasks/navigation.py
Outputs:              .sdd/docs/sessions/implement.md
Acceptance:           STEP 4.5 inserted between STEP 4 and STEP 5; includes: (1) anchor discovery via `sdd resolve`, (2) dependency traversal via `sdd explain --edge-types`, (3) before-write trace via `sdd trace --edge-types`; `graph_budget` warning-only note present; FORBIDDEN grep-based navigation noted; `task.navigation is None` fallback protocol documented; SEM-13 sequential chain preserved
Depends on:           T-5503, T-5506, T-5508, T-5514, T-5517

---

T-5520: Update `.sdd/docs/sessions/decompose.md` — add keyword validation step

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P1 — decompose.md keyword validation; §9 Verification #12
Invariants:           I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2
spec_refs:            [Spec_v55 §2 BC-55-P1, Spec_v55 §9 Verification #12, I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
produces_invariants:  [I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
requires_invariants:  [I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2]
Inputs:               .sdd/docs/sessions/decompose.md,
                      src/sdd/domain/tasks/navigation.py
Outputs:              .sdd/docs/sessions/decompose.md
Acceptance:           Decompose session includes keyword validation step: for each `resolve_keywords` entry in TaskNavigationSpec → `sdd resolve "<keyword>" --format json` must exit 0 (I-DECOMPOSE-RESOLVE-1); top-1 candidate kind ∈ expected_kinds (I-DECOMPOSE-RESOLVE-2); invalid keyword → STOP per §9 Verification #12; existing session steps preserved
Depends on:           T-5506, T-5508

---

T-5521: Update `.sdd/docs/ref/tool-reference.md` — add Graph Navigation Commands section

Status:               DONE
Spec ref:             Spec_v55 §2 BC-55-P5 — tool-reference.md; §4 CLI interfaces
Invariants:           I-IMPLEMENT-GRAPH-1
spec_refs:            [Spec_v55 §2 BC-55-P5, Spec_v55 §4, I-IMPLEMENT-GRAPH-1]
produces_invariants:  [I-IMPLEMENT-GRAPH-1]
requires_invariants:  [I-ENGINE-EDGE-FILTER-1]
Inputs:               .sdd/docs/ref/tool-reference.md,
                      src/sdd/graph_navigation/cli/explain.py,
                      src/sdd/graph_navigation/cli/trace.py
Outputs:              .sdd/docs/ref/tool-reference.md
Acceptance:           New section "Graph Navigation Commands (IMPLEMENT-allowed)" added; documents `sdd resolve --format json` (STEP 4.5 usage), `sdd explain --edge-types TYPE1,...` (traversal from anchor), `sdd trace --edge-types TYPE1,...` (reverse traversal); all three commands with correct flags per Spec_v55 §4; existing tool-reference entries unchanged
Depends on:           T-5503, T-5508

---

<!-- Granularity: 21 tasks (TG-2: 10–30). All tasks independently implementable and independently testable (TG-1). -->
<!-- Each task declares Inputs + Outputs + Invariants Covered (TG-3). -->
<!-- TaskSet covers all Plan milestones M1–M7 (SDD-3). -->
