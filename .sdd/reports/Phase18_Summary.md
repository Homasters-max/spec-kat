# Phase 18 Summary — SpatialIndex (BC-18)

Status: READY

---

## Tasks

| Task | Title | Status |
|------|-------|--------|
| T-1801 | Invariants §INV (I-NAV-1..9, I-CONTEXT-1, I-SI-1..5) | DONE |
| T-1802 | glossary.yaml — TERM-записи (≥8) | DONE |
| T-1803 | SpatialNode dataclass (nodes.py) | DONE |
| T-1804 | IndexBuilder + SpatialIndex (index.py) | DONE |
| T-1805 | StalenessChecker (staleness.py) | DONE |
| T-1806 | NavigationPolicy (navigator.py — Intent + Constraints) | DONE |
| T-1807 | NavigationSession (navigator.py — step tracking) | DONE |
| T-1808 | Navigator class (nav-get, search) | DONE |
| T-1809 | nav-get command | DONE |
| T-1810 | nav-search command | DONE |
| T-1811 | nav-rebuild command | DONE |
| T-1812 | nav-session command | DONE |
| T-1813 | Integration test nav-rebuild on real project root | DONE |

All 13/13 tasks DONE.

---

## Invariant Coverage

| Invariant | Задача | Status |
|-----------|--------|--------|
| I-NAV-1 | T-1801, T-1807 | PASS |
| I-NAV-2 | T-1801 | PASS |
| I-NAV-3 | T-1801, T-1807 | PASS |
| I-NAV-4 | T-1801, T-1810 | PASS |
| I-NAV-5 | T-1801, T-1807 | PASS |
| I-NAV-6 | T-1801, T-1807, T-1812 | PASS |
| I-NAV-7 | T-1806 | PASS |
| I-NAV-8 | T-1806 | PASS |
| I-NAV-9 | T-1807, T-1812 | PASS |
| I-SI-1 | T-1804, T-1813 | PASS |
| I-SI-2 | T-1808 | PASS |
| I-SI-3 | T-1808, T-1809 | PASS |
| I-SI-4 | T-1804, T-1813 | PASS |
| I-SI-5 | T-1804, T-1805 | PASS |
| I-DDD-0 | T-1802, T-1803 | PASS |
| I-DDD-1 | T-1803, T-1804 | PASS |
| I-TERM-1 | T-1811 | PASS |
| I-TERM-2 | T-1802, T-1811 | PASS |
| I-TERM-COVERAGE-1 | T-1811 | PASS |
| I-SUMMARY-1 | T-1803 | PASS |
| I-SUMMARY-2 | T-1803 | PASS |
| I-SIGNATURE-1 | T-1803 | PASS |
| I-FUZZY-1 | T-1808, T-1810 | PASS |
| I-SEARCH-2 | T-1808, T-1810 | PASS |
| I-GIT-OPTIONAL | T-1805, T-1813 | PASS |
| I-CONTEXT-1 | T-1801 | PASS |
| I-NAV-SESSION-1 | T-1809, T-1812 | PASS |
| I-SESSION-2 | T-1809, T-1812 | PASS |

---

## Spec Coverage

| Section | Coverage |
|---------|----------|
| §3 BC-18-0..BC-18-5 (node kinds, glossary, builder, commands) | covered |
| §7 M0..M6 (milestones) | covered |
| §9 Verification / Stabilization Criteria | covered (T-1813) |

---

## Tests

| Suite | Status |
|-------|--------|
| `tests/unit/spatial/test_nodes.py` | PASS |
| `tests/unit/spatial/test_index.py` | PASS |
| `tests/unit/spatial/test_staleness.py` | PASS |
| `tests/unit/spatial/test_navigation_policy.py` | PASS |
| `tests/unit/spatial/test_navigation_session.py` | PASS |
| `tests/unit/spatial/test_navigator.py` | PASS |
| `tests/unit/commands/test_nav_get.py` | PASS |
| `tests/unit/commands/test_nav_search.py` | PASS |
| `tests/unit/commands/test_nav_rebuild.py` | PASS |
| `tests/unit/commands/test_nav_session.py` | PASS |
| `tests/integration/test_nav_rebuild_integration.py` | PASS |

Инвариантный и тестовый статус: PASS.

---

## Metrics

См. [Metrics_Phase18.md](Metrics_Phase18.md).

Аномалий не обнаружено. Метрики тренда недоступны (Phase 18 — первая фаза с metrics-report в текущем формате).

---

## Key Decisions

- `TermNode` как отдельный класс отклонён (BUG-4): TERM-узлы реализованы через `SpatialNode(kind="TERM")` с дополнительными полями `definition`, `aliases`, `links`.
- `nav-rebuild` не регистрируется в `cli.py` в рамках Phase 18 (регистрация — следующая фаза); тест вызывает `run()` напрямую через Python API.
- `I-SI-4` проверяется через Python API `build_index()` дважды, а не через CLI (CLI без `nav-rebuild` в registry).

---

## Improvement Hypotheses

- Регистрация `nav-rebuild`, `nav-get`, `nav-search`, `nav-session` в `cli.py` — естественный следующий шаг (Phase 19).
- Тест `test_nav_rebuild_exit_zero` вызывает `run()` напрямую, т.к. CLI-маршрут не зарегистрирован. После регистрации тест можно переключить на `subprocess`.

---

## Decision

READY — все 13 задач DONE, все инварианты PASS, тесты PASS, аномалий нет.
