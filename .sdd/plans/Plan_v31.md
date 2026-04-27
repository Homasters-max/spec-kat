# Plan_v31 — Phase 31: Governance Commands

Status: DRAFT
Spec: specs/Spec_v31_GovernanceCommands.md

---

## Milestones

### M1: Domain Event Types (BC-31-1, BC-31-2, BC-31-3)

```text
Spec:       §2 Architecture/BCs — BC-31-1, BC-31-2, BC-31-3
BCs:        BC-31-1, BC-31-2, BC-31-3
Invariants: I-HANDLER-PURE-1, I-2, I-SESSION-PHASE-NULL-1
Depends:    — (baseline: existing events.py)
Risks:      Optional[int] change в SessionDeclaredEvent ломает существующие тесты
            и DuckDB десериализацию, если backward compat не сохранена;
            новые dataclasses должны быть frozen=True как все DomainEvent
```

- Добавить `SpecApproved` dataclass в `src/sdd/core/events.py` (BC-31-1)
- Добавить `PlanAmended` dataclass в `src/sdd/core/events.py` (BC-31-2)
- Изменить `SessionDeclaredEvent.phase_id: int → Optional[int] = None` (BC-31-3)
- Добавить `ApproveSpecCommand` и `AmendPlanCommand` dataclasses в types/commands

### M2: approve-spec Command (BC-31-1)

```text
Spec:       §2 BC-31-1, §6 Pre/Post Conditions approve-spec
BCs:        BC-31-1
Invariants: I-2, I-HANDLER-PURE-1, I-ERROR-1, I-DB-1
Depends:    M1 (SpecApproved dataclass exists)
Risks:      Write Kernel post-event hook — mv после EventStore.append;
            при сбое mv ErrorEvent уже зафиксирован, откат невозможен;
            guard против перезаписи specs/ обязателен
```

- Создать `src/sdd/commands/approve_spec.py`: `ApproveSpecHandler` + `CommandSpec`
- Handler pre-checks: specs_draft/Spec_vN_*.md существует; specs/Spec_vN_*.md НЕ существует
- Handler: вычисляет sha256[:16], возвращает `[SpecApproved(...)]` (I-HANDLER-PURE-1)
- Write Kernel post-event hook в `execute_and_project`: `shutil.move` specs_draft → specs
- Зарегистрировать в `src/sdd/commands/registry.py`
- CLI: `sdd approve-spec --phase N` (actor=human guard в handler)

### M3: amend-plan Command + Reducer (BC-31-2)

```text
Spec:       §2 BC-31-2, §6 Pre/Post Conditions amend-plan
BCs:        BC-31-2
Invariants: I-2, I-HANDLER-PURE-1, I-ERROR-1, I-PLAN-IMMUTABLE-AFTER-ACTIVATE,
            I-PHASE-SNAPSHOT-1, I-PHASE-SNAPSHOT-2
Depends:    M1 (PlanAmended dataclass exists)
Risks:      Reducer: PlanAmended должен обновить plan_hash в phases_snapshots[phase_id];
            если snapshot не существует → I-PHASE-SNAPSHOT-4 (Inconsistency);
            pre-condition "phase activated" проверяет phase_status != PLANNED
```

- Создать `src/sdd/commands/amend_plan.py`: `AmendPlanHandler` + `CommandSpec`
- Handler pre-checks: Plan_vN.md существует; phase_status != PLANNED
- Handler: вычисляет sha256(Plan_vN.md)[:16], возвращает `[PlanAmended(...)]`
- Reducer: `case PlanAmended` → обновить `plan_hash` в `phases_snapshots[phase_id]`
- Зарегистрировать в `src/sdd/commands/registry.py`
- CLI: `sdd amend-plan --phase N --reason "..."`

### M4: _check_i_sdd_hash (BC-31-4)

```text
Spec:       §2 BC-31-4, §7 UC-31-3, §9 Verification #7-8
BCs:        BC-31-4
Invariants: I-2 (read via EventLog query, not direct file access)
Depends:    M2 (SpecApproved events могут присутствовать в EventLog)
Risks:      Если SpecApproved не найден → SKIP (не FAIL); не сломает существующие
            фазы где approve-spec не использовался;
            hash вычисляется по текущему файлу → нужно знать путь specs/Spec_vN_*.md
```

- Реализовать `_check_i_sdd_hash(phase_id)` в `src/sdd/commands/validate_invariants.py`
- Логика: найти последний `SpecApproved` для phase_id в EventLog → читать spec_hash
- Вычислить sha256[:16] текущего `specs/Spec_vN_*.md` → сравнить
- Если `SpecApproved` не найден → `CheckResult(status=SKIP, reason="No SpecApproved event")`
- CLI trigger: `sdd validate-invariants --check I-SDD-HASH --phase N`

---

## Risk Notes

- R-1: `Optional[int]` в `SessionDeclaredEvent` — backward compat с DuckDB: существующие
  строки с `phase_id INTEGER` должны десериализоваться как `int` (подтип `Optional[int]`).
  Mitigation: проверить DuckDB schema upgrade и тест с replay существующего EventLog.

- R-2: Write Kernel post-event hook для `approve-spec` (mv operation) — атомарность не
  гарантирована: EventLog append успешен, mv сбойный → `ErrorEvent` зафиксирован, файл
  остаётся в specs_draft. Mitigation: при следующем вызове guard "specs/Spec_vN не
  существует" снова пропускает → можно перезапустить. Документировать поведение в тестах.

- R-3: `amend-plan` guard "phase activated" читает состояние из EventLog-проекции.
  Если State_index устарел → false negative. Mitigation: handler читает state через
  `sdd show-state` контракт (read-only projection) — актуален на момент команды.
