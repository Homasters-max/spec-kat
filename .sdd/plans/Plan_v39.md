# Plan_v39 — Phase 39: Event–Reducer Consistency (SSOT Fix)

Status: DRAFT
Spec: specs/Spec_v39_EventRegistrySSot.md

---

## Logical Context

```
type: none
rationale: "Standard structural improvement phase. Eliminates a pre-existing SSOT defect
            (_KNOWN_NO_HANDLER static literal duplicating V1_L1_EVENT_TYPES). No specific
            anchor phase — defect predates phase tracking."
```

---

## Milestones

### M1: Рефакторинг reducer.py — _KNOWN_NO_HANDLER как derived expression

```text
Spec:       §2 Architecture/BCs — BC-39-2
BCs:        BC-39-2
Invariants: I-EREG-1, I-ST-10
Depends:    — (первый шаг)
Risks:      Порядок объявления ClassVar критичен: _EVENT_SCHEMA → _HANDLER_EVENTS →
            _KNOWN_NO_HANDLER. Нарушение порядка → NameError при загрузке модуля.
            import-time assert удаляется — регрессия ловится только тестами M2.
```

### M2: Явный pytest-тест на I-EREG-1 и I-ST-10

```text
Spec:       §2 Architecture/BCs — BC-39-3
BCs:        BC-39-3
Invariants: I-EREG-1, I-ST-10
Depends:    M1 (тест проверяет результат рефакторинга M1)
Risks:      Тест должен явно падать при регрессии (добавление типа только в
            V1_L1_EVENT_TYPES без _EVENT_SCHEMA → missing в диагностике).
            Нельзя дублировать assert из M1 в теле теста.
```

### M3: Event-Addition Rule в TaskSet_template.md

```text
Spec:       §2 Architecture/BCs — BC-39-4
BCs:        BC-39-4
Invariants: I-EREG-SCOPE-1
Depends:    M1, M2 (правило ссылается на тесты M2 в DoD-секции)
Risks:      Изменение только документального шаблона — нет риска регрессии.
            Правило должно явно разделять no-handler и has-handler случаи.
```

---

## Risk Notes

- R-1: **Порядок инициализации ClassVar** — единственное нетривиальное изменение в классе.
  `_EVENT_SCHEMA` должен быть объявлен до `_HANDLER_EVENTS` и `_KNOWN_NO_HANDLER`.
  Митигация: import-smoke-test в Verification §8 п.1 поймает ошибку немедленно.

- R-2: **Обратная совместимость `_KNOWN_NO_HANDLER`** — тип (`frozenset[str]`) и содержимое
  не меняются; потребители (guards, тесты) продолжают работать без изменений.
  Митигация: полный прогон существующих тестов (1012+) в M2 валидации.

- R-3: **Автоматическая классификация** — новый тип, добавленный только в `V1_L1_EVENT_TYPES`,
  автоматически попадает в `_KNOWN_NO_HANDLER`. Поведение корректно и документировано в спеке.
  Митигация: тест `test_i_st_10_all_event_types_classified` фиксирует это свойство.
