# Spec_v52 — Phase 52: CLI + Migration + LightRAG (BC SHIFT)

**Status:** Draft
**Supersedes:** Spec_v36_2 (Phase 36 ARCHIVED — superseded by Phase 50+51+52)
**Baseline:** Spec_v36_2_GraphNavigation.md §BC-36-7, §BC-36-4, §BC-36-5
**Depends on:** Phase 51 DoD полностью выполнен
**Session:** DRAFT_SPEC 2026-04-29 — разбивка Phase 36 на 50/51/52

**Цель:** Wire CLI, завершить LightRAG полную реализацию, закрыть migration window с измеримым DoD.

**Risk fix в этой фазе:** R-DOD-MIGRATION

---

## 0. Архитектурная модель (Phase 52 scope)

```text
CLI (BC-36-7) — runtime coordinator:
  index    = IndexBuilder.build()
  graph    = graph_service.get_or_build(index, force_rebuild)    ← Graph Subsystem (Phase 50)
  intent   = parse_query_intent(query)                           ← Context Kernel (Phase 51)
  policy   = policy_resolver.resolve(intent)                     ← Policy Layer (Phase 51)
  response = runtime.query(graph, policy, index, node_id)        ← Context Kernel (Phase 51)
  output → --format json|text
```

**Phase Isolation Rule (I-PHASE-ISOLATION-1):**
- Phase 52 не добавляет CLI-оркестрацию внутрь `ContextEngine` или `ContextRuntime`
- Phase 52 не пробрасывает `GraphService` как зависимость `ContextRuntime`
- `sdd.graph_navigation` не импортирует напрямую из `sdd.graph.cache` или `sdd.graph.builder` (только через `GraphService`)
- CLI handlers MUST satisfy I-RUNTIME-ORCHESTRATOR-1: никакой бизнес-логики кроме разбора аргументов, pipeline вызовов, форматирования вывода
- Проверяется `test_import_direction_phase52`

---

## 1. BC-36-7: CLI

### Команды

```bash
sdd resolve <query>            [--rebuild] [--debug] [--format json|text]
sdd explain <node_id>          [--rebuild] [--debug] [--format json|text]
sdd trace <node_id>            [--rebuild] [--debug] [--format json|text]
sdd invariant <I-NNN>          [--rebuild] [--debug] [--format json|text]
```

`--rebuild` — принудительная пересборка графа (игнорирует GraphCache).
`--format json` — машиночитаемый вывод `NavigationResponse` (для агентов). Дефолт: `text`.

**I-CLI-FORMAT-1**: `--format json` MUST output a valid `NavigationResponse` JSON on stdout. `--format text` MUST output human-readable markdown. Exit codes и JSON stderr неизменны при обоих форматах.

### Canonical handler pattern

```python
index    = IndexBuilder.build()
graph    = graph_service.get_or_build(index, force_rebuild=args.rebuild)   # Graph Subsystem
intent   = parse_query_intent(raw_query)    # I-INTENT-CANONICAL-1, I-INTENT-HEURISTIC-1
policy   = policy_resolver.resolve(intent)                                 # Policy Layer
response = runtime.query(graph, policy, index, node_id)                    # Context Kernel
# output → --format json|text
```

### Error Codes

Все ошибки выводятся в JSON stderr (совместимо с I-CLI-API-1):

| `error_type` | Условие |
|---|---|
| `NOT_FOUND` | SEARCH вернул 0 кандидатов; node_id не существует в графе |
| `GRAPH_NOT_BUILT` | GraphCache промах + IndexBuilder завершился с ошибкой |
| `INVARIANT_VIOLATION` | `GraphInvariantError` при построении графа |
| `BUDGET_EXCEEDED` | Context превысил лимит (seed-only context) |

**I-CLI-ERROR-CODES-1**: BC-36 CLI MUST use exactly these `error_type` values. Unknown errors MUST use `error_type = "INTERNAL_ERROR"`.

### Debug-режим

```json
{
  "intent": "EXPLAIN",
  "selection": {
    "start_node": "COMMAND:complete",
    "strategy": "EXPLAIN_DEFAULT_V1",
    "steps": [...]
  },
  "budget": {
    "max_nodes": 20,
    "max_edges": 40,
    "max_chars": 16000,
    "used_nodes": 17,
    "used_edges": 31,
    "total_chars": 9800
  },
  "dropped": {"nodes": [], "edges": []}
}
```

**I-CLI-TRANSPARENCY-1**: В debug-режиме каждая стадия выбора (`selection.steps`) видна пользователю.

**I-CLI-TRANSPARENCY-2**: В debug-режиме бюджет и фактически использованные ресурсы отражены.

### §7.2 Tool Definitions (Agent Integration)

```json
{
  "name": "sdd_resolve",
  "description": "Поиск узлов графа по свободному тексту. Возвращает ranked list кандидатов (SearchCandidate) без выбора. При одном кандидате ContextEngine автоматически применяет RESOLVE_EXACT (I-SEARCH-AUTO-EXACT-1).",
  "input_schema": {
    "type": "object",
    "properties": {
      "query":   {"type": "string", "description": "Свободный текст или NAMESPACE:ID"},
      "rebuild": {"type": "boolean", "default": false}
    },
    "required": ["query"]
  }
}
```

```json
{
  "name": "sdd_explain",
  "description": "Объяснить как работает узел графа: его out-связи (emits, guards, implements, tested_by). Для EVENT/TERM автоматически применяется TRACE fallback.",
  "input_schema": {
    "type": "object",
    "properties": {
      "node_id": {"type": "string", "description": "Точный node_id, например COMMAND:complete"},
      "rebuild": {"type": "boolean", "default": false}
    },
    "required": ["node_id"]
  }
}
```

```json
{
  "name": "sdd_trace",
  "description": "Проследить обратные связи узла: кто на него ссылается (reverse BFS, max hop=2). Лучший выбор для EVENT и TERM узлов.",
  "input_schema": {
    "type": "object",
    "properties": {
      "node_id": {"type": "string", "description": "Точный node_id, например EVENT:TaskImplementedEvent"},
      "rebuild": {"type": "boolean", "default": false}
    },
    "required": ["node_id"]
  }
}
```

```json
{
  "name": "sdd_invariant",
  "description": "Навигация по инварианту: узел INVARIANT + verified_by + introduced_in связи.",
  "input_schema": {
    "type": "object",
    "properties": {
      "invariant_id": {"type": "string", "description": "Идентификатор инварианта, например I-GRAPH-DET-1"},
      "rebuild":      {"type": "boolean", "default": false}
    },
    "required": ["invariant_id"]
  }
}
```

**I-TOOL-DEF-1**: Tool definitions MUST match CLI contract exactly. Изменение CLI сигнатуры = breaking change → требует bump tool schema version.

---

## 2. BC-36-4: LightRAGProjection (полная реализация)

### LightRAGRegistry — fingerprint-bound KG storage

```python
class LightRAGRegistry:
    """Pure filesystem registry: graph_fingerprint → KG path.
    Не знает о GraphService, ContextEngine, LightRAGClient.
    Storage: .sdd/runtime/lightrag_cache/<graph_fingerprint>/
    """
    def has_kg(self, fingerprint: str) -> bool:
        """True если KG для данного fingerprint существует на диске."""
        ...

    def get_path(self, fingerprint: str) -> Path:
        """Возвращает путь .sdd/runtime/lightrag_cache/<fingerprint>/.
        Путь возвращается независимо от существования KG.
        """
        ...
```

**I-RAG-EXPORT-FRESHNESS-1**: LightRAG KG MUST be bound to `graph_fingerprint`. Storage MUST be `.sdd/runtime/lightrag_cache/<graph_fingerprint>/`. If the stored KG fingerprint does not match the current `graph_fingerprint` → KG is invalid and MUST NOT be used. `LightRAGRegistry.has_kg(fingerprint)` is the single check point.

**I-RAG-REGISTRY-PURE-1**: `LightRAGRegistry` MUST be a pure filesystem accessor. MUST NOT import `GraphService`, `ContextEngine`, or `LightRAGClient`.

### LightRAGProjection

```python
# Phase 52 не создаёт новый LightRAGProjection.
# Canonical class живёт в sdd.context_kernel.rag_types (I-LIGHTRAG-CANONICAL-1).
# Phase 52 передаёт LightRAGRegistry через __init__(registry) — ЕДИНСТВЕННОЕ изменение.
# query() сигнатура НЕ меняется.

class LightRAGProjection:
    def __init__(self, registry: "LightRAGRegistry | None" = None): ...
    # Phase 51: registry=None (stub mode). Phase 52: registry = реальный LightRAGRegistry.

    def query(self,
              question:    str,
              context:     Context,
              rag_mode:    RagMode,
              rag_client:  "LightRAGClient | None") -> "RAGResult | None":
        """
        Если rag_client is None → logging.warning(); return None (деградация к OFF).

        fingerprint = context.graph_snapshot_hash  # берётся из Context, не из параметра

        Если rag_mode in (GLOBAL, HYBRID) и self._registry is not None:
            если not registry.has_kg(fingerprint):
                logging.warning("KG not found for fingerprint; degrading to LOCAL")
                rag_mode = RagMode.LOCAL   # деградация к LOCAL, не OFF

        rag_client.query(question, context=context.documents, mode=rag_mode.value.lower())
        LightRAG получает context.documents во всех режимах.
        → return RAGResult(summary=..., rag_mode=rag_mode.value)
        """
```

**I-RAG-DEGRADE-LOCAL-1**: При отсутствии KG для текущего `graph_fingerprint`, `RagMode.GLOBAL` и `RagMode.HYBRID` MUST degrade к `RagMode.LOCAL` (не OFF). Warning MUST быть залогирован в stderr. `NavigationResponse.rag_mode` MUST отражать фактически использованный режим (`"LOCAL"`), не запрошенный.

### LightRAGExporter + sdd rag-export

```python
class LightRAGExporter:
    def export(self,
               graph:       DeterministicGraph,
               docs:        list[DocumentChunk],
               rag_client:  "LightRAGClient",
               registry:    LightRAGRegistry,
               fingerprint: str) -> None:
        """
        Идемпотентный экспорт:
        1. Если registry.has_kg(fingerprint) → skip, return (уже актуален).
        2. entities = [{entity_name: n.node_id, entity_type: n.kind, ...}]
        3. relationships = [{src_id: e.src, tgt_id: e.dst, description: e.kind, ...}]
        4. chunks = [{content: doc.content, source_id: doc.node_id, file_path: ...}]
        5. rag_client.insert_custom_kg({entities, relationships, chunks})
           → сохраняет в registry.get_path(fingerprint)/
        """
```

**sdd rag-export** — отдельная CLI-команда (не часть query-пайплайна):

```bash
sdd rag-export [--rebuild]
```

Вычисляет `graph_fingerprint`, проверяет `LightRAGRegistry.has_kg()`, при промахе — запускает `LightRAGExporter.export()`. `--rebuild` игнорирует существующий KG и пересобирает.

**I-RAG-EXPORT-NOT-IN-QUERY-1**: `LightRAGExporter.export()` MUST NOT be called from `ContextEngine`, `ContextRuntime`, или любого CLI query-handler (resolve/explain/trace/invariant). Экспорт — исключительно через `sdd rag-export` или явный вызов вне query-пути.

**I-RAG-GLOBAL-V1-DISABLED-1**: В Phase 52 (v1) `RagMode.GLOBAL` и `RagMode.HYBRID` MUST be disabled by default. `PolicyResolver._DEFAULT` MUST NOT assign `GLOBAL` или `HYBRID` в v1. При явном запросе GLOBAL/HYBRID через конфигурацию — предупреждение в stderr: "GLOBAL/HYBRID mode is experimental; requires sdd rag-export". Причина: hidden state (KG), freshness risk, LLM non-determinism. Активация в будущей фазе после стабилизации `LightRAGRegistry` + `sdd rag-export`.

**I-RAG-EXPORT-TASK-MODE-1**: `sdd rag-export` MUST быть исключён из task mode build_commands (ключ начинается с `"rag"` → исключается аналогично `"test"`-командам по I-TASK-MODE-1).

**Инварианты LightRAG:**

- **I-RAG-1**: `LightRAGProjection` не создаёт новых фактов; все entities/relationships/chunks из `DeterministicGraph`/`DocumentChunk`.
- **I-RAG-CHUNK-1**: Каждый entity/relationship в LightRAG связан хотя бы с одним chunk через `source_id`/`file_path`.
- **I-RAG-NO-PERSISTENCE-1**: `LightRAGClient` used in `query()` MUST NOT persist any state across calls.

---

## 3. BC-36-5: Legacy Context Migration — completion (R-DOD-MIGRATION fix)

### migration.py

```python
# src/sdd/graph_navigation/migration.py

def migration_complete() -> bool:
    """
    Проверяет оба критерия I-LEGACY-FS-EXCEPTION-1:
    1. grep: все BC-36 CLI handlers маршрутизируют через ContextRuntime
    2. grep: build_context.py имеет 0 прямых callers вне context_legacy/

    После возврата True — I-LEGACY-FS-EXCEPTION-1 формально закрыт.
    Прямое чтение filesystem в build_context.py становится нарушением I-GRAPH-FS-ROOT-1.
    """
```

`migration_complete()` — hard gate в DoD: если возвращает `False`, DoD Phase 52 не выполнен.

### Изменяемые файлы

```
src/sdd/context/build_context.py   → тонкий адаптер + deprecation warning
                                     rename → src/sdd/context_legacy/build_context.py
                                     (пакетная изоляция для I-CTX-MIGRATION-4)
```

**I-CTX-MIGRATION-1..4** (финальная проверка): все инварианты миграции должны выполняться.

**I-LEGACY-FS-EXCEPTION-1** (закрытие): Migration window закрыт после `migration_complete() == True`.

---

## 4. Agent Integration Guide

### 4.1 Онтология

**Node kinds:**

| Kind | Namespace пример | Описание |
|---|---|---|
| `COMMAND` | `COMMAND:complete` | CLI-команда SDD |
| `EVENT` | `EVENT:TaskImplementedEvent` | DomainEvent |
| `TASK` | `TASK:T-4901` | Задача TaskSet |
| `INVARIANT` | `INVARIANT:I-GRAPH-DET-1` | Инвариант системы |
| `TERM` | `TERM:WriteKernel` | Термин глоссария |
| `FILE` | `FILE:src/sdd/commands/complete.py` | Файл кодовой базы |

**Edge kinds и приоритеты:**

| Kind | Приоритет | Направление |
|---|---|---|
| `emits` | 0.95 | COMMAND → EVENT |
| `guards` | 0.90 | GUARD → COMMAND |
| `implements` | 0.85 | FILE → COMMAND |
| `tested_by` | 0.80 | COMMAND → TEST |
| `verified_by` | 0.75 | INVARIANT → TEST |
| `depends_on` | 0.70 | TASK → TASK |
| `introduced_in` | 0.65 | INVARIANT → COMMAND |
| `imports` | 0.60 | FILE → FILE |
| `means` | 0.50 | TERM → NODE |

### 4.2 Known Graph Gap — COMMAND ↔ FILE (R-COMMAND-FILE-GAP)

**Проблема (обнаружена в Phase 51):** `COMMAND`-узлы в `SpatialIndex` указывают на `registry.py`
как общий `path`, а не на индивидуальные handler-файлы. Из-за этого у узлов вида
`COMMAND:activate-phase` нет исходящих рёбер в графе — BFS по такому seed даёт пустой контекст.

Фактические handler-файлы (`FILE:src/sdd/commands/activate_phase.py`) существуют как FILE-узлы,
но ребра `implements` (FILE → COMMAND) ещё не производятся ни одним extractor'ом.

**Требование Phase 52:** Реализовать `ImplementsEdgeExtractor`, который связывает handler-файлы
с соответствующими COMMAND-узлами через `implements`-рёбра (priority = 0.85):

```python
# src/sdd/graph/extractors/implements_edges.py
class ImplementsEdgeExtractor:
    """Emit FILE → COMMAND 'implements' edges by matching command name to handler filename.

    Mapping rule: COMMAND:<name> → FILE:src/sdd/commands/<name_underscored>.py
    Example: COMMAND:activate-phase → FILE:src/sdd/commands/activate_phase.py
    """
    EXTRACTOR_VERSION = "implements_v1"
```

**I-GRAPH-IMPLEMENTS-1**: После реализации `ImplementsEdgeExtractor` каждый COMMAND-узел,
для которого существует соответствующий handler FILE-узел, MUST иметь ровно одно входящее
`implements`-ребро. Отсутствие `implements`-ребра при наличии handler-файла = нарушение
(проверяется `test_command_nodes_have_implements_edges`).

**I-GRAPH-IMPLEMENTS-2**: `sdd explain COMMAND:<name>` MUST seed BFS от FILE-узла handler
(через входящее `implements`-ребро), если прямой BFS от COMMAND-узла возвращает пустой контекст
(`selection_exhausted=True` и `len(nodes)==1`). Это fallback, а не основной путь.

---

### 4.3 Правила работы агента

**I-AGENT-1**: Агент MUST NOT читать файлы кодовой базы напрямую.
**I-AGENT-2**: `effective_intent ≠ intent` → агент MUST сообщить о fallback.
**I-AGENT-3**: `selection_exhausted: true` → агент MUST остановить навигацию по ветке.
**I-AGENT-4**: `DocumentChunk.references` — готовые цели для следующего navigation call.
**I-AGENT-5**: `rag_summary` — inference, не факт; при точности использовать только `context`.
**I-AGENT-6**: Error handling по error_type (NOT_FOUND, GRAPH_NOT_BUILT, INVARIANT_VIOLATION, INTERNAL_ERROR).
**I-AGENT-7**: Сессионный бюджет calls — ответственность agent harness.

---

## 5. Новые файлы

```
src/sdd/graph/extractors/implements_edges.py — ImplementsEdgeExtractor (R-COMMAND-FILE-GAP fix)
src/sdd/graph_navigation/__init__.py
src/sdd/graph_navigation/cli/resolve.py    — sdd resolve
src/sdd/graph_navigation/cli/explain.py   — sdd explain
src/sdd/graph_navigation/cli/trace.py     — sdd trace
src/sdd/graph_navigation/cli/invariant.py — sdd invariant
src/sdd/graph_navigation/cli/rag_export.py — sdd rag-export (идемпотентный экспорт KG)
src/sdd/graph_navigation/cli/formatting.py — format_json, format_text, format_error, debug_output
src/sdd/graph_navigation/tool_definitions.py — 4 JSON schemas (§7.2)
src/sdd/graph_navigation/rag/registry.py      — LightRAGRegistry (fingerprint → path)
src/sdd/graph_navigation/rag/lightrag_projection.py — LightRAGProjection (полная реализация)
src/sdd/graph_navigation/rag/lightrag_exporter.py   — LightRAGExporter (идемпотентный)
src/sdd/graph_navigation/migration.py      — migration_complete() → bool
tests/unit/graph_navigation/test_cli_formatting.py
tests/unit/graph_navigation/test_cli_error_codes.py
tests/unit/graph_navigation/test_tool_definitions.py
tests/unit/graph_navigation/test_rag_projection.py
tests/unit/graph_navigation/test_rag_registry.py
tests/unit/graph_navigation/test_migration.py
tests/integration/test_graph_navigation_cli.py  — INT-1..10
tests/integration/test_lightrag_export.py
```

### Изменяемые файлы

```
src/sdd/cli.py                          — зарегистрировать 4 новые команды
src/sdd/context/build_context.py        → src/sdd/context_legacy/build_context.py
```

---

## 6. Verification

### Unit tests

28. `test_cli_debug_output` — I-CLI-TRANSPARENCY-1/2.
46. `test_cli_format_json_valid_navigation_response` — I-CLI-FORMAT-1.
47. `test_cli_error_codes_not_found` — I-CLI-ERROR-CODES-1.
48. `test_cli_error_codes_graph_not_built`
49. `test_tool_def_node_id_format` — I-TOOL-DEF-1.

**LightRAGRegistry:**

59. `test_registry_has_kg_false_when_missing` — I-RAG-EXPORT-FRESHNESS-1: отсутствие папки → `has_kg() == False`.
60. `test_registry_has_kg_true_after_export` — после `LightRAGExporter.export()` → `has_kg() == True`.
61. `test_registry_get_path_deterministic` — одинаковый fingerprint → одинаковый путь.
62. `test_registry_does_not_import_graph_service` — I-RAG-REGISTRY-PURE-1: grep-тест.

**LightRAGProjection деградация:**

63. `test_projection_global_degrades_to_local_when_no_kg` — I-RAG-DEGRADE-LOCAL-1: GLOBAL + no KG → LOCAL + warning, `rag_mode="LOCAL"` в response.
64. `test_projection_hybrid_degrades_to_local_when_no_kg` — аналогично для HYBRID.
65. `test_projection_none_client_degrades_to_off` — `rag_client=None` → `None` (OFF, не LOCAL).
66. `test_projection_response_rag_mode_reflects_actual` — `NavigationResponse.rag_mode` = фактически использованный режим.

**LightRAGExporter идемпотентность:**

67. `test_exporter_skip_if_kg_exists` — I-RAG-EXPORT-FRESHNESS-1: повторный вызов → skip, `insert_custom_kg` не вызывается.
68. `test_exporter_not_called_from_context_engine` — I-RAG-EXPORT-NOT-IN-QUERY-1: grep-тест.

`test_migration_complete_returns_true` — migration gate.
`test_import_direction_phase52` — `sdd.graph_navigation` не импортирует из `sdd.graph.cache` или `sdd.graph.builder` напрямую.
`test_command_nodes_have_implements_edges` — I-GRAPH-IMPLEMENTS-1: каждый COMMAND-узел с соответствующим handler-файлом имеет ≥1 входящее `implements`-ребро (grep + graph build на реальном индексе).
`test_explain_command_fallback_to_file_seed` — I-GRAPH-IMPLEMENTS-2: `sdd explain COMMAND:activate-phase` возвращает непустой контекст (≥2 узла, включая handler FILE-узел).
`test_cli_handler_no_business_logic_beyond_pipeline` — I-RUNTIME-ORCHESTRATOR-1: CLI handler содержит только pipeline вызовы (IndexBuilder → GraphService → parse_query_intent → PolicyResolver → ContextRuntime → format); никаких BFS/selection/scoring логик.

### Integration tests

1. `sdd explain COMMAND:complete` → детерминированный JSON, ≤20 узлов, `total_chars ≤ 16000`.
2. `sdd trace EVENT:TaskImplementedEvent` → ≤2 hop, корректные reverse-соседи.
3. `sdd invariant I-XXX` → INVARIANT узел + verified_by/introduced_in.
4. `sdd resolve "complete task"` → ranked list при N>1, без выбора.
5. `sdd resolve "unknown xyz"` → exit 1, `must_not_guess: true`.
6. `sdd explain EVENT:X` → TRACE fallback + warning в stderr.
7. `sdd explain COMMAND:complete --rebuild` → graph пересобирается.
8. LightRAGProjection: export не создаёт новые node_id; RAG query получает только context.documents.
9. (Phase 50 regression)
10. `ContextAssembler` не вызывает `build_context()`.

---

## 7. DoD Phase 52

1. `sdd resolve`, `sdd explain`, `sdd trace`, `sdd invariant` работают через `sdd.cli:main`
2. Все 5 unit-тестов (28, 46–49) проходят
3. Все 10 integration tests (INT-1..10) проходят
4. `--format json` = валидный `NavigationResponse` JSON на stdout
5. Все 4 typed error codes (NOT_FOUND, GRAPH_NOT_BUILT, INVARIANT_VIOLATION, BUDGET_EXCEEDED) покрыты тестами 47–48
6. **`migration_complete()` возвращает `True` — hard gate** (False → DoD не выполнен)
7. `LightRAGClient` = Protocol; `LightRAGProjection` компилируется без lightrag; graceful degradation к OFF при `rag_client=None`, к LOCAL при отсутствии KG в registry
8. `LightRAGRegistry` — pure filesystem, zero imports от GraphService/ContextEngine — grep-тест (test 62)
9. `LightRAGExporter.export()` идемпотентен — тест 67
10. `sdd rag-export` работает через `sdd.cli:main`; исключён из task mode build_commands
11. Tool definitions в `tool_definitions.py` соответствуют CLI — test 49
12. `mypy --strict` проходит на `sdd.graph_navigation.*`
13. Все Phase 50 и Phase 51 тесты не регрессируют
14. `ImplementsEdgeExtractor` реализован; `COMMAND`-узлы с handler-файлами имеют входящее `implements`-ребро; `sdd explain COMMAND:<name>` возвращает непустой контекст (I-GRAPH-IMPLEMENTS-1/2)
