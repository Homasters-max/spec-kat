# Spec_v57 — Phase 57: Graph as Architectural SSOT

Status: Draft
Baseline: Spec_v56_GraphFirst.md (Phase 56 — Graph-First + Architecture Context)
Created: 2026-04-30

---

## 0. Goal

Граф становится единственным источником архитектурной истины (SSOT).

Три задачи фазы:

1. **Legacy cleanup** — удалить `Task Inputs` и `resolve_keywords` из `parser.py`;
   единственный навигационный формат = `anchor_nodes` + `TaskNavigationSpec`.

2. **Архитектурные инварианты** — `I-ARCH-1/2/3` вводятся как формальные инварианты,
   проверяемые через граф командой `sdd arch-check`.

3. **graph-guard v2** — вместо `count(graph_calls) ≥ 1` проверяет,
   что *все* `anchor_nodes` задачи были traversed хотя бы раз.

**Phase Gate (перед PLAN Phase 57):**
```bash
sdd arch-check --format json
# → {"violations": 0} required
# count > 0 → Phase 57 BLOCKED до исправления архитектурных нарушений
```

Человек запускает `sdd arch-check` и принимает решение после Phase 56 COMPLETE.

---

## 1. Scope

### In-Scope

- BC-57-BUILD-PIPELINE: GraphBuild pipeline phases (raw→classified→derived→validated) + I-GRAPH-BUILD-PIPELINE-1
- BC-57-1: Legacy Cleanup — удаление `Task Inputs` / `resolve_keywords` из `parser.py`
- BC-57-2: I-ARCH Invariants — формализация I-ARCH-1/2/3 как проверяемых правил
- BC-57-3: `ViolatesEdgeExtractor` + `sdd arch-check` — детекция нарушений слоёв (с формальной violations formula)
- BC-57-4: graph-guard v2 — anchor_nodes coverage enforcement (I-GRAPH-GUARD-3 + I-GRAPH-GUARD-4)
- BC-57-5: `graph_coverage` marker в `SpatialIndex.meta` (числовой + multi-type)
- BC-57-6: `sdd arch-check --check module-cohesion` — enforcement I-MODULE-COHESION-1
- BC-57-7: `sdd arch-check --check bc-cross-dependencies` — enforce I-BC-CONSISTENCY-1 violations (cycles → exit 1)
- BC-57-RAG-SOFT: RAG soft enforcement — `NavigationResponse.based_on` + `LightRAGProjection` soft guard

### Out of Scope

См. §10.

---

## 2. Architecture / BCs

### BC-57-BUILD-PIPELINE: GraphBuild Pipeline Phases (NEW — D-1)

**Проблема:** `GraphFactsBuilder.build()` выполняет все экстракторы в одном pass.
`CrossBCEdgeExtractor` (derived edge) не может читать `belongs_to` edges (classified edge)
из того же build pass → дублирует логику классификации → риск рассинхрона.

**Решение:** 4 последовательные стадии с передачей промежуточного графа между ними:

```
raw        — прямые экстракторы (ASTEdgeExtractor, GlossaryEdgeExtractor, ImplementsEdgeExtractor, ...)
classified  — path-based классификация (BoundedContextEdgeExtractor, LayerEdgeExtractor)
             CrossBCEdgeExtractor получает уже собранный raw+classified граф
derived    — производные рёбра (CrossBCEdgeExtractor, ViolatesEdgeExtractor)
validated  — финальный граф после arch-check invariant validation
```

**Реализация в builder.py:**
Каждый экстрактор декларирует атрибут `pipeline_stage`:
```python
class BoundedContextEdgeExtractor:
    pipeline_stage: ClassVar[Literal["raw","classified","derived","validated"]] = "classified"

class CrossBCEdgeExtractor:
    pipeline_stage: ClassVar[str] = "derived"
    # В extract() читает existing_graph: DeterministicGraph (raw+classified edges уже есть)
```

`GraphFactsBuilder` разбивает `extractors` на 4 группы по `pipeline_stage`,
выполняет группы последовательно, передаёт накопленный граф `derived` экстракторам.

**Инвариант I-GRAPH-BUILD-PIPELINE-1:**
`arch-check` и `graph-guard` ДОЛЖНЫ работать ТОЛЬКО с `derived`/`validated` edges.
Прямое использование `raw` edges для arch-проверок запрещено.
Нарушение → `GraphInvariantError` с message "arch-check requires derived/validated stage".

**Файлы:**
```
src/sdd/graph/builder.py           # pipeline_stage grouping + sequential execution
src/sdd/graph/extractors/__init__.py  # pipeline_stage attr в EdgeExtractor protocol
```

---

### BC-57-1: Legacy Navigation Cleanup

**Цель:** Устранить three-generation schema drift из `parser.py` и `TaskNavigationSpec`.
После Phase 57 единственный валидный навигационный формат — `anchor_nodes`.

**Удаляется:**
```
src/sdd/tasks/navigation.py
  - ResolveKeyword dataclass           (Phase 55, deprecated с Phase 56)
  - TaskNavigationSpec.resolve_keywords field
  - TaskNavigationSpec.is_anchor_mode()  # всегда True теперь

src/sdd/tasks/parser.py
  - Parsing logic for "Inputs:" section   (original era)
  - Parsing logic for "resolve_keywords:" (Phase 55 era)
```

**После удаления `TaskNavigationSpec`:**
```python
@dataclass(frozen=True)
class TaskNavigationSpec:
    """Phase 57+: только anchor_nodes era. resolve_keywords и Inputs удалены."""
    anchor_nodes: tuple[str, ...]        # COMMAND:X, INVARIANT:I-X, FILE:path, ...
    allowed_traversal: tuple[str, ...]   # edge type whitelist
    write_scope: tuple[str, ...]         # FILE:path nodes
```

**Инвариант I-TASK-INPUTS-REMOVED:**
`parser.py` MUST NOT parse `Inputs:` or `resolve_keywords:` sections.
If detected in TaskSet → `ParseError` с явным сообщением "legacy format: upgrade to anchor_nodes".

**Migration path:** TaskSet Phase 55/56 с `resolve_keywords` нужно обновить перед Phase 57.
Инструмент: `sdd migrate-taskset --from resolve_keywords --to anchor_nodes` (BC-57-1 опция).

**Инвариант I-ANCHOR-REQUIRED:**
В Phase 57+ каждая задача со статусом TODO MUST иметь `TaskNavigationSpec` с непустым
`anchor_nodes`. Задача без `anchor_nodes` → `norm-guard` блокирует IMPLEMENT.

---

### BC-57-2: I-ARCH Invariants

**Цель:** Формализовать архитектурные инварианты, которые граф теперь может проверить.

Граф Phase 56 содержит: `BOUNDED_CONTEXT` nodes, `LAYER` nodes, `belongs_to` edges,
`in_layer` edges, `imports` edges, `calls` edges. Этого достаточно для трёх проверок.

**Три инварианта:**

| ID | Statement | Check mechanism |
|----|-----------|-----------------|
| I-ARCH-1 | No circular dependencies between BOUNDED_CONTEXTs: `imports/calls` edges MUST NOT form a cycle across BOUNDED_CONTEXT boundaries | `sdd arch-check --check bc-cycles` |
| I-ARCH-2 | LAYER:domain MUST NOT have `imports` or `calls` edges → LAYER:infrastructure | `sdd arch-check --check layer-purity` |
| I-ARCH-3 | Dependency direction MUST be interface → application → domain only. Reverse direction (domain → application, application → interface) MUST NOT exist via `imports/calls` | `sdd arch-check --check layer-direction` |

**Проверка через граф:**

```
I-ARCH-1 (BC cycles):
  1. Для каждой пары (BOUNDED_CONTEXT:A, BOUNDED_CONTEXT:B):
     найти FILE nodes в A, у которых есть imports/calls → FILE nodes в B
  2. Построить граф BC-зависимостей
  3. Cycle detection (DFS) → список циклических пар

I-ARCH-2 (domain purity):
  1. domain_files = {n for n with in_layer → LAYER:domain}
  2. infra_files = {n for n with in_layer → LAYER:infrastructure}
  3. Найти: FILE ∈ domain_files имеет imports/calls → FILE ∈ infra_files
  4. Каждое такое ребро = violation

I-ARCH-3 (layer direction):
  Допустимые направления: interface→application, interface→domain,
                          application→domain, domain→(ничего выше)
  Запрещённые: domain→application, domain→interface,
               application→interface, infrastructure→domain,
               infrastructure→application, infrastructure→interface
  Проверить: существуют ли imports/calls edges в запрещённых направлениях
```

**Файл конфигурации проверок** (в `sdd_config.yaml`):
```yaml
arch_check:
  enabled_checks:
    - bc-cycles
    - layer-purity
    - layer-direction
    - bc-cross-dependencies     # NEW (E-1, Phase 57 enforcement)
    - module-cohesion            # NEW (E-4)
  coverage_full_threshold: 0.9  # NEW (E-2, D-3)
  module_cohesion_max_external_imports: 10  # NEW (E-4)
  guard_reachability_max_hops: 3            # NEW (D-4)
  ignore_patterns:
    - "src/sdd/cli.py"   # top-level entry point — intentionally imports everything
```

---

### BC-57-3: ViolatesEdgeExtractor + sdd arch-check

**ViolatesEdgeExtractor:**

```
src/sdd/graph/extractors/violates_edges.py    # ViolatesEdgeExtractor (новый)
```

Edge kind: `violates` (FILE → INVARIANT)
- Priority: `0.92` (высокий — рядом с `emits:0.95`, т.к. violations критичны)
- Направление: `FILE:src/sdd/context_kernel/engine.py → violates → INVARIANT:I-ARCH-2`

```python
class ViolatesEdgeExtractor:
    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: SpatialIndex) -> list[Edge]:
        """Detect architectural violations and emit violates edges.

        For each check in arch_check config:
          - Run graph query (using in-memory graph via index)
          - For each violating FILE → emit Edge(src=FILE, dst=INVARIANT:I-ARCH-X, kind="violates")

        Sources index only (I-GRAPH-FS-ISOLATION-1): all data via index.read_content() and iter_*.
        """
```

**Формальное определение violations (D-6, уточнение I-ARCH-CONFIDENCE-1):**
```
violations(arch-check) = {e : e.kind="imports", violates_rule(e)}
                       ∪ {e : e.kind="calls", e.confidence ≥ 0.9, violates_rule(e)}
```
В текущей конфигурации `EDGE_KIND_CONFIDENCE["calls"] = 0.6` → второе множество пусто.
Calls edges с confidence < 0.9 → WARNING only, никогда не exit 1.
Если в будущем calls extractor улучшится и confidence пересечёт порог → автоматически станет violation.

**sdd arch-check command:**

```bash
sdd arch-check [--check bc-cycles|layer-purity|layer-direction|bc-cross-dependencies|module-cohesion|all] [--format json|text]

# Алгоритм:
# 1. Build graph (via GraphService)
# 2. Query violates edges: graph.edges_out per FILE, kind="violates"
# 3. Count violations grouped by check type
# 4. Exit 0 → no violations
# 5. Exit 1 → violations found, report in JSON/text

# JSON output:
{
  "violations": [
    {
      "check": "layer-purity",
      "file": "FILE:src/sdd/context_kernel/engine.py",
      "invariant": "INVARIANT:I-ARCH-2",
      "detail": "domain imports infrastructure: sdd.infra.paths"
    }
  ],
  "total": 1
}
```

**Read-only command (не через REGISTRY write pipeline).**

**Integrate с `sdd validate-invariants`:**
`validate-invariants` вызывает `sdd arch-check --format json` как sub-check.
Ненулевые violations → отчёт нарушения I-ARCH-* в общем выводе.

---

### BC-57-4: graph-guard v2 — anchor_nodes Coverage

**Проблема Phase 56 graph-guard:** проверяет `count(graph_calls) ≥ 1` для сессии.
Можно выполнить один `sdd explain` над несвязанным узлом — guard пройдёт.
Реальная цель: все `anchor_nodes` задачи должны быть traversed.

**Решение:**

```
GraphCallEntry v2 (расширение BC-56-A1):
  + nodes_covered: list[str]   # node IDs, возвращённые в response.context.nodes
```

```python
@dataclass(frozen=True)
class GraphCallEntry:
    command: str
    args: dict[str, Any]
    session_id: str | None
    ts: str
    result_size: dict[str, int]
    nodes_covered: tuple[str, ...] = ()   # NEW в Phase 57
```

**sdd graph-guard check v2 (обновление BC-56-G1):**
```bash
sdd graph-guard check --task T-NNN [--session-id <id>]
# Phase 57 logic:
# 1. task = load_task(T-NNN)
# 2. anchor_nodes = task.navigation.anchor_nodes
# 3. calls = query_graph_calls(session_id)
# Step 4 (I-GRAPH-GUARD-3): считаем только calls с edges > 0
#    covered = union(c.nodes_covered for c in calls if c.result_size.get("edges", 0) > 0)
#    Seed-only записи (edges==0) НЕ вносят вклад в covered
# Step 5 (I-GRAPH-GUARD-4): reachability check
#    reachable = undirected_bfs(anchor_nodes, graph, max_hops=guard_reachability_max_hops)
#    covered_relevant = covered ∩ reachable
#    if not covered_relevant → exit 1 (coverage есть, но изолирована от anchors)
# Step 6:
#    uncovered = set(anchor_nodes) - covered
#    uncovered == {} AND covered_relevant → exit 0
#    otherwise → exit 1, report uncovered + reachability info
```

**Инвариант I-GRAPH-GUARD-3 (E-3 — Issue I-5 fix):**
`nodes_covered` включает seed node даже при 0 edges → loophole.
`GraphCallEntry` вносит вклад в `covered` ТОЛЬКО если `result_size["edges"] > 0`.
Seed-only записи (edges==0) НЕ считаются покрытием.

**Инвариант I-GRAPH-GUARD-4 (D-4 — reachability):**
`covered ∩ reachable_from(anchor_nodes, hops ≤ guard_reachability_max_hops) ≠ ∅`.
Изолированное coverage (все covered nodes недостижимы от anchors) → exit 1.
Порог: `sdd_config.yaml: arch_check.guard_reachability_max_hops: 3` (default).

**Инвариант I-GRAPH-GUARD-2:**
Each IMPLEMENT session MUST have at least one `GraphCallEntry` covering each
`anchor_node` in `task.navigation.anchor_nodes`.
`covered(anchor_nodes) = union(entry.nodes_covered for entry in session_calls)`.
`I-GRAPH-GUARD-2` supersedes `I-GRAPH-GUARD-1` in Phase 57.

**Backward compat:** `nodes_covered = ()` в старых записях → guard считает как uncovered.
Для задач Phase 56 (без anchor_nodes) → guard не применяется (I-GRAPH-GUARD-1 остаётся).

---

### BC-57-5: graph_coverage Marker (E-2 + D-3)

**Цель:** Явно маркировать неполноту покрытия графом. Предотвращает "ложное чувство безопасности".
Multi-type coverage (D-3): `belongs_to + in_layer` ≠ полное архитектурное покрытие —
COMMAND и INVARIANT nodes также должны классифицироваться.

**Количественный критерий (E-2 — Issue I-4 resolution):**
```python
coverage_score = covered_file_nodes / total_file_nodes
# covered_file_nodes = FILE nodes с ОБОИМИ belongs_to И in_layer edges
# total_file_nodes   = все FILE nodes в src/

FULL_THRESHOLD = 0.90   # configurable: arch_check.coverage_full_threshold
```

**Multi-type coverage (D-3):**
```python
# SpatialIndex.meta["graph_coverage"]:
{
    "coverage": "partial" | "full",
    "coverage_score": float,          # covered_file_nodes / total_file_nodes, 0.0-1.0
    "coverage_threshold": float,      # порог (default 0.9)
    "coverage_by_type": {             # D-3: multi-type breakdown
        "file":      {"covered": int, "total": int, "score": float},
        "command":   {"covered": int, "total": int, "score": float},
        "invariant": {"covered": int, "total": int, "score": float},
    },
    "missing_classifications": list[str],
    "bounded_contexts_covered_pct": int,
    "layers_covered_pct": int,
}
```

**"full" условие (обновлено D-3):**
`coverage_score >= FULL_THRESHOLD` AND `command.score >= 0.7` AND `invariant.score >= 0.7`.
Все три пороги configurable в `sdd_config.yaml` под `arch_check.*`.

**"partial":** любой из порогов не достигнут.

**Где используется:**
- `sdd arch-check` предупреждает если `coverage = "partial"`: *"arch-check results are incomplete — unclassified files may contain violations"*
- `sdd graph-stats` показывает coverage summary по типам

**Инвариант I-GRAPH-COVERAGE-1:**
`SpatialIndex.meta["graph_coverage"]` MUST be set by `IndexBuilder`.
`sdd arch-check` with `coverage = "partial"` MUST emit `[WARNING] partial coverage` to stderr.
Partial coverage MUST NOT cause exit 1 (only warning).

**Инвариант I-GRAPH-COVERAGE-2 (новый — E-2):**
`IndexBuilder` ДОЛЖЕН вычислять `coverage_score = covered_file_nodes / total_file_nodes`.
`"full"` iff `coverage_score >= arch_check.coverage_full_threshold` (default 0.9)
AND `command.score >= 0.7` AND `invariant.score >= 0.7`.

---

### BC-57-6: sdd arch-check --check module-cohesion (E-4)

**I-MODULE-COHESION-1 enforcement (определён в Phase 55, enforced здесь):**

Для каждого FILE:f в MODULE:M:
```python
external_imports(f) = |{imports edges f→g : module(g) ≠ M}|
external_imports(f) > N (default 10) → cohesion violation
```

Confidence filter: считаются ТОЛЬКО imports edges с confidence >= 0.9.
`calls` edges (confidence=0.6) исключаются — I-ARCH-CONFIDENCE-1.

`sdd arch-check --check module-cohesion` использует `contains` in-edges для определения
MODULE содержимого, затем `imports` out-edges для подсчёта external imports.

```bash
sdd arch-check --check module-cohesion --format json
→ {"violations": [{"file": "FILE:src/sdd/...", "module": "MODULE:graph",
                   "external_imports": 12, "limit": 10}]}
```

Verification:
- FILE с 11 imports вне MODULE → violation
- FILE с 9 imports вне MODULE → no violation
- calls edges (confidence=0.6) не учитываются

---

### BC-57-7: sdd arch-check --check bc-cross-dependencies enforcement (E-1 Phase 57)

**Phase 56 (BC-56-BC-2):** cross_bc_dependency edges эмитируются, проверка информационная (exit 0).
**Phase 57 (здесь):** enforcement — циклические cross-BC зависимости → exit 1.

```
Алгоритм bc-cross-dependencies enforcement:
1. Собрать все cross_bc_dependency edges: FILE → BOUNDED_CONTEXT
2. Построить граф BC → BC зависимостей:
   для каждого FILE:f (belongs_to→BC:A), имеющего cross_bc_dependency→BC:B:
     добавить ребро A → B в BC-граф
3. DFS cycle detection на BC-графе
4. Cycle → exit 1, report с деталями цикла
5. No cycle → exit 0
```

Информационный отчёт без exit 1 (Phase 56 поведение) сохраняется через:
`sdd arch-check --check bc-cross-dependencies --severity info`

---

### BC-57-RAG-SOFT: RAG Soft Enforcement + Explainability (NEW)

**Цель:** Начать применение I-ARCH-LAYER-SEPARATION-1 (Phase 55 declared) на L3 границе.
Phase 57 = soft enforcement (warning + degrade). Phase 58 = hard enforcement (exception).

**Архитектурный принцип:**
```
ContextEngine (deterministic L2)
  ↓ context.documents (sealed at entry gate)
LightRAGProjection (L3 adapter, soft guard Phase 57)
  ↓
RAG ranking (advisory, non-deterministic)
```

**Изменяемые файлы:**

```
src/sdd/context_kernel/rag_types.py   — based_on поле + soft enforcement в LightRAGProjection
src/sdd/context_kernel/engine.py      — заполнять based_on из selection.nodes.keys()
```

**`NavigationResponse.based_on` (I-NAV-BASED-ON-1):**

```python
@dataclass
class NavigationResponse:
    context: Context
    rag_summary: str | None
    rag_mode: str | None
    candidates: list[SearchCandidate] | None
    based_on: list[str] | None = None  # NEW: ["FILE:X", "COMMAND:Y", "INVARIANT:Z"]
```

Заполняется в `engine.py`:
```python
return NavigationResponse(
    ...,
    based_on=list(selection.nodes.keys()),  # deterministic: selection always computed before RAG
)
```

**Soft enforcement в `LightRAGProjection.query()`:**

```python
def query(self, question, context, rag_mode, rag_client, rag_policy=None):
    # I-RAG-SCOPE-1 soft enforcement (Phase 57):
    if rag_policy is not None and rag_policy.allow_global_search:
        import warnings
        warnings.warn(
            "I-RAG-SCOPE-1: allow_global_search=True violates I-ARCH-LAYER-SEPARATION-1; "
            "degrading to LOCAL (graph-scoped) mode",
            RuntimeWarning,
        )
        rag_mode = RagMode.LOCAL

    # I-RAG-SCOPE-ENTRY-1 soft (Phase 57): seal input at L2/L3 boundary
    # Phase 58 will assert; Phase 57 logs for observability
    allowed_ids = {d.node_id for d in getattr(context, "documents", [])}
    if allowed_ids:
        import logging
        logging.debug("RAG entry gate: allowed document scope = %d docs", len(allowed_ids))
    # ... rest of existing query() logic unchanged
```

**Backward compatibility:** `rag_policy` — опциональный параметр (default `None`).
Существующие вызовы без `rag_policy` работают без изменений.

**Phase 57 — НЕ изменяет:**
- `ContextEngine.query()` signature (I-ENGINE-PURE-1 preserved)
- `LightRAGProjection.__init__()` (I-LIGHTRAG-CANONICAL-1 preserved)
- `NavigationPolicy` loading (rag_policy propagated via caller, not engine)

---

### Dependencies

```text
BC-57-1 → BC-56-S1 (Phase 56) : anchor_nodes format established
BC-57-2 → BC-56-BC (Phase 56) : BOUNDED_CONTEXT nodes required for I-ARCH-1
BC-57-2 → BC-56-LAYER (Phase 56) : LAYER nodes required for I-ARCH-2/3
BC-57-3 → BC-57-2 : ViolatesEdgeExtractor implements I-ARCH checks
BC-57-4 → BC-57-1 : anchor_nodes required (no resolve_keywords fallback)
BC-57-4 → BC-56-A1 (Phase 56) : extends GraphCallEntry with nodes_covered
BC-57-5 → BC-56-BC + BC-56-LAYER : coverage computed from belongs_to + in_layer completeness
BC-57-RAG-SOFT → BC-55-P9 (Phase 55) : RAGPolicy declared; Phase 57 adds soft enforcement
BC-57-RAG-SOFT → BC-57-3 : arch-check framework validates I-ARCH-LAYER-SEPARATION-1 context
```

---

## 3. Domain Events

Новых domain events в Phase 57 нет.
`sdd arch-check` — read-only. `ViolatesEdgeExtractor` — build-time artifact, не EventStore.
`graph_coverage` — computed field в SpatialIndex, не state mutation.

---

## 4. Types & Interfaces

### TaskNavigationSpec v3 (BC-57-1)

```python
# src/sdd/tasks/navigation.py — Phase 57 final form

@dataclass(frozen=True)
class TaskNavigationSpec:
    anchor_nodes: tuple[str, ...]        # REQUIRED в Phase 57+
    allowed_traversal: tuple[str, ...]   # edge type whitelist
    write_scope: tuple[str, ...]         # FILE:path nodes
    # resolve_keywords и Inputs УДАЛЕНЫ

    @classmethod
    def parse(cls, raw: dict) -> "TaskNavigationSpec":
        """Raises ParseError if legacy fields (Inputs, resolve_keywords) detected."""
        ...
```

### GraphCallEntry v2 (BC-57-4)

```python
@dataclass(frozen=True)
class GraphCallEntry:
    command: str
    args: dict[str, Any]
    session_id: str | None
    ts: str
    result_size: dict[str, int]
    nodes_covered: tuple[str, ...] = ()  # NEW: node IDs in response.context.nodes
```

### sdd arch-check (BC-57-3)

```python
# sdd arch-check [--check bc-cycles|layer-purity|layer-direction|all] [--format json|text]
# Exit 0: no violations (or coverage=partial with warning)
# Exit 1: violations found

@dataclass(frozen=True)
class ArchViolation:
    check: str           # "bc-cycles" | "layer-purity" | "layer-direction"
    file_node: str       # FILE:...
    invariant: str       # INVARIANT:I-ARCH-*
    detail: str          # human-readable

@dataclass(frozen=True)
class ArchCheckResult:
    violations: tuple[ArchViolation, ...]
    coverage: str        # "partial" | "full"
    coverage_warnings: tuple[str, ...]
```

### SpatialIndex.meta["graph_coverage"] (BC-57-5)

```python
{
    "coverage": "partial" | "full",
    "coverage_score": float,          # covered_file_nodes / total_file_nodes
    "coverage_threshold": float,      # default 0.9
    "coverage_by_type": {             # D-3: multi-type
        "file":      {"covered": int, "total": int, "score": float},
        "command":   {"covered": int, "total": int, "score": float},
        "invariant": {"covered": int, "total": int, "score": float},
    },
    "missing_classifications": list[str],
    "bounded_contexts_covered_pct": int,
    "layers_covered_pct": int,
}
```

### Edge.confidence field + EDGE_KIND_CONFIDENCE (E-5 — Issue I-7)

**Добавить в `src/sdd/graph/types.py`:**

1. Новое поле в Edge dataclass (backward compatible — default 1.0):
```python
@dataclass(frozen=True)
class Edge:
    # ... существующие поля ...
    confidence: float = 1.0   # extraction reliability, 0.0-1.0
    # __post_init__: добавить проверку 0.0 <= confidence <= 1.0
```

2. Новый словарь EDGE_KIND_CONFIDENCE:
```python
EDGE_KIND_CONFIDENCE: dict[str, float] = {
    "emits": 1.0, "guards": 1.0, "implements": 1.0,
    "tested_by": 1.0, "verified_by": 1.0, "depends_on": 1.0,
    "introduced_in": 1.0, "imports": 1.0, "means": 1.0,
    "contains": 1.0,           # deterministic path-based
    "belongs_to": 1.0,         # deterministic path-based
    "in_layer": 1.0,           # deterministic path-based
    "cross_bc_dependency": 1.0, # derived from belongs_to + imports
    "violates": 1.0,           # computed rule-based
    "calls": 0.6,              # AST heuristics — misses dynamic dispatch
}
```

**I-ARCH-CONFIDENCE-1:**
`sdd arch-check --check layer-purity` и `--check layer-direction` ДОЛЖНЫ использовать
ТОЛЬКО edges с confidence >= 0.9 для VIOLATIONS (exit 1).
Edges с confidence < 0.9 (calls = 0.6) → WARNING only, никогда не exit 1.
Formalized: `violations = {e : kind="imports", violates} ∪ {e : kind="calls", confidence≥0.9, violates}`

**Backward compatibility:** confidence = 1.0 as default — существующий код не ломается.
Сериализация: "confidence" key в JSON (отсутствие → читается как 1.0).

### path_confidence в RankedNode (D-5)

**Добавить в `src/sdd/context_kernel/selection.py`:**

```python
@dataclass
class RankedNode:
    node_id: str
    hop: int
    global_importance_score: float
    path_confidence: float = 1.0  # NEW: Π(edge.confidence) на пути от seed
```

**BFS обновляет path_confidence:**
```python
child.path_confidence = parent.path_confidence * edge.confidence
```
Nodes с `path_confidence < context.min_path_confidence` (default 0.5) не включаются в Selection.
Seed node (hop=0): всегда `path_confidence = 1.0` (I-CONTEXT-SEED-1 preserved).

**Сортировка в `sdd explain` output:**
edges сортируются по `(hop, -edge.confidence, -priority, edge_id)`.

`sdd_config.yaml: context.min_path_confidence: 0.5`

### Полная таблица EDGE_KIND_PRIORITY (Phase 57 final state)

После всех фаз 53-57, `src/sdd/graph/types.py` ДОЛЖЕН содержать:

```python
EDGE_KIND_PRIORITY: dict[str, float] = {
    "emits":                0.95,   # Phase 50
    "violates":             0.92,   # Phase 57 BC-57-3
    "guards":               0.90,   # Phase 50
    "implements":           0.85,   # Phase 50
    "tested_by":            0.80,   # Phase 52 (declared), Phase 53 (extractor)
    "verified_by":          0.75,   # Phase 50
    "depends_on":           0.70,   # Phase 50
    "introduced_in":        0.65,   # Phase 50
    "cross_bc_dependency":  0.63,   # Phase 56 BC-56-BC-2
    "imports":              0.60,   # Phase 50
    "calls":                0.58,   # Phase 56 BC-56-LAYER
    "belongs_to":           0.55,   # Phase 56 BC-56-BC
    "means":                0.50,   # Phase 50
    "contains":             0.45,   # Phase 55 BC-55-P7
    "in_layer":             0.35,   # Phase 56 BC-56-LAYER
}
```

`violates` (0.92) вставляется между `emits` (0.95) и `guards` (0.90) — violations критичны.

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-TASK-INPUTS-REMOVED | `parser.py` MUST NOT parse `Inputs:` or `resolve_keywords:`. Detection → `ParseError` | 57 |
| I-ANCHOR-REQUIRED | Each TODO task in Phase 57+ MUST have non-empty `anchor_nodes` in `TaskNavigationSpec`. Empty → `norm-guard` blocks IMPLEMENT | 57 |
| I-ARCH-1 | No circular `imports/calls` dependencies between BOUNDED_CONTEXTs. Cycles → `sdd arch-check` exit 1 | 57 |
| I-ARCH-2 | `LAYER:domain` files MUST NOT have `imports/calls` edges → `LAYER:infrastructure` files | 57 |
| I-ARCH-3 | Layer dependency direction: interface → application → domain only. Reverse direction MUST NOT exist | 57 |
| I-GRAPH-GUARD-2 | Each IMPLEMENT session MUST cover all `anchor_nodes` via `nodes_covered` in `GraphCallEntry`. Supersedes I-GRAPH-GUARD-1 for Phase 57+ tasks | 57 |
| I-GRAPH-COVERAGE-1 | `SpatialIndex.meta["graph_coverage"]` MUST be set by IndexBuilder. Partial → warning, not error | 57 |
| I-GRAPH-BUILD-PIPELINE-1 | arch-check и graph-guard работают ТОЛЬКО с derived/validated edges. Прямое использование raw edges → GraphInvariantError | 57 |
| I-BC-RESOLVER-1 | belongs_to(f) == BCResolver(path(f)) — строгое равенство. Расхождение → GraphInvariantError на validated stage | 57 |
| I-GRAPH-GUARD-3 | GraphCallEntry вносит вклад в covered ТОЛЬКО если result_size["edges"] > 0. Seed-only записи (edges==0) НЕ считаются покрытием | 57 |
| I-GRAPH-GUARD-4 | covered ∩ reachable_from(anchor_nodes, hops≤3) ≠ ∅. Изолированное coverage (все covered nodes недостижимы от anchors) → exit 1 | 57 |
| I-GRAPH-COVERAGE-2 | coverage_score = covered_file_nodes / total_file_nodes. "full" iff score >= 0.9 AND command.score >= 0.7 AND invariant.score >= 0.7 | 57 |
| I-MODULE-COHESION-1 | FILE в MODULE:M с external_imports > N (default 10) → cohesion violation. Enforcement: sdd arch-check --check module-cohesion | 57 |
| I-ARCH-CONFIDENCE-1 | arch-check layer-purity/layer-direction используют только edges с confidence >= 0.9 для violations. calls (0.6) → WARNING only | 57 |
| I-CONTEXT-CONFIDENCE-1 | Selection НЕ содержит nodes с path_confidence < min_path_confidence (default 0.5). Исключение: seed node (hop=0, path_confidence=1.0) | 57 |
| I-RAG-1 | soft enforcement: `allow_global_search=True` → `RuntimeWarning` + degrade to `RagMode.LOCAL`. Hard enforcement → Phase 58 | 57 soft |
| I-RAG-SCOPE-ENTRY-1 | soft: entry gate logs allowed document scope. Hard assertion → Phase 58. `input_documents == ContextEngine.output.documents` at LightRAGProjection entry | 57 soft |
| I-NAV-BASED-ON-1 | `NavigationResponse.based_on` MUST list all `selection.nodes.keys()`. MUST NOT be None when context is non-empty. Populated in `ContextEngine.query()` | 57 |
| I-RAG-DEGRADED-1 | При недоступности EmbeddingProvider (нет ключа, сеть, 429, parse error): EmbeddingProvider/rerank НЕ вызываются. `documents` возвращаются в граф-порядке (hop ASC, global_importance_score DESC, node_id ASC). `rag_summary: null`. `rag_mode: "DEGRADED"`. Никаких полупересчитанных ранков. L1/L2 MUST остаться полностью работоспособными | 57 |
| I-SPATIAL-PROJECTION-1 | `SpatialIndex` является проекцией Graph/FS. НЕ создаёт собственных node_id. НЕ является самостоятельным source of truth структурной информации. Обновляется синхронно с GraphIndexBuilder | 57 declared |

### Preserved Invariants

| ID | Statement |
|----|-----------|
| I-GRAPH-GUARD-1 | Preserved for Phase 55/56 tasks without anchor_nodes |
| I-ENGINE-EDGE-FILTER-1 | edge filter в BFS, не post-filter |
| I-BC-DETERMINISTIC-1 | path-based BC classification only |
| I-LAYER-DETERMINISTIC-1 | path-based LAYER classification only |
| I-GRAPH-CALL-LOG-1 | graph_calls.jsonl separate from audit_log.jsonl |
| I-IMPLEMENT-GRAPH-2 | fallback запрещён |
| I-IMPLEMENT-SCOPE-1 | write_scope sacred |
| I-2 | All write commands via REGISTRY |

---

## 6. Pre/Post Conditions

### BC-57-1 — Legacy Cleanup

**Pre:**
- Phase 56 COMPLETE
- Все существующие TaskSet конвертированы в anchor_nodes format
  (проверяется: `grep -r "resolve_keywords\|^Inputs:" .sdd/tasks/` → 0 результатов)

**Post:**
- `parser.py` не содержит parsing logic для Inputs / resolve_keywords
- `TaskNavigationSpec` не содержит `resolve_keywords` field
- Тест: старый TaskSet → ParseError

### BC-57-3 — sdd arch-check Phase Gate

**Pre:** Phase 56 COMPLETE с BOUNDED_CONTEXT + LAYER nodes в графе

**Post (required перед PLAN Phase 57):**
- `sdd arch-check --format json` → `{"violations": 0}`
- Если violations > 0 → Phase 57 BLOCKED до исправлений
- Человек проверяет результат

### BC-57-4 — graph-guard v2

**Pre:**
- Phase 56 graph-guard (BC-56-G1) работает
- `GraphCallEntry.nodes_covered` заполняется graph nav CLIs

**Post:**
- `sdd graph-guard check --task T-NNN` проверяет coverage всех anchor_nodes
- `uncovered_anchor_nodes == set()` → exit 0
- `uncovered != {}` → exit 1 с списком непокрытых узлов

---

## 7. Use Cases

### UC-57-1: IMPLEMENT с anchor_nodes coverage enforcement

1. Task T-NNN: `anchor_nodes: [COMMAND:complete, INVARIANT:I-HANDLER-PURE-1]`
2. STEP 4.5: `sdd explain COMMAND:complete --edge-types implements,guards,emits`
   → `nodes_covered: ["COMMAND:complete", "FILE:src/sdd/commands/complete.py", ...]`
   → `log_graph_call(GraphCallEntry(..., nodes_covered=(...)))`
3. STEP 4.5: `sdd explain INVARIANT:I-HANDLER-PURE-1 --edge-types verified_by`
   → `nodes_covered: ["INVARIANT:I-HANDLER-PURE-1", "FILE:tests/unit/..."]`
4. `sdd graph-guard check --task T-NNN`
   → covered = {"COMMAND:complete", "INVARIANT:I-HANDLER-PURE-1"} (both!)
   → exit 0
5. `sdd complete T-NNN`

### UC-57-2: Phase Gate — arch-check перед Phase 57

```bash
# После Phase 56 COMPLETE:
sdd arch-check --format json

# Сценарий 1: clean
{"violations": [], "total": 0}
# → Phase 57 PLAN разрешён

# Сценарий 2: violation
{"violations": [{"check": "layer-purity",
                 "file": "FILE:src/sdd/context_kernel/engine.py",
                 "invariant": "INVARIANT:I-ARCH-2",
                 "detail": "domain imports infra: sdd.infra.paths"}],
 "total": 1}
# → Phase 57 BLOCKED, исправить до старта
```

### UC-57-3: Граф как архитектурный SSOT

```bash
# Полная картина одного файла:
sdd explain FILE:src/sdd/graph/builder.py --edge-types implements,imports,in_layer,belongs_to,tested_by

# Кто зависит от builder.py (с фильтром по типу):
sdd trace FILE:src/sdd/graph/builder.py --edge-types imports
sdd trace FILE:src/sdd/graph/builder.py --edge-types calls

# Где нарушения архитектуры:
sdd arch-check --check layer-purity

# Какой % кода покрыт классификацией:
sdd graph-stats
```

---

## 8. Integration

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-56-BC (Phase 56) | this requires | BOUNDED_CONTEXT nodes для I-ARCH-1 |
| BC-56-LAYER (Phase 56) | this requires | LAYER nodes для I-ARCH-2/3 |
| BC-56-A1 (Phase 56) | this extends | GraphCallEntry + nodes_covered |
| BC-56-S1 (Phase 56) | this extends | TaskNavigationSpec → removes resolve_keywords |
| validate-invariants | this integrates | arch-check результаты в общий DoD check |
| sdd_config.yaml | this reads | arch_check.enabled_checks, ignore_patterns |

---

## 9. Verification

| # | Test / Check | Invariant(s) |
|---|--------------|--------------|
| 1 | TaskSet с `Inputs:` секцией → ParseError | I-TASK-INPUTS-REMOVED |
| 2 | TaskSet с `resolve_keywords:` → ParseError | I-TASK-INPUTS-REMOVED |
| 3 | TaskSet с `anchor_nodes:` → корректный parse | BC-57-1 |
| 4 | TODO task без anchor_nodes → `norm-guard check --action implement_task` → exit 1 | I-ANCHOR-REQUIRED |
| 5 | `sdd arch-check --check layer-purity` → exit 0 на чистой codebase | I-ARCH-2, BC-57-3 |
| 6 | Добавить искусственный import domain→infra → `sdd arch-check` → exit 1 с violation detail | I-ARCH-2, BC-57-3 |
| 7 | `sdd arch-check --check bc-cycles` → exit 0 (нет циклов) | I-ARCH-1, BC-57-3 |
| 8 | `sdd graph-guard check --task T-NNN` → exit 1 если anchor_node не в nodes_covered | I-GRAPH-GUARD-2 |
| 9 | `sdd graph-guard check` → exit 0 если все anchor_nodes covered | I-GRAPH-GUARD-2 |
| 10 | `graph_coverage = "full"` если все FILE nodes классифицированы | I-GRAPH-COVERAGE-1, BC-57-5 |
| 11 | `graph_coverage = "partial"` + warning если есть unclassified | I-GRAPH-COVERAGE-1, BC-57-5 |
| 12 | `sdd arch-check` с `coverage=partial` → exit 0 + warning (не error) | I-GRAPH-COVERAGE-1 |
| 13 | violates edge создаётся для реального нарушения I-ARCH-2 | BC-57-3 |
| 14 | `sdd explain FILE:X --edge-types violates` возвращает нарушенные инварианты | BC-57-3 |

---

## 11. Phase Acceptance Checklist

> Методология: `.sdd/docs/ref/phase-acceptance.md`

### Part 1 — In-Phase DoD

**Step U (Universal):**
```bash
sdd show-state                          # tasks_completed == tasks_total
sdd validate --check-dod --phase 57     # exit 0
python3 -m pytest tests/unit/ -q        # 0 failures
```

**Step 57-A — Build pipeline stages (BC-57-BUILD-PIPELINE):**
```bash
# Derived extractors не запускаются до classified
python3 -c "
from sdd.graph.builder import GraphFactsBuilder
b = GraphFactsBuilder.__new__(GraphFactsBuilder)
stages = [e.pipeline_stage for e in b._extractors]
# raw → classified → derived → validated (порядок)
print(stages)
"
# → все 'derived' экстракторы идут после всех 'classified'
```

**Step 57-B — arch-check functional (BC-57-3):**
```bash
sdd arch-check --check layer-purity --format json
# → exit 0 ИЛИ exit 1 с violations list
# Неприемлемо: crash/traceback

sdd arch-check --check layer-direction --format json
# → exit 0 ИЛИ exit 1 с violations list

sdd arch-check --check bc-cycles --format json
# → exit 0 ИЛИ exit 1

sdd arch-check --check module-cohesion --format json
# → exit 0 ИЛИ exit 1

sdd arch-check --check all --format json
# → exit 0 ИЛИ exit 1; НЕ crash
```

**Step 57-C — graph-guard v2 с seed-only guard (I-GRAPH-GUARD-3):**
```bash
# Сессия только с seed вызовом (edges=0) → guard не засчитывает покрытие
python3 -m pytest tests/unit/test_graph_guard_v2.py::test_guard_v2_seed_only_not_counted -v
# → PASSED

# I-GRAPH-GUARD-4: изолированный coverage → exit 1
python3 -m pytest tests/unit/test_graph_guard_v2.py::test_guard_v2_isolated_coverage -v
# → PASSED
```

**Step 57-D — graph_coverage числовой (BC-57-5):**
```bash
python3 -c "
from sdd.spatial.index import IndexBuilder
# После nav-rebuild
idx = ...  # load spatial index
meta = idx.meta.get('graph_coverage', {})
assert 'coverage_score' in meta, 'coverage_score MISSING'
assert 'coverage_by_type' in meta, 'coverage_by_type MISSING'
assert isinstance(meta['coverage_score'], float)
print(f'coverage_score={meta[\"coverage_score\"]:.2f}')
"
# → coverage_score=X.XX (float, 0.0-1.0)
```

**Step 57-E — Edge.confidence и EDGE_KIND_CONFIDENCE (E-5):**
```bash
python3 -c "
from sdd.graph.types import EDGE_KIND_CONFIDENCE, Edge
assert 'calls' in EDGE_KIND_CONFIDENCE
assert EDGE_KIND_CONFIDENCE['calls'] == 0.6
assert EDGE_KIND_CONFIDENCE['imports'] == 1.0
e = Edge(edge_id='x', src='A', dst='B', kind='imports', priority=0.6, source='test', meta={})
assert e.confidence == 1.0  # default
print('OK')
"
# → OK
```

**Step 57-F — module-cohesion enforcement (BC-57-6):**
```bash
sdd arch-check --check module-cohesion --format json
# → {"violations": [...]} или {"violations": []}
# Неприемлемо: crash или отсутствие ключа "violations"
```

---

### Part 2 — Regression Guard

```bash
# (R-57-1) arch-check informational mode Phase 56 → violations mode Phase 57
# Убедиться что bc-cross-dependencies теперь exit 1 при нарушениях (не exit 0 всегда)
sdd arch-check --check bc-cross-dependencies --format json
# Если violations > 0 → exit 1 (Phase 57 enforcement, нормально)

# (R-57-2) BOUNDED_CONTEXT, LAYER nodes из Phase 56 — всё ещё присутствуют
sdd graph-stats --node-type BOUNDED_CONTEXT --format json  # count > 0
sdd graph-stats --node-type LAYER --format json            # count > 0

# (R-57-3) tested_by из Phase 53, MODULE из Phase 55 — не сломаны
sdd graph-stats --edge-type tested_by --format json   # count > 0
sdd graph-stats --node-type MODULE --format json       # count > 0

# (R-57-4) sdd explain без --edge-types — поведение идентично Phase 56
sdd explain COMMAND:complete --format json
# → те же nodes что и в Phase 56 (confidence filter не убирает лишнего)
```

Если хоть одна регрессия → **STOP → sdd report-error → recovery.md**.

---

### Part 3 — Transition Gate (before Phase 58)

Человек верифицирует перед `sdd activate-phase 58`:

```bash
# Gate 58-A: arch-check tool functional (все check types работают)
sdd arch-check --check all --format json
# Expected: exit 0 ИЛИ exit 1; НЕ crash/traceback

# Gate 58-B: понять схему существующего invariant_edges.py (ручная проверка)
cat src/sdd/graph/extractors/invariant_edges.py | head -20
# Ожидание: понять какие edge kinds уже строятся (verified_by, introduced_in)
# BC-58-3 расширяет, не заменяет — это нужно подтвердить до старта

# Gate 58-C: graph-guard v2 работает (требуется для BC-58-6)
sdd graph-guard check --format json 2>&1 | head -5
# Expected: json output (не crash)
```

---

### Part 4 — Rollback Triggers

Немедленно STOP если:
- `sdd arch-check --check all` → crash вместо exit 0/1 с JSON
- `Edge.confidence` поле ломает сериализацию существующих edges в graph cache
- `path_confidence` filter в Selection убирает более 20% nodes на существующих queries (regression)
- `coverage_score` = 0.0 после полного nav-rebuild (не вычислен или вычислен неверно)
- `I-GRAPH-GUARD-3` тест падает (seed-only не фильтруется)
- Любой тест Phase 52-56 начинает падать

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `sdd graph-guard` coverage report (% anchor nodes traversed per session) | Phase 58+ |
| Автоматическое обновление anchor_nodes при изменении графа | Phase 58+ |
| `calls` edge refinement (AST Call node direct detection, не только imports) | Phase 58+ |
| Cross-BC dependency matrix (полная matrica зависимостей) | Phase 58+ |
| Graph-level diff между состояниями фаз (что изменилось в архитектуре) | Отдельная спека |
| Embedding-based search в `sdd resolve` (I-SEARCH-NO-EMBED-1 снята?) | Отдельная спека |
| `sdd migrate-taskset` CLI utility | Phase 57 option (может быть добавлен в BC-57-1) |
| Автоматическая генерация arch_check.ignore_patterns | Phase 58+ |
| BOUNDED_CONTEXT ownership map (кто отвечает за какой BC) | Отдельная спека |
