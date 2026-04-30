# Spec_v55 — Phase 55: Graph-Guided Implement

Status: Draft (revised — архитектурные решения по фрикционным точкам интегрированы)
Baseline: Spec_v54_RealSystemValidation.md (Phase 54 — Real System Validation)
Revised: 2026-04-30 (интегрированы решения по 5 фрикционным точкам + предложения по расширению графа)

---

## 0. Goal

Сделать граф зависимостей обязательным навигационным слоем в IMPLEMENT-сессиях.
Файлы в `src/` доступны LLM только если они появились в выводе graph traversal
(resolve/explain/trace) от anchor nodes задачи, либо через явный fallback.
Навигация через grep запрещена.

Параллельно: заложить инфраструктуру для полной архитектурной модели системы
(Phase 56: BOUNDED_CONTEXT + LAYER), добавив MODULE nodes как первый шаг.

Результат: контекст LLM при реализации = детерминированный подграф задачи.
Каждое чтение файла обосновано graph justification или явным fallback с решением.

---

## 1. Scope

### In-Scope

- BC-55-P1: Protocol — `implement.md` (STEP 4.5) и `decompose.md` (keyword validation)
- BC-55-P2: Engine Threading — `--edge-types` flag с проброской через `ContextEngine.query()` (не post-filter)
- BC-55-P3: `TaskNavigationSpec` — изолированный тип для навигационных метаданных задачи
- BC-55-P4: Norm — `NORM-GRAPH-001` в `norm_catalog.yaml`
- BC-55-P5: Documentation — `tool-reference.md`
- BC-55-P6: NORM-SCOPE-002 Update — добавить исключение для graph-justified reads
- BC-55-P7: MODULE nodes — `MODULE:<dotted.path>` nodes + `contains` edges в графе
- BC-55-P8: Session Context — `infra/session_context.py` + `current_session.json`

### Out of Scope

См. §10.

---

## 2. Architecture / BCs

### BC-55-P1: Graph-Guided Implement Protocol

Новый STEP 4.5 вставляется в `implement.md` между STEP 4 (norm-guard) и STEP 5 (code write).
Шаг обязателен согласно SEM-13 (линейная цепочка, нельзя пропустить).

```
STEP 4.5 — Graph Discovery (MANDATORY, sequential per SEM-13):

  # 1. Anchor discovery
  sdd resolve "<keyword>" --format json
    → exit 0 required (I-DECOMPOSE-RESOLVE-1)
    → top-1 candidate kind ∈ expected_kinds (I-DECOMPOSE-RESOLVE-2)

  # 2. Dependency traversal (per anchor node found)
  sdd explain <anchor_node_id> --edge-types implements,guards,emits
    → возвращает FILE nodes, достижимые от anchor по whitelist edges
    → эти файлы получают graph justification для чтения

  # 3. Before-write trace (per file in write_scope)
  sdd trace FILE:<target> --edge-types imports
    → возвращает все dependents (кто импортирует target)
    → per I-IMPLEMENT-TRACE-1: каждый dependent MUST получить явное решение

  # Graph calls логируются автоматически через infra/graph_call_log.py (BC-55-P8 + BC-56-A1)
```

**Правило чтения файлов (I-IMPLEMENT-GRAPH-1):**
Файл может быть прочитан ТОЛЬКО если:
- (a) появился в выводе resolve/explain/trace текущей сессии, ИЛИ
- (b) явно в Task Inputs И `sdd explain FILE:X` вернул 0 edges → fallback + лог решения

**Правило записи файлов (I-IMPLEMENT-SCOPE-1):**
Файлы вне `write_scope` = read-only. Если dependent требует изменений →
LLM MUST FLAG и остановить запись до разрешения (новая задача или escalate).

**graph_budget (предупреждение, не блокировка):**
```yaml
graph_budget:
  max_graph_calls_warning: 5
  max_nodes_per_query: 20
  max_traversal_depth: 2
  traversal_edge_types_default: [implements, guards, emits]
```

---

### BC-55-P2: Engine Threading — `--edge-types` (REVISED от исходного драфта)

**Архитектурное решение:** `--edge-types` filter MUST применяться внутри BFS traversal
(в `_expand_explain` / `_expand_trace`), не как post-filter после `engine.query()`.

**Обоснование:** Post-filter даёт неверный результат — BFS пройдёт полный граф, узлы
достижимые только через отфильтрованные рёбра появятся в выводе с hop=1. Filter
на уровне CLI после сборки контекста не контролирует traversal — только вывод.

**Инвариант I-ENGINE-EDGE-FILTER-1:** edge_types filter MUST применяться в expand функции BFS,
а не после `engine.query()` или `ContextRuntime.query()`. Нарушение = silent correctness bug.

**Изменяемые файлы:**

```
src/sdd/context_kernel/engine.py     — _expand_explain, _expand_trace, ContextEngine.query()
src/sdd/context_kernel/runtime.py    — ContextRuntime.query()
src/sdd/graph_navigation/cli/explain.py — --edge-types arg parsing → передача в engine
src/sdd/graph_navigation/cli/trace.py  — --edge-types arg parsing → передача в engine
```

**Изменения сигнатур:**

```python
# engine.py — expand functions получают optional allowed_kinds
def _expand_explain(
    graph: DeterministicGraph,
    node_id: str,
    hop: int,
    *,
    allowed_kinds: frozenset[str] | None = None,
) -> list[Edge]:
    """Out-edges filtered by allowed_kinds; если None — использовать _EXPLAIN_OUT_KINDS."""
    effective_kinds = allowed_kinds if allowed_kinds is not None else _EXPLAIN_OUT_KINDS
    edges = [e for e in graph.edges_out.get(node_id, []) if e.kind in effective_kinds]
    if hop == 0:
        seed = graph.nodes.get(node_id)
        if seed and seed.kind == "TASK":
            task_allowed = allowed_kinds if allowed_kinds is not None else _EXPLAIN_TASK_IN_KINDS
            edges += [e for e in graph.edges_in.get(node_id, []) if e.kind in task_allowed]
    return edges

def _expand_trace(
    graph: DeterministicGraph,
    node_id: str,
    hop: int,
    *,
    allowed_kinds: frozenset[str] | None = None,
) -> list[Edge]:
    """In-edges filtered by allowed_kinds; если None — все in-edges."""
    if hop >= 2:
        return []
    in_edges = graph.edges_in.get(node_id, [])
    if allowed_kinds is None:
        return list(in_edges)
    return [e for e in in_edges if e.kind in allowed_kinds]

# ContextEngine.query() получает edge_types параметр
class ContextEngine:
    def query(
        self,
        graph: DeterministicGraph,
        policy: NavigationPolicy,
        doc_provider: DocProvider,
        seed: str,
        intent: QueryIntent | None = None,
        rag_client: LightRAGClient | None = None,
        edge_types: frozenset[str] | None = None,  # NEW
    ) -> NavigationResponse: ...

# ContextRuntime.query() прокидывает edge_types
class ContextRuntime:
    def query(
        self,
        graph: DeterministicGraph,
        policy: NavigationPolicy,
        index: SpatialIndex,
        node_id: str,
        edge_types: frozenset[str] | None = None,  # NEW
    ) -> NavigationResponse: ...

# CLI parsing (explain.py, trace.py)
# --edge-types implements,guards,emits → frozenset({"implements", "guards", "emits"})
# если не передан → None (backward compat: engine использует свои defaults)
```

**Backward compatibility:** без `--edge-types` поведение идентично текущему.
`--edge-types ""` (пустая строка) → ValueError с сообщением (не silent empty result).

---

### BC-55-P3: TaskNavigationSpec (REVISED от исходного драфта)

**Архитектурное решение:** Навигационные метаданные задачи (resolve_keywords, write_scope)
инкапсулируются в отдельный тип `TaskNavigationSpec`. Это изолирует эволюцию схемы
(v55 → v56 → v57) от типа `Task`.

**Обоснование:** Без изоляции `Task` dataclass будет накапливать поля трёх поколений
(Task Inputs, resolve_keywords, anchor_nodes), все с optional/deprecated статусом.
`parser.py` будет знать обо всех форматах. Deletion test: удали `TaskNavigationSpec` —
сложность переходит в `Task`, IMPLEMENT-протокол, DECOMPOSE-сессию.

**Файлы:**
```
src/sdd/tasks/navigation.py    # TaskNavigationSpec, ResolveKeyword (новый файл)
src/sdd/tasks/parser.py        # Task.navigation: TaskNavigationSpec | None
```

**Типы:**

```python
# src/sdd/tasks/navigation.py

@dataclass(frozen=True)
class ResolveKeyword:
    keyword: str
    expected_kinds: tuple[str, ...]  # ("COMMAND", "INVARIANT", ...)

@dataclass(frozen=True)
class TaskNavigationSpec:
    """Навигационные метаданные задачи. Версионированная эволюция:
      v55: resolve_keywords + write_scope (keyword-search era)
      v56: anchor_nodes + allowed_traversal + write_scope (node-id era)
      v57: только anchor_nodes (legacy fields удалены)
    """
    # Общие поля (все версии)
    write_scope: tuple[str, ...]        # FILE:path nodes

    # v55 fields (keyword-search era)
    resolve_keywords: tuple[ResolveKeyword, ...] = ()

    # v56+ fields (node-id era, populated after Phase 56)
    anchor_nodes: tuple[str, ...]       = ()  # COMMAND:X, INVARIANT:I-X, ...
    allowed_traversal: tuple[str, ...]  = ()  # edge type whitelist

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> "TaskNavigationSpec":
        """Parse from TaskSet markdown section dict.
        Supports v55 format (resolve_keywords) and v56 format (anchor_nodes).
        """
        ...

    def is_anchor_mode(self) -> bool:
        """True = v56+ (anchor_nodes present). False = v55 (resolve_keywords era)."""
        return bool(self.anchor_nodes)

@dataclass
class Task:
    # ... существующие поля ...
    navigation: TaskNavigationSpec | None = None  # None = original Task Inputs era
```

**Backward compatibility:** существующие TaskSet без `resolve_keywords` / `anchor_nodes`
секции: `Task.navigation = None`. STEP 4.5 проверяет `task.navigation is not None`.

---

### BC-55-P4: NORM-GRAPH-001

```yaml
- norm_id: NORM-GRAPH-001
  description: "LLM MAY call graph navigation commands during IMPLEMENT and DECOMPOSE sessions"
  actor: llm
  allowed_actions:
    - graph_resolve
    - graph_explain
    - graph_trace
  applies_to_sessions: [IMPLEMENT, DECOMPOSE]
  enforcement: hard
  sdd_invariant_refs:
    - I-IMPLEMENT-GRAPH-1
    - I-DECOMPOSE-RESOLVE-1
```

---

### BC-55-P5: tool-reference.md

Добавить секцию "Graph Navigation Commands (IMPLEMENT-allowed)":
- `sdd resolve` — с флагом `--format json`, использование в STEP 4.5
- `sdd explain` — с флагом `--edge-types TYPE1,TYPE2,...`, traversal от anchor
- `sdd trace` — с флагом `--edge-types TYPE1,TYPE2,...`, reverse traversal

---

### BC-55-P6: NORM-SCOPE-002 Update (NEW)

**Проблема:** NORM-SCOPE-002 текущая формулировка: *"LLM MUST NOT read src/** unless the file
is listed in Task Inputs"*. После Phase 55 graph-justified read (случай a по I-IMPLEMENT-GRAPH-1)
нарушает NORM-SCOPE-002 — файл не в `Task Inputs`, но читать его легитимно.

**Решение:** Обновить NORM-SCOPE-002 добавив второе исключение:

```yaml
- norm_id: NORM-SCOPE-002  # UPDATE
  description: "LLM MUST NOT read src/** unless authorized by Task Inputs OR graph-justified"
  exception: |
    "files explicitly listed in the task Inputs field"
    OR
    "graph-justified via NORM-GRAPH-001: file appeared in output of sdd resolve/explain/trace
     for current session (I-IMPLEMENT-GRAPH-1, condition a)"
  overridable_by: [TASK-INPUT-LAYER, NORM-GRAPH-001]
```

**Механизм переопределения:** `norm_resolution_policy.overrides` расширяется:
```yaml
overrides:
  TASK_INPUT_OVERRIDE:
    allowed_norms: [NORM-SCOPE-001, NORM-SCOPE-002]
  GRAPH_NAVIGATION_OVERRIDE:
    allowed_norms: [NORM-SCOPE-002]
    requires_norm: NORM-GRAPH-001
```

**Note:** Изменение нормы требует человеческого gate (NORM-GATE-001). BC-55-P6 описывает
намерение — фактическое изменение `norm_catalog.yaml` происходит при activate-phase 55.

---

### BC-55-P7: MODULE Nodes + contains Edges (NEW)

**Цель:** Заложить основу для BOUNDED_CONTEXT (Phase 56). MODULE nodes описывают
пакеты/директории как первый класс граф-объектов.

**Node kind:** `MODULE`
- `node_id`: `MODULE:<dotted.path>` (e.g., `MODULE:sdd.graph`, `MODULE:sdd.context_kernel`)
- `kind`: `"MODULE"`
- `label`: dotted package name
- `meta.path`: filesystem path relative to project root (e.g., `src/sdd/graph/`)

**Edge kind:** `contains` (MODULE → FILE)
- Priority: `0.45` (ниже `means: 0.50`)
- Направление: `MODULE:sdd.graph → contains → FILE:src/sdd/graph/builder.py`

**Изменяемые файлы:**

```
src/sdd/spatial/index.py         — _collect_modules() метод в IndexBuilder
src/sdd/graph/types.py           — добавить в EDGE_KIND_PRIORITY: "contains": 0.45
                                   Добавить в ALLOWED_META_KEYS: "module_path"
                                   (Полная таблица EDGE_KIND_PRIORITY после всех фаз 53-57 — в Spec_v57 §4.)
src/sdd/graph/extractors/
  module_edges.py                # ModuleEdgeExtractor (новый)
src/sdd/graph/extractors/__init__.py  — регистрация ModuleEdgeExtractor
```

**Логика IndexBuilder._collect_modules():**
```python
def _collect_modules(self) -> list[SpatialNode]:
    """Scan src/sdd/ для Python packages (директории с __init__.py).
    Создать MODULE node для каждого sub-package.
    """
    # Детерминировано: only path-based, no heuristics
    # MODULE:sdd → src/sdd/
    # MODULE:sdd.graph → src/sdd/graph/
    # MODULE:sdd.context_kernel → src/sdd/context_kernel/
    # etc.
```

**ModuleEdgeExtractor:**
```python
class ModuleEdgeExtractor:
    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: SpatialIndex) -> list[Edge]:
        """FILE nodes → belongs to MODULE node via contains edges."""
        # Для каждого FILE node: найти самый конкретный MODULE по path prefix
        # FILE:src/sdd/graph/builder.py → MODULE:sdd.graph
```

**ALLOWED_META_KEYS update:** добавить `"module_path"` в `types.py::ALLOWED_META_KEYS`.

**I-MODULE-COHESION-1 (Enhancement 4 — определяется здесь, enforcement в Phase 57):**
FILE в MODULE:M с количеством imports-edges к файлам вне MODULE:M > N (default 10)
→ нарушение когезии модуля.
  external_imports(f) = |{e : e.kind="imports", e.src=f, module(dst) ≠ M}|
  external_imports(f) > N → violation
Порог N конфигурируется в sdd_config.yaml:
  arch_check.module_cohesion_max_external_imports: 10
Detection: `sdd arch-check --check module-cohesion` (Phase 57 BC-57-6).

**Edge confidence note (Enhancement 5 — поле определяется в Phase 57 §4):**
`contains` edges (MODULE → FILE) — детерминированные, confidence = 1.0.
`calls` edges — AST-эвристики, confidence = 0.6 (см. EDGE_KIND_CONFIDENCE в Spec_v57).
Ссылки: E-4 (I-MODULE-COHESION-1), E-5 (Edge.confidence).

**Пример результата:**
```
sdd explain MODULE:sdd.graph --edge-types contains
→ возвращает все FILE nodes в src/sdd/graph/
```

---

### BC-55-P8: Session Context (NEW)

**Проблема:** Graph navigation CLIs stateless — не знают текущую `session_id`.
Phase 56 потребует `session_id` в каждой `graph_call` записи.
Без явного source каждый из трёх CLI будет иметь ad-hoc реализацию.

**Решение:**

```
src/sdd/infra/session_context.py    # новый модуль
.sdd/runtime/current_session.json   # файл с текущей сессией
```

**`current_session.json` schema:**
```json
{
  "session_id": "<uuid>",
  "session_type": "IMPLEMENT",
  "phase_id": 55,
  "declared_at": "2026-04-30T12:00:00Z"
}
```

**Кто пишет:** `sdd record-session` обновляет `current_session.json` атомарно
(via `atomic_write` из `infra/audit.py`) при объявлении сессии.

**API:**
```python
# src/sdd/infra/session_context.py

def get_current_session_id() -> str | None:
    """Read session_id from .sdd/runtime/current_session.json.
    Returns None if file absent or malformed (no-session context).
    MUST NOT raise — graph nav CLIs log calls with session_id=None if unavailable.
    """

def set_current_session(session_id: str, session_type: str, phase_id: int) -> None:
    """Write current_session.json atomically. Called by sdd record-session handler."""
```

**Использование в graph nav CLIs:** каждый из `explain.py`, `trace.py`, `resolve.py`
вызывает `get_current_session_id()` перед/после engine.query() для логирования
(логирование реализуется в Phase 56 BC-56-A1; в Phase 55 только infrastructure).

**Инвариант I-SESSION-CONTEXT-1:**
`current_session.json` MUST be written by `sdd record-session` handler only.
No other command MAY write this file directly.

---

### Dependencies

```text
BC-55-P1 → BC-55-P2 : STEP 4.5 использует --edge-types флаг (с engine threading)
BC-55-P1 → BC-55-P3 : STEP 4.5 читает resolve_keywords из TaskNavigationSpec
BC-55-P1 → BC-55-P4 : STEP 4.5 вызывает graph-команды (должны быть allowed по норме)
BC-55-P1 → BC-55-P5 : tool-reference документирует команды STEP 4.5
BC-55-P4 → BC-55-P6 : NORM-GRAPH-001 становится механизмом override для NORM-SCOPE-002
BC-55-P7 → BC-55-P8 : MODULE nodes используют session_context при логировании (Phase 56)
BC-55-P2 → BC-55-P8 : engine.query() получает session_id для audit через CLI
BC-55-P9 → BC-55-P2 : RAGPolicy передаётся через NavigationPolicy в engine.query()
```

---

### BC-55-P9: RAGPolicy Declaration + L0–L3 Architecture Hierarchy (NEW)

**Цель:** Зафиксировать архитектурный контракт RAG-слоя до его реализации.
Без явной иерархии RAG может выйти за границы graph scope и сломать детерминизм L1/L2.

**Главный инвариант (I-ARCH-LAYER-SEPARATION-1):**
```
L0: EventLog (SSOT)
L1: Graph (derived, deterministic)
L2: ContextEngine (selection, deterministic)
L3: RAG (ranking ONLY within L2 output, NON-deterministic, advisory)
```
RAG MAY ONLY reorder ContextEngine output.
RAG MUST NOT: add new nodes, remove nodes, trigger graph traversal, access filesystem.

**Новый тип `RAGPolicy` (Phase 55: объявлен, Phase 58: enforced):**

```python
# src/sdd/policy/__init__.py

@dataclass(frozen=True)
class RAGPolicy:
    """RAG pipeline constraints. Phase 55: declared. Phase 57: soft. Phase 58: hard."""
    max_documents: int = 20
    allow_global_search: bool = False   # I-RAG-SCOPE-1: MUST remain False
    min_graph_hops: int = 0

@dataclass(frozen=True)
class NavigationPolicy:
    budget: Budget
    rag_mode: RagMode
    rag_policy: RAGPolicy = field(default_factory=RAGPolicy)  # backward compat
```

**Файл:** `src/sdd/policy/__init__.py` — единственное изменение, backward compat через `field(default_factory=...)`.

**Стадия Phase 55:** `RAGPolicy` объявлен как тип. `allow_global_search=False` — default.
Enforcement (warning, exception) — Phase 57 и Phase 58 соответственно.

---

## 3. Domain Events

Новых domain events в Phase 55 нет. Graph navigation — read-only операции.
`current_session.json` — filesystem artifact, не EventStore (не нарушает I-2).

---

## 4. Types & Interfaces

### TaskNavigationSpec (BC-55-P3)

```python
# src/sdd/tasks/navigation.py
@dataclass(frozen=True)
class ResolveKeyword:
    keyword: str
    expected_kinds: tuple[str, ...]

@dataclass(frozen=True)
class TaskNavigationSpec:
    write_scope: tuple[str, ...]
    resolve_keywords: tuple[ResolveKeyword, ...] = ()
    anchor_nodes: tuple[str, ...] = ()        # Phase 56+
    allowed_traversal: tuple[str, ...] = ()   # Phase 56+

    @classmethod
    def parse(cls, raw: dict) -> "TaskNavigationSpec": ...
    def is_anchor_mode(self) -> bool: ...
```

### ContextEngine.query() / ContextRuntime.query() (BC-55-P2)

```python
# Добавляется edge_types параметр
# engine.py
def query(self, graph, policy, doc_provider, seed, intent=None, rag_client=None,
          edge_types: frozenset[str] | None = None) -> NavigationResponse: ...

# runtime.py
def query(self, graph, policy, index, node_id,
          edge_types: frozenset[str] | None = None) -> NavigationResponse: ...
```

### CLI: `sdd explain` / `sdd trace` (BC-55-P2)

```
sdd explain <node_id> [--edge-types TYPE1,TYPE2,...] [--query "текст вопроса"] [--format json|text]
sdd trace <node_id>   [--edge-types TYPE1,TYPE2,...] [--query "текст вопроса"] [--format json|text]

--edge-types: comma-separated; если не передан → None (engine defaults)
--edge-types ""       → ValueError, не silent empty result
--query: свободный текст текущего вопроса LLM/пользователя.
         Если передан → активирует Semantic Ranking Layer (L3): RAG-реранкинг context.documents.
         Если не передан → rag_mode: OFF, чистая граф-навигация (поведение без изменений).
         В tool-schema агента поле query ОБЯЗАТЕЛЬНО (query="" → rag_mode: OFF явно).
```

**I-RAG-QUERY-1:** Query НЕ является domain-событием EventLog. Логируется в `graph_calls.jsonl`
как операционный атрибут `ExecutionContext`. Replay-safety = тот же query в логах + тот же
`EmbeddingCache` composite key → идентичные векторы → идентичный порядок чанков.

### Session Context (BC-55-P8)

```python
# src/sdd/infra/session_context.py
def get_current_session_id() -> str | None: ...
def set_current_session(session_id: str, session_type: str, phase_id: int) -> None: ...
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-IMPLEMENT-GRAPH-1 | LLM MUST NOT read any `src/` file unless (a) graph-justified via resolve/explain/trace OR (b) in Task Inputs AND explain returns 0 edges (fallback — must log) | 55 |
| I-IMPLEMENT-TRACE-1 | All dependent nodes from `sdd trace` MUST receive explicit compatibility decision | 55 |
| I-IMPLEMENT-SCOPE-1 | Files outside `write_scope` are read-only; dependent changes → BLOCK + FLAG | 55 |
| I-DECOMPOSE-RESOLVE-1 | Each resolve_keywords entry MUST map to ≥1 graph candidate: exit 0 | 55 |
| I-DECOMPOSE-RESOLVE-2 | top-1 candidate kind from `sdd resolve` MUST be in `expected_kinds` | 55 |
| I-ENGINE-EDGE-FILTER-1 | edge_types filter MUST be applied inside BFS expand functions, never as post-filter after engine.query() or ContextRuntime.query() | 55 |
| I-SESSION-CONTEXT-1 | `current_session.json` MUST be written ONLY by `sdd record-session` handler | 55 |
| I-ARCH-LAYER-SEPARATION-1 | RAG MAY ONLY reorder ContextEngine output. MUST NOT add/remove nodes, trigger graph traversal, or access filesystem/graph store | 55 declared |
| I-RAG-1 | RAG MUST NOT introduce documents outside ContextEngine output. RAG role = ranking within `context.documents` only | 55 declared |
| I-RAG-SCOPE-1 | `LightRAGProjection.query()` MUST only rank documents already in `context.documents`. No filesystem read, no graph traversal, no external vector search | 55 declared |
| I-RAG-SCOPE-ENTRY-1 | `input_documents == ContextEngine.output.documents`. Verified at `LightRAGProjection` entry before any ranking. Phase 55: declared. Phase 57: soft. Phase 58: hard | 55 declared |
| I-RAG-QUERY-1 | Query используемый для RAG-реранкинга MUST логироваться в `graph_calls.jsonl` как операционный атрибут ExecutionContext. Query НЕ становится domain-событием EventLog. Replay-safety через cache composite key | 55 declared |
| I-BM25-SINGLETON-1 | BM25-индекс существует ТОЛЬКО в `SpatialIndex`. `sdd resolve` — фасад над `SpatialIndex.query_bm25()`. Не допускается вторая независимая BM25-реализация вне SpatialIndex | 55 declared |

### Preserved Invariants

| ID | Statement |
|----|-----------|
| I-2 | All write commands execute via REGISTRY |
| SEM-13 | Sequential guard chain |
| I-HANDLER-PURE-1 | handle() returns events only |
| I-ENGINE-PURE-1 | ContextEngine.query() MUST NOT call IndexBuilder, GraphService, PolicyResolver |
| I-INTENT-HEURISTIC-1 | EXPLAIN/TRACE set by CLI routing only |

---

## 6. Pre/Post Conditions

### STEP 4.5 — Graph Discovery

**Pre:**
- STEP 4 (norm-guard check) завершён с exit 0
- Session type = IMPLEMENT
- `task.navigation is not None` (иначе → fallback протокол, STEP 4.5 пропускается с лог-записью)

**Post:**
- ≥1 graph-вызов выполнен
- Каждый прочитанный файл имеет graph justification или fallback-лог
- Каждый dependent из trace имеет compatibility decision

### BC-55-P2 — engine.query() с edge_types

**Pre:** `edge_types` — корректный frozenset или None

**Post:**
- Если не None: BFS expand функции используют `edge_types` как whitelist
- Если None: поведение идентично текущему (backward compat)
- Пустой frozenset `frozenset()` → ValueError (не silent empty traversal)

### BC-55-P7 — MODULE nodes

**Pre:** `src/sdd/*/` директории существуют с `__init__.py`

**Post:**
- Каждый Python sub-package имеет MODULE node в SpatialIndex
- Каждый FILE node имеет ≥1 `contains` edge от MODULE node
- `sdd explain MODULE:sdd.X --edge-types contains` возвращает все FILE nodes пакета

---

## 7. Use Cases

### UC-55-1: IMPLEMENT с Graph Discovery (engine threading)

**Steps:**
1. LLM вызывает `sdd resolve "<keyword>" --format json`
2. LLM вызывает `sdd explain <anchor> --edge-types implements,guards,emits`
   → engine.query(..., edge_types=frozenset({"implements", "guards", "emits"}))
   → BFS использует allowed_kinds={"implements","guards","emits"} в _expand_explain
3. LLM составляет список graph-justified файлов
4. LLM вызывает `sdd trace FILE:<target> --edge-types imports`
   → engine.query(..., edge_types=frozenset({"imports"}), intent=TRACE)
   → _expand_trace фильтрует in-edges по kind="imports"
5. Только imports-dependents в результате (не все обратные рёбра)

### UC-55-2: DECOMPOSE с TaskNavigationSpec

**Steps:**
1. LLM генерирует задачу, предлагает keywords + expected_kinds
2. `sdd resolve "<keyword>" --format json` → exit 0 + top-1 валиден
3. LLM создаёт `TaskNavigationSpec(resolve_keywords=[...], write_scope=[...])`
4. TaskSet сохраняется с `task.navigation = TaskNavigationSpec(...)`
5. parser.py сериализует в Markdown секцию `Navigation:` задачи

### UC-55-3: MODULE traversal

**Steps:**
1. `sdd explain MODULE:sdd.graph --edge-types contains`
   → возвращает все FILE nodes в `src/sdd/graph/`
2. `sdd trace FILE:src/sdd/graph/builder.py --edge-types imports`
   → кто импортирует builder.py (с engine filter, только imports edges)

---

## 8. Integration

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-Graph (Phase 50) | this → BC-Graph | sdd resolve/explain/trace — graph traversal |
| ContextEngine (BC-36-3) | this extends | edge_types parameter threading |
| TaskSet schema | this extends | TaskNavigationSpec type |
| norm_catalog.yaml | this extends | NORM-GRAPH-001 + NORM-SCOPE-002 update |
| implement.md | this extends | STEP 4.5 |
| decompose.md | this extends | keyword validation step |
| Phase 56 | this → Phase 56 | MODULE nodes → BOUNDED_CONTEXT; session_context.py → GraphCallLog |

---

## 9. Verification

| # | Test / Check | Invariant(s) |
|---|--------------|--------------|
| 1 | `sdd explain NODE --edge-types implements` — BFS использует only implements edges (not post-filter: hop=1 nodes MUST be reachable via implements only) | I-ENGINE-EDGE-FILTER-1, BC-55-P2 |
| 2 | `sdd trace FILE:X --edge-types imports` — возвращает только imports-dependents | I-ENGINE-EDGE-FILTER-1, BC-55-P2 |
| 3 | `_expand_explain(graph, node, 0, allowed_kinds=frozenset({"implements"}))` unit test без CLI | BC-55-P2 |
| 4 | `ContextRuntime.query(..., edge_types=frozenset())` → ValueError | BC-55-P2 |
| 5 | TaskSet с `resolve_keywords` + `write_scope` → `TaskNavigationSpec` парсится корректно | BC-55-P3 |
| 6 | TaskSet без навигационных полей → `task.navigation = None` | BC-55-P3 |
| 7 | `sdd norm-guard check --actor llm --action graph_resolve` → exit 0 после NORM-GRAPH-001 | BC-55-P4 |
| 8 | MODULE:sdd.graph exists в SpatialIndex после nav-rebuild | BC-55-P7 |
| 9 | `sdd explain MODULE:sdd.graph --edge-types contains` возвращает builder.py, service.py и т.д. | BC-55-P7 |
| 10 | `get_current_session_id()` возвращает None если `current_session.json` отсутствует | BC-55-P8 |
| 11 | `sdd record-session` обновляет `current_session.json` корректно | BC-55-P8 |
| 12 | DECOMPOSE с невалидным keyword (resolve exit 1) → STOP | I-DECOMPOSE-RESOLVE-1 |

---

## 11. Phase Acceptance Checklist

> Методология: `.sdd/docs/ref/phase-acceptance.md`

### Part 1 — In-Phase DoD

**Step U (Universal):**
```bash
sdd show-state                          # tasks_completed == tasks_total
sdd validate --check-dod --phase 55     # exit 0
python3 -m pytest tests/unit/ -q        # 0 failures
```

**Step 55-A — Engine threading (I-ENGINE-EDGE-FILTER-1):**
```bash
# BFS filter применяется внутри expand, не как post-filter
sdd explain COMMAND:complete --edge-types implements,guards --format json
# → все nodes на hop=1 достижимы ТОЛЬКО через implements или guards
# → нет nodes, достигнутых через другие edge kinds

sdd trace FILE:src/sdd/graph/builder.py --edge-types imports --format json
# → только imports-edges в результате (не все in-edges)

# Пустой frozenset → ошибка, не молчаливый пустой результат
sdd explain COMMAND:complete --edge-types "" 2>&1 | grep -i "error\|invalid"
# → должен вывести ошибку
```

**Step 55-B — MODULE nodes (BC-55-P7):**
```bash
sdd graph-stats --node-type MODULE --format json
# → {"count": N}, N > 0

sdd explain MODULE:sdd.graph --edge-types contains --format json
# → возвращает FILE nodes из src/sdd/graph/

sdd explain MODULE:sdd.context_kernel --edge-types contains --format json
# → возвращает FILE nodes из src/sdd/context_kernel/
```

**Step 55-C — TaskNavigationSpec (BC-55-P3):**
```bash
# TaskSet с resolve_keywords секцией → task.navigation != None
# TaskSet без навигации → task.navigation = None (без ошибки)
python3 -c "from sdd.tasks.navigation import TaskNavigationSpec; print('OK')"
# → OK
```

**Step 55-D — Session Context (BC-55-P8):**
```bash
sdd record-session --type IMPLEMENT --phase 55
cat .sdd/runtime/current_session.json
# → {"session_id": "...", "session_type": "IMPLEMENT", "phase_id": 55, "declared_at": "..."}
```

---

### Part 2 — Regression Guard

Следующие команды должны давать тот же результат что и на Phase 52:

```bash
# (R-55-1) sdd explain без --edge-types — поведение идентично Phase 52
sdd explain COMMAND:complete --format json
# → те же nodes что и до Phase 55 (backward compat: allowed_kinds=None)

# (R-55-2) sdd trace без --edge-types — поведение идентично Phase 52
sdd trace FILE:src/sdd/graph/builder.py --format json
# → те же nodes что и до Phase 55

# (R-55-3) sdd resolve не затронут
sdd resolve "complete" --format json
# → результат аналогичен Phase 52
```

Если хоть одна регрессия → **STOP → sdd report-error → recovery.md**.

---

### Part 3 — Transition Gate (before Phase 56)

Человек верифицирует перед `sdd activate-phase 56`:

```bash
# Gate 56-A: TestedByEdgeExtractor (Phase 53 COMPLETE required)
sdd graph-stats --edge-type tested_by --format json
# Expected: {"count": N}, N > 0
# Если 0 → Phase 53 не завершена → Phase 56 BLOCKED

# Gate 56-B: MODULE nodes из Phase 55
sdd explain MODULE:sdd.graph --edge-types contains --format json
# Expected: ≥1 FILE node в результате

# Gate 56-C: sdd_config.yaml содержит bounded_contexts секцию
python3 -c "import yaml; c=yaml.safe_load(open('.sdd/config/sdd_config.yaml')); assert 'bounded_contexts' in c, 'MISSING'"
# Expected: exit 0 (нет AssertionError)
# Если MISSING → добавить конфиг по шаблону в phase-acceptance.md §5 ПЕРЕД активацией 56
```

---

### Part 4 — Rollback Triggers

Немедленно STOP если:
- `sdd explain COMMAND:complete --format json` возвращает меньше nodes чем до Phase 55
- `sdd explain COMMAND:complete --edge-types implements` возвращает nodes с hop=1 через НЕ-implements edges
- `sdd graph-stats --node-type MODULE` → `count: 0` (MODULE nodes не построены)
- `current_session.json` записан НЕ через `sdd record-session` (нарушение I-SESSION-CONTEXT-1)
- Любой unit тест упавший до Phase 55 начинает падать снова

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `GraphCallLog` module (`graph_calls.jsonl`) + typed API | Phase 56 (BC-56-A1) |
| `sdd record-metric` (MetricRecorded event) | Phase 56 (BC-56-A2) |
| `sdd graph-guard check` (enforcement) | Phase 56 (BC-56-G1) |
| `sdd graph-stats` | Phase 56 (BC-56-G2) |
| `TestedByEdgeExtractor` | Phase 53 (Spec_v53_GraphTestFilter.md) — Phase 56 gate dependency |
| `TaskNavigationSpec` v2 — anchor_nodes (замена resolve_keywords) | Phase 56 (BC-56-S1) |
| Score нормализация в `sdd resolve` | Phase 56 (BC-56-S2) |
| `BOUNDED_CONTEXT` nodes + `belongs_to` edges | Phase 56 (BC-56-BC) |
| `LAYER` nodes + `in_layer` edges + `calls` edges | Phase 56 (BC-56-LAYER) |
| Удаление Task Inputs / resolve_keywords из parser.py | Phase 57 (BC-57-1) |
| `ViolatesEdgeExtractor` + `sdd arch-check` | Phase 57 (BC-57-3) |
| I-ARCH-1/2/3 invariants (graph-enforced layer compliance) | Phase 57 (BC-57-2) |
| graph-guard v2 (anchor_nodes coverage) | Phase 57 (BC-57-4) |
| `graph_coverage` marker в SpatialIndex.meta | Phase 57 (BC-57-5) |
| I-RAG-1 / I-RAG-SCOPE-1 soft enforcement (warning + degrade) | Phase 57 (BC-57-RAG-SOFT) |
| `NavigationResponse.based_on` explainability field | Phase 57 (BC-57-RAG-SOFT) |
| `I-NAV-BASED-ON-1` (based_on non-None enforcement) | Phase 57 (BC-57-RAG-SOFT) |
| `EmbeddingProvider` Protocol + `EmbeddingCache` | Phase 58 (BC-58-RAG) |
| `rank_documents()` pure function (RAGRanker) | Phase 58 (BC-58-RAG) |
| I-RAG-1 hard enforcement (RAGPolicyViolation exception) | Phase 58 (BC-58-RAG) |
| I-RAG-DETERMINISTIC-1 (ranking determinism + lexical tie-breaker) | Phase 58 (BC-58-RAG) |
| I-EMBED-CACHE-1 (composite cache key) | Phase 58 (BC-58-RAG) |
| I-CHUNK-DETERMINISTIC-1 (AST-boundary chunking) | Phase 58 (BC-58-RAG) |
