# Session Context: Fix Failing Tests After Phase 31

**Date:** 2026-04-27  
**Status:** COMPLETE — 917 passed, 0 failed (was: 24 failed + 2 collection errors)

---

## Исходное состояние

Фаза 31 закрыта (phase.status = COMPLETE). В `tests/unit/` — 24 падения + 2 collection error.
Все провалы — pre-existing, не от T-3114.

---

## Корневые причины и правки (5 кластеров)

### Кластер A — EventStore удалён, тесты не обновлены (14 тестов + 2 collection errors)

`src/sdd/infra/event_store.py` удалён в одной из предыдущих фаз. Код перешёл на `EventLog`.
Тесты продолжали патчить несуществующие символы → `AttributeError`.

**Правки:**
- `tests/unit/commands/test_check_dod.py` — убраны `@patch("sdd.commands.update_state.EventStore")` из 5 тестов, убраны `mock_event_store_cls` параметры и ассерты. TestPurity переписан: теперь проверяет `len(events) == 2` вместо `mock_store.append.assert_not_called()`.
- `tests/unit/commands/test_complete_task.py` — то же для 6 тестов; `TestAtomicity`, `TestNoDirectFileWrite`, `TestIdempotency` — убраны EventStore-патчи, скорректированы сигнатуры.
- `tests/unit/commands/test_sync_state.py` — то же для 5 тестов.
- `tests/unit/commands/test_guard_factory.py` — в `test_execute_command_calls_build_guards` заменён `patch("sdd.commands.registry.EventStore")` → `patch("sdd.commands.registry.EventLog")`.
- `tests/unit/infra/test_event_store.py` — **удалён** (тестировал удалённый модуль).
- `tests/unit/infra/test_event_log_commands.py` — переписан: импорт `exists_command, exists_semantic, get_error_count` убран (это методы класса, не module-level функции); все вызовы переведены на `EventLog(tmp_db_path).exists_command(...)` etc.

**Архитектурный вывод:** тесты были связаны с implementation internals (`EventStore`), а не с интерфейсом (возвращаемые events). Признак shallow module design в тестах.

---

### Кластер B — get_error_count не module-level функция (1 тест)

`tests/unit/commands/test_base.py::test_retry_count_is_best_effort_note` патчил `sdd.commands._base.get_error_count`, но в `_base.py` вызов идёт как `EventLog(self._db_path).get_error_count(command.command_id)`.

**Правка:** `patch("sdd.commands._base.get_error_count", ...)` → `patch("sdd.infra.event_log.EventLog.get_error_count", ...)`

---

### Кластер C — amend-plan в REGISTRY, тест не знает (1 тест)

`tests/unit/test_registry_contract.py::test_registry_write_commands_complete` — `_EXPECTED_REGISTRY_KEYS` не содержал `"amend-plan"` (добавлен в Phase 31).

**Правка:** добавлен `"amend-plan"` в frozenset на строке 17–28.

---

### Кластер D — approve-spec зарегистрирован с idempotent=False (1 тест)

`tests/unit/commands/test_command_idempotency.py::test_command_spec_idempotent_default` требовал, что только `switch-phase` может быть `idempotent=False`. Но `approve-spec` обоснованно `idempotent=False` — каждое утверждение спека является уникальным audit-фактом (BC-31-1).

**Решение:** тест неправ в части whitelist. Обновлён whitelist:
```python
_non_idempotent = frozenset({
    "switch-phase",   # navigation: каждый вызов — уникальный history fact (I-CMD-IDEM-1)
    "approve-spec",   # audit: каждое утверждение — уникальный audit fact (BC-31-1)
})
```

**Правило идемпотентности уточнено:** `idempotent=False` допустим для двух категорий:
1. Navigation commands (`switch-phase`) — временная семантика
2. Audit-unique commands (`approve-spec`) — каждое событие несёт уникальную историческую ценность

---

### Кластер E — Hook error path не эмитирует HookError (3 теста)

`tests/unit/hooks/test_log_tool.py` и `test_log_tool_parity.py` — тесты ожидали 1 `HookError` в DB после провала основного `sdd_append`, но получали 0.

**Корневая причина:** `_make_constrained_db` создавала таблицу с `seq BIGINT NOT NULL PRIMARY KEY DEFAULT nextval('sdd_event_seq')`. Это создавало зависимость сиквенса от колонки. Когда `log_tool.py` вызывал `sdd_append` для записи `HookError`, внутри вызывался `open_sdd_connection(db_path)` → `_restart_sequence(conn)` → `CREATE OR REPLACE SEQUENCE sdd_event_seq START {next_seq}` — **FAIL** с "Dependency Error: Cannot drop entry sdd_event_seq because there are entries that depend on it". Оба write падали → double-failure → stderr, `HookError` не попадал в DB.

**Правка:** в `_make_constrained_db` убран `DEFAULT nextval('sdd_event_seq')` из определения `seq` — приведено в соответствие с production DDL в `db.py` (там `seq BIGINT NOT NULL PRIMARY KEY` без DEFAULT; `nextval` используется явно в INSERT).

---

## Финальный результат

```
917 passed, 4 warnings in 56.86s
```

Все collection errors устранены. Все 24 упавших теста исправлены.

---

## Файлы, изменённые в этой сессии

| Файл | Тип изменения |
|------|---------------|
| `tests/unit/commands/test_check_dod.py` | Убраны EventStore-патчи (5 тестов) |
| `tests/unit/commands/test_complete_task.py` | Убраны EventStore-патчи (6 тестов) |
| `tests/unit/commands/test_sync_state.py` | Убраны EventStore-патчи (5 тестов) |
| `tests/unit/commands/test_guard_factory.py` | EventStore → EventLog в patch |
| `tests/unit/infra/test_event_store.py` | **Удалён** |
| `tests/unit/infra/test_event_log_commands.py` | Переписан под EventLog instance methods |
| `tests/unit/commands/test_base.py` | Цель patch: `_base.get_error_count` → `EventLog.get_error_count` |
| `tests/unit/test_registry_contract.py` | Добавлен `"amend-plan"` в _EXPECTED_REGISTRY_KEYS |
| `tests/unit/commands/test_command_idempotency.py` | Whitelist расширен: approve-spec |
| `tests/unit/hooks/test_log_tool.py` | `_make_constrained_db`: убран DEFAULT nextval |
| `tests/unit/hooks/test_log_tool_parity.py` | `_make_constrained_db`: убран DEFAULT nextval |
