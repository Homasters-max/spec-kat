# Spec_v45 — Phase 45: Enforce PostgreSQL (BREAKING)

Status: Draft  
Baseline: Spec_v44_RoutingSwitch.md  
Architectural analysis: `.claude/plans/dazzling-dreaming-stardust.md`

---

## 0. Goal

Убрать DuckDB fallback из `event_store_url()`. После Phase 45 `SDD_DATABASE_URL` **обязателен**:
его отсутствие → `EnvironmentError` немедленно. DuckDB как backend перестаёт поддерживаться
для production-workflow; DuckDB-код остаётся в codebase (удаление — Phase 46).

**Это BREAKING CHANGE.** Все тесты, использующие implicit DB resolution без `SDD_DATABASE_URL`,
упадут. Перед написанием TaskSet требуется обязательный аудит тестов (§8 "Pre-requisites").

---

## 1. Scope

### In-Scope

- BC-45-A: `event_store_url()` — обязательный `SDD_DATABASE_URL`; fallback удалён (I-DB-URL-REQUIRED-1)
- BC-45-B: `is_production_event_store()` — согласование с новым `event_store_url()` (I-PROD-GUARD-1)
- BC-45-C: `validate_invariants.py` — `SDD_DATABASE_URL` passthrough в subprocess (блокер)
- BC-45-D: `get_current_state()` — YAML + staleness guard (I-STATE-READ-1)
- BC-45-E: `_isolate_sdd_home` fixture — Путь A: passthrough `SDD_DATABASE_URL` (блокер)
- BC-45-F: `show_path.py` — diagnostic fix для PG mode
- BC-45-G: Аудит и фикс всех тестов с implicit DB resolution

### Out of Scope

- Удаление DuckDB кода — Phase 46
- `el_kernel.py` extraction — Phase 46 prerequisite
- `_sdd_root` глобал (Путь B: инвертирование зависимости) — Phase 47+
- Connection pooling — Future

---

## 2. Architecture / BCs

### BC-45-A: event_store_url() — mandatory SDD_DATABASE_URL

**Файл:** `src/sdd/infra/paths.py`

```python
def event_store_url() -> str:
    """Single routing point for event store backend.

    I-DB-URL-REQUIRED-1: SDD_DATABASE_URL MUST be set.
    Raises EnvironmentError if not set (no DuckDB fallback).
    """
    pg_url = os.environ.get("SDD_DATABASE_URL")
    if not pg_url:
        raise EnvironmentError(
            "SDD_DATABASE_URL is not set. "
            "Run: source scripts/dev-up.sh"
        )
    return pg_url
```

`event_store_file()` сохраняется без изменений:
- используется в `show_path.py` (diagnostic)
- используется в тестах с explicit DuckDB path
- deprecated: в Phase 46 получит `DeprecationWarning`

### BC-45-B: is_production_event_store() — согласование

**Файл:** `src/sdd/infra/paths.py`

**Проблема:** старый код вызывает `event_store_file()` при `SDD_DATABASE_URL` не установлен.
После BC-45-A `event_store_url()` поднимет `EnvironmentError`. Нужно согласовать guard.

```python
def is_production_event_store(db_path: str) -> bool:
    """True if db_path refers to the production event store.

    I-PROD-GUARD-1: agreed with event_store_url().
    Raises EnvironmentError if SDD_DATABASE_URL is not set (I-DB-URL-REQUIRED-1).
    """
    pg_url = os.environ.get("SDD_DATABASE_URL")
    if not pg_url:
        raise EnvironmentError(
            "SDD_DATABASE_URL is not set. "
            "Cannot determine production event store."
        )
    return db_path == pg_url
```

Используется в: `db.py:83`, `event_log.py:83,352,647` — все три места получают согласованное поведение.

### BC-45-C: validate_invariants subprocess passthrough

**Файл:** `src/sdd/commands/validate_invariants.py`

**Проблема:** subprocess env строится из `command.env_whitelist`, который по умолчанию пуст.
Дочерний pytest-процесс не получает `SDD_DATABASE_URL` → `EnvironmentError` на первом вызове.

```python
# validate_invariants.py — добавить константу и расширить env construction

_ALWAYS_PASSTHROUGH: frozenset[str] = frozenset({
    "SDD_DATABASE_URL",
    "SDD_PROJECT",
    "SDD_HOME",
})

# в месте построения env (строки 134–138):
env: dict[str, str] = {
    k: os.environ[k]
    for k in (_ALWAYS_PASSTHROUGH | set(command.env_whitelist))
    if k in os.environ
}
```

**Инвариант:** `SDD_DATABASE_URL` всегда проходит в subprocess-env; whitelist расширяем,
но не требует явного указания для base variables.

### BC-45-D: get_current_state() — YAML + staleness guard

**Файл:** `src/sdd/infra/projections.py` (или отдельная функция — по фактической структуре)

**Мотивация (I-STATE-READ-1):** crash между TX1 (EventLog.append) и project_all() оставляет
`State_index.yaml` на одно событие позади. Следующая команда читает устаревшее состояние —
guard-ы проходят на неверных данных.

```python
def get_current_state(db_url: str, full_replay: bool = False) -> SDDState:
    """Read current state.

    Default: YAML (O(1)). Falls back to replay if:
    - full_replay=True (explicit, e.g. rebuild-state command)
    - YAML absent
    - YAML stale (yaml.last_seq < event_log.max_seq)

    I-STATE-READ-1: staleness guard prevents stale state from reaching guards.
    """
    if full_replay:
        return _replay_from_event_log(db_url)

    yaml_state = _read_yaml()
    if yaml_state is None:
        return _replay_from_event_log(db_url)

    max_seq = _pg_max_seq(db_url)
    if yaml_state.last_seq < max_seq:
        logger.warning(
            "State_index.yaml is stale (last_seq=%d < el_max=%d). Replaying.",
            yaml_state.last_seq,
            max_seq,
        )
        return _replay_from_event_log(db_url)

    return yaml_state
```

`_pg_max_seq(db_url)` — вспомогательная функция: `SELECT COALESCE(MAX(sequence_id), 0) FROM event_log`.  
Только для `sdd rebuild-state` передаётся `full_replay=True`.

**Pre:**
- `db_url` — PG URL (I-DB-URL-REQUIRED-1 в Phase 45)

**Post:**
- Если YAML актуален (`last_seq >= max_seq`) → возвращает YAML-state (O(1))
- Если YAML stale или absent → replay из `event_log` → возвращает актуальный state
- В любом случае: возвращаемый state имеет `last_seq == MAX(event_log.sequence_id)`

### BC-45-E: _isolate_sdd_home fixture — Путь A

**Файл:** `tests/conftest.py`

**Проблема:** `_isolate_sdd_home` (autouse fixture) управляет `_sdd_root` глобалом.
После BC-45-A тесты, запущенные без `SDD_DATABASE_URL`, упадут на первом вызове `event_store_url()`.

**Путь A (минимальный fix — Phase 45):**

```python
# conftest.py — обновить _isolate_sdd_home

@pytest.fixture(autouse=True)
def _isolate_sdd_home(tmp_path, monkeypatch):
    # ... существующая логика _sdd_root isolation ...

    # Passthrough SDD_DATABASE_URL для тестов, явно использующих PG
    # Unit-тесты с FakeEventLog/explicit db_path НЕ должны иметь SDD_DATABASE_URL
    # — иначе event_store_url() вернёт реальный PG URL вместо test URL.
    # Поэтому: passthrough только если тест явно помечен @pytest.mark.pg
    # или если SDD_DATABASE_URL уже установлен в env (CI с PG).
    if pg_url := os.environ.get("SDD_DATABASE_URL"):
        monkeypatch.setenv("SDD_DATABASE_URL", pg_url)
    # else: unit-тесты должны передавать db_path явно (не через event_store_url())
```

**Путь B (правильный, Phase 47+):** инвертировать зависимость — передавать `sdd_root: Path`
явно в потребителей; `paths.py` становится набором чистых функций; autouse фикстура исчезает.

### BC-45-F: show_path.py diagnostic fix

**Файл:** `src/sdd/commands/show_path.py`

В Phase 45 `sdd path state` выводит DuckDB-путь, хотя реально используется PG.

```python
# show_path.py — обновить диагностический вывод

def _show_event_store_path() -> str:
    pg_url = os.environ.get("SDD_DATABASE_URL")
    if pg_url:
        # Скрыть пароль для безопасного вывода
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(pg_url)
        safe = parsed._replace(netloc=parsed.netloc.rsplit("@", 1)[-1])
        return f"[PG] {urlunparse(safe)}"
    # Fallback: show DuckDB path (deprecated, Phase 46 removes)
    return str(event_store_file())
```

### BC-45-G: Аудит и фикс тестов

**Обязателен до написания TaskSet Phase 45.**

Категории тестов:

| Категория | Признак | Действие |
|-----------|---------|---------|
| Безопасные | `in_memory_db` fixture (`:memory:` explicit) | нет изменений (пока DuckDB есть) |
| Безопасные | `tmp_db_path` fixture (explicit path) | нет изменений |
| Безопасные | `@pytest.mark.pg` тесты | получают `SDD_DATABASE_URL` через BC-45-E |
| Требуют фикса | implicit DB resolution (нет explicit `db_path`, нет `SDD_DATABASE_URL`) | передать `db_path` явно или мокировать `event_store_url` |

**Шаги аудита:**

```bash
# 1. Найти тесты с implicit resolution
grep -r "event_store_url()" tests/ --include="*.py"
grep -r "event_store_file()" tests/ --include="*.py"

# 2. Найти тесты без explicit db_path и без pg mark
# (вручную: просмотр conftest.py, test_*.py на предмет вызовов без db_path=)

# 3. Запустить с SDD_DATABASE_URL не установленным — увидеть падения
unset SDD_DATABASE_URL && pytest -m "not pg" -x 2>&1 | head -50
```

**Стратегия фикса:** для каждого упавшего теста — передать `db_path` явно (из фикстуры),
либо мокировать `event_store_url` через `monkeypatch.setenv("SDD_DATABASE_URL", test_pg_url)`.

---

## 3. Domain Events

Phase 45 не вводит новых domain events.

---

## 4. Types & Interfaces

```python
# src/sdd/infra/paths.py — изменённые сигнатуры

def event_store_url() -> str:
    """I-DB-URL-REQUIRED-1: raises EnvironmentError if SDD_DATABASE_URL not set."""
    ...

def is_production_event_store(db_path: str) -> bool:
    """I-PROD-GUARD-1: raises EnvironmentError if SDD_DATABASE_URL not set."""
    ...

# event_store_file() — СОХРАНЯЕТСЯ без изменений
def event_store_file() -> Path:
    """Deprecated: use show_path.py only. Will raise DeprecationWarning in Phase 46."""
    ...
```

```python
# src/sdd/infra/projections.py — новая сигнатура

def get_current_state(db_url: str, full_replay: bool = False) -> SDDState:
    """I-STATE-READ-1: YAML-first with staleness guard.

    full_replay=True: explicit full replay (rebuild-state only).
    """
    ...
```

```python
# src/sdd/commands/validate_invariants.py — новая константа

_ALWAYS_PASSTHROUGH: frozenset[str] = frozenset({
    "SDD_DATABASE_URL",
    "SDD_PROJECT",
    "SDD_HOME",
})
```

---

## 5. Invariants

### Новые инварианты

| ID | Statement | Phase |
|----|-----------|-------|
| I-DB-URL-REQUIRED-1 | `event_store_url()` MUST NOT fallback к DuckDB; отсутствие `SDD_DATABASE_URL` → `EnvironmentError`; сообщение MUST содержать команду восстановления (`source scripts/dev-up.sh`) | 45 |
| I-STATE-READ-1 | `get_current_state()` читает `State_index.yaml` по умолчанию (O(1)); при `yaml.last_seq < el_max_seq` → fallback на replay + emit WARNING; explicit `full_replay=True` — только для `sdd rebuild-state` | 45 |
| I-SUBPROCESS-ENV-1 | `validate_invariants` subprocess MUST получать `SDD_DATABASE_URL`, `SDD_PROJECT`, `SDD_HOME` из parent env без явного `--env`; список `_ALWAYS_PASSTHROUGH` — константа, не конфигурируема через CommandSpec | 45 |

### Обновлённые инварианты

| ID | Обновление |
|----|-----------|
| I-PROD-GUARD-1 | `is_production_event_store()` согласована с `event_store_url()`: при `SDD_DATABASE_URL` не установлен — обе функции поднимают `EnvironmentError` (Phase 43: DuckDB fallback; Phase 45: error) |
| I-EVENT-STORE-URL-1 | DuckDB fallback удалён; `SDD_DATABASE_URL` обязателен (Phase 45, ранее: fallback разрешён) |

---

## 6. Pre/Post Conditions

### BC-45-A: event_store_url()

**Pre:**
- Phase 44 завершена (все CLI используют `event_store_url()`)

**Post:**
- `SDD_DATABASE_URL` установлен → возвращает PG URL
- `SDD_DATABASE_URL` не установлен → `EnvironmentError("SDD_DATABASE_URL is not set...")`
- Никаких DuckDB fallbacks

### BC-45-B: is_production_event_store()

**Pre:**
- BC-45-A применён

**Post:**
- `SDD_DATABASE_URL` не установлен → `EnvironmentError` (согласовано с BC-45-A)
- `SDD_DATABASE_URL` установлен → `db_path == SDD_DATABASE_URL` (строгое равенство)
- Нет вызовов `event_store_file()` внутри функции

### BC-45-C: validate_invariants subprocess

**Pre:**
- `SDD_DATABASE_URL` установлен в parent process

**Post:**
- Дочерний subprocess получает `SDD_DATABASE_URL` без явного `--env SDD_DATABASE_URL`
- `event_store_url()` в subprocess → PG URL (не `EnvironmentError`)

### BC-45-D: get_current_state() staleness

**Pre:**
- `db_url` = PG URL
- `State_index.yaml` существует и содержит `last_seq`

**Post:**
- `yaml.last_seq == el_max_seq` → возвращает YAML-state (O(1) путь)
- `yaml.last_seq < el_max_seq` → WARNING + replay → возвращает актуальный state
- `State_index.yaml` absent → replay → возвращает актуальный state
- Всегда: возвращаемый state имеет `last_seq == MAX(event_log.sequence_id)`

---

## 7. Use Cases

### UC-45-1: Запуск команды без SDD_DATABASE_URL

**Pre:** `SDD_DATABASE_URL` не установлен  
**Steps:**
1. CLI вызывает `execute_and_project(spec, cmd)`
2. `registry.py` вызывает `event_store_url()`
3. `event_store_url()` → `EnvironmentError("SDD_DATABASE_URL is not set...")`
4. CLI показывает сообщение с командой восстановления
**Post:** команда не выполнена; пользователь видит actionable сообщение

### UC-45-2: validate_invariants с SDD_DATABASE_URL

**Pre:** `SDD_DATABASE_URL` установлен  
**Steps:**
1. `sdd validate T-4501 --result PASS`
2. `validate_invariants.py` строит subprocess env с `_ALWAYS_PASSTHROUGH`
3. Дочерний pytest получает `SDD_DATABASE_URL`
4. `event_store_url()` в subprocess → PG URL → тесты проходят
**Post:** валидация успешна; нет `EnvironmentError` в subprocess

### UC-45-3: Stale YAML — staleness guard срабатывает

**Pre:** crash после TX1 (event_log.append) до project_all()  
**Steps:**
1. Следующая команда вызывает `get_current_state(db_url)`
2. `_read_yaml()` → `yaml.last_seq = N`
3. `_pg_max_seq(db_url)` → `max_seq = N+1`
4. `yaml.last_seq < max_seq` → WARNING log
5. `_replay_from_event_log(db_url)` → актуальный state с `last_seq = N+1`
**Post:** команда работает на актуальном state; guard-ы получают корректные данные

### UC-45-4: YAML актуален — O(1) путь

**Pre:** нет crash-ов; `yaml.last_seq == el_max_seq`  
**Steps:**
1. Команда вызывает `get_current_state(db_url)`
2. `_read_yaml()` → `yaml.last_seq = N`
3. `_pg_max_seq(db_url)` → `max_seq = N`
4. `yaml.last_seq == max_seq` → возвращает YAML-state
**Post:** O(1) чтение; нет replay

---

## 8. Pre-requisites (обязательны до TaskSet)

### Аудит тестов (до написания TaskSet)

Перед декомпозицией Phase 45 на задачи **LLM MUST выполнить аудит**:

```bash
# Найти все тесты, упавшие без SDD_DATABASE_URL
unset SDD_DATABASE_URL && pytest -m "not pg" --tb=no -q 2>&1 | grep FAILED
```

Результат аудита документируется в `TaskSet_v45.md` как блокирующие задачи перед BC-45-A.

**Порядок применения BC обязателен:**

```
BC-45-G: аудит тестов  →  BC-45-E: fixture fix  →  BC-45-C: subprocess passthrough
  ↓
BC-45-D: staleness guard  →  BC-45-B: is_production_event_store  →  BC-45-A: event_store_url
  ↓
BC-45-F: show_path diagnostic
```

BC-45-A применяется **последним** — после фикса всех мест, которые упадут.

---

## 9. Integration

### Dependencies

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-44: Routing Switch | this after | BC-45-A ломает DuckDB fallback только если все CLI уже на event_store_url() |
| BC-43-D: PostgresEventLog | this uses | `_pg_max_seq` использует PG connection |
| BC-43-E: Projector | this uses | staleness guard trigger rebuild через Projector |

### Влияние на тесты

После Phase 45:
- Все тесты с implicit DB resolution и без `SDD_DATABASE_URL` → упадут (BC-45-G фиксирует заранее)
- `pytest -m "not pg"` без `SDD_DATABASE_URL` → 0 FAILED (после BC-45-G + BC-45-E)
- `pytest -m pg` с `SDD_DATABASE_URL` → PASS

---

## 10. Verification

### Unit Tests

| # | Test | Invariant(s) |
|---|------|--------------|
| 1 | `test_event_store_url_raises_without_env` — нет `SDD_DATABASE_URL` → `EnvironmentError` с правильным сообщением | I-DB-URL-REQUIRED-1 |
| 2 | `test_event_store_url_returns_pg_url` — `SDD_DATABASE_URL` установлен → возвращает значение | I-DB-URL-REQUIRED-1 |
| 3 | `test_is_production_event_store_raises_without_env` — нет `SDD_DATABASE_URL` → `EnvironmentError` | I-PROD-GUARD-1 |
| 4 | `test_is_production_event_store_matches_pg_url` — db_path == SDD_DATABASE_URL → True | I-PROD-GUARD-1 |
| 5 | `test_validate_invariants_subprocess_gets_pg_url` — mock subprocess env → содержит `SDD_DATABASE_URL` | I-SUBPROCESS-ENV-1 |
| 6 | `test_get_current_state_yaml_path_when_fresh` — yaml.last_seq == max_seq → YAML возвращён, replay не вызван | I-STATE-READ-1 |
| 7 | `test_get_current_state_replays_when_stale` — yaml.last_seq < max_seq → WARNING + replay | I-STATE-READ-1 |
| 8 | `test_get_current_state_replays_when_yaml_absent` — нет YAML файла → replay | I-STATE-READ-1 |
| 9 | `test_get_current_state_full_replay_flag` — `full_replay=True` → replay независимо от YAML | I-STATE-READ-1 |
| 10 | `test_show_path_pg_mode_hides_password` — `SDD_DATABASE_URL` установлен → вывод без пароля | BC-45-F |

### Smoke Tests

```bash
# 1. Без SDD_DATABASE_URL → EnvironmentError (ожидаемо)
unset SDD_DATABASE_URL && sdd show-state 2>&1 | grep "SDD_DATABASE_URL"

# 2. С SDD_DATABASE_URL → работает
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd sdd show-state

# 3. Все unit тесты без SDD_DATABASE_URL
unset SDD_DATABASE_URL && pytest -m "not pg" --cov=sdd

# 4. Все pg тесты с SDD_DATABASE_URL
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd pytest -m pg
```

---

## 11. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `event_store_file()` DeprecationWarning | Phase 46 |
| Удаление DuckDB кода | Phase 46 |
| `el_kernel.py` extraction | Phase 46 prerequisite |
| `in_memory_db` fixture → PG test schema | Phase 46 |
| `_sdd_root` глобал инвертирование (Путь B) | Phase 47+ |
| Connection pooling для Projector | Future |
