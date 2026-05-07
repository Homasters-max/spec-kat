# TaskSet_v56 — Phase 56: Graph-First + Architecture Context

Spec: specs/Spec_v56_GraphFirst.md
Plan: plans/Plan_v56.md

---

T-5601: M0 — Edge kinds + meta keys in types.py

Status:               DONE
Spec ref:             Spec_v56 §4 — Edge Kinds Phase 56
Invariants:           I-GRAPH-PRIORITY-1
spec_refs:            [Spec_v56 §4, I-GRAPH-PRIORITY-1]
produces_invariants:  [I-GRAPH-PRIORITY-1]
requires_invariants:  []
Inputs:               src/sdd/graph/types.py
Outputs:              src/sdd/graph/types.py
Acceptance:           EDGE_KIND_PRIORITY содержит cross_bc_dependency=0.63, calls=0.58, belongs_to=0.55, in_layer=0.35; ALLOWED_META_KEYS содержит path_prefix, description, path_patterns
Depends on:           —
Navigation:
    anchor_nodes:      FILE:src/sdd/graph/types.py
    allowed_traversal: imports, implements
    write_scope:       src/sdd/graph/types.py

---

T-5602: M0 — graph_calls_file() в paths.py + sdd_config.yaml

Status:               DONE
Spec ref:             Spec_v56 §2 BC-56-A1, §2 BC-56-BC, BC-56-LAYER
Invariants:           I-GRAPH-CALL-LOG-1, I-BC-DETERMINISTIC-1, I-LAYER-DETERMINISTIC-1
spec_refs:            [Spec_v56 §2, I-GRAPH-CALL-LOG-1]
produces_invariants:  [I-GRAPH-CALL-LOG-1]
requires_invariants:  []
Inputs:               src/sdd/infra/paths.py, .sdd/config/sdd_config.yaml
Outputs:              src/sdd/infra/paths.py, .sdd/config/sdd_config.yaml
Acceptance:           graph_calls_file() возвращает .sdd/runtime/graph_calls.jsonl; sdd_config.yaml содержит секции bounded_contexts и layers
Depends on:           —
Navigation:
    anchor_nodes:      FILE:src/sdd/infra/paths.py
    allowed_traversal: imports, implements
    write_scope:       src/sdd/infra/paths.py

---

T-5603: M1 — GraphCallLog модуль + unit tests

Status:               DONE
Spec ref:             Spec_v56 §2 BC-56-A1
Invariants:           I-GRAPH-CALL-LOG-1, I-AUDIT-SESSION-1
spec_refs:            [Spec_v56 §2 BC-56-A1, I-GRAPH-CALL-LOG-1, I-AUDIT-SESSION-1]
produces_invariants:  [I-GRAPH-CALL-LOG-1, I-AUDIT-SESSION-1]
requires_invariants:  [I-GRAPH-CALL-LOG-1]
Inputs:               src/sdd/infra/paths.py
Outputs:              src/sdd/infra/graph_call_log.py, tests/unit/infra/test_graph_call_log.py
Acceptance:           write→read roundtrip PASS; session_id filter PASS; absent file → empty list; malformed line → skipped
Depends on:           T-5602
Navigation:
    anchor_nodes:      FILE:src/sdd/infra/paths.py
    allowed_traversal: implements, imports
    write_scope:       src/sdd/infra/graph_call_log.py

---

T-5604: M1 — Интеграция log_graph_call() в CLI explain/trace/resolve

Status:               DONE
Spec ref:             Spec_v56 §2 BC-56-A1
Invariants:           I-GRAPH-CALL-LOG-1
spec_refs:            [Spec_v56 §2 BC-56-A1, I-GRAPH-CALL-LOG-1]
produces_invariants:  [I-GRAPH-CALL-LOG-1]
requires_invariants:  [I-GRAPH-CALL-LOG-1, I-AUDIT-SESSION-1]
Inputs:               src/sdd/graph_navigation/cli/explain.py, src/sdd/graph_navigation/cli/trace.py, src/sdd/graph_navigation/cli/resolve.py, src/sdd/infra/graph_call_log.py
Outputs:              src/sdd/graph_navigation/cli/explain.py, src/sdd/graph_navigation/cli/trace.py, src/sdd/graph_navigation/cli/resolve.py
Acceptance:           После каждого engine.query() вызывается log_graph_call(); graph_calls.jsonl обновляется при sdd explain / sdd trace / sdd resolve
Depends on:           T-5603
Navigation:
    resolve_keywords: explain
    write_scope:      src/sdd/graph_navigation/cli/explain.py, src/sdd/graph_navigation/cli/trace.py, src/sdd/graph_navigation/cli/resolve.py

---

T-5605: M2 — MetricRecorded event + record-metric команда + tests

Status:               DONE
Spec ref:             Spec_v56 §2 BC-56-A2
Invariants:           I-2, I-EREG-SCOPE-1
spec_refs:            [Spec_v56 §2 BC-56-A2, I-2]
produces_invariants:  [I-2]
requires_invariants:  [I-2]
Inputs:               src/sdd/core/events.py, src/sdd/commands/registry.py
Outputs:              src/sdd/core/events.py, src/sdd/commands/record_metric.py, src/sdd/commands/registry.py, tests/unit/commands/test_record_metric.py
Acceptance:           MetricRecorded(DomainEvent) с полями metric_key/value/phase_id/task_id/context; sdd record-metric --key X --value 1.0 --phase 56 --task T-5601 → MetricRecorded в EventLog; test_i_st_10_all_event_types_classified PASS
Depends on:           —
Navigation:
    resolve_keywords: DomainEvent, REGISTRY
    write_scope:      src/sdd/core/events.py, src/sdd/commands/record_metric.py, src/sdd/commands/registry.py

---

T-5606: M3 — graph-guard команда + регистрация в cli.py

Status:               DONE
Spec ref:             Spec_v56 §2 BC-56-G1
Invariants:           I-GRAPH-GUARD-1
spec_refs:            [Spec_v56 §2 BC-56-G1, I-GRAPH-GUARD-1]
produces_invariants:  [I-GRAPH-GUARD-1]
requires_invariants:  [I-GRAPH-CALL-LOG-1]
Inputs:               src/sdd/infra/graph_call_log.py, src/sdd/cli.py
Outputs:              src/sdd/graph_navigation/cli/graph_guard.py, src/sdd/cli.py
Acceptance:           sdd graph-guard check --task T-NNN exit 0 если ≥1 graph call в session; exit 1 JSON stderr с I-GRAPH-GUARD-1; read-only (не REGISTRY)
Depends on:           T-5603
Navigation:
    anchor_nodes:      FILE:src/sdd/graph_navigation/cli/explain.py
    allowed_traversal: imports, implements
    write_scope:       src/sdd/graph_navigation/cli/graph_guard.py, src/sdd/cli.py

---

T-5607: M3 — graph-stats команда + обновление docs

Status:               DONE
Spec ref:             Spec_v56 §2 BC-56-G2
Invariants:           I-GRAPH-GUARD-1
spec_refs:            [Spec_v56 §2 BC-56-G2]
produces_invariants:  []
requires_invariants:  [I-GRAPH-GUARD-1]
Inputs:               src/sdd/cli.py, .sdd/docs/sessions/implement.md, .sdd/docs/ref/tool-reference.md
Outputs:              src/sdd/graph_navigation/cli/graph_stats.py, src/sdd/cli.py, .sdd/docs/sessions/implement.md, .sdd/docs/ref/tool-reference.md
Acceptance:           sdd graph-stats [--edge-type X] [--node-type Y] [--format json|text] работает; implement.md содержит STEP 8 с sdd graph-guard check перед sdd complete; tool-reference.md обновлён
Depends on:           T-5606
Navigation:
    anchor_nodes:      FILE:src/sdd/spatial/index.py
    allowed_traversal: imports, implements
    write_scope:       src/sdd/graph_navigation/cli/graph_stats.py, src/sdd/cli.py

---

T-5608: M3 — Integration test: test_graph_guard.py

Status:               DONE
Spec ref:             Spec_v56 §11 Step 56-C
Invariants:           I-GRAPH-GUARD-1
spec_refs:            [Spec_v56 §11, I-GRAPH-GUARD-1]
produces_invariants:  [I-GRAPH-GUARD-1]
requires_invariants:  [I-GRAPH-CALL-LOG-1, I-GRAPH-GUARD-1]
Inputs:               src/sdd/graph_navigation/cli/graph_guard.py, src/sdd/infra/graph_call_log.py
Outputs:              tests/integration/test_graph_guard.py
Acceptance:           Integration test: graph call logged → graph-guard check exit 0; no calls → exit 1
Depends on:           T-5606, T-5604
Navigation:
    write_scope:      

---

T-5609: M4 — TaskNavigationSpec v2: anchor_nodes + is_anchor_mode + AnchorNode

Status:               TODO
Spec ref:             Spec_v56 §4 TaskNavigationSpec v2
Invariants:           I-DECOMPOSE-RESOLVE-3
spec_refs:            [Spec_v56 §4, I-DECOMPOSE-RESOLVE-3]
produces_invariants:  [I-DECOMPOSE-RESOLVE-3]
requires_invariants:  []
Inputs:               src/sdd/tasks/navigation.py
Outputs:              src/sdd/tasks/navigation.py
Acceptance:           anchor_nodes: tuple[str, ...] = () добавлено; allowed_traversal добавлено; is_anchor_mode() → True если anchor_nodes непустое; AnchorNode dataclass создан; TaskSet с resolve_keywords → is_anchor_mode() = False (backward compat)
Depends on:           —
Navigation:
    resolve_keywords: TaskNavigationSpec
    write_scope:      src/sdd/tasks/navigation.py

---

T-5610: M4 — Парсер: anchor_nodes секция + Candidate.score_normalized

Status:               TODO
Spec ref:             Spec_v56 §4 TaskNavigationSpec v2, Candidate
Invariants:           I-DECOMPOSE-RESOLVE-3
spec_refs:            [Spec_v56 §4, I-DECOMPOSE-RESOLVE-3]
produces_invariants:  [I-DECOMPOSE-RESOLVE-3]
requires_invariants:  [I-DECOMPOSE-RESOLVE-3]
Inputs:               src/sdd/domain/tasks/parser.py, src/sdd/context_kernel/engine.py, src/sdd/tasks/navigation.py
Outputs:              src/sdd/domain/tasks/parser.py, src/sdd/context_kernel/engine.py
Acceptance:           Парсер разбирает anchor_nodes: секцию → TaskNavigationSpec.anchor_nodes заполнен; Candidate.score_normalized = score/(score+1) ∈ (0,1); TaskSet с resolve_keywords продолжает парситься без ошибок
Depends on:           T-5609
Navigation:
    resolve_keywords: TaskNavigationSpec
    write_scope:      src/sdd/domain/tasks/parser.py, src/sdd/context_kernel/engine.py

---

T-5611: M5 — BCResolver (bc_resolver.py)

Status:               TODO
Spec ref:             Spec_v56 §2 BC-56-BC
Invariants:           I-BC-DETERMINISTIC-1, I-BC-RESOLVER-1
spec_refs:            [Spec_v56 §2 BC-56-BC, I-BC-DETERMINISTIC-1, I-BC-RESOLVER-1]
produces_invariants:  [I-BC-DETERMINISTIC-1, I-BC-RESOLVER-1]
requires_invariants:  []
Inputs:               .sdd/config/sdd_config.yaml
Outputs:              src/sdd/graph/extractors/bc_resolver.py
Acceptance:           BCResolver(rules).resolve(path) → str|None; одинаковый path → идентичный результат; None → unclassified
Depends on:           T-5602
Navigation:
    anchor_nodes:      FILE:src/sdd/graph/extractors/__init__.py
    allowed_traversal: imports, implements
    write_scope:       src/sdd/graph/extractors/bc_resolver.py

---

T-5612: M5 — BoundedContextEdgeExtractor + CrossBCEdgeExtractor + IndexBuilder

Status:               TODO
Spec ref:             Spec_v56 §2 BC-56-BC, BC-56-BC-2
Invariants:           I-BC-DETERMINISTIC-1, I-BC-CONSISTENCY-1, I-BC-RESOLVER-1, I-GRAPH-PRIORITY-1
spec_refs:            [Spec_v56 §2 BC-56-BC, I-BC-CONSISTENCY-1, I-BC-RESOLVER-1]
produces_invariants:  [I-BC-CONSISTENCY-1]
requires_invariants:  [I-BC-DETERMINISTIC-1, I-BC-RESOLVER-1, I-GRAPH-PRIORITY-1]
Inputs:               src/sdd/graph/extractors/bc_resolver.py, src/sdd/graph/extractors/__init__.py, src/sdd/spatial/index.py, src/sdd/graph/types.py
Outputs:              src/sdd/graph/extractors/bounded_context_edges.py, src/sdd/graph/extractors/cross_bc_edges.py, src/sdd/graph/extractors/__init__.py, src/sdd/spatial/index.py
Acceptance:           BoundedContextEdgeExtractor регистрируется ДО CrossBCEdgeExtractor в __init__.py; FILE вне rules → BOUNDED_CONTEXT:unclassified; ≤1 cross_bc_dependency edge на пару (src FILE, dst BC)
Depends on:           T-5611, T-5601
Navigation:
    anchor_nodes:      FILE:src/sdd/spatial/index.py
    allowed_traversal: imports, implements
    write_scope:       src/sdd/graph/extractors/bounded_context_edges.py, src/sdd/graph/extractors/cross_bc_edges.py, src/sdd/graph/extractors/__init__.py, src/sdd/spatial/index.py

---

T-5613: M5 — arch-check команда + регистрация в cli.py + unit tests

Status:               TODO
Spec ref:             Spec_v56 §2 BC-56-BC-2
Invariants:           I-BC-CONSISTENCY-1
spec_refs:            [Spec_v56 §2 BC-56-BC-2, I-BC-CONSISTENCY-1]
produces_invariants:  [I-BC-CONSISTENCY-1]
requires_invariants:  [I-BC-CONSISTENCY-1, I-BC-RESOLVER-1]
Inputs:               src/sdd/graph/extractors/bounded_context_edges.py, src/sdd/graph/extractors/cross_bc_edges.py, src/sdd/cli.py
Outputs:              src/sdd/graph_navigation/cli/arch_check.py, src/sdd/cli.py, tests/unit/graph/test_bounded_context.py
Acceptance:           sdd arch-check --check bc-cross-dependencies exit 0; возвращает список cross_bc_dependency edges; test: FILE в src/sdd/graph/ → belongs_to → BOUNDED_CONTEXT:graph; BCResolver: одинаковый результат для обоих экстракторов (I-BC-RESOLVER-1)
Depends on:           T-5612
Navigation:
    anchor_nodes:      FILE:src/sdd/graph/extractors/cross_bc_edges.py
    allowed_traversal: implements, guards
    write_scope:       src/sdd/graph_navigation/cli/arch_check.py, src/sdd/cli.py

---

T-5614: M6 — LayerEdgeExtractor + CallsEdgeExtractor + IndexBuilder + __init__

Status:               TODO
Spec ref:             Spec_v56 §2 BC-56-LAYER
Invariants:           I-LAYER-DETERMINISTIC-1, I-GRAPH-PRIORITY-1
spec_refs:            [Spec_v56 §2 BC-56-LAYER, I-LAYER-DETERMINISTIC-1]
produces_invariants:  [I-LAYER-DETERMINISTIC-1]
requires_invariants:  [I-GRAPH-PRIORITY-1]
Inputs:               src/sdd/graph/extractors/__init__.py, src/sdd/spatial/index.py, .sdd/config/sdd_config.yaml, src/sdd/graph/types.py
Outputs:              src/sdd/graph/extractors/layer_edges.py, src/sdd/graph/extractors/calls_edges.py, src/sdd/graph/extractors/__init__.py, src/sdd/spatial/index.py
Acceptance:           LayerEdgeExtractor: src/sdd/infra/ → in_layer → LAYER:infrastructure; непокрытый файл → warning в stderr, без edge; CallsEdgeExtractor Phase 56 scope: derived из imports (full module ref)
Depends on:           T-5601, T-5612
Navigation:
    anchor_nodes:      FILE:src/sdd/spatial/index.py
    allowed_traversal: imports, implements
    write_scope:       src/sdd/graph/extractors/layer_edges.py, src/sdd/graph/extractors/calls_edges.py, src/sdd/graph/extractors/__init__.py, src/sdd/spatial/index.py

---

T-5615: M6 — Unit tests: test_layer_edges.py

Status:               TODO
Spec ref:             Spec_v56 §2 BC-56-LAYER
Invariants:           I-LAYER-DETERMINISTIC-1
spec_refs:            [Spec_v56 §2 BC-56-LAYER, I-LAYER-DETERMINISTIC-1]
produces_invariants:  [I-LAYER-DETERMINISTIC-1]
requires_invariants:  [I-LAYER-DETERMINISTIC-1]
Inputs:               src/sdd/graph/extractors/layer_edges.py, src/sdd/graph/extractors/calls_edges.py
Outputs:              tests/unit/graph/test_layer_edges.py
Acceptance:           src/sdd/infra/ → in_layer → LAYER:infrastructure PASS; src/sdd/commands/ → in_layer → LAYER:application PASS; непокрытый файл → нет in_layer edge, warning logged PASS; sdd explain LAYER:domain --edge-types in_layer работает
Depends on:           T-5614
Navigation:
    write_scope:      

---

<!-- Granularity: 15 tasks (TG-2 range 10–30). All tasks independently implementable and testable (TG-1). -->

---

### Event-Addition Rule (I-EREG-SCOPE-1)

Если Task добавляет новый event type:

THEN Outputs MUST include:
  - src/sdd/core/events.py              (V1_L1_EVENT_TYPES — всегда)
  - src/sdd/domain/state/reducer.py    (ТОЛЬКО если тип имеет handler:
                                        _EVENT_SCHEMA + _fold())

DoD MUST include:
  - test_i_st_10_all_event_types_classified PASS
  - test_i_ereg_1_known_no_handler_is_derived PASS

NOTE: reducer.py НЕ нужен в Outputs для no-handler событий.
Это основной эффект Spec_v39.
