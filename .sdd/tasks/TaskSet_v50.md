# TaskSet_v50 — Phase 50: Graph Subsystem Foundation

Spec: specs/Spec_v50_GraphSubsystemFoundation.md
Plan: plans/Plan_v50.md

---

T-5001: SpatialIndex — add snapshot_hash field and _content_map private field

Status:               DONE
Spec ref:             Spec_v50 §1 — SpatialIndex расширения (BC-18 → Phase 50)
Invariants:           I-SI-READ-1, I-GRAPH-FS-ROOT-1
spec_refs:            [Spec_v50 §1, I-SI-READ-1, I-GRAPH-FS-ROOT-1]
produces_invariants:  [I-SI-READ-1]
requires_invariants:  []
Inputs:               src/sdd/spatial/index.py
Outputs:              src/sdd/spatial/index.py
Acceptance:           SpatialIndex dataclass has snapshot_hash: str and _content_map: dict[str, str]; _content_map has no public constructor parameter (private)
Depends on:           —

---

T-5002: IndexBuilder.build() — compute snapshot_hash and _content_map

Status:               DONE
Spec ref:             Spec_v50 §1 — IndexBuilder.build() вычисляет snapshot_hash
Invariants:           I-SI-READ-1, I-GRAPH-CACHE-2
spec_refs:            [Spec_v50 §1, I-SI-READ-1, I-GRAPH-CACHE-2]
produces_invariants:  [I-SI-READ-1]
requires_invariants:  [I-SI-READ-1]
Inputs:               src/sdd/spatial/index.py
Outputs:              src/sdd/spatial/index.py
Acceptance:           IndexBuilder.build() computes snapshot_hash as sha256(sorted FILE-nodes by path+content); _content_map populated for FILE nodes only
Depends on:           T-5001

---

T-5003: SpatialIndex — add read_content() public method

Status:               DONE
Spec ref:             Spec_v50 §1 — read_content(node: SpatialNode) -> str
Invariants:           I-SI-READ-1, I-GRAPH-FS-ROOT-1, I-GRAPH-FS-ISOLATION-1
spec_refs:            [Spec_v50 §1, I-SI-READ-1, I-GRAPH-FS-ROOT-1]
produces_invariants:  [I-SI-READ-1, I-GRAPH-FS-ROOT-1]
requires_invariants:  [I-SI-READ-1]
Inputs:               src/sdd/spatial/index.py
Outputs:              src/sdd/spatial/index.py
Acceptance:           read_content(node) returns content for FILE nodes, "" for others; raises KeyError for missing FILE node; no direct _content_map access outside SpatialIndex
Depends on:           T-5002

---

T-5004: Unit tests — SpatialIndex extensions (snapshot_hash + read_content)

Status:               DONE
Spec ref:             Spec_v50 §6 — тесты 1-2: test_snapshot_hash_content_based, test_read_content_is_only_public_accessor
Invariants:           I-SI-READ-1, I-GRAPH-FS-ROOT-1
spec_refs:            [Spec_v50 §6, I-SI-READ-1]
produces_invariants:  []
requires_invariants:  [I-SI-READ-1]
Inputs:               src/sdd/spatial/index.py
Outputs:              tests/unit/spatial/test_snapshot_hash.py
Acceptance:           test_snapshot_hash_content_based PASS; test_read_content_is_only_public_accessor PASS
Depends on:           T-5003

---

T-5005: src/sdd/graph/errors.py — GraphInvariantError

Status:               DONE
Spec ref:             Spec_v50 §2 — BC-36-1: DeterministicGraph (error type)
Invariants:           I-GRAPH-TYPES-1
spec_refs:            [Spec_v50 §2, I-GRAPH-TYPES-1]
produces_invariants:  [I-GRAPH-TYPES-1]
requires_invariants:  []
Inputs:               —
Outputs:              src/sdd/graph/errors.py
Acceptance:           GraphInvariantError is importable from sdd.graph.errors; is subclass of Exception
Depends on:           —

---

T-5006: src/sdd/graph/types.py — Node, Edge (frozen), DeterministicGraph

Status:               DONE
Spec ref:             Spec_v50 §2 — BC-36-1: Node, Edge, DeterministicGraph types
Invariants:           I-GRAPH-TYPES-1, I-GRAPH-DET-1, I-GRAPH-DET-2, I-GRAPH-DET-3, I-GRAPH-LINEAGE-1
spec_refs:            [Spec_v50 §2, I-GRAPH-TYPES-1, I-GRAPH-DET-1, I-GRAPH-DET-2, I-GRAPH-DET-3, I-GRAPH-LINEAGE-1]
produces_invariants:  [I-GRAPH-TYPES-1, I-GRAPH-DET-2, I-GRAPH-LINEAGE-1]
requires_invariants:  [I-GRAPH-TYPES-1]
Inputs:               src/sdd/graph/errors.py
Outputs:              src/sdd/graph/types.py
Acceptance:           Node and Edge are frozen dataclasses; Edge.__post_init__ raises ValueError for priority outside [0.0,1.0]; DeterministicGraph has source_snapshot_hash field and neighbors()/reverse_neighbors() methods; no inheritance from SpatialNode/SpatialEdge
Depends on:           T-5005

---

T-5007: src/sdd/graph/projection.py — ALLOWED_META_KEYS + project_node()

Status:               DONE
Spec ref:             Spec_v50 §2 — project_node(), ALLOWED_META_KEYS
Invariants:           I-GRAPH-META-1, I-GRAPH-META-DEBUG-1, I-GRAPH-TYPES-1
spec_refs:            [Spec_v50 §2, I-GRAPH-META-1, I-GRAPH-META-DEBUG-1]
produces_invariants:  [I-GRAPH-META-1, I-GRAPH-META-DEBUG-1]
requires_invariants:  [I-GRAPH-TYPES-1]
Inputs:               src/sdd/graph/types.py, src/sdd/spatial/index.py
Outputs:              src/sdd/graph/projection.py
Acceptance:           ALLOWED_META_KEYS is frozenset; project_node() drops unknown keys silently; in debug mode logs dropped keys; indexing fields (signature, git_hash, indexed_at) never appear in Node.meta
Depends on:           T-5006

---

T-5008: src/sdd/graph/__init__.py — public re-export

Status:               DONE
Spec ref:             Spec_v50 §5 — Новые файлы: src/sdd/graph/__init__.py
Invariants:           I-GRAPH-SUBSYSTEM-1, I-PHASE-ISOLATION-1
spec_refs:            [Spec_v50 §5, I-GRAPH-SUBSYSTEM-1, I-PHASE-ISOLATION-1]
produces_invariants:  [I-GRAPH-SUBSYSTEM-1]
requires_invariants:  [I-GRAPH-TYPES-1, I-GRAPH-META-1]
Inputs:               src/sdd/graph/errors.py, src/sdd/graph/types.py, src/sdd/graph/projection.py
Outputs:              src/sdd/graph/__init__.py
Acceptance:           from sdd.graph import DeterministicGraph, Node, Edge, GraphService, GraphInvariantError, EDGE_KIND_PRIORITY succeeds; no import from sdd.context_kernel/sdd.policy/sdd.graph_navigation
Depends on:           T-5007

---

T-5009: Unit tests — types + projection (tests 3, 29-32 from §6)

Status:               DONE
Spec ref:             Spec_v50 §6 — тесты 3, 29-32: project_node_excludes_indexing_fields, project_node_allowlist, project_node_blocklist_removed, edge_priority_out_of_range, edge_priority_from_canonical_table
Invariants:           I-GRAPH-TYPES-1, I-GRAPH-META-1, I-GRAPH-DET-2
spec_refs:            [Spec_v50 §6, I-GRAPH-TYPES-1, I-GRAPH-META-1]
produces_invariants:  []
requires_invariants:  [I-GRAPH-TYPES-1, I-GRAPH-META-1]
Inputs:               src/sdd/graph/types.py, src/sdd/graph/projection.py
Outputs:              tests/unit/graph/test_types.py, tests/unit/graph/test_projection.py
Acceptance:           test_project_node_excludes_indexing_fields PASS; test_project_node_allowlist PASS; test_project_node_blocklist_removed PASS; test_edge_priority_out_of_range PASS; test_edge_priority_from_canonical_table PASS (5 tests total)
Depends on:           T-5008

---

T-5010: src/sdd/graph/extractors/__init__.py — EdgeExtractor Protocol + _DEFAULT_EXTRACTORS

Status:               DONE
Spec ref:             Spec_v50 §3 — EdgeExtractor Protocol (с R-INSPECT fix)
Invariants:           I-GRAPH-FINGERPRINT-1, I-GRAPH-EXTRACTOR-1, I-GRAPH-EXTRACTOR-2
spec_refs:            [Spec_v50 §3, I-GRAPH-FINGERPRINT-1, I-GRAPH-EXTRACTOR-1]
produces_invariants:  [I-GRAPH-FINGERPRINT-1]
requires_invariants:  [I-GRAPH-TYPES-1]
Inputs:               src/sdd/graph/types.py, src/sdd/spatial/index.py
Outputs:              src/sdd/graph/extractors/__init__.py
Acceptance:           EdgeExtractor is typing.Protocol with EXTRACTOR_VERSION: ClassVar[str] and extract(index: SpatialIndex) -> list[Edge]; _DEFAULT_EXTRACTORS is list[EdgeExtractor] (initially empty, filled after T-5011..T-5013)
Depends on:           T-5008

---

T-5011: ASTEdgeExtractor — emits, imports, guards, tested_by

Status:               DONE
Spec ref:             Spec_v50 §3 — ASTEdgeExtractor (EXTRACTOR_VERSION req.)
Invariants:           I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1, I-GRAPH-EMITS-1, I-GRAPH-PRIORITY-1, I-GRAPH-1
spec_refs:            [Spec_v50 §3, I-GRAPH-EXTRACTOR-2, I-GRAPH-EMITS-1, I-GRAPH-PRIORITY-1]
produces_invariants:  [I-GRAPH-EXTRACTOR-2, I-GRAPH-EMITS-1]
requires_invariants:  [I-GRAPH-FINGERPRINT-1]
Inputs:               src/sdd/graph/extractors/__init__.py, src/sdd/graph/types.py, src/sdd/graph/builder.py (EDGE_KIND_PRIORITY — forward dep, must be defined first in T-5014)
Outputs:              src/sdd/graph/extractors/ast_edges.py
Acceptance:           ASTEdgeExtractor.EXTRACTOR_VERSION defined as ClassVar[str]; extract() does not call open(); all returned edges use EDGE_KIND_PRIORITY[kind]; emits-edges satisfy I-GRAPH-EMITS-1 conditions
Depends on:           T-5010

---

T-5012: GlossaryEdgeExtractor + InvariantEdgeExtractor

Status:               DONE
Spec ref:             Spec_v50 §3 — GlossaryEdgeExtractor (means), InvariantEdgeExtractor (verified_by, introduced_in)
Invariants:           I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1, I-GRAPH-PRIORITY-1, I-DDD-1
spec_refs:            [Spec_v50 §3, I-GRAPH-EXTRACTOR-2, I-GRAPH-PRIORITY-1, I-DDD-1]
produces_invariants:  [I-GRAPH-EXTRACTOR-2, I-DDD-1]
requires_invariants:  [I-GRAPH-FINGERPRINT-1]
Inputs:               src/sdd/graph/extractors/__init__.py, src/sdd/graph/types.py, src/sdd/graph/builder.py
Outputs:              src/sdd/graph/extractors/glossary_edges.py, src/sdd/graph/extractors/invariant_edges.py
Acceptance:           Both extractors have EXTRACTOR_VERSION: ClassVar[str]; extract() does not call open(); edges use EDGE_KIND_PRIORITY for means/verified_by/introduced_in; GlossaryEdgeExtractor validates TERM references (I-DDD-1)
Depends on:           T-5010

---

T-5013: TaskDepsExtractor — depends_on, implements

Status:               DONE
Spec ref:             Spec_v50 §3 — TaskDepsExtractor (depends_on, implements)
Invariants:           I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1, I-GRAPH-PRIORITY-1
spec_refs:            [Spec_v50 §3, I-GRAPH-EXTRACTOR-2, I-GRAPH-PRIORITY-1]
produces_invariants:  [I-GRAPH-EXTRACTOR-2]
requires_invariants:  [I-GRAPH-FINGERPRINT-1]
Inputs:               src/sdd/graph/extractors/__init__.py, src/sdd/graph/types.py, src/sdd/graph/builder.py
Outputs:              src/sdd/graph/extractors/task_deps.py
Acceptance:           TaskDepsExtractor.EXTRACTOR_VERSION defined; extract() does not call open(); edges use EDGE_KIND_PRIORITY for depends_on/implements
Depends on:           T-5010

---

T-5014: src/sdd/graph/builder.py — EDGE_KIND_PRIORITY + GraphFactsBuilder + _DeterministicGraphBuilder

Status:               DONE
Spec ref:             Spec_v50 §3 — GraphFactsBuilder, EDGE_KIND_PRIORITY, private _DeterministicGraphBuilder
Invariants:           I-GRAPH-FACTS-ESCAPE-1, I-GRAPH-PRIORITY-1, I-GRAPH-DET-1, I-GRAPH-DET-3, I-GRAPH-FS-ISOLATION-1, I-GRAPH-1, I-GRAPH-LINEAGE-1
spec_refs:            [Spec_v50 §3, I-GRAPH-FACTS-ESCAPE-1, I-GRAPH-PRIORITY-1, I-GRAPH-DET-1, I-GRAPH-DET-3]
produces_invariants:  [I-GRAPH-FACTS-ESCAPE-1, I-GRAPH-PRIORITY-1, I-GRAPH-DET-1, I-GRAPH-DET-3, I-GRAPH-FS-ISOLATION-1]
requires_invariants:  [I-GRAPH-TYPES-1, I-GRAPH-META-1, I-GRAPH-EXTRACTOR-2]
Inputs:               src/sdd/graph/types.py, src/sdd/graph/projection.py, src/sdd/graph/errors.py, src/sdd/graph/extractors/__init__.py, src/sdd/spatial/index.py
Outputs:              src/sdd/graph/builder.py
Acceptance:           EDGE_KIND_PRIORITY dict has all 9 canonical edge kinds; GraphFactsBuilder.build() verifies I-GRAPH-1/I-GRAPH-EMITS-1/I-DDD-1; raises GraphInvariantError on violation; _DeterministicGraphBuilder is private (not exported in __init__.py); source_snapshot_hash set from index.snapshot_hash; builder.py has zero direct open() calls
Depends on:           T-5011, T-5012, T-5013

---

T-5015: Update extractors/__init__.py — populate _DEFAULT_EXTRACTORS

Status:               DONE
Spec ref:             Spec_v50 §3 — _DEFAULT_EXTRACTORS list
Invariants:           I-GRAPH-EXTRACTOR-1, I-GRAPH-FINGERPRINT-1
spec_refs:            [Spec_v50 §3, I-GRAPH-EXTRACTOR-1]
produces_invariants:  [I-GRAPH-EXTRACTOR-1]
requires_invariants:  [I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1]
Inputs:               src/sdd/graph/extractors/ast_edges.py, src/sdd/graph/extractors/glossary_edges.py, src/sdd/graph/extractors/invariant_edges.py, src/sdd/graph/extractors/task_deps.py
Outputs:              src/sdd/graph/extractors/__init__.py
Acceptance:           _DEFAULT_EXTRACTORS = [ASTEdgeExtractor(), GlossaryEdgeExtractor(), InvariantEdgeExtractor(), TaskDepsExtractor()]; list has exactly 4 items
Depends on:           T-5014

---

T-5016: Unit tests — extractors + builder (tests 4-12, 50, 57 from §6)

Status:               DONE
Spec ref:             Spec_v50 §6 — тесты 4-12: ast_edge_extractor_emits, ast_edge_extractor_imports, glossary_extractor_means, invariant_extractor_verified_by, task_deps_extractor_depends_on, extractor_no_open_call, graph_facts_builder_custom_extractors, graph_cache_hit_miss, graph_builder_deterministic; test 50: graph_fingerprint_changes_on_extractor_code_change; test 57: fs_root_only_spatial_index
Invariants:           I-GRAPH-EXTRACTOR-1, I-GRAPH-EXTRACTOR-2, I-GRAPH-DET-1, I-GRAPH-FACTS-ESCAPE-1, I-GRAPH-FS-ROOT-1
spec_refs:            [Spec_v50 §6, I-GRAPH-EXTRACTOR-1, I-GRAPH-EXTRACTOR-2, I-GRAPH-DET-1, I-GRAPH-FS-ROOT-1]
produces_invariants:  []
requires_invariants:  [I-GRAPH-EXTRACTOR-1, I-GRAPH-EXTRACTOR-2, I-GRAPH-DET-1, I-GRAPH-FACTS-ESCAPE-1]
Inputs:               src/sdd/graph/extractors/, src/sdd/graph/builder.py, src/sdd/spatial/index.py
Outputs:              tests/unit/graph/test_extractors.py, tests/unit/graph/test_builder.py
Acceptance:           test_ast_edge_extractor_emits PASS; test_ast_edge_extractor_imports PASS; test_glossary_edge_extractor_means PASS; test_invariant_edge_extractor_verified_by PASS; test_task_deps_extractor_depends_on PASS; test_extractor_no_open_call PASS; test_graph_facts_builder_custom_extractors PASS; test_graph_builder_deterministic PASS; test_graph_fingerprint_changes_on_extractor_code_change PASS; test_fs_root_only_spatial_index PASS (grep-test)
Depends on:           T-5015

---

T-5017: src/sdd/graph/cache.py — GraphCache (JSON, schema_version, eviction)

Status:               DONE
Spec ref:             Spec_v50 §4 — GraphCache pure memoization (R-PICKLE fix)
Invariants:           I-GRAPH-CACHE-1, I-GRAPH-CACHE-2, I-GRAPH-SERVICE-1
spec_refs:            [Spec_v50 §4, I-GRAPH-CACHE-1, I-GRAPH-CACHE-2]
produces_invariants:  [I-GRAPH-CACHE-1, I-GRAPH-CACHE-2]
requires_invariants:  [I-GRAPH-TYPES-1, I-GRAPH-LINEAGE-1]
Inputs:               src/sdd/graph/types.py
Outputs:              src/sdd/graph/cache.py
Acceptance:           GRAPH_SCHEMA_VERSION = "50.1"; cache stores JSON with {"schema_version": "50.1", "graph": {...}}; get() returns None on schema_version mismatch (eviction); zero pickle usage; cache path defaults to .sdd/runtime/graph_cache/; GraphCache has no knowledge of SpatialIndex or EdgeExtractor (R-PICKLE fix)
Depends on:           T-5008

---

T-5018: src/sdd/graph/service.py — GraphService.get_or_build() + _compute_fingerprint()

Status:               DONE
Spec ref:             Spec_v50 §4 — GraphService build+cache boundary (R-NAMING fix, R-INSPECT fix)
Invariants:           I-GRAPH-SERVICE-1, I-GRAPH-SUBSYSTEM-1, I-GRAPH-CACHE-2, I-GRAPH-FINGERPRINT-1, I-PHASE-ISOLATION-1
spec_refs:            [Spec_v50 §4, I-GRAPH-SERVICE-1, I-GRAPH-SUBSYSTEM-1, I-GRAPH-CACHE-2, I-GRAPH-FINGERPRINT-1]
produces_invariants:  [I-GRAPH-SERVICE-1, I-GRAPH-SUBSYSTEM-1, I-GRAPH-FINGERPRINT-1]
requires_invariants:  [I-GRAPH-CACHE-1, I-GRAPH-CACHE-2, I-GRAPH-FACTS-ESCAPE-1, I-GRAPH-LINEAGE-1]
Inputs:               src/sdd/graph/cache.py, src/sdd/graph/builder.py, src/sdd/graph/extractors/__init__.py, src/sdd/spatial/index.py
Outputs:              src/sdd/graph/service.py
Acceptance:           method is named get_or_build() (R-NAMING fix); fingerprint = sha256(snapshot_hash+":"+GRAPH_SCHEMA_VERSION+":"+extractor_hashes); git_tree_hash not in fingerprint (I-GRAPH-CACHE-2); inspect.getsource() absent (R-INSPECT fix); force_rebuild=True bypasses cache; sdd.graph does not import from sdd.context_kernel/sdd.policy/sdd.graph_navigation (I-PHASE-ISOLATION-1)
Depends on:           T-5017

---

T-5019: Unit tests — cache + service + import direction (tests 33, 50, 51, 58 + I-PHASE-ISOLATION-1)

Status:               DONE
Spec ref:             Spec_v50 §6 — тесты 33, 50, 51, 58: graph_cache_key_includes_schema_version, graph_fingerprint_changes_on_extractor_code_change, test_deterministic_graph_has_source_snapshot_hash, test_project_node_debug_logs_dropped_keys; test_import_direction_phase50
Invariants:           I-GRAPH-CACHE-1, I-GRAPH-CACHE-2, I-GRAPH-FINGERPRINT-1, I-GRAPH-LINEAGE-1, I-GRAPH-META-DEBUG-1, I-PHASE-ISOLATION-1
spec_refs:            [Spec_v50 §6, I-GRAPH-CACHE-1, I-GRAPH-CACHE-2, I-GRAPH-FINGERPRINT-1, I-GRAPH-LINEAGE-1, I-PHASE-ISOLATION-1]
produces_invariants:  []
requires_invariants:  [I-GRAPH-CACHE-1, I-GRAPH-CACHE-2, I-GRAPH-SERVICE-1, I-GRAPH-SUBSYSTEM-1]
Inputs:               src/sdd/graph/cache.py, src/sdd/graph/service.py, src/sdd/graph/
Outputs:              tests/unit/graph/test_cache.py, tests/unit/graph/test_service.py
Acceptance:           test_graph_cache_key_includes_schema_version PASS; test_deterministic_graph_has_source_snapshot_hash PASS; test_project_node_debug_logs_dropped_keys PASS; test_import_direction_phase50 PASS (grep-test: no import from sdd.context_kernel/sdd.policy/sdd.graph_navigation in sdd/graph/*)
Depends on:           T-5018

---

<!-- Granularity: 19 tasks — within TG-2 range (10-30). All tasks independently implementable and testable (TG-1). -->
<!-- Every task references exactly one Spec_v50 section + ≥1 invariant (SDD-2). All M1..M5 milestones covered (SDD-3). -->
