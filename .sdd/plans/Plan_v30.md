# Plan_v30 — Phase 30: Documentation Fixes

Status: DRAFT
Spec: specs/Spec_v30_DocFixes.md

---

## Milestones

### M1: Исправить противоречия в tool-reference.md (BC-30-1)

```text
Spec:       §1 Scope (BC-30-1), §2 Architecture (BC-30-1), §5 Invariants (Acceptance Criteria BC-30-1)
BCs:        BC-30-1
Invariants: I-SESSION-AUTO-1, I-SESSION-ACTOR-1
Depends:    — (входная точка фазы)
Risks:      tool-reference.md — строгий ref-файл; ошибка в строке 55 создаёт ложный
            запрет для LLM в DECOMPOSE, блокируя auto-action. Правка должна быть точечной:
            только строки 55 и 57.
```

### M2: Устранить дублирование и добавить recovery path в decompose.md (BC-30-2, BC-30-4)

```text
Spec:       §1 Scope (BC-30-2, BC-30-4), §2 Architecture (BC-30-2, BC-30-4), §5 AC BC-30-2, BC-30-4
BCs:        BC-30-2, BC-30-4
Invariants: I-SESSION-AUTO-1, SEM-12
Depends:    M1 (tool-reference.md исправлен — recovery path теперь согласован)
Risks:      Удаление раздела "After TaskSet is Written" — необратимо без git. Удалять
            целиком, не оставлять комментариев. Recovery path: ссылка на RD-2, НЕ RP-STALE.
```

### M3: Исправить план-сессию plan-phase.md (BC-30-3)

```text
Spec:       §1 Scope (BC-30-3), §2 Architecture (BC-30-3), §7 UC-30-2, §5 AC BC-30-3
BCs:        BC-30-3
Invariants: I-SESSION-AUTO-1, I-SESSION-VISIBLE-1
Depends:    M2 (decompose.md содержит корректные auto-actions, на которые ссылается план)
Risks:      plan-phase.md используется в текущей сессии (PLAN Phase 30). После правки
            "After Plan is Written" секция описывает "объявить DECOMPOSE Phase N".
            Это именно то, что произойдёт после написания этого плана — circular risk низкий.
```

### M4: Закрыть открытые вопросы в dev-cycle-map.md (BC-30-5)

```text
Spec:       §1 Scope (BC-30-5), §2 Architecture (BC-30-5), §5 AC BC-30-5
BCs:        BC-30-5
Invariants: I-1 (State_index = readonly snapshot), design locked §5.5 и §5.6
Depends:    M1, M2, M3 (все BC-30-1..4 должны быть выполнены, чтобы §5.1–5.4 имели корректный статус)
Risks:      dev-cycle-map.md — living doc в specs_draft/. Закрытие §5.5 и §5.6 фиксирует
            архитектурные решения (plan immutability, Optional[int] для phase_id).
            Реализация deferred to Phase 31 — НЕ реализовывать здесь. Только текст.
```

### M5: Добавить задекларированные инварианты в CLAUDE.md (BC-30-6)

```text
Spec:       §1 Scope (BC-30-6), §2 Architecture (BC-30-6), §5 AC BC-30-6
BCs:        BC-30-6
Invariants: I-PLAN-IMMUTABLE-AFTER-ACTIVATE (declared), I-SESSION-PHASE-NULL-1 (declared)
Depends:    M4 (dev-cycle-map.md содержит полные decision texts, которые инварианты отражают)
Risks:      CLAUDE.md — Priority 3 в иерархии (§META). Новый подраздел "Declared (not enforced)"
            должен быть чётко отделён от enforced инвариантов. Статус "DECLARED" предотвращает
            попытки LLM проверять эти инварианты через sdd validate-invariants.
```

---

## Risk Notes

- R-1: **Редактирование tool-reference.md без нарушения нумерации строк.** BC-30-1 ссылается
  на конкретные строки 55 и 57. После правки строки могут сдвинуться. Acceptance criteria
  проверяется по содержимому (`grep`), не по номеру строки — риск контролируемый.

- R-2: **Нет изменений в `src/`.** Все 6 BC затрагивают только `.sdd/docs/` и `CLAUDE.md`.
  `git diff src/` ДОЛЖЕН быть пустым после всех задач. Это базовый post-condition фазы.

- R-3: **dev-cycle-map.md находится в `specs_draft/`, а не в `specs/`.** Это living doc,
  его редактирование не нарушает SDD-9 (запрет изменений в `specs/`). PIR-3 разрешает
  чтение файлов, явно требуемых Spec_vN.

- R-4: **CLAUDE.md правится в активной сессии.** Изменения вступают в силу немедленно.
  Подраздел "Declared (not enforced)" добавляется после существующей таблицы инвариантов —
  только append, не изменение существующих строк.
