# Plan_v55 — Phase 55: Graph-Guided Implement

Status: DRAFT
Spec: specs/Spec_v55_GraphGuidedImplement.md

---

## Logical Context

```
type: none
rationale: "Standard new phase. Extends graph navigation infrastructure to enforce deterministic context in IMPLEMENT sessions, adds MODULE nodes, TaskNavigationSpec type, and session context infrastructure."
```

---

## Milestones

### M1: Engine Threading — `--edge-types` parameter (BC-55-P2)

```text
Spec:       §2 BC-55-P2, §4 ContextEngine/ContextRuntime interfaces, §9 Verification #1–4
BCs:        BC-55-P2
Invariants: I-ENGINE-EDGE-FILTER-1
Depends:    — (foundational, no prior milestone required)
Risks:      BFS filter applied in wrong layer → silent correctness bug (I-ENGINE-EDGE-FILTER-1).
            Must verify: nodes at hop=1 reachable ONLY via allowed_kinds, not via post-filter.
            Backward compat: without --edge-types behavior identical to current (allowed_kinds=None).
```

### M2: TaskNavigationSpec type (BC-55-P3)

```text
Spec:       §2 BC-55-P3, §4 TaskNavigationSpec interfaces, §9 Verification #5–6
BCs:        BC-55-P3
Invariants: I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2
Depends:    — (independent type definition, no external deps)
Risks:      Existing TaskSets without navigation section must parse to task.navigation=None.
            Must not break current parser.py — backward-compat required.
```

### M3: NORM-GRAPH-001 + NORM-SCOPE-002 Update (BC-55-P4, BC-55-P6)

```text
Spec:       §2 BC-55-P4, §2 BC-55-P6, §9 Verification #7
BCs:        BC-55-P4, BC-55-P6
Invariants: I-RRL-1, I-RRL-2, I-RRL-3
Depends:    — (norm catalog changes independent of code)
Risks:      NORM-SCOPE-002 update must preserve existing TASK-INPUT-LAYER override.
            GRAPH_NAVIGATION_OVERRIDE requires_norm: NORM-GRAPH-001 — must be added to policy.
            Note: BC-55-P6 describes intent; actual norm_catalog.yaml change is human-gated
            at activate-phase 55.
```

### M4: RAGPolicy Declaration (BC-55-P9)

```text
Spec:       §2 BC-55-P9, §4 RAGPolicy type, §5 I-ARCH-LAYER-SEPARATION-1
BCs:        BC-55-P9
Invariants: I-ARCH-LAYER-SEPARATION-1 (declared), I-RAG-1 (declared), I-RAG-SCOPE-1 (declared),
            I-RAG-SCOPE-ENTRY-1 (declared), I-RAG-QUERY-1 (declared), I-BM25-SINGLETON-1 (declared)
Depends:    — (type declaration only, enforcement in Phase 57–58)
Risks:      Default field (default_factory=RAGPolicy) in NavigationPolicy MUST preserve
            backward compat for all existing callers. No enforcement in Phase 55 —
            only declaration. Soft/hard enforcement deferred to Phase 57/58.
```

### M5: MODULE Nodes + contains edges (BC-55-P7)

```text
Spec:       §2 BC-55-P7, §6 Pre/Post Conditions BC-55-P7, §9 Verification #8–9, §11 Step 55-B
BCs:        BC-55-P7
Invariants: I-MODULE-COHESION-1 (defined, enforcement Phase 57)
Depends:    M1 (engine threading complete before testing MODULE explain traversal)
Risks:      _collect_modules() must be purely path-based (deterministic, no heuristics).
            ModuleEdgeExtractor maps FILE nodes to MODULE via path prefix — must handle nested
            packages (sdd.graph vs sdd.graph.extractors).
            ALLOWED_META_KEYS in types.py must include "module_path" before extractor runs.
```

### M6: Session Context infrastructure (BC-55-P8)

```text
Spec:       §2 BC-55-P8, §4 Session Context interfaces, §5 I-SESSION-CONTEXT-1,
            §9 Verification #10–11, §11 Step 55-D
BCs:        BC-55-P8
Invariants: I-SESSION-CONTEXT-1
Depends:    — (independent infra module)
Risks:      atomic_write must be used (from infra/audit.py) to avoid partial writes.
            get_current_session_id() MUST NOT raise — returns None if file absent/malformed.
            Only sdd record-session handler may write current_session.json (I-SESSION-CONTEXT-1).
```

### M7: Graph-Guided Implement Protocol + Documentation (BC-55-P1, BC-55-P5)

```text
Spec:       §2 BC-55-P1, §2 BC-55-P5, §6 Pre/Post Conditions STEP 4.5,
            §7 UC-55-1, §9 Verification #12
BCs:        BC-55-P1, BC-55-P5
Invariants: I-IMPLEMENT-GRAPH-1, I-IMPLEMENT-TRACE-1, I-IMPLEMENT-SCOPE-1,
            I-DECOMPOSE-RESOLVE-1, I-DECOMPOSE-RESOLVE-2
Depends:    M1 (engine threading), M2 (TaskNavigationSpec), M3 (NORM-GRAPH-001),
            M5 (MODULE nodes), M6 (session context)
Risks:      STEP 4.5 inserts between STEP 4 and STEP 5 in implement.md — must not break
            existing session contract. SEM-13 sequential chain preserved.
            graph_budget is warning-only (not blocking) — document explicitly.
            FORBIDDEN: grep-based navigation in STEP 4.5 and after.
            tool-reference.md update must include all three CLI commands with correct flags.
```

---

## Risk Notes

- R-1: **Engine backward compat** — `--edge-types` without flag must produce identical output to current phase. Unit test: `_expand_explain(graph, node, 0, allowed_kinds=None)` must match legacy behavior. Mitigation: `allowed_kinds=None` → fallback to `_EXPLAIN_OUT_KINDS` (existing default).

- R-2: **BFS filter correctness** — post-filter is explicitly forbidden (I-ENGINE-EDGE-FILTER-1). Risk of implementing as post-filter and passing tests due to shallow graphs. Mitigation: test with a graph where nodes are reachable via non-allowed edges only at hop=1 to verify they're excluded.

- R-3: **TaskSet parser backward compat** — existing TaskSets without `Navigation:` section must not fail parsing. All `task.navigation = None` for legacy tasks. Mitigation: parser returns None for missing section, no exception.

- R-4: **MODULE path prefix collisions** — `sdd.graph` and `sdd.graph.extractors` both match prefix of `src/sdd/graph/extractors/module_edges.py`. Must assign to most specific module. Mitigation: sort MODULE nodes by dotted path length descending, pick first match.

- R-5: **atomic_write for current_session.json** — without atomic write, concurrent `sdd record-session` calls could corrupt the file. Mitigation: use `atomic_write` from `infra/audit.py` as specified in BC-55-P8.

- R-6: **NavigationPolicy backward compat** — adding `rag_policy: RAGPolicy = field(default_factory=RAGPolicy)` to a frozen dataclass may fail if callers use positional args. Mitigation: verify all call sites use keyword args or update them.
