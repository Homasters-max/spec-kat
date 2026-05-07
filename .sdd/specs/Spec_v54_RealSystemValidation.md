# Spec_v54 — Phase 54: Real System Validation

**Status:** Draft
**Supersedes:** —
**Baseline:** Phase 52 DoD полностью выполнен (15/15 задач, 14/14 пунктов DoD)
**Depends on:** Phase 52 COMPLETE
**Session:** DRAFT_SPEC 2026-04-29 — испытание системы как целого

**Цель:** Убедиться, что система Phase 52 реально работает end-to-end — не только проходит тесты, но детерминирована, устойчива к реальным сценариям и пригодна для использования агентами.

**Отличие от DoD Phase 52:** DoD = "код правилен". Phase 54 = "система живёт".

---

## 0. Что проверяется

```text
код → SpatialIndex → Graph → ContextEngine → CLI → JSON → LLM-tool
```

Гарантии:

| Свойство | Проверка |
|----------|----------|
| Детерминизм | идентичный вывод при повторном запуске |
| Cache correctness | cache hit не меняет результат |
| Cache invalidation | мутация файла → rebuild |
| CLI coverage | все 4 команды BC-36-7 работают |
| Error model | структурированные ошибки, не traceback |
| Optional dependency | система работает без LightRAG |
| Idempotency | rag-export второй раз = no-op |
| Migration gate | migration_complete() = True |
| Explainability | nodes/edges/docs не пустые, нет фантомов |

---

## 1. Инварианты Phase 54

**I-SYSVAL-COLD-1:** Первый запуск после удаления кэша MUST успешно построить граф (`nodes > 0`) и вернуть валидный `NavigationResponse`.

**I-SYSVAL-DET-1:** Два последовательных вызова `sdd explain COMMAND:complete --format json` MUST производить побайтово идентичный вывод. Нарушение = CRITICAL (нарушен I-GRAPH-DET-1/DET-3).

**I-SYSVAL-CACHE-1:** Cache hit MUST производить результат, идентичный cold-start. Fingerprint MUST совпадать.

**I-SYSVAL-MUTATE-1:** Изменение любого исходного файла MUST изменить `graph_fingerprint` в следующем запросе. Неизменённый fingerprint = нарушение cache invalidation.

**I-SYSVAL-ERROR-1:** Неизвестный `node_id` MUST возвращать `error_type = "NOT_FOUND"` и exit code ≠ 0. Traceback в stdout MUST NOT появляться.

**I-SYSVAL-RAG-OPTIONAL-1:** Система MUST работать при `rag_client=None` (LightRAG не установлен). `rag_summary` = null, остальные поля валидны.

**I-SYSVAL-IDEM-1:** `sdd rag-export` второй раз MUST быть no-op (I-RAG-EXPORT-FRESHNESS-1). KG создаётся один раз.

**I-SYSVAL-PHANTOM-1:** В `NavigationResponse`: все `edge.src` и `edge.dst` MUST быть в `nodes`. Все `document.node_id` MUST быть в `nodes`. Фантомные ссылки = нарушение ContextAssembler.

---

## 2. Сценарные тесты (TEST 1–10)

### TEST 1 — Cold start

```bash
rm -rf .sdd/runtime/lightrag_cache .sdd/runtime/graph_cache
sdd explain COMMAND:complete --format json
```

**Ожидание:** exit 0, `nodes > 0`, нет исключений.
**Инварианты:** I-SYSVAL-COLD-1.
**Проверяет:** GraphService + IndexBuilder + ContextEngine pipeline.

> ⚠️ MUST NOT удалять `.sdd/runtime/sdd_events.duckdb` (EventStore, I-1).
> Удалять только кэш: `lightrag_cache/`, `graph_cache/` (имена уточнить по реальной структуре runtime/).

---

### TEST 2 — Determinism

```bash
sdd explain COMMAND:complete --format json > /tmp/r1.json
sdd explain COMMAND:complete --format json > /tmp/r2.json
diff /tmp/r1.json /tmp/r2.json
```

**Ожидание:** пустой diff.
**Инварианты:** I-SYSVAL-DET-1, I-GRAPH-DET-1, I-GRAPH-DET-3.
**Если diff есть:** STOP → `sdd report-error --type INVARIANT_VIOLATION --message "non-deterministic output"`.

---

### TEST 3 — Cache correctness

```bash
sdd explain COMMAND:complete --format json > /tmp/r3.json
diff /tmp/r1.json /tmp/r3.json
```

**Ожидание:** пустой diff (результат идентичен r1.json).
**Инварианты:** I-SYSVAL-CACHE-1.

---

### TEST 4 — Mutation → rebuild

```bash
echo "# probe" >> src/sdd/commands/complete.py

sdd explain COMMAND:complete --format json > /tmp/r4.json

python3 -c "
import json
r1 = json.load(open('/tmp/r1.json'))
r4 = json.load(open('/tmp/r4.json'))
h1 = r1.get('debug', {}).get('graph_fingerprint') or r1.get('graph_fingerprint')
h4 = r4.get('debug', {}).get('graph_fingerprint') or r4.get('graph_fingerprint')
print(f'r1 fingerprint: {h1}')
print(f'r4 fingerprint: {h4}')
assert h1 != h4, 'FAIL: fingerprint не изменился после мутации'
print('OK: cache miss + rebuild')
"

git checkout src/sdd/commands/complete.py
```

**Ожидание:** fingerprint изменился, граф пересобрался.
**Инварианты:** I-SYSVAL-MUTATE-1.

---

### TEST 5 — CLI полный цикл (BC-36-7)

```bash
sdd resolve "complete task" --format json
sdd explain COMMAND:complete --format text
sdd trace FILE:src/sdd/commands/complete.py --format json
sdd invariant I-HANDLER-PURE-1 --format json
```

**Ожидание:** все 4 команды exit 0, без traceback.
**Инварианты:** BC-36-7, I-CLI-FORMAT-1.

---

### TEST 6 — Error model

```bash
sdd explain COMMAND:unknown --format json
echo "exit=$?"
```

**Ожидание:** exit ≠ 0, `{"error_type": "NOT_FOUND", ...}` на stderr, никакого traceback.
**Инварианты:** I-SYSVAL-ERROR-1, I-CLI-ERROR-CODES-1.

---

### TEST 7 — Без LightRAG

```bash
python3 -c "
from sdd.context_kernel.runtime import ContextRuntime
from sdd.context_kernel.rag_types import LightRAGProjection
rt = ContextRuntime(LightRAGProjection())
print('OK: graceful degradation, rag_client=None')
"
sdd explain COMMAND:complete --format json
```

**Ожидание:** `rag_summary = null`, остальные поля валидны, exit 0.
**Инварианты:** I-SYSVAL-RAG-OPTIONAL-1, I-RAG-DEGRADE-LOCAL-1.

---

### TEST 8 — LightRAG export idempotency

```bash
sdd rag-export
sdd rag-export
```

**Ожидание:** второй вызов = no-op (KG уже существует).
**Инварианты:** I-SYSVAL-IDEM-1, I-RAG-EXPORT-FRESHNESS-1.

> Если `lightrag-hku` не установлен, установить: `pip install -e ".[lightrag]"` (после добавления в `pyproject.toml` extras).
> Если lightrag недоступен — команда MUST завершиться понятной ошибкой, не traceback.

---

### TEST 9 — Migration hard gate

```bash
python3 -c "
from sdd.graph_navigation.migration import migration_complete
result = migration_complete()
print(f'migration_complete() = {result}')
assert result is True, 'FAIL: hard gate не пройден'
"
```

**Ожидание:** `True`.
**Инварианты:** I-CTX-MIGRATION-1..4.

---

### TEST 10 — Explainability (нет фантомов)

```bash
sdd explain COMMAND:complete --format json | python3 -c "
import sys, json
d = json.load(sys.stdin)
nodes = d.get('nodes', [])
edges = d.get('edges', [])
docs  = d.get('documents', [])
assert nodes, 'FAIL: nodes пустые'
assert edges, 'FAIL: edges пустые'
assert docs,  'FAIL: documents пустые'
node_ids = {n['node_id'] for n in nodes}
for e in edges:
    assert e['src'] in node_ids, f'фантомный src: {e[\"src\"]}'
    assert e['dst'] in node_ids, f'фантомный dst: {e[\"dst\"]}'
for doc in docs:
    assert doc.get('node_id') in node_ids, f'фантомный doc node_id: {doc.get(\"node_id\")}'
print(f'OK: {len(nodes)} nodes, {len(edges)} edges, {len(docs)} docs — всё трассируемо')
"
```

**Ожидание:** нет фантомных ссылок, все коллекции непустые.
**Инварианты:** I-SYSVAL-PHANTOM-1.

---

## 3. Структура задач (предварительная декомпозиция)

| ID | Задача | Тесты |
|----|--------|-------|
| T-5401 | Cold start + determinism (TEST 1, 2, 3) | I-SYSVAL-COLD-1, I-SYSVAL-DET-1, I-SYSVAL-CACHE-1 |
| T-5402 | Cache invalidation + mutation test (TEST 4) | I-SYSVAL-MUTATE-1 |
| T-5403 | CLI полный цикл + error model (TEST 5, 6) | BC-36-7, I-SYSVAL-ERROR-1 |
| T-5404 | LightRAG optional + rag-export idempotency (TEST 7, 8) | I-SYSVAL-RAG-OPTIONAL-1, I-SYSVAL-IDEM-1 |
| T-5405 | Migration gate + explainability (TEST 9, 10) | I-CTX-MIGRATION-1..4, I-SYSVAL-PHANTOM-1 |
| T-5406 | DoD verification (все 10 тестов + инварианты) | все I-SYSVAL-* |

---

## 4. Риски

| ID | Риск | Следствие | Митигация |
|----|------|-----------|-----------|
| R-54-1 | diff в TEST 2 | нарушен детерминизм (CRITICAL) | STOP → report-error, исследовать edge ordering |
| R-54-2 | нет rebuild в TEST 4 | сломан fingerprint/cache | проверить IndexBuilder.snapshot_hash |
| R-54-3 | падение без LightRAG | нарушена модульность | проверить импорты в rag_types.py |
| R-54-4 | rag-export не idempotent | утечка состояния KG | проверить LightRAGRegistry.has_kg() |
| R-54-5 | explain пустой | graph extraction сломан | проверить ImplementsEdgeExtractor |
| R-54-6 | путь к кэшу в TEST 1 неверный | не чистится нужная директория | уточнить структуру .sdd/runtime/ |

---

## 5. DoD Phase 54

```
[ ] TEST 1: cold start — nodes > 0, exit 0
[ ] TEST 2: determinism — diff = ∅
[ ] TEST 3: cache — результат идентичен cold-start
[ ] TEST 4: mutation → fingerprint изменился
[ ] TEST 5: все 4 CLI команды — exit 0
[ ] TEST 6: unknown node → NOT_FOUND, нет traceback
[ ] TEST 7: без LightRAG — система работает
[ ] TEST 8: rag-export второй раз — no-op
[ ] TEST 9: migration_complete() = True
[ ] TEST 10: нет фантомных ссылок в NavigationResponse
[ ] все I-SYSVAL-* инварианты подтверждены
[ ] sdd validate-invariants --check I-PHASES-INDEX-1 PASS
```
