# Plan_v53 — Phase 53: Graph-Based Test Filtering

Status: DRAFT
Spec: specs/Spec_v53_GraphTestFilter.md

---

## Logical Context

```
type: backfill
anchor_phase: 52
rationale: "Phase 53 fills the gap left before Phase 54 was implemented. Spec_v53
            depends on Phase 52 DoD (implements edges, graph navigation CLI) which is
            COMPLETE. Phase 53 was skipped in the activation sequence; now added as
            backfill to deliver TestedByEdgeExtractor and sdd test-filter before Phase 56."
```

---

## Milestones

### M1: TEST Node Kind

```text
Spec:       §1 — Новый node kind: TEST
BCs:        —
Invariants: I-TEST-NODE-1, I-TEST-NODE-2, I-TEST-NODE-3
Depends:    — (foundational; Phase 52 DoD required)
Risks:      IndexBuilder double-scan risk: TEST and FILE paths must be strictly
            partitioned by prefix (tests/** vs src/**). Wrong prefix check →
            same file indexed as both kinds. Guard: I-TEST-NODE-3 unit test first.
```

Deliverables:
- `src/sdd/spatial/nodes.py` — добавить `"TEST"` в множество валидных node kinds
- `src/sdd/graph/builder.py` (IndexBuilder scan pass) — отдельный проход по `tests/unit/`
  и `tests/integration/`; файлы из `tests/property/` и `tests/fuzz/` → `tier: slow` metadata

### M2: TestedByEdgeExtractor

```text
Spec:       §2 — TestedByEdgeExtractor
BCs:        —
Invariants: I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2, I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1
Depends:    M1 (TEST nodes must be in SpatialIndex before extractor can emit edges)
Risks:      Phantom edge risk: extractor must check destination TEST node exists in
            index before emitting. Missing guard → I-GRAPH-TESTED-BY-2 violation.
            EXTRACTOR_VERSION must be set to avoid cache stale on redeploy.
```

Deliverables:
- `src/sdd/graph/extractors/tested_by_edges.py` — `TestedByEdgeExtractor` class
  - Mapping rule: `tests/unit/<mod>/test_<name>.py` →
    `FILE:src/sdd/<mod>/<name>.py` + `COMMAND:<name>` (underscores→dashes)
  - Emits both COMMAND→TEST and FILE→TEST edges
  - `EXTRACTOR_VERSION = "tested_by_v1"`
  - No `open()` calls; content only via `index.read_content(node)` (I-GRAPH-EXTRACTOR-2)
- `src/sdd/graph/builder.py` — зарегистрировать `TestedByEdgeExtractor`

### M3: sdd test-filter CLI

```text
Spec:       §3 — sdd test-filter
BCs:        —
Invariants: I-TEST-FILTER-1, I-TEST-FILTER-2
Depends:    M2 (tested_by edges must be available in graph)
Risks:      Returncode propagation: sdd test-filter must return pytest's returncode
            unchanged. Wrapping in try/except and returning 1 on exception is correct,
            but catching SystemExit from pytest would swallow the real code.
            Use subprocess, not pytest.main().
```

Deliverables:
- `src/sdd/graph_navigation/cli/test_filter.py` — `sdd test-filter` command handler
  - BFS от NODE_ID по out-edges вида `tested_by`, глубина ≤ 2
  - Tier fallback: `fast→test_fast`, `default→test`, `full→test_full`
  - Runs: `pytest <paths...> -q -m "not pg"`, возвращает returncode
  - Zero TEST-nodes → warn stderr + fallback (не ошибка: I-TEST-FILTER-1)
- `src/sdd/cli.py` — зарегистрировать `sdd test-filter`
- `.sdd/config/project_profile.yaml` — добавить:
  ```yaml
  test_filter: sdd test-filter --node {node_id} --tier default
  ```
  (ключ `test_filter` → автоматически исключён из task mode: I-TASK-MODE-1)

### M4: Test Coverage

```text
Spec:       §6 — Verification
BCs:        —
Invariants: I-TEST-NODE-3, I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2, I-TEST-FILTER-1
Depends:    M1, M2, M3 (all production code must exist before tests)
Risks:      Tests open production DB risk: must satisfy I-DB-TEST-1 (no prod DB in tests).
            Use PYTEST_CURRENT_TEST guard (I-DB-TEST-2). Tests must not use glob patterns
            for file access (NORM-SCOPE-003).
```

Deliverables:
- `tests/unit/graph/test_tested_by_extractor.py`
  - `test_test_node_kind_not_file` — I-TEST-NODE-3
  - `test_tested_by_edges_filename_convention` — I-GRAPH-TESTED-BY-1
  - `test_tested_by_no_phantom_edges` — I-GRAPH-TESTED-BY-2
  - `test_tested_by_no_ast_heuristics` — I-GRAPH-TESTED-BY-1
- `tests/unit/graph_navigation/test_test_filter_cli.py`
  - `test_test_filter_runs_targeted_pytest` — I-TEST-FILTER-1
  - `test_test_filter_fallback_when_no_edges` — I-TEST-FILTER-1

---

## Risk Notes

- R-1: **Prefix collision (I-TEST-NODE-3)** — IndexBuilder may accidentally scan a path
  that matches both `tests/` and `src/` prefixes (symlinks, generated files). Mitigation:
  strict `path.startswith("tests/")` check in IndexBuilder; unit test `test_test_node_kind_not_file`
  must run before any extractor test.

- R-2: **Phantom edges (I-GRAPH-TESTED-BY-2)** — extractor emits edge only after verifying
  destination node exists in SpatialIndex. If IndexBuilder scan of `tests/` is incomplete,
  extractor silently drops edges (correct) but sdd test-filter hits fallback (surprising).
  Mitigation: `test_tested_by_no_phantom_edges` must assert edge count = 0 when index
  lacks TEST node, not error.

- R-3: **returncode propagation (I-TEST-FILTER-1)** — `sdd test-filter` must forward
  pytest returncode unchanged. Use `subprocess.run()` not `pytest.main()` to avoid
  SystemExit capture issues.

- R-4: **Phase ordering** — Phase 53 MUST be COMPLETE before Phase 56 PLAN is approved
  (Spec_v53 §5). Phase gate for Phase 56: `sdd graph-stats --edge-type tested_by → count > 0`.
  BC-56-T1 is a phase gate check only (removed from Phase 56 in-scope per Spec_v53 §5).
