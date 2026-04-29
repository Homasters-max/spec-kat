# Spec_v51 — Phase 51: Context Kernel + Policy Layer (EXECUTION SHIFT)

**Status:** Draft
**Supersedes:** Spec_v36_2 (Phase 36 ARCHIVED — superseded by Phase 50+51+52)
**Baseline:** Spec_v36_2_GraphNavigation.md §BC-36-3, §BC-36-P, §BC-36-5
**Depends on:** Phase 50 DoD полностью выполнен
**Session:** DRAFT_SPEC 2026-04-29 — разбивка Phase 36 на 50/51/52

**Цель:** Pure-functional `sdd.context_kernel` + `sdd.policy`. Никакого CLI. LightRAG = stub (Protocol + graceful degradation).

**Risk fixes в этой фазе:** R-RUNTIME-CONTRADICTION, R-LIGHTRAG-COUPLING, R-FUZZY-ALGO

---

## 0. Архитектурная модель (Phase 51 scope)

```text
                    ┌─────────────────────────────────────────────────┐
                    │  Graph Subsystem (Phase 50, frozen)              │
                    │  GraphService.get_or_build() → DeterministicGraph│
                    └─────────────────────┬───────────────────────────┘
                                          │ DeterministicGraph
                                          ▼
                    ┌─────────────────────────────────────────────────┐
                    │  Context Kernel  (BC-36-3)                       │
                    │  ContextEngine.query(graph, policy, index, id)   │
                    │  Получает inputs готовыми — нет I/O              │
                    └─────────────────────────────────────────────────┘
                                          ▲
                                          │ NavigationPolicy
                    ┌─────────────────────────────────────────────────┐
                    │  Policy Layer  (BC-36-P)                         │
                    │  PolicyResolver.resolve(intent) → NavigationPolicy│
                    │  Pure function. Без состояния.                   │
                    └─────────────────────────────────────────────────┘
```

**Runtime sequence (Phase 51, без CLI):**
```text
1. index    = IndexBuilder.build()                              (внешний вызов)
2. graph    = GraphService.get_or_build(index)                  (Phase 50)
3. intent   = parse_query_intent(raw_query)                     (Phase 51)
4. policy   = PolicyResolver.resolve(intent)                    (Phase 51)
5. response = ContextRuntime.query(graph, policy, index, id)    (Phase 51)
```

**Запрещённые пересечения:**

| Уровень | НЕ МОЖЕТ использовать |
|---|---|
| Graph Subsystem | intent, budget, RagMode, Context Kernel |
| Policy Layer | DeterministicGraph, traversal, GraphService, cache |
| Context Kernel | GraphService.build(), PolicyResolver.resolve() |

**Phase Isolation Rule (I-PHASE-ISOLATION-1):**
- Phase 51 не изменяет публичный API `sdd.graph` (Node, Edge, DeterministicGraph, GraphService)
- Phase 51 не добавляет intent/budget-логику в `GraphService` или `GraphFactsBuilder`
- `sdd.context_kernel` не импортирует из `sdd.graph_navigation`
- `sdd.policy` не импортирует из `sdd.context_kernel`
- Проверяется `test_import_direction_phase51`

**Стабильный интерфейс для Phase 52:**
```python
from sdd.context_kernel import (ContextEngine, ContextRuntime, NavigationResponse,
                                 QueryIntent, parse_query_intent, SearchCandidate,
                                 Context, DocumentChunk, LightRAGClient, LightRAGProjection)
from sdd.policy import PolicyResolver, NavigationPolicy, Budget, RagMode
```

---

## 1. BC-36-P: Policy Layer

### Назначение

Policy Layer — изолированная pure функция `QueryIntent → NavigationPolicy`. Единственная ответственность: определить бюджет и RAG-режим для данного intent. Без состояния, без знания о структуре графа, traversal, cache.

### Типы

```python
MIN_CONTEXT_SIZE: int = 256  # policy/types.py; min chars for non-empty context (I-CONTEXT-BUDGET-VALID-1)

@dataclass
class Budget:
    max_nodes: int
    max_edges: int
    max_chars: int    # model-agnostic; approx_tokens = max_chars / 4 (runtime only)

    def __post_init__(self) -> None:
        if self.max_nodes < 1:
            raise ValueError(f"Budget.max_nodes must be ≥ 1, got {self.max_nodes}")
        if self.max_chars < MIN_CONTEXT_SIZE:
            raise ValueError(f"Budget.max_chars must be ≥ MIN_CONTEXT_SIZE ({MIN_CONTEXT_SIZE}), got {self.max_chars}")

class RagMode(Enum):
    OFF
    LOCAL
    GLOBAL
    HYBRID

@dataclass(frozen=True)
class NavigationPolicy:
    budget:   Budget
    rag_mode: RagMode
```

### PolicyResolver

```python
class PolicyResolver:
    """Pure mapping: QueryIntent → NavigationPolicy.
    Единственный источник intent → (Budget, RagMode) в системе.
    Не знает о DeterministicGraph, traversal, ContextEngine, GraphService.
    """
    _DEFAULT: dict[QueryIntent, NavigationPolicy] = {
        # v1: GLOBAL и HYBRID отключены (I-RAG-GLOBAL-V1-DISABLED-1)
        QueryIntent.RESOLVE_EXACT: NavigationPolicy(Budget(5,  10, 4000),  RagMode.OFF),
        QueryIntent.EXPLAIN:       NavigationPolicy(Budget(20, 40, 16000), RagMode.LOCAL),
        QueryIntent.TRACE:         NavigationPolicy(Budget(30, 60, 20000), RagMode.LOCAL),
        QueryIntent.INVARIANT:     NavigationPolicy(Budget(10, 20, 8000),  RagMode.OFF),
        QueryIntent.SEARCH:        NavigationPolicy(Budget(15, 0,  12000), RagMode.LOCAL),
    }

    def resolve(self, intent: QueryIntent) -> NavigationPolicy:
        """Детерминированное разрешение. Вызывается ровно один раз в ContextRuntime.query()."""
```

### Инварианты

- **I-POLICY-RESOLVER-1**: `PolicyResolver.resolve()` MUST be the single source of truth for `intent → (Budget, RagMode)` mapping. `ContextAssembler` и `LightRAGProjection` MUST NOT call `PolicyResolver` directly.
- **I-POLICY-LAYER-1**: `PolicyResolver` MUST be imported ONLY в точке входа Context Kernel (`ContextRuntime.query()` или CLI handler).
- **I-POLICY-LAYER-PURE-1**: `PolicyResolver` MUST be a pure function без side effects, без I/O, без state.

---

## 2. BC-36-3: ContextEngine

### 2.1 Architecture Model

**I-ARCH-MODEL-1**: В системе существует ровно один runtime Kernel — Context Kernel. Graph Subsystem и Policy Layer не являются Kernels.

**I-ARCH-MODEL-2**: Context Kernel НЕ инициирует построение графа или вычисление policy. Оба inputs (DeterministicGraph, NavigationPolicy) приходят в Context Kernel готовыми.

### 2.2 QueryIntent

```python
class QueryIntent(Enum):
    RESOLVE_EXACT  # точный id (COMMAND:complete)
    SEARCH         # structured uncertainty: возвращает N кандидатов без выбора
    EXPLAIN        # объяснить, как что-то работает (kind-aware)
    TRACE          # проследить связи (обычно reverse)
    INVARIANT      # навигация по инварианту

def parse_query_intent(query: str) -> QueryIntent:
    """
    RESOLVE_EXACT: query вида NAMESPACE:ID
    INVARIANT:     query вида I-NNN
    иначе:         SEARCH
    MUST NOT infer EXPLAIN or TRACE от keyword heuristics (I-INTENT-HEURISTIC-1).
    """
```

**I-INTENT-CANONICAL-1**: `QueryIntent` MUST be the single canonical intent type. `NavigationIntent` MUST NOT appear in `ContextEngine`, `ContextAssembler`, `DocProvider`. Conversion to `NavigationIntent` allowed ONLY in `spatial/adapter.py`.

**I-INTENT-HEURISTIC-1**: `parse_query_intent()` output MUST be one of `{RESOLVE_EXACT, INVARIANT, SEARCH}`. `EXPLAIN` и `TRACE` устанавливаются только CLI-маршрутизацией.

**I-INTENT-SOURCE-OF-TRUTH-1**: Единственный источник `QueryIntent` в системе:
- для `explain` / `trace` / `invariant`: CLI-команда → фиксированный intent (100%).
- для `resolve`: `parse_query_intent(raw_query)`.

`PolicyResolver.resolve(intent)` НЕ может изменять или уточнять intent. Его единственный выход — `NavigationPolicy(budget, rag_mode)` для уже установленного `QueryIntent`. Нарушение: любой код, изменяющий intent после `parse_query_intent()`, кроме explicit EXPLAIN→TRACE fallback в `ContextEngine._build_selection()` (закрыт I-CONTEXT-EXPLAIN-KIND-1).

### 2.3 RankedNode, RankedEdge, Selection

```python
@dataclass(frozen=True)
class RankedNode:
    node_id:                 str
    hop:                     int
    global_importance_score: float   # max(priority) по ВСЕМ входящим рёбрам в DeterministicGraph (I-RANKED-NODE-BP-1)

@dataclass(frozen=True)
class RankedEdge:
    edge_id:  str
    src:      str
    dst:      str
    hop:      int
    priority: float

@dataclass
class Selection:
    seed:  str                      # node_id seed-узла (immutable anchor)
    nodes: dict[str, RankedNode]
    edges: dict[str, RankedEdge]
```

**I-RANKED-NODE-BP-1**: `RankedNode.global_importance_score` MUST be `max(priority)` over ALL incoming edges of `dst` in `DeterministicGraph` (global scope), not only edges present in the current BFS Selection.

**BFS (каноническая):**
```python
BFS_OVERSELECT_FACTOR = 3  # policy/types.py; BFS останавливается по max_nodes * factor

queue = deque([(seed_node_id, 0)])
nodes[seed_node_id] = RankedNode(seed_node_id, hop=0, global_importance_score=1.0)
while queue:
    node_id, hop = queue.popleft()
    if len(nodes) >= budget.max_nodes * BFS_OVERSELECT_FACTOR:
        break  # I-BFS-BUDGET-1: early-stop prevents O(N) traversal on large graphs
    for edge in expand(graph, node_id, strategy, hop):
        dst = edge.dst
        if dst not in nodes or hop+1 < nodes[dst].hop:
            bp = max(e.priority for e in graph.edges_in.get(dst, [edge]))
            nodes[dst] = RankedNode(dst, hop+1, bp)
            edges[edge.edge_id] = RankedEdge(edge.edge_id, edge.src, dst, hop+1, edge.priority)
            queue.append((dst, hop+1))
```

**I-BFS-BUDGET-1**: BFS MUST stop early when `len(nodes) >= budget.max_nodes * BFS_OVERSELECT_FACTOR`. This prevents O(N) full-graph traversal when budget is small. `BFS_OVERSELECT_FACTOR = 3` is a module-level constant in `policy/types.py`. Seed node is always expanded regardless of this limit (I-CONTEXT-SEED-1). SEARCH intent (max_edges=0) is exempt: BFS runs only over nodes, no edge expansion.

**Стратегии selection:**

- **RESOLVE_EXACT**: seed + все рёбра (out+in) hop=1 + endpoints
- **EXPLAIN** *(kind-aware)*: out-edges `{emits, guards, implements, tested_by}`; S1=∅ → TRACE fallback + warning; если seed.kind==TASK добавляются in-edges `{depends_on}`
- **TRACE**: reverse_neighbors(seed) hop≤2
- **INVARIANT**: out-edges `{verified_by, introduced_in}`
- **SEARCH** *(structured uncertainty)*: ranked list[SearchCandidate], BM25 fuzzy score (R-FUZZY-ALGO fix)

**SearchCandidate:**
```python
@dataclass(frozen=True)
class SearchCandidate:
    node_id:     str
    kind:        str
    label:       str
    summary:     str
    fuzzy_score: float  # BM25 over (label + " " + summary) corpus (I-SEARCH-NO-EMBED-1)
```

**I-SEARCH-CANDIDATE-1**: SEARCH MUST return `SearchCandidate`, not `RankedNode`.

**I-SEARCH-AUTO-EXACT-1**: If SEARCH returns exactly one `SearchCandidate`, `ContextEngine._build_selection()` MUST automatically upgrade intent to `RESOLVE_EXACT` and build a full selection for that node. `NavigationResponse.candidates` MUST still contain the single candidate for transparency. This logic lives exclusively in `ContextEngine`, never in CLI handlers (I-RUNTIME-ORCHESTRATOR-1).
**I-SEARCH-NO-EMBED-1**: `fuzzy_score` MUST be computed via BM25 over `(label + " " + summary)` corpus. Embedding-based similarity FORBIDDEN (R-FUZZY-ALGO fix).

**Инварианты selection:**

- **I-CONTEXT-SELECT-1**: Selection для `(graph, start_node, intent)` детерминированна.
- **I-CONTEXT-SELECT-2**: Ни один узел из `Selection.nodes` нельзя удалить без нарушения стратегии.
- **I-CONTEXT-EXPLAIN-KIND-1**: EXPLAIN MUST check S1 emptiness; empty S1 → TRACE fallback + warning. `Context.effective_intent = TRACE`; `intent_transform_reason` non-None.

### 2.4 DocumentChunk и Context

```python
@dataclass
class DocumentChunk:
    node_id:    str
    content:    str
    kind:       str        # "code" | "invariant" | "task" | "doc"
    char_count: int
    meta:       dict
    references: list[str]  # node_id-ы в content (I-DOC-REFS-1)

@dataclass
class Context:
    intent:                  QueryIntent
    effective_intent:        QueryIntent
    intent_transform_reason: str | None
    nodes:                   list[Node]
    edges:                   list[Edge]
    documents:               list[DocumentChunk]
    budget_used:             dict
    selection_exhausted:     bool           # True если BFS не может расшириться (I-CONTEXT-EXHAUSTED-1)
    graph_snapshot_hash:     str
    context_id:              str            # sha256(graph_snapshot_hash + seed_node_id + intent.value)[:32]
```

**DocProvider:**
```python
class ContentMapper(Protocol):
    def extract_chunk(self, node: SpatialNode, content: str) -> str:
        """FILE + line_start/line_end → slice; FILE без → whole file; non-FILE → ""."""
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
    def __init__(self, index: SpatialIndex, mapper: ContentMapper = DefaultContentMapper()): ...
    def get_chunks(self, node_ids: list[str]) -> list[DocumentChunk]: ...
```

**I-DOC-CHUNK-BOUNDARY-1**: `ContentMapper.extract_chunk()` MUST use `line_start/line_end`. Direct inline string slicing in `DocProvider` forbidden.

**I-DOC-REFS-1**: `DocumentChunk.references` MUST contain only `node_id`-ы из `DeterministicGraph.nodes`. Broken references dropped.

**I-DOC-SI-ONLY-1**: `SpatialIndex` is the single source of file metadata (paths, line bounds, kind). `DocProvider` resolves file paths from `SpatialIndex` and reads actual content from the filesystem. CLAUDE.md, TaskSet.md, glossary.yaml MUST NOT be read directly outside `build_context.py` (I-CTX-MIGRATION-3).

**I-DOC-FS-IO-1**: `DocProvider.get_chunks()` is the SINGLE point of filesystem I/O in Context Kernel. `ContextEngine`, `ContextAssembler`, and `LightRAGProjection` MUST NOT open files directly. Enforced by grep-test: no `open(` calls outside `DocProvider`.

**I-DOC-NON-FILE-1**: For non-FILE nodes (`COMMAND`, `EVENT`, `TASK`, `INVARIANT`, `TERM`): `DefaultContentMapper.extract_chunk()` returns `""`. `DocumentChunk.content = ""`, `char_count = 0`. These chunks are included in `documents` list for reference resolution (I-DOC-REFS-1) but do NOT consume char budget. Implementors MUST NOT synthesize content for non-FILE nodes — absence of content is intentional.

**I-DOC-2**: Chunk extraction для FILE-узлов MUST be deterministic (AST-based).

**I-CONTEXT-EXHAUSTED-1**: `Context.selection_exhausted = True` iff BFS cannot further expand.

### 2.5 ContextAssembler

```python
class ContextAssembler:
    def build(self,
              graph: DeterministicGraph,
              selection: Selection,
              budget: Budget,
              doc_provider: DocProvider) -> Context:
        """
        1. seed всегда включён (I-CONTEXT-SEED-1).
        2. nodes/edges сортируются по (hop ASC, -global_importance_score, node_id ASC).
        3. Берётся prefix до max_nodes / max_edges.
        4. docs через doc_provider.get_chunks(node_ids).
        5. docs сортируются по (node_rank[node_id], kind, hash(content)).
        6. Prefix пока Σ char_count ≤ max_chars.
        """
```

**I-CONTEXT-BUDGET-1**: `len(nodes) ≤ max_nodes`, `len(edges) ≤ max_edges`, `Σ char_count(documents) ≤ max_chars`.

**I-CONTEXT-BUDGET-VALID-1**: `Budget` MUST satisfy `max_nodes ≥ 1` и `max_chars ≥ MIN_CONTEXT_SIZE` (константа в `policy/types.py`). Violation при создании `Budget` → `ValueError`. Защищает от пустых контекстов и неконсистентных ответов. `PolicyResolver._DEFAULT` MUST pass this validation at import time (static assert).

**I-CONTEXT-TRUNCATE-1**: Deterministic ordering: `(hop ASC, -global_importance_score, node_id ASC)` для nodes; `(hop ASC, -priority, edge_id ASC)` для edges; `(node_rank, kind, hash(content))` для documents.

**I-CONTEXT-SEED-1**: Seed node MUST always be present regardless of budget.

**I-CONTEXT-ORDER-1**: Document ordering MUST depend only on stable `(node_id rank, kind, hash(content))`.

**I-CONTEXT-LINEAGE-1**: `Context.graph_snapshot_hash` MUST equal `DeterministicGraph.source_snapshot_hash`. `Context.context_id` computation:
- For all intents except SEARCH: `sha256(graph_snapshot_hash + ":" + seed_node_id + ":" + intent.value)[:32]`
- For SEARCH: `sha256(graph_snapshot_hash + ":SEARCH:" + sha256(raw_query.encode())[:16])[:32]`

`raw_query` MUST be passed through to `ContextAssembler.build()` when intent is SEARCH. For non-SEARCH, `raw_query` is never used in `context_id`. Rationale: SEARCH has no single seed node; caching by query text prevents `context_id` collisions between different SEARCH queries on the same snapshot.

**I-CONTEXT-DETERMINISM-1**: Context MUST be identical for same `(graph, query, budget)`.

### 2.6 LightRAGClient Protocol (R-LIGHTRAG-COUPLING fix)

```python
class LightRAGClient(Protocol):
    """Structural typing (Protocol) — не требует lightrag installed (R-LIGHTRAG-COUPLING fix)."""
    def query(self, question: str, context: list[DocumentChunk], mode: str) -> str: ...
    def insert_custom_kg(self, kg: dict) -> None: ...

@dataclass
class RAGResult:
    """Результат LightRAG query. Изолирован от Context."""
    summary:  str
    rag_mode: str   # фактически использованный режим: "LOCAL"|"GLOBAL"|"HYBRID"

@dataclass
class NavigationResponse:
    """Полный ответ. Явная граница fact vs inference."""
    context:     Context
    rag_summary: str | None              # None если RAG=OFF
    rag_mode:    str | None              # "LOCAL"|"HYBRID"|"GLOBAL"|None; фактический режим
    candidates:  list[SearchCandidate] | None  # non-None только для QueryIntent.SEARCH (I-SEARCH-RESPONSE-1)

class LightRAGProjection:
    """Canonical implementation. Lives in sdd.context_kernel.rag_types — единственный класс.
    Phase 52 НЕ создаёт новый класс; только добавляет LightRAGRegistry как __init__ dependency.
    query() сигнатура НЕИЗМЕННА между фазами (I-LIGHTRAG-CANONICAL-1).
    """
    def __init__(self, registry: "LightRAGRegistry | None" = None): ...
    # registry=None допустимо в Phase 51 (stub mode); Phase 52 передаёт реальный LightRAGRegistry.

    def query(self, question: str, context: Context,
              rag_mode: RagMode, rag_client: "LightRAGClient | None") -> "RAGResult | None":
        if rag_client is None:
            return None  # graceful degradation
        ...
```

**I-NAV-RESPONSE-1**: `rag_summary` MUST NOT be mixed into `context.documents`.

**I-SEARCH-RESPONSE-1**: For `QueryIntent.SEARCH`: `NavigationResponse.candidates` MUST be non-None and contain the ranked `list[SearchCandidate]`. `NavigationResponse.context.nodes` MUST contain only the seed node (or empty if no seed is applicable). For all other intents: `candidates` MUST be `None`. `ContextEngine._build_selection()` MUST NOT return `SearchCandidate` inside `Selection.nodes`.

**I-SEARCH-MAX-EDGES-1**: For `QueryIntent.SEARCH`, `Budget.max_edges = 0` is valid. `ContextAssembler.build()` MUST treat `max_edges = 0` as "include no edges" — not as an error. `Selection.edges` remains empty; `Context.edges` is `[]`.

**I-RAG-POLICY-1**: `rag_mode=RagMode.OFF` → LightRAG не вызывается. `rag_mode=RagMode.LOCAL` → LightRAG вызывается только с `Context.documents`, без KG. `rag_mode=RagMode.GLOBAL` или `HYBRID` → требует предварительно построенного KG (Phase 52 `LightRAGRegistry`).

**I-RAG-GROUNDING-1**: Для `RagMode.LOCAL` — `rag_summary` MUST be based only on provided `Context.documents`. Для `RagMode.GLOBAL` и `HYBRID` — LightRAG MAY use pre-built KG; `rag_summary` является KG-augmented inference и MUST быть отмечен как таковой в `NavigationResponse.rag_mode`. Агент MUST применять `I-AGENT-5` (`rag_summary` = inference, не факт) строго к GLOBAL/HYBRID ответам.

**I-RAG-KG-DEPENDENCY-1**: `RagMode.LOCAL` НЕ требует предварительного KG-экспорта. `RagMode.GLOBAL` и `HYBRID` требуют валидного KG в `LightRAGRegistry` (fingerprint совпадает с `graph_fingerprint`). Отсутствие KG при GLOBAL/HYBRID → деградация к `LOCAL` (не OFF) + warning в stderr.

**I-RAG-DETACH-1**: LightRAG MUST NOT access global knowledge graph during LOCAL-mode query.

**I-RAG-CLIENT-ISOLATION-1**: `LightRAGClient` used in `query()` MUST be stateless with respect to previously inserted KG data.

**I-RAG-NO-PERSISTENCE-1**: `LightRAGClient` used in `query()` MUST NOT persist any state across calls.

**I-RAG-NONDETERMINISTIC-1**: `NavigationResponse.rag_summary` является недетерминированным (LLM inference). `Context` (nodes, edges, documents) — детерминирован и является единственной truth. `rag_summary` — interpretation layer поверх `Context`. Система разделена на:
- **Deterministic core**: `Context = f(snapshot_hash, query)` — полностью воспроизводим, тестируем без моков LLM.
- **Non-deterministic layer**: `rag_summary = g(Context)` — опциональный, изолирован от ядра.

Следствие: replayability, дебажимость и testability гарантированы для ядра независимо от наличия LightRAG.

**I-RAG-LLM-CONFIG-1**: `LightRAGClient` MUST be initialized with `temperature=0` (or the equivalent determinism parameter of the underlying model). This is a mandatory construction-site requirement enforced at instantiation, not a type-level constraint. Enforced by: integration test that calls `LightRAGProjection.query()` twice with identical `(question, context, mode)` and asserts `rag_summary` equality.

**I-LIGHTRAG-CANONICAL-1**: `LightRAGProjection` in `sdd.context_kernel.rag_types` is the single canonical class. Phase 52 MUST NOT define a second `LightRAGProjection` in `sdd.graph_navigation`. Phase 52 extends it via `__init__(registry)` injection only. `ContextEngine` always imports from `sdd.context_kernel`. Enforced by grep-test: `class LightRAGProjection` appears in exactly one file.

**I-RAG-EXPLAINABILITY-1**: `Context` обеспечивает 100% explainability — любой ответ раскладывается в nodes + edges + document chunks. `rag_summary` — interpretation, explainability для него не требуется. Агент MUST применять `I-AGENT-5` при работе с `rag_summary`.

### 2.7 ContextEngine — pure pipeline

```python
class ContextEngine:
    """Pure pipeline: (DeterministicGraph, NavigationPolicy, DocProvider) → NavigationResponse.
    Нет зависимостей на I/O, SpatialIndex, GraphService, GraphCache, PolicyResolver.
    """
    def __init__(
        self,
        assembler:      ContextAssembler,
        rag_projection: "LightRAGProjection | None" = None,
    ): ...

    def query(
        self,
        graph:        DeterministicGraph,
        policy:       NavigationPolicy,    # уже resolved внешним вызовом PolicyResolver.resolve()
        doc_provider: DocProvider,         # создан вне ContextEngine (в ContextRuntime)
        node_id:      str,
        rag_client:   "LightRAGClient | None" = None,  # прокинут из ContextRuntime
    ) -> NavigationResponse:
        """
        1. selection = _build_selection(graph, node_id, policy)
        2. context = assembler.build(graph, selection, policy.budget, doc_provider)
        3. rag_result = rag_projection.query(node_id, context, policy.rag_mode, rag_client)
               if rag_projection and policy.rag_mode != RagMode.OFF else None
        4. return NavigationResponse(
               context,
               rag_summary=rag_result.summary if rag_result else None,
               rag_mode=rag_result.rag_mode if rag_result else None,
               candidates=None,  # non-None only for SEARCH (set in step 1)
           )
        """
```

**I-ENGINE-PURE-1**: `ContextEngine.query()` MUST NOT call `IndexBuilder`, `GraphService`, `GraphCache`, `PolicyResolver`, or any filesystem API.

**I-ENGINE-INPUTS-1**: `ContextEngine.query(graph, policy, doc_provider, seed)` НЕ принимает `SpatialIndex` напрямую. Вся работа с файловым контентом — ответственность `DocProvider`. `DocProvider` создаётся вне `ContextEngine` (в `ContextRuntime`). `ContextEngine` MUST NOT import `SpatialIndex` — grep-тест.

**I-ENGINE-POLICY-1**: `policy.budget` передаётся в `ContextAssembler`; `policy.rag_mode` в `LightRAGProjection`. Ни тот ни другой не получают `NavigationPolicy` напрямую.

### 2.8 ContextRuntime — lifecycle orchestrator (R-RUNTIME-CONTRADICTION fix)

```python
# Module-level default; allows Phase 52 CLI to instantiate ContextRuntime without custom wiring.
_default_doc_provider_factory: Callable[[SpatialIndex], DocProvider] = (
    lambda index: DocProvider(index, DefaultContentMapper())
)

class ContextRuntime:
    """Entry point to Context Kernel. Создаёт DocProvider из SpatialIndex.
    НЕ держит GraphService — граф строится в CLI до вызова query().  ← R-RUNTIME-CONTRADICTION fix
    Держит rag_client — инжектируется при инстанциировании, не при каждом query().
    """
    def __init__(
        self,
        engine:               ContextEngine,
        doc_provider_factory: Callable[[SpatialIndex], DocProvider] = _default_doc_provider_factory,
        rag_client:           "LightRAGClient | None" = None,
    ): ...
    # rag_client прокидывается в LightRAGProjection.query() через ContextEngine._rag_projection

    def query(
        self,
        graph:   DeterministicGraph,  # построен Graph Subsystem-ом (CLI step 2)
        policy:  NavigationPolicy,    # resolved Policy Layer-ом (CLI step 4)
        index:   SpatialIndex,
        node_id: str,
    ) -> NavigationResponse:
        """
        doc_provider = self._doc_provider_factory(index)
        return self._engine.query(graph, policy, doc_provider, node_id, rag_client=self._rag_client)
        """
```

**I-RUNTIME-BOUNDARY-1**: CLI commands MUST call `ContextRuntime.query()` and MUST NOT call `ContextEngine.query()` directly. `ContextRuntime` MUST NOT import `GraphService` — это grep-тест. (R-RUNTIME-CONTRADICTION fix: "ContextRuntime не держит GraphService" — единственно верная интерпретация инварианта.)

**I-RUNTIME-ORCHESTRATOR-1**: `ContextRuntime.query(graph, policy, index, node_id)` — единственная точка входа в Context Kernel для ВСЕХ внешних рантаймов (CLI, HTTP, agent). CLI handler MUST NOT содержать бизнес-логику сверх: разбора CLI-аргументов, вызова `IndexBuilder.build()` + `GraphService.get_or_build()`, вызова `parse_query_intent()` + `PolicyResolver.resolve()`, вызова `ContextRuntime.query()`, форматирования и вывода `NavigationResponse`, генерации `error_type` при исключении. Любая стратегия выбора, сборки контекста, ранжирования — исключительная ответственность Context Kernel.

**I-CONTEXT-KERNEL-INPUT-1**: `ContextEngine.query()` MUST receive `DeterministicGraph`, `NavigationPolicy`, и `DocProvider` как готовые параметры. Violation: любой вызов `GraphService`, `PolicyResolver`, или создание `DocProvider` внутри `ContextEngine`.

---

## 3. BC-36-5: Legacy Context Migration (инварианты)

**I-CTX-MIGRATION-1**: `ContextAssembler` MUST NOT import from `context/build_context.py`.

**I-CTX-MIGRATION-2**: `build_context.py` MUST NOT be called from любого BC-36 модуля.

**I-CTX-MIGRATION-3**: Прямое чтение CLAUDE.md, TaskSet.md, glossary.yaml допустимо ТОЛЬКО внутри `build_context.py`.

**I-CTX-MIGRATION-4**: Import boundary MUST be enforced by tooling (import-linter или CI gate). Grep-tests остаются как second-layer check.

**I-LEGACY-FS-EXCEPTION-1**: `build_context.py` MAY read filesystem directly ONLY during Phase 36 migration window. Window остаётся открытым в Phase 51. Закрывается в Phase 52 `migration_complete()`.

---

## 4. spatial/adapter.py

```python
# src/sdd/spatial/adapter.py
def to_navigation_intent(intent: QueryIntent, node_kind: str | None = None) -> "NavigationIntent":
    """Конверсия QueryIntent → NavigationIntent для backward compat с BC-18 Navigator.
    Живёт на шве (spatial/adapter.py), не в CLI и не в ContextEngine.
    """
```

---

## 5. Новые файлы

```
src/sdd/policy/__init__.py
src/sdd/policy/types.py            — Budget, NavigationPolicy (frozen), RagMode
src/sdd/policy/resolver.py         — PolicyResolver._DEFAULT (5 intents), resolve()
src/sdd/context_kernel/__init__.py
src/sdd/context_kernel/intent.py   — QueryIntent (Enum), parse_query_intent(), SearchCandidate
src/sdd/context_kernel/selection.py — RankedNode, RankedEdge, Selection, _build_selection() (BFS)
src/sdd/context_kernel/documents.py — DocumentChunk, ContentMapper (Protocol), DefaultContentMapper, DocProvider
src/sdd/context_kernel/context_types.py — Context
src/sdd/context_kernel/assembler.py — ContextAssembler (deterministic truncation + document ordering)
src/sdd/context_kernel/rag_types.py — LightRAGClient (Protocol!), LightRAGProjection (stub), NavigationResponse
src/sdd/context_kernel/engine.py   — ContextEngine (pure)
src/sdd/context_kernel/runtime.py  — ContextRuntime (thin wrapper над ContextEngine только)
src/sdd/spatial/adapter.py         — to_navigation_intent() (BC-18 compat)
tests/unit/policy/test_resolver.py
tests/unit/context_kernel/test_intent.py
tests/unit/context_kernel/test_selection.py
tests/unit/context_kernel/test_assembler.py
tests/unit/context_kernel/test_doc_provider.py
tests/unit/context_kernel/test_engine.py
tests/unit/context_kernel/test_runtime.py
tests/unit/spatial/test_adapter.py
```

---

## 6. Verification

### Unit tests

**QueryIntent / Canonical Layer:**

13. `test_query_intent_parse_all_forms`
14. `test_to_navigation_intent_conversion` — I-INTENT-CANONICAL-1.
15. `test_context_engine_uses_query_intent_only` — grep-тест: ContextEngine не импортирует NavigationIntent.

**ContextEngine / Selection:**

16. `test_ranked_selection_bfs`
17. `test_context_selection_resolve/explain/trace/invariant`
18. `test_explain_kind_aware_fallback` — I-CONTEXT-EXPLAIN-KIND-1.
19. `test_context_truncation_deterministic`
20. `test_context_seed_always_present`
21. `test_context_budget_chars`
22. `test_context_budget_per_intent` — PolicyResolver._DEFAULT покрывает все 5 QueryIntent.

**DocProvider / Migration:**

23. `test_doc_provider_si_only`
24. `test_context_assembler_no_build_context_import` — I-CTX-MIGRATION-1.

**RAG:**

25. `test_rag_export_mapping`
26. `test_rag_grounding`
27. `test_search_structured_uncertainty`

**Risk hardening:**

34. `test_global_importance_score_global_scope` — I-RANKED-NODE-BP-1.
35. `test_parse_query_intent_no_explain_trace` — I-INTENT-HEURISTIC-1.
36. `test_explain_fallback_context_fields`
37. `test_content_mapper_line_boundaries`
38. `test_doc_provider_uses_content_mapper`
39. `test_rag_client_is_stateless`
40. `test_ctx_migration_import_boundary`
41. `test_search_candidate_has_label_summary_kind`
42. `test_document_chunk_references_valid_node_ids`
43. `test_selection_exhausted_true_when_no_expansion`
44. `test_selection_exhausted_false_when_expandable`
45. `test_navigation_response_rag_summary_separate`
52. `test_context_id_deterministic`
53. `test_context_graph_snapshot_hash_matches_graph`
54. `test_document_order_stable_regardless_of_bfs_traversal_order`
55. `test_search_no_embeddings` — I-SEARCH-NO-EMBED-1 (BM25, no embeddings).
56. `test_rag_no_persistence`

**ContextRuntime import:**

`test_runtime_does_not_import_graph_service` — grep: `ContextRuntime` не импортирует `GraphService`. (R-RUNTIME-CONTRADICTION fix)

`test_engine_does_not_import_spatial_index` — I-ENGINE-INPUTS-1: grep: `ContextEngine` не импортирует `SpatialIndex`.

`test_runtime_creates_doc_provider_from_index` — `ContextRuntime.query()` вызывает `doc_provider_factory(index)` перед передачей в `ContextEngine.query()`.

**Import direction:**

`test_import_direction_phase51` — `sdd.context_kernel` не импортирует из `sdd.graph_navigation`; `sdd.policy` не импортирует из `sdd.context_kernel`.

### Integration tests (engine-level, без CLI)

INT-1..3, 6, 8, 10 — запускаются с mock graph + mock policy + mock index (no filesystem).

---

## 7. DoD Phase 51

1. `sdd.policy` и `sdd.context_kernel` importable, zero circular imports
2. Все 32 unit-тесты проходят
3. `ContextEngine` инстанциируем с mock graph + mock policy + mock index (нет filesystem)
4. `LightRAGClient` — Protocol; `LightRAGProjection` — stub без lightrag install; graceful degradation к OFF при `rag_client=None`
5. `ContextRuntime` не импортирует `GraphService` — grep-тест
6. `ContextAssembler` не импортирует `build_context.py` — test 24 + test 40
7. `PolicyResolver._DEFAULT` покрывает все 5 QueryIntent — test 22
8. `mypy --strict` проходит на `sdd.policy.*` и `sdd.context_kernel.*`
9. Все Phase 50 тесты не регрессируют
