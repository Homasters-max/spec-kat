# Plan_v25 — Phase 25: Explicit DB Access & Test Isolation Hardening

Status: DRAFT
Spec: specs_draft/Spec_v25_ExplicitDBAccess.md

> ⚠️ Precondition note: Spec_v25 имеет статус DRAFT (не в specs/). Phase 24 ACTIVE
> (2/11 задач). Планирование выполнено по явному запросу. Активация Phase 25 невозможна
> до: (a) человек одобрит Spec_v25 → переместит в specs/, (b) Phase 24 завершена.

---

## Milestones

### M1: Core DB Hardening — `open_sdd_connection` explicit + fail-fast + guard

```text
Spec:       §2 Scope — BC-DB-1, BC-DB-2, BC-DB-3
            §3 Инварианты — I-DB-1, I-DB-TEST-1, I-DB-TEST-2
            §4 Контракты — open_sdd_connection новая сигнатура
            §5 Файлы — src/sdd/infra/db.py
Invariants: I-DB-1 (db_path обязательный), I-DB-TEST-1 (guard), I-DB-TEST-2 (fail-fast)
Depends:    —
Risks:      Breaking change: любой caller без db_path → TypeError.
            Анализ показал единственный нарушитель в production — metrics.py:116 (закрывается M2).
            Тесты: все используют :memory: или tmp_path явно — не затронуты.
```

Изменения в `src/sdd/infra/db.py`:
- Сигнатура: `db_path: str | None = None` → `db_path: str` (убрать Optional, убрать default)
- Удалить строки 66-67: `if db_path is None: db_path = str(event_store_file())`
- Удалить import `event_store_file` из `db.py` (строка 7)
- Добавить после сигнатуры: `if not db_path: raise ValueError("I-DB-1 violated: db_path must be explicit")`
- Добавить `PYTEST_CURRENT_TEST` fail-fast: `if os.getenv("PYTEST_CURRENT_TEST"): timeout_secs = 0.0`
- Добавить production DB guard (если `PYTEST_CURRENT_TEST` и path == prod): raise `RuntimeError`
- Добавить `import os` и `from pathlib import Path` в импорты

---

### M2: Metrics Dependency Injection

```text
Spec:       §2 Scope — BC-DB-4
            §4 Контракты — get_phase_metrics новая сигнатура
            §5 Файлы — src/sdd/infra/metrics.py + callers
Invariants: I-DB-1, I-DB-2
Depends:    M1
Risks:      Нужно найти все callers get_phase_metrics перед изменением сигнатуры.
            grep: `grep -rn "get_phase_metrics" src/ tests/`
            Если callers в CLI — они должны передать str(event_store_file()) явно.
```

Изменения в `src/sdd/infra/metrics.py`:
- Добавить `db_path: str` параметр к `get_phase_metrics()` (и всем другим функциям файла, если есть вызовы `open_sdd_connection()` без аргумента)
- Заменить `open_sdd_connection()` → `open_sdd_connection(db_path)`
- Удалить `from sdd.infra.paths import event_store_file` (или локальный import на строке 114)
- Обновить все callers: добавить `db_path=str(event_store_file())` в точке вызова (CLI-уровень)

---

### M3: Test Infrastructure — fixtures + timeout

```text
Spec:       §2 Scope — BC-DB-5, BC-DB-6
            §6 Тесты
Invariants: I-DB-TEST-1, I-DB-TEST-2
Depends:    M1 (guard проверяется тестами), M2 (metrics тестируется с db_path)
Risks:      _guard_production_db использует monkeypatch — function-scope fixture.
            Если какой-то тест имеет scope=session, потребуется отдельная обработка.
            pytest-timeout: --timeout=30 прервёт медленные integration тесты если есть.
```

Изменения в `tests/conftest.py`:
- Добавить `_reset_sdd_root` autouse fixture (вызывает `paths.reset_sdd_root()` до и после)
- Добавить `_guard_production_db` autouse fixture (monkeypatch duckdb.connect, Path.resolve() check)
- Добавить `sdd_home` opt-in fixture (tmp_path/.sdd, SDD_HOME, reset_sdd_root)

Изменения в `pyproject.toml`:
- Dev deps: добавить `"pytest-timeout>=4.0"`
- `addopts`: `"--tb=short"` → `"--tb=short --timeout=30"`

Новые тесты в `tests/unit/infra/test_db.py`:
- `test_db_path_required`: `open_sdd_connection("")` → `ValueError` (I-DB-1)
- `test_fail_fast_in_test_context`: mock `PYTEST_CURRENT_TEST`, locked file → немедленный `DuckDBLockTimeoutError` (I-DB-TEST-2)
- `test_production_db_guard`: `PYTEST_CURRENT_TEST` + production path → `RuntimeError` (I-DB-TEST-1)

Новые тесты в `tests/unit/infra/test_metrics.py` (или дополнение существующего):
- `test_get_phase_metrics_requires_db_path`: вызов без `db_path` → `TypeError`

---

### M4: Invariant Documentation — CLAUDE.md §INV

```text
Spec:       §3 Инварианты — I-DB-1, I-DB-2, I-DB-TEST-1, I-DB-TEST-2
            §2 Scope — BC-DB-7
Invariants: I-DB-1, I-DB-2, I-DB-TEST-1, I-DB-TEST-2
Depends:    M1, M2, M3 (документирует завершённые изменения)
Risks:      Нет риска. Только документация. Если M1-M3 не завершены — не применять.
```

Изменения в `CLAUDE.md §INV`:
- Добавить секцию "DB Access Invariants (Phase 25 — BC-25-DB)" после существующей таблицы
- Добавить строки:
  - `I-DB-1`: `open_sdd_connection(db_path)` — `db_path` MUST be explicit non-empty str; no implicit fallback
  - `I-DB-2`: CLI is the single point that resolves `event_store_file()` for default DB path; no other module may call it for connection defaults
  - `I-DB-TEST-1`: Tests MUST NOT open production DB; violation = immediate `RuntimeError` via Path.resolve() guard
  - `I-DB-TEST-2`: In test context (`PYTEST_CURRENT_TEST` set): `timeout_secs = 0.0`; fail-fast, no retry

---

## Risk Notes

- R-1: **Breaking change M1** — `open_sdd_connection` теряет default. Единственный
  затронутый production caller: `metrics.py:116` (закрывается M2 в той же фазе).
  Тесты не затронуты: все передают `":memory:"` или `tmp_path` явно.

- R-2: **Порядок M1 → M2** — если M1 применить без M2, production CLI (`sdd` команды
  использующие metrics) сломается. Оба milestone должны быть завершены до валидации.

- R-3: **pytest-timeout и integration тесты** — 30 секунд может оказаться недостаточно
  для медленных integration тестов. Если `pytest tests/ -q` показывает тесты > 15s —
  увеличить до 60s или добавить `@pytest.mark.timeout(60)` для конкретных тестов.

- R-4: **Spec_v25 не утверждён** — Phase 25 не может быть активирована пока:
  (a) Spec_v25 не перемещён из `specs_draft/` в `specs/` (human gate),
  (b) Phase 24 не завершена (MPS-2).
