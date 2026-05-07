# Plan_v50 — Phase 50: Graph Subsystem Foundation

Status: DRAFT
Spec: specs/Spec_v50_GraphSubsystemFoundation.md

---

## Logical Context

type: none
rationale: "Standard new phase. Phase 50 is the first of three phases (50/51/52) splitting the archived Phase 36 into isolated BCs. Builds `sdd.graph` as a standalone subsystem with no dependency on ContextEngine or CLI."

---

## Milestones

### M1: SpatialIndex Extensions

```text
Spec:       §1 — SpatialIndex расширения (BC-18 → Phase 50)
BCs:        BC-18 (extension)
Invariants: I-SI-READ-1, I-GRAPH-FS-ROOT-1
Depends:    — (Phase 49 COMPLETE)
Risks:      snapshot_hash должен быть детерминирован: sorted() по (path, content) критичен.
            Нарушение порядка → cache miss на каждый rebuild.
            _content_map должен остаться PRIVATE — не добавлять в __init__ public-параметры.
```

Deliverables:
- `SpatialIndex.snapshot_hash: str` — sha256 по всем FILE-узлам (sorted)
- `SpatialIndex._content_map: dict[str, str]` — private
- `SpatialIndex.read_content(node: SpatialNode) -> str` — единственный public accessor
- `IndexBuilder.build()` вычисляет `snapshot_hash` и `_content_map`
- `tests/unit/spatial/test_snapshot_hash.py` — тесты 1-2 из §6

---

### M2: Core Graph Types и Projection

```text
Spec:       §2 — BC-36-1: DeterministicGraph
BCs:        BC-36-1
Invariants: I-GRAPH-TYPES-1, I-GRAPH-META-1, I-GRAPH-META-DEBUG-1,
            I-GRAPH-DET-1, I-GRAPH-DET-2, I-GRAPH-DET-3, I-GRAPH-LINEAGE-1
Depends:    M1 (snapshot_hash нужен для DeterministicGraph.source_snapshot_hash)
Risks:      Edge.__post_init__ должен проверять priority range [0,1] — без этого
            R-INSPECT fix в M3 не защищает от некорректных значений.
            ALLOWED_META_KEYS — frozenset, изменение = bump spec (задокументировать явно).
```

Deliverables:
- `src/sdd/graph/__init__.py` — публичный реэкспорт
- `src/sdd/graph/errors.py` — `GraphInvariantError`
- `src/sdd/graph/types.py` — `Node`, `Edge` (frozen), `DeterministicGraph`, `neighbors()`, `reverse_neighbors()`
- `src/sdd/graph/projection.py` — `ALLOWED_META_KEYS`, `project_node()`
- `tests/unit/graph/test_types.py`, `tests/unit/graph/test_projection.py` — тесты 3, 29-32 из §6

---

### M3: EdgeExtractors + GraphFactsBuilder + EDGE_KIND_PRIORITY

```text
Spec:       §3 — BC-36-2: GraphBuilder
BCs:        BC-36-2
Invariants: I-GRAPH-EXTRACTOR-1, I-GRAPH-EXTRACTOR-2, I-GRAPH-FACTS-ESCAPE-1,
            I-GRAPH-1, I-GRAPH-EMITS-1, I-DDD-1,
            I-GRAPH-PRIORITY-1, I-GRAPH-FINGERPRINT-1,
            I-GRAPH-FS-ISOLATION-1, I-GRAPH-FS-ROOT-1
Depends:    M2 (Node, Edge, project_node нужны для построения графа)
Risks:      R-INSPECT fix: EXTRACTOR_VERSION = ClassVar[str], НЕ inspect.getsource().
            Нарушение → кэш становится недетерминированным при рефакторинге кода экстракторов.
            EdgeExtractor.extract() не должен вызывать open() — нарушение I-GRAPH-EXTRACTOR-2.
            Все 4 экстрактора тестируются изолированно (I-GRAPH-EXTRACTOR-1).
```

Deliverables:
- `src/sdd/graph/extractors/__init__.py` — `EdgeExtractor` Protocol + `_DEFAULT_EXTRACTORS`
- `src/sdd/graph/extractors/ast_edges.py` — `ASTEdgeExtractor` (`EXTRACTOR_VERSION`, `emits`, `imports`, `guards`, `tested_by`)
- `src/sdd/graph/extractors/glossary_edges.py` — `GlossaryEdgeExtractor` (`EXTRACTOR_VERSION`, `means`)
- `src/sdd/graph/extractors/invariant_edges.py` — `InvariantEdgeExtractor` (`EXTRACTOR_VERSION`, `verified_by`, `introduced_in`)
- `src/sdd/graph/extractors/task_deps.py` — `TaskDepsExtractor` (`EXTRACTOR_VERSION`, `depends_on`, `implements`)
- `src/sdd/graph/builder.py` — `EDGE_KIND_PRIORITY`, `GraphFactsBuilder`, private `_DeterministicGraphBuilder`
- `tests/unit/graph/test_extractors.py` — тесты 4-10, 50, 57 из §6
- `tests/unit/graph/test_builder.py` — тесты 11-12 из §6

---

### M4: GraphCache + GraphService (Risk hardening)

```text
Spec:       §4 — BC-36-C: GraphCache + GraphService
BCs:        BC-36-C
Invariants: I-GRAPH-CACHE-1, I-GRAPH-CACHE-2, I-GRAPH-SERVICE-1,
            I-GRAPH-SUBSYSTEM-1, I-GRAPH-FINGERPRINT-1 (service side),
            I-PHASE-ISOLATION-1
Depends:    M3 (GraphFactsBuilder нужен GraphService)
Risks:      R-PICKLE fix: JSON + schema_version header; никакого pickle.
            R-NAMING fix: метод get_or_build(), НЕ get_graph().
            R-GRAPHCACHE-LOCATION fix: .sdd/runtime/graph_cache/ (не .sdd/state/).
            fingerprint = sha256(snapshot_hash + ":" + SCHEMA_VERSION + ":" + extractor_hashes).
            git_tree_hash в fingerprint запрещён (I-GRAPH-CACHE-2).
```

Deliverables:
- `src/sdd/graph/cache.py` — `GraphCache` (`GRAPH_SCHEMA_VERSION = "50.1"`, JSON, eviction on version mismatch)
- `src/sdd/graph/service.py` — `GraphService.get_or_build()`, `_compute_fingerprint()`
- `tests/unit/graph/test_cache.py` — тесты 33 из §6
- `tests/unit/graph/test_service.py` — тесты 50, 51, 58 из §6
- `test_import_direction_phase50` — I-PHASE-ISOLATION-1

---

### M5: Интеграционные тесты + DoD Validation

```text
Spec:       §6 Integration tests, §7 DoD Phase 50
BCs:        все BC фазы
Invariants: все I-GRAPH-* Phase 50
Depends:    M1-M4 (все юнит-тесты должны пройти)
Risks:      Реальный SpatialIndex может вернуть пустые узлы нужных типов — экстракторы
            должны корректно обрабатывать пустой граф (не падать).
            mypy --strict может выявить проблемы с Protocol + ClassVar — проверить заранее.
```

Deliverables:
- Integration test 9 (§6): `GraphFactsBuilder` на реальном `SpatialIndex` проекта
- `mypy --strict` passes на `sdd.graph.*` и изменённом `sdd.spatial.index`
- Все существующие тесты не регрессируют
- DoD checklist (§7) полностью выполнен

---

## Risk Notes

- R-NAMING: `GraphService.get_or_build()` — не `get_graph()`. Фиксируется в M4. Нарушение → API-breaking change при рефакторинге Phase 51/52.
- R-INSPECT: `EXTRACTOR_VERSION: ClassVar[str]` вместо `inspect.getsource()`. Фиксируется в M3. Нарушение → недетерминированный fingerprint; cache invalidation при любом изменении отступов.
- R-PICKLE: JSON с `schema_version` header вместо pickle. Фиксируется в M4. Нарушение → cache files несовместимы между Python-версиями.
- R-GRAPHCACHE-LOCATION: `.sdd/runtime/graph_cache/` как canonical path. Фиксируется в M4. Нарушение → cache файлы вне `.sdd/runtime/` не покрываются `.gitignore`.
- R-ISOLATION: `sdd.graph` не импортирует из `sdd.context_kernel`, `sdd.policy`, `sdd.graph_navigation`. Проверяется `test_import_direction_phase50`. Нарушение → цикличные зависимости в Phase 51.
