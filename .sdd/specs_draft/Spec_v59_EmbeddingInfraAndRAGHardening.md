# Spec_v59 — Embedding Infrastructure & RAG Hardening

**Status:** DRAFT
**Depends on:** Phase 53 COMPLETE
**Revised:** 2026-04-30

**Motive:** Phase 53 завершила graph test filtering. Спеки v55–v58 охватывают широкий фронт
(Module API, calls refinement, DSL, hotspot). Spec_v59 вырезает из этого фронта реализуемое
ядро: инфраструктуру embeddings и hardening RAG pipeline. Цель — получить работающий
semantic reranking документов поверх BFS-графа с hard enforcement policy gates.

---

## 1. Scope

### In-Scope

| BC | Название | Приоритет |
|----|----------|-----------|
| BC-59-1 | EmbeddingProvider Protocol | Критический |
| BC-59-2 | OpenAIEmbeddingProvider (text-embedding-3-small) | Критический |
| BC-59-3 | EmbeddingCache (composite key, in-memory) | Критический |
| BC-59-4 | DocumentChunk extensions (ast_signature, graph_hop) | Критический |
| BC-59-5 | RAGRanker module (build_embeddings + rank_documents_from_vectors) | Критический |
| BC-59-6 | NavigationResponse extensions (based_on, rag_top_k) | Критический |
| BC-59-7 | LightRAGProjection hard gates (RAGPolicyViolation, DEGRADED mode) | Критический |
| BC-59-8 | pyproject.toml: openai>=1.0, numpy в основные зависимости | Критический |

### Out of Scope → Spec_v60

| Item | Owner |
|------|-------|
| ModulePublicAPIExtractor / ModuleDependsOnExtractor | BC-60-1 |
| CallsEdgeExtractor v2 (AST Call, 0.85 confidence) | BC-60-2 |
| InvariantEdgeExtractor (violated_by / enforced_by) | BC-60-3 |
| Graph Query DSL MVP (`sdd query --dsl`) | BC-60-4 |
| Hotspot detection (`sdd hotspot`) | BC-60-5 |
| graph-guard coverage report | BC-60-6 |
| ASTBoundaryMapper (deterministic AST chunking) | BC-60-7 |
| Persistent EmbeddingCache (file-based) | BC-60-8 |
| MODULE / BOUNDED_CONTEXT / LAYER node kinds + classifiers | BC-60-9 |

---

## 2. BC-59-1: EmbeddingProvider Protocol

**Проблема:** RAGRanker требует вызов embedding API, но не должен знать о конкретном провайдере.
Нужен Protocol для инъекции зависимости и изоляции I/O.

**Файл:** `src/sdd/infra/embeddings/provider.py`

```python
from typing import Protocol

EmbeddingVector = list[float]


class EmbeddingProviderError(Exception):
    """Raised when embedding API call fails (timeout, auth, rate limit)."""


class EmbeddingProvider(Protocol):
    """Stateless embedding API client. No side effects (I-EMBED-PROVIDER-1)."""

    def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        """Return one vector per text. Raises EmbeddingProviderError on failure."""
        ...
```

**Инварианты:**

| ID | Формулировка |
|----|--------------|
| I-EMBED-PROVIDER-1 | `EmbeddingProvider.embed()` — stateless, no side effects. `timeout` и `max_retries` конфигурируемы при создании объекта, не при вызове. |
| I-SEARCH-NO-EMBED-1 | `sdd resolve` MUST NOT import `EmbeddingProvider` или любой из `infra/embeddings/`. Граница слоя L3→L2 нарушается при нарушении. |

---

## 3. BC-59-2: OpenAIEmbeddingProvider

**Файл:** `src/sdd/infra/embeddings/openai.py`

**Зависимость:** `openai>=1.0` в `pyproject.toml` (основные, не optional).
**ENV:** `OPENAI_API_KEY` — обязателен в runtime, не в тестах.

```python
from sdd.infra.embeddings.provider import EmbeddingProvider, EmbeddingVector, EmbeddingProviderError

class OpenAIEmbeddingProvider:
    """Implements EmbeddingProvider via openai.embeddings.create()."""

    MODEL = "text-embedding-3-small"
    BATCH_SIZE = 100  # max texts per API call

    def __init__(self, timeout: float = 10.0, max_retries: int = 3): ...

    def embed(self, texts: list[str]) -> list[EmbeddingVector]:
        """Batch texts → MODEL → list of float vectors.
        Raises EmbeddingProviderError on APIError / timeout / auth failure."""
        ...
```

**Модель:** `text-embedding-3-small` — зафиксирована как нормативное требование (I-EMBED-MODEL-1).
Вектор: **1536 измерений**.

**Поведение:**
- Разбивает `texts` на батчи по `BATCH_SIZE`
- При `openai.APIError` → raise `EmbeddingProviderError(str(e))`
- Возвращает векторы в том же порядке, что и входные тексты
- Не кэширует (кэш — BC-59-3)

**Инвариант:**

| ID | Формулировка |
|----|--------------|
| I-EMBED-MODEL-1 | `OpenAIEmbeddingProvider` MUST use model `text-embedding-3-small` (1536 dims). Смена модели требует новой фазы и обновления `SCHEMA_VERSION` в `EmbeddingCache`. |

---

## 4. BC-59-3: EmbeddingCache

**Файл:** `src/sdd/infra/embeddings/cache.py`

**Ключ кэша:** `sha256(content | ast_signature | node_id | SCHEMA_VERSION)` (I-EMBED-CACHE-1)

```python
SCHEMA_VERSION = "v1"

class EmbeddingCache:
    """In-memory cache. Persistent storage — Phase 60 (BC-60-8)."""

    def get_or_compute(
        self,
        chunk: "DocumentChunk",
        provider: EmbeddingProvider,
    ) -> EmbeddingVector:
        """Return cached vector or call provider.embed([chunk.content])."""
        ...

    @staticmethod
    def cache_key(chunk: "DocumentChunk") -> str:
        """sha256(content | ast_signature | node_id | SCHEMA_VERSION)."""
        ...
```

**Инвариант:**

| ID | Формулировка |
|----|--------------|
| I-EMBED-CACHE-1 | Ключ кэша = `sha256(content + "\x00" + (ast_sig or "") + "\x00" + node_id + "\x00" + SCHEMA_VERSION)`. Изменение SCHEMA_VERSION инвалидирует весь кэш автоматически. |

---

## 5. BC-59-4: DocumentChunk Extensions

**Файл:** `src/sdd/context_kernel/documents.py`

Добавить два новых поля в `DocumentChunk`:

```python
@dataclass
class DocumentChunk:
    node_id: str
    content: str
    kind: str
    char_count: int
    meta: dict
    references: list[str]
    # NEW (BC-59-4):
    ast_signature: str | None = None   # используется как компонент EmbeddingCache key
    graph_hop: int = 0                  # BFS distance от anchor node; 0 = seed
```

**Файл:** `src/sdd/context_kernel/assembler.py`

В методе, который создаёт `DocumentChunk` из `RankedNode`, добавить:
```python
graph_hop=ranked_node.hop,
```

Seed node (hop=0) — ближайший к anchor. Документы без `RankedNode` (если появятся) — `graph_hop=999`.

**Инвариант:**

| ID | Формулировка |
|----|--------------|
| I-DOC-HOP-1 | `DocumentChunk.graph_hop` MUST equal `RankedNode.hop` for the corresponding node. Seed node (anchor) → hop=0. Fallback for non-BFS documents → 999. |

---

## 6. BC-59-5: RAGRanker Module

**Файл:** `src/sdd/context_kernel/rag_ranker.py`

**Ключевой дизайн:** I/O и чистая функция разделены (I-RAG-SPLIT-1).

```python
from dataclasses import dataclass
from sdd.context_kernel.documents import DocumentChunk
from sdd.infra.embeddings.provider import EmbeddingProvider, EmbeddingVector
from sdd.infra.embeddings.cache import EmbeddingCache


@dataclass
class EmbeddedChunk:
    chunk: DocumentChunk
    vector: EmbeddingVector


@dataclass
class RankedChunk:
    chunk: DocumentChunk
    cosine_score: float


def build_embeddings(
    chunks: list[DocumentChunk],
    provider: EmbeddingProvider,
    cache: EmbeddingCache,
) -> list[EmbeddedChunk]:
    """I/O layer: fetch embeddings (cached or via provider)."""
    ...


def rank_documents_from_vectors(
    query_vector: EmbeddingVector,
    embedded_chunks: list[EmbeddedChunk],
    top_k: int,
) -> list[RankedChunk]:
    """Pure function: cosine similarity + deterministic sort.
    Sort key: (cosine DESC, chunk.graph_hop ASC, chunk.node_id ASC).
    Returns at most top_k items."""
    ...


def rank_documents(
    query: str,
    chunks: list[DocumentChunk],
    provider: EmbeddingProvider,
    cache: EmbeddingCache,
    top_k: int,
) -> list[RankedChunk]:
    """Thin orchestrator: build_embeddings → embed query → rank_documents_from_vectors."""
    ...
```

**Cosine similarity:**
```
cosine(a, b) = dot(a, b) / (||a|| * ||b||)
```
Реализуется через `numpy` или чистый Python (fallback).

**Инварианты:**

| ID | Формулировка |
|----|--------------|
| I-RAG-SPLIT-1 | `build_embeddings` (I/O) и `rank_documents_from_vectors` (pure) — строго разделены. `rank_documents_from_vectors` MUST NOT call provider или cache. |
| I-RAG-DETERMINISTIC-1 | `rank_documents_from_vectors` детерминирован при фиксированных векторах: одинаковые inputs → одинаковый порядок. |
| I-RAG-TIEBREAK-1 | Sort key: `(-cosine_score, chunk.graph_hop, chunk.node_id)`. Tiebreak: ближайшие к anchor побеждают. |

---

## 7. BC-59-6: NavigationResponse Extensions

**Файл:** `src/sdd/context_kernel/rag_types.py`

Добавить в `NavigationResponse`:

```python
@dataclass
class NavigationResponse:
    context: Context
    rag_summary: str | None
    rag_mode: str | None
    candidates: list[SearchCandidate] | None
    # NEW (BC-59-6):
    based_on: list[str] | None = None   # node_ids документов, использованных для rag_summary
    rag_top_k: int | None = None         # фактическое N использованных документов
```

Добавить новый тип исключения:

```python
class RAGPolicyViolation(Exception):
    """Raised when RAGPolicy constraints are violated (I-RAG-1)."""
```

**Инвариант:**

| ID | Формулировка |
|----|--------------|
| I-NAV-BASED-ON-1 | Если `context` непустой И `rag_mode != "DEGRADED"` И `rag_mode != None` → `based_on` MUST NOT be None и MUST NOT be empty. Нарушение = ошибка сборки ответа. |

---

## 8. BC-59-7: LightRAGProjection Hard Gates

**Файл:** `src/sdd/context_kernel/rag_types.py` (класс `LightRAGProjection`)

### Hard Gate 1: Policy Enforcement (I-RAG-1)

На входе в `LightRAGProjection.query()` — **до любых вычислений**:

```python
if rag_policy.allow_global_search:
    raise RAGPolicyViolation(
        "allow_global_search=True is forbidden (I-RAG-1). "
        "RAGPolicy.allow_global_search MUST remain False."
    )
```

Это I-RAG-SCOPE-ENTRY-1: gate enforced BEFORE ranking.

### Hard Gate 2: DEGRADED Mode (I-RAG-DEGRADED-1)

При `EmbeddingProviderError` во время ranking:

```python
# вместо propagating исключения:
return NavigationResponse(
    context=context,
    rag_summary=None,
    rag_mode="DEGRADED",
    candidates=None,
    based_on=None,
    rag_top_k=None,
)
```

Documents возвращаются в graph-order (сортировка ассемблера без reranking).

**Инварианты:**

| ID | Формулировка |
|----|--------------|
| I-RAG-1 | hard: `RAGPolicyViolation` при `allow_global_search=True`. Нет исключений. |
| I-RAG-SCOPE-ENTRY-1 | hard: entry gate проверяется первым в `LightRAGProjection.query()`, до ranking и до вызова embedding provider. |
| I-RAG-DEGRADED-1 | `EmbeddingProviderError` → `rag_mode="DEGRADED"`, `rag_summary=None`. Исключение НЕ пробрасывается наверх. |

---

## 9. BC-59-8: pyproject.toml Changes

```toml
[project]
dependencies = [
    "PyYAML>=6.0",
    "click>=8.0",
    "psycopg[binary]>=3.1",
    "openai>=1.0",    # NEW: embedding API
    "numpy>=1.26",    # MOVED from optional[lightrag]
]

[project.optional-dependencies]
lightrag = [
    "lightrag-hku>=1.4",
    # numpy moved to main dependencies
]
```

---

## 10. Полная таблица инвариантов Spec_v59

| ID | BC | Формулировка | Enforcement |
|----|----|--------------|-------------|
| I-EMBED-PROVIDER-1 | BC-59-1 | `EmbeddingProvider.embed()` stateless, no side effects | Protocol definition |
| I-SEARCH-NO-EMBED-1 | BC-59-1 | `sdd resolve` MUST NOT import `EmbeddingProvider` | Import boundary check |
| I-EMBED-MODEL-1 | BC-59-2 | Model = `text-embedding-3-small` (1536 dims); смена модели → новая фаза + bump `SCHEMA_VERSION` | `OpenAIEmbeddingProvider.MODEL` |
| I-EMBED-CACHE-1 | BC-59-3 | Cache key = sha256(content\|ast_sig\|node_id\|SCHEMA_VERSION) | `EmbeddingCache.cache_key()` |
| I-DOC-HOP-1 | BC-59-4 | `DocumentChunk.graph_hop` = `RankedNode.hop`; seed=0; fallback=999 | assembler.py |
| I-RAG-SPLIT-1 | BC-59-5 | `build_embeddings` (IO) и `rank_documents_from_vectors` (pure) строго разделены | Module structure |
| I-RAG-DETERMINISTIC-1 | BC-59-5 | `rank_documents_from_vectors` детерминирован | Pure function |
| I-RAG-TIEBREAK-1 | BC-59-5 | Sort: `(-cosine, graph_hop, node_id)` | `rank_documents_from_vectors` |
| I-NAV-BASED-ON-1 | BC-59-6 | `based_on` non-None/non-empty при active RAG context | NavigationResponse assembly |
| I-RAG-1 | BC-59-7 | `RAGPolicyViolation` при `allow_global_search=True` | `LightRAGProjection.query()` |
| I-RAG-SCOPE-ENTRY-1 | BC-59-7 | Policy gate первый в `query()`, до ranking | Code order |
| I-RAG-DEGRADED-1 | BC-59-7 | `EmbeddingProviderError` → `rag_mode="DEGRADED"`, no raise | Exception handler |

---

## 11. Milestones

| M | Критерий | Задачи |
|---|----------|--------|
| M-59-A | EmbeddingProvider Protocol + OpenAI impl + Cache готовы, unit-тесты проходят без API | T-5901..T-5903 |
| M-59-B | RAGRanker: `rank_documents_from_vectors` pure, unit-тесты с фейковыми векторами проходят | T-5904..T-5905 |
| M-59-C | DocumentChunk + assembler extended; `graph_hop` корректно propagates | T-5906 |
| M-59-D | NavigationResponse + hard gates в LightRAGProjection; `RAGPolicyViolation` работает | T-5907..T-5908 |
| M-59-E | pyproject.toml обновлён; `pip install -e .` успешен | T-5909 |

---

## 12. Risk Notes

| Риск | Митигация |
|------|-----------|
| `OPENAI_API_KEY` отсутствует в CI | Unit-тесты для `rank_documents_from_vectors` — без API (фейковые векторы). OpenAI impl покрывается только в integration tier (skip без ключа). |
| numpy не установлен | numpy перенесён в основные зависимости; cosine без numpy — чистый Python fallback. |
| Изменение `DocumentChunk` ломает downstream | Оба новых поля имеют дефолты (`None` и `0`) — обратно совместимо. |
| LightRAGProjection используется в query path | Hard gate (I-RAG-1) бросает исключение; не DEGRADED. Не нарушает SEM-5 — это намеренный fail-fast. |
