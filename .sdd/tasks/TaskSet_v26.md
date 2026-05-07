# TaskSet_v26 — Phase 26: Task Mode Filter Fix & Human Test Protocol

Spec: specs/Spec_v26_TaskModeFilterAndTestProtocol.md
Plan: plans/Plan_v26.md

> ⚠️ Implementation note: Spec §4 предлагает Option B (`"pytest" not in v`).
> При реализации используется Option A (`not k.startswith("test")`), т.к. Option B
> сломает существующие тесты: `_fake_config` генерирует значения `"run-{n}"` без "pytest".
> Option A семантически эквивалентен для текущего конфига и совместим с тест-инфраструктурой.

---

T-2601: validate_invariants.py — fix task mode filter + CLAUDE.md I-TASK-MODE-1

Status:               DONE
Spec ref:             Spec_v26 §4 Interface Changes — BC-26-1, BC-26-2
Invariants:           I-TASK-MODE-1
spec_refs:            [Spec_v26 §4 BC-26-1, Spec_v26 §3]
produces_invariants:  [I-TASK-MODE-1]
requires_invariants:  []
Inputs:               src/sdd/commands/validate_invariants.py, CLAUDE.md
Outputs:              src/sdd/commands/validate_invariants.py, CLAUDE.md
Acceptance:           (1) строка 128 изменена: `if k != "test"` → `if not k.startswith("test")`; (2) I-TASK-MODE-1 добавлен в CLAUDE.md §INV; (3) mypy src/sdd/commands/validate_invariants.py — чисто; (4) ruff check src/sdd/commands/validate_invariants.py — чисто
Depends on:           —

---

T-2602: test_validate_invariants.py — regression test for test_full exclusion

Status:               DONE
Spec ref:             Spec_v26 §4 Interface Changes — BC-26-3, §6 Tests
Invariants:           I-TASK-MODE-1
spec_refs:            [Spec_v26 §4 BC-26-3, Spec_v26 §6]
produces_invariants:  [I-TASK-MODE-1]
requires_invariants:  [I-TASK-MODE-1]
Inputs:               tests/unit/commands/test_validate_invariants.py, src/sdd/commands/validate_invariants.py
Outputs:              tests/unit/commands/test_validate_invariants.py
Acceptance:           (1) добавлен тест `TestValidationModes::test_task_mode_skips_all_pytest_commands`; (2) mock_load использует `_fake_config("lint", "typecheck", "test", "test_full")`; (3) assert: "run-test_full" отсутствует в executed; (4) assert: "run-lint" и "run-typecheck" присутствуют; (5) pytest tests/unit/commands/test_validate_invariants.py -q — все тесты green
Depends on:           T-2601

---

T-2603: human-guide-phase-cycle.md — раздел "Протокол тестирования"

Status:               DONE
Spec ref:             Spec_v26 §1 D-3, §4 Interface Changes — BC-26-4
Invariants:           —
spec_refs:            [Spec_v26 §4 BC-26-4]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/docs/human-guide-phase-cycle.md
Outputs:              .sdd/docs/human-guide-phase-cycle.md
Acceptance:           (1) раздел "## Протокол тестирования: агент vs человек" добавлен после "## Быстрая шпаргалка: команды человека"; (2) раздел содержит таблицу "Что запускает агент", блок команд "Что запускаешь ты", описание system mode, таблицу "Почему такое разделение"; (3) grep -n "Протокол тестирования" .sdd/docs/human-guide-phase-cycle.md — находит строку
Depends on:           —

---

T-2604: SDD_Improvements.md — закрыть IMP-003

Status:               DONE
Spec ref:             Spec_v26 §7 DoD — BC-26-5
Invariants:           —
spec_refs:            [Spec_v26 §7]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/specs_draft/SDD_Improvements.md
Outputs:              .sdd/specs_draft/SDD_Improvements.md
Acceptance:           (1) IMP-003 содержит строку `Implemented in: Phase 26 (T-2601, T-2602)`; (2) IMP-003 содержит строку `Invariant introduced: I-TASK-MODE-1`
Depends on:           T-2601, T-2602
