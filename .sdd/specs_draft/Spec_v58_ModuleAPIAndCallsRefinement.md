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

### Out of Scope

| Item | Owner |
|------|-------|
| Embedding-based search в `sdd resolve` (I-SEARCH-NO-EMBED-1) | Phase 59+ |
| DECOMPOSE/PLANNER адаптация (session FSM) | Другой домен |
| Cross-BC dependency matrix (аналитика) | Phase 59+ |
| Graph-level diff между фазами | Phase 59+ |
| calls confidence ≥ 0.9 → violation enforcement | Phase 59+ (после BC-58-2 поднимает до 0.85) |

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

---

## 11. Risk Notes

| Risk | Mitigation |
|------|------------|
| calls confidence 0.85 < 0.9 → violations не включаются | Намеренно; phase boundary чёткая |
| ModulePublicAPIExtractor зависит от `__init__.py` structure | Fallback: нет `__all__` → все files public |
| INVARIANT nodes из статического YAML — ручное ведение | Автогенерация из SDD_Spec_v1.md парсером в Phase 59+ |
| DSL parser — новый язык, сложность разрастается | Жёсткий MVP: только FROM/EXPAND/TRACE/FILTER, без OR/AND |

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
