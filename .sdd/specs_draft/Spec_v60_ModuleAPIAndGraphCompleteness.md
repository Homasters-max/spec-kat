# Spec_v60 — Module API, Calls Refinement & Graph Completeness

**Status:** DRAFT (stub — детализация после Phase 59 COMPLETE)
**Depends on:** Phase 59 COMPLETE (Spec_v59 одобрена и реализована)
**Revised:** 2026-04-30

**Motive:** Spec_v59 закрыла embedding infra и RAG hardening. Spec_v60 завершает широкий
фронт из Spec_v58: MODULE API enforcement, calls edge с реальной precision,
INVARIANT nodes в графе, DSL, hotspot detection и graph-guard report.
Вместе они превращают граф в полноценный архитектурный SSOT.

---

## 1. Scope (reserved — не для реализации до Phase 59 COMPLETE)

| BC | Название | Приоритет |
|----|----------|-----------|
| BC-60-1 | ModulePublicAPIExtractor + ModuleDependsOnExtractor | Критический |
| BC-60-2 | CallsEdgeExtractor v2 (AST Call analysis, confidence 0.85) | Критический |
| BC-60-3 | InvariantEdgeExtractor (violated_by + enforced_by edges) | Критический |
| BC-60-4 | Graph Query DSL MVP (`sdd query --dsl`) | Средний |
| BC-60-5 | Hotspot Detection (`sdd hotspot`) | Средний |
| BC-60-6 | graph-guard Coverage Report (`sdd graph-guard report`) | Средний |
| BC-60-7 | ASTBoundaryMapper (deterministic AST-boundary chunking) | Средний |
| BC-60-8 | Persistent EmbeddingCache (file-based, extends BC-59-3) | Средний |
| BC-60-9 | MODULE / BOUNDED_CONTEXT / LAYER node kinds + path classifiers | Средний |

---

## 2. Краткое описание BC (предварительно, детализируется после Phase 59)

### BC-60-1: MODULE API Boundary
- `ModulePublicAPIExtractor`: читает `__init__.py`; если `__all__` задан → public files; иначе все файлы публичные
- Новые edge kinds: `module_public_api` (MODULE→FILE, priority 0.65), `module_depends_on` (MODULE→MODULE, priority 0.67)
- `sdd arch-check --check module-api-boundary`
- I-MODULE-API-1: внешние imports к FILE:f в MODULE:M — только через `module_public_api` edge

### BC-60-2: calls Edge Refinement
- Обновить `CallsEdgeExtractor` с imports-heuristic (0.6) на AST `ast.Call` analysis (0.85)
- Qualified call `foo.bar()` → 0.85; unqualified `from foo import bar; bar()` → 0.75
- I-CALLS-PRECISION-1: AST Call analysis обязателен; imports-based detection запрещён
- После: confidence 0.85, но I-ARCH-CONFIDENCE-1 threshold (0.9) → enforcement в Phase 61+

### BC-60-3: Arch Invariants as Graph Nodes
- Новый kind: `INVARIANT` (e.g., `INVARIANT:I-ARCH-1`)
- Новые edge kinds: `violated_by` (FILE→INVARIANT, priority 0.91), `enforced_by` (INVARIANT→COMMAND, priority 0.88)
- `InvariantEdgeExtractor`: строит из `invariant_registry.yaml`; `enforced_by` — статические; `violated_by` — из arch-check cache
- `sdd arch-check --check invariant-coverage`

### BC-60-4: Graph Query DSL (MVP)
- `sdd query --dsl "FROM <node> EXPAND <edges> [TRACE hops] [FILTER k=v]"`
- Whitelist-only, no eval()/exec() (I-DSL-1)
- Возвращает JSON с nodes + edges

### BC-60-5: Hotspot Detection
- `sdd hotspot [--top N]` — ранжирует FILE nodes по fan-in/fan-out coupling
- `sdd hotspot --check cross-bc-density` — пары BC с высокой связностью

### BC-60-6: graph-guard Coverage Report
- `sdd graph-guard report --task T-NNN` → JSON с покрытием anchor_nodes
- Использует тот же алгоритм что и `check` (I-GRAPH-GUARD-REPORT-1)

### BC-60-7: ASTBoundaryMapper
- Детерминированная нарезка DocumentChunk по AST границам (function, class)
- НЕ по token count, НЕ случайно (I-CHUNK-DETERMINISTIC-1)
- Расширяет infra из Spec_v59 (DocumentChunk.ast_signature)

### BC-60-8: Persistent EmbeddingCache
- Расширение `EmbeddingCache` из BC-59-3: file-based хранение (.sdd/runtime/embeddings_cache/)
- Composite key тот же (I-EMBED-CACHE-1)
- LRU eviction policy (параметр max_entries)

### BC-60-9: NODE KIND Extensions
- Добавить в `VALID_KINDS`: `MODULE`, `BOUNDED_CONTEXT`, `LAYER`
- Path-based classifiers (без LLM)
- `belongs_to` edges (FILE → BOUNDED_CONTEXT), `in_layer` edges (FILE → LAYER)

---

## 3. Pre-condition Gate

Перед `PLAN Phase 60` MUST выполниться:
```bash
sdd show-state   # phase_status = COMPLETE для Phase 59
```

Spec_v60 детализируется после Phase 59 COMPLETE.
