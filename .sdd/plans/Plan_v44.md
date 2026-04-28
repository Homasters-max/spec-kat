# Plan_v44 — Phase 44: Routing Switch (SAFE, minimal diff)

Status: DRAFT
Spec: specs/Spec_v44_RoutingSwitch.md

---

## Logical Context

```
type: none
rationale: "Standard new phase. Builds on Phase 43 infrastructure (event_store_url) by wiring all CLI entry points to use it. Not a bug fix — Phase 43 intentionally deferred the callsite migration."
```

---

## Milestones

### M1: CLI modules — replace event_store_file() → event_store_url()

```text
Spec:       §2, BC-44-A
BCs:        BC-44-A
Invariants: I-CLI-DB-RESOLUTION-1, I-EVENT-STORE-URL-1, I-DB-1
Depends:    — (Phase 43 complete: event_store_url() implemented)
Risks:      Широкий diff (10 файлов). Неправильный импорт или пропущенный callsite
            оставит I-CLI-DB-RESOLUTION-1 нарушенным. Митигация: BC-44-E-тест
            верифицирует полноту после применения всех M1–M4.
```

Файлы:
- `src/sdd/commands/registry.py` (строки 630, 806, 847)
- `src/sdd/commands/show_state.py` (строка 129)
- `src/sdd/commands/activate_phase.py` (строка 186)
- `src/sdd/commands/switch_phase.py` (строка 140)
- `src/sdd/commands/metrics_report.py` (строка 183)
- `src/sdd/commands/validate_invariants.py` (строка 455)
- `src/sdd/commands/next_tasks.py` (строка 27)
- `src/sdd/commands/reconcile_bootstrap.py` (строка 50)
- `src/sdd/commands/invalidate_event.py` (строка 113)
- `src/sdd/infra/projections.py` (строка 65)

### M2: Argparse eager evaluation fix

```text
Spec:       §2, BC-44-B
BCs:        BC-44-B
Invariants: I-CLI-DB-RESOLUTION-1
Depends:    — (независим от M1, применяется параллельно)
Risks:      Если lazy resolve не применён — event_store_url() вызывается при
            импорте. В тестовой среде без SDD_DATABASE_URL может поднять
            EnvironmentError до разбора аргументов.
```

Файлы:
- `src/sdd/commands/update_state.py` (аргументы `--state`, `--db`)
- `src/sdd/commands/query_events.py` (аргумент `--db`)
- `src/sdd/commands/report_error.py` (аргумент `--db`)

Паттерн: `default=None` в `add_argument`; `x = args.x or event_store_url()` в теле функции.

### M3: cli.py — удаление hardcoded DuckDB path

```text
Spec:       §2, BC-44-C
BCs:        BC-44-C
Invariants: I-CLI-DB-RESOLUTION-1
Depends:    — (независим от M1/M2)
Risks:      cli.py — точка входа CLI. Неправильная замена ломает весь routing.
            Проверить: grep sdd_events.duckdb src/sdd/ --exclude=show_path.py
            возвращает пустой результат после применения.
```

Файл:
- `src/sdd/cli.py` (инлайн-конструкция `_root / "state" / "sdd_events.duckdb"`)

### M4: log_tool.py — subprocess routing fix

```text
Spec:       §2, BC-44-D
BCs:        BC-44-D
Invariants: I-CLI-DB-RESOLUTION-1
Depends:    — (независим от M1–M3; отдельный процесс)
Risks:      log_tool.py — subprocess, не наследует env напрямую.
            Сохранить SDD_DB_PATH override для legacy compatibility.
            Без него: fallback через event_store_url() → SDD_DATABASE_URL или DuckDB.
```

Файл:
- `src/sdd/log_tool.py`

Паттерн: `db_path = os.environ.get("SDD_DB_PATH") or event_store_url()`

### M5: Enforcement test I-CLI-DB-RESOLUTION-1

```text
Spec:       §2, BC-44-E; §9, Unit Tests 1–6
BCs:        BC-44-E
Invariants: I-CLI-DB-RESOLUTION-1
Depends:    M1, M2, M3, M4 (тест должен видеть уже исправленный код)
Risks:      Тест должен исключать show_path.py и tests/ из grep.
            Если exclusion patterns неправильные — false positives/negatives.
```

Файл:
- `tests/unit/infra/test_paths.py` (новые тесты: 2 grep-теста + 4 no-eager-eval теста)

---

## Risk Notes

- R-1: **Широкий callsite diff (10+ файлов)** — любой пропущенный callsite нарушает I-CLI-DB-RESOLUTION-1. Митигация: BC-44-E grep-тест как финальная верификация.
- R-2: **Eager evaluation при импорте** — если argparse default= не заменён на `None`, `event_store_url()` вызывается при загрузке модуля. В средах без `SDD_DATABASE_URL` это может поднять ошибку конфигурации до начала работы команды.
- R-3: **log_tool.py subprocess isolation** — subprocess не наследует `SDD_DATABASE_URL` если он выставлен только в Python-среде и не экспортирован в shell. Документировать `SDD_DB_PATH` как explicit override.
- R-4: **cli.py — единственная точка входа** — ошибка здесь ломает всё CLI. Применять последовательно с немедленной проверкой `sdd show-state`.
