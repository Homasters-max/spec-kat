# Spec_v36_2 — Phase 36: Context Navigation Engine (CNE)

**Status:** Draft → Target ACTIVE
**Supersedes:** Spec_v36
**Baseline:** Spec_v18 (SpatialIndex)
**Philosophy:** Deterministic Graph Core + Intent‑Driven Context + Optional LightRAG Projection
**Session:** grill-me 2026-04-29 — architectural review; 16 gaps resolved
**Architectural Review:** 2026-04-29 — improve-codebase-architecture; 5 deepening decisions (I-SI-READ-1, I-GRAPH-TYPES-1, I-GRAPH-EXTRACTOR-1/2, I-INTENT-CANONICAL-1, I-CTX-MIGRATION-1/2/3, EdgeExtractor Protocol, project_node projection, BC-CTX-LEGACY migration path)
**Kernel Review:** 2026-04-29 — improve-codebase-architecture (round 2); 4 deepening decisions: GraphCache→pure KV + GraphService layer, GraphFactsBuilder→DeterministicGraph (I-GRAPH-FACTS-ESCAPE-1), ContextBudgeter+RagPolicy→PolicyResolver+NavigationPolicy (I-POLICY-RESOLVER-1), ContextEngine pure class + ContextRuntime orchestrator (I-ENGINE-PURE-1, I-RUNTIME-BOUNDARY-1)
**Agent Integration Review:** 2026-04-29 — grill-me; 8 gaps resolved (G-1..G-8): SearchCandidate, error codes, --format json, tool definitions, selection_exhausted, rag_summary separation, DocumentChunk.references, Agent Integration Guide §3)
**Architecture Model Review:** 2026-04-29 — risk analysis; 8 risks identified (R-1..R-8); Architecture Model фиксирует: 1 Kernel + Graph Subsystem + Policy Layer; PolicyResolver вынесен в BC-36-P; I-POLICY-LAYER-1, I-CONTEXT-KERNEL-INPUT-1, I-GRAPH-SUBSYSTEM-1, I-LEGACY-FS-EXCEPTION-1 добавлены.

***

## 0. Goal

Сделать **детерминированное ядро навигации и сборки контекста** поверх `SpatialIndex` с опциональной RAG‑проекцией.

```text
System := ⟨
  Kernel,
  ValidationRuntime,
  SpatialIndex,        # SSOT структуры файлов
  DeterministicGraph,  # SSOT структурных связей (in-memory, cached projection)
  GraphService,        # build + cache boundary: Index → DeterministicGraph (BC-36-C)
  GraphCache,          # pure memoization: key → DeterministicGraph (BC-36-C)
  ContextEngine,       # pure pipeline: (graph, index, node_id, intent) → NavigationResponse (BC-36-3)
  ContextRuntime,      # lifecycle orchestrator: (index, node_id, intent) → NavigationResponse (BC-36-3)
  LightRAGProjection?  # semantic / global reasoning (не SSOT)
⟩
```

**Цель:**
Давать агенту **минимальный, детерминированный и бюджетированный** контекст под запрос без guessing.

***

## 1. Принципы

1. **Graph ≠ Context** — граф это база фактов, контекст = подграф + документы.
2. **Context = minimal subgraph + documents (chunks)** — только необходимое.
3. **Deterministic Core** — на одинаковом `SpatialIndex` контекст всегда одинаков.
4. **No guessing** — SEARCH = structured uncertainty (список кандидатов без выбора); на неразрешимых запросах ядро не выдумывает (I‑DDD‑2).
5. **RAG not SSOT** — LightRAG работает только поверх переданного Context; не ходит в свой KG.
6. **Strict budget** — контекст всегда ограничен по символам (model-agnostic).
7. **Graph = cached projection** — DeterministicGraph не хранится в БД; персистируется только SpatialIndex snapshot.

***

## 1.5. Architecture Model

Система состоит из **одного Kernel** и двух вспомогательных уровней:

```text
┌─────────────────────────────────────────────────────────────────┐
│  Graph Subsystem  (stateful; BC-36-1 + BC-36-2 + BC-36-C)      │
│  GraphService.get_or_build(index) → DeterministicGraph          │
│  Ответственность: построение + кэш. НЕ знает о intent/budget.  │
└─────────────────────────┬───────────────────────────────────────┘
                          │ DeterministicGraph
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Context Kernel  (единственный runtime kernel; BC-36-3)         │
│  ContextEngine.query(graph, policy, node_id) → NavigationResponse│
│  Ответственность: traversal + assembly + budget + RAG call.     │
│  Получает inputs готовыми — НЕ строит граф, НЕ вычисляет policy.│
└─────────────────────────────────────────────────────────────────┘
                          ▲
                          │ NavigationPolicy
┌─────────────────────────────────────────────────────────────────┐
│  Policy Layer  (pure function; BC-36-P)                         │
│  PolicyResolver.resolve(intent) → NavigationPolicy              │
│  Ответственность: intent → (Budget, RagMode). Без состояния.   │
│  НЕ знает о структуре графа, traversal, cache.                  │
└─────────────────────────────────────────────────────────────────┘
```

**Runtime sequence (каноническая):**

```text
1. index    = IndexBuilder.build()
2. graph    = GraphSubsystem.get_or_build(index)        ← Graph Subsystem
3. intent   = parse_query_intent(raw_query)
4. policy   = PolicyLayer.resolve(intent)               ← Policy Layer
5. response = ContextKernel.query(graph, policy, node_id) ← Context Kernel
6. CLI formats output
```

**Запрещённые пересечения:**

| Уровень | НЕ МОЖЕТ использовать |
|---|---|
| Graph Subsystem | intent, budget, RagMode, Context Kernel |
| Policy Layer | DeterministicGraph, traversal, GraphService, cache |
| Context Kernel | GraphService.build(), PolicyResolver.resolve() |

**Инварианты:**

**I‑ARCH‑MODEL‑1**: В системе существует ровно один runtime Kernel — Context Kernel. Graph Subsystem и Policy Layer не являются Kernels. Любое введение нового "Kernel" требует явного изменения этого инварианта.

**I‑ARCH‑MODEL‑2**: Context Kernel НЕ инициирует построение графа или вычисление policy. Оба inputs (DeterministicGraph, NavigationPolicy) приходят в Context Kernel готовыми. Нарушение: вызов GraphService или PolicyResolver из ContextEngine.query().

***

## 2. Bounded Contexts

### BC‑36‑1: DeterministicGraph

#### Назначение

Детерминированное in‑memory представление структурного графа системы, полностью восстанавливаемое из `SpatialIndex`.

`DeterministicGraph.Node` — projection SpatialNode для graph layer. Не дублирует indexing-поля (`signature`, `git_hash`, `indexed_at`). `DocProvider` получает `SpatialNode` из `SpatialIndex` напрямую.

#### Типы

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
```

```python
@dataclass
class DeterministicGraph:
    nodes: dict[str, Node]
    edges_out: dict[str, list[Edge]]
    edges_in: dict[str, list[Edge]]
    source_snapshot_hash: str   # snapshot_hash SpatialIndex из которого построен граф (I-GRAPH-LINEAGE-1)

    def neighbors(self, node_id: str, kinds: set[str] | None = None) -> list[Edge]: ...
    def reverse_neighbors(self, node_id: str, kinds: set[str] | None = None) -> list[Edge]: ...
```

#### SpatialIndex.snapshot_hash и read_content

`SpatialIndex` (Phase 18, расширяется в Phase 36) получает поле и публичный метод:

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

**I‑GRAPH‑CACHE‑2**: Cache key MUST reflect full filesystem snapshot used by SpatialIndex. `git_tree_hash` недостаточен (не включает uncommitted изменения).

**I‑SI‑READ‑1**: `SpatialIndex.read_content(node)` MUST be the only public access point for node content. Direct access to `_content_map` is forbidden outside `SpatialIndex`. `DocProvider`, `GraphFactsBuilder` и все прочие потребители MUST use `read_content()`.

#### project_node

Явная проекция `SpatialNode → DeterministicGraph.Node` живёт на шве между BC-18 и BC-36-1:

```python
ALLOWED_META_KEYS: frozenset[str] = frozenset({
    "path", "language", "line_start", "line_end", "links", "phase",
    "verified_by", "introduced_in", "depends_on", "implements",
})

def project_node(n: SpatialNode) -> Node:
    """Проекция SpatialNode → Node. Использует ALLOWED_META_KEYS allowlist (I-GRAPH-META-1).
    Не копирует indexing-поля и любые неизвестные ключи. Добавление ключа = bump spec.
    Все вызовы GraphFactsBuilder/ContextEngine проходят через эту функцию.
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

**I‑GRAPH‑META‑1**: `project_node()` MUST use `ALLOWED_META_KEYS` allowlist. Unknown keys from `SpatialNode.meta` MUST be silently dropped. `ALLOWED_META_KEYS` is a `frozenset` — additions require spec bump.

**I‑GRAPH‑TYPES‑1**: `DeterministicGraph.Node` и `DeterministicGraph.Edge` MUST be independent types from `SpatialNode`/`SpatialEdge`. No inheritance. No reuse of indexing fields (`signature`, `git_hash`, `indexed_at`). `SpatialEdge` (BC-18) and `DeterministicGraph.Edge` are different types at different layers — never aliased.

#### Инварианты

- **I‑GRAPH‑DET‑1**: Для одного и того же `SpatialIndex` результат `DeterministicGraph` должен быть идентичен (byte‑wise для множества Node/Edge).
- **I‑GRAPH‑DET‑2**: Каждый `Edge.edge_id = sha256(src+":"+kind+":"+dst)[:16]`.
- **I‑GRAPH‑DET‑3**: `edges_out[src]` и `edges_in[dst]` взаимно согласованы (каждое ребро присутствует в обоих индексах).

***

### BC‑36‑2: GraphBuilder

#### Назначение

Построение `DeterministicGraph` из `SpatialIndex` с проверкой инвариантов.

#### Pipeline

```text
SpatialIndex
 → GraphFactsBuilder (оркестратор EdgeExtractor-ов; DeterministicGraphBuilder — private impl)
     ├── ASTEdgeExtractor       (imports, emits, guards, tested_by)
     ├── GlossaryEdgeExtractor  (means)
     ├── InvariantEdgeExtractor (verified_by, introduced_in)
     └── TaskDepsExtractor      (depends_on, implements)
 → DeterministicGraph           ← единственный публичный результат (I-GRAPH-FACTS-ESCAPE-1)
```

#### Каноническая таблица приоритетов рёбер

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

**I‑GRAPH‑PRIORITY‑1**: Each `EdgeExtractor` MUST assign `Edge.priority = EDGE_KIND_PRIORITY[edge.kind]`. Self-assigned priority values are forbidden. Unknown edge kinds MUST raise `GraphInvariantError`. This is the single source of truth for edge ranking — no extractor may override it.

#### EdgeExtractor Protocol

```python
from typing import Protocol

class EdgeExtractor(Protocol):
    EXTRACTOR_VERSION: ClassVar[str]  # semver; обязателен (I-GRAPH-FINGERPRINT-1); inspect.getsource() запрещён
    def extract(self, index: SpatialIndex) -> list[Edge]:
        """Чистая функция: SpatialIndex → list[Edge]. Нет side effects. Нет open()."""
        ...
```

Конкретные экстракторы:

```python
class ASTEdgeExtractor:
    """FILE-узлы: AST-скан → imports, emits (I-GRAPH-EMITS-1), guards, tested_by."""
    def extract(self, index: SpatialIndex) -> list[Edge]: ...

class GlossaryEdgeExtractor:
    """TERM-узлы: iter_terms() → means edges (glossary-проекция)."""
    def extract(self, index: SpatialIndex) -> list[Edge]: ...

class InvariantEdgeExtractor:
    """INVARIANT-узлы: iter_invariants() → verified_by, introduced_in."""
    def extract(self, index: SpatialIndex) -> list[Edge]: ...

class TaskDepsExtractor:
    """TASK-узлы: iter_tasks() → depends_on, implements."""
    def extract(self, index: SpatialIndex) -> list[Edge]: ...
```

#### GraphFactsBuilder

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
        3. Проверяет I-GRAPH-1, I-GRAPH-EMITS-1, I-DDD-1 (typed references).
        4. Строит edges_out / edges_in индексы; устанавливает source_snapshot_hash.
        5. При violation → GraphInvariantError.
        Промежуточный GraphFacts (nodes+edges как сырые списки) — internal DTO,
        не утекает за пределы этого метода (I-GRAPH-FACTS-ESCAPE-1).
        """

# DeterministicGraphBuilder — private implementation detail GraphFactsBuilder.
# Не является частью публичного интерфейса BC-36-2.
# Вызывается только из GraphFactsBuilder.build(); напрямую не использовать.
```

**I‑GRAPH‑EXTRACTOR‑1**: Каждый `EdgeExtractor` MUST be tested in isolation on a minimal `SpatialIndex` fixture. No extractor test MAY depend on another extractor. `GraphFactsBuilder` integration test uses all 4 extractors.

**I‑GRAPH‑EXTRACTOR‑2**: Каждый `EdgeExtractor.extract()` MUST NOT call `open()` directly. Весь контент через `index.read_content(node)` (I-GRAPH-FS-ISOLATION-1).

**I‑GRAPH‑FACTS‑ESCAPE‑1**: The intermediate `GraphFacts` representation (`list[Node]` + `list[Edge]`) MUST NOT escape the `GraphFactsBuilder.build()` method boundary. `DeterministicGraphBuilder` is a private implementation detail of `GraphFactsBuilder`. The only public result of BC-36-2 is `DeterministicGraph`. Tests MUST NOT instantiate `DeterministicGraphBuilder` directly — use `GraphFactsBuilder.build()` as the test surface.

#### Унаследованные инварианты

- **I‑GRAPH‑1**: Каждое ребро выводится из статического AST или явного конфига (API `SpatialIndex`); нет runtime‑анализа и causal inference.
- **I‑GRAPH‑EMITS‑1**: `emits`‑ребро только если выполнены все 4 условия (handle() + AST return + DomainEvent registry + handler binding).
- **I‑DDD‑1**: Все TERM‑ссылки валидны относительно `typed_registry()`; broken typed ref → hard violation.
- **I‑GRAPH‑FS‑ISOLATION‑1**: GraphBuilder никогда не вызывает `open()`; весь контент через `SpatialIndex.read_content(node)`.
- **I‑GRAPH‑FS‑ROOT‑1**: ONLY `SpatialIndex` MAY access the filesystem layer, directly or indirectly. No module except `IndexBuilder` and `SpatialIndex` MAY call `open()`, `pathlib.Path.read_text()`, or any filesystem API. `GraphFactsBuilder`, `EdgeExtractor`-ы, `DocProvider`, `ContextAssembler` MUST obtain all content via `SpatialIndex.read_content()`. Это правило — explicit, не implied; нарушение = hard violation.
- **I‑GRAPH‑META‑DEBUG‑1**: В debug-режиме (`--debug`) `project_node()` MUST log dropped keys: `{"dropped_meta_keys": ["unknown_key1", ...], "node_id": "..."}`. В production dropped keys логируются только на уровне WARNING если непустые. Silent drop в production сохраняется (I-GRAPH-META-1), но debug-трассировка обязательна.

***

### BC‑36‑3: ContextEngine

#### Назначение

Дать **детерминированный и бюджетированный** контекст под запрос.

#### Intent Layer: QueryIntent как канонический тип

`QueryIntent` — единственный канонический тип намерения в Phase 36+. `NavigationIntent` (BC-18, `spatial/navigator.py`) — легаси-представление; получается из `QueryIntent` через явную конверсию на шве.

```python
def to_navigation_intent(intent: QueryIntent, node_kind: str | None = None) -> "NavigationIntent":
    """Конверсия QueryIntent → NavigationIntent для backward compat с BC-18 Navigator.
    Живёт на шве (spatial/adapter.py), не в CLI и не в ContextEngine.
    node_kind используется для kind-aware логики (например EXPLAIN→TRACE fallback).
    """
```

Все CLI-команды Phase 36 (`sdd resolve`, `sdd explain`, `sdd trace`, `sdd invariant`) принимают и передают `QueryIntent` — они не знают о `NavigationIntent`.

**I‑INTENT‑CANONICAL‑1**: `QueryIntent` MUST be the single canonical intent type for Phase 36 CLI and ContextEngine. `NavigationIntent` MUST NOT appear in `ContextEngine`, `ContextAssembler`, `DocProvider`, или любом BC-36 модуле. Conversion to `NavigationIntent` is allowed ONLY in `spatial/adapter.py`.

#### 3.1 QueryIntent

```python
class QueryIntent(Enum):
    RESOLVE_EXACT  # точный id (COMMAND:complete)
    SEARCH         # structured uncertainty: возвращает N кандидатов без выбора
    EXPLAIN        # объяснить, как что-то работает (kind-aware, см. 3.2)
    TRACE          # проследить связи (обычно reverse)
    INVARIANT      # навигация по инварианту
```

```python
def parse_query_intent(query: str) -> QueryIntent:
    """
    RESOLVE_EXACT: query вида NAMESPACE:ID (COMMAND:*, EVENT:*, TERM:*, INVARIANT:*)
    INVARIANT:     query вида I-NNN или "I-XXX"
    иначе:         SEARCH (structured uncertainty)

    MUST NOT infer EXPLAIN or TRACE from keyword heuristics (I-INTENT-HEURISTIC-1).
    EXPLAIN и TRACE определяются исключительно маршрутизацией CLI-команды
    (sdd explain → EXPLAIN, sdd trace → TRACE) — не этой функцией.
    SEARCH никогда не выбирает за пользователя — возвращает список кандидатов.
    """
```

**I‑INTENT‑HEURISTIC‑1**: `parse_query_intent()` output MUST be one of `{RESOLVE_EXACT, INVARIANT, SEARCH}`. `EXPLAIN` and `TRACE` MUST NOT be inferred from query text or keyword heuristics. They are set exclusively by CLI command routing (`sdd explain` → `EXPLAIN`, `sdd trace` → `TRACE`).

#### 3.2 RankedNode, RankedEdge, Selection

Selection несёт метаданные ранжирования, необходимые для детерминированного truncation.

```python
@dataclass(frozen=True)
class RankedNode:
    node_id:        str
    hop:            int
    global_importance_score:  float   # max(priority) по ВСЕМ входящим рёбрам в DeterministicGraph (global scope, не локально в Selection); 1.0 для seed (I-RANKED-NODE-BP-1)

@dataclass(frozen=True)
class RankedEdge:
    edge_id:   str
    src:       str
    dst:       str
    hop:       int
    priority:  float

@dataclass
class Selection:
    seed:   str                      # node_id seed-узла (immutable anchor)
    nodes:  dict[str, RankedNode]    # node_id → RankedNode
    edges:  dict[str, RankedEdge]    # edge_id → RankedEdge
```

**Seed-узел:** `hop=0`, `global_importance_score=1.0` (фиксировано), не участвует в truncation (I‑CONTEXT‑SEED‑1).

**BFS построение Selection:**

```python
queue = deque([(seed_node_id, 0)])
nodes[seed_node_id] = RankedNode(seed_node_id, hop=0, global_importance_score=1.0)

while queue:
    node_id, hop = queue.popleft()
    for edge in expand(graph, node_id, strategy, hop):
        dst = edge.dst
        ranked_edge = RankedEdge(edge.edge_id, edge.src, dst, hop+1, edge.priority)
        if dst not in nodes or hop+1 < nodes[dst].hop:
            # global_importance_score = GLOBAL scope: max по всем входящим рёбрам dst
            # в DeterministicGraph (не только тем, что попали в BFS).
            # Это стабильная характеристика узла в графе, не локальная для Selection.
            # I-RANKED-NODE-BP-1
            bp = max(e.priority for e in graph.edges_in.get(dst, [edge]))
            nodes[dst] = RankedNode(dst, hop+1, bp)
            edges[edge.edge_id] = ranked_edge
            queue.append((dst, hop+1))
```

Стратегии selection зависят от intent:

- **RESOLVE_EXACT**:

  ```text
  S0 = seed
  S1 = все рёбра (out+in) с hop=1
  Selection = S0 ∪ endpoints(S1)
  ```

- **EXPLAIN** *(kind-aware)*:

  ```text
  S0 = seed
  S1 = out-edges kind ∈ {emits, guards, implements, tested_by}
  S2 = in-edges kind ∈ {depends_on} (если seed.kind == TASK)

  Если S1 = ∅ (seed.kind не имеет out-edges EXPLAIN-типов):
      → автоматический fallback на стратегию TRACE
      → выводить предупреждение: "EXPLAIN не применим к {seed.kind}, использован TRACE"

  Selection = S0 ∪ endpoints(S1 ∪ S2)
  ```

- **TRACE**:

  ```text
  S0 = seed
  S1 = reverse_neighbors(seed, kinds=None) с hop ≤ 2
  Selection = S0 ∪ endpoints(S1)
  ```

- **INVARIANT**:

  ```text
  S0 = {INVARIANT:I-XXX}
  S1 = out-edges kind ∈ {verified_by, introduced_in}
  Selection = S0 ∪ endpoints(S1)
  ```

- **SEARCH** *(structured uncertainty)*:

  ```text
  Возвращает ranked list[SearchCandidate] — top-N кандидатов по fuzzy score.
  Нет subgraph expansion. Нет выбора одного кандидата.
  Если candidates пусты → exit 1, must_not_guess: true.
  Если ровно один кандидат → автоматически применяется RESOLVE_EXACT.
  ```

  ```python
  @dataclass(frozen=True)
  class SearchCandidate:
      node_id:      str    # e.g. "COMMAND:complete"
      kind:         str    # COMMAND|EVENT|TASK|TERM|INVARIANT|FILE|...
      label:        str    # человекочитаемое имя
      summary:      str    # краткое описание узла
      fuzzy_score:  float  # релевантность запросу (0.0..1.0)
  # I-SEARCH-CANDIDATE-1: SEARCH MUST return SearchCandidate, not RankedNode.
  # Агент использует kind/label/summary для выбора без дополнительных вызовов.
  # I-SEARCH-NO-EMBED-1: fuzzy_score MUST be computed via BM25 over (label + " " + summary) corpus.
  # BM25 — обязательный алгоритм (единственный допустимый для deterministic core).
  # Embedding-based semantic similarity is FORBIDDEN unless explicitly configured as RAG-backed mode
  # (requires I-RAG-POLICY-1 override). SEARCH with embeddings = shadow RAG = violation.
  ```

**Инварианты:**

- **I‑CONTEXT‑SELECT‑1 (structural)**: Selection для заданного `(graph, start_node, intent)` детерминированна и не содержит узлов/рёбер вне формально определённой стратегии.
- **I‑CONTEXT‑SELECT‑2 (minimality)**: Ни один узел из `Selection.nodes` нельзя удалить без нарушения стратегии (проверяется в тестах на small‑graph).
- **I‑CONTEXT‑EXPLAIN‑KIND‑1**: EXPLAIN MUST check S1 emptiness before subgraph expansion; empty S1 → TRACE fallback + warning. `Context.effective_intent` MUST be set to `TRACE`; `Context.intent_transform_reason` MUST be non-None.
- **I‑RANKED‑NODE‑BP‑1**: `RankedNode.global_importance_score` MUST be computed as `max(priority)` over ALL incoming edges of `dst` in `DeterministicGraph` (global scope), not only edges present in the current BFS Selection. This is a stable node characteristic. Tests MUST verify this scope explicitly (see test `test_global_importance_score_global_scope`).

#### 3.3 DocumentChunk и Context

```python
@dataclass
class DocumentChunk:
    node_id:    str        # привязка к Node
    content:    str        # текст кода / invariant / task / doc
    kind:       str        # "code" | "invariant" | "task" | "doc"
    char_count: int        # len(content), считается при создании
    meta:       dict       # {"path": "...", "language": "python", ...}
    references: list[str]  # node_id-ы упомянутые в content (I-DOC-REFS-1)

@dataclass
class Context:
    intent:                  QueryIntent    # исходный intent (из CLI / parse_query_intent) — всегда оригинальный запрос
    effective_intent:        QueryIntent    # фактически применённый (при transform может отличаться)
    intent_transform_reason: str | None     # None если transform не происходил; non-None при EXPLAIN→TRACE и других transforms
    nodes:                   list[Node]
    edges:                   list[Edge]
    documents:               list[DocumentChunk]
    budget_used:             dict
    selection_exhausted:     bool           # True если BFS не может расшириться (I-CONTEXT-EXHAUSTED-1)
    graph_snapshot_hash:     str            # snapshot_hash графа из которого построен Context (I-CONTEXT-LINEAGE-1)
    context_id:              str            # sha256(graph_snapshot_hash + seed_node_id + intent.value)[:32] (I-CONTEXT-LINEAGE-1)
```

**DocProvider** — pure adapter поверх `SpatialIndex`. Не читает файлы напрямую, не обращается к CLAUDE.md, TaskSet.md, glossary.yaml. Использует `ContentMapper` для извлечения чанков из FILE-узлов.

```python
class ContentMapper(Protocol):
    def extract_chunk(self, node: SpatialNode, content: str) -> str:
        """
        FILE + meta has line_start/line_end → slice content by line boundaries (I-DOC-CHUNK-BOUNDARY-1)
        FILE + no line_start/line_end       → whole file content
        non-FILE nodes                      → "" (контент в node.summary/meta)
        Deterministic: same (node, content) → same output always.
        """
        ...

class DefaultContentMapper:
    def extract_chunk(self, node: SpatialNode, content: str) -> str:
        if node.kind != "FILE":
            return ""
        ls = node.meta.get("line_start")
        le = node.meta.get("line_end")
        if ls is not None and le is not None:
            lines = content.splitlines()
            return "\n".join(lines[ls - 1:le])
        return content

class DocProvider:
    def __init__(self, index: SpatialIndex,
                 mapper: ContentMapper | None = None): ...

    def get_chunks(self, node_ids: list[str]) -> list[DocumentChunk]:
        """
        FILE          → mapper.extract_chunk(node, index.read_content(node)) (I-DOC-2, I-DOC-CHUNK-BOUNDARY-1)
        COMMAND/EVENT → node.summary + "\n" + node.signature (из SpatialNode)
        INVARIANT     → node.summary + meta (phase, verified_by)
        TASK          → node.summary + meta (depends_on, implements)
        TERM          → node.summary + meta (links)
        """
```

**I‑DOC‑CHUNK‑BOUNDARY‑1**: `ContentMapper.extract_chunk()` MUST use `SpatialNode.meta["line_start", "line_end"]` as slice boundaries when both are present. If absent → whole file. Non-FILE nodes → `""`. `DocProvider` MUST use `ContentMapper`; direct inline string slicing is forbidden.

**I‑DOC‑REFS‑1**: `DocumentChunk.references` MUST contain only `node_id`-ы которые реально присутствуют в `DeterministicGraph.nodes`. Broken references (node_id не существует в графе) MUST be silently dropped при сборке. `DocProvider` вычисляет `references` из AST-анализа контента FILE-узлов и `meta["links"]` для non-FILE узлов.

**I‑CONTEXT‑EXHAUSTED‑1**: `Context.selection_exhausted` MUST be `True` if and only if `Selection.nodes` cannot be further expanded by any additional BFS step (all neighbors of all nodes in Selection are already in Selection, or truncated by budget). Агент использует этот флаг как stopping signal.

**ContextAssembler:**

```python
class ContextAssembler:
    def build(self,
              graph: DeterministicGraph,
              selection: Selection,
              budget: "Budget",
              doc_provider: "DocProvider") -> Context:
        """
        1. seed всегда включён (I-CONTEXT-SEED-1).
        2. Остальные nodes/edges сортируются по (hop ASC, -global_importance_score, node_id ASC).
        3. Берётся prefix до max_nodes / max_edges.
        4. Через doc_provider.get_chunks(node_ids) подтягиваются документы.
        5. docs сортируются по (node_rank[node_id], kind, hash(content)).
        6. Берётся prefix пока Σ char_count ≤ max_chars.
        """
```

#### 3.4 Policy Layer: PolicyResolver

Единственный источник `intent → (Budget, RagMode)` mapping. Объединяет то, что ранее было `ContextBudgeter` и `RagPolicy`, в один **policy layer** — явный уровень между intent и execution.

```python
@dataclass
class Budget:
    max_nodes: int
    max_edges: int
    max_chars: int    # model-agnostic; approx_tokens = max_chars / 4 (runtime only)

@dataclass(frozen=True)
class NavigationPolicy:
    budget:   Budget    # параметры truncation
    rag_mode: RagMode   # режим LightRAG для данного intent (RagMode из BC-36-4)

class PolicyResolver:
    """Единственный источник intent → NavigationPolicy mapping.
    ContextEngine разрешает policy здесь; ContextAssembler и LightRAGProjection
    получают уже resolved значения и не знают о QueryIntent.
    """
    _DEFAULT: dict[QueryIntent, NavigationPolicy] = {
        QueryIntent.RESOLVE_EXACT: NavigationPolicy(Budget(5,  10, 4000),  RagMode.OFF),
        QueryIntent.EXPLAIN:       NavigationPolicy(Budget(20, 40, 16000), RagMode.HYBRID),
        QueryIntent.TRACE:         NavigationPolicy(Budget(30, 60, 20000), RagMode.LOCAL),
        QueryIntent.INVARIANT:     NavigationPolicy(Budget(10, 20, 8000),  RagMode.OFF),
        QueryIntent.SEARCH:        NavigationPolicy(Budget(15, 0,  12000), RagMode.GLOBAL),
    }

    def resolve(self, intent: QueryIntent) -> NavigationPolicy:
        """Детерминированное разрешение. Вызывается ровно один раз в ContextEngine.query()."""
```

`ContextBudgeter` как отдельный класс **упразднён**. `RagPolicy` как отдельный dataclass **упразднён**. Оба заменены `PolicyResolver`.

**I‑POLICY‑RESOLVER‑1**: `PolicyResolver.resolve()` MUST be the single source of truth for `intent → (Budget, RagMode)` mapping. `ContextAssembler` и `LightRAGProjection` MUST NOT call `PolicyResolver` directly — они получают resolved values (бюджет и rag_mode) только из `ContextEngine.query()`. Tests MUST verify that `PolicyResolver._DEFAULT` covers all `QueryIntent` values.

**I‑POLICY‑LAYER‑1**: `PolicyResolver` MUST be imported ONLY в `ContextRuntime.query()` или CLI handler (точка входа в Context Kernel). Любой другой импорт PolicyResolver (из ContextEngine, ContextAssembler, GraphService, CLI subcommands) — нарушение. Граница Policy Layer / Context Kernel должна быть enforceable через import-linter или grep-test.

**Инварианты:**

- **I‑CONTEXT‑BUDGET‑1**: Любой `Context` удовлетворяет `len(nodes) ≤ max_nodes`, `len(edges) ≤ max_edges`, `Σ char_count(documents) ≤ max_chars`.
- **I‑CONTEXT‑BUDGET‑2**: Для каждого `QueryIntent` задан фиксированный `NavigationPolicy` в `PolicyResolver._DEFAULT` (юнит-тесты на полноту mapping).
- **I‑CONTEXT‑BUDGET‑EXHAUST‑1**: При `Context.selection_exhausted = True` CLI MUST возвращать partial context + warning в stderr (не ошибку). Error code `BUDGET_EXCEEDED` зарезервирован ТОЛЬКО для случая, когда бюджет исчерпан до того, как удалось включить хотя бы 1 non-seed node (т.е. context содержит только seed). `selection_exhausted = True` при наличии ≥1 node — это normal truncation, не error.
- **I‑CONTEXT‑TRUNCATE‑1**: Truncation MUST use deterministic ordering: `(hop ASC, -global_importance_score, node_id ASC)` для nodes; `(hop ASC, -priority, edge_id ASC)` для edges; `(node_rank, kind, hash(content))` для documents.
- **I‑CONTEXT‑DETERMINISM‑1**: Context MUST be identical for same `(graph, query, budget)`.
- **I‑CONTEXT‑SEED‑1**: Seed node MUST always be present in final Context regardless of budget. Seed не участвует в sorting/truncation.
- **I‑CONTEXT‑ORDER‑1**: Document ordering MUST depend only on stable `(node_id rank, kind, hash(content))` — не на BFS-derived transient order. `node_id rank` вычисляется как позиция в `sorted(selection.nodes.keys())` после truncation. Любое изменение BFS-порядка обхода MUST NOT change final document ordering. Тесты MUST verify: одинаковый граф + разный порядок edges_out → одинаковый document order.
- **I‑CONTEXT‑LINEAGE‑1**: `Context.graph_snapshot_hash` MUST equal `DeterministicGraph.source_snapshot_hash` из которого построен контекст. `Context.context_id` MUST be `sha256(graph_snapshot_hash + ":" + seed_node_id + ":" + intent.value)[:32]`. Эти поля позволяют доказать reproducibility: одинаковый `context_id` ↔ идентичный контекст.
- **I‑GRAPH‑LINEAGE‑1**: `DeterministicGraph.source_snapshot_hash` MUST be set from `SpatialIndex.snapshot_hash` at build time. Cache MUST NOT reuse a graph with mismatched `source_snapshot_hash`.

#### 3.5 ContextEngine — pure pipeline

`ContextEngine` — явный класс, encapsulating полный pipeline от графа до `NavigationResponse`. Нет I/O, нет кэша, нет `IndexBuilder`, нет PolicyResolver. Детерминированная чистая функция от `(graph, policy, index, node_id)`.

```python
class ContextEngine:
    """Pure pipeline: (DeterministicGraph, NavigationPolicy) → NavigationResponse.
    Нет зависимостей на I/O, GraphService, GraphCache, PolicyResolver. Deterministic.
    Policy уже resolved до входа в Context Kernel (I-CONTEXT-KERNEL-INPUT-1).
    """
    def __init__(
        self,
        assembler:            ContextAssembler,
        doc_provider_factory: Callable[[SpatialIndex], DocProvider],
        rag_projection:       "LightRAGProjection | None" = None,
    ): ...

    def query(
        self,
        graph:    DeterministicGraph,
        policy:   NavigationPolicy,  # уже resolved внешним вызовом PolicyResolver.resolve()
        index:    SpatialIndex,      # для DocProvider (read_content); нет прямого I/O
        node_id:  str,
    ) -> NavigationResponse:
        """
        1. selection = _build_selection(graph, node_id, policy)    # BFS + RankedNode/RankedEdge
        2. doc_provider = doc_provider_factory(index)
        3. context = assembler.build(graph, selection, policy.budget, doc_provider)
        4. rag_summary = rag_projection.query(...) if policy.rag_mode != RagMode.OFF else None
        5. return NavigationResponse(context, rag_summary, rag_mode=policy.rag_mode.value)
        """
```

**I‑ENGINE‑PURE‑1**: `ContextEngine.query()` MUST NOT call `IndexBuilder`, `GraphService`, `GraphCache`, `PolicyResolver`, or any filesystem API. It operates on an already-built `DeterministicGraph` and already-resolved `NavigationPolicy` passed by the caller. Any I/O or policy dependency in `ContextEngine` is a hard violation. Tests MUST verify `ContextEngine` is instantiable and fully functional with mock `graph` + mock `policy` + mock `index` (no real filesystem needed).

**I‑ENGINE‑POLICY‑1**: `policy.budget` MUST be passed to `ContextAssembler`; `policy.rag_mode` MUST be passed to `LightRAGProjection`. Neither `ContextAssembler` nor `LightRAGProjection` receives `NavigationPolicy` directly — только уже извлечённые из неё budget и rag_mode. `PolicyResolver.resolve()` вызывается ровно один раз — в `ContextRuntime.query()` до вызова `ContextEngine.query()`.

#### 3.6 ContextRuntime — lifecycle orchestrator

`ContextRuntime` — единственная точка входа в Context Kernel. Получает `DeterministicGraph` и `NavigationPolicy` как готовые inputs (уже построенные снаружи). Не держит `GraphService` — граф строится в CLI до вызова `ContextRuntime.query()`.

```python
class ContextRuntime:
    """Entry point to Context Kernel. Receives graph + policy as ready inputs.
    Does NOT hold GraphService. CLI builds graph + resolves policy before calling here.
    """
    def __init__(self, engine: ContextEngine): ...

    def query(
        self,
        graph:   DeterministicGraph,  # построен Graph Subsystem-ом (CLI step 2)
        policy:  NavigationPolicy,    # resolved Policy Layer-ом (CLI step 4)
        index:   SpatialIndex,        # для DocProvider
        node_id: str,
    ) -> NavigationResponse:
        """
        1. return engine.query(graph, policy, index, node_id)
        """
```

CLI-handler (canonical):
```python
index    = IndexBuilder.build()
graph    = graph_service.get_or_build(index, force_rebuild)   # Graph Subsystem
intent   = parse_query_intent(raw_query)
policy   = policy_resolver.resolve(intent)                     # Policy Layer
response = runtime.query(graph, policy, index, node_id)        # Context Kernel
```


**I‑RUNTIME‑BOUNDARY‑1**: CLI commands MUST call `ContextRuntime.query()` and MUST NOT call `ContextEngine.query()` directly. `ContextRuntime` MUST NOT import `GraphService` — graph is built by CLI before calling `ContextRuntime.query()`. Violation: CLI command that imports `ContextEngine` directly; or `ContextRuntime` that imports `GraphService`.

**I‑CONTEXT‑KERNEL‑INPUT‑1**: `ContextEngine.query()` MUST receive `DeterministicGraph` и `NavigationPolicy` как готовые параметры. `ContextEngine` MUST NOT call `GraphService.get_or_build()` or `PolicyResolver.resolve()` inside `query()`. Эти вызовы происходят до входа в Context Kernel (в CLI). Violation: любой вызов GraphService или PolicyResolver внутри ContextEngine.

***

### BC‑36‑4: LightRAGProjection (optional)

#### Назначение

Дать semantic reasoning поверх уже собранного `Context` без роли источника истины. LightRAG работает только поверх переданных DocumentChunk — не ходит в свой глобальный KG.

#### 4.1 RagMode

```python
class RagMode(Enum):
    OFF
    LOCAL
    GLOBAL
    HYBRID
```

`RagPolicy` как отдельный dataclass **упразднён** — mapping `intent → RagMode` перенесён в `PolicyResolver.resolve()` (BC-36-3 §3.4). `LightRAGProjection` получает уже resolved `rag_mode: RagMode` из `ContextEngine` — не знает о `QueryIntent`.

Mapping по умолчанию (определён в `PolicyResolver._DEFAULT`):

| Intent | RagMode |
|---|---|
| RESOLVE_EXACT | OFF |
| INVARIANT | OFF |
| EXPLAIN | HYBRID |
| TRACE | LOCAL |
| SEARCH | GLOBAL |

**I‑RAG‑POLICY‑1**: Для каждого `QueryIntent` явно определён `RagMode` в `PolicyResolver._DEFAULT`. Если `rag_mode=RagMode.OFF`, LightRAG не вызывается. `LightRAGProjection` MUST NOT inspect `QueryIntent` directly.

#### 4.2 Grounded Query Model

LightRAG вызывается исключительно поверх `Context.documents` — не поверх глобального KG:

```python
@dataclass
class NavigationResponse:
    """Полный ответ CLI-команды в --format json. Явная граница fact vs inference."""
    context:     Context         # детерминированный граф-контекст (SSOT)
    rag_summary: str | None      # semantic inference поверх context.documents; None если RAG=OFF
    rag_mode:    str | None      # "LOCAL"|"HYBRID"|"GLOBAL"|None
# I-NAV-RESPONSE-1: rag_summary MUST NOT be mixed into context.documents.
# Агент явно видит границу: context = факт, rag_summary = inference.
# При rag_mode=OFF: rag_summary=None, rag_mode=None.

class LightRAGProjection:
    def query(self,
              question:   str,
              context:    Context,
              rag_mode:   RagMode,        # resolved by PolicyResolver via ContextEngine
              rag_client: "LightRAGClient") -> "RAGResult":
        """
        rag_client.query(question, context=context.documents, mode=rag_mode.value.lower())
        LightRAG получает только context.documents как input.
        Ссылки на node_id добавляет ContextAssembler, не LightRAG.
        rag_mode приходит от ContextEngine (не вычисляется здесь — I-ENGINE-POLICY-1).

        rag_client MUST be stateless or context-scoped (I-RAG-CLIENT-ISOLATION-1).
        MUST NOT be a persistent client that has had insert_custom_kg() called on it —
        accumulated KG state would violate I-RAG-DETACH-1.
        """
```

**Экспорт в LightRAG (для pre-indexing):**

```python
class LightRAGExporter:
    def export(self,
               graph: DeterministicGraph,
               docs: list[DocumentChunk],
               rag_client: "LightRAGClient") -> None:
        entities = [{"entity_name": n.node_id, "entity_type": n.kind, ...}
                    for n in graph.nodes.values()]
        relationships = [{"src_id": e.src, "tgt_id": e.dst, "description": e.kind, ...}
                         for edges in graph.edges_out.values() for e in edges]
        chunks = [
            {
                "content": doc.content,
                "source_id": doc.node_id,
                "file_path": doc.meta.get("path", ""),
            }
            for doc in docs
        ]
        rag_client.insert_custom_kg({
            "entities": entities,
            "relationships": relationships,
            "chunks": chunks,
        })
```

| DeterministicGraph | LightRAG        |
|--------------------|-----------------|
| Node               | entity          |
| Edge               | relationship    |
| DocumentChunk      | chunk (content) |

**Инварианты:**

- **I‑RAG‑1**: LightRAGProjection не создаёт новых фактов; все entities/relationships/chunks происходят из `DeterministicGraph`/`DocumentChunk`.
- **I‑RAG‑CHUNK‑1**: Каждый entity/relationship в LightRAG связан хотя бы с одним chunk через `source_id`/`file_path`.
- **I‑RAG‑GROUNDING‑1**: RAG-ответ MUST be based only on provided `Context.documents`. Ссылки на `node_id` добавляет вызывающий код (ContextAssembler), не LightRAG.
- **I‑RAG‑DETACH‑1**: LightRAG MUST NOT access global knowledge graph during query. Передаётся только `context=context.documents`.
- **I‑RAG‑CLIENT‑ISOLATION‑1**: `LightRAGClient` used in `LightRAGProjection.query()` MUST be stateless with respect to previously inserted KG data OR scoped to the current `Context` (ephemeral per-query client). A persistent KG-accumulating client MUST NOT be reused for `query()` calls — its accumulated state violates I-RAG-DETACH-1.
- **I‑RAG‑NO‑PERSISTENCE‑1**: `LightRAGClient` used in `query()` MUST NOT persist any state across calls: no embeddings cache, no KG accumulation, no query memory, no implicit external storage. "Stateless" means zero observable state change after `query()` returns. Ephemeral per-query instantiation is the recommended implementation pattern. Violation: client that caches embeddings between calls while returning correct results — this is still a violation even if output is correct.

***

### BC‑36‑5: Legacy Context Migration (BC-CTX-LEGACY)

#### Назначение

`context/build_context.py` (Phase 18) — legaсy session adapter. `ContextAssembler` (BC-36-3) является авторитетным сборщиком контекста для Phase 36+. Оба сосуществуют в переходный период, но с явными ролями.

#### Разделение ответственностей

| Модуль | Роль | Phase |
|---|---|---|
| `context/build_context.py` | Legacy session adapter (слои 0–8, markdown out) | BC-18, устаревает |
| `ContextAssembler` (BC-36-3) | Авторитетный граф-сборщик (Selection → Context) | Phase 36+ |

#### Инварианты миграции

**I‑CTX‑MIGRATION‑1**: `ContextAssembler` MUST NOT import from `context/build_context.py`. Обратное допустимо: `build_context.py` MAY delegate to `ContextAssembler` как тонкий адаптер.

**I‑CTX‑MIGRATION‑2**: `build_context.py` MUST NOT be called from любого BC-36 модуля (CLI, ContextEngine, GraphCache, DocProvider). Если session type требует legacy-контекст — он явно вызывает `build_context.py` сам.

**I‑CTX‑MIGRATION‑3**: Код, нарушающий I-DOC-SI-ONLY-1 (прямое чтение CLAUDE.md, TaskSet.md, glossary.yaml вне SpatialIndex), допустим ТОЛЬКО внутри `build_context.py`. Вне него — нарушение.

**I‑CTX‑MIGRATION‑4**: Import boundary MUST be enforced by tooling, not only by grep-tests. Grep-tests (test 24) remain as second-layer check. Enforcement options (choose one):
- `import-linter` rule: no module under `sdd/graph/` or `sdd/context/` MAY import from `sdd.context.build_context`
- Package isolation: move `build_context.py` into `sdd/context_legacy/` package (explicit import path makes boundary visible)
- CI gate: `lint-imports` check in pre-commit / GitHub Actions

**I‑LEGACY‑FS‑EXCEPTION‑1**: `build_context.py` MAY read filesystem directly ONLY during Phase 36 migration window (в нарушение I-GRAPH-FS-ROOT-1 — временное исключение). Migration complete criteria: (1) все CLI-команды Phase 36 routing через `ContextRuntime`; (2) `build_context.py` имеет 0 прямых callers кроме legacy session adapter. После выполнения обоих критериев — прямое чтение filesystem из `build_context.py` становится нарушением I-GRAPH-FS-ROOT-1.

#### Путь миграции (отдельная задача Phase 36)

```text
Текущее состояние:
  build_context.py — читает файлы напрямую, собирает markdown

Целевое состояние (Phase 36):
  build_context.py → thin adapter
      ↓ delegates to
  ContextAssembler.build(graph, selection, budget, doc_provider)
      ↓
  Context (структурированный, детерминированный)
```

Миграция не блокирует Phase 36: `ContextAssembler` строится независимо. `build_context.py` продолжает работать для legacy session types до явного решения о deprecation.

***

### BC‑36‑P: Policy Layer

#### Назначение

Policy Layer — изолированная pure функция `QueryIntent → NavigationPolicy`. Единственная ответственность: определить бюджет и RAG-режим для данного intent. Без состояния, без знания о структуре графа, traversal, cache.

Вынесен из BC-36-3 в отдельный Bounded Context чтобы явно выразить: Policy Layer ≠ Context Kernel.

#### Типы и реализация

```python
@dataclass
class Budget:
    max_nodes: int
    max_edges: int
    max_chars: int    # model-agnostic; approx_tokens = max_chars / 4 (runtime only)

@dataclass(frozen=True)
class NavigationPolicy:
    budget:   Budget    # параметры truncation
    rag_mode: RagMode   # режим LightRAG для данного intent (RagMode из BC-36-4)

class PolicyResolver:
    """Pure mapping: QueryIntent → NavigationPolicy.
    Единственный источник intent → (Budget, RagMode) в системе.
    Не знает о DeterministicGraph, traversal, ContextEngine, GraphService.
    """
    _DEFAULT: dict[QueryIntent, NavigationPolicy] = {
        QueryIntent.RESOLVE_EXACT: NavigationPolicy(Budget(5,  10, 4000),  RagMode.OFF),
        QueryIntent.EXPLAIN:       NavigationPolicy(Budget(20, 40, 16000), RagMode.HYBRID),
        QueryIntent.TRACE:         NavigationPolicy(Budget(30, 60, 20000), RagMode.LOCAL),
        QueryIntent.INVARIANT:     NavigationPolicy(Budget(10, 20, 8000),  RagMode.OFF),
        QueryIntent.SEARCH:        NavigationPolicy(Budget(15, 0,  12000), RagMode.GLOBAL),
    }

    def resolve(self, intent: QueryIntent) -> NavigationPolicy:
        """Детерминированное разрешение. Вызывается ровно один раз в ContextRuntime.query()
        до передачи policy в ContextEngine (I-CONTEXT-KERNEL-INPUT-1).
        """
```

#### Инварианты

**I‑POLICY‑RESOLVER‑1**: `PolicyResolver.resolve()` MUST be the single source of truth for `intent → (Budget, RagMode)` mapping. `ContextAssembler` и `LightRAGProjection` MUST NOT call `PolicyResolver` directly — они получают resolved values (бюджет и rag_mode) только через уже resolved `NavigationPolicy` из `ContextEngine.query()`. Tests MUST verify that `PolicyResolver._DEFAULT` covers all `QueryIntent` values.

**I‑POLICY‑LAYER‑1**: `PolicyResolver` MUST be imported ONLY в точке входа Context Kernel (`ContextRuntime.query()` или CLI handler). Импорт PolicyResolver из ContextAssembler, GraphService, CLI subcommands — нарушение. Граница Policy Layer / Context Kernel должна быть enforceable через import-linter или grep-test.

**I‑POLICY‑LAYER‑PURE‑1**: `PolicyResolver` MUST be a pure function: `resolve(intent) → NavigationPolicy` без side effects, без I/O, без state. Одинаковый `intent` → идентичный `NavigationPolicy`. Policy Layer не инициализируется с внешними зависимостями.

***

### BC‑36‑7: CLI

#### Команды

```bash
sdd resolve <query>            [--rebuild] [--debug] [--format json|text]
sdd explain <node_id>          [--rebuild] [--debug] [--format json|text]
sdd trace <node_id>            [--rebuild] [--debug] [--format json|text]
sdd invariant <I-NNN>          [--rebuild] [--debug] [--format json|text]
```

`--rebuild` — принудительная пересборка графа (игнорирует GraphCache).  
`--format json` — машиночитаемый вывод `NavigationResponse` (для агентов). Дефолт: `text`.

**I-CLI-FORMAT-1**: `--format json` MUST output a valid `NavigationResponse` JSON on stdout. `--format text` MUST output human-readable markdown. Exit codes и JSON stderr неизменны при обоих форматах.

Контракт (общий):

```text
1) index  = IndexBuilder.build() → SpatialIndex (с snapshot_hash)
2) intent = parse_query_intent(query or node_id)   # RESOLVE_EXACT / INVARIANT / SEARCH / EXPLAIN / TRACE
3) graph    = graph_service.get_or_build(index, force_rebuild=--rebuild)    ← Graph Subsystem (BC-36-C)
   policy  = policy_resolver.resolve(intent)                               ← Policy Layer (BC-36-P)
   response = runtime.query(graph, policy, index, node_id)                 ← Context Kernel (BC-36-3)
              # Внутри ContextEngine:
              #   selection → assembler.build(... policy.budget ...)  ← ContextAssembler
              #   rag      = rag_projection.query(... policy.rag_mode ...) ← LightRAGProjection
4) вывести response по --format (NavigationResponse JSON / markdown)
```

#### Error Codes (BC-36 CLI)

Все ошибки выводятся в JSON stderr (совместимо с I-CLI-API-1). Типизированные коды для GraphNavigation:

| `error_type` | Условие | Рекомендуемое действие агента |
|---|---|---|
| `NOT_FOUND` | SEARCH вернул 0 кандидатов; node_id не существует в графе | Сообщить пользователю, запросить уточнение |
| `GRAPH_NOT_BUILT` | GraphCache промах + IndexBuilder завершился с ошибкой | Повторить с `--rebuild`; эскалировать если снова ошибка |
| `INVARIANT_VIOLATION` | `GraphInvariantError` при построении графа | Стоп + эскалация; не повторять |
| `BUDGET_EXCEEDED` | Context превысил лимит (не должно происходить — защитный код) | Использовать `--format json` и урезать самостоятельно |

**I-CLI-ERROR-CODES-1**: BC-36 CLI MUST use exactly these `error_type` values for the conditions above. Unknown errors MUST use `error_type = "INTERNAL_ERROR"`.

#### Debug‑режим

```bash
sdd explain COMMAND:complete --debug
```

```json
{
  "intent": "EXPLAIN",
  "selection": {
    "start_node": "COMMAND:complete",
    "strategy": "EXPLAIN_DEFAULT_V1",
    "steps": [
      {"name": "seed", "nodes_added": ["COMMAND:complete"], "edges_added": []},
      {"name": "out_edges_emit_guard_impl_test",
       "nodes_added": ["EVENT:TaskImplementedEvent"],
       "edges_added": ["e1234..."]}
    ]
  },
  "budget": {
    "max_nodes": 20,
    "max_edges": 40,
    "max_chars": 16000,
    "used_nodes": 17,
    "used_edges": 31,
    "total_chars": 9800
  },
  "dropped": {"nodes": [], "edges": []}
}
```

**Инварианты:**

- **I‑CLI‑TRANSPARENCY‑1**: В debug‑режиме каждая стадия выбора (`selection.steps`) должна быть видна пользователю.
- **I‑CLI‑TRANSPARENCY‑2**: В debug‑режиме бюджет и фактически использованные ресурсы (`budget`) должны быть отражены.

#### §7.2 Tool Definitions (Agent Integration)

Четыре отдельных tool definition для LLM tool use. Схемы — часть спеки (I-CLI-FORMAT-1).

```json
{
  "name": "sdd_resolve",
  "description": "Поиск узлов графа по свободному тексту. Возвращает ranked list кандидатов (SearchCandidate) без выбора. Используй когда не знаешь точный node_id. При одном кандидате автоматически применяется RESOLVE_EXACT.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query":   {"type": "string", "description": "Свободный текст или NAMESPACE:ID"},
      "rebuild": {"type": "boolean", "default": false}
    },
    "required": ["query"]
  }
}
```

```json
{
  "name": "sdd_explain",
  "description": "Объяснить как работает узел графа: его out-связи (emits, guards, implements, tested_by). Лучший выбор для COMMAND и TASK узлов. Для EVENT/TERM автоматически применяется TRACE fallback.",
  "input_schema": {
    "type": "object",
    "properties": {
      "node_id": {"type": "string", "description": "Точный node_id, например COMMAND:complete"},
      "rebuild": {"type": "boolean", "default": false}
    },
    "required": ["node_id"]
  }
}
```

```json
{
  "name": "sdd_trace",
  "description": "Проследить обратные связи узла: кто на него ссылается (reverse BFS, max hop=2). Лучший выбор для EVENT и TERM узлов.",
  "input_schema": {
    "type": "object",
    "properties": {
      "node_id": {"type": "string", "description": "Точный node_id, например EVENT:TaskImplementedEvent"},
      "rebuild": {"type": "boolean", "default": false}
    },
    "required": ["node_id"]
  }
}
```

```json
{
  "name": "sdd_invariant",
  "description": "Навигация по инварианту: узел INVARIANT + verified_by + introduced_in связи.",
  "input_schema": {
    "type": "object",
    "properties": {
      "invariant_id": {"type": "string", "description": "Идентификатор инварианта, например I-GRAPH-DET-1"},
      "rebuild":      {"type": "boolean", "default": false}
    },
    "required": ["invariant_id"]
  }
}
```

Все четыре tool вызывают соответствующую CLI команду с `--format json` и возвращают `NavigationResponse`.

**I-TOOL-DEF-1**: Tool definitions MUST match CLI contract exactly. `node_id` формат MUST follow namespace convention (`KIND:identifier`). Изменение CLI сигнатуры = breaking change → требует bump tool schema version.

***

### BC‑36‑C: GraphCache + GraphService

Два разных модуля с чёткими ролями:

- **`GraphCache`** — pure memoization: key → DeterministicGraph. Нет build-логики, нет policy.
- **`GraphService`** — build + cache boundary: знает fingerprint-алгоритм, оркестрирует `GraphCache` + `GraphFactsBuilder`. Единственный вызывающий обоих.

#### GraphCache — pure memoization

```python
GRAPH_SCHEMA_VERSION: str = "36.1"
# Bump только при структурных изменениях типов Node/Edge/DeterministicGraph.
# Primary invalidation — через extractor_hashes в GraphService._compute_fingerprint() (I-GRAPH-FINGERPRINT-1).
# GRAPH_SCHEMA_VERSION = последний рубеж, не основной механизм инвалидации.

class GraphCache:
    """Pure memoization: key → DeterministicGraph. Нет build-логики.
    Storage: .sdd/runtime/graph_cache/ (canonical; project-local)
    Format: JSON {"schema_version": "50.1", "graph": {...}} — никакого pickle
    Eviction: cache miss при schema_version mismatch; ручная (sdd cache-clear) или TTL (опционально)
    """
    def get(self, key: str) -> DeterministicGraph | None: ...
    def store(self, key: str, graph: DeterministicGraph) -> None: ...
    def invalidate(self, key: str) -> None: ...
```

`GraphCache` не знает о `SpatialIndex`, `EdgeExtractor`, `GRAPH_SCHEMA_VERSION`. Это детали `GraphService`.

#### GraphService — build + cache boundary

```python
class GraphService:
    """Build + cache boundary. Единственный модуль, знающий о
    GraphCache + GraphFactsBuilder одновременно.
    Вычисляет graph_fingerprint. Никто кроме него не вызывает GraphCache напрямую.
    """
    def __init__(
        self,
        cache:      GraphCache,
        extractors: list[EdgeExtractor] | None = None,
    ): ...

    def get_or_build(
        self,
        index:         SpatialIndex,
        force_rebuild: bool = False,
    ) -> DeterministicGraph:
        """
        1. key = _compute_fingerprint(index, self._extractors)   # I-GRAPH-CACHE-2
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
        inspect.getsource() запрещён (I-GRAPH-FINGERPRINT-1).
        """
```

| Сценарий | Поведение |
|---|---|
| код не менялся | cache hit → reuse graph |
| код изменился | fingerprint изменился → rebuild + store |
| `--rebuild` флаг | force rebuild, игнорирует cache.get() |

**Инварианты:**

- **I‑GRAPH‑CACHE‑1**: Graph MUST be rebuilt only if `graph_fingerprint` changed.
- **I‑GRAPH‑CACHE‑2**: `graph_fingerprint` MUST be `sha256(snapshot_hash + ":" + GRAPH_SCHEMA_VERSION + ":" + extractor_hashes)`. `git_tree_hash` запрещён — не включает uncommitted изменения.
- **I‑GRAPH‑FINGERPRINT‑1**: Каждый `EdgeExtractor` MUST реализовывать `EXTRACTOR_VERSION: ClassVar[str]` (semver). `inspect.getsource()` для вычисления fingerprint запрещён (нестабилен: whitespace-sensitive). `extractor_hashes = sha256(sorted([e.EXTRACTOR_VERSION for e in extractors]) + repr(EDGE_KIND_PRIORITY))`. Изменение `EXTRACTOR_VERSION` или `EDGE_KIND_PRIORITY` автоматически инвалидирует кэш. `GRAPH_SCHEMA_VERSION` остаётся как последний рубеж для структурных изменений типов Node/Edge/DeterministicGraph.
- **I‑GRAPH‑SERVICE‑1**: `GraphService` MUST be the only caller of `GraphCache.get()` / `GraphCache.store()` and `GraphFactsBuilder.build()`. CLI commands MUST use `GraphService.get_or_build()` (public API), NOT access `GraphCache` or `GraphFactsBuilder` directly. `ContextRuntime` does NOT call `GraphService` — graph построен до вызова `ContextRuntime.query()`. Violation: any module outside `GraphService` that imports `GraphCache` for write operations.
- **I‑GRAPH‑SUBSYSTEM‑1**: Публичный API Graph Subsystem = единственный метод `GraphService.get_or_build(index: SpatialIndex, force_rebuild: bool = False) → DeterministicGraph`. Graph Subsystem не экспортирует `GraphCache`, `GraphFactsBuilder`, fingerprint-логику. Всё прочее — internal detail. CLI вызывает `get_or_build()`, получает готовый `DeterministicGraph`, передаёт в Context Kernel.

**DocProvider инварианты (из grill-me сессии):**

- **I‑DOC‑SI‑ONLY‑1**: DocProvider MUST use SpatialIndex as the only source of truth. CLAUDE.md, TaskSet.md, glossary.yaml не читаются напрямую.
- **I‑DOC‑2**: Chunk extraction для FILE-узлов MUST be deterministic (AST-based); fallback = whole file если AST match не найден.

***

## 3. Agent Integration Guide

### 3.0 Модель взаимодействия

Агент (LLM) работает с GraphNavigation через **tool use** — явные вызовы `sdd_resolve`, `sdd_explain`, `sdd_trace`, `sdd_invariant`. Агент самостоятельно выбирает инструмент и формирует `node_id`. GraphNavigation не является препроцессором — контекст строится on-demand по мере необходимости.

```text
Канонический flow (happy path):

  1. Пользователь: "объясни как работает команда complete"
  2. Агент: sdd_resolve("complete task")
     → [{node_id: "COMMAND:complete", kind: "COMMAND", label: "complete", summary: "...", fuzzy_score: 0.95}]
  3. Агент: sdd_explain("COMMAND:complete")
     → NavigationResponse {
         context: {nodes, edges, documents, selection_exhausted: false, effective_intent: "EXPLAIN"},
         rag_summary: "..."
       }
  4. Агент видит в documents: chunk с references: ["EVENT:TaskImplementedEvent"]
  5. Агент: sdd_trace("EVENT:TaskImplementedEvent")
     → NavigationResponse {context: {..., selection_exhausted: true}, rag_summary: null}
  6. Агент формирует ответ пользователю на основе собранного контекста
```

### 3.1 Онтология (System Prompt)

Агент ДОЛЖЕН знать следующее (вшивается в system prompt):

#### Node kinds и namespace конвенция

| Kind | Namespace пример | Описание |
|---|---|---|
| `COMMAND` | `COMMAND:complete` | CLI-команда SDD |
| `EVENT` | `EVENT:TaskImplementedEvent` | DomainEvent |
| `TASK` | `TASK:T-4901` | Задача TaskSet |
| `INVARIANT` | `INVARIANT:I-GRAPH-DET-1` | Инвариант системы |
| `TERM` | `TERM:WriteKernel` | Термин глоссария |
| `FILE` | `FILE:src/sdd/commands/complete.py` | Файл кодовой базы |

#### Edge kinds и семантика

| Kind | Приоритет | Направление | Семантика |
|---|---|---|---|
| `emits` | 0.95 | COMMAND → EVENT | команда порождает событие |
| `guards` | 0.90 | GUARD → COMMAND | guard проверяет команду |
| `implements` | 0.85 | FILE → COMMAND | файл реализует команду |
| `tested_by` | 0.80 | COMMAND → TEST | команда покрыта тестом |
| `verified_by` | 0.75 | INVARIANT → TEST | инвариант верифицирован тестом |
| `depends_on` | 0.70 | TASK → TASK | зависимость между задачами |
| `introduced_in` | 0.65 | INVARIANT → COMMAND | инвариант введён командой |
| `imports` | 0.60 | FILE → FILE | импорт модуля |
| `means` | 0.50 | TERM → NODE | определение термина |

#### Выбор инструмента

| Ситуация | Инструмент |
|---|---|
| Не знаю точный node_id | `sdd_resolve` |
| Хочу понять как работает COMMAND/TASK | `sdd_explain` |
| Хочу понять кто использует EVENT/TERM | `sdd_trace` |
| Хочу проверить инвариант | `sdd_invariant` |
| EVENT/TERM через `sdd_explain` | система сделает TRACE fallback автоматически |

### 3.2 Правила работы агента

**I-AGENT-1 (no direct file read)**: Агент MUST NOT читать файлы кодовой базы напрямую. Весь контекст — через GraphNavigation (`I-DOC-SI-ONLY-1`).

**I-AGENT-2 (fallback handling)**: Если `effective_intent ≠ intent` в ответе — агент MUST сообщить пользователю о fallback и учесть `effective_intent` при следующем шаге.

**I-AGENT-3 (stopping)**: Если `selection_exhausted: true` — дальнейший вызов того же узла не даст новой информации. Агент MUST остановить навигацию по данной ветке.

**I-AGENT-4 (references chain)**: Агент MAY использовать `DocumentChunk.references` как готовые цели для следующего navigation call без дополнительного парсинга content.

**I-AGENT-5 (rag boundary)**: `rag_summary` — semantic inference, не факт. При задачах требующих точности агент MUST использовать только `context`, игнорируя `rag_summary`.

**I-AGENT-6 (error handling)**:
- `NOT_FOUND` → сообщить пользователю, запросить уточнение
- `GRAPH_NOT_BUILT` → повторить с `rebuild: true`; если снова ошибка — эскалировать
- `INVARIANT_VIOLATION` → стоп + эскалация; не повторять
- `INTERNAL_ERROR` → стоп + эскалация

**I-AGENT-7 (session budget)**: Агент сам контролирует количество navigation calls. GraphNavigation гарантирует детерминированный per-call бюджет. Сессионный лимит — ответственность agent harness.

***

## 4. Use Cases

### UC‑36‑1: Explain command

```bash
sdd explain COMMAND:complete
```

- Intent: `EXPLAIN`
- Selection: `COMMAND:complete` (seed) + `emits/guards/implements/tested_by` соседей, hop=1.
- Budget: `max_nodes=20`, `max_edges=40`, `max_chars=16000`.
- Output: `Context` + (если RagPolicy.EXPLAIN=HYBRID) LightRAG‑summary поверх Context.documents.

### UC‑36‑2: Explain для EVENT (kind-aware fallback)

```bash
sdd explain EVENT:TaskImplementedEvent
```

- Intent: `EXPLAIN` → S1=∅ (EVENT не имеет emits/guards/implements out-edges) → auto TRACE
- Warning: `"EXPLAIN не применим к EVENT, использован TRACE"`
- Selection: reverse-edges от события, max hop=2.

### UC‑36‑3: Trace event

```bash
sdd trace EVENT:TaskImplementedEvent
```

- Intent: `TRACE`
- Selection: reverse‑edges от события, max hop=2.
- Результат: подграф вызвавших команд/тасков.

### UC‑36‑4: Resolve search (structured uncertainty)

```bash
sdd resolve "complete task"
```

- Intent: `SEARCH`
- Алгоритм:
  - fuzzy поиск кандидатов в `DeterministicGraph` (label/summary),
  - если 0 кандидатов → exit 1, `must_not_guess: true`,
  - если 1 кандидат → автоматически RESOLVE_EXACT,
  - если N>1 кандидатов → вернуть ranked list, не выбирать (I‑DDD‑2).

***

## 4. Verification

### Unit tests

**SpatialIndex / Projection:**

1. `test_snapshot_hash_content_based` — I‑GRAPH‑CACHE‑2: uncommitted изменение меняет snapshot_hash.
2. `test_read_content_is_only_public_accessor` — I‑SI‑READ‑1: `patch SpatialIndex._content_map` напрямую → нет прямого доступа снаружи; `read_content()` возвращает корректный контент.
3. `test_project_node_excludes_indexing_fields` — I‑GRAPH‑TYPES‑1: `project_node()` не копирует `signature`, `git_hash`, `indexed_at`; результат — независимый `Node`.

**EdgeExtractors (изолированные):**

4. `test_ast_edge_extractor_emits` — I‑GRAPH‑EMITS‑1: extract() возвращает emits только при выполнении всех 4 условий.
5. `test_ast_edge_extractor_imports` — imports-рёбра из minimal SpatialIndex fixture.
6. `test_glossary_edge_extractor_means` — GlossaryEdgeExtractor на minimal TERM-узлах.
7. `test_invariant_edge_extractor_verified_by` — InvariantEdgeExtractor: verified_by/introduced_in.
8. `test_task_deps_extractor_depends_on` — TaskDepsExtractor: depends_on/implements.
9. `test_extractor_no_open_call` — I‑GRAPH‑EXTRACTOR‑2: patch `builtins.open` → каждый extractor не вызывает его.
10. `test_graph_facts_builder_custom_extractors` — I‑GRAPH‑EXTRACTOR‑1: GraphFactsBuilder с одним extractor возвращает только его рёбра.

**GraphBuilder / Cache:**

11. `test_graph_cache_hit_miss` — I‑GRAPH‑CACHE‑1: rebuild только при изменении snapshot_hash.
12. `test_graph_builder_deterministic` — I‑GRAPH‑DET‑1..3.

**QueryIntent / Canonical Layer:**

13. `test_query_intent_parse_all_forms` — RESOLVE_EXACT (COMMAND:X), INVARIANT (I-NNN), SEARCH (ambiguous), EXPLAIN (how/why), TRACE.
14. `test_to_navigation_intent_conversion` — I‑INTENT‑CANONICAL‑1: `to_navigation_intent()` живёт только в `spatial/adapter.py`; ContextEngine не импортирует NavigationIntent.
15. `test_context_engine_uses_query_intent_only` — I‑INTENT‑CANONICAL‑1: grep-тест что ContextEngine, ContextAssembler, DocProvider не импортируют NavigationIntent.

**ContextEngine / Selection:**

16. `test_ranked_selection_bfs` — RankedNode.hop корректен; seed.global_importance_score=1.0.
17. `test_context_selection_resolve/explain/trace/invariant` — I‑CONTEXT‑SELECT‑1/2.
18. `test_explain_kind_aware_fallback` — I‑CONTEXT‑EXPLAIN‑KIND‑1: EVENT/TERM → TRACE fallback + warning.
19. `test_context_truncation_deterministic` — I‑CONTEXT‑TRUNCATE‑1: одинаковый порядок при одинаковом input.
20. `test_context_seed_always_present` — I‑CONTEXT‑SEED‑1: seed не выбрасывается при overflow budget.
21. `test_context_budget_chars` — I‑CONTEXT‑BUDGET‑1: `Σ char_count ≤ max_chars`.
22. `test_context_budget_per_intent` — I‑CONTEXT‑BUDGET‑2.

**DocProvider / Migration:**

23. `test_doc_provider_si_only` — I‑DOC‑SI‑ONLY‑1: patch open() → AssertionError в DocProvider.
24. `test_context_assembler_no_build_context_import` — I‑CTX‑MIGRATION‑1: grep-тест что ContextAssembler не импортирует из `context/build_context`.

**RAG:**

25. `test_rag_export_mapping` — I‑RAG‑1/CHUNK‑1.
26. `test_rag_grounding` — I‑RAG‑GROUNDING‑1: LightRAG получает только context.documents.
27. `test_search_structured_uncertainty` — SEARCH возвращает список, не выбирает.
28. `test_cli_debug_output` — I‑CLI‑TRANSPARENCY‑1/2; `max_chars` и `total_chars` в JSON.

**Новые тесты (Phase 36 risk hardening):**

29. `test_project_node_allowlist` — I‑GRAPH‑META‑1: `SpatialNode` с unknown key в meta → key не попадает в `Node.meta`.
30. `test_project_node_blocklist_removed` — убедиться что старый blocklist `not in (signature, git_hash, indexed_at)` не используется; вместо него allowlist.
31. `test_edge_priority_out_of_range` — `Edge(priority=1.5, ...)` → `ValueError`; `Edge(priority=-0.1, ...)` → `ValueError`.
32. `test_edge_priority_from_canonical_table` — каждый `EdgeExtractor` возвращает рёбра с `priority == EDGE_KIND_PRIORITY[edge.kind]`; самостоятельное задание приоритета → `GraphInvariantError`.
33. `test_graph_cache_key_includes_schema_version` — I‑GRAPH‑CACHE‑2: изменение `GRAPH_SCHEMA_VERSION` (при неизменном `snapshot_hash`) → cache miss, граф пересобирается.
34. `test_global_importance_score_global_scope` — I‑RANKED‑NODE‑BP‑1: граф с двумя путями к `dst` (один в BFS-обходе, один нет); `RankedNode.global_importance_score` = max по обоим входящим рёбрам в DeterministicGraph.
35. `test_parse_query_intent_no_explain_trace` — I‑INTENT‑HEURISTIC‑1: `parse_query_intent("how does X work")` → `SEARCH`, не `EXPLAIN`; `parse_query_intent("what emits Y")` → `SEARCH`, не `TRACE`.
36. `test_explain_fallback_context_fields` — I‑CONTEXT‑EXPLAIN‑KIND‑1: EVENT-seed → fallback; `context.intent == EXPLAIN`, `context.effective_intent == TRACE`, `context.intent_transform_reason is not None`.
37. `test_content_mapper_line_boundaries` — I‑DOC‑CHUNK‑BOUNDARY‑1: `SpatialNode(kind="FILE", meta={"line_start": 5, "line_end": 10})` → `extract_chunk` возвращает строки 5–10; без `line_start/line_end` → весь файл; non-FILE → `""`.
38. `test_doc_provider_uses_content_mapper` — `DocProvider` вызывает `mapper.extract_chunk()` для FILE-узлов; прямое слайсирование строк в `DocProvider` запрещено (mock `mapper` — вызван).
39. `test_rag_client_is_stateless` — I‑RAG‑CLIENT‑ISOLATION‑1: mock `rag_client`; проверить что `rag_client.query_global()` или эквивалент не вызывается; только `rag_client.query(question, context=context.documents, ...)`.
40. `test_ctx_migration_import_boundary` — I‑CTX‑MIGRATION‑4: статический grep-тест; ни один модуль в `sdd/graph/` или `sdd/context/` не импортирует из `sdd.context.build_context`.
41. `test_search_candidate_has_label_summary_kind` — I‑SEARCH‑CANDIDATE‑1: SEARCH возвращает `SearchCandidate` с непустыми `label`, `summary`, `kind`; `RankedNode` в SEARCH-ответе запрещён.
42. `test_document_chunk_references_valid_node_ids` — I‑DOC‑REFS‑1: все `node_id` в `references` присутствуют в графе; broken refs dropped.
43. `test_selection_exhausted_true_when_no_expansion` — I‑CONTEXT‑EXHAUSTED‑1: граф где все соседи seed уже в Selection → `selection_exhausted=True`.
44. `test_selection_exhausted_false_when_expandable` — I‑CONTEXT‑EXHAUSTED‑1: граф с непосещёнными соседями → `selection_exhausted=False`.
45. `test_navigation_response_rag_summary_separate` — I‑NAV‑RESPONSE‑1: `rag_summary` не присутствует в `context.documents`; при `RagMode=OFF` → `rag_summary=None`.
46. `test_cli_format_json_valid_navigation_response` — I‑CLI‑FORMAT‑1: `sdd explain X --format json` → валидный JSON с полями `context`, `rag_summary`, `rag_mode`.
47. `test_cli_error_codes_not_found` — I‑CLI‑ERROR‑CODES‑1: несуществующий node_id → exit 1, `error_type="NOT_FOUND"` в JSON stderr.
48. `test_cli_error_codes_graph_not_built` — I‑CLI‑ERROR‑CODES‑1: имитация ошибки IndexBuilder → `error_type="GRAPH_NOT_BUILT"`.
49. `test_tool_def_node_id_format` — I‑TOOL‑DEF‑1: tool definition принимает только строки вида `KIND:identifier`; невалидный формат → валидационная ошибка до вызова CLI.
50. `test_graph_fingerprint_changes_on_extractor_code_change` — I‑GRAPH‑FINGERPRINT‑1: mock extractor с изменённым source → новый `extractor_hashes` → cache miss без ручного bump `GRAPH_SCHEMA_VERSION`.
51. `test_deterministic_graph_has_source_snapshot_hash` — I‑GRAPH‑LINEAGE‑1: `DeterministicGraph.source_snapshot_hash` равен `SpatialIndex.snapshot_hash` использованному при build.
52. `test_context_id_deterministic` — I‑CONTEXT‑LINEAGE‑1: одинаковые `(graph_snapshot_hash, seed, intent)` → одинаковый `context_id`; разные → разные.
53. `test_context_graph_snapshot_hash_matches_graph` — I‑CONTEXT‑LINEAGE‑1: `context.graph_snapshot_hash == graph.source_snapshot_hash`.
54. `test_document_order_stable_regardless_of_bfs_traversal_order` — I‑CONTEXT‑ORDER‑1: два одинаковых графа с разным порядком edges_out → идентичный document order в Context.
55. `test_search_no_embeddings` — I‑SEARCH‑NO‑EMBED‑1: patch embedding library → не вызывается при SEARCH; `fuzzy_score` вычисляется только лексически.
56. `test_rag_no_persistence` — I‑RAG‑NO‑PERSISTENCE‑1: два последовательных `LightRAGProjection.query()` с разными `context` → второй вызов не содержит данных из первого (проверяется через mock client state).
57. `test_fs_root_only_spatial_index` — I‑GRAPH‑FS‑ROOT‑1: grep-тест; `open(` и `Path.*read` не встречаются в `sdd/graph/`, `sdd/context/`, `sdd/spatial/navigator.py`; разрешены только в `sdd/spatial/index_builder.py` и `sdd/spatial/spatial_index.py`.
58. `test_project_node_debug_logs_dropped_keys` — I‑GRAPH‑META‑DEBUG‑1: `project_node()` с `SpatialNode(meta={"unknown_key": 1})` в debug mode → лог содержит `dropped_meta_keys: ["unknown_key"]`.

### Integration tests

1. `sdd explain COMMAND:complete` → детерминированный JSON, ≤20 узлов, `total_chars ≤ 16000`.
2. `sdd trace EVENT:TaskImplementedEvent` → ≤2 hop, корректные reverse‑соседи.
3. `sdd invariant I-XXX` → INVARIANT узел + verified_by/introduced_in.
4. `sdd resolve "complete task"` → ranked list при N>1 совпадениях, без выбора.
5. `sdd resolve "unknown xyz"` → exit 1, `must_not_guess: true`.
6. `sdd explain EVENT:X` → TRACE fallback + warning в stderr.
7. `sdd explain COMMAND:complete --rebuild` → graph пересобирается, новый cache entry.
8. При включённом LightRAGProjection: export не создаёт новые node_id; RAG query получает только context.documents.
9. `GraphFactsBuilder` на реальном `SpatialIndex` проекта: все 4 экстрактора выполняются; рёбра не пересекаются по `edge_id`; `I-GRAPH-DET-3` выполняется для результирующего `DeterministicGraph`.
10. `ContextAssembler` не вызывает `build_context()`: end-to-end тест `sdd explain` проходит без импорта `context/build_context`.

***

## 5. Коротко (для LLM)

```text
Architecture (GraphExecution Kernel):

Filesystem
  ↓ (единственный reader — I-GRAPH-FS-ROOT-1)
IndexBuilder → SpatialIndex (snapshot_hash, read_content())    ← I-SI-READ-1

  ↓                                      ↓
GraphService (BC-36-C)              DocProvider (SpatialIndex.read_content() only)
  ├── GraphCache (pure KV)               ← I-GRAPH-SERVICE-1: только GraphService вызывает cache
  └── GraphFactsBuilder                  ← I-GRAPH-FACTS-ESCAPE-1: DeterministicGraph — единственный выход
        ├── ASTEdgeExtractor             → I-GRAPH-EXTRACTOR-1/2, I-GRAPH-FS-ISOLATION-1
        ├── GlossaryEdgeExtractor
        ├── InvariantEdgeExtractor
        └── TaskDepsExtractor
        └── [private] DeterministicGraphBuilder
  ↓
  fingerprint = sha256(snapshot_hash + SCHEMA_VERSION + extractor_hashes)  ← I-GRAPH-CACHE-2
  ↓
DeterministicGraph (source_snapshot_hash)   ← I-GRAPH-TYPES-1, I-GRAPH-LINEAGE-1

  ↓

CLI (BC-36-7) — runtime coordinator:
  index   = IndexBuilder.build()
  graph   = graph_service.get_or_build(index, force_rebuild)  ← Graph Subsystem (BC-36-C)
  intent  = parse_query_intent(query)    ← I-INTENT-CANONICAL-1, I-INTENT-HEURISTIC-1
  policy  = policy_resolver.resolve(intent)                   ← Policy Layer (BC-36-P)
  response = runtime.query(graph, policy, index, node_id)     ← Context Kernel (BC-36-3)
  output → --format json|text            ← I-CLI-FORMAT-1

ContextRuntime (BC-36-3 §3.6)      ← I-RUNTIME-BOUNDARY-1: единственная точка входа в Context Kernel
  └── ContextEngine (pure, BC-36-3 §3.5)  ← I-ENGINE-PURE-1: нет I/O, cache, PolicyResolver
        ├── _build_selection(graph, node_id, policy)
        │     └── BFS → RankedNode / RankedEdge (I-RANKED-NODE-BP-1)
        │     └── EXPLAIN S1=∅ → TRACE fallback (I-CONTEXT-EXPLAIN-KIND-1)
        │     └── SEARCH = structured uncertainty (I-SEARCH-CANDIDATE-1)
        ├── ContextAssembler.build(graph, selection, policy.budget, doc_provider)
        │     └── deterministic truncation: (hop, -score, id) (I-CONTEXT-TRUNCATE-1)
        │     └── seed = immutable anchor (I-CONTEXT-SEED-1)
        └── LightRAGProjection.query(..., rag_mode=policy.rag_mode)  ← if rag_mode != OFF
              └── grounded on Context.documents only (I-RAG-DETACH-1)
  ↓
NavigationResponse { context (fact), rag_summary (inference), rag_mode }  ← I-NAV-RESPONSE-1

Layers (ownership):
  Graph Subsystem  (BC-36-C)   owns: cache + build + fingerprint; public API = get_or_build()
  Policy Layer     (BC-36-P)   owns: intent → (Budget, RagMode); pure function, no state
  Context Kernel   (BC-36-3)   owns: selection + assembly + truncation + RAG call (pure)
  CLI              (BC-36-7)   owns: IndexBuilder call + intent parse + format output + orchestration

Intent flow:
  QueryIntent → PolicyResolver.resolve() → NavigationPolicy { Budget + RagMode }   ← Policy Layer
  QueryIntent → to_navigation_intent() ONLY in spatial/adapter.py (BC-18 compat)

Policy:
  unit = chars (model-agnostic); approx_tokens = chars / 4 (runtime only, not invariant)
  RagPolicy dataclass REMOVED; ContextBudgeter REMOVED → both absorbed into PolicyResolver

Legacy:
  build_context.py = BC-CTX-LEGACY (session adapter, не граф-aware)
  ContextAssembler НЕ импортирует build_context.py (I-CTX-MIGRATION-1)
  Миграция: build_context.py → thin adapter поверх ContextAssembler (отдельная задача)

Invariants (Phase 36, round 1 — architectural review 2026-04-29):
  I-SI-READ-1              SpatialIndex.read_content() — единственный публичный accessor
  I-GRAPH-TYPES-1          Node/Edge независимы от SpatialNode/SpatialEdge
  I-GRAPH-META-1           project_node() использует ALLOWED_META_KEYS allowlist; unknown keys dropped
  I-GRAPH-PRIORITY-1       EDGE_KIND_PRIORITY — единственный источник Edge.priority; self-assign запрещён
  I-GRAPH-EXTRACTOR-1      Каждый EdgeExtractor тестируется изолированно
  I-GRAPH-EXTRACTOR-2      Каждый EdgeExtractor.extract() не вызывает open()
  I-GRAPH-FACTS-ESCAPE-1   GraphFacts (nodes+edges) не утекает из GraphFactsBuilder.build()
  I-GRAPH-CACHE-2          fingerprint = sha256(snapshot_hash + SCHEMA_VERSION + extractor_hashes)
  I-GRAPH-FINGERPRINT-1    extractor_hashes автоматически инвалидируют кэш; SCHEMA_VERSION = last resort
  I-GRAPH-SERVICE-1        Только GraphService вызывает GraphCache и GraphFactsBuilder напрямую
  I-GRAPH-SUBSYSTEM-1      Graph Subsystem публичный API = get_or_build(); внутренние детали не экспортируются
  I-RANKED-NODE-BP-1       global_importance_score = global scope (все входящие рёбра в графе)
  I-INTENT-CANONICAL-1     QueryIntent — единственный canonical intent в BC-36
  I-INTENT-HEURISTIC-1     parse_query_intent выдаёт только RESOLVE_EXACT/INVARIANT/SEARCH
  I-POLICY-RESOLVER-1      PolicyResolver — единственный источник intent → (Budget, RagMode) [BC-36-P]
  I-POLICY-LAYER-1         PolicyResolver импортируется ТОЛЬКО в entry point Context Kernel [BC-36-P]
  I-POLICY-LAYER-PURE-1    PolicyResolver — pure function без side effects и I/O [BC-36-P]
  I-ENGINE-PURE-1          ContextEngine.query() без I/O, кэша, PolicyResolver, IndexBuilder
  I-ENGINE-POLICY-1        policy.budget → ContextAssembler; policy.rag_mode → LightRAGProjection
  I-CONTEXT-KERNEL-INPUT-1 ContextEngine получает готовые DeterministicGraph + NavigationPolicy
  I-RUNTIME-BOUNDARY-1     ContextRuntime — единственная точка входа в Context Kernel для CLI
  I-ARCH-MODEL-1           Единственный runtime Kernel — Context Kernel; Graph и Policy — не Kernels
  I-ARCH-MODEL-2           Context Kernel НЕ инициирует построение графа или вычисление policy
  I-CONTEXT-EXPLAIN-KIND-1 EXPLAIN→TRACE fallback: effective_intent=TRACE, intent_transform_reason non-None
  I-DOC-CHUNK-BOUNDARY-1  ContentMapper использует line_start/line_end как границы среза
  I-RAG-CLIENT-ISOLATION-1 LightRAGClient в query() — stateless или ephemeral; KG-накопитель запрещён
  I-CTX-MIGRATION-1        ContextAssembler не импортирует build_context.py
  I-CTX-MIGRATION-2        BC-36 модули не вызывают build_context.py
  I-CTX-MIGRATION-3        Прямое чтение CLAUDE.md/TaskSet.md/glossary.yaml — только в build_context.py
  I-CTX-MIGRATION-4        Import boundary enforced by tooling (import-linter или package isolation)
  I-LEGACY-FS-EXCEPTION-1  build_context.py MAY read filesystem — временное исключение Phase 36

Invariants (Phase 36, round 2 — agent integration grill-me 2026-04-29):
  I-SEARCH-CANDIDATE-1     SEARCH возвращает SearchCandidate (label+summary+kind); RankedNode в SEARCH запрещён
  I-SEARCH-NO-EMBED-1      SEARCH fuzzy_score = lexical/structural only; embedding similarity запрещён
  I-DOC-REFS-1             DocumentChunk.references — только валидные node_id из графа; broken dropped
  I-CONTEXT-EXHAUSTED-1    selection_exhausted=True iff BFS не может расшириться; False иначе
  I-CONTEXT-BUDGET-EXHAUST-1 selection_exhausted=True → partial context + warning; BUDGET_EXCEEDED только если 0 non-seed nodes
  I-CONTEXT-ORDER-1        Document ordering = stable (node_id rank, kind, hash); не BFS-transient
  I-CONTEXT-LINEAGE-1      context_id = sha256(snapshot_hash + seed + intent); graph_snapshot_hash в Context
  I-GRAPH-LINEAGE-1        DeterministicGraph.source_snapshot_hash = SpatialIndex.snapshot_hash при build
  I-GRAPH-FS-ROOT-1        Только SpatialIndex MAY access filesystem; все остальные через read_content()
  I-GRAPH-META-DEBUG-1     debug mode логирует dropped_meta_keys; production — WARNING если непустые
  I-NAV-RESPONSE-1         rag_summary отдельное поле; не смешивается с context.documents
  I-RAG-NO-PERSISTENCE-1   LightRAGClient в query() = zero state persistence (no cache, no KG, no memory)
  I-CLI-FORMAT-1           --format json → NavigationResponse JSON; --format text → markdown
  I-CLI-ERROR-CODES-1      BC-36 error_type: NOT_FOUND|GRAPH_NOT_BUILT|INVARIANT_VIOLATION|BUDGET_EXCEEDED|INTERNAL_ERROR
  I-TOOL-DEF-1             Tool definitions соответствуют CLI контракту; изменение = breaking change
  I-AGENT-1..7             Правила работы агента (§3.2): no direct file read, fallback handling,
                           stopping via selection_exhausted, references chain, rag boundary,
                           error handling, session budget = harness responsibility
```
