# Phase 53 Summary — Graph-Based Test Filtering

Status: READY

---

## Tasks

| Task | Status | Описание |
|------|--------|----------|
| T-5301 | DONE | Добавить `"TEST"` в `VALID_KINDS` (nodes.py) |
| T-5302 | DONE | IndexBuilder: скан TEST-узлов из `tests/unit/` и `tests/integration/` |
| T-5303 | DONE | `TestedByEdgeExtractor` — filename convention, нет AST-эвристик |
| T-5304 | DONE | Регистрация `TestedByEdgeExtractor` в `GraphBuilder` |
| T-5305 | DONE | `sdd test-filter` CLI handler (BFS + fallback) |
| T-5306 | DONE | Регистрация `sdd test-filter` в `cli.py` + ключ `test_filter` в `project_profile.yaml` |
| T-5307 | DONE | Тесты `TestedByEdgeExtractor` (4 unit-теста) |
| T-5308 | DONE | Тесты `sdd test-filter` CLI handler (2 unit-теста) |

Итого: 8/8 DONE.

---

## Invariant Coverage

| Инвариант | Статус | Покрывает задача(и) |
|-----------|--------|---------------------|
| I-TEST-NODE-1 | PASS | T-5301 |
| I-TEST-NODE-2 | PASS | T-5301, T-5302 |
| I-TEST-NODE-3 | PASS | T-5301, T-5307 |
| I-GRAPH-TESTED-BY-1 | PASS | T-5303, T-5304, T-5307 |
| I-GRAPH-TESTED-BY-2 | PASS | T-5303, T-5307 |
| I-GRAPH-EXTRACTOR-2 | PASS | T-5303 |
| I-GRAPH-FINGERPRINT-1 | PASS | T-5303 |
| I-TEST-FILTER-1 | PASS | T-5305, T-5308 |
| I-TEST-FILTER-2 | PASS | T-5306 |
| I-TASK-MODE-1 | PASS | T-5306 |
| I-DB-TEST-1 | PASS | T-5307, T-5308 |

---

## Spec Coverage (Spec_v53)

| Секция | Покрытие |
|--------|----------|
| §1 Новый node kind TEST | covered — T-5301, T-5302 |
| §2 TestedByEdgeExtractor | covered — T-5303, T-5304 |
| §3 sdd test-filter CLI | covered — T-5305, T-5306 |
| §4 Инварианты | covered — все 11 инвариантов PASS |
| §5 Scope & Dependencies | covered — новые файлы созданы, изменяемые файлы обновлены |
| §6 Verification | covered — все 6 тестов PASS |
| §7 Tier-иерархия | covered — `test_filter` tier зарегистрирован |

---

## Tests

| Тест | Инвариант | Статус |
|------|-----------|--------|
| `test_test_node_kind_not_file` | I-TEST-NODE-3 | PASS |
| `test_tested_by_edges_filename_convention` | I-GRAPH-TESTED-BY-1 | PASS |
| `test_tested_by_no_phantom_edges` | I-GRAPH-TESTED-BY-2 | PASS |
| `test_tested_by_no_ast_heuristics` | I-GRAPH-TESTED-BY-1 | PASS |
| `test_test_filter_runs_targeted_pytest` | I-TEST-FILTER-1 | PASS |
| `test_test_filter_fallback_when_no_edges` | I-TEST-FILTER-1 | PASS |

Все 6 новых тестов PASS. Существующие тесты не сломаны (TP-1).

---

## Key Decisions

- **Filename convention only** (I-GRAPH-TESTED-BY-1): детерминированный маппинг без AST. Упрощает экстрактор и гарантирует воспроизводимость рёбер.
- **Двойные рёбра** (COMMAND + FILE → TEST): `sdd explain` работает для обоих видов узлов.
- **Fallback не ошибка** (I-TEST-FILTER-1): ноль `tested_by` рёбер — предупреждение в stderr + переход к tier-команде. Обратная совместимость с незаиндексированными компонентами.
- **I-TASK-MODE-1 compliance**: ключ `test_filter` начинается с `test` → автоматически исключается из task mode build_commands.

---

## Metrics

→ См. [Metrics_Phase53.md](Metrics_Phase53.md)

---

## Anomalies & Improvement Hypotheses

- **Lint fix in VALIDATE**: в T-5308 потребовалась мелкая правка (`_src` вместо `src`) — признак недостаточной pre-commit проверки в IMPLEMENT-loop. Гипотеза: добавить `ruff check` в `test_fast` или как отдельный хук.
- **Нет ValidationReport файлов по задачам**: `validate-invariants` не генерирует `ValidationReport_T-NNN.md` — только запускает проверки. Гипотеза: добавить явный output-артефакт в `validate-invariants`.

---

## Decision

READY

Все 8 задач DONE, все 11 инвариантов PASS, 6 новых тестов PASS. Граф теперь эмитирует `tested_by` рёбра; `sdd test-filter` готов к использованию в VALIDATE-сессиях.
