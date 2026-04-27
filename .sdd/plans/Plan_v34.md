# Plan_v34 — Phase 34: EventLog Deep Module

Status: DRAFT
Spec: specs/Spec_v34_EventLogDeepModule.md

---

## Milestones

### M1: Перенос canonical_json в core/json_utils.py

```text
Spec:       §2 (BC-34a), §4 (core/json_utils.py)
BCs:        BC-34a
Invariants: I-EL-CANON-1
Depends:    — (нет зависимостей; safe first step)
Risks:      circular import если core/ вдруг импортирует infra/ — проверить
            перед выполнением; все callers canonical_json обновляются атомарно
```

Создать `src/sdd/core/json_utils.py` с функцией `canonical_json()`.
Удалить `canonical_json` из `infra/event_log.py`.
Обновить все файлы, импортирующие `canonical_json` из `event_log`,
на `from sdd.core.json_utils import canonical_json`.

---

### M2: Реализация класса EventLog в event_log.py

```text
Spec:       §4 (EventLog — Public Interface), §5 (New Invariants), §6 (Pre/Post)
BCs:        BC-34
Invariants: I-EL-UNIFIED-2, I-EL-DEEP-1, I-EL-BATCH-ID-1, I-EL-NON-KERNEL-1,
            I-EL-LEGACY-1
Depends:    M1
Risks:      append() объединяет locked и unlocked пути — нельзя оставлять
            _append_locked() как отдельный метод (I-EL-UNIFIED-2);
            I-EL-BATCH-ID-1 требует разного поведения для single/multi event
```

Реализовать `EventLog` класс с методами `append()`, `replay()`, `max_seq()`,
`exists_command()`, `exists_semantic()`, `get_error_count()`.
Реализовать `EventLogError` (наследует `SDDError`).
Логика из `EventStore._append_locked()` и `EventStore.append()` переносится
в единый `EventLog.append()` с auto-batch_id (I-EL-BATCH-ID-1).
Метод `sdd_append_batch()` получает guard против вызова внутри execute_command
(I-EL-NON-KERNEL-1).
Module-level функции `sdd_append`, `sdd_append_batch`, `meta_context`,
`archive_expired_l3` сохраняются (I-EL-LEGACY-1).

---

### M3: Миграция registry.py и commands/ на EventLog

```text
Spec:       §8 (Integration — Callers, Mandatory Import Updates для src/)
BCs:        BC-34 (kernel integration), BC-34b (partial: src/ callers)
Invariants: I-KERNEL-WRITE-1 (updated), I-EL-UNIFIED-1 (partial: EventStore
            не используется в production code)
Depends:    M2
Risks:      registry.py — Write Kernel; неверная миграция EventStore→EventLog
            ломает все write commands; выполнять атомарно: один PR, тесты
            должны проходить до удаления event_store.py
```

Обновить импорты и вызовы в:
- `src/sdd/commands/registry.py`
- `src/sdd/commands/reconcile_bootstrap.py`
- `src/sdd/commands/validate_invariants.py`
- `src/sdd/commands/report_error.py`
- `src/sdd/commands/update_state.py`

`EventStore` → `EventLog`, `EventStoreError` → `EventLogError`.
`infra/metrics.py` — `EventLog.append(..., allow_outside_kernel="metrics")`.

---

### M4: Миграция тестов и удаление event_store.py

```text
Spec:       §8 (Callers — tests/), §8 (test_event_store.py migration table)
BCs:        BC-34b (test callers), I-EL-UNIFIED-1 (удаление файла)
Invariants: I-EL-UNIFIED-1, I-EL-DEEP-1 (тесты покрывают instance methods),
            I-DB-TEST-1, I-DB-TEST-2
Depends:    M3
Risks:      test_event_store.py содержит тесты с разной судьбой (migrate /
            delete / rewrite) — строго следовать таблице из §8 спека;
            regression/test_kernel_contract.py:35 хардкодит путь
            event_store.py — обновить на проверку отсутствия файла
```

Создать `tests/unit/infra/test_event_log_class.py` с мигрированными тестами.
Обновить / удалить тесты в `test_event_store.py` по таблице миграции §8.
Обновить импорты во всех test-файлах (список в §8 спека).
Обновить `tests/regression/test_kernel_contract.py` строки 35 и 78.
Удалить `src/sdd/infra/event_store.py`.

---

### M5: Обновление kernel-contracts.md

```text
Spec:       §8 (Kernel-Contracts Update, I-KERNEL-EXT-1)
BCs:        BC-34c
Invariants: I-KERNEL-WRITE-1 (updated), I-EL-UNIFIED-1
Depends:    M4
Risks:      kernel-contracts.md является §HARD-LOAD Rule 1 для всех write
            commands — устаревшие записи вводят LLM в заблуждение в будущих
            сессиях; выполнять последним, только после валидации всего кода
```

Обновить таблицу замороженных поверхностей в `.sdd/docs/ref/kernel-contracts.md`:
- Удалить строку `infra/event_store.py | EventStore.append()`
- Обновить строки `infra/event_log.py` согласно таблице §8 спека
- Обновить формулировку I-KERNEL-WRITE-1 (EventLog вместо EventStore)

---

## Risk Notes

- R-1: **Write Kernel регрессия** — registry.py использует EventStore в критическом
  пути execute_command; неверная миграция в M3 ломает все write commands.
  Mitigation: тесты интеграции для registry проходят до удаления event_store.py (M4).

- R-2: **Legacy API сохранность** — sdd_append() и sdd_append_batch() используются
  hooks/log_tool.py и metrics.py; изменение сигнатуры нарушает I-EL-LEGACY-1.
  Mitigation: оба метода остаются module-level, сигнатуры не меняются.

- R-3: **Circular imports** — core/json_utils.py не должен импортировать из infra/.
  Mitigation: M1 выполняется первым; явная проверка перед мержем.

- R-4: **test_event_store.py частичная миграция** — три теста с разной судьбой
  (migrate / delete / rewrite); неверная обработка оставляет мёртвый код.
  Mitigation: следовать таблице §8 спека пошагово, по одному тесту.
