# Spec_v58 — Module API Boundary & Calls Refinement

**Status:** DRAFT
**Depends on:** Phase 57 COMPLETE
**Revised:** 2026-04-30

**Motive:** Phase 57 создала SSOT граф с layer/BC инвариантами. MODULE nodes (Phase 55) —
пока только структурная группировка (cohesion count). Phase 58 даёт им поведенческую границу
(public API) и улучшает надёжность `calls` edges с 0.6 → 0.85, что разблокирует полноценный
layer enforcement через вызовы.

---

## 1. Scope

### In-Scope

| BC | Название | Приоритет |
|----|----------|-----------|
| BC-58-1 | MODULE API Boundary | Критический |
| BC-58-2 | calls Edge Refinement (AST Call nodes) | Критический |
| BC-58-3 | Arch Invariants as Graph Nodes | Критический |
| BC-58-4 | Graph Query DSL (MVP) | Средний |
| BC-58-5 | Hotspot Detection | Средний |
| BC-58-6 | graph-guard Coverage Report | Средний |
| BC-58-RAG | RAG Pipeline Hardening (EmbeddingProvider, EmbeddingCache, RAGRanker, hard enforcement) | Средний |

### Out of Scope

| Item | Owner |
|------|-------|
| Embedding-based search в `sdd resolve` (I-SEARCH-NO-EMBED-1) | Phase 59+ |
| DECOMPOSE/PLANNER адаптация (session FSM) | Другой домен |
| Cross-BC dependency matrix (аналитика) | Phase 59+ |
| Graph-level diff между фазами | Phase 59+ |
| calls confidence ≥ 0.9 → violation enforcement | Phase 59+ (после BC-58-2 поднимает до 0.85) |
| calls confidence ≥ 0.9 → RAG violations (I-ARCH-CONFIDENCE-1 threshold) | Phase 59+ |

---

## 2. BC-58-1: MODULE API Boundary

**Проблема (из aurora proposals Bug #6):** MODULE nodes — только структурная группировка.
Нет инварианта: файл в модуле может быть напрямую импортирован из любого места.
Нарушение инкапсуляции не видно в графе.

**Решение:** `module_public_api` edges + `sdd arch-check --check module-api-boundary`.

### Новые edge kinds

| Edge Kind | Priority | Направление | Confidence |
|-----------|----------|-------------|------------|
| `module_depends_on` | 0.67 | MODULE → MODULE | 1.0 |
| `module_public_api` | 0.65 | MODULE → FILE | 1.0 |

Вставляются между `cross_bc_dependency` (0.63) и `imports` (0.60) в EDGE_KIND_PRIORITY.

### Новые экстракторы

```
src/sdd/graph/extractors/module_api_edges.py   # ModulePublicAPIExtractor
src/sdd/graph/extractors/module_dep_edges.py   # ModuleDependsOnExtractor
```

**ModulePublicAPIExtractor:**
- Читает `__init__.py` каждого MODULE.
- Если `__all__` определён → public files = только экспортированные символы → FILE nodes.
- Если `__all__` отсутствует → fallback: все FILE nodes пакета считаются public.
- Pipeline stage: `classified` (после path-based classification, до derived).

**ModuleDependsOnExtractor:**
- Для каждой пары (MODULE:A, MODULE:B): если ∃ imports/calls edge из FILE в A к FILE в B → emit `MODULE:A → module_depends_on → MODULE:B`.
- Pipeline stage: `derived` (читает classified output, I-GRAPH-BUILD-PIPELINE-1).

### Инварианты

**I-MODULE-API-1:**
FILE:f ∈ MODULE:M доступно извне (external imports) только если M имеет
`module_public_api → f` edge. Прямой `imports` из FILE:g (module(g) ≠ M) к FILE:f,
где f ∉ public_api(M) → violation.
`sdd arch-check --check module-api-boundary` → exit 1 при нарушении.

**I-MODULE-API-2:**
`module_depends_on(A, B)` ↔ ∃ `imports`/`calls` edge из FILE в A к FILE в B.
Производное ребро, derived stage. Расхождение с imports graph → GraphInvariantError.

### Команды

```bash
sdd arch-check --check module-api-boundary [--format json|text]
→ {"violations": [{"src": "FILE:...", "dst": "FILE:...", "module": "MODULE:..."}]}
# exit 0 = no violations; exit 1 = violations found

sdd explain MODULE:sdd.graph --edge-types module_public_api
→ список public FILE nodes модуля

sdd explain MODULE:sdd.graph --edge-types module_depends_on
→ другие MODULE, от которых зависит sdd.graph
```

### sdd_config.yaml additions

```yaml
arch_check:
  enabled_checks:
    # ... existing ...
    - module-api-boundary   # NEW BC-58-1
```

---

## 3. BC-58-2: calls Edge Refinement

**Проблема:** Phase 56 calls extractor — эвристика по imports statements, confidence=0.6.
I-ARCH-CONFIDENCE-1 требует ≥ 0.9 для violations → calls не участвуют в arch enforcement.

**Решение:** анализ `ast.Call` nodes с explicit module-prefix qualifiers.

### Стратегия

```python
# Phase 56 подход (заменяется):
# "если файл импортирует из модуля X, X вероятно вызывает Y" → confidence=0.6

# Phase 58 подход:
# Парсим ast.Call nodes:
#   import foo; foo.bar() → calls edge src→file_of_foo, confidence=0.85
#   from foo import bar; bar() → calls edge src→file_of_bar, confidence=0.75
# Квалифицированный вызов (module.function) → confidence=0.85
# Неквалифицированный (from import) → confidence=0.75
```

### Изменения

```
src/sdd/graph/extractors/ast_edges.py   # CallsEdgeExtractor — полная замена логики
```

**EDGE_KIND_CONFIDENCE update:**
```python
"calls": 0.85  # Phase 58: up from 0.6 (Phase 56)
```

**Важно:** `I-ARCH-CONFIDENCE-1` threshold = 0.9. После Phase 58:
- `calls` confidence = 0.85 → ещё ниже порога → calls остаются warnings в arch-check.
- Phase 59+ может поднять до ≥ 0.9 после dynamic dispatch detection.

**Инвариант I-CALLS-PRECISION-1 (новый):**
`CallsEdgeExtractor` ДОЛЖЕН использовать `ast.Call` node analysis.
Прямой детект по imports statements запрещён (устаревший подход).
Qualified calls (module.function) → confidence=0.85; unqualified → confidence=0.75.

---

## 4. BC-58-3: Arch Invariants as Graph Nodes

**Проблема (aurora Arch #3):** Нарушения arch-check показывают FILE, нарушающий правило,
но не связывают нарушение с конкретным INVARIANT node в графе. `sdd explain INVARIANT:I-ARCH-2`
невозможен — таких nodes нет.

**Решение:** INVARIANT nodes + `enforced_by`/`violated_by` edges.

### Node kind: INVARIANT

```
node_id: INVARIANT:I-ARCH-1
kind: "INVARIANT"
label: "I-ARCH-1"
meta.description: "Layer N may import only from N-1 (direct adjacency)"
meta.spec_ref: "Spec_v57 §5"
meta.enforcement_command: "COMMAND:arch-check"
```

**Источник:** `INVARIANT_REGISTRY` в `src/sdd/commands/validate_invariants.py` + §5 спеков.
Первая реализация — статический список в конфиге или отдельном YAML.

### Новые edge kinds

| Edge Kind | Priority | Направление |
|-----------|----------|-------------|
| `violated_by` | 0.91 | FILE → INVARIANT |
| `enforced_by` | 0.88 | INVARIANT → COMMAND |

`violated_by` (0.91) вставляется между `emits` (0.95) и `guards` (0.90) — violations критичны.

### Новые файлы

```
src/sdd/graph/extractors/invariant_edges.py   # InvariantEdgeExtractor
.sdd/config/invariant_registry.yaml           # список инвариантов с meta
```

**InvariantEdgeExtractor:**
- Строит INVARIANT nodes из `invariant_registry.yaml`.
- Эмитирует `INVARIANT → enforced_by → COMMAND` edges (статические, из конфига).
- Эмитирует `FILE → violated_by → INVARIANT` edges по результатам последнего `arch-check` (из кеша).
- Pipeline stage: `classified`.

### Инварианты

**I-ARCH-NODES-1:**
Каждый инвариант в `invariant_registry.yaml` ДОЛЖЕН иметь соответствующий INVARIANT node
в графе. `sdd arch-check --check invariant-coverage` → exit 1 при отсутствии.

**I-ARCH-NODES-2:**
`violated_by` edges ДОЛЖНЫ отражать последнее состояние arch-check.
Если arch-check не запускался → `violated_by` edges отсутствуют (не ошибка).

### Использование

```bash
sdd explain INVARIANT:I-ARCH-2 --edge-types enforced_by,violated_by
→ {
    "enforced_by": [{"node": "COMMAND:arch-check"}],
    "violated_by": [{"node": "FILE:src/sdd/context_kernel/engine.py"}]
  }
# Граф объясняет, что нарушено и кем
```

---

## 5. BC-58-4: Graph Query DSL (MVP)

**Проблема (aurora Arch #1):** Комбинации `sdd explain`/`trace`/`resolve` громоздки.
LLM вынужден многократно вызывать CLI с разными флагами.

**Решение:** Минимальный DSL — `sdd query --dsl "..."`.

### DSL синтаксис (MVP)

```
FROM <node_id> EXPAND <edge_types> [TRACE <hops>] [FILTER <key>=<value>]

Примеры:
  FROM COMMAND:complete EXPAND implements,guards TRACE 2
  FROM INVARIANT:I-ARCH-2 EXPAND violated_by FILTER kind=FILE
  FROM MODULE:sdd.graph EXPAND contains,module_public_api
```

**Новый файл:**
```
src/sdd/graph_navigation/cli/query.py   # sdd query --dsl handler
src/sdd/graph/dsl_parser.py            # DSL tokenizer + AST
```

**I-DSL-1:** DSL parser MUST NOT call eval() или exec(). Только whitelist tokens.

---

## 6. BC-58-5: Hotspot Detection

**Проблема (aurora Arch #4):** Нет автоматической диагностики файлов с высокой coupling.

**Решение:** `sdd hotspot` — fan-in/fan-out метрики по графу.

```bash
sdd hotspot [--top N] [--format json|text]
→ файлы, ранжированные по fan_in + fan_out score

sdd hotspot --check cross-bc-density [--threshold 0.3]
→ BC пары с высокой density cross_bc_dependency edges
```

**Метрики:**
```python
fan_in(f)  = |in_edges(f, kind ∈ {imports, calls, depends_on})|
fan_out(f) = |out_edges(f, kind ∈ {imports, calls, depends_on})|
hotspot_score(f) = fan_in(f) * 0.6 + fan_out(f) * 0.4
```

**Новый файл:**
```
src/sdd/graph_navigation/cli/hotspot.py   # sdd hotspot handler
```

---

## 7. BC-58-6: graph-guard Coverage Report

**Из §10 Out of Scope Spec_v57.**

```bash
sdd graph-guard report --task T-NNN [--format json|text]
→ {
    "anchor_nodes": ["COMMAND:complete", "INVARIANT:I-HANDLER-PURE-1"],
    "covered": ["COMMAND:complete"],
    "uncovered": ["INVARIANT:I-HANDLER-PURE-1"],
    "coverage_pct": 50.0
  }
```

**Новый файл:**
```
src/sdd/graph_navigation/cli/guard_report.py   # sdd graph-guard report handler
```

**I-GRAPH-GUARD-REPORT-1:**
`sdd graph-guard report` ДОЛЖЕН использовать те же `covered_anchor_nodes` алгоритм,
что и `sdd graph-guard check` (I-GRAPH-GUARD-2, I-GRAPH-GUARD-3). Не отдельная реализация.

---

## BC-58-RAG: RAG Pipeline Hardening

**Baseline:** Phase 55 (RAGPolicy declared), Phase 57 (soft enforcement + based_on).
Phase 58 = hard enforcement + реализация `EmbeddingProvider`, `EmbeddingCache`, `RAGRanker`.

**Архитектурная цель:**
```
ContextEngine (L2, deterministic)
      ↓  context.documents (sealed — entry gate HARD)
Semantic Ranking Layer / RAGRanker (L3, pure function, deterministic under fixed embeddings)
      ↓  cascaded rerank: Graph выбирает, RAG расставляет приоритеты
LightRAGProjection (thin adapter / orchestration shell)
```

**Принцип:** L3 = чистый каскадный реранкер. Graph/ContextEngine делают selection;
Semantic Ranking Layer только переупорядочивает context.documents по cosine-близости к query.
Слияние score-ов (fusion) запрещено — graph_score не участвует в финальном ранке.

### Новые файлы

```
src/sdd/infra/embeddings/provider.py   # EmbeddingProvider Protocol
src/sdd/infra/embeddings/openai.py     # OpenAIEmbeddingProvider (text-embedding-3-small)
src/sdd/infra/embeddings/cache.py      # EmbeddingCache (composite key)
src/sdd/context_kernel/rag_ranker.py   # rank_documents() pure function
```

**Обоснование размещения в `infra/`:**
`EmbeddingProvider` = внешний API (OpenAI). Infra-level dependency.
`context_kernel/rag_ranker.py` зависит от `EmbeddingProvider` Protocol (не от реализации).
I-ENGINE-PURE-1 сохраняется: `EmbeddingCache` инжектируется в `LightRAGProjection`, не в `ContextEngine`.

### Типы и API

**`src/sdd/infra/embeddings/provider.py`:**
```python
from typing import Protocol

class EmbeddingProvider(Protocol):
    """I-EMBED-PROVIDER-1: stateless, no side effects. No filesystem, no cache."""
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

**`src/sdd/infra/embeddings/cache.py`:**
```python
import hashlib
from sdd.context_kernel.documents import DocumentChunk
from sdd.infra.embeddings.provider import EmbeddingProvider

class EmbeddingCache:
    """I-EMBED-CACHE-1: composite key prevents false cache hits.

    key = sha256(content + ast_signature + node_id + schema_version)
    Protects against: node_id rename with same text, AST boundary rule change,
    schema version bump.
    """
    def __init__(self) -> None:
        self._store: dict[str, list[float]] = {}

    def get_or_compute(
        self,
        chunk: DocumentChunk,
        provider: EmbeddingProvider,
        schema_version: str,
    ) -> list[float]:
        key = hashlib.sha256(
            f"{chunk.content}|{chunk.ast_signature or ''}|{chunk.node_id}|{schema_version}"
            .encode()
        ).hexdigest()
        if key not in self._store:
            self._store[key] = provider.embed([chunk.content])[0]
        return self._store[key]
```

**`src/sdd/context_kernel/rag_ranker.py`:**
```python
@dataclass(frozen=True)
class RankedDocument:
    chunk: DocumentChunk
    relevance_score: float

# ── IO layer (вызывает EmbeddingProvider + EmbeddingCache) ────────────────────

def build_embeddings(
    question: str,
    documents: list[DocumentChunk],
    provider: EmbeddingProvider,
    cache: EmbeddingCache,
    schema_version: str,
) -> tuple[list[float], list[tuple[DocumentChunk, list[float]]]]:
    """IO layer: embeds question and documents. May call external API.

    Returns (query_embedding, [(chunk, doc_embedding), ...]).
    On EmbeddingProvider failure: raises EmbeddingProviderError → caller degrades to DEGRADED.
    """
    q_vec = provider.embed([question])[0]
    doc_vecs = [(chunk, cache.get_or_compute(chunk, provider, schema_version)) for chunk in documents]
    return q_vec, doc_vecs

# ── Pure ranking layer (no I/O, no filesystem, no graph) ─────────────────────

def rank_documents_from_vectors(
    query_embedding: list[float],
    doc_embeddings: list[tuple[DocumentChunk, list[float]]],
    top_k: int,
) -> list[RankedDocument]:
    """Pure function. No I/O, no filesystem, no graph traversal.

    I-RAG-DETERMINISTIC-1: output is deterministic under fixed embeddings.
    I-RAG-TIEBREAK-1: sort key = (cosine DESC, chunk.graph_hop ASC, chunk.node_id ASC).

    Input = doc_embeddings (precomputed vectors from build_embeddings).
    Output count <= top_k.
    """
    # 1. cosine_similarity(query_embedding, doc_vec) per doc
    # 2. sorted(results, key=lambda r: (-r.relevance_score, r.chunk.graph_hop, r.chunk.node_id))
    # 3. return results[:top_k]

# ── Thin wrapper (production use) ────────────────────────────────────────────

def rank_documents(
    question: str,
    documents: list[DocumentChunk],
    provider: EmbeddingProvider,
    cache: EmbeddingCache,
    policy: RAGPolicy,
    schema_version: str,
) -> list[RankedDocument]:
    """Thin wrapper: build_embeddings → rank_documents_from_vectors.

    On EmbeddingProviderError → caller (LightRAGProjection) handles DEGRADED.
    """
    q_vec, doc_vecs = build_embeddings(question, documents, provider, cache, schema_version)
    return rank_documents_from_vectors(q_vec, doc_vecs, top_k=policy.max_documents)
```

**Тестируемость:**
```python
# Юнит-тест без API (только pure функция):
def test_rag_ranker_order():
    chunk_a = make_chunk(node_id="a", graph_hop=1)
    chunk_b = make_chunk(node_id="b", graph_hop=0)
    docs = [(chunk_a, [1.0, 0.0]), (chunk_b, [0.0, 1.0])]
    result = rank_documents_from_vectors([0.9, 0.1], docs, top_k=2)
    assert result[0].chunk is chunk_a  # выше cosine

# Тест tiebreak (одинаковый cosine → ближе к anchor выигрывает):
def test_rag_tiebreak_hop():
    chunk_near = make_chunk(node_id="z", graph_hop=1)
    chunk_far  = make_chunk(node_id="a", graph_hop=3)
    docs = [(chunk_near, [0.8, 0.2]), (chunk_far, [0.8, 0.2])]  # equal cosine
    result = rank_documents_from_vectors([0.8, 0.2], docs, top_k=2)
    assert result[0].chunk is chunk_near  # hop=1 wins
```

**Hard enforcement в `LightRAGProjection.query()` (entry gate):**
```python
def query(self, question, context, rag_mode, rag_client, rag_policy=None):
    # I-RAG-SCOPE-ENTRY-1 hard (Phase 58):
    allowed_ids = {d.node_id for d in getattr(context, "documents", [])}

    # I-RAG-1 hard:
    if rag_policy is not None and rag_policy.allow_global_search:
        raise RAGPolicyViolation(
            "I-RAG-SCOPE-1: allow_global_search=True violates I-ARCH-LAYER-SEPARATION-1. "
            "RAG MUST NOT access documents outside ContextEngine output."
        )
    # ... existing logic
```

**`RAGPolicyViolation` exception:**
```python
class RAGPolicyViolation(RuntimeError):
    """Raised when RAGPolicy constraints are violated. I-RAG-1 hard enforcement."""
```

### Deterministic chunking (расширение `ContentMapper`)

**Файл:** `src/sdd/context_kernel/documents.py`

```python
class ASTBoundaryMapper(ContentMapper):
    """I-CHUNK-DETERMINISTIC-1: deterministic AST-boundary chunking.

    chunk = f(file_path, ast.parse(), fixed_rules)
    NOT by token count. NOT by random splits.
    Boundaries = class/function AST node start lines.
    Produces DocumentChunk.ast_signature for EmbeddingCache composite key.
    """
```

`DocumentChunk` расширяется двумя полями:
- `ast_signature: str | None = None` — для composite cache key EmbeddingCache
- `graph_hop: int = 0` — BFS-дистанция от anchor/seed узла (из `RankedNode.hop`); используется в I-RAG-TIEBREAK-1

Assembler прокидывает `graph_hop` из `RankedNode.hop` при построении `DocumentChunk`.
Seed node (hop=0) получает `graph_hop=0`. Chunk без соответствующего RankedNode → `graph_hop=999` (lowest priority).

### Инварианты Phase 58

| ID | Statement |
|----|-----------|
| I-ARCH-LAYER-SEPARATION-1 | hard: LightRAGProjection verifies entry gate; RAGRanker receives only sealed context.documents |
| I-RAG-1 | hard: `RAGPolicyViolation` on `allow_global_search=True` |
| I-RAG-SCOPE-ENTRY-1 | hard: entry gate enforced before any ranking |
| I-RAG-DETERMINISTIC-1 | `rank_documents_from_vectors()` output MUST be deterministic under fixed embeddings. Pure function, no I/O, no filesystem, no graph traversal | 58 |
| I-RAG-TIEBREAK-1 | Финальный sort key: `(cosine DESC, chunk.graph_hop ASC, chunk.node_id ASC)`. Chunk ближе к anchor_node (hop малый) → выше при равном cosine. `graph_hop` приходит из `RankedNode.hop` в assembler | 58 |
| I-RAG-SPLIT-1 | `build_embeddings` (IO, может вызывать API) и `rank_documents_from_vectors` (pure, без I/O) MUST быть отдельными функциями. `rank_documents` — допустимый thin wrapper | 58 |
| I-RAG-QUERY-1 | Query логируется в `graph_calls.jsonl` как операционный атрибут ExecutionContext. НЕ становится domain-событием EventLog | 58 |
| I-RAG-DEGRADED-1 | При сбое EmbeddingProvider: documents в граф-порядке, `rag_summary: null`, `rag_mode: "DEGRADED"`. L1/L2 не блокируются. Никаких полупересчитанных ранков | 58 hard |
| I-BM25-SINGLETON-1 | BM25 живёт только в `SpatialIndex`. `sdd resolve` = фасад над `SpatialIndex.query_bm25()`. Вторая независимая BM25-реализация вне SpatialIndex запрещена | 58 |
| I-BM25-RESOLVE-EXCEPTION-1 | `sdd resolve` — единственное разрешённое место standalone BM25 retrieval. Производит только node_id[] для seed. После resolve ВСЕГДА следует Graph→ContextEngine | 58 |
| I-BM25-INTERNAL-1 | BM25 внутри RAG/ContextEngine (если применяется) = scoring only внутри nodes уже выбранных Graph. MUST NOT добавлять новые nodes/documents в Selection | 58 |
| I-EMBED-PROVIDER-1 | `EmbeddingProvider.embed()` MUST be stateless. No side effects. timeout + max_retries конфигурируемы. EmbeddingProviderError → caller handles degrade | 58 |
| I-EMBED-CACHE-1 | Cache key MUST be `sha256(content + ast_sig + node_id + schema_version)`. NOT content-only | 58 |
| I-CHUNK-DETERMINISTIC-1 | Chunking MUST be `f(file, AST, fixed_rules)`. NOT by token count, NOT random splits | 58 |
| I-NAV-BASED-ON-1 | hard: `NavigationResponse.based_on` MUST be non-None/non-empty for non-empty context | 58 hard |
| I-ARCH-LAYER-SEPARATION-1 | hard: LightRAGProjection verifies entry gate; RAGRanker receives only sealed context.documents | 58 hard |
| I-RAG-1 | hard: `RAGPolicyViolation` on `allow_global_search=True` | 58 hard |
| I-RAG-SCOPE-ENTRY-1 | hard: entry gate enforced before any ranking | 58 hard |

**Примечание:** `I-SEARCH-NO-EMBED-1` НЕ снимается. `EmbeddingProvider` живёт в `infra/embeddings/`
и MUST NOT be imported by `sdd resolve` or `sdd graph-*` commands.

### NavigationResponse RAG fields

```python
@dataclass
class NavigationResponse:
    context: Context
    rag_summary: str | None      # top-N chunks concatenated "\n---\n"; null if rag_mode != ON
    rag_mode: str | None         # "ON" | "OFF" | "DEGRADED"
    candidates: list[SearchCandidate] | None
    based_on: list[str] | None
    rag_top_k: int | None        # actual N used (None if rag_mode != ON)
```

`rag_summary` = детерминированная конкатенация текстов top-N чанков по cosine-порядку (I-RAG-TIEBREAK-1).
Без LLM-синтеза. `N` = `RAGPolicy.rag_summary_top_k` (default: 5, конфигурируемо).
LLM-агент: читает `rag_summary` как приоритизированный контекст; при необходимости обращается к
полному `context.documents` по `node_id`.

### DoD Criterion (BC-58-RAG)

**Criterion A — Technical (обязателен):**
- `rank_documents_from_vectors` тесты зелёные: детерминизм порядка, tiebreak по hop/node_id, max_documents
- DEGRADED тест: при `EmbeddingProviderError` → граф-порядок, `rag_mode: "DEGRADED"`, `rag_summary: null`
- Cache тест: same chunk content + разные node_id → разные cache keys (I-EMBED-CACHE-1)
- Entry gate тест: `allow_global_search=True` → `RAGPolicyViolation`

**Criterion B — Semantic eval (обязателен перед кодом):**

Фиксируется до написания RAG-кода. 5 якорных кейсов из реального SDD-кода:

| # | query | anchor_node | expected_top_chunk |
|---|-------|------------|---------------------|
| 1 | "как регистрируется команда" | `FILE:src/sdd/commands/registry.py` | участок с `REGISTRY[name]` / регистрацией handler'а |
| 2 | "кто эмитит TaskImplementedEvent" | `EVENT:TaskImplementedEvent` | handler в `reconcile_bootstrap.py` с emit |
| 3 | "какие инварианты проверяет activate_phase" | `COMMAND:activate-phase` | заголовок handler-файла с `Invariants:` |
| 4 | "как extractor регистрируется в builder" | `FUNCTION:TestedByEdgeExtractor` | место добавления extractor'а в GraphFactsBuilder |
| 5 | "где объявлен PhaseStartedEvent" | `EVENT:PhaseStartedEvent` | `core/events.py` с dataclass + docstring |

RAG "работает" если в этих кейсах expected_chunk попадает в top-3 при включённом реранкинге.
`@pytest.mark.semantic_eval` — запускаются вручную с реальным `OPENAI_API_KEY`, не в CI.

### Verification (BC-58-RAG)

```bash
# Hard enforcement
python3 -m pytest tests/unit/context_kernel/test_rag_policy.py -v
# → RAGPolicyViolation raised on allow_global_search=True

# Deterministic ranking (same inputs → same order)
python3 -m pytest tests/unit/context_kernel/test_rag_ranker.py::test_deterministic_order -v

# EmbeddingCache composite key
python3 -m pytest tests/unit/infra/test_embedding_cache.py -v
# → same content + different node_id → different cache key (no false hit)

# I-SEARCH-NO-EMBED-1 not violated
python3 -c "
import ast, sys
with open('src/sdd/graph_navigation/cli/resolve.py') as f:
    src = f.read()
assert 'EmbeddingProvider' not in src and 'embedding' not in src.lower(), 'VIOLATION I-SEARCH-NO-EMBED-1'
print('OK: sdd resolve does not import EmbeddingProvider')
"
```

---

## 8. §4 Types — additions to types.py

### EDGE_KIND_PRIORITY additions (Phase 58)

```python
EDGE_KIND_PRIORITY: dict[str, float] = {
    # Phase 50-57 (existing) ...
    "violated_by":       0.91,   # Phase 58 BC-58-3 — НОВЫЙ
    "enforced_by":       0.88,   # Phase 58 BC-58-3 — НОВЫЙ
    "module_depends_on": 0.67,   # Phase 58 BC-58-1 — НОВЫЙ
    "module_public_api": 0.65,   # Phase 58 BC-58-1 — НОВЫЙ
    # existing: cross_bc_dependency: 0.63, imports: 0.60, calls: 0.58 (обновляется ниже) ...
}
```

### EDGE_KIND_CONFIDENCE updates (Phase 58)

```python
EDGE_KIND_CONFIDENCE: dict[str, float] = {
    # existing ...
    "calls":             0.85,   # Phase 58 BC-58-2 (up from 0.6)
    "violated_by":       1.0,    # Phase 58 BC-58-3 — computed rule-based
    "enforced_by":       1.0,    # Phase 58 BC-58-3 — static config
    "module_depends_on": 1.0,    # Phase 58 BC-58-1 — derived from imports
    "module_public_api": 1.0,    # Phase 58 BC-58-1 — from __init__.py
}
```

---

## 9. §5 Invariants

| ID | Утверждение | Phase |
|----|-------------|-------|
| I-MODULE-API-1 | imports к internal FILE в MODULE:M → violation если FILE ∉ module_public_api(M) | 58 |
| I-MODULE-API-2 | `module_depends_on` — derived stage; расхождение с imports graph → GraphInvariantError | 58 |
| I-CALLS-PRECISION-1 | CallsEdgeExtractor MUST use ast.Call analysis; imports-based detection запрещён | 58 |
| I-ARCH-NODES-1 | Каждый инвариант в INVARIANT_REGISTRY имеет INVARIANT node в графе | 58 |
| I-ARCH-NODES-2 | `violated_by` edges отражают последнее arch-check; отсутствие при no-run не ошибка | 58 |
| I-DSL-1 | DSL parser НЕ вызывает eval()/exec(); только whitelist tokens | 58 |
| I-GRAPH-GUARD-REPORT-1 | `graph-guard report` использует тот же алгоритм что и `graph-guard check` | 58 |
| I-ARCH-LAYER-SEPARATION-1 | → см. BC-58-RAG инварианты (hard enforcement) | 58 |
| I-RAG-1 | → см. BC-58-RAG инварианты | 58 |
| I-RAG-SCOPE-ENTRY-1 | → см. BC-58-RAG инварианты | 58 |
| I-RAG-DETERMINISTIC-1 | → см. BC-58-RAG инварианты (обновлён: tiebreak включает graph_hop) | 58 |
| I-RAG-TIEBREAK-1 | → см. BC-58-RAG инварианты (НОВЫЙ) | 58 |
| I-RAG-SPLIT-1 | → см. BC-58-RAG инварианты (НОВЫЙ: build_embeddings / rank_documents_from_vectors) | 58 |
| I-RAG-QUERY-1 | → см. BC-58-RAG инварианты (НОВЫЙ: query в graph_calls.jsonl) | 58 |
| I-RAG-DEGRADED-1 | → см. BC-58-RAG инварианты (НОВЫЙ: DEGRADED формализован) | 58 |
| I-BM25-SINGLETON-1 | → см. BC-58-RAG инварианты (НОВЫЙ) | 58 |
| I-BM25-RESOLVE-EXCEPTION-1 | → см. BC-58-RAG инварианты (НОВЫЙ) | 58 |
| I-EMBED-PROVIDER-1 | → см. BC-58-RAG инварианты (timeout + max_retries добавлены) | 58 |
| I-EMBED-CACHE-1 | → см. BC-58-RAG инварианты | 58 |
| I-CHUNK-DETERMINISTIC-1 | → см. BC-58-RAG инварианты | 58 |
| I-NAV-BASED-ON-1 | → см. BC-58-RAG инварианты | 58 |

---

## 10. §7 Milestones

| Milestone | Deliverable |
|-----------|-------------|
| M58-1 | BC-58-2: CallsEdgeExtractor v2, ast.Call analysis, confidence=0.85, tests |
| M58-2 | BC-58-1: ModulePublicAPIExtractor + ModuleDependsOnExtractor + arch-check module-api-boundary |
| M58-3 | BC-58-3: INVARIANT nodes + enforced_by/violated_by edges + arch-check invariant-coverage |
| M58-4 | BC-58-6: graph-guard report (из Spec_v57 Out of Scope) |
| M58-5 | BC-58-4: Graph Query DSL MVP |
| M58-6 | BC-58-5: Hotspot detection |
| M58-7 | BC-58-RAG: EmbeddingProvider + EmbeddingCache (composite key) + RAGRanker pure function + hard enforcement |

---

## 11. Risk Notes

| Risk | Mitigation |
|------|------------|
| calls confidence 0.85 < 0.9 → violations не включаются | Намеренно; phase boundary чёткая |
| ModulePublicAPIExtractor зависит от `__init__.py` structure | Fallback: нет `__all__` → все files public |
| INVARIANT nodes из статического YAML — ручное ведение | Автогенерация из SDD_Spec_v1.md парсером в Phase 59+ |
| DSL parser — новый язык, сложность разрастается | Жёсткий MVP: только FROM/EXPAND/TRACE/FILTER, без OR/AND |
| ASTBoundaryMapper — сложность при macro-level chunking | Fallback: ASTBoundaryMapper MUST fall back to whole-file chunk if ast.parse() fails |
| EmbeddingCache memory growth — in-memory, no eviction | Acceptable: scoped per ContextEngine session; TTL eviction in Phase 59+ if needed |

---

## 13. Phase Acceptance Checklist

> Методология: `.sdd/docs/ref/phase-acceptance.md`

### Part 1 — In-Phase DoD

**Step U (Universal):**
```bash
sdd show-state                          # tasks_completed == tasks_total
sdd validate --check-dod --phase 58     # exit 0
python3 -m pytest tests/unit/ -q        # 0 failures
```

**Step 58-A — calls extractor v2 (BC-58-2):**
```bash
python3 -c "
from sdd.graph.types import EDGE_KIND_CONFIDENCE
assert EDGE_KIND_CONFIDENCE['calls'] == 0.85, f'Expected 0.85, got {EDGE_KIND_CONFIDENCE[\"calls\"]}'
print('calls confidence OK: 0.85')
"
# → calls confidence OK: 0.85

# AST Call analysis: qualified call foo.bar() → edge с confidence=0.85
python3 -m pytest tests/unit/graph/test_calls_extractor_v2.py -v
# → PASSED
```

**Step 58-B — MODULE API Boundary (BC-58-1):**
```bash
sdd graph-stats --edge-type module_public_api --format json
# → {"count": N}, N ≥ 0 (0 если нет __all__ → fallback, ОК)

sdd graph-stats --edge-type module_depends_on --format json
# → {"count": N}, N ≥ 0

sdd arch-check --check module-api-boundary --format json
# → exit 0 ИЛИ exit 1 с violations; НЕ crash
```

**Step 58-C — INVARIANT nodes (BC-58-3, расширение invariant_edges.py):**
```bash
sdd graph-stats --node-type INVARIANT --format json
# → {"count": N}, N > 0  (инварианты из invariant_registry.yaml)

sdd graph-stats --edge-type enforced_by --format json
# → {"count": N}, N > 0

sdd explain INVARIANT:I-ARCH-1 --edge-types enforced_by --format json
# → возвращает COMMAND:arch-check (или аналог)
```

**Step 58-D — graph-guard coverage report (BC-58-6):**
```bash
sdd graph-guard report --task T-5801 --format json
# → {"anchor_nodes": [...], "covered": [...], "uncovered": [...], "coverage_pct": float}
# Неприемлемо: crash или отсутствие "coverage_pct"
```

**Step 58-E — типы в EDGE_KIND_PRIORITY:**
```bash
python3 -c "
from sdd.graph.types import EDGE_KIND_PRIORITY
for k in ['violated_by', 'enforced_by', 'module_depends_on', 'module_public_api']:
    assert k in EDGE_KIND_PRIORITY, f'{k} MISSING'
    print(f'{k}: {EDGE_KIND_PRIORITY[k]}')
"
# → violated_by: 0.91, enforced_by: 0.88, module_depends_on: 0.67, module_public_api: 0.65
```

**Step 58-F — RAG Pipeline Hardening (BC-58-RAG):**
```bash
# Hard enforcement: RAGPolicyViolation on allow_global_search=True
python3 -m pytest tests/unit/context_kernel/test_rag_policy.py -v
# → PASSED

# Deterministic ranking
python3 -m pytest tests/unit/context_kernel/test_rag_ranker.py::test_deterministic_order -v
# → PASSED

# EmbeddingCache composite key (different node_id → different key)
python3 -m pytest tests/unit/infra/test_embedding_cache.py -v
# → PASSED

# I-SEARCH-NO-EMBED-1 preserved (sdd resolve не импортирует EmbeddingProvider)
python3 -c "
import ast
with open('src/sdd/graph_navigation/cli/resolve.py') as f:
    src = f.read()
assert 'EmbeddingProvider' not in src
print('OK: I-SEARCH-NO-EMBED-1 preserved')
"

# NavigationResponse.based_on non-None for non-empty context
python3 -m pytest tests/unit/context_kernel/test_engine.py -k 'based_on' -v
# → PASSED
```

---

### Part 2 — Regression Guard

```bash
# (R-58-1) calls confidence 0.6→0.85: violations не включаются (I-ARCH-CONFIDENCE-1 threshold=0.9)
sdd arch-check --check layer-direction --format json
# → calls edges должны быть WARNING, не violations (confidence < 0.9)

# (R-58-2) существующий invariant_edges.py — verified_by, introduced_in edges всё ещё работают
sdd graph-stats --edge-type verified_by --format json    # count > 0 (если были до Phase 58)
sdd graph-stats --edge-type introduced_in --format json  # count ≥ 0

# (R-58-3) arch-check из Phase 57 — не сломан
sdd arch-check --check all --format json
# → exit 0 ИЛИ exit 1; НЕ crash

# (R-58-4) MODULE nodes из Phase 55, BOUNDED_CONTEXT из Phase 56
sdd graph-stats --node-type MODULE --format json           # count > 0
sdd graph-stats --node-type BOUNDED_CONTEXT --format json  # count > 0
```

Если хоть одна регрессия → **STOP → sdd report-error → recovery.md**.

---

### Part 3 — Transition Gate (before Phase 59+)

Phase 58 — финальная в текущем roadmap. Transition gate = готовность к Phase 59.

```bash
# Gate 59-A: calls confidence достигнут 0.85 (зафиксировано)
python3 -c "from sdd.graph.types import EDGE_KIND_CONFIDENCE; print(EDGE_KIND_CONFIDENCE['calls'])"
# Expected: 0.85

# Gate 59-B: Module API boundary работает (основа для Phase 59 embedding-search)
sdd arch-check --check module-api-boundary --format json
# Expected: exit 0 ИЛИ exit 1 с JSON

# Gate 59-C: INVARIANT nodes полностью покрывают инварианты из INVARIANT_REGISTRY
sdd arch-check --check invariant-coverage --format json
# Expected: exit 0 (все инварианты имеют INVARIANT nodes)
```

---

### Part 4 — Rollback Triggers

Немедленно STOP если:
- `sdd graph-stats --edge-type verified_by` → `count: 0` когда до Phase 58 было > 0 (invariant_edges.py сломан)
- `EDGE_KIND_CONFIDENCE['calls']` ≠ 0.85 после реализации BC-58-2
- `sdd arch-check --check module-api-boundary` → crash (не exit 1)
- `sdd explain INVARIANT:I-ARCH-1` → "not found" (INVARIANT nodes не построены)
- `sdd graph-guard report` → crash вместо JSON
- Любой тест Phase 52-57 начинает падать

---

## 12. Ordering

```
Phase 56 COMPLETE
  ↓
Phase 57 COMPLETE (SSOT граф, arch-check, I-ARCH-CONFIDENCE-1)
  ↓
Phase 58 PLAN/ACTIVE
  BC-58-2 (calls v2) → M58-1
  BC-58-1 (module API) → M58-2  [зависит от Module nodes из Phase 55]
  BC-58-3 (INVARIANT nodes) → M58-3
  BC-58-6 (guard report) → M58-4  [зависит от graph-guard v2 Phase 57]
  BC-58-4 (DSL) → M58-5
  BC-58-5 (hotspot) → M58-6
```
