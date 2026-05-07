# T-503 Handover — GuardContext Deduplication

**Статус:** BLOCKED — требует human-решения до продолжения  
**Создан:** 2026-04-22  
**Incident report:** `.sdd/reports/SENARIncident_2026-04-22T15-39-13Z_MissingContext.md`

---

## Что такое T-503

Задача из Phase 5, TaskSet_v5.md:

> **T-503: GuardContext Deduplication**  
> Удалить дублирующий класс `GuardContext` из `src/sdd/guards/runner.py`.  
> Canonical: `src/sdd/domain/guards/context.py`.

Declared Outputs в TaskSet: **только `src/sdd/guards/runner.py`**.

---

## Что было обнаружено в этой сессии

### 1. Два GuardContext — несовместимые контракты

| Поле | `guards/runner.py` | `domain/guards/context.py` |
|---|---|---|
| `state` | ✓ | ✓ |
| `config` | ✓ | — |
| `taskset_path` | ✓ | — |
| `reports_dir` | ✓ | — |
| `emit` | ✓ | — |
| `catalog` | ✓ | — |
| `phase` | — | ✓ |
| `task` | — | ✓ |
| `norms` | — | ✓ |
| `event_log` | — | ✓ |
| `task_graph` | — | ✓ |
| `now` | — | ✓ |

Это не истинные дубликаты — это разные контракты разных эпох (Phase 3 vs Phase 4+).

### 2. Старые guards — мёртвый код (подтверждено эмпирически)

```
grep -rn "from sdd.guards import" src/   → 0 результатов вне guards/
grep -rn "from sdd.guards import" .sdd/tools/  → 0 результатов
```

`CommandRunner` (sdd_run.py) реализует всю guard-логику **inline**, старые классы не вызывает.  
`.sdd/tools/phase_guard.py`, `.sdd/tools/guard_runner.py` реализуют guard-логику **независимо** через CLI, не импортируют Python-классы из `src/sdd/guards/`.

Сам `sdd_run.py` явно комментирует:
```python
# Step 4: TaskStartGuard — [skipped: reports_dir not in GuardContext]
# Step 5: ScopeGuard — [skipped: config not in GuardContext]
```

### 3. Что было попробовано

**Попытка:** заменить класс GuardContext в runner.py на re-export из domain/guards/context.py.

**Результат:** 31 из 58 тестов в `tests/unit/guards/` упали с `TypeError: GuardContext.__init__() got an unexpected keyword argument 'config'`. Тесты конструируют GuardContext со старыми полями.

**Решение:** изменение отменено, код возвращён в исходное состояние. Все 58 тестов проходят.

### 4. Корневая причина блокировки

TaskSet T-503 Outputs объявляет только `runner.py`, но acceptance criteria требует обновить все import sites (guards/*.py, tests/unit/guards/*.py). Это противоречие невозможно разрешить без human-решения.

---

## Архитектурный анализ (итог сессии)

### Текущее состояние системы (гибридное)

```
[Phase 3 guards/]          ← мёртвый код (guards/*.py + тесты)
[domain/guards/context.py] ← canonical GuardContext (Phase 4+)
[domain/guards/dependency_guard.py] ← единственный живой domain guard
[commands/sdd_run.py]      ← inline guard pipeline (Phase 4+)
```

### Фактический контракт Guard в системе

```python
Guard = Callable[[GuardContext], tuple[GuardResult, list[DomainEvent]]]
```

Guards — это **event-emitting decision layer**, не pure validation. `DependencyGuard` уже реализует этот контракт.

### Текущий `run_guard_pipeline` — fail-fast семантика

```python
# В sdd_run.py — stop_on_deny=True по умолчанию
if stop_on_deny and result.outcome is GuardOutcome.DENY:
    return deny_result, all_audit  # останавливается на первом DENY
```

Это архитектурный выбор, а не недостаток.

---

## Решение, которое нужно принять (Human)

### Вариант D (рекомендуемый) — удаление мёртвого кода

Расширить T-503 Outputs в TaskSet_v5.md:

```yaml
Outputs:
  src/sdd/guards/runner.py          # убрать GuardContext класс
  src/sdd/guards/task.py            # удалить
  src/sdd/guards/norm.py            # удалить
  src/sdd/guards/scope.py           # удалить
  src/sdd/guards/phase.py           # удалить
  src/sdd/guards/task_start.py      # удалить
  src/sdd/guards/__init__.py        # убрать legacy exports
  tests/unit/guards/test_task.py    # удалить (тесты мёртвого кода)
  tests/unit/guards/test_norm.py    # удалить
  tests/unit/guards/test_scope.py   # удалить
  tests/unit/guards/test_phase.py   # удалить
  tests/unit/guards/test_task_start.py # удалить
```

И явно разрешить удаление тестов (переопределить CEP-3 для этих файлов).

`tests/unit/guards/test_runner.py` — оставить (тестирует `run_guard_pipeline` и `GuardResult`, живой код).

### Вариант: не делать сейчас

Оставить T-503 как есть, признать что Spec §2.3 написан с неверным допущением о совместимости GuardContext. Задокументировать как known issue.

---

## Шаги для продолжения в новой сессии

### Если Human выбрал Вариант D и расширил Outputs:

1. Прочитать обновлённый TaskSet_v5.md T-503 (проверить что Outputs расширены)
2. Прочитать State_index.yaml (проверить phase=5 ACTIVE)
3. Прочитать `src/sdd/guards/__init__.py` — понять что экспортируется
4. Удалить файлы мёртвого кода:
   - `src/sdd/guards/task.py`, `norm.py`, `scope.py`, `phase.py`, `task_start.py`
   - `tests/unit/guards/test_task.py`, `test_norm.py`, `test_scope.py`, `test_phase.py`, `test_task_start.py`
5. Обновить `src/sdd/guards/__init__.py` — убрать импорты удалённых классов
6. Обновить `src/sdd/guards/runner.py`:
   - Убрать класс `GuardContext`
   - Добавить `from sdd.domain.guards.context import GuardContext` (re-export)
7. Запустить: `PYTHONPATH=src python3 -m pytest tests/unit/guards/ -q`
   - Должен остаться только `test_runner.py` с 3 тестами
8. Запустить полный тест-сьют: `PYTHONPATH=src python3 -m pytest -q`
9. `python3 .sdd/tools/update_state.py complete T-503`

### Контекст который нужно иметь в виду (для T-506, отдельная фаза)

После T-503 в системе останется inline guard logic в `sdd_run.py`. Это технический долг для Phase 6:
- Извлечь phase_check, task_check, norm_check как callable guards
- Зафиксировать формальный контракт `Guard = Callable[[GuardContext], tuple[GuardResult, list[DomainEvent]]]` в `domain/guards/types.py`
- Generic `run_guard_pipeline(ctx, guards, stop_on_deny=True)`
- `CommandRunner` становится чистым оркестратором
