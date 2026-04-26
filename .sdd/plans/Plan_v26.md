# Plan_v26 — Phase 26: Task Mode Filter Fix & Human Test Protocol

Status: DRAFT
Spec: specs/Spec_v26_TaskModeFilterAndTestProtocol.md

> ⚠️ Precondition note: Spec_v26 имеет статус DRAFT (в specs_draft/, не в specs/).
> Активация Phase 26 невозможна до того как человек переместит спец в specs/:
> `cp .sdd/specs_draft/Spec_v26_*.md .sdd/specs/`

---

## Milestones

### M1: Fix task mode filter (BC-26-1, BC-26-2)

```text
Spec:       §4 Interface Changes — BC-26-1
BCs:        BC-26-1, BC-26-2
Invariants: I-TASK-MODE-1 (new)
Depends:    — (independent)
Risks:      acceptance содержит "pytest" → тоже фильтруется; безопасно, т.к.
            acceptance обрабатывается отдельно (строки 142, 455-468) и читает
            из оригинального config, не из build_commands
```

**Задача T-2601:** `src/sdd/commands/validate_invariants.py:128` — исправить фильтр  
**Задача T-2601a:** `CLAUDE.md §INV` — добавить I-TASK-MODE-1

### M2: Regression test coverage (BC-26-3)

```text
Spec:       §4 Interface Changes — BC-26-3, §6 Tests
BCs:        BC-26-3
Invariants: I-TASK-MODE-1
Depends:    M1
Risks:      _fake_config в тесте должен строить команды совместимо с новым фильтром;
            проверить как именно формируются строки в executed (mock_popen.call_args_list)
```

**Задача T-2602:** `tests/unit/commands/test_validate_invariants.py` — добавить  
`test_task_mode_skips_all_pytest_commands` в `TestValidationModes`

### M3: Human test protocol documentation (BC-26-4)

```text
Spec:       §1 Диагностика дефектов — D-3, §4 Interface Changes — BC-26-4
BCs:        BC-26-4
Invariants: —
Depends:    — (independent от M1/M2)
Risks:      нет кода → нет рисков; только документация
```

**Задача T-2603:** `.sdd/docs/human-guide-phase-cycle.md` — добавить раздел  
"Протокол тестирования: агент vs человек" после "## Быстрая шпаргалка"

### M4: Close IMP-003 (BC-26-5)

```text
Spec:       §7 DoD
BCs:        BC-26-5
Invariants: —
Depends:    M1, M2
Risks:      нет
```

**Задача T-2604:** `.sdd/specs_draft/SDD_Improvements.md` — IMP-003 пометить  
`Implemented in: Phase 26 (T-2601, T-2602)`

---

## Risk Notes

- R-1: `acceptance` командная строка содержит "pytest" → будет отфильтрована новым фильтром.
  Безопасно: acceptance уже пропускается через `continue` в цикле (строка 142 validate_invariants.py)
  и обрабатывается отдельно в блоке строк 455-468, который читает из `config` напрямую.
  Регрессия невозможна. Тест `test_system_mode_runs_all_commands` использует
  `_fake_config("lint", "typecheck", "test")` — без acceptance — и не затронут.

- R-2: Spec_v26 в DRAFT → Phase 26 нельзя активировать до одобрения человеком.
  Активация через `sdd activate-phase 26 --tasks 4` возможна только после перемещения спец.
