# Spec_v36 — Phase 36: Graph Navigation (GN)

Status: Draft
Baseline: Spec_v18_SpatialIndex.md
Supersedes: Spec_v19_v1_GraphNavigation.md (Phase 19→36 перенумерация; I-PHASE-SEQ-1)
Session: grill-me 2026-04-26 — архитектурные решения зафиксированы
Revision: improve-codebase-architecture 2026-04-26 — pipeline deepening; SpatialIndex.read_content() + strict I-GRAPH-FS-ISOLATION-1 (no carve-out)
Revision: 2026-04-27 — Phase 19→36 перенумерация; SDD_DSN→SDD_DATABASE_URL; open_graph_connection() wrapper

---

## 0. Goal

Phase 18 дала агенту карту системы — плоский JSON-индекс с узлами.
Агент умеет находить узел по `node_id`, но не умеет **перемещаться по связям**.

Phase 36 добавляет **рёбра** и **единую точку входа** через DDD-язык:

```
System := ⟨Kernel, ValidationRuntime, SpatialIndex, GraphNavigation⟩
GN отвечает на вопрос: "как это связано и что это значит в терминах домена?"
```

### Ключевые архитектурные решения

1. **Postgres backend** — граф живёт в схеме `graph` единой Postgres БД. После Phase 32
   (PostgresMigration) EventLog тоже живёт в Postgres — единая БД для graph и EventLog.

2. **Typed registry space** — `node_id` формат (`NAMESPACE:id`) является типизированной
   ссылкой. Typed registry строится из детерминированных источников per namespace.

3. **TERM = слой навигации, не существования** — TERM определяет reachability и
   семантику. COMMAND без TERM — валидно. TERM со сломанной ссылкой — violation.

4. **Graph = SSOT структурных фактов** — команды, события, инварианты, термины.
   Flat-docs = SSOT протокола (session FSM, SEM-правила, роли).

5. **`invariants.yaml`** — machine-readable источник инвариантов. CLAUDE.md §INV
   = generated view (`sdd nav-export --invariants`).

6. **`emits`-рёбра = validated inference** — AST return analysis + DomainEvent
   registry + handler binding + execution path constraint. Нет heuristics.

7. **BFS сортировка** — `hop ASC, priority DESC, dst ASC`. Семантическая близость
   (расстояние) важнее веса отдельного ребра.

8. **`edge_id` = семантическая дедупликация** — `sha256(src+":"+kind+":"+dst)[:16]`.
   Один src→dst+kind = одна связь независимо от источника.

9. **3-слойная модель (строгая FS-изоляция):**
   ```
   [Filesystem]                    ← единственное место open()
         ↓
   [IndexBuilder + SpatialIndex]   ← адаптер; eager build: metadata + content за один проход
         ↓
   [GraphLoader]                   ← чистая логика (AST, edges); FS-free, YAML-free
         ↓
   [Postgres graph]
   ```
   `IndexBuilder.build()` = единственный filesystem reader; читает metadata + content за
   один проход. `SpatialIndex` = иммутабельный snapshot (frozen=True, content_map заполнен).
   `read_content(node)` = dict lookup без I/O. Инвалидация — внешняя через staleness.py.
   `GraphLoader` не знает о filesystem, YAML, project_root. (I-SI-SNAPSHOT-1, I-GRAPH-FS-ISOLATION-1)

---

## 1. Scope

### In-Scope

- **BC-36-0: Postgres Graph Schema** — `graph.spatial_nodes`, `graph.spatial_edges`,
  `graph.node_tags` (schema.py)
- **BC-36-1: SpatialIndex API Extension** — `iter_files()`, `iter_terms()`,
  `iter_invariants()`, `iter_tasks()`, `typed_registry()`, `read_content()`, `content_map`
  добавляются в `SpatialIndex`; `frozen=True` (I-SI-SNAPSHOT-1)
- **BC-36-2: IndexBuilder Extension** — INVARIANT-узлы мигрируют с CLAUDE.md →
  `invariants.yaml`; IndexBuilder остаётся единственным filesystem reader
- **BC-36-3: Graph Loader** — FS-free преобразователь: `build_graph(index, conn)`,
  AST-сканы через `iter_files()`, config-рёбра через `iter_terms/invariants/tasks()`
  (loader.py)
- **BC-36-4: GraphQuerier** — `get_node()`, `search_nodes()`, `neighbors()` через
  psycopg + `WITH RECURSIVE` CTE (querier.py)
- **BC-36-4a: open_graph_connection()** — unified connection helper; `SDD_DATABASE_URL`
  (connections.py)
- **BC-36-5: TERM Integration** — typed `means`-рёбра; I-DDD-1 (typed reference check)
- **BC-36-6: sdd resolve** — unified DDD entrypoint: search → resolve → neighbors
  (nav_resolve.py), Postgres-native fuzzy
- **BC-36-7: nav-neighbors, nav-invariant** — дополнительные CLI-команды
- **BC-36-8: Tests** — unit + integration
- **BC-36-9: Backend registration** — nav-get/nav-rebuild получают `--backend postgres`
- **BC-36-10: invariants.yaml + sdd nav-export** — machine-readable инварианты;
  I-INV-EXPORT-1

### Out of Scope

- `observed_in` edges, `eventlog-projector`, `nav-drift` — Phase 34+
- Temporal navigation (nav-changed-since) — Phase 34+
- TaskCheckpoint events — Phase 34+
- ML-ранжирование, embedding search, shortest path — никогда
- Graph visualization, Apache AGE — никогда
- Causal graph (event ordering as proxy for causation) — запрещено навсегда (нарушает I-GRAPH-1)

---

## 2. Edge Priority Model

### Приоритеты рёбер

```yaml
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

**I-GRAPH-PRIORITY-1:** `nav-neighbors` output MUST be sorted by `hop ASC`,
then `priority DESC`, then `dst ASC` (стабильная сортировка).

### Три слоя системы (namespace governance)

```
L1 — COMMAND (governed):   registry.py = SSOT существования
                            I-DDD-1 проверяет валидность TERM-ссылок
L2 — EVENT (observed):     events.py = SSOT определений
                            coverage — observational, не enforced
L3 — TASK (ephemeral):     TaskSet_vN.md = SSOT per phase
                            coverage — observational, не enforced
```

---

## 3. Architecture / BCs

### BC-36-0: Postgres Graph Schema

```
src/sdd/spatial/graph/
  __init__.py
  schema.py      # DDL + ensure_graph_schema()
```

```sql
CREATE SCHEMA IF NOT EXISTS graph;

CREATE TABLE IF NOT EXISTS graph.spatial_nodes (
    node_id     VARCHAR NOT NULL PRIMARY KEY,
    kind        VARCHAR NOT NULL,
    label       VARCHAR NOT NULL,
    path        VARCHAR,
    summary     VARCHAR NOT NULL DEFAULT '',
    signature   VARCHAR NOT NULL DEFAULT '',
    meta_json   VARCHAR NOT NULL DEFAULT '{}',
    git_hash    VARCHAR,
    indexed_at  BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph.spatial_edges (
    edge_id     VARCHAR NOT NULL PRIMARY KEY,
    src         VARCHAR NOT NULL,
    dst         VARCHAR NOT NULL,
    kind        VARCHAR NOT NULL,
    edge_source VARCHAR NOT NULL,
    priority    FLOAT NOT NULL DEFAULT 0.3,
    meta_json   VARCHAR NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS graph.node_tags (
    node_id     VARCHAR NOT NULL,
    tag         VARCHAR NOT NULL,
    PRIMARY KEY (node_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON graph.spatial_edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON graph.spatial_edges(dst);
CREATE INDEX IF NOT EXISTS idx_edges_kind ON graph.spatial_edges(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON graph.spatial_nodes(kind);
```

**`ensure_graph_schema(conn)`** — идемпотентна (CREATE IF NOT EXISTS, без DROP).
Принимает `psycopg.Connection`.

**Topological contract:**
- `graph.*` — граф (Phase 36)
- `p_sdd.*` — EventLog + State (Phase 32 PostgresMigration)
- `shared.*` — фреймворковые таблицы (Phase 32)
- Нет FK между схемами — граф является производной проекцией (I-1)

### BC-36-1: SpatialIndex API Extension

```
src/sdd/spatial/
  nodes.py     # SpatialEdge обновлён: edge_source, priority как first-class поля
  index.py     # SpatialIndex расширен: iter_* методы + typed_registry()
```

**`SpatialEdge` обновление** (новые поля):

```python
@dataclass(frozen=True)
class SpatialEdge:
    edge_id:     str    # sha256(src+":"+kind+":"+dst)[:16]
    src:         str
    dst:         str
    kind:        str
    edge_source: str    # I-GRAPH-2: детерминированный источник
    priority:    float = 0.3
    meta:        dict = field(default_factory=dict)
```

**`SpatialIndex` новый API:**

```python
@dataclass(frozen=True)
class SpatialIndex:
    nodes:         dict[str, SpatialNode]
    content_map:   dict[str, str]          # node_id → file content; FILE nodes only
    built_at:      str
    git_tree_hash: str | None
    version:       int = 1
    meta:          dict = field(default_factory=dict)

    def iter_files(self) -> Iterable[SpatialNode]:
        """Все FILE-узлы. Единственная точка входа для GraphLoader AST-сканов."""
        return (n for n in self.nodes.values() if n.kind == "FILE")

    def iter_terms(self) -> Iterable[SpatialNode]:
        """Все TERM-узлы с links для построения means-рёбер."""
        return (n for n in self.nodes.values() if n.kind == "TERM")

    def iter_invariants(self) -> Iterable[SpatialNode]:
        """Все INVARIANT-узлы для построения verified_by/introduced_in рёбер."""
        return (n for n in self.nodes.values() if n.kind == "INVARIANT")

    def iter_tasks(self) -> Iterable[SpatialNode]:
        """Все TASK-узлы для построения depends_on/implements рёбер."""
        return (n for n in self.nodes.values() if n.kind == "TASK")

    def typed_registry(self) -> dict[str, set[str]]:
        """
        Проекция nodes по namespace. Нет file I/O.
        Результат: {"COMMAND": {"complete", ...}, "EVENT": {"TaskImplementedEvent", ...}, ...}
        Используется GraphLoader для I-DDD-1 и I-GRAPH-EMITS-1 validated inference.
        """
        result: dict[str, set[str]] = {}
        for node_id in self.nodes:
            ns, _, id_ = node_id.partition(":")
            result.setdefault(ns, set()).add(id_)
        return result

    def read_content(self, node: SpatialNode) -> str:
        """
        Dict lookup в content_map — нет I/O, нет state.
        IndexBuilder.build() выполнил весь file I/O однократно.
        Raises KeyError если node не FILE-узел или отсутствует в content_map.
        """
        return self.content_map[node.node_id]
```

**I-INDEX-FILE-COVERAGE-1:** All Python files in `src/sdd/` relevant for graph
construction MUST be represented as FILE nodes in SpatialIndex. GraphLoader MUST
NOT access filesystem directly (I-GRAPH-FS-ISOLATION-1).

### BC-36-2: IndexBuilder Extension

```
src/sdd/spatial/
  index.py     # _build_invariant_nodes() мигрирует с CLAUDE.md → invariants.yaml
```

**Ключевое изменение:** `_build_invariant_nodes()` переезжает с regex-парсинга
CLAUDE.md на `yaml.safe_load` из `.sdd/config/invariants.yaml`.

```python
def _build_invariant_nodes(self) -> list[SpatialNode]:
    """
    Reads .sdd/config/invariants.yaml (SSOT, Phase 36+).
    CLAUDE.md §INV = generated view — не читается для узлов.
    """
    invariants_path = os.path.join(self._root, ".sdd", "config", "invariants.yaml")
    if not os.path.isfile(invariants_path):
        return []
    with open(invariants_path) as f:
        data = yaml.safe_load(f)
    nodes = []
    for inv in data.get("invariants", []):
        inv_id = inv["id"]
        nodes.append(SpatialNode(
            node_id=f"INVARIANT:{inv_id}",
            kind="INVARIANT",
            label=inv_id,
            path=None,
            summary=inv.get("statement", f"INVARIANT:{inv_id}").split("\n")[0].strip(),
            signature="",
            meta={"phase": inv.get("phase"), "kind": inv.get("kind")},
            git_hash=None,
            indexed_at=self._now,
        ))
    return nodes
```

**Эффект на SSOT:**

| Источник | Было | Станет |
|----------|------|--------|
| INVARIANT-узлы в IndexBuilder | CLAUDE.md (regex) | `invariants.yaml` (yaml.safe_load) |
| CLAUDE.md §INV | human-edited | generated view (`sdd nav-export --invariants`) |
| DB graph.spatial_nodes (INVARIANT) | — | projection через `IndexBuilder → SpatialIndex` |

### BC-36-3: Graph Loader

```
src/sdd/spatial/graph/
  loader.py      # GraphLoader — FS-free edge transformer
```

**Контракт:**

```python
class GraphLoader:
    """
    I-GRAPH-FS-ISOLATION-1: filesystem-free.
    Все входные данные — через SpatialIndex API.
    """

    def build_graph(self, index: SpatialIndex, conn: psycopg.Connection) -> GraphBuildResult:
        """
        Pipeline:
          1. typed_reg = index.typed_registry()
          2. Для каждого FILE-узла: _scan_ast(node, typed_reg)
          3. Для каждого TERM-узла: _build_means_edges(term, typed_reg)
          4. Для каждого INVARIANT-узла: _build_invariant_edges(inv)
          5. Для каждого TASK-узла: _build_task_edges(task)
          6. I-DDD-1 check: check_ddd_coverage(typed_reg, index.iter_terms())
          7. Bulk upsert → Postgres (edge_id = семантическая дедупликация)
        """

    def _scan_ast(self, file_node: SpatialNode, index: SpatialIndex,
                  typed_reg: dict[str, set[str]]) -> list[SpatialEdge]:
        """
        Контент получает через index.read_content(file_node) — НЕ через open().
        Извлекает: imports, emits (I-GRAPH-EMITS-1), guards (ast_guards), tested_by.
        emits требует все 4 условия:
          1. handle() метод (AST)
          2. Конструкторы классов в return (AST return analysis)
          3. Класс наследует DomainEvent (typed_reg["EVENT"])
          4. Файл привязан к COMMAND (typed_reg["COMMAND"] + registry binding)
        """

    def _build_means_edges(self, term: SpatialNode, typed_reg: dict[str, set[str]]) -> list[SpatialEdge]:
        """
        term.links → means-рёбра (edge_source="glossary", priority=0.6).
        I-DDD-1: каждый link проверяется через typed_reg.
        Источник: iter_terms() — файл glossary.yaml не читается.
        """

    def _build_invariant_edges(self, inv: SpatialNode) -> list[SpatialEdge]:
        """
        inv.meta["verified_by"] → verified_by рёбра (edge_source="invariants_yaml", priority=0.4).
        inv.meta["introduced_in"] → introduced_in рёбра.
        Источник: iter_invariants() — файл invariants.yaml не читается.
        Требует: IndexBuilder._build_invariant_nodes() сохраняет verified_by/introduced_in в meta.
        """

    def _build_task_edges(self, task: SpatialNode) -> list[SpatialEdge]:
        """
        task.meta["depends_on"] → depends_on рёбра (edge_source="taskset_depends_on", priority=0.7).
        task.meta["implements"] → implements рёбра (edge_source="taskset_implements", priority=0.8).
        Источник: iter_tasks() — TaskSet файл не читается.
        Требует: IndexBuilder._build_task_nodes() сохраняет depends_on/implements в meta.
        """
```

**Дедупликация:** `edge_id = sha256(src+":"+kind+":"+dst)[:16]`. При конфликте
источников побеждает более специфичный `edge_source`.

**I-GRAPH-1:** Every edge derives from static AST analysis or explicit config
(SpatialIndex API). No heuristics. No runtime introspection. No causal inference.

**I-GRAPH-2:** `edge_source VARCHAR NOT NULL` — каждое ребро имеет детерминированный
источник. Допустимые значения: `ast_import`, `ast_emits`, `registry`, `cli_route`,
`taskset_depends_on`, `taskset_implements`, `glossary`, `ast_tested_by`, `events_py`,
`ast_guards`, `invariants_yaml`.

**I-GRAPH-3:** For every INVARIANT node, exists at least one outgoing `verified_by`
or `introduced_in` edge.

**I-GRAPH-EMITS-1:** `emits` edge требует ВСЕ четыре условия:
1. Файл содержит метод handle() (AST)
2. handle() возвращает экземпляры классов (AST return analysis)
3. Классы наследуют DomainEvent (typed_reg["EVENT"])
4. Файл привязан к COMMAND через registry.py (handler binding via typed_reg["COMMAND"])

**I-GRAPH-FS-ISOLATION-1 (final):** GraphLoader MUST NOT access filesystem directly.
All file content MUST be accessed via `SpatialIndex.read_content(node)`.
GraphLoader has no knowledge of filesystem, YAML, or `project_root`.
No carve-out: `open()` is unconditionally forbidden in `GraphLoader`.

### BC-36-4: GraphQuerier

```
src/sdd/spatial/graph/
  querier.py     # GraphQuerier — pure read interface
```

```python
class GraphQuerier:
    """Pure read interface. No DDD validation — see GraphLoader.build_graph()."""

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn  # I-DB-1: caller resolves connection via open_graph_connection()

    def get_node(self, node_id: str) -> dict | None: ...

    def search_nodes(self, query: str, kind: str | None = None,
                     limit: int = 10) -> list[dict]:
        """
        Postgres-native fuzzy search по label, summary.
        TERM: включает aliases из meta_json.
        SQL: jaro_winkler_similarity + term_boost + LIMIT.
        """

    def neighbors(self, node_id: str, hops: int = 1,
                  mode: str = "POINTER") -> dict:
        """
        BFS через WITH RECURSIVE CTE. Максимум hops=2.
        Сортировка: hop ASC, priority DESC, dst ASC (I-GRAPH-PRIORITY-1).
        """

    def get_invariant_coverage(self, invariant_id: str) -> dict:
        """INVARIANT:I-X → verified_by + introduced_in edges."""

    def get_term_links(self, term_id: str) -> list[dict]:
        """TERM:x → means-рёбра с соседями."""
```

**Примечание:** `check_ddd_coverage()` удалён из `GraphQuerier`. DDD-валидация
выполняется внутри `GraphLoader.build_graph()` при построении графа (BC-36-3).
`GraphQuerier` — чистый read-интерфейс без validation concerns.

### BC-36-4a: open_graph_connection()

```
src/sdd/infra/connections.py  # добавить (или создать если нет)
```

```python
def open_graph_connection(
    db_url: str | None = None,
) -> psycopg.Connection:
    """
    Открывает Postgres соединение для graph layer.
    После Phase 32: использует SDD_DATABASE_URL — та же БД что и EventLog.
    I-DB-1: url MUST be non-empty str.
    """
    url = db_url or os.environ.get("SDD_DATABASE_URL")
    if not url:
        raise ValueError("SDD_DATABASE_URL not set and db_url not provided (I-DB-1)")
    return psycopg.connect(url)
```

**Мотивация:** единая env var `SDD_DATABASE_URL` для EventLog (Phase 32) и graph layer
(Phase 36). Нет split-brain между отдельными `$SDD_DSN` и `$SDD_DATABASE_URL`.
Тесты передают `db_url` явно через pytest fixture `$SDD_TEST_DSN`.

### BC-36-5: TERM Integration (I-DDD-1)

**I-DDD-1 (финальная формулировка):**

```
∀ TERM.link ∈ glossary.yaml → typed_registry.has(link.namespace, link.id)

Где typed_registry = index.typed_registry() — чистая проекция SpatialIndex.
Broken typed reference = hard violation (exit 1 в nav-rebuild).
COMMAND без TERM entry = valid (TERM defines reachability, not existence).
EVENT/TASK: observational coverage report, no enforcement.
```

**`nav-rebuild --backend postgres`** выводит:
- ERROR (exit 1) при `violations != []`
- WARNING при `uncovered_commands != []`

### BC-36-6: sdd resolve — Unified DDD Entrypoint

```
src/sdd/spatial/commands/
  nav_resolve.py    # sdd resolve <query> [--limit N]
```

**I-DDD-2:** `sdd resolve` MUST always return `must_not_guess: true` on not_found.
Response MUST always include `neighbors` (может быть пустым `[]`).

Output format — без изменений относительно предыдущей версии спека.

### BC-36-7: nav-neighbors, nav-invariant

```
src/sdd/spatial/commands/
  nav_neighbors.py    # sdd nav-neighbors <id> [--hops N] [--mode POINTER|SUMMARY]
  nav_invariant.py    # sdd nav-invariant <I-NNN>
```

Output formats — без изменений относительно предыдущей версии спека.

### BC-36-8: Tests

```
tests/unit/spatial/
  test_index_api.py   # iter_files/terms/invariants/tasks; typed_registry(); I-INDEX-FILE-COVERAGE-1
tests/unit/spatial/graph/
  test_schema.py      # ensure_graph_schema(); идемпотентность
  test_loader.py      # I-GRAPH-FS-ISOLATION-1: GraphLoader не делает прямых fs-вызовов
                      # I-GRAPH-1, I-GRAPH-2, I-GRAPH-3, I-GRAPH-EMITS-1
                      # iter_files → means-рёбра; typed_registry checks (I-DDD-1)
                      # iter_invariants → verified_by рёбра (I-GRAPH-3)
  test_querier.py     # get_node/search_nodes/neighbors; I-GRAPH-PRIORITY-1

tests/unit/commands/
  test_nav_resolve.py   # TERM hit; not_found → must_not_guess (I-DDD-2)
  test_nav_neighbors.py # hop sort; hops=2 BFS
  test_nav_invariant.py # exit 0 с verified_by; exit 1 если не найден

tests/integration/
  test_nav_postgres.py  # nav-rebuild --backend postgres; SQL checks I-GRAPH-2, I-GRAPH-3, I-DDD-1
```

**Ключевой тест FS-изоляции:**

```python
def test_graph_loader_is_fs_free():
    """I-GRAPH-FS-ISOLATION-1 (final): GraphLoader никогда не вызывает open().
    FILE-узлы включены — read_content() возвращает строки через FakeIndex.
    """
    fake_content = "import ast\nclass Foo: pass\n"

    class FakeIndex:
        def iter_files(self): return [SpatialNode(node_id="FILE:foo", kind="FILE", ...)]
        def iter_terms(self): return []
        def iter_invariants(self): return []
        def iter_tasks(self): return []
        def typed_registry(self): return {}
        def read_content(self, node): return fake_content

    loader = GraphLoader()
    with patch("builtins.open", side_effect=AssertionError("unexpected fs access")):
        result = loader.build_graph(FakeIndex(), mock_conn)
    # Если GraphLoader где-то вызовет open() — тест падает немедленно.
```

**Test DB:** Postgres (не DuckDB). Тесты используют Postgres в Docker или `$SDD_TEST_DSN`.

### BC-36-9: Backend Registration

**`src/sdd/spatial/commands/nav_rebuild.py`** — обновлённый pipeline для
`--backend postgres`:

```python
# nav-rebuild --backend postgres
conn = open_graph_connection()              # SDD_DATABASE_URL → psycopg.Connection
index = IndexBuilder(project_root).build()  # шаг 1: единственный fs-reader
result = GraphLoader().build_graph(index, conn)  # шаг 2: FS-free
# persist → Postgres (шаг 3)

# nav-rebuild --backend json
index = IndexBuilder(project_root).build()
save_index(index, json_path)

# nav-rebuild --backend both
conn = open_graph_connection()
index = IndexBuilder(project_root).build()  # один проход по FS
save_index(index, json_path)               # JSON
GraphLoader().build_graph(index, conn)     # Postgres
```

**`src/sdd/cli.py`** — добавить: `nav-neighbors`, `nav-invariant`, `resolve`.

### BC-36-10: invariants.yaml + sdd nav-export

```
.sdd/config/invariants.yaml     # machine-readable SSOT инвариантов
src/sdd/spatial/commands/
  nav_export.py                  # sdd nav-export [--invariants] [--terms]
```

**`invariants.yaml`** — схема без изменений относительно предыдущей версии спека.
Добавить поля `verified_by` и `introduced_in` в meta при построении INVARIANT-узлов
в `IndexBuilder._build_invariant_nodes()`:

```python
meta={
    "phase": inv.get("phase"),
    "kind": inv.get("kind"),
    "verified_by": inv.get("verified_by", []),    # для _build_invariant_edges()
    "introduced_in": inv.get("introduced_in"),    # для _build_invariant_edges()
}
```

**I-INV-EXPORT-1:** После любого изменения `invariants.yaml` LLM MUST вызвать
`sdd nav-export --invariants` и зафиксировать обновлённый CLAUDE.md §INV.

---

## 4. Domain Events

Phase 36 не эмитирует domain events в производственный EventLog.
`GraphLoader.build_graph()` — read-only по отношению к SDD-ядру.

---

## 5. Invariants

### New Invariants — Phase 36

| ID | Statement | Phase | Verification |
|----|-----------|-------|-------------|
| I-SI-SNAPSHOT-1 | `SpatialIndex` = иммутабельный snapshot (frozen=True). Инвалидация — исключительно внешняя (staleness.py / nav-rebuild). Внутреннего cache, lazy-load, file I/O внутри `SpatialIndex` — нет. | 33 | `test_index_api.py` (frozen check) |
| I-INDEX-FILE-COVERAGE-1 | All Python files in `src/sdd/` relevant for graph construction MUST be represented as FILE nodes in SpatialIndex | 33 | `test_index_api.py` |
| I-GRAPH-FS-ISOLATION-1 | GraphLoader MUST NOT access filesystem directly. All file content via `SpatialIndex.read_content(node)`. No carve-out. | 33 | `test_loader.py` (patch builtins.open + FakeIndex with FILE nodes) |
| I-GRAPH-1 | Every edge derives from static AST or explicit config (SpatialIndex API); no heuristics, no causal inference | 33 | `test_loader.py` |
| I-GRAPH-2 | `edge_source VARCHAR NOT NULL` — детерминированный источник каждого ребра | 33 | SQL check + `test_loader.py` |
| I-GRAPH-3 | Every INVARIANT node has ≥1 outgoing `verified_by` or `introduced_in` edge | 33 | SQL check + `test_loader.py` |
| I-GRAPH-EMITS-1 | `emits` edge requires all 4 conditions: handle() + AST return + DomainEvent registry + handler binding | 33 | `test_loader.py` |
| I-GRAPH-PRIORITY-1 | `nav-neighbors` sorted by `hop ASC, priority DESC, dst ASC` | 33 | `test_querier.py`, `test_nav_neighbors.py` |
| I-DDD-1 | ∀ TERM.link → typed_registry.has(namespace, id); broken typed ref = hard violation | 33 | `GraphLoader.build_graph()` + `test_nav_postgres.py` |
| I-DDD-2 | `sdd resolve` MUST return `must_not_guess: true` on not_found | 33 | `test_nav_resolve.py` |
| I-TERM-REGISTRY-SOURCE-OF-TRUTH-1 | registry.py = SSOT для COMMAND; glossary.yaml = semantic projection only | 33 | `test_loader.py` |
| I-INV-EXPORT-1 | После изменения invariants.yaml LLM MUST вызвать `sdd nav-export --invariants` | 33 | protocol (CI diff check) |

### Preserved Invariants (Phase 18)

I-NAV-1..3, I-CONTEXT-1, I-SI-1..4, I-DDD-0 — без изменений.

---

## 6. Pre/Post Conditions

### M0 — Postgres Graph Schema + invariants.yaml

**Pre:**
- Phase 18 COMPLETE (spatial_index.json актуален)
- Phase 32 COMPLETE (PostgresMigration: `$SDD_DATABASE_URL` установлен, схема `p_sdd` существует)
- `.sdd/config/` директория существует

**Post:**
- `src/sdd/spatial/graph/schema.py` создан
- `ensure_graph_schema(conn)` идемпотентна на Postgres test DB
- `.sdd/config/invariants.yaml` создан с Phase 18 + Phase 36 инвариантами
- `src/sdd/infra/connections.py` содержит `open_graph_connection()`
- `tests/unit/spatial/graph/test_schema.py` PASS

### M1 — SpatialIndex API Extension + IndexBuilder Migration

**Pre:** M0 COMPLETE, Phase 18 M1 COMPLETE

**Post:**
- `SpatialIndex.iter_files/terms/invariants/tasks()` добавлены
- `SpatialIndex.typed_registry()` добавлен (чистая проекция, нет file I/O)
- `SpatialIndex.content_map: dict[str, str]` добавлен; `read_content(node)` = dict lookup (нет I/O)
- `IndexBuilder.build()` выполняет весь file I/O однократно; SpatialIndex иммутабелен после build (I-SI-SNAPSHOT-1)
- `IndexBuilder._build_invariant_nodes()` читает `invariants.yaml` (не CLAUDE.md)
- `IndexBuilder._build_invariant_nodes()` сохраняет `verified_by`/`introduced_in` в `meta`
- `IndexBuilder._build_task_nodes()` сохраняет `depends_on`/`implements` в `meta`
- I-INDEX-FILE-COVERAGE-1 выполнен
- `tests/unit/spatial/test_index_api.py` PASS

### M2 — Graph Loader (FS-free)

**Pre:** M1 COMPLETE

**Post:**
- `loader.py` создан
- `build_graph(index: SpatialIndex, conn)` — без `project_root`
- `_scan_ast()` принимает `SpatialNode` + `index: SpatialIndex`; контент через `index.read_content(node)`
- `_build_means_edges()` использует `iter_terms()` (не читает glossary.yaml)
- `_build_invariant_edges()` использует `iter_invariants()` (не читает invariants.yaml)
- `_build_task_edges()` использует `iter_tasks()` (не читает TaskSet)
- I-GRAPH-FS-ISOLATION-1: `test_graph_loader_is_fs_free` PASS
- I-GRAPH-1, I-GRAPH-2, I-GRAPH-3, I-GRAPH-EMITS-1: `test_loader.py` PASS

### M3 — GraphQuerier (psycopg + WITH RECURSIVE)

**Pre:** M0 COMPLETE

**Post:**
- `querier.py` создан
- `GraphQuerier(conn: psycopg.Connection)` — принимает соединение, не DSN строку
- `neighbors()` использует `WITH RECURSIVE` CTE
- Сортировка: `hop ASC, priority DESC, dst ASC`
- `check_ddd_coverage()` ОТСУТСТВУЕТ в GraphQuerier (перенесён в GraphLoader)
- `tests/unit/spatial/graph/test_querier.py` PASS

### M4 — TERM Integration + I-DDD-1

**Pre:** M2, M3 COMPLETE

**Post:**
- `nav-rebuild --backend postgres` создаёт `means`-рёбра из `iter_terms()`
- `GraphLoader.build_graph()` выполняет I-DDD-1 check: `violations == []`
- `uncovered_commands` выводится как warning
- I-DDD-1 верифицирован SQL-проверкой в integration test

### M5 — sdd resolve

**Pre:** M3, M4 COMPLETE

**Post:**
- `nav_resolve.py` создан
- TERM-hit: возвращает `{resolved_via, term, node, neighbors}`
- not_found: exit 1, `must_not_guess: true`
- I-DDD-2 PASS

### M6 — nav-neighbors, nav-invariant

**Pre:** M3 COMPLETE

**Post:**
- `nav_neighbors.py`, `nav_invariant.py` созданы
- Hop-sort верифицирован
- `cli.py` зарегистрированы 3 новые команды

### M7 — sdd nav-export + I-INV-EXPORT-1

**Pre:** M0 COMPLETE (invariants.yaml существует)

**Post:**
- `nav_export.py` создан
- `sdd nav-export --invariants` генерирует CLAUDE.md §INV из `invariants.yaml`
- Детерминированный вывод

### M8 — Integration

**Pre:** M0..M7 COMPLETE

**Post:**
- `SELECT count(*) FROM graph.spatial_nodes` > 100
- I-GRAPH-2: no edges with empty `edge_source`
- I-GRAPH-3: все INVARIANT-узлы имеют ≥1 исходящее ребро
- I-DDD-1: `violations == []`
- `sdd resolve "activate phase"` → `TERM:activate_phase`
- `sdd resolve "unknown xyz"` exit 1, `must_not_guess: true`
- Все тесты Phase 18 по-прежнему проходят
- `tests/integration/test_nav_postgres.py` PASS

---

## 7. Use Cases

### UC-33-1: nav-rebuild запускает pipeline

**Actor:** разработчик / LLM
**Trigger:** `sdd nav-rebuild --backend postgres`
**Steps:**
1. `open_graph_connection()` — resolves `SDD_DATABASE_URL` → psycopg.Connection
2. `IndexBuilder(root).build()` — единственный fs-проход, строит все узлы
3. `SpatialIndex` готов с полным API
4. `GraphLoader().build_graph(index, conn)` — FS-free, строит рёбра из API
5. Postgres upsert: nodes + edges
6. I-DDD-1 check внутри `build_graph`
**Post:** граф актуален; pipeline выполнен за один fs-проход

### UC-33-2: Agent Starts Navigation via sdd resolve

**Actor:** LLM-агент
**Steps:**
1. `sdd resolve "complete task"` → TERM:complete_task → definition + neighbors
2. `sdd nav-get COMMAND:complete --mode SIGNATURE` → детали
3. `sdd nav-neighbors COMMAND:complete --hops 1` → emits: TaskImplementedEvent
**Post:** агент построил контекст за 3 детерминированных шага

### UC-33-3: DDD Coverage Check

**Actor:** разработчик
**Trigger:** `sdd nav-rebuild --backend postgres`
**Post:** I-DDD-1 проверяет целостность ссылок, не полноту покрытия

### UC-33-4: Invariant Coverage Navigation

**Actor:** LLM-агент
**Steps:**
1. `sdd nav-invariant I-SI-1` → `verified_by: [COMMAND:nav-rebuild]`
**Post:** I-GRAPH-3 обеспечивает трассируемость каждого инварианта

---

## 8. Verification

```bash
# Phase 18 тесты всё ещё PASS
pytest tests/unit/spatial/ tests/integration/test_nav_rebuild_integration.py -q

# SpatialIndex API
pytest tests/unit/spatial/test_index_api.py -q

# Phase 36 unit
pytest tests/unit/spatial/graph/ tests/unit/commands/test_nav_*.py -q

# FS-isolation
pytest tests/unit/spatial/graph/test_loader.py -k "fs_free" -q

# Phase 36 integration
sdd nav-rebuild --backend both
pytest tests/integration/test_nav_postgres.py -q

# DDD layer
sdd resolve 'activate phase'
sdd resolve 'unknown xyz'        # exit 1
sdd nav-neighbors COMMAND:complete --hops 2
sdd nav-invariant I-SI-1

# nav-export
sdd nav-export --invariants
```

### Test Suite

| # | File | Invariants |
|---|------|------------|
| 1 | `tests/unit/spatial/test_index_api.py` | I-SI-SNAPSHOT-1, I-INDEX-FILE-COVERAGE-1, typed_registry(), read_content() |
| 2 | `tests/unit/spatial/graph/test_schema.py` | idempotency, Postgres schema |
| 3 | `tests/unit/spatial/graph/test_loader.py` | I-GRAPH-FS-ISOLATION-1, I-GRAPH-1..3, I-GRAPH-EMITS-1 |
| 4 | `tests/unit/spatial/graph/test_querier.py` | I-GRAPH-PRIORITY-1, WITH RECURSIVE BFS |
| 5 | `tests/unit/commands/test_nav_resolve.py` | I-DDD-2 |
| 6 | `tests/unit/commands/test_nav_neighbors.py` | hop sort, hops=2 |
| 7 | `tests/unit/commands/test_nav_invariant.py` | I-GRAPH-3 |
| 8 | `tests/integration/test_nav_postgres.py` | I-GRAPH-2, I-GRAPH-3, I-DDD-1 |

### Stabilization Criteria

1. `SELECT count(*) FROM graph.spatial_nodes` > 100
2. I-GRAPH-2: no edges with `edge_source IS NULL OR edge_source = ''`
3. I-GRAPH-3: each INVARIANT node has ≥1 outgoing edge
4. I-DDD-1: `violations == []`
5. `sdd nav-invariant I-SI-1` exit 0, непустой `verified_by`
6. `sdd nav-neighbors COMMAND:complete --hops 2` ≥3 соседей, sorted hop ASC
7. `sdd resolve "activate phase"` exit 0, `TERM:activate_phase`
8. `sdd resolve "unknown xyz"` exit 1, `must_not_guess: true`
9. Phase 18 тесты PASS
10. `sdd nav-export --invariants` детерминированно воспроизводит CLAUDE.md §INV

---

## 9. Out of Scope

| Item | Owner |
|------|-------|
| `observed_in` edges, eventlog-projector, nav-drift | Phase 34+ |
| Causal graph | Запрещено навсегда (I-GRAPH-1) |
| Temporal navigation | Phase 34+ |
| TaskCheckpoint events | Phase 34+ |
| NORM-NAV-001 в norm_catalog | Phase 34+ |
| ML ranking, embedding, shortest path | Никогда |
| Graph visualization, Apache AGE | Никогда |

---

## 10. Dependencies & Impact

### Upstream (Phase 36 requires)

| Dependency | Required from |
|-----------|---------------|
| `spatial_index.json` актуален | Phase 18 COMPLETE |
| `nodes.py` с `TermNode` и `SpatialEdge` | Phase 18 M1 |
| `glossary.yaml` с typed links | Phase 18 (расширяется в Phase 36) |
| Postgres DB; `$SDD_DATABASE_URL` env var | Phase 32 COMPLETE |
| `p_sdd` схема создана | Phase 32 `sdd init-project` |

### Downstream (Phase 34+ requires from Phase 36)

| What | Where used |
|------|-----------|
| `SpatialIndex` iter_* API | Phase 34+ temporal queries |
| `graph.spatial_nodes/edges` schema | Phase 34+ temporal extensions |
| `invariants.yaml` format | Phase 34+ new invariants |
| `GraphQuerier` interface | Phase 34+ temporal extensions |
| `nav-export` infrastructure | Phase 34+ additions |

### Impact на Spec_v30 (DocFixes)

BC-30-5 упрощается: `dev-cycle-map.md` содержит только ссылки `→ см. CLAUDE.md §INV`.
CLAUDE.md §INV = generated view из `invariants.yaml` (Phase 36).
