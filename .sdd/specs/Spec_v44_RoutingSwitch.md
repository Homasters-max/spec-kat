# Spec_v44 — Phase 44: Routing Switch (SAFE, minimal diff)

Status: Draft  
Baseline: Spec_v43_UnifiedPostgresEventLog.md  
Architectural analysis: `.claude/plans/dazzling-dreaming-stardust.md`

---

## 0. Goal

Заменить все вызовы `event_store_file()` и хардкоды `.duckdb` на `event_store_url()` во всём CLI.  
После завершения Phase 44: если `SDD_DATABASE_URL` установлен — все команды используют PG;
если не установлен — DuckDB (обратная совместимость сохраняется).

Инвариант I-EVENT-STORE-URL-1 (Phase 43) становится технически соблюдённым: все entry points CLI
маршрутизируются через единую точку `event_store_url()`.

---

## 1. Scope

### In-Scope

- BC-44-A: замена `event_store_file()` → `event_store_url()` во всех CLI-модулях (15 файлов)
- BC-44-B: исправление argparse eager evaluation (`default=None` + lazy resolve)
- BC-44-C: исправление `cli.py` hardcoded DuckDB path
- BC-44-D: исправление `log_tool.py` (отдельный subprocess-процесс)
- BC-44-E: enforcement тест I-CLI-DB-RESOLUTION-1 (grep/ast CI-тест)

### Out of Scope

- Удаление DuckDB fallback из `event_store_url()` — Phase 45
- Любые изменения в `event_store_url()` / `is_production_event_store()` — Phase 45
- `get_current_state()` staleness guard — Phase 45
- Удаление DuckDB зависимости — Phase 46
- PG triggers / REVOKE для enforcement app-level invariants — Phase 44+ (не настоящая Phase 44)

---

## 2. Architecture / BCs

### BC-44-A: Полная замена event_store_file() в CLI-модулях

**Правило:** каждый CLI-модуль, которому нужен путь к event store, вызывает `event_store_url()`.
Прямые вызовы `event_store_file()` (кроме `show_path.py` и тестов) → нарушение I-CLI-DB-RESOLUTION-1.

Полный список замен:

| Файл | Строки | Действие |
|------|--------|---------|
| `src/sdd/commands/registry.py` | 630, 806, 847 | `event_store_file()` → `event_store_url()` |
| `src/sdd/commands/show_state.py` | 129 | `event_store_file()` → `event_store_url()` |
| `src/sdd/commands/activate_phase.py` | 186 | `or event_store_file()` → `or event_store_url()` |
| `src/sdd/commands/switch_phase.py` | 140 | `or event_store_file()` → `or event_store_url()` |
| `src/sdd/commands/metrics_report.py` | 183 | `or event_store_file()` → `or event_store_url()` |
| `src/sdd/commands/validate_invariants.py` | 455 | `or event_store_file()` → `or event_store_url()` |
| `src/sdd/commands/next_tasks.py` | 27 | `or event_store_file()` → `or event_store_url()` |
| `src/sdd/commands/reconcile_bootstrap.py` | 50 | `event_store_file()` → `event_store_url()` |
| `src/sdd/commands/invalidate_event.py` | 113 | `event_store_file()` → `event_store_url()` |
| `src/sdd/infra/projections.py` | 65 | `event_store_file()` → `event_store_url()` |

Везде: обновить импорты (`from sdd.infra.paths import event_store_url`).  
`event_store_file` исключить из imports, где более не используется.

### BC-44-B: Argparse eager evaluation fix

**Проблема:** `parser.add_argument("--db", default=str(event_store_file()))` вызывает
`event_store_file()` при **импорте** модуля — до того как аргументы разбираются. При переходе на
`event_store_url()` проблема усиливается: PG URL может не быть доступен во время импорта.

**Решение:** `default=None` + lazy resolve в теле функции.

**Затронуто:**

| Файл | Строки | Аргумент | Действие |
|------|--------|---------|---------|
| `src/sdd/commands/update_state.py` | 394, 395 | `--state` | `default=None`; `state_path = args.state or str(state_file())` |
| `src/sdd/commands/update_state.py` | 404, 409, 410 | `--db` | `default=None`; `db_path = args.db or event_store_url()` |
| `src/sdd/commands/query_events.py` | 65 | `--db` | `default=None`; `db_path = args.db or event_store_url()` |
| `src/sdd/commands/report_error.py` | 99 | `--db` | `default=None`; `db_path = args.db or event_store_url()` |

`state_file()` остаётся без изменений (DuckDB-независима, lazy OK).

### BC-44-C: cli.py hardcoded path

**Файл:** `src/sdd/cli.py` (~строки 250–400)

```python
# НЕПРАВИЛЬНО — bypass routing (I-CLI-DB-RESOLUTION-1)
_db = str(_root / "state" / "sdd_events.duckdb")
```

```python
# ПРАВИЛЬНО
from sdd.infra.paths import event_store_url
_db = event_store_url()
```

Все вхождения инлайн-конструкции пути к DuckDB в `cli.py` → заменить на `event_store_url()`.

### BC-44-D: log_tool.py (отдельный subprocess)

`log_tool.py` запускается как отдельный процесс, не разделяет environment с основным CLI.

```python
# ПРАВИЛЬНО — сохранить explicit override из SDD_DB_PATH; fallback → event_store_url()
import os
from sdd.infra.paths import event_store_url

db_path = os.environ.get("SDD_DB_PATH") or event_store_url()
```

Документировать в комментарии: `SDD_DB_PATH` — legacy override для subprocess-контекста.

### BC-44-E: Enforcement тест I-CLI-DB-RESOLUTION-1

Новый тест в `tests/unit/infra/test_paths.py`:

```python
# tests/unit/infra/test_paths.py

def test_no_event_store_file_calls_in_cli():
    """I-CLI-DB-RESOLUTION-1: CLI modules MUST NOT call event_store_file().

    Exception: show_path.py (diagnostic output) and tests/.
    """
    import subprocess, sys
    result = subprocess.run(
        ["grep", "-r", "event_store_file()", "src/sdd/",
         "--include=*.py",
         "--exclude=show_path.py"],
        capture_output=True, text=True
    )
    assert result.stdout == "", (
        f"I-CLI-DB-RESOLUTION-1 violated. Files calling event_store_file():\n{result.stdout}"
    )


def test_no_duckdb_hardcodes_in_cli():
    """I-CLI-DB-RESOLUTION-1: CLI MUST NOT hardcode .duckdb paths.

    Exception: show_path.py.
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-r", "sdd_events.duckdb", "src/sdd/",
         "--include=*.py",
         "--exclude=show_path.py"],
        capture_output=True, text=True
    )
    assert result.stdout == "", (
        f"I-CLI-DB-RESOLUTION-1 violated. Hardcoded .duckdb paths:\n{result.stdout}"
    )
```

---

## 3. Domain Events

Phase 44 не вводит новых domain events. Изменения — routing-only.

---

## 4. Types & Interfaces

Нет новых типов. Изменяются только сайты вызова.

### Обновлённый import pattern (после Phase 44)

```python
# Правильный импорт после Phase 44
from sdd.infra.paths import event_store_url  # вместо event_store_file

# Использование
db_path = args.db or event_store_url()  # lazy, в теле функции
```

### Остающиеся исключения (не меняются в Phase 44)

| Файл | Причина |
|------|---------|
| `src/sdd/commands/show_path.py` | диагностический вывод пути к файлу БД |
| `src/sdd/infra/paths.py` | определение `event_store_file()` — само определение |
| `tests/` | тесты могут использовать `event_store_file()` для explicit DuckDB assertions |

---

## 5. Invariants

### Новые инварианты

| ID | Statement | Phase |
|----|-----------|-------|
| I-CLI-DB-RESOLUTION-1 | CLI MUST NOT резолвить DB path вручную (хардкоды, inline Path construction, прямые вызовы `event_store_file()`); единственная точка: `event_store_url()`; enforcement: grep CI-тест (BC-44-E) | 44 |

### Подтверждаемые инварианты

| ID | Statement |
|----|-----------|
| I-EVENT-STORE-URL-1 | Технически соблюдён после Phase 44: все CLI entry points используют `event_store_url()` |
| I-DB-1 | `open_sdd_connection(db_url)` — `db_url` MUST be explicit non-empty str |

---

## 6. Pre/Post Conditions

### BC-44-A/B/C: Маршрутизация CLI

**Pre:**
- `event_store_url()` реализована (Phase 43)
- `SDD_DATABASE_URL` либо установлен (PG), либо нет (DuckDB fallback)

**Post:**
- Все 15 CLI-файлов (список в BC-44-A + BC-44-B) используют `event_store_url()` для DB resolution
- Ни один `argparse default=` не вызывает `event_store_file()` или `event_store_url()` при импорте
- `grep event_store_file src/sdd/ --exclude=show_path.py` → пустой результат (I-CLI-DB-RESOLUTION-1)
- `grep sdd_events.duckdb src/sdd/ --exclude=show_path.py` → пустой результат (I-CLI-DB-RESOLUTION-1)

### BC-44-D: log_tool.py

**Pre:**
- `SDD_DB_PATH` либо установлен (explicit override) либо нет

**Post:**
- Если `SDD_DB_PATH` → использует его (legacy compatibility)
- Если не установлен → вызывает `event_store_url()` → PG или DuckDB в зависимости от `SDD_DATABASE_URL`

### Smoke tests

**Pre:** Phase 44 применена, тесты зелёные

**Post (3 сценария):**
1. `pytest -m "not pg" --cov=sdd` → PASS (unit + DuckDB backward compat)
2. `SDD_DATABASE_URL=postgresql://... sdd show-state` → PASS (PG smoke)
3. `unset SDD_DATABASE_URL && sdd show-state` → PASS (DuckDB backward compat)

---

## 7. Use Cases

### UC-44-1: `sdd complete T-4401` с `SDD_DATABASE_URL` установлен

**Pre:** `SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd` в env  
**Steps:**
1. CLI вызывает `execute_and_project(spec, cmd)`
2. `registry.py:630` вызывает `event_store_url()` → PG URL
3. `open_sdd_connection(pg_url)` → psycopg connection
4. `PostgresEventLog.append(...)` → INSERT в `event_log`
5. `Projector.apply(...)` → UPDATE `p_tasks`
6. `project_all(...)` → State_index.yaml
**Post:** Событие записано в PG `event_log`; `p_tasks.status='DONE'`; YAML актуален

### UC-44-2: `sdd complete T-4401` без `SDD_DATABASE_URL` (DuckDB fallback)

**Pre:** `SDD_DATABASE_URL` не установлен  
**Steps:**
1. CLI вызывает `execute_and_project(spec, cmd)`
2. `event_store_url()` → DuckDB file path (fallback)
3. `open_sdd_connection(duckdb_path)` → DuckDB connection
4. Далее — старый DuckDB flow без изменений
**Post:** Событие записано в DuckDB; обратная совместимость сохранена

### UC-44-3: CLI import не вызывает event_store_url() на верхнем уровне

**Pre:** Module imported (e.g., `import sdd.commands.update_state`)  
**Post:** `event_store_url()` не вызвана; нет side effects; нет `EnvironmentError`

---

## 8. Integration

### Dependencies

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-43-A: `event_store_url()` | this uses | единственный callee для DB resolution |
| BC-43-B: `open_sdd_connection()` | this uses | реализует PG/DuckDB routing |
| BC-43-F: `execute_and_project()` | this is used by | CLI entry points вызывают через `registry.py` |

### Порядок применения BC

```
BC-44-A: замена в commands/ и infra/
BC-44-B: argparse eager eval fix (может быть в тех же файлах — атомарно)
BC-44-C: cli.py hardcode fix
BC-44-D: log_tool.py fix
BC-44-E: enforcement тест (последним — после всех замен)
```

Все BC-44-A…D могут применяться параллельно (нет cross-dependencies между ними).
BC-44-E — последним: тест должен видеть уже исправленный код.

---

## 9. Verification

### Unit Tests

| # | Test | Invariant(s) |
|---|------|--------------|
| 1 | `test_no_event_store_file_calls_in_cli` — grep src/sdd/ → пусто | I-CLI-DB-RESOLUTION-1 |
| 2 | `test_no_duckdb_hardcodes_in_cli` — grep `.duckdb` → пусто | I-CLI-DB-RESOLUTION-1 |
| 3 | `test_update_state_argparse_no_eager_eval` — импорт `update_state`; `event_store_url` не вызвана при импорте | I-CLI-DB-RESOLUTION-1 |
| 4 | `test_query_events_argparse_no_eager_eval` — аналогично для `query_events` | I-CLI-DB-RESOLUTION-1 |
| 5 | `test_report_error_argparse_no_eager_eval` — аналогично для `report_error` | I-CLI-DB-RESOLUTION-1 |
| 6 | `test_log_tool_uses_event_store_url_fallback` — без `SDD_DB_PATH`, без `SDD_DATABASE_URL` → DuckDB path | BC-44-D |

### Smoke Tests (ручные / CI)

```bash
# 1. Unit + DuckDB backward compat
pytest -m "not pg" --cov=sdd

# 2. PG smoke
SDD_DATABASE_URL=postgresql://sdd:sdd@localhost:5432/sdd sdd show-state

# 3. DuckDB backward compat
unset SDD_DATABASE_URL && sdd show-state
```

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Удаление DuckDB fallback из `event_store_url()` | Phase 45 |
| `is_production_event_store()` согласование | Phase 45 |
| `validate_invariants` subprocess passthrough | Phase 45 |
| `get_current_state()` staleness guard | Phase 45 |
| Удаление DuckDB зависимости | Phase 46 |
| `show_path.py` diagnostic fix для PG mode | Phase 45 |
| PG RLS / REVOKE для p_* enforcement | Future |
