# TaskSet_v54 — Phase 54: Real System Validation

Spec: specs/Spec_v54_RealSystemValidation.md
Plan: plans/Plan_v54.md

---

T-5401: Cold Start, Determinism & Cache Correctness (TEST 1–3)

Status:               DONE
Spec ref:             Spec_v54 §2 — TEST 1 (Cold start), TEST 2 (Determinism), TEST 3 (Cache correctness)
Invariants:           I-SYSVAL-COLD-1, I-SYSVAL-DET-1, I-SYSVAL-CACHE-1, I-GRAPH-DET-1, I-GRAPH-DET-3
spec_refs:            [Spec_v54 §2 TEST 1, Spec_v54 §2 TEST 2, Spec_v54 §2 TEST 3, I-SYSVAL-COLD-1, I-SYSVAL-DET-1, I-SYSVAL-CACHE-1]
produces_invariants:  [I-SYSVAL-COLD-1, I-SYSVAL-DET-1, I-SYSVAL-CACHE-1]
requires_invariants:  [I-GRAPH-DET-1, I-GRAPH-DET-3]
Inputs:               .sdd/runtime/ (graph_cache/, lightrag_cache/),
                      src/sdd/ (CLI + GraphService + IndexBuilder + ContextEngine)
Outputs:              /tmp/r1.json (baseline result artifact),
                      .sdd/reports/ValidationReport_T5401.md
Acceptance:           TEST 1: exit 0, nodes > 0 в /tmp/r1.json;
                      TEST 2: diff /tmp/r1.json /tmp/r2.json = пустой;
                      TEST 3: diff /tmp/r1.json /tmp/r3.json = пустой.
                      При непустом diff в TEST 2 — STOP → sdd report-error (CRITICAL).
Depends on:           —

---

T-5402: Cache Invalidation — Mutation Probe (TEST 4)

Status:               DONE
Spec ref:             Spec_v54 §2 — TEST 4 (Mutation → rebuild)
Invariants:           I-SYSVAL-MUTATE-1
spec_refs:            [Spec_v54 §2 TEST 4, I-SYSVAL-MUTATE-1]
produces_invariants:  [I-SYSVAL-MUTATE-1]
requires_invariants:  [I-SYSVAL-COLD-1]
Inputs:               /tmp/r1.json (baseline fingerprint из T-5401),
                      src/sdd/commands/complete.py (мутируется и восстанавливается)
Outputs:              /tmp/r4.json (post-mutation result),
                      .sdd/reports/ValidationReport_T5402.md
Acceptance:           fingerprint в /tmp/r4.json ≠ fingerprint в /tmp/r1.json;
                      src/sdd/commands/complete.py восстановлен (git checkout) после теста.
                      Идентичный fingerprint = FAIL → sdd report-error.
Depends on:           T-5401

---

T-5403: CLI Full Cycle & Error Model (TEST 5–6)

Status:               DONE
Spec ref:             Spec_v54 §2 — TEST 5 (CLI полный цикл, BC-36-7), TEST 6 (Error model)
Invariants:           BC-36-7, I-SYSVAL-ERROR-1, I-CLI-FORMAT-1, I-CLI-ERROR-CODES-1
spec_refs:            [Spec_v54 §2 TEST 5, Spec_v54 §2 TEST 6, BC-36-7, I-SYSVAL-ERROR-1, I-CLI-ERROR-CODES-1]
produces_invariants:  [I-SYSVAL-ERROR-1]
requires_invariants:  [I-SYSVAL-COLD-1, BC-36-7]
Inputs:               src/sdd/ (CLI: resolve, explain, trace, invariant команды)
Outputs:              .sdd/reports/ValidationReport_T5403.md
Acceptance:           TEST 5: все 4 команды (resolve, explain, trace, invariant) — exit 0, без traceback;
                      TEST 6: sdd explain COMMAND:unknown → exit ≠ 0,
                              stdout содержит {"error_type": "NOT_FOUND"}, traceback отсутствует.
Depends on:           T-5401

---

T-5404: LightRAG Optional & Export Idempotency (TEST 7–8)

Status:               DONE
Spec ref:             Spec_v54 §2 — TEST 7 (без LightRAG), TEST 8 (rag-export idempotency)
Invariants:           I-SYSVAL-RAG-OPTIONAL-1, I-SYSVAL-IDEM-1, I-RAG-DEGRADE-LOCAL-1, I-RAG-EXPORT-FRESHNESS-1
spec_refs:            [Spec_v54 §2 TEST 7, Spec_v54 §2 TEST 8, I-SYSVAL-RAG-OPTIONAL-1, I-SYSVAL-IDEM-1]
produces_invariants:  [I-SYSVAL-RAG-OPTIONAL-1, I-SYSVAL-IDEM-1]
requires_invariants:  [I-RAG-DEGRADE-LOCAL-1, I-RAG-EXPORT-FRESHNESS-1]
Inputs:               src/sdd/context_kernel/rag_types.py,
                      src/sdd/context_kernel/runtime.py (ContextRuntime),
                      pyproject.toml (lightrag extras — при необходимости),
                      .sdd/runtime/lightrag_cache/ (KG store)
Outputs:              .sdd/reports/ValidationReport_T5404.md
Acceptance:           TEST 7: ContextRuntime(LightRAGProjection()) — rag_summary=null, exit 0, нет ImportError;
                      TEST 8: второй вызов sdd rag-export = no-op (KG не пересоздаётся).
                      Если lightrag-hku не установлен: уточнить наличие extras в pyproject.toml.
Depends on:           T-5401

---

T-5405: Migration Gate & Explainability (TEST 9–10)

Status:               DONE
Spec ref:             Spec_v54 §2 — TEST 9 (migration_complete() = True), TEST 10 (нет фантомов)
Invariants:           I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4, I-SYSVAL-PHANTOM-1
spec_refs:            [Spec_v54 §2 TEST 9, Spec_v54 §2 TEST 10, I-CTX-MIGRATION-1, I-SYSVAL-PHANTOM-1]
produces_invariants:  [I-SYSVAL-PHANTOM-1]
requires_invariants:  [I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4]
Inputs:               src/sdd/graph_navigation/migration.py (migration_complete()),
                      /tmp/r1.json (NavigationResponse для проверки фантомов)
Outputs:              .sdd/reports/ValidationReport_T5405.md
Acceptance:           TEST 9: migration_complete() is True (иначе CRITICAL → STOP);
                      TEST 10: все edge.src, edge.dst ∈ nodes; все doc.node_id ∈ nodes;
                               nodes, edges, docs — непустые коллекции.
Depends on:           T-5401

---

T-5406: DoD Verification — All Tests & Invariants

Status:               DONE
Spec ref:             Spec_v54 §5 — DoD Phase 54 (12 пунктов)
Invariants:           I-SYSVAL-COLD-1, I-SYSVAL-DET-1, I-SYSVAL-CACHE-1, I-SYSVAL-MUTATE-1,
                      I-SYSVAL-ERROR-1, I-SYSVAL-RAG-OPTIONAL-1, I-SYSVAL-IDEM-1, I-SYSVAL-PHANTOM-1,
                      BC-36-7, I-PHASES-INDEX-1
spec_refs:            [Spec_v54 §5, все I-SYSVAL-*]
produces_invariants:  [I-SYSVAL-COLD-1, I-SYSVAL-DET-1, I-SYSVAL-CACHE-1, I-SYSVAL-MUTATE-1,
                       I-SYSVAL-ERROR-1, I-SYSVAL-RAG-OPTIONAL-1, I-SYSVAL-IDEM-1, I-SYSVAL-PHANTOM-1]
requires_invariants:  [I-SYSVAL-COLD-1, I-SYSVAL-DET-1, I-SYSVAL-CACHE-1, I-SYSVAL-MUTATE-1,
                       I-SYSVAL-ERROR-1, I-SYSVAL-RAG-OPTIONAL-1, I-SYSVAL-IDEM-1, I-SYSVAL-PHANTOM-1,
                       I-CTX-MIGRATION-1, I-CTX-MIGRATION-2, I-CTX-MIGRATION-3, I-CTX-MIGRATION-4,
                       I-PHASES-INDEX-1]
Inputs:               .sdd/reports/ValidationReport_T5401.md,
                      .sdd/reports/ValidationReport_T5402.md,
                      .sdd/reports/ValidationReport_T5403.md,
                      .sdd/reports/ValidationReport_T5404.md,
                      .sdd/reports/ValidationReport_T5405.md
Outputs:              .sdd/reports/ValidationReport_Phase54_DoD.md
Acceptance:           Все 12 пунктов DoD = PASS;
                      sdd validate-invariants --phase 54 --check I-PHASES-INDEX-1 = exit 0;
                      Ни одного непройденного пункта (любой FAIL блокирует COMPLETE).
Depends on:           T-5401, T-5402, T-5403, T-5404, T-5405

---

<!-- Granularity: 6 tasks (TG-2: 10–30 recommended — фаза является валидационной, 6 задач соответствуют 6 вехам плана). -->
<!-- Every task is independently runnable and independently testable (TG-1). -->
