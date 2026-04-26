# Spec_v29_StreamlinedWorkflow — Streamlined Session Flow

Status: DRAFT — подлежит human approval перед включением в план фазы
Baseline: CLAUDE.md §SESSION, §ROLES; norm_catalog.yaml NORM-ACTOR-001
Discovered: Phase 27 close, 2026-04-25

---

## 0. Проблема

Текущая модель требует от человека выполнять CLI-команды между сессиями:

```
Human: "PLAN Phase N"               → LLM пишет план
Human: (вручную) sdd activate-phase N   ← лишний шаг
Human: "DECOMPOSE Phase N"          → LLM пишет TaskSet
Human: (вручную) sdd activate-phase N   ← лишний шаг
```

Friction points:
- F-1: `sdd activate-phase N` требуется вручную дважды
- F-2: Phases_index.md не обновляется автоматически после PLAN
- F-3: `--tasks` флаг документирован неверно (устарел)
- F-4: Цикличная зависимость: activate-phase требует TaskSet → TaskSet создаётся в
  DECOMPOSE → DECOMPOSE precondition требовал активированный план

Корневая причина: **actor model** объявляет `activate-phase` human-only (NORM-ACTOR-001),
хотя реальный human gate — объявление сессии в чате, а не выполнение CLI.

---

## 1. Целевая модель

### «Human Declares, LLM Executes»

```
Человек выполняет ТОЛЬКО:
  1. DRAFT_SPEC vN    → объявляет сессию + approves spec (переносит файл)
  2. PLAN Phase N     → объявляет сессию
  3. DECOMPOSE Phase N → объявляет сессию
  4. IMPLEMENT T-NNN  → объявляет сессию
  5. VALIDATE T-NNN   → опционально

Всё остальное — LLM автоматически, с явным выводом каждого действия.
```

### Принцип явности auto-actions (I-SESSION-VISIBLE-1)

Каждое автоматическое CLI действие LLM MUST отображать в ответе:

```
[Auto-action] sdd activate-phase 27
[Result] Phase 27 activated. Tasks detected: 4
[State] phase.current=27, phase.status=ACTIVE
```

Скрытые мутации состояния запрещены.

---

## 2. Causal Chain — SessionDeclaredEvent

### Проблема без события

```
[нет события]
→ PhaseInitialized(actor="human", executed_by="llm")   ← missing causal link
```

EventLog теряет причинно-следственную связь. Это нарушает event sourcing (I-1).

### Решение: новый event type

```python
@dataclass(frozen=True)
class SessionDeclaredEvent(DomainEvent):
    """Captures human's session declaration — causal anchor for auto-actions.

    Emitted by LLM immediately on session start, before any auto-action.
    caused_by_meta_seq: None (this IS the root cause)
    """
    event_type: str = "SessionDeclared"
    session_type: str   # "PLAN" | "DECOMPOSE" | "IMPLEMENT" | "VALIDATE" | ...
    phase_id: int
    actor: str = "human"   # always "human" — human declared the session
```

### Causal chain с событием

```
H: "DECOMPOSE Phase 27"
→ LLM emits: SessionDeclared(session_type="DECOMPOSE", phase_id=27, actor="human", seq=X)
→ LLM executes: sdd activate-phase 27
   → PhaseInitialized(actor="human", executed_by="llm", caused_by_meta_seq=X)

EventLog:
  seq=X   SessionDeclared(DECOMPOSE, phase_id=27, actor=human)
  seq=X+1 PhaseStarted(phase_id=27, caused_by_meta_seq=X)
  seq=X+2 PhaseInitialized(phase_id=27, caused_by_meta_seq=X)
```

Causal chain полная. Audit trail честный.

### SessionDeclaredEvent — уровень и replay

- Level: L1 (replay/SSOT — сохраняется навсегда)
- Reducer: read-only при replay (no state mutation — информационное событие)
- Не меняет `phase_current`, не меняет `phase_status`

---

## 3. Actor Model — Revision

### Проблема с actor="llm-session"

Смешение двух ролей:
- Кто инициировал (человек объявил сессию)
- Кто исполнил (LLM вызвал CLI)

### Решение: actor + executed_by

```python
# В PhaseInitialized payload:
{
  "actor": "human",          # инициатор = человек (объявил сессию)
  "executed_by": "llm",      # исполнитель = LLM (авто-вызов CLI)
  "caused_by_meta_seq": X    # ссылка на SessionDeclaredEvent
}
```

```python
# В activate_phase.py — без изменения VALID_ACTORS:
VALID_ACTORS = {"human"}   # actor всегда "human"

# Добавить опциональный параметр executed_by:
parser.add_argument("--executed-by", default=None,
                    help="llm | None; injected into payload for audit")
```

**Преимущество:** handler validation не меняется (`actor="human"` везде). Различие
между ручной и авто-активацией читается из `payload.executed_by`.

---

## 4. Plan Integrity Check перед DECOMPOSE

### Проблема без проверки

```
Plan_vN.md (черновик, неполный)
→ DECOMPOSE
→ sdd activate-phase N   ← фаза активирована на непроверенном плане
```

### Решение: content check + plan_hash

**DECOMPOSE precondition (revised):**

```
- Plan_vN.md EXISTS in .sdd/plans/
- Plan_vN.md содержит обязательные секции: ## Milestones + ≥1 milestone + ## Risk Notes
- Spec_vN.md exists in .sdd/specs/
```

(Убрать: "Plan Status = ACTIVE" — это была ложная safety)

**plan_hash в PhaseInitialized:**

```python
# Добавить поле в PhaseInitializedEvent (EV-2: additive, backward-compatible):
plan_hash: str   # sha256(Plan_vN.md content)[:16]
```

Фиксирует, на каком точном содержании плана была активирована фаза. При audit
можно проверить: `sha256(current Plan_v27.md) == PhaseInitialized.plan_hash`.

---

## 5. Phases_index Consistency

### Проблема

После авто-обновления Phases_index.md нет проверки консистентности с EventLog.
Phases_index может стать "вторым truth source" (нарушение I-1).

### Решение: post-write validation

После записи в Phases_index.md LLM MUST выполнить:

```python
# Проверка: все phases_known из EventLog есть в Phases_index
known_from_events = {p.phase_id for p in PhaseInitialized events}
known_from_index = {row.id for row in Phases_index rows}
assert known_from_events.issubset(known_from_index), "Phases_index desync"
```

Phases_index остаётся **derived view** (как State_index.yaml), не truth source.
Добавить инвариант I-PHASES-INDEX-1:

```
I-PHASES-INDEX-1:
  phases_known ⊆ Phases_index.ids
  Violation → LLM MUST update Phases_index before proceeding
```

---

## 6. Revised Session FSM

```
DRAFT_SPEC vN
  └─ LLM AUTO: emit SessionDeclared(DRAFT_SPEC, phase_id=N)
  └─ LLM: создаёт .sdd/specs_draft/Spec_vN.md
  └─ Human: approves (переносит в .sdd/specs/) ← ЕДИНСТВЕННЫЙ ручной шаг
  └─ LLM: [Auto-action] подтверждает перенос через sdd show-spec --phase N

PLAN Phase N
  └─ LLM AUTO: emit SessionDeclared(PLAN, phase_id=N)
  └─ LLM: пишет Plan_vN.md
  └─ LLM AUTO: обновляет Phases_index.md → валидирует консистентность (I-PHASES-INDEX-1)
  └─ LLM MUST display: "[Auto-action] Phases_index updated. [Result] Phase N = PLANNED"
  └─ → предлагает: "Готово. Следующий шаг: DECOMPOSE Phase N"

DECOMPOSE Phase N
  └─ Preconditions: Plan_vN.md EXISTS + content check + Spec_vN.md in .sdd/specs/
  └─ LLM AUTO: emit SessionDeclared(DECOMPOSE, phase_id=N)
  └─ LLM: пишет TaskSet_vN.md
  └─ LLM AUTO: [Auto-action] sdd activate-phase N --executed-by llm
  └─ LLM AUTO: [Auto-action] sdd show-state
  └─ → предлагает: "Phase N активирована. Задач: M. Следующий шаг: IMPLEMENT T-N01"

IMPLEMENT T-NNN
  └─ LLM AUTO: emit SessionDeclared(IMPLEMENT, phase_id=N)
  └─ LLM: реализует код
  └─ LLM AUTO: sdd complete T-NNN              ← уже было
  └─ → если есть следующая TODO задача: предлагает IMPLEMENT T-NNN+1
  └─ → если все DONE: предлагает VALIDATE

VALIDATE T-NNN
  └─ LLM AUTO: emit SessionDeclared(VALIDATE, phase_id=N)
  └─ LLM: проверяет тесты и инварианты
  └─ LLM AUTO: sdd validate T-NNN --result PASS|FAIL  ← уже было
```

---

## 7. Race Conditions

`execute_command` использует optimistic lock (`expected_head=head_seq`, I-OPTLOCK-1).
Если между записью TaskSet и `activate-phase` другой процесс пишет в EventLog:
`activate-phase` упадёт с `StaleStateError` (exit 1). LLM MUST обработать это через
recovery (sessions/recovery.md RP-STALE).

Никакой дополнительной защиты не требуется — I-OPTLOCK-1 покрывает race conditions.

---

## 8. Scope

### In-Scope (BC-SW-1..9)

| BC | Что | Файл |
|----|-----|------|
| BC-SW-1 | `SessionDeclaredEvent` dataclass | `src/sdd/core/events.py` |
| BC-SW-2 | `sdd record-session` CLI — emit SessionDeclaredEvent | `src/sdd/commands/record_session.py` (новый) |
| BC-SW-3 | Reducer: SessionDeclared → DEBUG log only, no state mutation | `src/sdd/domain/state/reducer.py` |
| BC-SW-4 | `activate_phase.py` — добавить `--executed-by` arg; inject в payload | `src/sdd/commands/activate_phase.py` |
| BC-SW-5 | `PhaseInitializedEvent` — добавить `plan_hash: str` (EV-2 additive) | `src/sdd/core/events.py` |
| BC-SW-6 | `activate_phase.py` — вычислять `plan_hash` перед emit | `src/sdd/commands/activate_phase.py` |
| BC-SW-7 | `sessions/decompose.md` — убрать `Plan Status = ACTIVE`; добавить content check + Auto-actions | `.sdd/docs/sessions/decompose.md` |
| BC-SW-8 | `sessions/plan-phase.md` — добавить Phases_index Auto-action + PI-6 | `.sdd/docs/sessions/plan-phase.md` |
| BC-SW-9 | `tool-reference.md` — исправить `--tasks`; добавить `record-session`; добавить `--executed-by` | `.sdd/docs/ref/tool-reference.md` |
| BC-SW-10 | `CLAUDE.md §SESSION FSM` + `§ROLES` + `§INV` | `CLAUDE.md` |

### Out of Scope

- Spec approval (перенос файла) — остаётся ручным; content review
- `sdd switch-phase` — навигация; не меняется
- Ретроспективное добавление SessionDeclared в старые фазы

---

## 9. Invariants

| ID | Statement |
|----|-----------|
| I-SESSION-AUTO-1 | LLM MUST run `sdd activate-phase N --executed-by llm` automatically at end of DECOMPOSE. No human CLI step required. |
| I-SESSION-DECLARED-1 | LLM MUST emit `SessionDeclared` event at start of every session (PLAN/DECOMPOSE/IMPLEMENT/VALIDATE) before any auto-action. |
| I-SESSION-VISIBLE-1 | Every auto-invoked CLI MUST be shown in LLM output as `[Auto-action] ... / [Result] ...`. Silent mutations forbidden. |
| I-SESSION-ACTOR-1 | `activate-phase` MUST always pass `actor="human"`. `executed_by="llm"` goes into payload field, not actor field. |
| I-SESSION-PI-6 | LLM MUST update Phases_index.md at end of PLAN session. Must validate I-PHASES-INDEX-1 after update. |
| I-PHASES-INDEX-1 | `phases_known ⊆ Phases_index.ids`. Violation → LLM updates Phases_index before proceeding. |
| I-SESSION-PLAN-HASH-1 | `PhaseInitializedEvent.plan_hash` MUST equal `sha256(Plan_vN.md)[:16]` at activation time. |

---

## 10. Verification

| # | Тест | Инвариант |
|---|------|-----------|
| 1 | `test_session_declared_emitted`: после record-session → SessionDeclared в EventLog | I-SESSION-DECLARED-1 |
| 2 | `test_session_declared_no_state_mutation`: replay с SessionDeclared → state не меняется | BC-SW-3 |
| 3 | `test_activate_phase_executed_by_llm`: `--executed-by llm` → payload содержит `executed_by="llm"` | I-SESSION-ACTOR-1 |
| 4 | `test_activate_phase_plan_hash`: plan_hash в PhaseInitialized совпадает с sha256(Plan_vN.md) | I-SESSION-PLAN-HASH-1 |
| 5 | `test_phases_index_consistency`: phases_known из EventLog ⊆ Phases_index | I-PHASES-INDEX-1 |

---

## 11. Implementation Order

```
BC-SW-1: SessionDeclaredEvent dataclass (events.py)
BC-SW-3: Reducer: SessionDeclared → no-op (reducer.py)
BC-SW-2: sdd record-session CLI (commands/record_session.py)
BC-SW-5: PhaseInitializedEvent.plan_hash (events.py, additive)
BC-SW-4+6: activate_phase.py — --executed-by + plan_hash computation
BC-SW-7: sessions/decompose.md
BC-SW-8: sessions/plan-phase.md
BC-SW-9: tool-reference.md
BC-SW-10: CLAUDE.md
Tests: BC-SW-* verification suite
```
