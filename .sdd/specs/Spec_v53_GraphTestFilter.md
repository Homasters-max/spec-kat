# Spec_v53 — Graph-Based Test Filtering (TestedByEdgeExtractor + sdd test-filter)

**Status:** DRAFT — for review before DRAFT_SPEC session
**Depends on:** Phase 52 DoD полностью выполнен (`implements` edges, graph navigation CLI shipped)

**Motivation:** Phase 52 объявляет `tested_by` в `EDGE_KIND_PRIORITY` (priority 0.80) и
`_EXPLAIN_OUT_KINDS`, но ни один extractor эти рёбра не производит. Этот спек закрывает gap
и делает граф управляющим execution, а не только анализом.

---

## 0. Проблема

`sdd explain COMMAND:complete --format json` включает `tested_by` в список out-edge видов,
но возвращает ноль таких рёбер — граф не знает, какие тесты покрывают какой компонент.

Следствия:
1. VALIDATE-сессии запускают весь `test` suite при изменении одного handler'а.
2. Граф не отвечает на вопрос "что тестирует этот код?"
3. `tested_by` в `_EXPLAIN_OUT_KINDS` — мёртвый интерфейс: обещан, не реализован.

---

## 1. Новый node kind: TEST

**I-TEST-NODE-1**: `TEST` — самостоятельный SpatialNode kind. Представляет один тестовый файл.
`node_id = f"TEST:{path}"`, где `path` — относительный путь от корня проекта.

Пример: `TEST:tests/unit/commands/test_complete.py`

**I-TEST-NODE-2**: TEST-узлы строятся `IndexBuilder` сканированием `tests/unit/` и
`tests/integration/`. Файлы из `tests/property/`, `tests/fuzz/`, `tests/regression/`
включаются с metadata `tier: slow`.

**I-TEST-NODE-3**: TEST и FILE — взаимоисключающие виды по path-префиксу:
`tests/**` → TEST, `src/**` → FILE. Один файл не может быть одновременно TEST и FILE.

**Scope note**: `scope.source_root: src/sdd/` не меняется. Скан TEST-узлов — отдельный проход
по `tests/` в IndexBuilder. LLM read guards (NORM-SCOPE-001) не затрагиваются.

---

## 2. TestedByEdgeExtractor

```python
# src/sdd/graph/extractors/tested_by_edges.py

class TestedByEdgeExtractor:
    """Emit 'tested_by' edges: COMMAND → TEST and FILE → TEST.

    Strategy: filename convention only (deterministic, no heuristics).
      tests/unit/commands/test_complete.py
        → COMMAND:complete
        → FILE:src/sdd/commands/complete.py

    Mapping rule (bidirectional derivation from TEST node path):
      TEST:tests/unit/<mod>/test_<name>.py
        src node → FILE:src/sdd/<mod>/<name>.py
        cmd node → COMMAND:<name> (dash-normalised: underscores → dashes)

    I-GRAPH-EXTRACTOR-2: no open() calls; all content via index.read_content(node).
    I-GRAPH-FINGERPRINT-1: EXTRACTOR_VERSION required.
    """
    EXTRACTOR_VERSION: ClassVar[str] = "tested_by_v1"
```

**Edge direction** (оба ребра эмитируются при совпадении по filename convention):

```
COMMAND:complete        --tested_by--> TEST:tests/unit/commands/test_complete.py
FILE:src/sdd/commands/complete.py --tested_by--> TEST:tests/unit/commands/test_complete.py
```

- COMMAND-ребро: `sdd explain COMMAND:complete` напрямую находит тест-файл.
- FILE-ребро: `sdd explain FILE:src/sdd/commands/complete.py` тоже находит тест-файл.

**I-GRAPH-TESTED-BY-1**: `TestedByEdgeExtractor` использует ТОЛЬКО filename convention.
Никаких AST-эвристик, pattern-matching по именам функций, импортам. Единственный источник
рёбер — соответствие пути TEST-узла пути source-узла по детерминированному правилу маппинга.

**I-GRAPH-TESTED-BY-2**: `tested_by`-ребро эмитируется ТОЛЬКО если destination TEST-узел
существует в SpatialIndex (IndexBuilder его отсканировал). Фантомные рёбра запрещены.

---

## 3. sdd test-filter

```bash
sdd test-filter --node NODE_ID [--tier fast|default|full]
```

**Алгоритм**:
1. Получить граф (из кеша или построить).
2. BFS от NODE_ID по out-edges вида `tested_by`, глубина ≤ 2, собрать TEST-узлы.
3. Если TEST-узлов ноль → fallback на tier (warn в stderr), вернуть его returncode.
4. Запустить `pytest <paths...> -q -m "not pg"`, вернуть его returncode.

**Tier fallback**:
- `--tier fast` → `test_fast`
- `--tier default` → `test` (по умолчанию)
- `--tier full` → `test_full`

**I-TEST-FILTER-1**: `sdd test-filter` завершается с returncode pytest. Ноль TEST-узлов —
предупреждение, не ошибка. Fallback на tier-default — корректное поведение.

**I-TEST-FILTER-2**: ключ `test_filter` в `project_profile.yaml` начинается с `test` →
автоматически исключается из task mode (I-TASK-MODE-1).

**project_profile.yaml** (добавляется в Phase 53):
```yaml
test_filter:  sdd test-filter --node {node_id} --tier default
```

---

## 4. Инварианты

| ID | Утверждение |
|---|---|
| I-TEST-NODE-1 | `TEST` — самостоятельный node kind для файлов под `tests/` |
| I-TEST-NODE-2 | IndexBuilder сканирует `tests/unit/` и `tests/integration/`; `tests/property/` и `tests/fuzz/` → `tier: slow` |
| I-TEST-NODE-3 | `tests/**` → TEST, `src/**` → FILE; виды взаимоисключающие |
| I-GRAPH-TESTED-BY-1 | Только filename convention; никаких AST-эвристик |
| I-GRAPH-TESTED-BY-2 | `tested_by` только к существующим TEST-узлам; фантомы запрещены |
| I-TEST-FILTER-1 | `sdd test-filter` возвращает returncode pytest; ноль-узлы → fallback |
| I-TEST-FILTER-2 | ключ `test_filter` исключён из task mode автоматически |

---

## 5. Scope & Dependencies

**Depends on**: Phase 52 DoD — `implements` edges, `sdd explain/resolve/trace` CLI

**Phase ordering note:** Phase 53 MUST be COMPLETE before Phase 56 PLAN is approved.
Phase 56 Phase Gate (`sdd graph-stats --edge-type tested_by → count > 0`) depends on
TestedByEdgeExtractor shipped here. BC-56-T1 in Spec_v56 is REMOVED from Phase 56
in-scope (converted to phase gate check only).

**Новые файлы**:
```
src/sdd/graph/extractors/tested_by_edges.py       — TestedByEdgeExtractor
src/sdd/graph_navigation/cli/test_filter.py        — sdd test-filter handler
tests/unit/graph/test_tested_by_extractor.py
tests/unit/graph_navigation/test_test_filter_cli.py
```

**Изменяемые файлы**:
```
src/sdd/spatial/nodes.py          — добавить "TEST" в валидные kinds
src/sdd/graph/builder.py          — зарегистрировать TestedByEdgeExtractor
src/sdd/cli.py                    — зарегистрировать sdd test-filter
.sdd/config/project_profile.yaml  — добавить test_filter команду
```

`src/sdd/graph/types.py` — изменений нет (`tested_by: 0.80` уже в `EDGE_KIND_PRIORITY`).

---

## 6. Verification

| Тест | Инвариант |
|---|---|
| `test_test_node_kind_not_file` | I-TEST-NODE-3: TEST и FILE — взаимоисключающие |
| `test_tested_by_edges_filename_convention` | I-GRAPH-TESTED-BY-1: `test_complete.py` → ребро к `COMMAND:complete` |
| `test_tested_by_no_phantom_edges` | I-GRAPH-TESTED-BY-2: нет ребра если TEST-узел отсутствует |
| `test_tested_by_no_ast_heuristics` | I-GRAPH-TESTED-BY-1: extractor не читает содержимое тест-файлов |
| `test_test_filter_runs_targeted_pytest` | I-TEST-FILTER-1: `sdd test-filter --node COMMAND:complete` запускает только test_complete.py |
| `test_test_filter_fallback_when_no_edges` | I-TEST-FILTER-1: предупреждение + fallback на tier |

---

## 7. Tier-иерархия (Phase 52 → Phase 53)

Phase 52 поставляет базовый tier contract. Phase 53 добавляет `test_filter` как прицельный tier:

```
test_filter  (graph-targeted, VALIDATE с известным node_id)  ←  самый быстрый
test_fast    (unit only, IMPLEMENT loop)
test         (unit + integration, VALIDATE default, coverage gate)
test_full    (все наборы, CHECK_DOD, coverage gate)
test_pg      (PG-only, explicit env)                          ←  ортогонален остальным
```

Правило использования:
- **VALIDATE** с конкретным изменённым узлом → `test_filter`, при fallback → `test`
- **VALIDATE** без известного node_id → `test`
- **CHECK_DOD** → `test_full` (без исключений)
- **IMPLEMENT** loop → `test_fast`
