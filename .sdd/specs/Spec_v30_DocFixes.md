# Spec_v30 — Phase 30: Documentation Fixes

Status: Draft
Baseline: Spec_v29_StreamlinedWorkflow.md

---

## 0. Goal

Phase 29 ввела новую модель «Human Declares, LLM Executes» и auto-action
`activate-phase --executed-by llm`. В результате три сессионных файла и один
ref-файл содержат устаревшие инструкции из «до-Phase-29» мира, которые прямо
противоречат новым инвариантам I-SESSION-AUTO-1, I-SESSION-ACTOR-1, I-SESSION-VISIBLE-1.

Дополнительно: `dev-cycle-map.md` — living doc, зафиксированный по итогам
Phase 29, содержит нерешённые вопросы (open choices), которые были закрыты
в архитектурном разборе после Phase 29. Их нужно зафиксировать.

Phase 30 устраняет документационный дрейф: никаких изменений в `src/`,
только правки протокольной документации.

---

## 1. Scope

### In-Scope

- **BC-30-1**: `tool-reference.md` — исправить строку 55 (добавить исключение DECOMPOSE auto-action) и строку 57 (описание `executed_by` включает `llm`)
- **BC-30-2**: `decompose.md` — удалить раздел "After TaskSet is Written" полностью (весь раздел дублирует Auto-actions)
- **BC-30-3**: `plan-phase.md` — заменить "activate phase" на "объявить DECOMPOSE Phase N"; удалить `LLM waits.` и `On activation: sdd show-state to confirm new state.`
- **BC-30-4**: `decompose.md` — добавить explicit recovery path для `StaleStateError` в auto-actions (ссылка на RD-2)
- **BC-30-5**: `dev-cycle-map.md` — зафиксировать все решения, закрыть открытые вопросы (§5.5 и §5.6 — design locked)
- **BC-30-6**: `CLAUDE.md` — добавить подраздел `### Declared (not enforced)` с двумя задекларированными инвариантами

### Out of Scope

- Новые CLI-команды (`approve-spec`, `amend-plan`) — Phase 31
- Новые события (`SpecApproved` dataclass, `PlanAmended`) — Phase 31
- `Optional[int]` для `SessionDeclaredEvent.phase_id` — Phase 31
- `_check_i_sdd_hash` в `validate_invariants.py` — Phase 31
- Изменения в `src/` — запрещены в этой фазе

---

## 2. Architecture / BCs

### BC-30-1: tool-reference.md — строки 55 и 57

**Файл:** `.sdd/docs/ref/tool-reference.md`

**Строка 55 — текущее (некорректное):**
```
`activate-phase`: HUMAN-ONLY gate — LLM MUST NOT invoke
```

**Строка 55 — исправить на:**
```
`activate-phase`: HUMAN-ONLY gate — LLM MUST NOT invoke EXCEPT in DECOMPOSE
auto-action with `--executed-by llm` (I-SESSION-AUTO-1). In all other contexts,
LLM invocation is forbidden (NORM-ACTOR-001).
```

**Строка 57 — текущее (неточное):**
```
`activate-phase --executed-by`: distinguishes `actor` (who is authorized to run
the command, always `human`) from `executed_by` (the concrete identity of the
human operator, e.g. `katyrev`); used for audit attribution in SessionDeclared /
PhaseInitialized events
```

**Строка 57 — исправить на:**
```
`activate-phase --executed-by`: distinguishes `actor` (who is authorized to run
the command, always `human`) from `executed_by` (the concrete identity of the
executor: human username (e.g. `katyrev`) or `llm` in DECOMPOSE auto-action);
used for audit attribution in SessionDeclared / PhaseInitialized events
```

**Противоречия:**
- Строка 55 запрещает LLM вызывать `activate-phase` безусловно, тогда как
  `decompose.md` Auto-actions и I-SESSION-AUTO-1 прямо требуют этого.
- Строка 57 описывает `executed_by` только как human identity, исключая `llm`.

---

### BC-30-2: decompose.md — удалить раздел "After TaskSet is Written"

**Файл:** `.sdd/docs/sessions/decompose.md`

**Удалить полностью:**
```
## After TaskSet is Written

Human reviews TaskSet_vN.md → activates:
sdd activate-phase N --tasks T   ← human-only (if not already activated)
LLM: sdd show-state to confirm task count matches.
```

**Причина:** раздел полностью дублирует Auto-actions блок, который находится
выше — `activate-phase --executed-by llm` и `sdd show-state` уже присутствуют
в Auto-actions. Устаревшая инструкция вводит человека в заблуждение, создавая
friction point F-1 (устранённый в Phase 29).

---

### BC-30-3: plan-phase.md — "After Plan is Written"

**Файл:** `.sdd/docs/sessions/plan-phase.md`

**Текущее (устаревшее):**
```
Human reviews Plan_vN.md → activates phase:
sdd activate-phase N [--tasks T]   ← human-only action
LLM waits. On activation: sdd show-state to confirm new state.
```

**Исправить на:**
```
Human reviews Plan_vN.md → объявляет "DECOMPOSE Phase N" в чате.
LLM выполняет DECOMPOSE auto-actions (record-session + activate-phase --executed-by llm).
```

**Удалить:**
- `LLM waits.` — описывала паузу перед human CLI-шагом, которого больше нет
- `On activation: sdd show-state to confirm new state.` — этот шаг теперь
  выполняется в DECOMPOSE Auto-actions, не в PLAN-сессии

**Причина:** после Phase 29 человек не активирует фазу вручную из PLAN-сессии.
Инструкция описывает удалённые шаги, создающие friction point F-1.

---

### BC-30-4: decompose.md — recovery path для StaleStateError

**Файл:** `.sdd/docs/sessions/decompose.md`

**Добавить** в Auto-actions блок после `sdd activate-phase N --executed-by llm`:
```
On exit 1 with error_type=StaleStateError:
→ load sessions/recovery.md → apply RD-2
Do NOT retry activate-phase without following RD-2.
```

**Примечание:** `RP-STALE` в `recovery.md` не существует. Корректная ссылка — `RD-2`
(Recovery Decision 2, error_code=6: CLI retry; on terminal → `sdd report-error`).

**Причина:** отсутствие явного recovery path нарушает SEM-12 (LLM не должен
слепо делать recovery без классификации JSON stderr). Race condition при
`StaleStateError` — задокументированный риск в Spec_v29 §7.

---

### BC-30-5: dev-cycle-map.md — закрыть открытые вопросы

**Файл:** `.sdd/specs_draft/dev-cycle-map.md`

Закрыть следующие открытые вопросы из §5 и §6:

| Раздел | Текущее состояние | Решение |
|--------|------------------|---------|
| §5.1 tool-reference.md строки 55, 57 | "Нужно исправить" | ЗАКРЫТО: BC-30-1 |
| §5.2 decompose.md двойственность | "Нужно исправить" | ЗАКРЫТО: BC-30-2 |
| §5.3 plan-phase.md финальная секция | "Нужно исправить" | ЗАКРЫТО: BC-30-3 |
| §5.4 отсутствие recovery path | "Нужно добавить" | ЗАКРЫТО: BC-30-4 |
| §5.5 plan_hash drift | open choice A vs B | ЗАКРЫТО (design locked), implementation deferred to Phase 31 |
| §5.6 phase_id в DRAFT_SPEC | open choice 0 vs None | ЗАКРЫТО (design locked), implementation deferred to Phase 31 |

**§5.5 Plan mutability — полное решение:**

```
Status: CLOSED (design locked), implementation deferred to Phase 31

Decision:
- Plan is immutable after activate-phase
- Any modification MUST be represented as PlanAmended event
- phases table does NOT store plan_hash
- plan history is stored in phase_plan_versions

Invariant (to be enforced in Phase 31):
I-PLAN-IMMUTABLE-AFTER-ACTIVATE (DECLARED, not enforced):
  After PhaseInitialized, direct mutation of plan artifacts is forbidden.
  All changes MUST go through PlanAmended events.
```

**§5.6 SessionDeclared.phase_id — полное решение:**

```
Status: CLOSED (design locked), implementation deferred to Phase 31

Decision:
- SessionDeclaredEvent.phase_id: Optional[int]
- phase_id = None for DRAFT_SPEC sessions
- phase_id MUST be non-null for PLAN / DECOMPOSE / IMPLEMENT / VALIDATE

Current behavior:
- phase_id: int (forward reference for DRAFT_SPEC) — temporary workaround until Phase 31

Invariant (to be enforced in Phase 31):
I-SESSION-PHASE-NULL-1 (DECLARED, not enforced):
  SessionDeclaredEvent.phase_id MUST be NULL iff session_type == DRAFT_SPEC.
  For all other session types, phase_id MUST be non-null.
```

Обновить §1 DRAFT_SPEC блок: убрать статус "Идея" у `approve-spec` предложения,
заменить на "Реализуется в Phase 31".

---

### BC-30-6: CLAUDE.md — добавить задекларированные инварианты

**Файл:** `CLAUDE.md`

**Добавить** в §INV новый подраздел после существующей таблицы инвариантов:

```markdown
### Declared (not enforced)

| ID | Statement |
|----|-----------|
| I-PLAN-IMMUTABLE-AFTER-ACTIVATE | After PhaseInitialized, direct mutation of plan artifacts is forbidden. All changes MUST go through PlanAmended events. *(Implementation: Phase 31)* |
| I-SESSION-PHASE-NULL-1 | SessionDeclaredEvent.phase_id MUST be NULL iff session_type == DRAFT_SPEC. For all other session types, phase_id MUST be non-null. *(Implementation: Phase 31)* |
```

**Причина:** решения §5.5 и §5.6 приняты архитектурно (design locked), но реализация
в Phase 31. CLAUDE.md — Priority 3 в иерархии; отсутствие инвариантов здесь создаёт
дрейф между источниками. Статус "DECLARED" явно отделяет от "enforced" инвариантов.

---

## 3. Domain Events

Phase 30 не эмитирует новых domain events.
`SessionDeclared` (I-SESSION-DECLARED-1) эмитируется в начале каждой сессии штатно.

---

## 4. Types & Interfaces

Нет изменений в `src/`. Все BCs затрагивают только `.sdd/docs/`.

---

## 5. Invariants

### New Invariants

Нет новых инвариантов.

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-SESSION-AUTO-1 | LLM MUST run `sdd activate-phase N --executed-by llm` at end of DECOMPOSE |
| I-SESSION-ACTOR-1 | `activate-phase` MUST always pass `actor="human"` |
| I-SESSION-VISIBLE-1 | Every auto-invoked CLI MUST be shown in LLM output |
| I-SESSION-DECLARED-1 | LLM MUST emit `SessionDeclared` at start of every session |

### Acceptance Criteria для BC-30-1

`tool-reference.md` строка 55 НЕ содержит безусловного запрета для LLM;
содержит явное исключение для DECOMPOSE + ссылку на I-SESSION-AUTO-1.
`tool-reference.md` строка 57 описывает `executed_by` как допускающий значение
`llm` в DECOMPOSE auto-action (не только human username).

### Acceptance Criteria для BC-30-2

`decompose.md` НЕ содержит раздел "After TaskSet is Written" (раздел удалён
полностью). `grep "After TaskSet is Written" decompose.md` → пусто.

### Acceptance Criteria для BC-30-3

`plan-phase.md` НЕ содержит инструкцию `sdd activate-phase N` для human
в секции "After Plan is Written"; содержит инструкцию "объявить DECOMPOSE Phase N".

### Acceptance Criteria для BC-30-4

`decompose.md` Auto-actions блок содержит: "On exit 1 with StaleStateError →
recovery.md → RD-2". Строка `RP-STALE` отсутствует.

### Acceptance Criteria для BC-30-5

`dev-cycle-map.md` §5 не содержит нерешённых open choices; все §5.1–5.6
помечены как ЗАКРЫТО с указанием решения и фазы реализации.
§5.5 содержит полный decision text (I-PLAN-IMMUTABLE-AFTER-ACTIVATE, phase_plan_versions).
§5.6 содержит полный decision text (Optional[int], None for DRAFT_SPEC, I-SESSION-PHASE-NULL-1).

### Acceptance Criteria для BC-30-6

`CLAUDE.md` §INV содержит подраздел `### Declared (not enforced)` с двумя
инвариантами: `I-PLAN-IMMUTABLE-AFTER-ACTIVATE` и `I-SESSION-PHASE-NULL-1`,
каждый с пометкой `*(Implementation: Phase 31)*`.

---

## 6. Pre/Post Conditions

### Phase 30 Preconditions

**Pre:**
- Phase 29 COMPLETE
- `.sdd/docs/ref/tool-reference.md` существует
- `.sdd/docs/sessions/decompose.md` существует
- `.sdd/docs/sessions/plan-phase.md` существует
- `.sdd/specs_draft/dev-cycle-map.md` существует

**Post:**
- Все 6 файлов обновлены согласно BC-30-1..6
- Ни один файл в `src/` не изменён
- Все acceptance criteria выполнены
- `CLAUDE.md` §INV содержит подраздел `### Declared (not enforced)` с двумя инвариантами

---

## 7. Use Cases

### UC-30-1: LLM выполняет DECOMPOSE после Phase 30

**Actor:** LLM
**Trigger:** Human объявляет "DECOMPOSE Phase 31" в чате
**Pre:** Phase 30 COMPLETE, tool-reference.md исправлен
**Steps:**
1. LLM читает `tool-reference.md` строка 55 — видит исключение для DECOMPOSE
2. LLM выполняет `sdd activate-phase 31 --executed-by llm` без колебаний
3. Нет противоречия между tool-reference и decompose.md
**Post:** I-SESSION-AUTO-1 выполнен без конфликта с документацией

### UC-30-2: Human завершает PLAN Phase N

**Actor:** Human
**Trigger:** LLM завершил написание Plan_vN.md
**Pre:** Phase 30 COMPLETE, plan-phase.md исправлен
**Steps:**
1. Human читает Plan_vN.md
2. Human объявляет "DECOMPOSE Phase N" — НЕ запускает `sdd activate-phase`
3. Нет ложного шага активации из устаревшей инструкции
**Post:** Friction point F-1 устранён на уровне документации

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| Spec_v29 §6 (Session FSM) | reference | I-SESSION-AUTO-1 — основание для BC-30-1..4 |
| Spec_v29 §9 (I-SESSION-ACTOR-1) | reference | actor model сохраняется |

### Нет изменений в reducer, EventStore, CLI

---

## 9. Verification

| # | Проверка | BC |
|---|----------|----|
| 1 | `grep "HUMAN-ONLY gate" tool-reference.md` содержит "EXCEPT in DECOMPOSE" | BC-30-1 |
| 2 | `grep "executed_by" tool-reference.md` содержит "llm" | BC-30-1 |
| 3 | `grep "After TaskSet is Written" decompose.md` → пусто | BC-30-2 |
| 4 | `grep "LLM waits" plan-phase.md` → пусто | BC-30-3 |
| 5 | `grep "On activation.*show-state" plan-phase.md` → пусто | BC-30-3 |
| 6 | `grep "StaleStateError" decompose.md` → содержит "RD-2" | BC-30-4 |
| 7 | `grep "RP-STALE" decompose.md` → пусто | BC-30-4 |
| 8 | `grep "open choice" .sdd/specs_draft/dev-cycle-map.md` → пусто | BC-30-5 |
| 9 | `grep "I-PLAN-IMMUTABLE-AFTER-ACTIVATE" .sdd/specs_draft/dev-cycle-map.md` → непусто | BC-30-5 |
| 10 | `grep "I-SESSION-PHASE-NULL-1" .sdd/specs_draft/dev-cycle-map.md` → непусто | BC-30-5 |
| 11 | `grep "Declared (not enforced)" CLAUDE.md` → непусто | BC-30-6 |
| 12 | `grep "I-PLAN-IMMUTABLE-AFTER-ACTIVATE" CLAUDE.md` → непусто | BC-30-6 |
| 13 | `grep "I-SESSION-PHASE-NULL-1" CLAUDE.md` → непусто | BC-30-6 |
| 14 | `git diff src/` → пусто (нет изменений в src/) | all BCs |

---

## 10. Out of Scope

| Item | Phase |
|------|-------|
| `sdd approve-spec` CLI команда | Phase 31 |
| `sdd amend-plan` CLI команда | Phase 31 |
| `SpecApproved` dataclass + handler | Phase 31 |
| `PlanAmended` event + I-PLAN-IMMUTABLE-AFTER-ACTIVATE | Phase 31 |
| `SessionDeclaredEvent.phase_id: Optional[int]` | Phase 31 |
| `_check_i_sdd_hash` в validate_invariants.py | Phase 31 |
| PostgreSQL migration | Phase 32+ |
