# Plan_v28 — Phase 28: Write Kernel Guard & Event Invalidation

Status: DRAFT
Spec: .sdd/specs/Spec_v28_WriteKernelGuard.md

---

## Milestones

### M1: EventInvalidatedEvent — domain event type

```text
Spec:       §2 BC-WG-1, §3 Domain Events, §5 Invariants (I-EL-6, C-1)
BCs:        BC-WG-1
Invariants: I-EL-6, C-1
Depends:    — (baseline: Phase 27 COMPLETE)
Risks:      Порядок регистрации в V1_L1_EVENT_TYPES и _KNOWN_NO_HANDLER важен;
            ошибка ломает C-1 invariant check при импорте
```

Добавить в `src/sdd/core/events.py`:
- `EventInvalidatedEvent` (frozen dataclass, поля: `target_seq`, `reason`, `invalidated_by_phase`)
- Регистрация через `register_l1_event_type("EventInvalidated", handler=None)`
  → попадает в `_KNOWN_NO_HANDLER`

### M2: Replay pre-filter с индексом и per-instance кэшем

```text
Spec:       §2 BC-WG-2, §5 I-INVALID-2, I-INVALID-CACHE-1
BCs:        BC-WG-2
Invariants: I-INVALID-2, I-INVALID-CACHE-1
Depends:    M1 (EventInvalidated должен быть в event catalog)
Risks:      Кэш-сброс в append() критичен; без него stale-кэш допустит воспроизведение
            невалидных событий в рамках одного инстанса
```

Изменения:
- `src/sdd/infra/db.py` → `ensure_sdd_schema`: добавить `CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type)`
- `src/sdd/infra/event_store.py`:
  - Поле `_invalidated_cache: frozenset[int] | None = None`
  - Метод `_get_invalidated_seqs() → frozenset[int]` с per-instance кэшем
  - `replay()` — добавить pre-filter: исключать seq ∈ `_get_invalidated_seqs()`, DEBUG лог при фильтрации

### M3: Kernel guard — EventStore.append() + sdd_append()

```text
Spec:       §2 BC-WG-3, BC-WG-4, §5 I-DB-WRITE-2, I-DB-WRITE-3, §6 Pre/Post Conditions
BCs:        BC-WG-3, BC-WG-4
Invariants: I-DB-WRITE-2, I-DB-WRITE-3, I-KERNEL-WRITE-1 (принуждение)
Depends:    M2 (сброс _invalidated_cache интегрирован в append())
Risks:      Bootstrap callers (reconcile_bootstrap.py, bootstrap_complete.py) ДОЛЖНЫ
            передавать allow_outside_kernel="bootstrap"; без этого bootstrap сломается.
            Тесты с tmp_db_path не затронуты — sdd_append guard срабатывает только
            для production DB path.
```

Изменения:
- `src/sdd/infra/event_store.py` → `EventStore.append()`:
  - Добавить параметр `allow_outside_kernel: Literal["bootstrap", "test"] | None = None`
  - При `None` → `assert_in_kernel("EventStore.append")`
  - При значении вне `("bootstrap", "test")` → `ValueError`
  - Сброс `self._invalidated_cache = None` при любом пути
- `src/sdd/infra/event_log.py` → `sdd_append()`:
  - Проверка: `resolved(db_path) == resolved(event_store_file())`
  - Если да — `current_execution_context() != "execute_command"` → `KernelContextError`
- Обновить все легитимные callers `EventStore.append()` вне kernel (bootstrap, reconcile):
  передавать `allow_outside_kernel="bootstrap"`

### M4: invalidate-event REGISTRY command

```text
Spec:       §2 BC-WG-5, §4 Types & Interfaces, §5 I-INVALID-1..4, I-INVALID-IDEM-1
BCs:        BC-WG-5
Invariants: I-INVALID-1, I-INVALID-3, I-INVALID-4, I-INVALID-IDEM-1
Depends:    M1 (EventInvalidatedEvent), M3 (kernel guard в append для самой команды)
Risks:      I-INVALID-4: _EVENT_SCHEMA lookup должен быть актуальным; тест
            test_invalidate_state_event_raises должен покрывать TaskImplemented
```

Изменения:
- `src/sdd/commands/invalidate_event.py` (новый файл):
  - `InvalidateEventCommand` (target_seq: int, reason: str)
  - `InvalidateEventHandler.handle()` — guard-цепочка I-INVALID-1 → I-INVALID-3 → I-INVALID-4 → I-INVALID-IDEM-1
- `src/sdd/commands/registry.py` → добавить `REGISTRY["invalidate-event"]` с `CommandSpec`
  (actor="human", projection=NONE, idempotent=True, requires_active_phase=False)
- `src/sdd/cli.py` → зарегистрировать subcommand `invalidate-event --seq N --reason "..."`

### M5: Incident backfill + интеграционный тест

```text
Spec:       §2 BC-WG-6, §9 Test 14, §7 UC-28-1
BCs:        BC-WG-6
Invariants: BC-WG-6 acceptance: sdd show-state 2>&1 | grep -c "WARNING.*unknown event_type" == 0
Depends:    M4 (invalidate-event команда реализована)
Risks:      Backfill выполняется в production EventLog; команда идемпотентна, но
            порядок вызовов для каждого из 6 seq не важен
```

Действия:
- `tests/integration/test_incident_backfill.py` (новый файл):
  - `test_incident_backfill_no_warnings` — end-to-end: write 6 TestEvent → baseline WARNING
    → invalidate all 6 → replay без WARNING (I-INVALID-2 + BC-WG-6)
- Выполнить backfill в production EventLog:
  ```bash
  for seq in 25970 25973 25974 25975 25976 25977; do
    sdd invalidate-event --seq $seq \
      --reason "direct write via bash (I-KERNEL-WRITE-1 violation, Phase 27 close, 2026-04-25)"
  done
  ```
- Финальная проверка: `sdd show-state` без единого WARNING `unknown event_type='TestEvent'`

---

## Risk Notes

- R-1: **Bootstrap regression** — `reconcile_bootstrap.py` и `bootstrap_complete.py` вызывают
  `EventStore.append()` вне `execute_command`. После M3 ДОЛЖНЫ передавать
  `allow_outside_kernel="bootstrap"`. Риск: bootstrap pipeline ломается при деплое.
  Митигация: grep всех callers `\.append(` до завершения M3; добавить тест
  `test_write_kernel_guard_bootstrap_bypass`.

- R-2: **Production backfill (M5)** — 6 seq в production EventLog. Команда `invalidate-event`
  идемпотентна (I-INVALID-IDEM-1), повторный вызов — noop. Риск: seq уже не существуют
  (unlikely — EventLog append-only). Митигация: `sdd query-events --type TestEvent`
  перед backfill для проверки наличия.

- R-3: **_KNOWN_NO_HANDLER coverage** — если `TestEvent` окажется в `_EVENT_SCHEMA`
  (невозможно по текущей схеме, но при рефакторинге core/events.py), I-INVALID-4 заблокирует
  backfill. Митигация: unit test `test_invalidate_state_event_raises` покрывает TaskImplemented;
  отдельная проверка `TestEvent not in _EVENT_SCHEMA` в тесте T-2803.

- R-4: **Spec file location discrepancy** — `Phases_index.md` строка 28 указывает
  `specs_draft/Spec_v28_WriteKernelGuard.md` со статусом DRAFT, но файл находится в
  `specs/` (approved). Требуется обновление `Phases_index.md` до PLANNED/ACTIVE
  при активации фазы.
