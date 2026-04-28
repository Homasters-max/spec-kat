# Plan_v35 — Phase 35: Test Harness Elevation

Status: DRAFT
Spec: specs/Spec_v35_TestHarnessElevation.md

---

## Logical Context

```
type: none
rationale: "Стандартная фаза улучшения качества тестов. Устраняет хрупкие анти-паттерны
            в тестах поведения команд без изменений src/."
```

---

## Milestones

### M1: BC-35-1 — Заменить patch.object → execute_sequence в крупных файлах

```text
Spec:       §2 BC-35-1, §5 I-TEST-IDEM-1
BCs:        BC-35-1
Invariants: I-TEST-IDEM-1
Файлы:      tests/unit/commands/test_validate_invariants.py (~20 вхождений)
            tests/unit/commands/test_check_dod.py (6 вхождений)
Подход:     Для каждого теста с patch.object(handler, "_check_idempotent"):
            1. cmd_id = uuid4(); cmd = Command(command_id=cmd_id, ...)
            2. events1, _ = execute_sequence([(spec, cmd)], db_path=db_path)
            3. assert len(events1) > 0
            4. cmd2 = Command(command_id=cmd_id, ...); тот же command_id
            5. events2, _ = execute_sequence([(spec, cmd2)], db_path=db_path)
            6. assert events2 == []
            spec = REGISTRY["<name>"].spec — не конструировать вручную
Depends:    — (harness/api.py::execute_sequence уже работает)
Risks:      R-1: command_id ДОЛЖЕН быть одинаковым в обоих вызовах
```

### M2: BC-35-1 — Заменить patch.object → execute_sequence в малых файлах

```text
Spec:       §2 BC-35-1, §5 I-TEST-IDEM-1
BCs:        BC-35-1
Invariants: I-TEST-IDEM-1
Файлы:      tests/unit/commands/test_validate_timeout.py (2 вхождения)
            tests/unit/commands/test_amend_plan.py (1 вхождение)
            tests/unit/commands/test_validate_invariants_v31.py (1 вхождение)
            tests/unit/commands/test_sync_state.py (1 вхождение, R-3 — добавлен после обнаружения)
Подход:     Тот же double-call паттерн, что в M1.
            Добавить комментарий # subprocess boundary — intentional
            там где patch("subprocess.Popen") оставляется нетронутым.
Depends:    M1 (паттерн отработан)
Risks:      Проверить что REGISTRY содержит нужные команды для test_amend_plan
            и test_validate_invariants_v31.
```

### M3: BC-35-2 — Заменить raw SQL state assertions → EventLogQuerier

```text
Spec:       §2 BC-35-2, §5 I-TEST-STATE-1
BCs:        BC-35-2
Invariants: I-TEST-STATE-1
Файлы:      tests/unit/infra/test_metrics.py (строки 22-34 и 72-73)
Подход:     test_record_metric_batch_with_task_completed (строки 22-34):
              conn.execute("SELECT event_type, level FROM events ...") →
              from sdd.infra.event_query import EventLogQuerier
              EventLogQuerier(tmp_db_path).query() → проверить по event_type атрибуту
            test_i_m_1_enforced (строка 72-73):
              conn.execute("SELECT event_type FROM events") →
              EventLogQuerier(tmp_db_path).query()
              Добавить # atomicity test — intentional internal patch к _FailingConn
              (_FailingConn класс оставить нетронутым)
Depends:    M1, M2 (порядок произвольный)
Risks:      R-2: если нужное поле отсутствует в SDDState — EventLogQuerier,
            не get_current_state; проверить заранее
```

---

## Risk Notes

- R-1: `command_id` ДОЛЖЕН быть одинаковым в обоих вызовах `execute_sequence`. Разные `uuid4()` — idempotency-check не сработает (EventStore deduplication по `command_id`).
- R-2: `_FailingConn` в `test_i_m_1_enforced` — тест атомарности транзакции, не state inspection. Оставить. Добавить `# atomicity test — intentional internal patch`.
- R-3: Итого 6 файлов с `patch.object(handler, "_check_idempotent")` — порог >5 сработал, человек уведомлён, `test_sync_state.py` добавлен в scope явно. R-3 закрыт.
