# Plan_v54 — Phase 54: Real System Validation

Status: DRAFT
Spec: specs/Spec_v54_RealSystemValidation.md

---

## Logical Context

```
type: none
rationale: "Стандартная фаза end-to-end валидации. Проверяет живучесть системы Phase 52 в реальных условиях — не исправляет баги, не закрывает пропуски, а подтверждает, что система работает как целое."
```

---

## Milestones

### M1: Cold Start, Determinism & Cache Correctness (TEST 1–3)

```text
Spec:       §2 — TEST 1 (Cold start), TEST 2 (Determinism), TEST 3 (Cache correctness)
Invariants: I-SYSVAL-COLD-1, I-SYSVAL-DET-1, I-SYSVAL-CACHE-1,
            I-GRAPH-DET-1, I-GRAPH-DET-3
Task:       T-5401
Depends:    — (first milestone; requires Phase 52 COMPLETE)
Risks:      Если diff в TEST 2 непустой — CRITICAL, STOP → report-error.
            Если graф пустой при cold start — GraphService/IndexBuilder сломан.
```

Выполняется строго в порядке TEST 1 → TEST 2 → TEST 3.
TEST 2 и TEST 3 используют артефакты TEST 1 (`/tmp/r1.json`).

---

### M2: Cache Invalidation — Mutation Probe (TEST 4)

```text
Spec:       §2 — TEST 4 (Mutation → rebuild)
Invariants: I-SYSVAL-MUTATE-1
Task:       T-5402
Depends:    M1 (нужен /tmp/r1.json с baseline fingerprint)
Risks:      Если fingerprint не изменился — сломана логика snapshot_hash в IndexBuilder.
            Файл src/sdd/commands/complete.py MUST быть восстановлен после теста (git checkout).
```

---

### M3: CLI Full Cycle & Error Model (TEST 5–6)

```text
Spec:       §2 — TEST 5 (CLI полный цикл, BC-36-7), TEST 6 (Error model)
Invariants: BC-36-7, I-SYSVAL-ERROR-1, I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1
Task:       T-5403
Depends:    M1 (граф должен быть построен)
Risks:      Traceback в stdout = нарушение I-SYSVAL-ERROR-1.
            Неизвестная команда exit 0 = нарушение I-CLI-ERROR-CODES-1.
```

Проверяются все 4 CLI-команды BC-36-7: `resolve`, `explain`, `trace`, `invariant`.

---

### M4: LightRAG Optional & Export Idempotency (TEST 7–8)

```text
Spec:       §2 — TEST 7 (без LightRAG), TEST 8 (rag-export idempotency)
Invariants: I-SYSVAL-RAG-OPTIONAL-1, I-SYSVAL-IDEM-1,
            I-RAG-DEGRADE-LOCAL-1, I-RAG-EXPORT-FRESHNESS-1
Task:       T-5404
Depends:    M1 (граф построен)
Risks:      ImportError при отсутствии lightrag-hku — нарушена опциональность зависимости.
            Второй вызов rag-export изменяет KG — нарушена идемпотентность.
```

Если `lightrag-hku` не установлен: `pip install -e ".[lightrag]"` либо тест без установки — зависит от наличия extras в pyproject.toml.

---

### M5: Migration Gate & Explainability (TEST 9–10)

```text
Spec:       §2 — TEST 9 (migration_complete() = True), TEST 10 (нет фантомов)
Invariants: I-CTX-MIGRATION-1..4, I-SYSVAL-PHANTOM-1
Task:       T-5405
Depends:    M1 (NavigationResponse доступен)
Risks:      migration_complete() = False — фаза 52 не закрыта корректно (CRITICAL).
            Фантомные edge/doc → нарушение ContextAssembler.
```

---

### M6: DoD Verification (все 10 тестов)

```text
Spec:       §5 — DoD Phase 54 (12 пунктов)
Invariants: все I-SYSVAL-*, BC-36-7, I-PHASES-INDEX-1
Task:       T-5406
Depends:    M1, M2, M3, M4, M5 (все предыдущие вехи PASS)
Risks:      Любой непройденный тест блокирует COMPLETE.
            sdd validate-invariants --check I-PHASES-INDEX-1 MUST пройти.
```

---

## Risk Notes

- R-54-1: **Детерминизм** — diff в TEST 2 непустой → CRITICAL, нарушен I-GRAPH-DET-1/DET-3. Митигация: STOP → report-error → исследовать edge ordering в GraphBuilder.
- R-54-2: **Cache invalidation** — fingerprint не меняется при мутации файла → IndexBuilder.snapshot_hash сломан. Митигация: inspect hash calculation logic.
- R-54-3: **LightRAG опциональность** — ImportError или traceback при `rag_client=None` → нарушена модульность. Митигация: проверить импорты в rag_types.py и ContextRuntime.
- R-54-4: **rag-export не idempotent** — второй вызов пересоздаёт KG → нарушен I-RAG-EXPORT-FRESHNESS-1. Митигация: проверить LightRAGRegistry.has_kg().
- R-54-5: **Пустой граф** — nodes = [] при cold start → GraphService/extractors сломаны. Митигация: проверить ImplementsEdgeExtractor.
- R-54-6: **Путь к кэшу** — неверный путь в TEST 1 → кэш не удаляется, cold start не чистый. Митигация: уточнить реальную структуру `.sdd/runtime/` перед удалением.
