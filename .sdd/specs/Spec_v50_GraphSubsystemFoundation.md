# Spec_v50 — Phase 50: Graph Subsystem Foundation (MODEL SHIFT)

**Status:** Draft
**Supersedes:** Spec_v36_2 (Phase 36 ARCHIVED — superseded by Phase 50+51+52)
**Baseline:** Spec_v36_2_GraphNavigation.md §BC-36-1, §BC-36-2, §BC-36-C
**Depends on:** Phase 49 COMPLETE
**Session:** DRAFT_SPEC 2026-04-29 — разбивка Phase 36 на 50/51/52

**Цель:** Построить `sdd.graph` как изолированный BC. Никакого CLI, никакого ContextEngine.
Единственный публичный результат = `GraphService.get_or_build()` → `DeterministicGraph`.

**Risk fixes в этой фазе:** R-NAMING, R-INSPECT, R-PICKLE, R-GRAPHCACHE-LOCATION

---

## 0. Архитектурная модель (Phase 50 scope)

```text
Filesystem
  ↓ (единственный reader — I-GRAPH-FS-ROOT-1)
IndexBuilder → SpatialIndex (snapshot_hash, read_content())    ← I-SI-READ-1

  ↓
GraphService.get_or_build(index) → DeterministicGraph
  ├── GraphCache (pure KV, JSON, schema_version header)        ← R-PICKLE fix
  └── GraphFactsBuilder
        ├── ASTEdgeExtractor        (EXTRACTOR_VERSION req.)   ← R-INSPECT fix
        ├── GlossaryEdgeExtractor   (EXTRACTOR_VERSION req.)
        ├── InvariantEdgeExtractor  (EXTRACTOR_VERSION req.)
        └── TaskDepsExtractor       (EXTRACTOR_VERSION req.)
        └── [private] DeterministicGraphBuilder

  fingerprint = sha256(snapshot_hash + SCHEMA_VERSION + extractor_hashes)
  cache path  = .sdd/runtime/graph_cache/                      ← R-GRAPHCACHE-LOCATION fix
```

**Phase Isolation Rule (I-PHASE-ISOLATION-1):**
`sdd.graph` НЕ импортирует из `sdd.context_kernel`, `sdd.policy`, `sdd.graph_navigation`.
Проверяется `test_import_direction_phase50`.

**Стабильный интерфейс для Phase 51:**
```python
from sdd.graph import DeterministicGraph, Node, Edge, GraphService, GraphInvariantError, EDGE_KIND_PRIORITY
SpatialIndex.snapshot_hash: str
SpatialIndex.read_content(node: SpatialNode) -> str
```

---

## 1. SpatialIndex — расширения (BC-18 → Phase 50)

`SpatialIndex` (Phase 18) получает поле `snapshot_hash` и метод `read_content()`.

```python
@dataclass(frozen=True)
class SpatialIndex:
    nodes:         dict[str, SpatialNode]
    _content_map:  dict[str, str]          # PRIVATE: ключ = node_id файла; доступ только через read_content()
    built_at:      str
    git_tree_hash: str | None
    snapshot_hash: str          # sha256 по всем (path, content) отсортированным FILE-узлам
    version:       int = 1
    meta:          dict = field(default_factory=dict)

    def read_content(self, node: SpatialNode) -> str:
        """Единственный публичный метод чтения контента узла.
        FILE → содержимое файла; остальные → "" (контент в node.summary/meta).
        Raises KeyError если FILE-узел отсутствует в content_map.
        """
        return self._content_map.get(node.node_id, "")
```

`snapshot_hash` считается в `IndexBuilder.build()`:
```python
hasher = sha256()
for path, content in sorted((n.path, content) for n, content in file_items):
    hasher.update(path.encode())
    hasher.update(content.encode())
snapshot_hash = hasher.hexdigest()
```

**I-SI-READ-1**: `SpatialIndex.read_content(node)` MUST be the only public access point for node content. Direct access to `_content_map` is forbidden outside `SpatialIndex`. `DocProvider`, `GraphFactsBuilder` и все прочие потребители MUST use `read_content()`.

---

## 2. BC-36-1: DeterministicGraph

### Назначение

Детерминированное in-memory представление структурного графа системы, полностью восстанавливаемое из `SpatialIndex`.

`DeterministicGraph.Node` — projection SpatialNode для graph layer. Не дублирует indexing-поля (`signature`, `git_hash`, `indexed_at`).

### Типы

```python
@dataclass(frozen=True)
class Node:
    node_id: str      # e.g. "COMMAND:complete", "EVENT:TaskImplementedEvent"
    kind: str         # COMMAND|EVENT|TASK|TERM|INVARIANT|FILE|...
    label: str
    summary: str
    meta: dict        # {"path": "...", "...": ...}

@dataclass(frozen=True)
class Edge:
    edge_id: str      # sha256(f"{src}:{kind}:{dst}")[:16]
    src: str          # node_id
    dst: str          # node_id
    kind: str         # emits|guards|implements|depends_on|means|imports|...
    priority: float   # 0.0..1.0; MUST equal EDGE_KIND_PRIORITY[kind] (I-GRAPH-PRIORITY-1)
    source: str       # ast_emits|taskset_depends_on|glossary|...
    meta: dict

    def __post_init__(self):
        if not (0.0 <= self.priority <= 1.0):
            raise ValueError(f"Edge.priority must be in [0.0, 1.0], got {self.priority!r}")
        if not self.edge_id:
            raise ValueError("Edge.edge_id must be non-empty")

@dataclass
class DeterministicGraph:
    nodes: dict[str, Node]
    edges_out: dict[str, list[Edge]]
    edges_in: dict[str, list[Edge]]
    source_snapshot_hash: str   # snapshot_hash SpatialIndex из которого построен граф (I-GRAPH-LINEAGE-1)

    def neighbors(self, node_id: str, kinds: set[str] | None = None) -> list[Edge]: ...
    def reverse_neighbors(self, node_id: str, kinds: set[str] | None = None) -> list[Edge]: ...
```

### project_node

```python
ALLOWED_META_KEYS: frozenset[str] = frozenset({
    "path", "language", "line_start", "line_end", "links", "phase",
    "verified_by", "introduced_in", "depends_on", "implements",
})

def project_node(n: SpatialNode) -> Node:
    """Проекция SpatialNode → Node. Использует ALLOWED_META_KEYS allowlist (I-GRAPH-META-1).
    Не копирует indexing-поля и любые неизвестные ключи. Добавление ключа = bump spec.
    """
    return Node(
        node_id=n.node_id,
        kind=n.kind,
        label=n.label,
        summary=n.summary,
        meta={"path": n.path,
              **{k: v for k, v in n.meta.items() if k in ALLOWED_META_KEYS}},
    )
```

### Инварианты

- **I-GRAPH-META-1**: `project_node()` MUST use `ALLOWED_META_KEYS` allowlist. Unknown keys from `SpatialNode.meta` MUST be silently dropped. `ALLOWED_META_KEYS` is a `frozenset` — additions require spec bump.
- **I-GRAPH-TYPES-1**: `DeterministicGraph.Node` и `DeterministicGraph.Edge` MUST be independent types from `SpatialNode`/`SpatialEdge`. No inheritance. No reuse of indexing fields (`signature`, `git_hash`, `indexed_at`).
- **I-GRAPH-DET-1**: Для одного и того же `SpatialIndex` результат `DeterministicGraph` должен быть идентичен (byte-wise для множества Node/Edge).
- **I-GRAPH-DET-2**: Каждый `Edge.edge_id = sha256(src+":"+kind+":"+dst)[:16]`.
- **I-GRAPH-DET-3**: `edges_out[src]` и `edges_in[dst]` взаимно согласованы.
- **I-GRAPH-LINEAGE-1**: `DeterministicGraph.source_snapshot_hash` MUST be set from `SpatialIndex.snapshot_hash` at build time. Cache MUST NOT reuse a graph with mismatched `source_snapshot_hash`.
- **I-GRAPH-META-DEBUG-1**: В debug-режиме `project_node()` MUST log dropped keys. В production — WARNING если непустые.

---

## 3. BC-36-2: GraphBuilder

### Назначение

Построение `DeterministicGraph` из `SpatialIndex` с проверкой инвариантов.

### Pipeline

```text
SpatialIndex
 → GraphFactsBuilder (оркестратор EdgeExtractor-ов; DeterministicGraphBuilder — private impl)
     ├── ASTEdgeExtractor       (imports, emits, guards, tested_by)
     ├── GlossaryEdgeExtractor  (means)
     ├── InvariantEdgeExtractor (verified_by, introduced_in)
     └── TaskDepsExtractor      (depends_on, implements)
 → DeterministicGraph           ← единственный публичный результат (I-GRAPH-FACTS-ESCAPE-1)
```

### Каноническая таблица приоритетов рёбер

```python
EDGE_KIND_PRIORITY: dict[str, float] = {
    "emits":         0.95,
    "guards":        0.90,
    "implements":    0.85,
    "tested_by":     0.80,
    "verified_by":   0.75,
    "depends_on":    0.70,
    "introduced_in": 0.65,
    "imports":       0.60,
    "means":         0.50,
}
```

**I-GRAPH-PRIORITY-1**: Each `EdgeExtractor` MUST assign `Edge.priority = EDGE_KIND_PRIORITY[edge.kind]`. Self-assigned priority values are forbidden. Unknown edge kinds MUST raise `GraphInvariantError`.

### EdgeExtractor Protocol (с R-INSPECT fix)

```python
from typing import Protocol, ClassVar

class EdgeExtractor(Protocol):
    EXTRACTOR_VERSION: ClassVar[str]  # semver; ОБЯЗАТЕЛЕН (I-GRAPH-FINGERPRINT-1)
                                      # inspect.getsource() ЗАПРЕЩЁН
    def extract(self, index: SpatialIndex) -> list[Edge]:
        """Чистая функция: SpatialIndex → list[Edge]. Нет side effects. Нет open()."""
        ...
```

Каждый конкретный экстрактор MUST определить `EXTRACTOR_VERSION: ClassVar[str] = "X.Y.Z"`.

### GraphFactsBuilder

```python
_DEFAULT_EXTRACTORS: list[EdgeExtractor] = [
    ASTEdgeExtractor(),
    GlossaryEdgeExtractor(),
    InvariantEdgeExtractor(),
    TaskDepsExtractor(),
]

class GraphFactsBuilder:
    def __init__(self, extractors: list[EdgeExtractor] | None = None):
        self._extractors = extractors if extractors is not None else _DEFAULT_EXTRACTORS

    def build(self, index: SpatialIndex) -> DeterministicGraph:
        """
        1. nodes = [project_node(n) for n in index.nodes.values()]
        2. edges = flatten([e.extract(index) for e in self._extractors])
        3. Проверяет I-GRAPH-1, I-GRAPH-EMITS-1, I-DDD-1.
        4. Строит edges_out / edges_in индексы; устанавливает source_snapshot_hash.
        5. При violation → GraphInvariantError.
        """

# DeterministicGraphBuilder — private. Вызывается только из GraphFactsBuilder.build().
```

### Инварианты

- **I-GRAPH-EXTRACTOR-1**: Каждый `EdgeExtractor` MUST be tested in isolation on a minimal `SpatialIndex` fixture.
- **I-GRAPH-EXTRACTOR-2**: Каждый `EdgeExtractor.extract()` MUST NOT call `open()` directly. Весь контент через `index.read_content(node)`.
- **I-GRAPH-FACTS-ESCAPE-1**: Intermediate `GraphFacts` MUST NOT escape `GraphFactsBuilder.build()`. Tests MUST NOT instantiate `DeterministicGraphBuilder` directly.
- **I-GRAPH-1**: Каждое ребро выводится из статического AST или явного конфига.
- **I-GRAPH-EMITS-1**: `emits`-ребро только если выполнены все 4 условия.
- **I-DDD-1**: Все TERM-ссылки валидны относительно `typed_registry()`.
- **I-GRAPH-FS-ISOLATION-1**: GraphBuilder никогда не вызывает `open()`; весь контент через `SpatialIndex.read_content(node)`.
- **I-GRAPH-FS-ROOT-1**: ONLY `SpatialIndex` MAY access the filesystem layer. No module except `IndexBuilder` and `SpatialIndex` MAY call `open()`, `pathlib.Path.read_text()`, or any filesystem API.

---

## 4. BC-36-C: GraphCache + GraphService

### GraphCache — pure memoization (R-PICKLE fix)

```python
GRAPH_SCHEMA_VERSION: str = "50.1"
# Storage: .sdd/runtime/graph_cache/ (canonical; project-local)  ← R-GRAPHCACHE-LOCATION fix
# Format: JSON {"schema_version": "50.1", "graph": {...}}        ← R-PICKLE fix: никакого pickle
# Eviction: cache miss при schema_version mismatch

class GraphCache:
    """Pure memoization: key → DeterministicGraph.
    Нет build-логики. Нет knowledge о SpatialIndex, EdgeExtractor, GRAPH_SCHEMA_VERSION.
    """
    def get(self, key: str) -> DeterministicGraph | None: ...
    def store(self, key: str, graph: DeterministicGraph) -> None: ...
    def invalidate(self, key: str) -> None: ...
```

### GraphService — build + cache boundary (R-NAMING fix)

```python
class GraphService:
    """Build + cache boundary. Единственный модуль, знающий о
    GraphCache + GraphFactsBuilder одновременно.
    """
    def __init__(
        self,
        cache:      GraphCache,
        extractors: list[EdgeExtractor] | None = None,
    ): ...

    def get_or_build(                         # ← R-NAMING fix: НЕ get_graph()
        self,
        index:         SpatialIndex,
        force_rebuild: bool = False,
    ) -> DeterministicGraph:
        """
        1. key = _compute_fingerprint(index, self._extractors)
        2. if not force_rebuild: graph = cache.get(key); if graph: return graph
        3. graph = GraphFactsBuilder(self._extractors).build(index)
        4. cache.store(key, graph)
        5. return graph
        """

    def _compute_fingerprint(
        self,
        index:      SpatialIndex,
        extractors: list[EdgeExtractor],
    ) -> str:
        """sha256(snapshot_hash + ":" + GRAPH_SCHEMA_VERSION + ":" + extractor_hashes)
        extractor_hashes = sha256(sorted([e.EXTRACTOR_VERSION for e in extractors]) + repr(EDGE_KIND_PRIORITY))
        inspect.getsource() ЗАПРЕЩЁН (I-GRAPH-FINGERPRINT-1).              ← R-INSPECT fix
        """
```

### Инварианты

- **I-GRAPH-CACHE-1**: Graph MUST be rebuilt only if `graph_fingerprint` changed.
- **I-GRAPH-CACHE-2**: `graph_fingerprint` MUST be `sha256(snapshot_hash + ":" + GRAPH_SCHEMA_VERSION + ":" + extractor_hashes)`. `git_tree_hash` запрещён.
- **I-GRAPH-FINGERPRINT-1**: `EXTRACTOR_VERSION: ClassVar[str]` обязателен для каждого EdgeExtractor. `inspect.getsource()` запрещён. Изменение `EXTRACTOR_VERSION` или `EDGE_KIND_PRIORITY` автоматически инвалидирует кэш.
- **I-GRAPH-SERVICE-1**: `GraphService` MUST be the only caller of `GraphCache.get()` / `GraphCache.store()` and `GraphFactsBuilder.build()`. CLI MUST use `GraphService.get_or_build()` (public API).
- **I-GRAPH-SUBSYSTEM-1**: Публичный API Graph Subsystem = единственный метод `GraphService.get_or_build(index, force_rebuild) → DeterministicGraph`.

---

## 5. Новые файлы

```
src/sdd/graph/__init__.py
src/sdd/graph/types.py             — Node, Edge (frozen), DeterministicGraph
src/sdd/graph/projection.py        — ALLOWED_META_KEYS, project_node()
src/sdd/graph/errors.py            — GraphInvariantError
src/sdd/graph/extractors/__init__.py  — EdgeExtractor Protocol, _DEFAULT_EXTRACTORS
src/sdd/graph/extractors/ast_edges.py
src/sdd/graph/extractors/glossary_edges.py
src/sdd/graph/extractors/invariant_edges.py
src/sdd/graph/extractors/task_deps.py
src/sdd/graph/builder.py           — GraphFactsBuilder, EDGE_KIND_PRIORITY (private _DeterministicGraphBuilder)
src/sdd/graph/cache.py             — GraphCache (JSON, schema_version header)
src/sdd/graph/service.py           — GraphService.get_or_build()
tests/unit/graph/test_types.py
tests/unit/graph/test_projection.py
tests/unit/graph/test_extractors.py
tests/unit/graph/test_builder.py
tests/unit/graph/test_cache.py
tests/unit/graph/test_service.py
tests/unit/spatial/test_snapshot_hash.py
```

### Изменяемые файлы

```
src/sdd/spatial/index.py           — добавить: snapshot_hash: str, _content_map: dict,
                                     read_content(node) -> str; IndexBuilder.build() вычисляет оба
```

---

## 6. Verification

### Unit tests

**SpatialIndex / Projection:**

1. `test_snapshot_hash_content_based` — I-GRAPH-CACHE-2: uncommitted изменение меняет snapshot_hash.
2. `test_read_content_is_only_public_accessor` — I-SI-READ-1: `_content_map` напрямую не доступен снаружи.
3. `test_project_node_excludes_indexing_fields` — I-GRAPH-TYPES-1: `project_node()` не копирует `signature`, `git_hash`, `indexed_at`.

**EdgeExtractors (изолированные):**

4. `test_ast_edge_extractor_emits` — I-GRAPH-EMITS-1.
5. `test_ast_edge_extractor_imports`
6. `test_glossary_edge_extractor_means`
7. `test_invariant_edge_extractor_verified_by`
8. `test_task_deps_extractor_depends_on`
9. `test_extractor_no_open_call` — I-GRAPH-EXTRACTOR-2.
10. `test_graph_facts_builder_custom_extractors` — I-GRAPH-EXTRACTOR-1.

**GraphBuilder / Cache:**

11. `test_graph_cache_hit_miss` — I-GRAPH-CACHE-1.
12. `test_graph_builder_deterministic` — I-GRAPH-DET-1..3.

**Risk hardening:**

29. `test_project_node_allowlist` — I-GRAPH-META-1: unknown key → не попадает в `Node.meta`.
30. `test_project_node_blocklist_removed` — убедиться что используется allowlist, не blocklist.
31. `test_edge_priority_out_of_range` — `ValueError` при priority вне [0,1].
32. `test_edge_priority_from_canonical_table` — каждый extractor возвращает priority из EDGE_KIND_PRIORITY.
33. `test_graph_cache_key_includes_schema_version`
50. `test_graph_fingerprint_changes_on_extractor_code_change` — I-GRAPH-FINGERPRINT-1.
51. `test_deterministic_graph_has_source_snapshot_hash` — I-GRAPH-LINEAGE-1.
57. `test_fs_root_only_spatial_index` — I-GRAPH-FS-ROOT-1: grep-тест.
58. `test_project_node_debug_logs_dropped_keys` — I-GRAPH-META-DEBUG-1.

**Import direction:**

`test_import_direction_phase50` — `sdd.graph` не импортирует из `sdd.context_kernel`, `sdd.policy`, `sdd.graph_navigation`.

### Integration tests

9. `GraphFactsBuilder` на реальном `SpatialIndex` проекта: все 4 экстрактора выполняются; рёбра не пересекаются по `edge_id`; I-GRAPH-DET-3 выполняется.

---

## 7. DoD Phase 50

1. `src/sdd/graph/` importable, zero circular imports
2. Все 21 unit-тест проходят без mock `sdd.graph` internals
3. Integration test 9 проходит на реальном SpatialIndex
4. Единственный публичный метод Graph Subsystem = `GraphService.get_or_build()`
5. Cache storage = JSON в `.sdd/runtime/graph_cache/` (нет pickle-файлов)
6. Каждый EdgeExtractor имеет `EXTRACTOR_VERSION` — grep-тест
7. `SpatialIndex._content_map` нет прямых caller-ов вне SpatialIndex — grep-тест
8. `mypy --strict` проходит на `sdd.graph.*` и изменённом `sdd.spatial.index`
9. Все существующие тесты не регрессируют
