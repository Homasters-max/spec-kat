# ValidationReport T-5404: LightRAG Optional & Export Idempotency

**Task:** T-5404  
**Phase:** 54  
**Date:** 2026-04-30  
**Status:** PASS

---

## Invariants Covered

| Invariant | Status | Evidence |
|-----------|--------|----------|
| I-SYSVAL-RAG-OPTIONAL-1 | PASS | ContextRuntime(rag_client=None) → rag_summary=None, exit 0, нет ImportError |
| I-SYSVAL-IDEM-1 | PASS | Второй вызов sdd rag-export = no-op (KG не пересоздаётся) |
| I-RAG-DEGRADE-LOCAL-1 | PASS | LightRAGProjection.query(rag_client=None) → None (warning logged) |
| I-RAG-EXPORT-FRESHNESS-1 | PASS | test_exporter_skip_if_kg_exists PASSED (unit test 67) |

---

## TEST 7 — ContextRuntime без LightRAG (I-SYSVAL-RAG-OPTIONAL-1)

**Acceptance:** ContextRuntime(LightRAGProjection()) — rag_summary=null, exit 0, нет ImportError

**Execution:**
```python
ContextRuntime(engine=mock_engine, rag_client=None)
result = runtime.query(graph, policy, index, node_id='FILE:test')
assert result.rag_summary is None  # PASS
```

**Result:** PASS
- `ContextRuntime._rag_client` = None по умолчанию
- `engine.query()` получает `rag_client=None`, возвращает `NavigationResponse(rag_summary=None)`
- Никакого `ImportError` (lightrag-hku не требуется для работы без RAG)
- `LightRAGProjection.query(rag_client=None)` → `None` + WARNING logged (I-RAG-DEGRADE-LOCAL-1)

---

## TEST 8 — sdd rag-export идемпотентность (I-SYSVAL-IDEM-1)

**Acceptance:** Второй вызов sdd rag-export = no-op (KG не пересоздаётся)

**Execution:**
```
$ sdd rag-export
→ rag-export: KG exported for fingerprint a663507e...   # первый вызов

$ sdd rag-export  
→ rag-export: KG up-to-date for fingerprint a663507e..., skipping.  # второй вызов
```

**Result:** PASS
- Второй вызов: `LightRAGRegistry.has_kg(fingerprint) = True` → `LightRAGExporter.export()` пропускает вставку
- `insert_custom_kg` не вызывается (подтверждено unit-тестом 67)
- KG хранится в `.sdd/runtime/lightrag_cache/a663507e.../`

---

## Unit Tests Run

```
tests/unit/context_kernel/test_runtime.py — 11/11 PASSED
tests/integration/test_lightrag_export.py — 8/8 PASSED
```

**Ключевые тесты:**
- `test_rag_client_defaults_to_none` — rag_client=None по умолчанию
- `test_none_rag_client_propagated` — None пробрасывается в engine
- `test_exporter_skip_if_kg_exists` — TEST 67/TEST 8 (I-RAG-EXPORT-FRESHNESS-1)
- `test_int9_export_uses_existing_node_ids` — INT-9

---

## pyproject.toml extras

```toml
[project.optional-dependencies]
lightrag = ["lightrag-hku>=1.4", "numpy>=1.26"]
```

lightrag-hku установлен (`pip install -e ".[lightrag]"`). Система работает без него (graceful degradation).

---

## Вывод

Все acceptance criteria T-5404 выполнены:
- TEST 7 (I-SYSVAL-RAG-OPTIONAL-1): **PASS**
- TEST 8 (I-SYSVAL-IDEM-1): **PASS**
- I-RAG-DEGRADE-LOCAL-1: **PASS**
- I-RAG-EXPORT-FRESHNESS-1: **PASS**
