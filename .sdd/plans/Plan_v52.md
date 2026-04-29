# Plan_v52 — Phase 52: CLI + LightRAG + Migration Window Close

Status: DRAFT
Spec: specs/Spec_v52_CLIMigrationLightRAG.md

---

## Logical Context

type: backfill
anchor_phase: 36
rationale: "Phase 36 was archived and split into phases 50/51/52. Phase 52 implements the remaining BC-36 items: BC-36-7 (CLI), BC-36-4 (LightRAGProjection full), BC-36-5 (legacy migration close). Fills the gap left when Phase 36 was retired."

---

## Milestones

### M1: ImplementsEdgeExtractor — R-COMMAND-FILE-GAP fix

```text
Spec:       §4.2 — Known Graph Gap COMMAND ↔ FILE
BCs:        BC-36 (graph subsystem, extractor layer)
Invariants: I-GRAPH-IMPLEMENTS-1, I-GRAPH-IMPLEMENTS-2
Depends:    Phase 50 (DeterministicGraph), Phase 51 (SpatialIndex with COMMAND nodes)
Risks:      Без implements-рёбер sdd explain COMMAND:<name> возвращает пустой контекст;
            M2 (CLI explain fallback) блокирован без M1.
```

Реализовать `src/sdd/graph/extractors/implements_edges.py` — `ImplementsEdgeExtractor`.
Маппинг: `COMMAND:<name>` → `FILE:src/sdd/commands/<name_underscored>.py`.
Зарегистрировать в pipeline построения графа.
Тест: `test_command_nodes_have_implements_edges`, `test_explain_command_fallback_to_file_seed`.

---

### M2: CLI navigation commands (sdd resolve / explain / trace / invariant)

```text
Spec:       §1 — BC-36-7 CLI
BCs:        BC-36-7
Invariants: I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1, I-CLI-TRANSPARENCY-1, I-CLI-TRANSPARENCY-2,
            I-RUNTIME-ORCHESTRATOR-1, I-PHASE-ISOLATION-1, I-CLI-FORMAT-1, I-TOOL-DEF-1
Depends:    M1 (explain fallback), Phase 51 (ContextRuntime, PolicyResolver, parse_query_intent)
Risks:      CLI handler с бизнес-логикой нарушает I-RUNTIME-ORCHESTRATOR-1;
            прямой импорт из sdd.graph.cache нарушает I-PHASE-ISOLATION-1 (тест: test_import_direction_phase52).
```

Файлы: `src/sdd/graph_navigation/__init__.py`, `cli/resolve.py`, `cli/explain.py`,
`cli/trace.py`, `cli/invariant.py`, `cli/formatting.py`, `tool_definitions.py`.
Canonical handler pattern: `IndexBuilder → GraphService → parse_query_intent → PolicyResolver → ContextRuntime → format`.
Зарегистрировать команды в `src/sdd/cli.py`.
Тесты: 28, 46–49, `test_cli_handler_no_business_logic_beyond_pipeline`, INT-1..7.

---

### M3: LightRAGRegistry + LightRAGExporter + sdd rag-export

```text
Spec:       §2 — BC-36-4 (LightRAGRegistry, LightRAGExporter, sdd rag-export)
BCs:        BC-36-4
Invariants: I-RAG-EXPORT-FRESHNESS-1, I-RAG-REGISTRY-PURE-1, I-RAG-EXPORT-NOT-IN-QUERY-1,
            I-RAG-GLOBAL-V1-DISABLED-1, I-RAG-EXPORT-TASK-MODE-1, I-RAG-1, I-RAG-CHUNK-1
Depends:    M2 (sdd.cli.py зарегистрирован)
Risks:      LightRAGExporter вызван из query-пути нарушает I-RAG-EXPORT-NOT-IN-QUERY-1
            (grep-тест 68); fingerprint mismatch → stale KG.
```

Файлы: `src/sdd/graph_navigation/rag/registry.py`, `rag/lightrag_exporter.py`,
`cli/rag_export.py`.
`sdd rag-export [--rebuild]`: идемпотентный экспорт KG.
Исключить из task mode build_commands (ключ `"rag"`).
Тесты: 59–62, 67–68, `tests/integration/test_lightrag_export.py`.

---

### M4: LightRAGProjection — полная реализация (degradation logic)

```text
Spec:       §2 — LightRAGProjection, деградация GLOBAL/HYBRID → LOCAL
BCs:        BC-36-4
Invariants: I-RAG-DEGRADE-LOCAL-1, I-RAG-NO-PERSISTENCE-1, I-LIGHTRAG-CANONICAL-1 (Phase 51)
Depends:    M3 (LightRAGRegistry)
Risks:      NavigationResponse.rag_mode отражает запрошенный, а не фактический режим — нарушение I-RAG-DEGRADE-LOCAL-1.
```

Обновить `LightRAGProjection` (канонический класс в `sdd.context_kernel.rag_types`):
— добавить `__init__(registry: LightRAGRegistry | None = None)`;
— деградация GLOBAL/HYBRID → LOCAL при `has_kg() == False`;
— деградация → OFF при `rag_client is None`.
Тесты: 63–66, INT-8.

---

### M5: Legacy Context Migration close (migration.py + context_legacy)

```text
Spec:       §3 — BC-36-5
BCs:        BC-36-5
Invariants: I-CTX-MIGRATION-1..4, I-LEGACY-FS-EXCEPTION-1, I-GRAPH-FS-ROOT-1
Depends:    M2 (все BC-36 CLI handlers маршрутизируют через ContextRuntime)
Risks:      migration_complete() == False блокирует DoD; прямые callers build_context.py
            за пределами context_legacy/ нарушают I-GRAPH-FS-ROOT-1 после закрытия migration window.
```

Реализовать `src/sdd/graph_navigation/migration.py` с `migration_complete() -> bool`.
Переименовать `src/sdd/context/build_context.py` → `src/sdd/context_legacy/build_context.py`.
Добавить deprecation warning в адаптер.
Тест: `test_migration_complete_returns_true`, INT-10.

---

### M6: Test suite + DoD verification

```text
Spec:       §6 — Verification, §7 — DoD Phase 52
BCs:        все BC-36
Invariants: все выше
Depends:    M1..M5
Risks:      Phase 50/51 рegressии; mypy --strict на sdd.graph_navigation.* — пропущенные аннотации.
```

Полный прогон unit + integration тестов.
`mypy --strict` на `sdd.graph_navigation.*`.
Phase 50 + 51 regression tests.
`sdd validate-invariants --check I-PHASES-INDEX-1`.
Все 14 пунктов DoD Phase 52.

---

## Risk Notes

- R-1: **Import direction** — CLI handlers могут случайно импортировать из `sdd.graph.cache`/`sdd.graph.builder` напрямую, нарушая I-PHASE-ISOLATION-1. Митигация: `test_import_direction_phase52` запускается в M2.
- R-2: **Export in query path** — `LightRAGExporter.export()` может утечь в ContextEngine/ContextRuntime при рефакторинге. Митигация: grep-тест 68 в M3.
- R-3: **Migration gate** — если `build_context.py` остаётся с прямыми callers вне `context_legacy/`, `migration_complete()` вернёт `False` и заблокирует DoD. Митигация: M5 реализуется до M6; `test_migration_complete_returns_true` — hard gate.
- R-4: **RAG mode leak** — `NavigationResponse.rag_mode` может отражать запрошенный, а не фактический режим деградации. Митигация: тест 66 в M4.
- R-5: **Phase 50/51 regressions** — изменения в extractor pipeline (M1) и LightRAGProjection (M4) могут сломать Phase 50/51 тесты. Митигация: явный regression run в M6 до DoD.
