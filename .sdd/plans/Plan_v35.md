# Plan_v35 — Phase 35: Test Harness Elevation

Status: DRAFT
Spec: — (spec не утверждён; план — черновик до формального DRAFT_SPEC сессии)

---

## Контекст

Источник: grilling-сессия /improve-codebase-architecture, кандидат №5.
Суть: два точечных анти-паттерна в тестах поведения команд:
- `patch.object(handler, "_check_idempotent", ...)` — патчит приватный метод, хрупок при переименовании
- `conn.execute("SELECT event_type FROM events")` — читает строки таблицы вместо публичного state-интерфейса

Принятые исключения (не трогаем):
- `test_db.py` — корректные unit-тесты DB-модуля через его собственный интерфейс
- `patch("subprocess.Popen")` — внешняя граница (процесс ОС), документируем как `# subprocess boundary — intentional`

---

## Milestones

### M1: Идемпотентные тесты переходят на execute_sequence

```text
Затронуто:  tests/unit/commands/test_validate_invariants.py (класс TestIdempotency)
            tests/unit/commands/ — любые другие файлы с patch.object(handler, "_check_idempotent")
Подход:     execute_sequence([(spec, cmd)], db_path) вызвать дважды с одним command_id;
            проверить, что второй вызов вернул [] (нет новых events) — через replay()
            или прямо по длине результата.
Leverage:   тест проверяет реальный механизм idempotency (EventStore dedup),
            а не внутренний guard метода handler.
Depends:    — (harness/api.py::execute_sequence уже работает)
Risks:      Нужен CommandSpec для ValidateInvariants в тесте — брать из registry,
            не конструировать руками, чтобы не сломаться при изменении полей.
```

### M2: Прямые SELECT для проверки state заменяются на get_current_state / replay

```text
Затронуто:  tests/unit/infra/test_metrics.py (test_record_metric_batch_with_task_completed,
            test_i_m_1_enforced — та часть где conn.execute("SELECT event_type FROM events"))
            tests/unit/ — любые другие файлы с open_sdd_connection + SELECT для state assertion
Подход:     вместо conn.execute("SELECT event_type FROM events").fetchall() →
            state = get_current_state(db_path) или events_list = EventLogQuerier(...).query(...)
            через публичный интерфейс.
            Для test_i_m_1_enforced — исключение: патч _FailingConn тестирует атомарность
            транзакции (не state inspection), оставить as-is.
Leverage:   рефакторинг схемы events-таблицы не ломает тесты поведения.
Depends:    M1 (порядок произвольный, но M1 проще — делать первым)
Risks:      get_current_state читает projection через DuckDB; если projection не включает
            нужное поле — тест потребует EventLogQuerier вместо get_current_state.
            Проверить заранее какие поля доступны в SDDState.
```

---

## Risk Notes

- R-1: CommandSpec в тестах — не конструировать `ValidateInvariantsCommand` с `command_id=uuid4()` руками для idempotency-теста. Использовать один и тот же `command_id` в обоих вызовах `execute_sequence`, иначе idempotency-check не сработает.
- R-2: `test_i_m_1_enforced` — `_FailingConn` патчит `commit()` для проверки атомарности. Это не state inspection anti-pattern — это тест транзакционной семантики. Оставить, добавить комментарий `# atomicity test — intentional internal patch`.
- R-3: Масштаб небольшой. Если при поиске других `patch.object(handler, "_check_idempotent")` найдётся больше 5 файлов — остановиться и сообщить человеку перед продолжением.
