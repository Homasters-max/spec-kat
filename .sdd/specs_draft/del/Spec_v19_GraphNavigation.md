# Spec_v19 — Phase 19: Graph Navigation (GN)

Status: Draft
Baseline: Spec_v18_SpatialIndex.md

---

## 0. Goal

Phase 18 дала агенту карту системы — плоский JSON-индекс с узлами.
Агент умеет находить узел по `node_id`, но не умеет **перемещаться по связям**:
не знает, что `COMMAND:complete` эмитирует `EVENT:TaskImplementedEvent`,
не знает, какие тесты проверяют инвариант `I-SI-1`.

Phase 19 добавляет **рёбра** и **единую точку входа** через DDD-язык:

```
System := ⟨Kernel, ValidationRuntime, SpatialIndex, GraphNavigation⟩
GN отвечает на вопрос: "как это связано и что это значит в терминах домена?"
```

Ключевые решения, принятые по итогам анализа плана:

1. **Edge priority** — рёбра не равны. `emits` важнее `imports`. Агент видит сначала
   семантически значимые связи.

2. **TERM → graph** — DDD-слой Phase 18 становится полноценным. TERM-узлы связаны с
   COMMAND, EVENT, TASK, INVARIANT через `means`-рёбра. Агент навигирует по концептам домена.

3. **`sdd resolve <query>`** — единая точка входа. Агент ВСЕГДА начинает отсюда:
   поиск по TERM + fuzzy → resolve узла → соседи с приоритетом.

---

## 1. Scope

### In-Scope

- **BC-19-0: DuckDB schema** — `spatial_nodes`, `spatial_edges` с `priority`, `node_tags` (schema.py)
- **BC-19-1: Graph loader** — AST-сканер + `means`-рёбра из glossary.yaml (loader.py)
- **BC-19-2: GraphQuerier** — `get_node()`, `search_nodes()`, `neighbors()` с сортировкой по priority (querier.py)
- **BC-19-3: TERM integration** — `means`-рёбра TERM → COMMAND/EVENT/TASK/INVARIANT; I-DDD-1
- **BC-19-4: sdd resolve** — unified DDD entrypoint: search → resolve → neighbors (nav_resolve.py)
- **BC-19-5: nav-neighbors, nav-invariant** — дополнительные CLI-команды
- **BC-19-6: Tests** — unit + integration
- **BC-19-7: Backend upgrade** — nav-get/nav-rebuild добавляют `--backend duckdb|json|both`

### Out of Scope

- Temporal navigation (nav-changed-since) — Phase 20
- TaskCheckpoint events — Phase 20
- ML-ранжирование, embedding search, shortest path — никогда
- Shortest path, граф-алгоритмы — никогда

---

## 2. Edge Priority Model

### Зачем нужны приоритеты (без ML)

Для агента `emits`-связь (команда → событие) семантически важнее, чем `imports`-связь
(модуль → модуль). Без приоритетов `nav-neighbors COMMAND:complete` вернёт 10+ соседей
в произвольном порядке — агент тратит лишние токены на фильтрацию.

Решение: статические priority weights в схеме. Детерминированная сортировка, никакого ML.

```yaml
# edge_priority (добавляется в spatial_edges.priority FLOAT)
emits:       1.0   # команда → событие: семантически главная связь
guards:      0.9   # guard → команда: enforcement связь
implements:  0.8   # файл → команда: реализация
depends_on:  0.7   # задача → задача: зависимость (TaskSet)
means:       0.6   # TERM → узел: DDD-семантика
tested_by:   0.5   # модуль → тест: покрытие
defined_in:  0.4   # команда → файл: физическое расположение
verified_by: 0.4   # инвариант → команда: проверка
imports:     0.3   # модуль → модуль: структурная зависимость
```

**I-GRAPH-PRIORITY-1:** `nav-neighbors` output MUST be sorted by `priority DESC`, then `dst ASC`
(стабильная сортировка для детерминизма при равных приоритетах).

---

## 3. Architecture / BCs

### BC-19-0: DuckDB Schema

```
src/sdd/spatial/graph/
  __init__.py
  schema.py      # DDL + ensure_spatial_schema()
```

```sql
-- В том же sdd_events.duckdb — 3 новые таблицы, без FK к events
CREATE TABLE IF NOT EXISTS spatial_nodes (
    node_id     VARCHAR NOT NULL PRIMARY KEY,
    kind        VARCHAR NOT NULL,       -- FILE|COMMAND|GUARD|REDUCER|EVENT|TASK|INVARIANT|TERM
    label       VARCHAR NOT NULL,
    path        VARCHAR,               -- NULL для TERM, INVARIANT
    summary     VARCHAR NOT NULL DEFAULT '',
    signature   VARCHAR NOT NULL DEFAULT '',
    meta_json   VARCHAR NOT NULL DEFAULT '{}',
    git_hash    VARCHAR,               -- NULL для TERM, INVARIANT
    indexed_at  BIGINT NOT NULL        -- Unix ms
);

CREATE TABLE IF NOT EXISTS spatial_edges (
    edge_id     VARCHAR NOT NULL PRIMARY KEY,   -- sha256(src+":"+kind+":"+dst)[:16]
    src         VARCHAR NOT NULL,
    dst         VARCHAR NOT NULL,
    kind        VARCHAR NOT NULL,    -- imports|emits|defined_in|depends_on|tested_by|
                                     -- verified_by|means|guards|implements
    edge_source VARCHAR NOT NULL,   -- I-GRAPH-2: "ast_import"|"ast_emits"|"registry"|
                                     -- "cli_route"|"taskset_depends_on"|"glossary"|
                                     -- "ast_tested_by"|"events_py"
    priority    FLOAT NOT NULL DEFAULT 0.3,   -- edge priority weight
    meta_json   VARCHAR NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS node_tags (
    node_id     VARCHAR NOT NULL,
    tag         VARCHAR NOT NULL,   -- "phase:19", "actor:llm", "I-2"
    PRIMARY KEY (node_id, tag)
);
```

`ensure_spatial_schema()` — идемпотентна (CREATE TABLE IF NOT EXISTS, без DROP).
Вызывается из `src/sdd/infra/db.py::ensure_sdd_schema()`.

### BC-19-1: Graph Loader (AST + TERM)

```
src/sdd/spatial/graph/
  loader.py      # scan_* + build_graph()
```

```python
class GraphLoader:
    """I-GRAPH-1: все рёбра из статического AST-анализа или явных источников."""

    def build_graph(self, project_root: str, db_path: str) -> GraphBuildResult: ...

    def scan_python_file(self, path: str) -> list[EdgeSpec]:
        """AST: import → imports (priority 0.3)
           class *Event(DomainEvent) → emits (priority 1.0) — для файлов с handle()"""

    def scan_events_file(self, path: str) -> list[EdgeSpec]:
        """events.py: каждый EventClass → EVENT:Name (defined_in, priority 0.4)"""

    def scan_registry(self, path: str) -> list[EdgeSpec]:
        """registry.py: REGISTRY[cmd] → COMMAND:cmd (cli_route, priority 0.8)"""

    def scan_cli_routes(self, path: str) -> list[EdgeSpec]:
        """cli.py: cmd → module (implements, priority 0.8)"""

    def scan_taskset(self, path: str) -> list[EdgeSpec]:
        """TaskSet: depends_on → (depends_on, priority 0.7)
           task_id → FILE (implements, priority 0.8)"""

    def scan_invariants(self) -> list[EdgeSpec]:
        """CLAUDE.md §INV: INVARIANT → COMMAND/GUARD (verified_by, priority 0.4)"""

    def scan_guards(self, path: str) -> list[EdgeSpec]:
        """guard файлы → COMMAND узлы (guards, priority 0.9)"""

    def scan_glossary(self, glossary_path: str) -> list[EdgeSpec]:
        """glossary.yaml: TERM:x → linked nodes (means, priority 0.6)
           edge_source = "glossary" """
```

**I-GRAPH-1:** Every edge derives from static AST analysis or explicit config (glossary.yaml, TaskSet).
No heuristics, no runtime introspection.

**I-GRAPH-2:** `edge_source VARCHAR NOT NULL` — каждое ребро имеет детерминированный источник.
Допустимые значения: `"ast_import"`, `"ast_emits"`, `"registry"`, `"cli_route"`,
`"taskset_depends_on"`, `"taskset_implements"`, `"glossary"`, `"ast_tested_by"`,
`"events_py"`, `"ast_guards"`.

**I-GRAPH-3:** For every INVARIANT node, exists at least one outgoing `verified_by` or
`introduced_in` edge.

**TERM → graph edges** (`scan_glossary`):

```yaml
# glossary.yaml entry:
- id: "activate_phase"
  links: ["COMMAND:activate-phase", "EVENT:PhaseActivated", "INVARIANT:NORM-ACTOR-001"]

# → EdgeSpec(src="TERM:activate_phase", dst="COMMAND:activate-phase",
#             kind="means", edge_source="glossary", priority=0.6)
```

### BC-19-2: GraphQuerier

```
src/sdd/spatial/graph/
  querier.py     # GraphQuerier
```

```python
class GraphQuerier:
    def __init__(self, db_path: str): ...

    def get_node(self, node_id: str) -> dict | None:
        """SELECT * FROM spatial_nodes WHERE node_id = ?"""

    def search_nodes(self, query: str, kind: str | None = None,
                     limit: int = 10) -> list[dict]:
        """Fuzzy search по label, summary. Для TERM — включает aliases из meta_json.
           Возвращает sorted by score DESC."""

    def neighbors(self, node_id: str, hops: int = 1,
                  mode: str = "POINTER") -> dict:
        """BFS до hops=2 (max). Результат sorted by priority DESC, dst ASC.
           I-GRAPH-PRIORITY-1."""

    def get_invariant_coverage(self, invariant_id: str) -> dict:
        """INVARIANT:I-X → verified_by + introduced_in edges."""

    def get_term_links(self, term_id: str) -> list[dict]:
        """TERM:x → means-рёбра с соседями."""
```

### BC-19-3: TERM Integration (I-DDD-1)

**I-DDD-1:** Every COMMAND, EVENT, TASK MUST be reachable from at least one TERM node
via `means`-edge. Verified by `GraphQuerier.check_ddd_coverage()`.

Поддержка этого инварианта:

```python
def check_ddd_coverage(self, db_path: str) -> DDDCoverageResult:
    """
    Для каждого COMMAND, EVENT, TASK:
    проверить: EXISTS (SELECT 1 FROM spatial_edges
               WHERE dst = node_id AND kind = 'means')
    Возвращает: {covered: [...], uncovered: [...]}
    I-DDD-1 PASS iff uncovered == []
    """
```

`nav-rebuild --backend duckdb` выводит предупреждение (не ошибку) при uncovered узлах.
Это позволяет итеративно расширять glossary.yaml без блокировки сборки.

### BC-19-4: sdd resolve — Unified DDD Entrypoint

```
src/sdd/spatial/commands/
  nav_resolve.py    # sdd resolve <query> [--limit N]
```

**Canonical agent start point.** Агент ВСЕГДА начинает с `sdd resolve`, не с `nav-get`.

```python
def main(args: list[str]) -> int:
    """
    1. Fuzzy search query → кандидаты (TERM приоритет)
    2. Если топ-1 = TERM → вернуть definition + linked nodes
    3. Если топ-1 = другой kind → вернуть SUMMARY + neighbors (POINTER)
    4. Если not_found → {status: not_found, must_not_guess: true, did_you_mean: [...]}
    """
```

**Output format:**
```json
// sdd resolve "activate phase"  (exit 0, попал в TERM)
{
  "resolved_via": "TERM:activate_phase",
  "term": {
    "node_id": "TERM:activate_phase",
    "label": "Activate Phase",
    "definition": "Human-only gate that transitions a PLANNED phase to ACTIVE state.",
    "aliases": ["phase activation", "activate phase"]
  },
  "node": {
    "node_id": "COMMAND:activate-phase",
    "kind": "COMMAND",
    "label": "sdd activate-phase",
    "summary": "..."
  },
  "neighbors": [
    {"node_id": "EVENT:PhaseActivated", "kind": "EVENT", "via_edge": "means", "priority": 0.6},
    {"node_id": "INVARIANT:NORM-ACTOR-001", "kind": "INVARIANT", "via_edge": "means", "priority": 0.6}
  ]
}

// sdd resolve "unknown xyz"  (exit 1)
{"status": "not_found", "must_not_guess": true,
 "query": "unknown xyz", "did_you_mean": ["TERM:activate_phase"]}
```

**I-DDD-2:** `sdd resolve` MUST always return `must_not_guess: true` on not_found.
Response MUST always include `neighbors` (может быть пустым []).

### BC-19-5: nav-neighbors, nav-invariant

```
src/sdd/spatial/commands/
  nav_neighbors.py    # sdd nav-neighbors <id> [--hops N] [--mode POINTER|SUMMARY]
  nav_invariant.py    # sdd nav-invariant <I-NNN>
```

**nav-neighbors output:**
```json
// sdd nav-neighbors COMMAND:complete --hops 2  (exit 0)
{
  "root": {"node_id": "COMMAND:complete", "kind": "COMMAND"},
  "neighbors": [
    {"node_id": "EVENT:TaskImplementedEvent", "hop": 1, "via_edge": "emits", "priority": 1.0},
    {"node_id": "FILE:src/sdd/commands/update_state.py", "hop": 1, "via_edge": "defined_in", "priority": 0.4},
    {"node_id": "TERM:complete_task", "hop": 2, "via_edge": "means", "priority": 0.6}
  ]
}
// Sorted: priority DESC, dst ASC при равных priority (I-GRAPH-PRIORITY-1)
```

**nav-invariant output:**
```json
// sdd nav-invariant I-SI-1  (exit 0)
{
  "invariant": {"node_id": "INVARIANT:I-SI-1", "summary": "Every indexed file has exactly one node..."},
  "verified_by": [{"node_id": "COMMAND:nav-rebuild", "priority": 0.4}],
  "introduced_in": {"node_id": "TASK:T-1801"}
}
```

### BC-19-6: Tests

```
tests/unit/spatial/graph/
  test_schema.py      # ensure_spatial_schema() на :memory:; идемпотентность
  test_loader.py      # fixture py-файлы → рёбра; I-GRAPH-1 (нет heuristics)
                      # I-GRAPH-2 (нет edge_source=""); I-GRAPH-3 (INVARIANT ≥1 edge)
                      # glossary.yaml → means-рёбра (I-DDD-1)
  test_querier.py     # :memory: DuckDB, get_node/search_nodes/neighbors
                      # I-GRAPH-PRIORITY-1: sorted by priority DESC

tests/unit/commands/
  test_nav_resolve.py # TERM hit → full response; not_found → must_not_guess
  test_nav_neighbors.py # priority sort; hops=2 BFS
  test_nav_invariant.py # exit 0 с verified_by; exit 1 если INVARIANT не найден

tests/integration/
  test_nav_duckdb.py  # nav-rebuild --backend both; SQL checks I-GRAPH-2, I-GRAPH-3, I-DDD-1
```

### BC-19-7: Backend Upgrade

**`src/sdd/spatial/commands/nav_get.py`** — добавить `--backend json|duckdb` (default `duckdb`).
**`src/sdd/spatial/commands/nav_rebuild.py`** — добавить `--backend json|duckdb|both` (default `both`).

JSON-бэкенд Phase 18 остаётся как fallback. DuckDB становится основным.

**`src/sdd/infra/db.py`** — `ensure_sdd_schema()` вызывает `ensure_spatial_schema()`.

**`src/sdd/cli.py`** — добавить: `nav-neighbors`, `nav-invariant`, `resolve`.

---

## 4. Domain Events

Phase 19 не эмитирует domain events в производственный EventLog.
`GraphLoader.build_graph()` — read-only по отношению к SDD-ядру; пишет только в `spatial_nodes/edges`.

---

## 5. Invariants

### New Invariants — Graph Navigation Layer

| ID | Statement | Phase | Verification |
|----|-----------|-------|-------------|
| I-GRAPH-1 | Every edge derives from static AST analysis or explicit config (no heuristics) | 19 | `test_loader.py` |
| I-GRAPH-2 | `edge_source VARCHAR NOT NULL` — каждое ребро имеет детерминированный источник | 19 | SQL check + `test_loader.py` |
| I-GRAPH-3 | For every INVARIANT node, ≥1 outgoing `verified_by` or `introduced_in` edge | 19 | SQL check + `test_loader.py` |
| I-GRAPH-PRIORITY-1 | `nav-neighbors` output sorted by priority DESC, dst ASC | 19 | `test_querier.py`, `test_nav_neighbors.py` |
| I-DDD-1 | Every COMMAND, EVENT, TASK reachable from ≥1 TERM via `means`-edge | 19 | `check_ddd_coverage()` + `test_nav_duckdb.py` |
| I-DDD-2 | `sdd resolve` MUST return `must_not_guess: true` on not_found | 19 | `test_nav_resolve.py` |

### Preserved Invariants (Phase 18)

I-NAV-1..3, I-CONTEXT-1, I-SI-1..4, I-DDD-0 — без изменений.

---

## 6. Pre/Post Conditions

### M0 — DuckDB Schema

**Pre:**
- Phase 18 COMPLETE (spatial_index.json актуален)
- `src/sdd/infra/db.py` содержит `ensure_sdd_schema()`

**Post:**
- `src/sdd/spatial/graph/schema.py` создан
- `ensure_spatial_schema()` идемпотентна на `:memory:` и реальном DuckDB
- `ensure_sdd_schema()` вызывает `ensure_spatial_schema()`
- `tests/unit/spatial/graph/test_schema.py` PASS

### M1 — Graph Loader

**Pre:** M0 COMPLETE, Phase 18 M1 COMPLETE (nodes.py с TermNode)

**Post:**
- `loader.py` создан
- `scan_glossary()` создаёт `means`-рёбра с `edge_source="glossary"`
- I-GRAPH-1: нет heuristic-рёбер (проверено в тестах)
- I-GRAPH-2: нет пустого `edge_source` (SQL CHECK в тесте)
- I-GRAPH-3: все INVARIANT-узлы имеют ≥1 исходящее ребро
- `tests/unit/spatial/graph/test_loader.py` PASS

### M2 — GraphQuerier

**Pre:** M0 COMPLETE

**Post:**
- `querier.py` создан
- `neighbors()` сортирует по `priority DESC, dst ASC`
- `check_ddd_coverage()` работает
- `tests/unit/spatial/graph/test_querier.py` PASS

### M3 — TERM Integration + I-DDD-1

**Pre:** M1, M2 COMPLETE

**Post:**
- `nav-rebuild --backend duckdb` создаёт `means`-рёбра из glossary.yaml
- `check_ddd_coverage()` возвращает `uncovered == []` (для текущего glossary.yaml)
- I-DDD-1 верифицирован SQL-проверкой в integration test

### M4 — sdd resolve

**Pre:** M2, M3 COMPLETE

**Post:**
- `nav_resolve.py` создан
- TERM-hit: возвращает `{term, node, neighbors}`
- not_found: exit 1, `must_not_guess: true`
- I-DDD-2 PASS
- `tests/unit/commands/test_nav_resolve.py` PASS

### M5 — nav-neighbors, nav-invariant

**Pre:** M2 COMPLETE

**Post:**
- `nav_neighbors.py`, `nav_invariant.py` созданы
- priority sort верифицирован
- `cli.py` зарегистрированы 3 новые команды
- Unit-тесты PASS

### M6 — Integration

**Pre:** M0..M5 COMPLETE

**Post:**
- `SELECT count(*) FROM spatial_nodes` > 100 после `nav-rebuild --backend duckdb`
- `SELECT count(*) FROM spatial_edges WHERE edge_source IS NULL OR edge_source = ''` = 0
- Каждый INVARIANT-узел имеет ≥1 исходящее ребро
- `sdd nav-invariant I-SI-1` exit 0 с непустым `verified_by`
- `sdd nav-neighbors COMMAND:complete --hops 2` ≥3 соседей (sorted by priority)
- `sdd resolve "activate phase"` → `TERM:activate_phase`
- Все тесты Phase 18 по-прежнему проходят (JSON-бэкенд сохранён)
- `tests/integration/test_nav_duckdb.py` PASS

---

## 7. Use Cases

### UC-19-1: Agent Starts Navigation via sdd resolve

**Actor:** LLM-агент
**Trigger:** агент получил задачу "разберись, как работает complete"
**Pre:** Phase 19 ACTIVE
**Steps:**
1. `sdd resolve "complete task"` → TERM:complete_task → definition + neighbors
2. Видит: `COMMAND:complete` (means, priority 0.6), `EVENT:TaskImplementedEvent` (means, priority 0.6)
3. `sdd nav-get COMMAND:complete --mode SIGNATURE` → детали команды
4. `sdd nav-neighbors COMMAND:complete --hops 1` → `emits: TaskImplementedEvent` (priority 1.0 — первый)
**Post:** агент построил контекст за 4 детерминированных шага через DDD-язык

### UC-19-2: Priority-Sorted Neighbors

**Actor:** LLM-агент
**Trigger:** `sdd nav-neighbors GUARD:scope --hops 1`
**Pre:** Phase 19 ACTIVE
**Steps:**
1. Результат: `guards → COMMAND:complete` (priority 0.9), `imports → FILE:…` (priority 0.3)
2. Агент видит semantic связь первой, structural — последней
**Post:** I-GRAPH-PRIORITY-1 — агент не тратит токены на фильтрацию нерелевантных связей

### UC-19-3: DDD Coverage Check

**Actor:** разработчик при добавлении новой команды
**Trigger:** `sdd nav-rebuild --backend duckdb`
**Pre:** добавлена новая команда `sdd show-path`, но в glossary.yaml нет записи
**Steps:**
1. `nav-rebuild` завершается exit 0 (не блокирует)
2. В stdout: `warning: I-DDD-1 uncovered nodes: ["COMMAND:show-path"]`
3. Разработчик добавляет запись в glossary.yaml
**Post:** I-DDD-1 достигается итеративно, не блокирует workflow

### UC-19-4: Invariant Coverage Navigation

**Actor:** LLM-агент в VALIDATE-сессии
**Trigger:** нужно проверить, что I-SI-1 верифицирован
**Pre:** Phase 19 ACTIVE
**Steps:**
1. `sdd nav-invariant I-SI-1` → `verified_by: [COMMAND:nav-rebuild]` + `introduced_in: TASK:T-1801`
2. Агент знает: тест в `test_nav_rebuild.py` должен это покрывать
**Post:** I-GRAPH-3 обеспечивает трассируемость каждого инварианта

---

## 8. Verification

### Phase 19 Complete iff

```bash
# Phase 18 тесты всё ещё PASS
pytest tests/unit/spatial/ tests/integration/test_nav_rebuild_integration.py -q

# Phase 19 unit
pytest tests/unit/spatial/graph/ tests/unit/commands/test_nav_*.py -q

# Phase 19 integration (SQL invariants)
sdd nav-rebuild --backend both
python3 -c "
import duckdb
c = duckdb.connect('.sdd/state/sdd_events.duckdb')
assert c.execute('SELECT count(*) FROM spatial_edges WHERE edge_source IS NULL OR edge_source = \"\"').fetchone()[0] == 0, 'I-GRAPH-2 FAIL'
assert c.execute('SELECT count(*) FROM spatial_nodes WHERE kind = \"TERM\"').fetchone()[0] >= 8, 'TERM nodes FAIL'
print('Graph invariants: PASS')
"
pytest tests/integration/test_nav_duckdb.py -q

# DDD layer
sdd resolve "activate phase"      # exit 0, term hit
sdd resolve "unknown xyz"         # exit 1, must_not_guess
sdd nav-neighbors COMMAND:complete --hops 2  # ≥3 соседей, sorted
sdd nav-invariant I-SI-1          # exit 0, непустой verified_by
```

### Test Suite

| # | File | Invariants |
|---|------|------------|
| 1 | `tests/unit/spatial/graph/test_schema.py` | idempotency, table structure |
| 2 | `tests/unit/spatial/graph/test_loader.py` | I-GRAPH-1, I-GRAPH-2, I-GRAPH-3, means edges |
| 3 | `tests/unit/spatial/graph/test_querier.py` | I-GRAPH-PRIORITY-1, DDD coverage |
| 4 | `tests/unit/commands/test_nav_resolve.py` | I-DDD-2, TERM-hit response |
| 5 | `tests/unit/commands/test_nav_neighbors.py` | priority sort, hops=2 |
| 6 | `tests/unit/commands/test_nav_invariant.py` | I-GRAPH-3, verified_by |
| 7 | `tests/integration/test_nav_duckdb.py` | I-GRAPH-2, I-GRAPH-3, I-DDD-1, SQL |

### Stabilization Criteria

1. `SELECT count(*) FROM spatial_nodes` > 100 после `nav-rebuild --backend duckdb`
2. `SELECT count(*) FROM spatial_edges WHERE edge_source IS NULL OR edge_source = ''` = 0 (I-GRAPH-2)
3. Каждый INVARIANT-узел имеет ≥1 исходящее ребро (I-GRAPH-3)
4. `sdd nav-invariant I-SI-1` exit 0 с непустым `verified_by`
5. `sdd nav-neighbors COMMAND:complete --hops 2` ≥3 соседей, sorted by priority
6. `sdd resolve "activate phase"` exit 0, `TERM:activate_phase` в ответе
7. `sdd resolve "unknown xyz"` exit 1, `must_not_guess: true` (I-DDD-2)
8. Все тесты Phase 18 по-прежнему проходят

---

## 9. Out of Scope

| Item | Owner |
|------|-------|
| Temporal navigation (nav-changed-since) | Phase 20 |
| TaskCheckpoint events | Phase 20 |
| NORM-NAV-001 в norm_catalog | Phase 20 |
| git bridge, ContentAddressableStore | Phase 20 |
| ML ranking, embedding, shortest path | никогда |
| Graph visualization | никогда |
