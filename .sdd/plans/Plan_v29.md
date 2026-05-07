# Plan_v29 — Phase 29: Streamlined Session Flow

Status: DRAFT
Spec: specs/Spec_v29_StreamlinedWorkflow.md

---

## Overview

Фаза устраняет friction в session lifecycle: LLM получает право авто-вызывать
`activate-phase` (с `--executed-by llm`), фиксирует каждую сессию через
`SessionDeclaredEvent` (causal anchor для audit trail), добавляет `plan_hash`
в `PhaseInitializedEvent`, и обновляет session docs + CLAUDE.md под новую модель.

Принцип: **Human Declares, LLM Executes**. Human gate — объявление типа сессии в чате.
CLI-команды — авто-действия LLM с явным выводом.

---

## Milestones

### M1: Event Infrastructure — SessionDeclaredEvent + plan_hash

```text
Spec:       §2 (SessionDeclaredEvent), §4 (plan_hash в PhaseInitializedEvent)
BCs:        BC-SW-1, BC-SW-3, BC-SW-5
Invariants: I-SESSION-DECLARED-1, I-SESSION-PLAN-HASH-1
Depends:    — (начальная точка)
Risks:      plan_hash — EV-2 additive field; не должен ломать replay старых событий (backward compat)
```

Что входит:
- `SessionDeclaredEvent` dataclass в `src/sdd/core/events.py` (поля: event_type, session_type, phase_id, actor="human")
- `PhaseInitializedEvent` — добавить `plan_hash: str` как опциональное поле с default="" (EV-2 additive)
- Reducer `src/sdd/domain/state/reducer.py`: case `SessionDeclared` → `logging.debug(...)`, return state unchanged; добавить `# I-PHASE-STARTED-1` комментарий-образец

### M2: record-session CLI

```text
Spec:       §2 (causal chain), §6 (Session FSM — emit SessionDeclared)
BCs:        BC-SW-2
Invariants: I-SESSION-DECLARED-1, I-SESSION-VISIBLE-1
Depends:    M1
Risks:      новая команда — MUST регистрироваться в registry.py; пропуск регистрации = I-2 violation
```

Что входит:
- Новый файл `src/sdd/commands/record_session.py` — CommandSpec + handler
- Handler emits `SessionDeclaredEvent(session_type=..., phase_id=..., actor="human")`
- Регистрация в `src/sdd/commands/registry.py`
- CLI subcommand: `sdd record-session --type PLAN|DECOMPOSE|IMPLEMENT|VALIDATE --phase N`

### M3: activate-phase Enhancement (--executed-by + plan_hash)

```text
Spec:       §3 (actor + executed_by), §4 (plan_hash computation)
BCs:        BC-SW-4, BC-SW-6
Invariants: I-SESSION-ACTOR-1, I-SESSION-PLAN-HASH-1
Depends:    M1
Risks:      VALID_ACTORS остаётся {"human"}; executed_by — payload field, НЕ actor field; нельзя путать
```

Что входит:
- `src/sdd/commands/activate_phase.py`: добавить `--executed-by` optional arg (default=None)
- Перед emit: вычислить `plan_hash = sha256(Plan_vN.md content)[:16]`; если файл не найден → `plan_hash=""`
- Инжектировать `executed_by` и `plan_hash` в event payload (backward-compatible)

### M4: Session Documentation Update

```text
Spec:       §6 (Revised Session FSM), §7 (Race Conditions reference)
BCs:        BC-SW-7, BC-SW-8, BC-SW-9, BC-SW-10
Invariants: I-SESSION-PI-6, I-PHASES-INDEX-1, I-SESSION-AUTO-1
Depends:    M1, M2, M3 (docs описывают уже реализованные механизмы)
Risks:      CLAUDE.md — изменения в §SESSION FSM и §ROLES могут сломать существующие session contracts;
            нужно строго следовать spec §6 без добавления новой логики
```

Что входит:
- `.sdd/docs/sessions/decompose.md`: убрать precondition "Plan Status = ACTIVE"; добавить content check (Milestones + Risk Notes); добавить Auto-actions блок (SessionDeclared + activate-phase)
- `.sdd/docs/sessions/plan-phase.md`: добавить Auto-action Phases_index update + I-PHASES-INDEX-1 validation; добавить PI-6 в Phase Index Invariants
- `.sdd/docs/ref/tool-reference.md`: исправить `--tasks` (устаревший флаг); добавить `record-session` entry; добавить `--executed-by` к `activate-phase`
- `CLAUDE.md`: обновить §SESSION FSM (добавить авто-действия), §ROLES (LLM MUST NOT: убрать activate-phase из запрещённых при DECOMPOSE), §INV (добавить I-SESSION-* и I-PHASES-INDEX-1)

### M5: Verification Tests

```text
Spec:       §10 (Verification table)
BCs:        BC-SW-1..6 (coverage)
Invariants: все I-SESSION-* + I-PHASES-INDEX-1
Depends:    M1, M2, M3
Risks:      тесты MUST использовать tmp_path (I-DB-TEST-1); НЕ открывать production DB
```

Что входит (по spec §10):
- `test_session_declared_emitted`: record-session → SessionDeclared в EventLog
- `test_session_declared_no_state_mutation`: replay с SessionDeclared → state не меняется (I-SESSION-DECLARED-1 + BC-SW-3)
- `test_activate_phase_executed_by_llm`: `--executed-by llm` → payload.executed_by="llm" (I-SESSION-ACTOR-1)
- `test_activate_phase_plan_hash`: plan_hash в PhaseInitialized == sha256(Plan_vN.md)[:16] (I-SESSION-PLAN-HASH-1)
- `test_phases_index_consistency`: phases_known из EventLog ⊆ Phases_index.ids (I-PHASES-INDEX-1)

---

## Risk Notes

- R-1: **Backward compatibility plan_hash.** Старые `PhaseInitializedEvent` не имеют `plan_hash`. Поле MUST иметь `default=""` или `Optional[str] = ""`, чтобы replay не ломал десериализацию.
- R-2: **actor/executed_by разделение.** `executed_by` — только payload metadata; VALID_ACTORS не трогаем. Путаница в этом месте нарушит I-SESSION-ACTOR-1 и сломает существующие guard checks.
- R-3: **CLAUDE.md §ROLES противоречие.** Сейчас LLM MUST NOT run `sdd activate-phase`. После M4 это правило меняется (только для DECOMPOSE сессий, с `--executed-by llm`). Формулировка MUST быть точной: "LLM MUST NOT activate-phase кроме авто-вызова в DECOMPOSE сессии с --executed-by llm".
- R-4: **record-session регистрация.** Новая команда MUST войти в REGISTRY (I-2). Пропуск = runtime error при первом вызове.
- R-5: **Race condition при авто-активации.** Если другой процесс пишет в EventLog между write TaskSet и activate-phase → StaleStateError. LLM обрабатывает через RP-STALE в recovery.md. Дополнительной защиты не нужно (spec §7).
