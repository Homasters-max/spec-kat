# Spec_v56 — Phase 56: Graph-First + Architecture Context

Status: Draft (revised — GraphCallLog, BOUNDED_CONTEXT, LAYER интегрированы)
Baseline: Spec_v55_GraphGuidedImplement.md (Phase 55 — Graph-Guided Implement)
Revised: 2026-04-30 (разделение audit log, architecture context model, TaskNavigationSpec v2)

---

## 0. Goal

Три задачи фазы:

1. **Инфраструктура аудита** — отдельный `GraphCallLog` модуль (`graph_calls.jsonl`),
   typed API для записи и запроса; `sdd record-metric` через EventStore

2. **Enforcement** — `sdd graph-guard check` блокирует `sdd complete` если в сессии
   не было graph-вызовов (использует `GraphCallLog.query_graph_calls()`, не парсит JSONL напрямую)

3. **Architecture Context Model** — `BOUNDED_CONTEXT` и `LAYER` nodes в графе;
   детерминированная path-based классификация без LLM;
   граф начинает отвечать: "кто в каком контексте?" и "в каком слое?"

**Phase Gate:** `sdd graph-stats --edge-type tested_by` → count > 0 (TestedByExtractor должен быть
реализован). Человек проверяет перед `DRAFT_SPEC v56 → PLAN Phase 56`.

---

## 1. Scope

### In-Scope

- BC-56-A1: `GraphCallLog` — отдельный модуль `infra/graph_call_log.py` + `graph_calls.jsonl`
- BC-56-A2: `sdd record-metric` — MetricRecorded event через REGISTRY
- BC-56-G1: `sdd graph-guard check` — использует `GraphCallLog.query_graph_calls()`
- BC-56-G2: `sdd graph-stats` — read-only утилита (edge/node counts)
- BC-56-T1: **[PHASE GATE — не в scope]** TestedByEdgeExtractor реализован в Phase 53.
  Перед PLAN Phase 56 верифицировать: `sdd graph-stats --edge-type tested_by → count > 0`.
- BC-56-S1: `TaskNavigationSpec` v2 — `anchor_nodes` заменяет `resolve_keywords`
- BC-56-S2: Score normalization — BM25 → (0, 1) в `sdd resolve`
- BC-56-BC: `BOUNDED_CONTEXT` nodes + `belongs_to` edges + classification rules
- BC-56-LAYER: `LAYER` nodes + `in_layer` edges + `calls` edges

### Out of Scope

См. §10.

---

## 2. Architecture / BCs

### BC-56-A1: GraphCallLog — отдельный модуль (REVISED от исходного драфта)

**Архитектурное решение:** `graph_call` записи хранятся в `graph_calls.jsonl`, отдельно
от `audit_log.jsonl`. `graph-guard` использует typed API модуля `GraphCallLog`,
не парсит JSONL напрямую.

**Обоснование:** `audit_log.jsonl` содержит `AuditEntry` (governance события, L2). Добавление
`graph_call` записей с другой схемой в тот же файл создаёт heterogeneous bag без typed seam.
`graph-guard` вынужден был бы парсить JSONL с inline логикой "что есть валидная graph_call запись" —
нарушение locality (знание о схеме в двух местах: writer и guard).

**Два отдельных файла:**
```
.sdd/runtime/audit_log.jsonl    — AuditEntry (governance, L2) — БЕЗ ИЗМЕНЕНИЙ
.sdd/runtime/graph_calls.jsonl  — GraphCallEntry (graph navigation audit) — НОВЫЙ
```

**Инвариант I-GRAPH-CALL-LOG-1:**
`graph_calls.jsonl` MUST be separate from `audit_log.jsonl`.
Graph navigation CLIs MUST write to `graph_calls.jsonl` only, never to `audit_log.jsonl`.

**Файлы:**
```
src/sdd/infra/graph_call_log.py    # GraphCallEntry, log_graph_call(), query_graph_calls()
src/sdd/infra/paths.py             # добавить graph_calls_file() → path
src/sdd/graph_navigation/cli/explain.py  — вызов log_graph_call() после engine.query()
src/sdd/graph_navigation/cli/trace.py   — вызов log_graph_call() после engine.query()
src/sdd/graph_navigation/cli/resolve.py — вызов log_graph_call() после engine.query()
```

**Типы и API:**

```python
# src/sdd/infra/graph_call_log.py

@dataclass(frozen=True)
class GraphCallEntry:
    command: str              # "explain" | "trace" | "resolve"
    args: dict[str, Any]      # {"node_id": "...", "edge_types": [...], ...}
    session_id: str | None    # из get_current_session_id() (None если нет сессии)
    ts: str                   # ISO 8601 timestamp
    result_size: dict[str, int]  # {"nodes": N, "edges": M}

def log_graph_call(entry: GraphCallEntry) -> None:
    """Append GraphCallEntry to graph_calls.jsonl atomically (via atomic_write)."""

def query_graph_calls(
    session_id: str | None = None,
) -> list[GraphCallEntry]:
    """Read graph_calls.jsonl, optionally filter by session_id.
    Returns [] if file absent (first run, no error).
    Skips malformed lines (I-AUDIT-SESSION-1: entries без session_id не учитываются graph-guard).
    """
```

**Логирование в CLI (explain.py, trace.py, resolve.py):**
```python
# После engine.query() в каждом CLI:
session_id = get_current_session_id()  # из infra/session_context.py (BC-55-P8)
log_graph_call(GraphCallEntry(
    command="explain",
    args={"node_id": node_id, "edge_types": list(edge_types) if edge_types else None},
    session_id=session_id,
    ts=datetime.now(timezone.utc).isoformat(),
    result_size={
        "nodes": len(response.context.nodes),
        "edges": len(response.context.edges),
    },
))
```

**Degraded calls (result_size.edges == 0):** детектируются через `query_graph_calls()` как
`count(entry.result_size["edges"] == 0)` — позволяет мониторить деградацию графа.

---

### BC-56-A2: sdd record-metric

Новая команда через REGISTRY:

```
sdd record-metric --key <str> --value <float> --phase <int> --task <task_id> [--context <str>]
```

```python
@dataclass(frozen=True)
class MetricRecorded(DomainEvent):
    metric_key: str    # "graph_degraded_reads", "graph_calls_count", etc.
    value: float
    phase_id: int
    task_id: str
    context: str       # free-text reason (≤140 chars)
```

Проекция не нужна — метрики доступны через `sdd query-events --event MetricRecorded`.

---

### BC-56-G1: sdd graph-guard

**Архитектурное решение:** `graph-guard check` использует `GraphCallLog.query_graph_calls(session_id)`,
не читает `graph_calls.jsonl` напрямую. Это дает locality: логика "что есть валидный graph_call"
— в одном месте (`graph_call_log.py`).

```bash
sdd graph-guard check --task T-NNN [--session-id <id>]
# Шаги:
# 1. session_id = arg OR get_current_session_id()
# 2. calls = query_graph_calls(session_id=session_id)
# 3. valid_calls = [c for c in calls if c.session_id is not None]
# 4. len(valid_calls) >= 1 → exit 0
# 5. len(valid_calls) == 0 → exit 1, stderr JSON с I-GRAPH-GUARD-1
```

Добавляется в `implement.md` перед `sdd complete T-NNN` (обновлённый STEP 8):
```bash
sdd graph-guard check --task T-NNN   # exit 1 → STOP
sdd complete T-NNN
```

**Инвариант I-GRAPH-GUARD-1:**
Each IMPLEMENT session MUST have ≥1 valid `GraphCallEntry` in `graph_calls.jsonl`
for current `session_id`. "Valid" = `entry.session_id is not None`.
Enforced by `sdd graph-guard check` before `sdd complete`.

**Read-only guard:** не через REGISTRY write pipeline (аналогично `norm-guard check`).

---

### BC-56-G2: sdd graph-stats

Read-only утилита (не через REGISTRY):

```bash
sdd graph-stats [--edge-type <type>] [--node-type <type>] [--format json|text]
# Примеры:
# sdd graph-stats --edge-type tested_by         → {"edge_type": "tested_by", "count": N}
# sdd graph-stats --edge-type belongs_to        → {"edge_type": "belongs_to", "count": N}
# sdd graph-stats --node-type BOUNDED_CONTEXT   → {"node_type": "BOUNDED_CONTEXT", "count": N}
# sdd graph-stats                               → полный summary
```

**Phase Gate (перед PLAN Phase 56):**
```bash
sdd graph-stats --edge-type tested_by --format json
# count == 0 → Phase 56 BLOCKED (нужен TestedByExtractor из Phase 55)
# count > 0  → gate passed
```

---

### BC-56-T1: TestedByEdgeExtractor — Phase Gate Verification (REVISED)

**NOT in Phase 56 scope. Phase Gate check only.**

TestedByEdgeExtractor реализован в Phase 53 (Spec_v53_GraphTestFilter.md).
Авторитетное направление рёбра (Phase 53):

```
FILE:src/sdd/X.py → tested_by → TEST:tests/unit/.../test_X.py
COMMAND:X          → tested_by → TEST:tests/unit/.../test_X.py
```

**Почему исходная версия BC-56-T1 была некорректна:**
Исходный BC-56-T1 определял направление `FILE:tests/X → tested_by → FILE:src/Y`.
Это противоречит:
- Семантике "X is tested by Y" → X → tested_by → Y (source → test)
- UC-56-4: `sdd explain FILE:src/... --edge-types tested_by` использует OUT-edges.
  Если тест указывает на источник (`tests → src`), LLM должен вызывать `sdd trace`, а не `sdd explain`.
  UC-56-4 требует `sdd explain` — значит, направление должно быть `src → tested_by → test`.

**Phase Gate (человек проверяет перед PLAN Phase 56):**
```bash
sdd graph-stats --edge-type tested_by --format json
# {"count": 0} → BLOCKED (Phase 53 не завершён)
# {"count": N, N > 0} → gate passed
```

---

### BC-56-S1: TaskNavigationSpec v2 — anchor_nodes (REVISED)

**Архитектурное решение:** Использует `TaskNavigationSpec` type из Phase 55 (BC-55-P3).
Phase 56 переводит `TaskNavigationSpec` в anchor_nodes mode (`is_anchor_mode() → True`).

**Что меняется:**
- `resolve_keywords` deprecated (поля остаются в `TaskNavigationSpec` для backward compat)
- `anchor_nodes` становится primary field
- DECOMPOSE Phase 56 генерирует `anchor_nodes` напрямую (не keywords)
- `allowed_traversal` становится обязательным (не defaults в engine)

**Формат TaskSet в Phase 56:**
```markdown
Navigation:
  anchor_nodes:
    - COMMAND:complete
    - INVARIANT:I-HANDLER-PURE-1
  allowed_traversal:
    - implements
    - guards
    - tested_by
    - imports
  write_scope:
    - FILE:src/sdd/commands/complete.py
```

**DECOMPOSE Phase 56 workflow:**
```bash
sdd resolve "<task keywords>" --format json
# LLM проверяет: score_normalized >= 0.5 (I-DECOMPOSE-RESOLVE-3)
# берёт top-1.node_id как anchor_node
# записывает: anchor_nodes: [COMMAND:complete]
```

**Что исчезает из DECOMPOSE (не из parser.py — backward compat остаётся):**
- Новые TaskSet Phase 56+ НЕ генерируют `resolve_keywords` секцию
- Существующие Phase 55 TaskSet с `resolve_keywords` продолжают парситься

---

### BC-56-S2: Score Normalization в sdd resolve

BM25 score: 0 → +∞ (не нормализован). Нормализация: `score_norm = score / (score + 1)`, диапазон (0, 1).

```python
class Candidate:
    node_id: str
    kind: str
    score: float            # BM25 raw (backward compat)
    score_normalized: float  # score / (score + 1)
```

**I-DECOMPOSE-RESOLVE-3:** top-1 `score_normalized` MUST be ≥ 0.5 (configurable через
`graph_budget.min_resolve_score_normalized`).

---

### BC-56-BC: BOUNDED_CONTEXT Nodes + belongs_to Edges (NEW)

**Цель:** Граф должен отвечать: "кто к какому bounded context принадлежит?"

**Node kind:** `BOUNDED_CONTEXT`
- `node_id`: `BOUNDED_CONTEXT:<id>` (e.g., `BOUNDED_CONTEXT:graph`, `BOUNDED_CONTEXT:infra`)
- `kind`: `"BOUNDED_CONTEXT"`
- `label`: человекочитаемое имя

**Edge kind:** `belongs_to` (FILE → BOUNDED_CONTEXT)
- Priority: `0.55` (выше `means:0.50`, ниже `imports:0.60`)
- Направление: `FILE:src/sdd/graph/builder.py → belongs_to → BOUNDED_CONTEXT:graph`

**Инвариант I-BC-DETERMINISTIC-1:**
BOUNDED_CONTEXT classification MUST be deterministic and path-based only.
No LLM, no heuristics. Rule = path prefix match. Ambiguous file (нет совпадения) →
`BOUNDED_CONTEXT:unclassified`. Нет silent skipping.

**Classification rules** (в `sdd_config.yaml` новая секция):
```yaml
bounded_contexts:
  - id: graph
    path_prefix: src/sdd/graph/
    description: "Graph build pipeline (extractors, cache, service)"
  - id: context_kernel
    path_prefix: src/sdd/context_kernel/
    description: "Pure functional query pipeline (engine, assembler, selection)"
  - id: graph_navigation
    path_prefix: src/sdd/graph_navigation/
    description: "CLI navigation layer (explain, trace, resolve)"
  - id: governance
    path_prefix: src/sdd/commands/
    description: "Write Kernel (REGISTRY, handlers, command pipeline)"
  - id: spatial
    path_prefix: src/sdd/spatial/
    description: "SpatialIndex, IndexBuilder, navigator"
  - id: infra
    path_prefix: src/sdd/infra/
    description: "Infrastructure (audit, db, paths, event_log)"
  - id: tasks
    path_prefix: src/sdd/tasks/
    description: "TaskSet parser, TaskNavigationSpec"
  - id: policy
    path_prefix: src/sdd/policy/
    description: "NavigationPolicy, PolicyResolver"
```

**Файлы:**
```
src/sdd/graph/extractors/bounded_context_edges.py  # BoundedContextEdgeExtractor (новый)
src/sdd/spatial/index.py       # _collect_bounded_contexts() в IndexBuilder
sdd_config.yaml                # секция bounded_contexts
src/sdd/graph/types.py         # добавить "belongs_to": 0.55 в EDGE_KIND_PRIORITY
```

**BoundedContextEdgeExtractor:**
```python
class BoundedContextEdgeExtractor:
    EXTRACTOR_VERSION: ClassVar[str] = "1.0.0"

    def extract(self, index: SpatialIndex) -> list[Edge]:
        """FILE nodes → BOUNDED_CONTEXT nodes via belongs_to edges.
        Uses classification rules from sdd_config.yaml (injected via index.meta).
        Path-based only. Unmatched files → BOUNDED_CONTEXT:unclassified.
        """
```

**Использование:**
```bash
sdd explain BOUNDED_CONTEXT:graph --edge-types belongs_to
→ все файлы в bounded context "graph"

sdd trace BOUNDED_CONTEXT:context_kernel --edge-types belongs_to
→ нет входящих edges (BOUNDED_CONTEXT — leaf node)
```

---

### BC-56-BC-2: cross_bc_dependency Edges (NEW)

**Мотивация (Issue I-6):** Файл в `src/sdd/graph/` может импортировать из `src/sdd/infra/`,
создавая cross-BC зависимость, невидимую в текущей модели. Для детекции архитектурных циклов
в Phase 57 (I-ARCH-1) необходимы явные `cross_bc_dependency` рёбра.

**Edge kind:** `cross_bc_dependency` (FILE → BOUNDED_CONTEXT)
- Priority: `0.63` (между `imports:0.60` и `belongs_to:0.55` — это derived edge)
- Направление: `FILE:src/sdd/graph/builder.py → cross_bc_dependency → BOUNDED_CONTEXT:infra`
  (если builder.py импортирует из src/sdd/infra/)

**Правило эмиссии:**
Для каждого FILE:f с `belongs_to → BOUNDED_CONTEXT:A`:
  Для каждого `imports` или `calls` edge (f → g):
    Если g belongs_to BOUNDED_CONTEXT:B, B ≠ A:
      emit edge: f → cross_bc_dependency → BOUNDED_CONTEXT:B
Дедупликация: не более одного edge на пару (src FILE, dst BC).

**BCResolver — единый модуль (D-2):**
`CrossBCEdgeExtractor` НЕ дублирует логику классификации из `BoundedContextEdgeExtractor`.
Обе используют единый класс `BCResolver` из `src/sdd/graph/extractors/bc_resolver.py`:

```python
class BCResolver:
    def __init__(self, rules: list[BCRule]): ...
    def resolve(self, path: str) -> str | None:
        """path → BC name (по path_prefix match) или None (→ unclassified)."""
```

**Инвариант I-BC-RESOLVER-1:**
`belongs_to(f) == BCResolver(path(f))` — строгое равенство.
Если результаты расходятся → `GraphInvariantError` на validated stage builder'а.
Это предотвращает silent drift при изменении правил классификации.

**Инвариант I-BC-CONSISTENCY-1:**
Когда FILE:f принадлежит BC:A по path и имеет imports/calls к FILE:g в BC:B (A≠B),
экстрактор ДОЛЖЕН эмитировать `FILE:f → cross_bc_dependency → BOUNDED_CONTEXT:B`.
Скрытые cross-BC зависимости запрещены.

**Новые файлы:**
```
src/sdd/graph/extractors/bc_resolver.py      # BCResolver class (единый модуль)
src/sdd/graph/extractors/cross_bc_edges.py   # CrossBCEdgeExtractor
```

**Phase 56 scope:** Рёбра эмитируются и доступны для query. `arch-check --check bc-cross-dependencies`
в Phase 56 → информационный отчёт, exit 0.
Violation enforcement (cycles → exit 1) — Phase 57 (BC-57-7).

**Использование:**
```bash
sdd arch-check --check bc-cross-dependencies --format json
→ {"cross_bc_dependencies": [...]}  # informational in Phase 56

sdd trace BOUNDED_CONTEXT:context_kernel --edge-types cross_bc_dependency
→ кто из других BC зависит от context_kernel
```

---

### BC-56-LAYER: LAYER Nodes + in_layer + calls Edges (NEW)

**Цель:** Граф должен отвечать: "в каком архитектурном слое находится файл?" и
"есть ли нарушения слоёв?" (Phase 57 будет проверять через `violates` edges).

**Node kinds:** `LAYER`
- `LAYER:domain` — чистая логика, типы (domain пуреness: нет IO, нет DB)
- `LAYER:application` — команды, обработчики (orchestration)
- `LAYER:infrastructure` — IO, DB, filesystem, cache
- `LAYER:interface` — CLI, HTTP (входные точки системы)

**Edge kind:** `in_layer` (FILE → LAYER)
- Priority: `0.35` (ниже `belongs_to:0.55`)

**Edge kind:** `calls` (FILE → FILE)
- Priority: `0.58` (между `imports:0.60` и `belongs_to:0.55`)
- Различие от `imports`: `imports` = "модуль A импортирует символ из B"; `calls` = "A напрямую
  вызывает функцию/метод из B" (детектируется через AST Call nodes с explicit module prefix)

**Инвариант I-LAYER-DETERMINISTIC-1:**
LAYER classification MUST be deterministic and path-based only.
No LLM. Same as I-BC-DETERMINISTIC-1 for BOUNDED_CONTEXT.

**Classification rules** (в `sdd_config.yaml`):
```yaml
layers:
  interface:
    path_patterns:
      - src/sdd/cli.py
      - src/sdd/graph_navigation/cli/
  application:
    path_patterns:
      - src/sdd/commands/
      - src/sdd/spatial/commands/
  domain:
    path_patterns:
      - src/sdd/context_kernel/engine.py
      - src/sdd/context_kernel/assembler.py
      - src/sdd/context_kernel/selection.py
      - src/sdd/graph/types.py
      - src/sdd/graph/builder.py
      - src/sdd/tasks/navigation.py
  infrastructure:
    path_patterns:
      - src/sdd/infra/
      - src/sdd/graph/service.py
      - src/sdd/graph/cache.py
      - src/sdd/spatial/index.py
```

**Файлы:**
```
src/sdd/graph/extractors/layer_edges.py         # LayerEdgeExtractor (новый)
src/sdd/graph/extractors/calls_edges.py         # CallsEdgeExtractor (новый)
src/sdd/spatial/index.py      # _collect_layers() в IndexBuilder
sdd_config.yaml               # секция layers
src/sdd/graph/types.py        # "in_layer": 0.35, "calls": 0.58 в EDGE_KIND_PRIORITY
```

**Использование:**
```bash
sdd explain LAYER:domain --edge-types in_layer
→ все файлы доменного слоя

sdd trace FILE:src/sdd/infra/db.py --edge-types calls
→ кто напрямую вызывает db.py (не просто импортирует)
```

**Ограничение Phase 56:** LAYER nodes созданы + in_layer edges существуют.
Проверка нарушений слоёв (domain → infra?) — Phase 57 (BC-57-3, violates edges).

---

### Dependencies

```text
BC-56-G1 → BC-56-A1 : graph-guard использует GraphCallLog.query_graph_calls()
BC-56-S1 → BC-56-T1 : anchor_nodes traversal с tested_by требует edges в графе
BC-56-S1 → BC-56-G2 : gate проверяет tested_by count перед PLAN Phase 56
BC-56-A2 → EventStore : MetricRecorded через REGISTRY pipeline
BC-56-BC → sdd_config.yaml : classification rules
BC-56-LAYER → sdd_config.yaml : layer classification rules
BC-56-BC → BC-55-P7 : MODULE nodes (Phase 55) → BOUNDED_CONTEXT nodes (Phase 56) дополняют друг друга
BC-56-A1 → BC-55-P8 : GraphCallLog.log_graph_call() использует session_context.get_current_session_id()
```

---

## 3. Domain Events

```python
@dataclass(frozen=True)
class MetricRecorded(DomainEvent):
    metric_key: str    # "graph_degraded_reads", "graph_calls_count", etc.
    value: float
    phase_id: int
    task_id: str
    context: str       # ≤140 chars
```

| Event | Emitter | Description |
|-------|---------|-------------|
| `MetricRecorded` | `sdd record-metric` | Числовая метрика фазы/задачи в EventLog |

---

## 4. Types & Interfaces

### GraphCallLog (BC-56-A1)

```python
# src/sdd/infra/graph_call_log.py

@dataclass(frozen=True)
class GraphCallEntry:
    command: str
    args: dict[str, Any]
    session_id: str | None
    ts: str
    result_size: dict[str, int]  # {"nodes": N, "edges": M}

def log_graph_call(entry: GraphCallEntry) -> None: ...
def query_graph_calls(session_id: str | None = None) -> list[GraphCallEntry]: ...
```

### TaskNavigationSpec v2 (BC-56-S1)

```python
# src/sdd/tasks/navigation.py — РАСШИРЕНИЕ Phase 55 type

@dataclass(frozen=True)
class AnchorNode:
    node_id: str    # "COMMAND:complete", "INVARIANT:I-HANDLER-PURE-1"

@dataclass(frozen=True)
class TaskNavigationSpec:
    write_scope: tuple[str, ...]
    # v55 fields (deprecated в Phase 56 DECOMPOSE, парсятся для backward compat)
    resolve_keywords: tuple[ResolveKeyword, ...] = ()
    # v56 fields (primary в Phase 56)
    anchor_nodes: tuple[str, ...] = ()
    allowed_traversal: tuple[str, ...] = ()

    def is_anchor_mode(self) -> bool:
        return bool(self.anchor_nodes)
```

### sdd resolve — нормализованный score (BC-56-S2)

```python
class Candidate:
    node_id: str
    kind: str
    score: float            # BM25 raw (backward compat)
    score_normalized: float  # score / (score + 1), диапазон (0, 1)
```

### BOUNDED_CONTEXT node (BC-56-BC)

```python
# SpatialNode.kind = "BOUNDED_CONTEXT"
# node_id = "BOUNDED_CONTEXT:graph"
# meta = {"path_prefix": "src/sdd/graph/", "description": "..."}
```

### LAYER node (BC-56-LAYER)

```python
# SpatialNode.kind = "LAYER"
# node_id = "LAYER:domain" | "LAYER:application" | "LAYER:infrastructure" | "LAYER:interface"
# meta = {"path_patterns": [...]}
```

### Edge Kinds, добавляемые в Phase 56 (src/sdd/graph/types.py)

Следующие типы ДОЛЖНЫ быть добавлены в `EDGE_KIND_PRIORITY` до регистрации
любого нового экстрактора Phase 56 (требование I-GRAPH-PRIORITY-1):

| Edge Kind             | Priority | Направление              | Экстрактор                   |
|-----------------------|----------|--------------------------|------------------------------|
| `cross_bc_dependency` | 0.63     | FILE → BOUNDED_CONTEXT   | CrossBCEdgeExtractor         |
| `calls`               | 0.58     | FILE → FILE              | CallsEdgeExtractor           |
| `belongs_to`          | 0.55     | FILE → BOUNDED_CONTEXT   | BoundedContextEdgeExtractor  |
| `in_layer`            | 0.35     | FILE → LAYER             | LayerEdgeExtractor           |

Примечание: `contains` (0.45, MODULE → FILE) добавлен в Phase 55 (BC-55-P7).
Полная таблица EDGE_KIND_PRIORITY после всех фаз 53-57 — в Spec_v57 §4.

`ALLOWED_META_KEYS` additions (Phase 56):
- `"path_prefix"` — для BOUNDED_CONTEXT nodes
- `"description"` — для BOUNDED_CONTEXT + LAYER nodes
- `"path_patterns"` — для LAYER nodes

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-GRAPH-GUARD-1 | Each IMPLEMENT session MUST have ≥1 valid `GraphCallEntry` with non-None `session_id` in `graph_calls.jsonl` for current session | 56 |
| I-IMPLEMENT-GRAPH-2 | Fallback (чтение без graph justification) запрещён. FILE не в графе → STOP | 56 |
| I-AUDIT-SESSION-1 | `GraphCallEntry.session_id` MUST NOT be None для вызовов из IMPLEMENT сессии | 56 |
| I-DECOMPOSE-RESOLVE-3 | top-1 `score_normalized` MUST be ≥ `graph_budget.min_resolve_score_normalized` (default: 0.5) | 56 |
| I-GRAPH-CALL-LOG-1 | `graph_calls.jsonl` MUST be separate from `audit_log.jsonl`. Graph nav CLIs write ONLY to `graph_calls.jsonl` | 56 |
| I-BC-DETERMINISTIC-1 | BOUNDED_CONTEXT classification MUST be path-based only. No LLM. Unmatched → `BOUNDED_CONTEXT:unclassified` | 56 |
| I-LAYER-DETERMINISTIC-1 | LAYER classification MUST be path-based only. No LLM. Unmatched file → не получает `in_layer` edge; логируется как warning | 56 |
| I-BC-CONSISTENCY-1 | FILE с belongs_to→BC:A, имеющий imports/calls к FILE в BC:B (A≠B), MUST emit cross_bc_dependency→BC:B. Нет скрытых cross-BC зависимостей | 56 |
| I-BC-RESOLVER-1 | belongs_to(f) == BCResolver(path(f)) — строгое равенство. Расхождение → GraphInvariantError на validated stage | 56 |

### Preserved Invariants

| ID | Statement |
|----|-----------|
| I-IMPLEMENT-GRAPH-1 | graph-justified read (Phase 55 — в Phase 56 fallback запрещён) |
| I-IMPLEMENT-TRACE-1 | все dependents из trace — явное compatibility decision |
| I-IMPLEMENT-SCOPE-1 | write_scope sacred |
| I-DECOMPOSE-RESOLVE-1 | resolve exit 0 |
| I-DECOMPOSE-RESOLVE-2 | top-1 kind ∈ expected_kinds (Phase 55) / anchor_nodes (Phase 56) |
| I-ENGINE-EDGE-FILTER-1 | edge filter в BFS, не post-filter |
| I-SESSION-CONTEXT-1 | current_session.json только через record-session |
| I-2 | All write commands via REGISTRY |
| SEM-13 | Sequential guard chain |

---

## 6. Pre/Post Conditions

### sdd graph-guard check (BC-56-G1)

**Pre:**
- session_id доступен через `get_current_session_id()` или `--session-id` arg
- IMPLEMENT сессия объявлена (`sdd record-session` выполнен)

**Post:**
- Exit 0: `len(query_graph_calls(session_id=sid)) >= 1`
- Exit 1: 0 вызовов → stderr JSON с `I-GRAPH-GUARD-1`, `sdd complete` не выполняется

### BC-56-BC — BOUNDED_CONTEXT nodes

**Pre:** `bounded_contexts` секция в `sdd_config.yaml` существует и валидна

**Post:**
- Каждый FILE node имеет ≥1 `belongs_to` edge
- FILE без совпадения → `belongs_to → BOUNDED_CONTEXT:unclassified`
- `sdd graph-stats --node-type BOUNDED_CONTEXT` → count > 0

### BC-56-LAYER — LAYER nodes

**Pre:** `layers` секция в `sdd_config.yaml` существует

**Post:**
- FILE nodes с совпавшим path pattern имеют `in_layer` edge
- Непокрытые файлы: warning в stderr (не error), без `in_layer` edge
- `sdd explain LAYER:domain --edge-types in_layer` возвращает domain files

---

## 7. Use Cases

### UC-56-1: IMPLEMENT с graph-guard enforcement

1. LLM выполняет STEP 4.5 — traversal от anchor_nodes (Phase 56 mode)
2. `explain.py` → `log_graph_call(GraphCallEntry(command="explain", session_id=sid, ...))`
3. LLM пишет только файлы в write_scope (fallback запрещён — I-IMPLEMENT-GRAPH-2)
4. `sdd graph-guard check --task T-NNN`
   → `query_graph_calls(session_id=sid)` → count ≥ 1 → exit 0
5. `sdd complete T-NNN`

### UC-56-2: Degraded graph call logging

1. `sdd explain FILE:X --edge-types implements` → result_size.edges = 0
2. `log_graph_call(GraphCallEntry(..., result_size={"nodes": 1, "edges": 0}))`
3. В Phase 56: это STOP (I-IMPLEMENT-GRAPH-2 — fallback запрещён)
4. LLM: `sdd record-metric --key graph_degraded_reads --value 1 --phase N --task T-NNN`
5. Деградация аудируема через `sdd query-events --event MetricRecorded`

### UC-56-3: Phase Gate check (перед PLAN Phase 56)

```bash
sdd graph-stats --edge-type tested_by --format json
# {"edge_type": "tested_by", "count": 0} → Phase 56 BLOCKED
# {"edge_type": "tested_by", "count": 47} → gate passed
```

### UC-56-4: BOUNDED_CONTEXT exploration

```bash
sdd explain BOUNDED_CONTEXT:graph --edge-types belongs_to
→ все FILES в src/sdd/graph/

sdd trace BOUNDED_CONTEXT:context_kernel --edge-types imports
→ кто из других BC импортирует context_kernel (cross-BC dependencies)
```

### UC-56-5: Layer-aware LLM navigation (preview Phase 57)

```bash
sdd explain LAYER:domain --edge-types in_layer
→ domain layer files

sdd trace FILE:src/sdd/infra/db.py --edge-types calls,imports
→ кто зависит от инфраструктуры (input для arch-check в Phase 57)
```

---

## 8. Integration

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-55-P8 (Phase 55) | this uses | session_context.get_current_session_id() для GraphCallEntry |
| BC-55-P7 (Phase 55) | this extends | MODULE nodes → BOUNDED_CONTEXT (параллельная иерархия) |
| BC-55-P2 (Phase 55) | this uses | --edge-types в traversal для belongs_to/in_layer exploration |
| BC-55-P3 (Phase 55) | this extends | TaskNavigationSpec → добавляем anchor_nodes |
| EventStore | this → EventStore | MetricRecorded через REGISTRY pipeline |
| sdd_config.yaml | this extends | bounded_contexts + layers секции |
| Phase 57 | this → Phase 57 | LAYER nodes → violates edges; GraphCallLog → guard v2 |

---

## 9. Verification

| # | Test / Check | Invariant(s) |
|---|--------------|--------------|
| 1 | `log_graph_call(...)` пишет в `graph_calls.jsonl`, НЕ в `audit_log.jsonl` | I-GRAPH-CALL-LOG-1 |
| 2 | `query_graph_calls(session_id="X")` возвращает только записи с session_id="X" | BC-56-A1 |
| 3 | `query_graph_calls()` возвращает [] если файл отсутствует (нет ошибки) | BC-56-A1 |
| 4 | `graph-guard check` → exit 0 если ≥1 entry с session_id | I-GRAPH-GUARD-1 |
| 5 | `graph-guard check` → exit 1 если 0 entries | I-GRAPH-GUARD-1 |
| 6 | `sdd resolve` возвращает `score_normalized ∈ (0, 1)` | BC-56-S2 |
| 7 | `sdd resolve` с разными BM25 scores → `score_normalized` корректно монотонен | BC-56-S2 |
| 8 | `sdd explain NODE --edge-types tested_by` возвращает тесты после TestedByExtractor | BC-56-T1 |
| 9 | `sdd graph-stats --edge-type tested_by` → count > 0 после rebuild | BC-56-T1 |
| 10 | TaskSet с `anchor_nodes` парсится корректно в TaskNavigationSpec | BC-56-S1 |
| 11 | TaskSet с `resolve_keywords` (Phase 55) → backward compat, `is_anchor_mode() = False` | BC-56-S1 |
| 12 | BOUNDED_CONTEXT:graph exists в графе после nav-rebuild | BC-56-BC |
| 13 | FILE:src/sdd/graph/builder.py имеет `belongs_to → BOUNDED_CONTEXT:graph` | BC-56-BC |
| 14 | Файл вне classification rules → `belongs_to → BOUNDED_CONTEXT:unclassified` | I-BC-DETERMINISTIC-1 |
| 15 | `sdd graph-stats --node-type BOUNDED_CONTEXT` → count = количество BC + unclassified | BC-56-BC |
| 16 | FILE в src/sdd/infra/ имеет `in_layer → LAYER:infrastructure` | BC-56-LAYER |
| 17 | `sdd record-metric` → MetricRecorded в EventStore, queryable | BC-56-A2 |

---

## 11. Phase Acceptance Checklist

> Методология: `.sdd/docs/ref/phase-acceptance.md`

### Part 1 — In-Phase DoD

**Step U (Universal):**
```bash
sdd show-state                          # tasks_completed == tasks_total
sdd validate --check-dod --phase 56     # exit 0
python3 -m pytest tests/unit/ -q        # 0 failures
```

**Step 56-A — BOUNDED_CONTEXT и LAYER coverage (BC-56-BC, BC-56-LAYER):**
```bash
sdd graph-stats --node-type BOUNDED_CONTEXT --format json
# → {"count": N}, N > 0  (все BC из sdd_config.yaml представлены)

sdd graph-stats --node-type LAYER --format json
# → {"count": N}, N > 0

sdd graph-stats --edge-type belongs_to --format json
# → {"count": N}, N > 0  (FILE nodes классифицированы по BC)

sdd graph-stats --edge-type in_layer --format json
# → {"count": N}, N > 0  (FILE nodes классифицированы по Layer)

# BCResolver консистентность: нет расхождений между экстракторами
sdd arch-check --check bc-cross-dependencies --format json
# → exit 0 (информационный режим в Phase 56)
```

**Step 56-B — GraphCallLog и audit (BC-56-A1, BC-56-A2):**
```bash
# После любого graph navigation вызова — запись в graph_calls.jsonl
sdd explain COMMAND:complete --format json
cat .sdd/runtime/graph_calls.jsonl | tail -1 | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert 'session_id' in d"
# → exit 0

sdd record-metric --name test_metric --value 1.0 --phase 56
sdd query-events --type MetricRecorded --limit 1
# → MetricRecorded event в EventStore
```

**Step 56-C — graph-guard enforcement (BC-56-G1):**
```bash
# graph-guard check блокирует complete если не было graph вызовов
# (проверяется через integration test, не вручную)
python3 -m pytest tests/integration/test_graph_guard.py -q
# → PASS
```

**Step 56-D — TaskNavigationSpec v2 anchor_nodes (BC-56-S1):**
```bash
# TaskSet с anchor_nodes секцией парсится в TaskNavigationSpec.is_anchor_mode() = True
python3 -c "from sdd.tasks.navigation import TaskNavigationSpec; ts=TaskNavigationSpec(write_scope=(), anchor_nodes=('COMMAND:complete',)); assert ts.is_anchor_mode()"
# → exit 0
```

---

### Part 2 — Regression Guard

```bash
# (R-56-1) sdd explain существующих nodes — поведение идентично Phase 55
sdd explain COMMAND:complete --format json
# → ≥ тот же набор nodes что и в Phase 55

# (R-56-2) sdd resolve — не затронут
sdd resolve "complete" --format json
# → результат аналогичен Phase 55

# (R-56-3) MODULE nodes из Phase 55 — всё ещё присутствуют
sdd graph-stats --node-type MODULE --format json
# → count > 0 (не сломан ModuleEdgeExtractor)

# (R-56-4) tested_by edges из Phase 53 — всё ещё присутствуют
sdd graph-stats --edge-type tested_by --format json
# → count > 0 (не сломан TestedByEdgeExtractor)
```

Если хоть одна регрессия → **STOP → sdd report-error → recovery.md**.

---

### Part 3 — Transition Gate (before Phase 57)

Человек верифицирует перед `sdd activate-phase 57`:

```bash
# Gate 57-A: BOUNDED_CONTEXT coverage
sdd graph-stats --node-type BOUNDED_CONTEXT --format json
# Expected: {"count": N}, N > 0

# Gate 57-B: LAYER coverage
sdd graph-stats --node-type LAYER --format json
# Expected: {"count": N}, N > 0

# Gate 57-C: arch-check tool functional (не "violations == 0", а "tool works")
# см. phase-acceptance.md §6 — gate semantics
sdd arch-check --check bc-cross-dependencies --format json
# Expected: exit 0, JSON output (violations list может быть непустым — ОК)

# Gate 57-D: cross_bc_dependency edges
sdd graph-stats --edge-type cross_bc_dependency --format json
# Expected: {"count": N}, N ≥ 0 (может быть 0 если нет cross-BC imports — ОК)
```

---

### Part 4 — Rollback Triggers

Немедленно STOP если:
- `sdd graph-stats --node-type BOUNDED_CONTEXT` → `count: 0` после Phase 56 implementation
- `sdd arch-check --check bc-cross-dependencies` → exit 1 с ошибкой парсинга (не violation — а crash)
- GraphCallLog не пишет записи после graph вызовов (audit broken)
- `sdd graph-guard check` блокирует `sdd complete` даже при наличии graph вызовов в сессии
- Registration order нарушен: `CrossBCEdgeExtractor` запустился до `BoundedContextEdgeExtractor` → I-BC-RESOLVER-1 violation

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `ViolatesEdgeExtractor` (layer violation detection) | Phase 57 (BC-57-3) |
| `sdd arch-check` (layer compliance command) | Phase 57 (BC-57-3) |
| I-ARCH-1/2/3 invariants (enforced via sdd validate-invariants) | Phase 57 (BC-57-2) |
| graph-guard v2 (anchor_nodes coverage, не просто count≥1) | Phase 57 (BC-57-4) |
| `graph_coverage` marker в SpatialIndex.meta | Phase 57 (BC-57-5) |
| Удаление Task Inputs / resolve_keywords из parser.py | Phase 57 (BC-57-1) |
| `calls` edge distinction refinement (AST Call node detection) | Phase 57 (BC-57-6) |
| Cross-BC dependency analysis (BOUNDED_CONTEXT циклы) | Phase 57 (BC-57-2) |
| `sdd arch-check --check cycles` | Phase 57 |
| Embedding-based search в `sdd resolve` | Отдельная спека |
| Graph-level diff между состояниями фаз | Отдельная спека |
| I-RAG-SCOPE-ENTRY-1 hard enforcement (entry gate) | Phase 57 (BC-57-RAG-SOFT) |
| `NavigationResponse.based_on` | Phase 57 (BC-57-RAG-SOFT) |
| `EmbeddingProvider`, `EmbeddingCache`, `rank_documents()` | Phase 58 (BC-58-RAG) |
