# Plan_v19 — Phase 19: Graph Navigation (GN)

Status: DRAFT
Spec: specs/Spec_v19_v1_GraphNavigation.md

---

## Milestones

### M0: Postgres Graph Schema + invariants.yaml

```text
Spec:       §3 BC-19-0 · §6 M0 · §10 Dependencies
BCs:        BC-19-0, BC-19-10 (invariants.yaml)
Invariants: I-DB-1 (explicit DSN), I-INV-EXPORT-1
Depends:    Phase 18 COMPLETE; $SDD_DSN установлен
Risks:      Если Postgres недоступен — всё Postgres-зависимое заблокировано.
            ensure_graph_schema() должна быть идемпотентной (CREATE IF NOT EXISTS).
```

**Deliverables:**
- `src/sdd/spatial/graph/__init__.py`
- `src/sdd/spatial/graph/schema.py` — `ensure_graph_schema(conn: psycopg.Connection)`
- `.sdd/config/invariants.yaml` — machine-readable SSOT инвариантов Phase 18 + Phase 19
- `tests/unit/spatial/graph/test_schema.py` — idempotency test на Postgres test DB

---

### M1: SpatialIndex API Extension + IndexBuilder Migration

```text
Spec:       §3 BC-19-1, BC-19-2 · §6 M1
BCs:        BC-19-1, BC-19-2
Invariants: I-SI-SNAPSHOT-1, I-INDEX-FILE-COVERAGE-1
Depends:    M0 COMPLETE; Phase 18 M1 COMPLETE (SpatialIndex, nodes.py существуют)
Risks:      Расширение SpatialIndex API не должно ломать Phase 18 тесты.
            content_map заполняется в IndexBuilder.build() за один FS-проход —
            нарушение этого порядка даст lazy-load в SpatialIndex (нарушает I-SI-SNAPSHOT-1).
```

**Deliverables:**
- `src/sdd/spatial/nodes.py` — `SpatialEdge` обновлён: `edge_id`, `edge_source`, `priority` как first-class поля
- `src/sdd/spatial/index.py` — `SpatialIndex`: `content_map`, `iter_files/terms/invariants/tasks()`, `typed_registry()`, `read_content()`; `frozen=True`
- `src/sdd/spatial/index.py` — `IndexBuilder._build_invariant_nodes()` читает `invariants.yaml` (не CLAUDE.md)
- `src/sdd/spatial/index.py` — `IndexBuilder._build_invariant_nodes()` сохраняет `verified_by`/`introduced_in` в `meta`
- `src/sdd/spatial/index.py` — `IndexBuilder._build_task_nodes()` сохраняет `depends_on`/`implements` в `meta`
- `tests/unit/spatial/test_index_api.py` PASS

---

### M2: Graph Loader (FS-free)

```text
Spec:       §3 BC-19-3 · §6 M2
BCs:        BC-19-3
Invariants: I-GRAPH-FS-ISOLATION-1, I-GRAPH-1, I-GRAPH-2, I-GRAPH-3, I-GRAPH-EMITS-1
Depends:    M1 COMPLETE
Risks:      Любой прямой вызов open() в GraphLoader — нарушение I-GRAPH-FS-ISOLATION-1.
            emits-рёбра требуют строго 4 условия (I-GRAPH-EMITS-1); ложные срабатывания
            при неполной проверке handler binding.
            edge_id дедупликация (sha256[:16]) — не должна порождать коллизии в реальном графе.
```

**Deliverables:**
- `src/sdd/spatial/graph/loader.py` — `GraphLoader`: `build_graph()`, `_scan_ast()`, `_build_means_edges()`, `_build_invariant_edges()`, `_build_task_edges()`
- `build_graph()` не принимает `project_root`; весь FS-доступ через `SpatialIndex.read_content()`
- `test_graph_loader_is_fs_free` PASS (patch builtins.open + FakeIndex с FILE-узлами)
- `tests/unit/spatial/graph/test_loader.py` PASS (все 4 условия emits, I-GRAPH-2, I-GRAPH-3)

---

### M3: GraphQuerier (psycopg + WITH RECURSIVE)

```text
Spec:       §3 BC-19-4 · §6 M3
BCs:        BC-19-4
Invariants: I-GRAPH-PRIORITY-1, I-DB-1
Depends:    M0 COMPLETE (схема создана)
Risks:      WITH RECURSIVE CTE может порождать циклы если граф не DAG — ограничить hops≤2.
            check_ddd_coverage() ДОЛЖЕН ОТСУТСТВОВАТЬ в GraphQuerier (перенесён в GraphLoader).
            Сортировка hop ASC, priority DESC, dst ASC — строгое требование I-GRAPH-PRIORITY-1.
```

**Deliverables:**
- `src/sdd/spatial/graph/querier.py` — `GraphQuerier`: `get_node()`, `search_nodes()`, `neighbors()`, `get_invariant_coverage()`, `get_term_links()`
- `neighbors()` использует `WITH RECURSIVE` CTE, hops ≤ 2
- `check_ddd_coverage()` отсутствует в `GraphQuerier`
- `tests/unit/spatial/graph/test_querier.py` PASS

---

### M4: TERM Integration + I-DDD-1

```text
Spec:       §3 BC-19-5 · §6 M4 · §2 Edge Priority
BCs:        BC-19-5
Invariants: I-DDD-1, I-TERM-REGISTRY-SOURCE-OF-TRUTH-1
Depends:    M2 COMPLETE (GraphLoader), M3 COMPLETE (GraphQuerier)
Risks:      I-DDD-1 = hard violation (exit 1) при broken typed reference.
            COMMAND без TERM = valid (не ошибка).
            Источник TERM-ссылок — iter_terms() из SpatialIndex; glossary.yaml не читается напрямую.
```

**Deliverables:**
- `GraphLoader.build_graph()` строит `means`-рёбра из `iter_terms()` (edge_source="glossary", priority=0.6)
- `GraphLoader.build_graph()` выполняет I-DDD-1 check: broken ref → exit 1; uncovered_commands → WARNING
- `nav-rebuild --backend postgres` pipeline работает end-to-end
- Integration test подтверждает I-DDD-1 SQL-проверкой

---

### M5: sdd resolve — Unified DDD Entrypoint

```text
Spec:       §3 BC-19-6 · §6 M5 · §7 UC-19-2
BCs:        BC-19-6
Invariants: I-DDD-2
Depends:    M3, M4 COMPLETE
Risks:      not_found MUST вернуть exit 1 с must_not_guess: true — нельзя возвращать
            ближайших кандидатов молча.
            Response ВСЕГДА содержит поле neighbors (может быть []).
```

**Deliverables:**
- `src/sdd/spatial/commands/nav_resolve.py` — `sdd resolve <query> [--limit N]`
- TERM-hit: `{resolved_via, term, node, neighbors}`
- not_found: exit 1, `{must_not_guess: true}`
- `cli.py` зарегистрирован `resolve`
- `tests/unit/commands/test_nav_resolve.py` PASS (I-DDD-2)

---

### M6: nav-neighbors + nav-invariant

```text
Spec:       §3 BC-19-7 · §6 M6
BCs:        BC-19-7
Invariants: I-GRAPH-PRIORITY-1, I-GRAPH-3
Depends:    M3 COMPLETE
Risks:      hop-sort верификация — приоритет DESC внутри одного hop.
            nav-invariant exit 1 если INVARIANT-узел не найден.
```

**Deliverables:**
- `src/sdd/spatial/commands/nav_neighbors.py` — `sdd nav-neighbors <id> [--hops N] [--mode POINTER|SUMMARY]`
- `src/sdd/spatial/commands/nav_invariant.py` — `sdd nav-invariant <I-NNN>`
- `cli.py` зарегистрированы `nav-neighbors`, `nav-invariant`
- `tests/unit/commands/test_nav_neighbors.py` PASS
- `tests/unit/commands/test_nav_invariant.py` PASS

---

### M7: sdd nav-export + I-INV-EXPORT-1

```text
Spec:       §3 BC-19-10 · §6 M7
BCs:        BC-19-10
Invariants: I-INV-EXPORT-1
Depends:    M0 COMPLETE (invariants.yaml существует)
Risks:      Вывод должен быть детерминированным — один и тот же invariants.yaml
            всегда порождает идентичный CLAUDE.md §INV.
            После любого изменения invariants.yaml LLM ДОЛЖЕН вызвать nav-export --invariants.
```

**Deliverables:**
- `src/sdd/spatial/commands/nav_export.py` — `sdd nav-export [--invariants] [--terms]`
- `cli.py` зарегистрирован `nav-export`
- `sdd nav-export --invariants` генерирует детерминированный CLAUDE.md §INV из invariants.yaml

---

### M8: Integration — End-to-End Verification

```text
Spec:       §6 M8 · §8 Verification · §8 Stabilization Criteria
BCs:        BC-19-0..BC-19-10 (все)
Invariants: I-GRAPH-2, I-GRAPH-3, I-DDD-1, I-DDD-2, I-INV-EXPORT-1
Depends:    M0..M7 COMPLETE
Risks:      Phase 18 тесты должны оставаться PASS (обратная совместимость SpatialIndex API).
            Postgres integration требует $SDD_DSN; тесты используют Docker или env var.
            10 Stabilization Criteria (§8) — все должны выполняться.
```

**Deliverables:**
- `tests/integration/test_nav_postgres.py` PASS
- `SELECT count(*) FROM graph.spatial_nodes` > 100
- I-GRAPH-2: нет рёбер с пустым `edge_source`
- I-GRAPH-3: все INVARIANT-узлы имеют ≥1 исходящее ребро
- I-DDD-1: `violations == []`
- Phase 18 тесты по-прежнему PASS
- `sdd resolve "activate phase"` exit 0 → `TERM:activate_phase`
- `sdd resolve "unknown xyz"` exit 1, `must_not_guess: true`
- `sdd nav-neighbors COMMAND:complete --hops 2` ≥3 соседей, sorted hop ASC
- `sdd nav-export --invariants` детерминированно воспроизводит CLAUDE.md §INV

---

## Risk Notes

- R-1: **Postgres dependency** — $SDD_DSN должен быть установлен до запуска M0. В CI
  нужен Docker Postgres или dedicated test DSN. Без Postgres всё Postgres-зависимое (M0..M8)
  заблокировано. Mitigation: добавить `SDD_DSN` в `.env.example`; CI yml поднимает postgres service.

- R-2: **FS-изоляция (I-GRAPH-FS-ISOLATION-1)** — тонкая граница: `open()` в GraphLoader
  нарушает инвариант даже если технически работает. Mitigation: `test_graph_loader_is_fs_free`
  патчит `builtins.open` → AssertionError; тест запускается в M2 до Postgres.

- R-3: **emits-рёбра ложные срабатывания (I-GRAPH-EMITS-1)** — требует строго 4 условия.
  Handler binding (условие 4) проверяется через `typed_reg["COMMAND"]` из `typed_registry()`,
  не через прямое чтение `registry.py`. Mitigation: тесты покрывают все 4 условия отдельно.

- R-4: **Phase 18 регрессия** — `SpatialIndex` расширяется новыми полями (`content_map`,
  `iter_*`, `typed_registry()`). Существующие `nav-get --backend json` и Phase 18 тесты
  должны остаться PASS. Mitigation: M1 запускает Phase 18 тесты перед завершением.

- R-5: **edge_id коллизии** — sha256[:16] теоретически возможны, но не ожидаются при
  реальном размере графа (< 10k рёбер). Mitigation: при upsert-конфликте побеждает более
  специфичный `edge_source`; логировать коллизии для диагностики.
