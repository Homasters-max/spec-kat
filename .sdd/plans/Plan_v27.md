# Plan_v27 — Phase 27: Command Idempotency Classification

Status: DRAFT
Spec: specs/Spec_v27_CommandIdempotency.md

---

## Milestones

### M1: CommandSpec Extension + REGISTRY Classification

```text
Spec:       §3 — CommandSpec расширение (BC-CI-1); §3 switch-phase REGISTRY entry (BC-CI-3)
BCs:        BC-CI-1, BC-CI-3
Invariants: I-CMD-IDEM-1 (struct contract), I-IDEM-SCHEMA-1 (preserved)
Depends:    —
Risks:      BC-CI-1 добавляет поле с default=True — все существующие REGISTRY entries
            получают idempotent=True автоматически, switch-phase явно переопределяется.
            Риск регрессии: если другие команды ошибочно получили бы False — но default
            гарантирует обратную совместимость. Нарушение I-KERNEL-EXT-1 невозможно:
            поле добавляется с default (non-breaking extension).
```

Deliverables:
- `src/sdd/commands/registry.py` — `CommandSpec` dataclass: добавлено поле
  `idempotent: bool = True` (после `description`)
- `src/sdd/commands/registry.py` — `REGISTRY["switch-phase"]`: установлен `idempotent=False`
- Все остальные REGISTRY entries: `idempotent` не указан явно (наследуют `True` от default)

---

### M2: execute_command — Non-Idempotent Path

```text
Spec:       §3 — execute_command Step 5 (BC-CI-2); §5 BC-CI-2 Pre/Post
BCs:        BC-CI-2
Invariants: I-CMD-IDEM-1, I-CMD-NAV-1, I-OPTLOCK-1 (preserved), I-KERNEL-WRITE-1 (preserved)
Depends:    M1 (spec.idempotent field must exist)
Risks:      Единственное место изменения — Step 5 в execute_command. Риск:
            случайная передача None вместо uuid4() нарушит traceability (I-CMD-IDEM-1).
            Митигация: effective_command_id = command_id if spec.idempotent else str(uuid4()).
            expected_head НЕ изменяется — I-OPTLOCK-1 сохраняется без условий.
            uuid4() импортируется из stdlib uuid — нет новых зависимостей.
```

Deliverables:
- `src/sdd/commands/registry.py` — `execute_command` Step 5:
  ```python
  from uuid import uuid4
  effective_command_id = command_id if spec.idempotent else str(uuid4())
  EventStore(_db).append(
      handler_events,
      source=spec.handler_class.__module__,
      command_id=effective_command_id,
      expected_head=head_seq,
  )
  ```
- `command_id=None` НИКОГДА не передаётся в `EventStore.append`

---

### M3: Invariant Registration in CLAUDE.md

```text
Spec:       §4 — Новые инварианты (BC-CI-4); §4 Temporal semantics
BCs:        BC-CI-4
Invariants: I-CMD-IDEM-1, I-CMD-IDEM-2, I-CMD-NAV-1
Depends:    M2 (инварианты документируют реализованное поведение)
Risks:      CLAUDE.md §INV — append-only операция, нет риска регрессии.
            Порядок добавления: после I-PHASE-SNAPSHOT-4 (последний текущий инвариант).
            Формулировки MUST совпадать со Spec_v27 §4 дословно.
```

Deliverables:
- `CLAUDE.md` §INV — добавлены три инварианта:
  - `I-CMD-IDEM-1`: `CommandSpec.idempotent=False` → `command_id=uuid4()`, не None
  - `I-CMD-IDEM-2`: handler-level idempotency MUST NOT override spec-level
  - `I-CMD-NAV-1`: Navigation events order-sensitive; MUST NOT be deduplicated

---

### M4: Test Suite

```text
Spec:       §6 — Verification (BC-CI-5); §5 BC-CI-5 Pre/Post
BCs:        BC-CI-5
Invariants: I-CMD-IDEM-1, I-IDEM-SCHEMA-1, I-OPTLOCK-1
Depends:    M1, M2 (тесты верифицируют реализацию)
Risks:      Тесты используют execute_and_project с tmp_path DB (I-DB-TEST-1).
            test_switch_phase_non_idempotent требует двух последовательных вызовов
            switch-phase(A→B) и проверки count=2 в EventLog.
            Precondition теста: нужны две инициализированные фазы A и B в fixtures.
```

Deliverables:
- `tests/unit/commands/test_command_idempotency.py` — 4 теста:
  1. `test_switch_phase_non_idempotent`: 2× switch-phase(A→B) → 2 события в EventLog (I-CMD-IDEM-1)
  2. `test_complete_still_idempotent`: 2× complete(T-NNN) → 1 событие в EventLog (I-IDEM-SCHEMA-1)
  3. `test_switch_phase_optlock_preserved`: optimistic lock активен при idempotent=False (I-OPTLOCK-1)
  4. `test_command_spec_idempotent_default`: все REGISTRY entries кроме switch-phase имеют idempotent=True

---

## Risk Notes

- R-1: **uuid4() vs payload-hash для traceability** — uuid4() гарантирует уникальность,
  но correlation по command_id между несколькими вызовами одной команды невозможна.
  Это приемлемо: navigation commands не нуждаются в cross-call correlation.
  compute_command_id() вызывается для всех команд (audit trail), но effective_command_id
  для append — только uuid4() для non-idempotent. Две переменные, одна используется для dedup.

- R-2: **Handler-level vs Spec-level idempotency** — если SwitchPhaseHandler содержит
  `_check_idempotent()` с noop-логикой, она нарушит I-CMD-IDEM-2. При реализации M1/M2
  нужно проверить handler и удалить конфликтующую логику если найдена.

- R-3: **Phases_index gap** — индекс пропускает фазы 17-25. Это технический долг вне
  scope Phase 27. Не исправлять в рамках этой фазы.
