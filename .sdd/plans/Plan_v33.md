# Plan_v33 — Phase 33: CommandSpec Guard Factory

Status: DRAFT
Spec: specs/Spec_v33_CommandSpecGuardFactory.md

---

## Milestones

### M1: CommandSpec расширяется полем guard_factory и методом build_guards()

```text
Spec:       §2 BC-33, §4 Types & Interfaces — CommandSpec structure
BCs:        BC-33
Invariants: I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3
Depends:    — (baseline: BC-15-REGISTRY, Spec_v15)
Risks:      Нарушение `@dataclass(frozen=True)` при добавлении Callable-поля
            (Callable не hashable по умолчанию — решается `field(hash=False, compare=False)`
            или отказом от frozen; нужно проверить совместимость с текущим кодом).
```

### M2: execute_command переходит на spec.build_guards(cmd)

```text
Spec:       §2 BC-33-REGISTRY, §8 Integration — "Изменения в execute_command"
BCs:        BC-33-REGISTRY
Invariants: I-CMD-GUARD-FACTORY-1
Depends:    M1 (build_guards обязан существовать до рефакторинга execute_command)
Risks:      Все 8 стандартных команд проходят через _default_build_guards —
            любая регрессия в логике флагов (requires_active_phase, apply_task_guard)
            нарушит их guard-пайплайн. Нужны тесты-регрессии по каждому флагу.
```

### M3: switch_phase.py объявляет собственный guard_factory; ветка if spec.name == "switch-phase" удаляется из registry.py

```text
Spec:       §2 BC-33-SWITCH, §4 switch_phase.py guard factory, §8 Nota Bene
BCs:        BC-33-SWITCH
Invariants: I-CMD-GUARD-FACTORY-4, I-CMD-GUARD-FACTORY-1
Depends:    M1, M2 (execute_command уже вызывает build_guards — фабрика подхватится автоматически)
Risks:      Circular import: switch_phase.py импортирует из sdd.domain.guards.*,
            которые в свою очередь не должны импортировать registry.py.
            При регистрации через guard_factory=_switch_phase_guards ссылка передаётся
            напрямую — registry.py НЕ импортирует switch_phase.py для сборки guards,
            импорт идёт в обратную сторону (switch_phase → guards). Безопасно.
```

### M4: Тесты для I-CMD-GUARD-FACTORY-1..4

```text
Spec:       §9 Verification — 7 test cases
BCs:        BC-33, BC-33-REGISTRY, BC-33-SWITCH
Invariants: I-CMD-GUARD-FACTORY-1, I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3,
            I-CMD-GUARD-FACTORY-4
Depends:    M1, M2, M3
Risks:      test_registry_no_conditional_on_spec_name использует AST/grep-проверку —
            нужно определить стратегию (статический анализ vs runtime).
            AST-подход надёжнее, но требует import ast и явного парсинга registry.py.
```

---

## Risk Notes

- R-1: `@dataclass(frozen=True)` + `Callable` поле — `Callable` не является hashable, что конфликтует с `frozen=True` (Python попытается включить поле в `__hash__`). Решение: `guard_factory: ... = field(default=None, hash=False, compare=False)`. Проверить совместимость с существующими сравнениями CommandSpec в тестах.
- R-2: Неполный guard list в custom factory — если `_switch_phase_guards` не включит norm_guard или phase_guard, команда выполнится без нужных проверок. I-CMD-GUARD-FACTORY-4 обязывает factory возвращать полный список; тест #4 (§9) проверяет это явно.
- R-3: Поведенческая регрессия в 8 стандартных командах — `_default_build_guards` должна быть функционально идентична удалённой `_build_spec_guards`. Расхождение в порядке guards изменит поведение пайплайна. Тест #5 (§9) покрывает флаги; дополнительно — интеграционный тест на полный execute_command flow.
