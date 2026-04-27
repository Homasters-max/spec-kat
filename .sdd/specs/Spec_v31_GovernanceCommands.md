# Spec_v31 — Phase 31: Governance Commands

Status: Draft
Baseline: Spec_v30_DocFixes.md

---

## 0. Goal

Phase 30 устранила документационный дрейф. Phase 31 закрывает три архитектурных
gap, выявленных в dev-cycle-map.md §5.5–5.6 и §1:

1. **approve-spec**: человек сейчас одобряет спек через ручной `mv` без CLI-команды
   и без события в EventLog. Нет `SpecApproved` в audit trail.

2. **amend-plan**: `Plan_vN.md` не защищён после DECOMPOSE. Тихое редактирование
   файла создаёт drift между `plan_hash` (зафиксированным в `PhaseInitialized`)
   и текущим содержимым. Нет инварианта иммутабельности.

3. **Optional[int] phase_id**: `SessionDeclaredEvent` требует `phase_id: int`,
   но в сессии `DRAFT_SPEC` фаза ещё не существует в EventLog. Форвардная ссылка
   нарушает формальную целостность.

4. **_check_i_sdd_hash**: норма `NORM-GATE-002` описывает проверку
   `sha256(Spec_vN.md) == spec_hash` в `SpecApproved` payload, но функция
   `_check_i_sdd_hash` не реализована в `validate_invariants.py`. Норма
   декларирует enforcement которого нет.

Принцип: **Human gate сохранён** — `sdd approve-spec` запускает человек явно.
NORM-ACTOR-001 не меняется. `approve-spec` — human CLI action, не LLM auto-action.

---

## 1. Scope

### In-Scope

- **BC-31-1**: `SpecApproved` dataclass + `sdd approve-spec --phase N` command
- **BC-31-2**: `PlanAmended` dataclass + `sdd amend-plan --phase N --reason "..."` command + `I-PLAN-IMMUTABLE-AFTER-ACTIVATE`
- **BC-31-3**: `SessionDeclaredEvent.phase_id: Optional[int]` — None для DRAFT_SPEC + `I-SESSION-PHASE-NULL-1`
- **BC-31-4**: `_check_i_sdd_hash` в `validate_invariants.py`

### Out of Scope

- PostgreSQL migration — Phase 32
- `PlanActivated` CLI command — вне scope
- Multi-project support — Phase 32
- `InvariantRegistered` / `InvariantUpdated` events — Phase 32

---

## 2. Architecture / BCs

### BC-31-1: SpecApproved + sdd approve-spec

**Новый dataclass** в `src/sdd/core/events.py`:
```python
@dataclass(frozen=True)
class SpecApproved(DomainEvent):
    event_type: str = "SpecApproved"
    phase_id: int = 0
    spec_hash: str = ""      # sha256(Spec_vN.md)[:16]
    actor: str = "human"
    spec_path: str = ""      # относительный путь в .sdd/specs/
```

**Новый файл** `src/sdd/commands/approve_spec.py`:
```python
# CommandSpec
approve_spec_spec = CommandSpec(
    name="approve-spec",
    actor="human",
    idempotent=False,
    description="Emit SpecApproved event; Write Kernel moves spec_draft → specs post-append"
)

# Handler (I-HANDLER-PURE-1: handle() возвращает только events — никаких side-effects)
class ApproveSpecHandler:
    def handle(self, command: ApproveSpecCommand) -> list[DomainEvent]:
        # 1. Проверить: specs_draft/Spec_vN_*.md существует
        # 2. Проверить: specs/Spec_vN_*.md НЕ существует (защита от перезаписи)
        # 3. Вычислить sha256(file)[:16]
        # 4. return [SpecApproved(phase_id=N, spec_hash=hash, spec_path=...)]
        #    mv НЕ выполняется в handle() — см. Write Kernel post-event hook ниже

# Write Kernel post-event hook (execute_and_project, вызывается после EventStore.append):
#   if isinstance(event, SpecApproved):
#       shutil.move(".sdd/specs_draft/" + event.spec_path,
#                   ".sdd/specs/" + event.spec_path)
#       # При ошибке mv: emit ErrorEvent, raise — event уже в EventLog, аудит сохранён
```

**Регистрация** в `src/sdd/commands/registry.py`:
```python
REGISTRY["approve-spec"] = (approve_spec_spec, ApproveSpecHandler)
```

**CLI usage:**
```bash
sdd approve-spec --phase N
```

**Actor model:** `actor="human"` — человек явно запускает команду.
NORM-ACTOR-001 не меняется: норма запрещает LLM эмитить SpecApproved,
`approve-spec` — human-only CLI action вне LLM auto-action механизма.

**Guard:** `approve_spec` command MUST NOT accept `actor="llm"`.
Это guard в handler, не отдельная норма.

---

### BC-31-2: PlanAmended + sdd amend-plan + I-PLAN-IMMUTABLE-AFTER-ACTIVATE

**Новый инвариант** в CLAUDE.md §INV:
```
I-PLAN-IMMUTABLE-AFTER-ACTIVATE:
Plan_vN.md MUST NOT be modified after activate-phase N has been executed.
Any change requires sdd amend-plan --phase N --reason "..." which emits
PlanAmended(new_plan_hash). Direct file edits without CLI command are a
protocol violation.
Declared (not enforced by file system — relies on protocol compliance).
```

**Новый dataclass** в `src/sdd/core/events.py`:
```python
@dataclass(frozen=True)
class PlanAmended(DomainEvent):
    event_type: str = "PlanAmended"
    phase_id: int = 0
    new_plan_hash: str = ""   # sha256(Plan_vN.md)[:16] после изменения
    reason: str = ""
    actor: str = "human"
```

**Новый файл** `src/sdd/commands/amend_plan.py`:
```python
# CommandSpec
amend_plan_spec = CommandSpec(
    name="amend-plan",
    actor="human",
    idempotent=False,
    description="Record plan amendment after post-activation edit"
)

# Handler
class AmendPlanHandler:
    def handle(self, command: AmendPlanCommand) -> list[DomainEvent]:
        # 1. Проверить: Plan_vN.md существует
        # 2. Проверить: фаза N активирована (phase_status != PLANNED)
        # 3. Вычислить sha256(Plan_vN.md)[:16]
        # 4. return [PlanAmended(phase_id=N, new_plan_hash=hash, reason=reason)]
```

**Регистрация** в `src/sdd/commands/registry.py`.

**Reducer:** `PlanAmended` → обновить `plan_hash` в `phases_snapshots[phase_id]`.

**CLI usage:**
```bash
sdd amend-plan --phase N --reason "Added T-NNN after scope change"
```

**Примечание:** `sdd amend-plan` НЕ проверяет содержимое изменений — только
фиксирует факт и новый hash. Это «lightweight» вариант (вариант A из
архитектурного разбора).

---

### BC-31-3: SessionDeclaredEvent.phase_id Optional[int]

**Изменение** в `src/sdd/core/events.py`:
```python
# До:
@dataclass(frozen=True)
class SessionDeclaredEvent(DomainEvent):
    phase_id: int = 0

# После:
@dataclass(frozen=True)
class SessionDeclaredEvent(DomainEvent):
    phase_id: Optional[int] = None
```

**Новый инвариант** в CLAUDE.md §INV:
```
I-SESSION-PHASE-NULL-1:
SessionDeclared events with session_type="DRAFT_SPEC" MUST use phase_id=None.
phase_id=None is reserved exclusively for pre-phase sessions.
Reducer MUST treat phase_id=None in SessionDeclared as a no-op (no state mutation).
All other session types MUST use a real phase_id ∈ phases_known.
```

**Reducer:** `case SessionDeclared` — уже no-op (DEBUG log, return state).
Изменение не требует логики в reducer, только type annotation.

**Backward compatibility:** существующие события с `phase_id: int` десериализуются
корректно — `int` является подтипом `Optional[int]`.

**CLI:** `sdd record-session --type DRAFT_SPEC --phase 0` остаётся как fallback
CLI-интерфейс (0 принимается как sentinel). Внутри handler: `phase_id=None`
для `session_type=DRAFT_SPEC`.

---

### BC-31-4: _check_i_sdd_hash в validate_invariants.py

**Реализация** в `src/sdd/commands/validate_invariants.py`:
```python
def _check_i_sdd_hash(self, phase_id: int) -> CheckResult:
    """
    Verifies: sha256(Spec_vN.md) == spec_hash in SpecApproved event payload.

    Steps:
    1. Find latest SpecApproved event for phase_id in EventLog
    2. Read spec_hash from event payload
    3. Read current Spec_vN.md file, compute sha256[:16]
    4. Compare: if mismatch → FAIL with details
    5. If no SpecApproved event found → SKIP (spec not yet approved)
    """
```

**Вызов:** `sdd validate-invariants --check I-SDD-HASH --phase N`

**Норма уже существует** в `norm_catalog.yaml` (check_mechanism ссылается на
эту функцию). Phase 31 реализует то, что норма декларировала.

---

## 3. Domain Events

| Event | Emitter | Description |
|-------|---------|-------------|
| `SpecApproved` | `ApproveSpecHandler` | Spec перенесён из specs_draft в specs, hash зафиксирован |
| `PlanAmended` | `AmendPlanHandler` | Plan изменён после активации фазы, новый hash зафиксирован |

`SessionDeclaredEvent` — изменение типа поля, не новое событие.

---

## 4. Types & Interfaces

```python
@dataclass(frozen=True)
class ApproveSpecCommand:
    phase_id: int
    actor: str = "human"

@dataclass(frozen=True)
class AmendPlanCommand:
    phase_id: int
    reason: str
    actor: str = "human"
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-PLAN-IMMUTABLE-AFTER-ACTIVATE | `Plan_vN.md` MUST NOT be modified after `activate-phase N`; changes require `sdd amend-plan` | 31 |
| I-SESSION-PHASE-NULL-1 | `SessionDeclared` with `session_type=DRAFT_SPEC` MUST use `phase_id=None`; reducer treats as no-op | 31 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| NORM-ACTOR-001 | LLM MUST NOT emit SpecApproved — не меняется |
| I-SESSION-DECLARED-1 | LLM MUST emit SessionDeclared at session start |
| I-2 | All write commands via REGISTRY |
| I-HANDLER-PURE-1 | handle() returns events only |

---

## 6. Pre/Post Conditions

### approve-spec

**Pre:**
- `specs_draft/Spec_vN_*.md` существует
- `specs/Spec_vN_*.md` НЕ существует (защита от перезаписи)

**Post:**
- `SpecApproved(phase_id=N, spec_hash=sha256[:16])` в EventLog (Write Kernel: EventStore.append)
- `specs/Spec_vN_*.md` существует (Write Kernel post-event hook: shutil.move после append)
- `specs_draft/Spec_vN_*.md` удалён (Write Kernel post-event hook)

Порядок гарантирован: EventLog append → mv. Откат mv невозможен; ErrorEvent фиксирует сбой.

### amend-plan

**Pre:**
- `plans/Plan_vN.md` существует
- Phase N: `phase_status != PLANNED` (должна быть активирована)

**Post:**
- `PlanAmended(phase_id=N, new_plan_hash=sha256[:16], reason=...)` в EventLog
- `plan_hash` в reducer snapshot для phase N обновлён

---

## 7. Use Cases

### UC-31-1: Human одобряет спек

**Actor:** Human
**Trigger:** Human прочитал `specs_draft/Spec_v32_PostgresMigration.md`, готов утвердить
**Steps:**
1. `sdd approve-spec --phase 32`
2. CLI: вычисляет hash, делает `mv`, эмитит `SpecApproved`
3. `specs/Spec_v32_PostgresMigration.md` создан с правильным hash в EventLog
**Post:** Human объявляет "PLAN Phase 32" — начинается следующий цикл

### UC-31-2: Plan поправлен после DECOMPOSE

**Actor:** Human
**Trigger:** В процессе Phase 32 IMPLEMENT обнаружен gap в плане
**Steps:**
1. Human редактирует `plans/Plan_v32.md`
2. `sdd amend-plan --phase 32 --reason "Added migration rollback milestone"`
3. `PlanAmended` в EventLog с новым hash
**Post:** Аудит-трейл честный, `plan_hash` актуален

### UC-31-3: _check_i_sdd_hash обнаруживает drift

**Actor:** LLM в VALIDATE сессии
**Trigger:** `sdd validate-invariants --check I-SDD-HASH --phase 31`
**Steps:**
1. CLI находит `SpecApproved` для phase 31 в EventLog, читает `spec_hash`
2. Читает текущий `specs/Spec_v31_*.md`, вычисляет sha256[:16]
3. Hashes совпадают → PASS
**Post:** Целостность spec подтверждена

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| Spec_v29 BC-SW (record-session) | reference | Паттерн handler/registry |
| norm_catalog.yaml NORM-GATE-002 | reference | _check_i_sdd_hash реализует существующую норму |

---

## 9. Verification

| # | Проверка | BC |
|---|----------|----|
| 1 | `sdd approve-spec --phase N` → exit 0, SpecApproved в EventLog | BC-31-1 |
| 2 | `sdd approve-spec --phase N` повторно → exit 1 (файл уже в specs/) | BC-31-1 |
| 3 | `sdd amend-plan --phase N --reason "X"` → exit 0, PlanAmended в EventLog | BC-31-2 |
| 4 | `sdd amend-plan --phase N --reason "X"` без активации → exit 1 | BC-31-2 |
| 5 | `from sdd.core.events import SessionDeclaredEvent; e = SessionDeclaredEvent(session_type="DRAFT_SPEC"); assert e.phase_id is None` | BC-31-3 |
| 6 | Replay EventLog с `phase_id=None` → state не изменился | BC-31-3 |
| 7 | `sdd validate-invariants --check I-SDD-HASH --phase N` → PASS при совпадении hash | BC-31-4 |
| 8 | `sdd validate-invariants --check I-SDD-HASH --phase N` → FAIL при расхождении | BC-31-4 |

---

## 10. Out of Scope

| Item | Phase |
|------|-------|
| PostgreSQL migration | Phase 32 |
| Multi-project support | Phase 32 |
| `InvariantRegistered` event + `sdd sync-invariants` | Phase 32 |
| `sdd init-project` | Phase 32 |
| `sdd next-tasks` + dependency graph | Phase 32 |
