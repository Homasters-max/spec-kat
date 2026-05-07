# TaskSet_v53 — Phase 53: Graph-Based Test Filtering

Spec: specs/Spec_v53_GraphTestFilter.md
Plan: plans/Plan_v53.md

---

T-5301: Add TEST node kind to VALID_KINDS

Status:               DONE
Spec ref:             Spec_v53 §1 — Новый node kind: TEST
Invariants:           I-TEST-NODE-1, I-TEST-NODE-2, I-TEST-NODE-3
spec_refs:            [Spec_v53 §1, I-TEST-NODE-1, I-TEST-NODE-2, I-TEST-NODE-3]
produces_invariants:  [I-TEST-NODE-1]
requires_invariants:  []
Inputs:               src/sdd/spatial/nodes.py
Outputs:              src/sdd/spatial/nodes.py
Acceptance:           `"TEST" in VALID_KINDS` assertion passes; existing FILE/COMMAND/MODULE kinds unaffected
Depends on:           —

---

T-5302: IndexBuilder test-directory scan pass

Status:               DONE
Spec ref:             Spec_v53 §1 — IndexBuilder scan для tests/
Invariants:           I-TEST-NODE-2, I-TEST-NODE-3
spec_refs:            [Spec_v53 §1, I-TEST-NODE-2, I-TEST-NODE-3]
produces_invariants:  [I-TEST-NODE-2, I-TEST-NODE-3]
requires_invariants:  [I-TEST-NODE-1]
Inputs:               src/sdd/graph/builder.py
Outputs:              src/sdd/graph/builder.py
Acceptance:           `tests/unit/**` и `tests/integration/**` индексируются как kind=TEST; `tests/property/` и `tests/fuzz/` получают `tier: slow`; файлы `src/**` не получают kind=TEST (I-TEST-NODE-3)
Depends on:           T-5301

---

T-5303: TestedByEdgeExtractor implementation

Status:               DONE
Spec ref:             Spec_v53 §2 — TestedByEdgeExtractor
Invariants:           I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2, I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1
spec_refs:            [Spec_v53 §2, I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2, I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1]
produces_invariants:  [I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2, I-GRAPH-EXTRACTOR-2, I-GRAPH-FINGERPRINT-1]
requires_invariants:  [I-TEST-NODE-1, I-TEST-NODE-2]
Inputs:               src/sdd/spatial/nodes.py (для проверки kind), src/sdd/graph/ (базовые классы экстракторов)
Outputs:              src/sdd/graph/extractors/tested_by_edges.py
Acceptance:           Mapping `tests/unit/<mod>/test_<name>.py` → рёбра `FILE:src/sdd/<mod>/<name>.py` и `COMMAND:<name>` (underscores→dashes); фантомные рёбра не эмитируются (I-GRAPH-TESTED-BY-2); `EXTRACTOR_VERSION = "tested_by_v1"` присутствует; нет вызовов `open()` (I-GRAPH-EXTRACTOR-2)
Depends on:           T-5301, T-5302

---

T-5304: Register TestedByEdgeExtractor in builder

Status:               DONE
Spec ref:             Spec_v53 §2 — Регистрация экстрактора
Invariants:           I-GRAPH-TESTED-BY-1
spec_refs:            [Spec_v53 §2, I-GRAPH-TESTED-BY-1]
produces_invariants:  []
requires_invariants:  [I-GRAPH-TESTED-BY-1, I-GRAPH-EXTRACTOR-2]
Inputs:               src/sdd/graph/builder.py, src/sdd/graph/extractors/tested_by_edges.py
Outputs:              src/sdd/graph/builder.py
Acceptance:           `IndexBuilder` содержит `TestedByEdgeExtractor` в списке активных экстракторов; `sdd build-graph` без ошибок завершается и `sdd graph-stats --edge-type tested_by` показывает count > 0 на реальном репо
Depends on:           T-5303

---

T-5305: sdd test-filter command handler

Status:               DONE
Spec ref:             Spec_v53 §3 — sdd test-filter
Invariants:           I-TEST-FILTER-1, I-TEST-FILTER-2
spec_refs:            [Spec_v53 §3, I-TEST-FILTER-1, I-TEST-FILTER-2]
produces_invariants:  [I-TEST-FILTER-1, I-TEST-FILTER-2]
requires_invariants:  [I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2]
Inputs:               src/sdd/graph_navigation/cli/ (базовые классы CLI)
Outputs:              src/sdd/graph_navigation/cli/test_filter.py
Acceptance:           BFS по out-edges `tested_by` глубина ≤ 2; tier-маппинг `fast→test_fast / default→test / full→test_full`; запускает `subprocess.run(["pytest", ...paths, "-q", "-m", "not pg"])`; возвращает returncode pytest без изменений (I-TEST-FILTER-1); 0 TEST-nodes → warn stderr + fallback, не ошибка (I-TEST-FILTER-1)
Depends on:           T-5303, T-5304

---

T-5306: Register test-filter in CLI and project_profile

Status:               DONE
Spec ref:             Spec_v53 §3 — Регистрация команды
Invariants:           I-TEST-FILTER-1, I-TASK-MODE-1
spec_refs:            [Spec_v53 §3, I-TEST-FILTER-1, I-TASK-MODE-1]
produces_invariants:  []
requires_invariants:  [I-TEST-FILTER-1]
Inputs:               src/sdd/cli.py, .sdd/config/project_profile.yaml
Outputs:              src/sdd/cli.py, .sdd/config/project_profile.yaml
Acceptance:           `sdd test-filter --help` работает без ошибок; ключ `test_filter` присутствует в `project_profile.yaml`; `k.startswith("test")` → исключается из task-mode build_commands (I-TASK-MODE-1)
Depends on:           T-5305

---

T-5307: Unit tests for TestedByEdgeExtractor

Status:               DONE
Spec ref:             Spec_v53 §6 — Verification (TestedByEdgeExtractor)
Invariants:           I-TEST-NODE-3, I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2, I-DB-TEST-1
spec_refs:            [Spec_v53 §6, I-TEST-NODE-3, I-GRAPH-TESTED-BY-1, I-GRAPH-TESTED-BY-2]
produces_invariants:  [I-TEST-NODE-3, I-GRAPH-TESTED-BY-2]
requires_invariants:  [I-TEST-NODE-1, I-TEST-NODE-2, I-GRAPH-TESTED-BY-1, I-GRAPH-EXTRACTOR-2]
Inputs:               src/sdd/spatial/nodes.py, src/sdd/graph/extractors/tested_by_edges.py, src/sdd/graph/builder.py
Outputs:              tests/unit/graph/test_tested_by_extractor.py
Acceptance:           Все 4 теста PASS: `test_test_node_kind_not_file` (I-TEST-NODE-3), `test_tested_by_edges_filename_convention` (I-GRAPH-TESTED-BY-1), `test_tested_by_no_phantom_edges` (I-GRAPH-TESTED-BY-2), `test_tested_by_no_ast_heuristics` (I-GRAPH-TESTED-BY-1); prod DB не открывается (I-DB-TEST-1)
Depends on:           T-5301, T-5302, T-5303

---

T-5308: Unit tests for sdd test-filter CLI

Status:               DONE
Spec ref:             Spec_v53 §6 — Verification (test-filter)
Invariants:           I-TEST-FILTER-1, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v53 §6, I-TEST-FILTER-1]
produces_invariants:  [I-TEST-FILTER-1]
requires_invariants:  [I-TEST-FILTER-1, I-TEST-FILTER-2]
Inputs:               src/sdd/graph_navigation/cli/test_filter.py, src/sdd/cli.py
Outputs:              tests/unit/graph_navigation/test_test_filter_cli.py
Acceptance:           Оба теста PASS: `test_test_filter_runs_targeted_pytest` (I-TEST-FILTER-1), `test_test_filter_fallback_when_no_edges` (I-TEST-FILTER-1); prod DB не открывается (I-DB-TEST-1)
Depends on:           T-5305, T-5306

---

<!-- Granularity: 8 tasks (TG-2: 10–30 recommended; 8 допустимо для изолированной фичи). -->
<!-- Every task is independently implementable and independently testable (TG-1). -->
