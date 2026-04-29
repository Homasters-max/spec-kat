# ValidationReport T-5019

**Phase:** 50  
**Task:** T-5019  
**Result:** PASS  
**Date:** 2026-04-29

---

## Spec Section Covered

Spec_v50 §Graph Subsystem — GraphCache, GraphService, phase-isolation contracts.

---

## Invariants Checked

| Invariant | Description | Result |
|---|---|---|
| I-GRAPH-CACHE-1 | Cache key includes GRAPH_SCHEMA_VERSION; eviction on mismatch | PASS |
| I-GRAPH-CACHE-2 | git_tree_hash MUST NOT appear in fingerprint | PASS |
| I-GRAPH-FINGERPRINT-1 | Fingerprint uses EXTRACTOR_VERSION values, sorted | PASS |
| I-GRAPH-LINEAGE-1 | graph.source_snapshot_hash == index.snapshot_hash | PASS |
| I-GRAPH-META-DEBUG-1 | project_node logs WARNING when dropping unknown meta keys | PASS |
| I-PHASE-ISOLATION-1 | No imports from sdd.context_kernel/sdd.policy/sdd.graph_navigation in sdd/graph/* | PASS |

---

## Acceptance Criteria

| Criterion | Result |
|---|---|
| test_graph_cache_key_includes_schema_version | PASS |
| test_deterministic_graph_has_source_snapshot_hash | PASS |
| test_project_node_debug_logs_dropped_keys | PASS |
| test_import_direction_phase50 (grep-test) | PASS |

---

## Test Results

- **test_cache.py:** 6 tests PASS (store/get, eviction, miss, invalidate, schema_version header, debug WARNING)
- **test_service.py:** 7 tests PASS (fingerprint includes schema, lineage, git_tree_hash excluded, extractor versions, cache hit, force_rebuild, import isolation)
- **Full suite:** 1016 passed, 0 failed

---

## Notes

- `ruff` available via `/usr/local/bin/ruff` (symlink to venv); acceptance check passed.
- `test_import_direction_phase50` checks only import-statement lines (not docstrings) to avoid false positives from inline prohibition notes.
