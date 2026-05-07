# Spec_v25_ExplicitDBAccess — Explicit DB Access & Test Isolation Hardening

Status: DRAFT
Baseline: Spec_v24_PhaseContextSwitch.md

---

## 0. Goal

Фазы 18–24 выявили системную проблему: `open_sdd_connection(db_path=None)` молча
открывает production базу данных. Если та заблокирована — pytest зависает в состоянии
`D` (uninterruptible kernel sleep). Это происходит повторно, поскольку корень не устранён.

Архитектурный принцип, нарушённый сейчас:

```
DB access MUST be: explicit / stateless / isolated / fail-fast
```

Конкретные нарушения:

```
implicit  := open_sdd_connection(db_path=None) резолвит production path самостоятельно
stateful  := _sdd_root глобальный кэш не сбрасывается между тестами
shared    := тесты могут открыть production DB если _sdd_root не очищен
blocking  := retry-loop (10s) не знает о тестовом контексте → D-state на 10 секунд
```

Данная спецификация вводит инвариант I-DB-1 и закрывает все связанные дефекты.

---

## 1. Диагностика дефектов

### D-1 — Implicit production DB access

`open_sdd_connection(db_path=None)` в `src/sdd/infra/db.py:66-67`:

```python
if db_path is None:
    db_path = str(event_store_file())   # открывает /root/project/.sdd/state/sdd_events.duckdb
```

Любой caller, не передавший `db_path`, открывает production базу.
Нарушает принцип explicit access.

### D-2 — Единственный нарушитель в production коде

`src/sdd/infra/metrics.py:116`:

```python
conn = open_sdd_connection()   # db_path не передан
```

Все остальные callers в `src/` передают `db_path` явно. `metrics.py` — единственное
исключение. Причина: функция знает про `paths`, что нарушает слоёвку (infra/metrics
не должна зависеть от infra/paths напрямую).

### D-3 — `_sdd_root` глобальный кэш не сбрасывается между тестами

`src/sdd/infra/paths.py:4`:

```python
_sdd_root: Path | None = None   # module-level global, кэшируется навсегда
```

Функция `reset_sdd_root()` существует, но нет `autouse` фикстуры в `tests/conftest.py`
которая её вызывает. Результат: первый тест, вызвавший `get_sdd_root()` без `SDD_HOME`,
кэширует `/root/project/.sdd`. Все последующие тесты, вызывающие `open_sdd_connection(None)`
(явно или через D-1), откроют production DB.

### D-4 — Retry-loop не знает о тестовом контексте

`open_sdd_connection` ретраится до `timeout_secs=10.0` при lock ошибке:

```python
deadline = time.monotonic() + timeout_secs
while True:
    try:
        conn = duckdb.connect(db_path)   # может войти в D-state здесь
```

В тестовом контексте (`PYTEST_CURRENT_TEST` set) это не нужно:
- тесты используют `tmp_path` — lock contention невозможен в нормальной ситуации
- если lock есть — это симптом проблемы (D-1 или D-3), нужно fail-fast, не retry

### D-5 — Нет timeout на тест

`pyproject.toml` не содержит `--timeout`, `pytest-timeout` не в зависимостях.
Зависший тест = pytest висит бесконечно без диагностики. `kill -9` вручную.

---

## 2. Scope

### In-Scope

- **BC-DB-1: `open_sdd_connection` — `db_path` обязательный** — убрать `Optional[str]`,
  убрать implicit path resolution, убрать import `event_store_file` из `db.py`.
  Добавить I-DB-1 enforcement: `if not db_path: raise ValueError("I-DB-1 violated")`.

- **BC-DB-2: Fail-fast в тестах** — в `open_sdd_connection`, если `PYTEST_CURRENT_TEST`
  env var выставлен (pytest устанавливает автоматически), форсировать `timeout_secs = 0.0`.
  Результат: lock error = немедленный fail теста вместо 10-секундного зависания.

- **BC-DB-3: Production DB guard в `open_sdd_connection`** — если `PYTEST_CURRENT_TEST`
  и `Path(db_path).resolve() == prod_db_path`, raise `RuntimeError` немедленно.
  Belt-and-suspenders к BC-DB-5 guard на уровне тестов.

- **BC-DB-4: `metrics.py` — Dependency Injection** — добавить `db_path: str` параметр
  к `get_phase_metrics()`. Убрать прямой вызов `event_store_file()` из `metrics.py`.
  Все callers передают `db_path` явно. `metrics.py` больше не импортирует `paths`.

- **BC-DB-5: `tests/conftest.py` — три фикстуры**:
  - `_reset_sdd_root` (autouse): вызывает `paths.reset_sdd_root()` до и после каждого теста
  - `_guard_production_db` (autouse): `monkeypatch(duckdb.connect, guarded)` где guarded
    проверяет `Path(db_path).resolve() == prod_db` через `Path.resolve()` (не string match)
  - `sdd_home` (opt-in): изолирует `SDD_HOME` в `tmp_path` для интеграционных тестов,
    вызывает `reset_sdd_root()` явно

- **BC-DB-6: `pyproject.toml`** — добавить `pytest-timeout>=4.0` в dev deps,
  добавить `--timeout=30` в `addopts`.

- **BC-DB-7: Invariants** — добавить в CLAUDE.md §INV:
  - I-DB-1: `db_path` MUST be explicit in all `open_sdd_connection()` calls outside CLI
  - I-DB-2: CLI is the single point that calls `event_store_file()` for the default DB path
  - I-DB-TEST-1: Tests MUST NOT open production DB; violation = immediate RuntimeError
  - I-DB-TEST-2: `PYTEST_CURRENT_TEST` triggers fail-fast mode (timeout_secs = 0)

### Out of Scope

- Переход на connection pooling — отдельная фаза если потребуется
- Изменение `timeout_secs` для production code — текущее значение (10s) корректно
- `autouse` для `sdd_home` фикстуры — opt-in достаточен; принудительный SDD_HOME
  в unit тестах создаёт лишние директории без пользы
- Изменение поведения `sdd_append` / `sdd_replay` — они уже принимают `db_path` явно

---

## 3. Инварианты (новые, BC-DB-7)

| ID | Statement |
|----|-----------|
| I-DB-1 | `open_sdd_connection(db_path)` — `db_path` MUST be explicit non-empty str |
| I-DB-2 | CLI is the single point that resolves `event_store_file()` for default DB path |
| I-DB-TEST-1 | Tests MUST NOT open production DB; path equality via `Path.resolve()` |
| I-DB-TEST-2 | In test context (`PYTEST_CURRENT_TEST`): `timeout_secs = 0.0` (fail-fast) |

---

## 4. Контракты изменённых интерфейсов

### `open_sdd_connection` (после BC-DB-1..3)

```python
def open_sdd_connection(
    db_path: str,            # обязательный (было: str | None = None)
    timeout_secs: float = 10.0,
) -> duckdb.DuckDBPyConnection:
    ...
```

Breaking change: callers без `db_path` получат `TypeError` при вызове.
Но единственный такой caller в production — `metrics.py` (D-2), закрывается BC-DB-4.

### `get_phase_metrics` (после BC-DB-4)

```python
def get_phase_metrics(
    metric_ids: list[str],
    window: int = 3,
    db_path: str = ...,     # новый обязательный параметр
) -> list[PhaseMetricRow]:
    ...
```

---

## 5. Файлы для изменения

| Файл | BC | Изменение |
|------|----|-----------|
| `src/sdd/infra/db.py` | BC-DB-1,2,3 | Убрать `None` default; I-DB-1 enforcement; `PYTEST_CURRENT_TEST` fail-fast; guard; убрать import `event_store_file` |
| `src/sdd/infra/metrics.py` | BC-DB-4 | Добавить `db_path: str` параметр; убрать `event_store_file()` |
| `tests/conftest.py` | BC-DB-5 | Добавить 3 фикстуры |
| `pyproject.toml` | BC-DB-6 | `pytest-timeout>=4.0`; `--timeout=30` |
| `CLAUDE.md §INV` | BC-DB-7 | Добавить I-DB-1..2, I-DB-TEST-1..2 |
| callers `get_phase_metrics` | BC-DB-4 | Передать `db_path` явно |

---

## 6. Тесты

- **Unit: `tests/unit/infra/test_db.py`** — тест I-DB-1 enforcement (пустой db_path → ValueError);
  тест fail-fast (mock `PYTEST_CURRENT_TEST`, lock error → немедленный raise);
  тест guard (production path → RuntimeError)

- **Unit: `tests/unit/infra/test_metrics.py`** — тест новой сигнатуры `get_phase_metrics(db_path=...)`

- **Integration: `tests/integration/test_sdd_home_isolation.py`** — добавить проверку
  что `_reset_sdd_root` autouse фикстура работает корректно

- **Regression: зависание больше не воспроизводится** — запуск `pytest tests/ -x -q`
  завершается без D-state

---

## 7. Верификация DoD

```bash
# Тип-проверка
python3 -m mypy src/sdd/infra/db.py src/sdd/infra/metrics.py

# Unit тесты
python3 -m pytest tests/unit/ -x -q

# Полный suite без зависаний
python3 -m pytest tests/ -x -q

# Проверить guard: должен упасть немедленно с RuntimeError
# (запустить из тестового контекста вручную если нужно)
```
