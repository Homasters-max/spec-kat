# ValidationReport T-5403 — CLI полный цикл + Error model

**Task:** T-5403  
**Phase:** 54  
**Date:** 2026-04-30  
**Result:** PASS

---

## Invariants Covered

- BC-36-7 — все 4 команды работают
- I-SYSVAL-ERROR-1 — неизвестный node → NOT_FOUND, exit ≠ 0, нет traceback
- I-CLI-FORMAT-1 — JSON/text вывод корректен
- I-CLI-ERROR-CODES-1 — структурированные ошибки

---

## TEST 5 — CLI полный цикл (BC-36-7)

| Команда | Exit | Результат |
|---------|------|-----------|
| `sdd resolve "complete task" --format json` | 0 | PASS — 9 кандидатов найдено BM25 |
| `sdd explain COMMAND:complete --format text` | 0 | PASS — 2 nodes, 1 edge (TRACE fallback) |
| `sdd trace FILE:src/sdd/commands/complete.py --format json` | 0 | PASS — 1 node |
| `sdd invariant I-HANDLER-PURE-1 --format json` | 0 | PASS — 1 node |

**Итог TEST 5: PASS** — все 4 команды exit 0, без traceback.

---

## TEST 6 — Error model

```bash
sdd explain COMMAND:unknown --format json
exit=1
{"error_type": "NOT_FOUND", "message": "Node not found: 'COMMAND:unknown'"}
```

**Итог TEST 6: PASS** — exit=1, структурированный `NOT_FOUND`, нет traceback.

---

## Что было исправлено

**Баг в `resolve.py`** (Phase 51 limitation): `ContextRuntime.query()` не передавал параметр `intent` в `ContextEngine.query()`, из-за чего BM25-поиск не запускался (движок всегда использовал RESOLVE_EXACT). В результате `sdd resolve` всегда возвращал exit=1 с NOT_FOUND для любого свободного текста.

**Фикс**: применён тот же паттерн, что уже использован в `trace.py` и `explain.py` — вызов `runtime._doc_provider_factory(index)` + прямой вызов `engine.query(..., intent=intent)`.

**Измененный файл:** `src/sdd/graph_navigation/cli/resolve.py`

---

## Тесты

```
tests/unit/graph_navigation/ + tests/integration/test_graph_navigation_cli.py
17 passed, 3 warnings
```

TP-1: все существующие тесты прошли без изменений.
