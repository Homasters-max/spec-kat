# Plan_v56 — Phase 56: Graph-First + Architecture Context

Status: DRAFT
Spec: specs/Spec_v56_GraphFirst.md

---

## Logical Context

type: none
rationale: "standard phase — extends Phase 55 Graph-Guided Implement with audit infrastructure, enforcement, and architectural context model"

---

## Milestones

### M0: Foundation — Edge Types + Paths + Config Skeleton

```text
Spec:       §4 — Edge Kinds, добавляемые в Phase 56
BCs:        BC-56-BC, BC-56-BC-2, BC-56-LAYER (I-GRAPH-PRIORITY-1 prerequisite)
Invariants: I-GRAPH-PRIORITY-1 (implied: all new extractors require edge kinds registered first)
Depends:    — (первый)
Risks:      CrossBCEdgeExtractor или LayerEdgeExtractor, запущенные до регистрации
            edge kinds → KeyError / undefined behavior в builder. Решение: M0 всегда первый.
```

Deliverables:
- `src/sdd/graph/types.py` — добавить в `EDGE_KIND_PRIORITY`:
  `"cross_bc_dependency": 0.63`, `"calls": 0.58`, `"belongs_to": 0.55`, `"in_layer": 0.35`
- `src/sdd/graph/types.py` — добавить в `ALLOWED_META_KEYS`:
  `"path_prefix"`, `"description"`, `"path_patterns"`
- `src/sdd/infra/paths.py` — добавить `graph_calls_file() → Path`
  (`.sdd/runtime/graph_calls.jsonl`, аналогично `audit_log_file()`)
- `.sdd/config/sdd_config.yaml` — добавить секции `bounded_contexts:` и `layers:` (из Spec §2)

---

### M1: GraphCallLog — Audit Infrastructure (BC-56-A1)

```text
Spec:       §2 BC-56-A1 — GraphCallLog отдельный модуль
BCs:        BC-56-A1
Invariants: I-GRAPH-CALL-LOG-1, I-AUDIT-SESSION-1
Depends:    M0 (graph_calls_file())
Risks:      Запись в audit_log.jsonl вместо graph_calls.jsonl → I-GRAPH-CALL-LOG-1 violation.
            Решение: graph_call_log.py использует только graph_calls_file(), не audit_log_file().
```

Deliverables:
- `src/sdd/infra/graph_call_log.py` — новый модуль:
  - `GraphCallEntry` (frozen dataclass: command, args, session_id, ts, result_size)
  - `log_graph_call(entry: GraphCallEntry) → None` (atomic append)
  - `query_graph_calls(session_id: str | None) → list[GraphCallEntry]` (filter + skip malformed)
- `src/sdd/graph_navigation/cli/explain.py` — вызов `log_graph_call()` после `engine.query()`
- `src/sdd/graph_navigation/cli/trace.py` — вызов `log_graph_call()` после `engine.query()`
- `src/sdd/graph_navigation/cli/resolve.py` — вызов `log_graph_call()` после `engine.query()`
- `tests/unit/infra/test_graph_call_log.py` — тесты:
  - write → read roundtrip
  - session_id filter
  - absent file → empty list (no error)
  - malformed line → skipped (I-AUDIT-SESSION-1)

---

### M2: sdd record-metric Command (BC-56-A2)

```text
Spec:       §2 BC-56-A2 — sdd record-metric via REGISTRY
BCs:        BC-56-A2
Invariants: I-2 (all write commands via REGISTRY)
Depends:    — (независим от M0-M1)
Risks:      MetricRecorded не совместим с DomainEvent base → ошибка при replay.
            Решение: наследует DomainEvent, поля additive-only (EV-2).
```

Deliverables:
- `src/sdd/core/events.py` — добавить `MetricRecorded(DomainEvent)`:
  `metric_key: str`, `value: float`, `phase_id: int`, `task_id: str`, `context: str`
- `src/sdd/commands/record_metric.py` — новый handler:
  - REGISTRY entry: `record-metric`
  - flags: `--key`, `--value`, `--phase`, `--task`, `[--context]`
- `src/sdd/commands/registry.py` — зарегистрировать `record-metric`
- `tests/unit/commands/test_record_metric.py` — тест: emit MetricRecorded, queryable через EventLog

---

### M3: Graph Guard + Graph Stats (BC-56-G1, BC-56-G2)

```text
Spec:       §2 BC-56-G1, BC-56-G2
BCs:        BC-56-G1, BC-56-G2
Invariants: I-GRAPH-GUARD-1
Depends:    M1 (graph-guard использует query_graph_calls())
Risks:      graph-guard парсит JSONL напрямую вместо typed API → нарушение locality.
            Решение: только через query_graph_calls() (никакого inline parsing).
            graph-guard блокирует complete при наличии graph вызовов → I-GRAPH-GUARD-1 false positive.
            Решение: тест с реальным graph_calls.jsonl (интеграционный).
```

Deliverables:
- `src/sdd/graph_navigation/cli/graph_guard.py` — `sdd graph-guard check`:
  - `--task T-NNN [--session-id <id>]`
  - exit 0: `len(query_graph_calls(session_id)) >= 1`
  - exit 1: JSON stderr с `I-GRAPH-GUARD-1`
  - read-only (не через REGISTRY write pipeline)
- `src/sdd/graph_navigation/cli/graph_stats.py` — `sdd graph-stats`:
  - `[--edge-type <type>] [--node-type <type>] [--format json|text]`
  - read-only (не через REGISTRY)
- `src/sdd/cli.py` — зарегистрировать `graph-guard` и `graph-stats` subcommands
- `.sdd/docs/sessions/implement.md` — добавить STEP 8 перед `sdd complete`:
  ```bash
  sdd graph-guard check --task T-NNN   # exit 1 → STOP
  sdd complete T-NNN
  ```
- `.sdd/docs/ref/tool-reference.md` — добавить `sdd graph-guard check`, `sdd graph-stats`
- `tests/integration/test_graph_guard.py` — integration test (Step 56-C из Spec §11)

---

### M4: TaskNavigationSpec v2 + Score Normalization (BC-56-S1, BC-56-S2)

```text
Spec:       §2 BC-56-S1, BC-56-S2; §4 TaskNavigationSpec v2, Candidate
BCs:        BC-56-S1, BC-56-S2
Invariants: I-DECOMPOSE-RESOLVE-3
Depends:    — (независим)
Risks:      Phase 55 TaskSets с resolve_keywords перестают парситься → регрессия.
            Решение: anchor_nodes — optional field с default=(), resolve_keywords остаётся.
            score_normalized нарушает backward compat если Candidate — frozen dataclass.
            Решение: добавить поле с default (EV-2 аналог для типов).
```

Deliverables:
- `src/sdd/tasks/navigation.py` — расширить `TaskNavigationSpec`:
  - добавить `anchor_nodes: tuple[str, ...] = ()`
  - добавить `allowed_traversal: tuple[str, ...] = ()`
  - добавить `is_anchor_mode() → bool`
  - `AnchorNode` dataclass
- `src/sdd/domain/tasks/parser.py` — поддержка парсинга `anchor_nodes:` секции
- `src/sdd/context_kernel/` — `sdd resolve` Candidate: добавить `score_normalized: float`
  - вычисление: `score / (score + 1)`
- `tests/unit/tasks/test_navigation.py` (или существующий) — тесты:
  - TaskSet с anchor_nodes → is_anchor_mode() = True
  - TaskSet с resolve_keywords → is_anchor_mode() = False (backward compat)
  - score_normalized ∈ (0, 1) для разных BM25 scores

---

### M5: BOUNDED_CONTEXT + CrossBC Edges (BC-56-BC, BC-56-BC-2)

```text
Spec:       §2 BC-56-BC, BC-56-BC-2
BCs:        BC-56-BC, BC-56-BC-2
Invariants: I-BC-DETERMINISTIC-1, I-BC-CONSISTENCY-1, I-BC-RESOLVER-1
Depends:    M0 (belongs_to + cross_bc_dependency в EDGE_KIND_PRIORITY)
Risks:      CrossBCEdgeExtractor дублирует классификационную логику из BoundedContextEdgeExtractor
            → расхождения при изменении правил (I-BC-RESOLVER-1 violation).
            Решение: единый BCResolver в bc_resolver.py; оба экстрактора используют его.
            Порядок регистрации: CrossBCEdgeExtractor запущен ДО BoundedContextEdgeExtractor
            → BCResolver не видит belongs_to edges при вычислении cross-BC.
            Решение: регистрация в IndexBuilder: BoundedContextEdgeExtractor первым.
            FILE вне classification rules → не получает belongs_to edge (silent skip).
            Решение: I-BC-DETERMINISTIC-1 требует BOUNDED_CONTEXT:unclassified для любого файла.
```

Deliverables:
- `src/sdd/graph/extractors/bc_resolver.py` — `BCResolver`:
  - `__init__(rules: list[BCRule])`
  - `resolve(path: str) → str | None` (path_prefix match → BC name, None → unclassified)
- `src/sdd/graph/extractors/bounded_context_edges.py` — `BoundedContextEdgeExtractor`:
  - `EXTRACTOR_VERSION = "1.0.0"`
  - `extract(index) → list[Edge]` — FILE → belongs_to → BOUNDED_CONTEXT
  - unmatched → BOUNDED_CONTEXT:unclassified node + belongs_to edge
  - BOUNDED_CONTEXT nodes создаются как SpatialNode(kind="BOUNDED_CONTEXT")
- `src/sdd/graph/extractors/cross_bc_edges.py` — `CrossBCEdgeExtractor`:
  - использует BCResolver (не дублирует логику)
  - FILE(BC:A) + imports/calls → FILE(BC:B, B≠A) → emit FILE → cross_bc_dependency → BOUNDED_CONTEXT:B
  - дедупликация: ≤1 edge на пару (src FILE, dst BC)
- `src/sdd/graph/extractors/__init__.py` — зарегистрировать новые экстракторы
  (порядок: BoundedContextEdgeExtractor перед CrossBCEdgeExtractor)
- `src/sdd/spatial/index.py` — `_collect_bounded_contexts()` в IndexBuilder:
  - загружает `bounded_contexts` из sdd_config.yaml → передаёт в BCResolver
- `src/sdd/graph_navigation/cli/arch_check.py` — `sdd arch-check`:
  - `--check bc-cross-dependencies [--format json|text]`
  - exit 0 (информационный режим в Phase 56)
  - возвращает список cross_bc_dependency edges
- `src/sdd/cli.py` — зарегистрировать `arch-check`
- `tests/unit/graph/test_bounded_context.py` — тесты:
  - FILE в src/sdd/graph/ → belongs_to → BOUNDED_CONTEXT:graph
  - FILE вне rules → BOUNDED_CONTEXT:unclassified
  - BCResolver: одинаковый результат для BoundedContext и CrossBC (I-BC-RESOLVER-1)
  - cross_bc_dependency: FILE в graph/ с imports из infra/ → cross_bc_dependency → BOUNDED_CONTEXT:infra
  - дедупликация cross_bc_dependency

---

### M6: LAYER + calls Edges (BC-56-LAYER)

```text
Spec:       §2 BC-56-LAYER
BCs:        BC-56-LAYER
Invariants: I-LAYER-DETERMINISTIC-1
Depends:    M0 (in_layer + calls в EDGE_KIND_PRIORITY)
Risks:      FILE не покрытый path_patterns → silent skip (нарушает predictability).
            Решение: I-LAYER-DETERMINISTIC-1 требует warning в stderr (не error), без in_layer edge.
            calls edges дублируют imports semantics → confusion в query.
            Решение: calls = explicit AST Call nodes с module prefix; imports = symbol import.
            Ограничение Phase 56: AST-based calls detection — scope spec §10 (Phase 57 BC-57-6).
            Phase 56: calls edges — структурные (из imports с full module ref), без AST Call detection.
```

Deliverables:
- `src/sdd/graph/extractors/layer_edges.py` — `LayerEdgeExtractor`:
  - `EXTRACTOR_VERSION = "1.0.0"`
  - `extract(index) → list[Edge]` — FILE → in_layer → LAYER
  - path_pattern match (из sdd_config.yaml layers секции)
  - LAYER nodes: LAYER:domain, LAYER:application, LAYER:infrastructure, LAYER:interface
  - непокрытые файлы: warning в stderr, без edge
- `src/sdd/graph/extractors/calls_edges.py` — `CallsEdgeExtractor`:
  - `EXTRACTOR_VERSION = "1.0.0"`
  - Phase 56 scope: derived из imports (full module reference) — AST Call detection отложен в Phase 57
- `src/sdd/spatial/index.py` — `_collect_layers()` в IndexBuilder
- `src/sdd/graph/extractors/__init__.py` — зарегистрировать LayerEdgeExtractor, CallsEdgeExtractor
- `tests/unit/graph/test_layer_edges.py` — тесты:
  - src/sdd/infra/ → in_layer → LAYER:infrastructure
  - src/sdd/commands/ → in_layer → LAYER:application
  - непокрытый файл → нет in_layer edge, warning logged
  - sdd explain LAYER:domain --edge-types in_layer → domain files

---

## Risk Notes

- R-1: **Registration order** — `CrossBCEdgeExtractor` MUST be registered AFTER `BoundedContextEdgeExtractor` в IndexBuilder. Нарушение → I-BC-RESOLVER-1 violation → GraphInvariantError. Mitigation: порядок явно зафиксирован в `__init__.py` с комментарием.
- R-2: **GRAPH-CALL-LOG-1** — `explain.py`, `trace.py`, `resolve.py` должны писать в `graph_calls.jsonl` (через `log_graph_call()`), не в `audit_log.jsonl`. Mitigation: тест M1 проверяет файл-destination.
- R-3: **Backward compat TaskNavigationSpec** — Phase 55 TaskSets с `resolve_keywords` продолжают работать. Mitigation: anchor_nodes optional, is_anchor_mode() = False для старых TaskSets.
- R-4: **sdd_config.yaml schema** — новые секции `bounded_contexts` и `layers` могут ломать `validate-config` если схема не расширена. Mitigation: M0 включает обновление schema-validation логики или делает секции optional.
- R-5: **Phase Gate (BC-56-T1)** — `sdd graph-stats --edge-type tested_by` должен показывать count > 0 до старта IMPLEMENT. Если TestedByExtractor (Phase 53) не работает после изменений M0-M6 → регрессия R-56-4. Mitigation: Regression Guard Step 56 Part 2 обязателен.
- R-6: **sdd record-metric flags** — Spec §11 использует `--name` вместо `--key` в Step 56-B. Авторитет: §2 BC-56-A2 определяет `--key`. Mitigation: CLI использует `--key` (§2 wins over §11 example).
