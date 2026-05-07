# Карта цикла разработки SDD

_Составлена по Spec_v29_StreamlinedWorkflow.md, CLAUDE.md, sessions/plan-phase.md, sessions/decompose.md, ref/tool-reference.md, norms/norm_catalog.yaml_
_Дата: 2026-04-25_

---

## 0. Порядок запуска фаз (приоритет)

_Обновлено 2026-04-27 (реструктуризация: Phase 19 архивирован, 20/21 → 37/38)_

### Линейный roadmap (I-PHASE-SEQ-1: phase_current=30)

| Шаг | Phase | Spec | Зависимости | Статус |
|-----|-------|------|-------------|--------|
| **→1** | **31** — GovernanceCommands | Spec_v31_GovernanceCommands.md | Phase 30 COMPLETE | Draft — **NEXT** |
| 2 | **32** — PostgresMigration | Spec_v32_PostgresMigration.md | Phase 31 | Draft |
| 3 | **35** — TestHarnessElevation | Spec_v35_TestHarnessElevation.md | Phase 33+34 (уже DONE) | Draft |
| 4 | **36** — GraphNavigation | Spec_v36_GraphNavigation.md | Phase 18 + Phase 32 | Draft |
| 5 | **37** — TemporalNavigation | Spec_v37_TemporalNavigation.md | Phase 36 | Draft |
| 6 | **38** — MutationGovernance | Spec_v38_MutationGovernance.md | Phase 37 | Draft |

**Порядок активации (строгий):**
```
current=30 → activate 31 → activate 32
                                ↓
             [33 DONE, 34 DONE — в phases_known]
                                ↓
                         activate 35 → activate 36 → activate 37 → activate 38
```

> **Phase 19 архивирован** (`del/Spec_v19_v1_GraphNavigation.md`).
> Phase 36 supersedes Phase 19: реализует тот же GraphNavigation layer,
> но сразу на unified `$SDD_DATABASE_URL` (не временный DuckDB-hybrid).

### Архив

| Файл | Статус |
|------|--------|
| `del/Spec_v19_GraphNavigation.md` | Архив — заменён Spec_v19_v1 |
| `del/Spec_v19_v1_GraphNavigation.md` | Архив — superseded by Phase 36 |

---

## 1. Полная жизненная цепочка одной фазы

### DRAFT_SPEC vN

| Кто | Команда | Функция | Примечание |
|-----|---------|---------|------------|
| LLM | `sdd record-session --type DRAFT_SPEC --phase N` | Записывает `SessionDeclared` в EventLog | Первое действие любой сессии (I-SESSION-DECLARED-1). `phase_id` здесь — опережающая ссылка: Phase N ещё не существует в EventLog (см. §5.6) |
| LLM | пишет `.sdd/specs_draft/Spec_vN.md` | Создаёт черновик спецификации | Запрещено писать сразу в `.sdd/specs/` (NORM-SCOPE-004) |
| **Human** ⛔ | переносит файл `specs_draft/ → specs/` | **Утверждает спек** → `SpecApproved` в EventLog | **HUMAN GATE.** Сейчас единственный нередуцируемый ручной шаг в этом блоке. О переносе на LLM — см. ниже ↓ |

> **Идея: перенос SpecApproved на LLM (предложение)**
>
> Паттерн Phase 29 — «Human Declares, LLM Executes» — уже применён к `activate-phase`.
> Тот же принцип применим к одобрению спека:
>
> - Физический перенос файла (`mv`) — механическая операция, не требующая суждения.
> - Настоящий **акт одобрения** — это когда человек произносит `"PLAN Phase N"` в чате:
>   этим он сигнализирует, что спек готов к работе.
> - Значит: **объявление сессии PLAN и есть approval-сигнал**.
>
> Предлагаемая механика:
> ```
> Human: "PLAN Phase N"
> → LLM: sdd record-session --type PLAN --phase N
> → LLM AUTO: mv .sdd/specs_draft/Spec_vN.md → .sdd/specs/Spec_vN.md
> → LLM AUTO: sdd approve-spec --phase N --executed-by llm
>   → emits SpecApproved(actor="human", executed_by="llm", spec_hash=sha256(Spec_vN.md)[:16])
> ```
>
> Аналогия с DECOMPOSE: `actor="human"` (человек инициировал), `executed_by="llm"` (LLM выполнил).
> Требуется: новая команда `sdd approve-spec`; изменение NORM-ACTOR-001 (добавить исключение для PLAN auto-action).
> Предусловие: `Spec_vN.md` должен существовать в `specs_draft/` — иначе LLM выбрасывает ошибку и не начинает PLAN.

↓

### PLAN Phase N

| Кто | Команда | Функция | Примечание |
|-----|---------|---------|------------|
| LLM | `sdd record-session --type PLAN --phase N` | Записывает `SessionDeclared` в EventLog | Первое действие (I-SESSION-DECLARED-1) |
| LLM | `sdd show-state` | Читает текущее состояние | Всегда первый read-шаг (SEM-13: строго последовательно) |
| LLM | `sdd show-spec --phase N` | Читает утверждённый спек | Запрещён прямой read `.sdd/specs/` (SDD-11) |
| LLM | пишет `.sdd/plans/Plan_vN.md` | Создаёт план фазы | Должен содержать `## Milestones` и `## Risk Notes` — это precondition следующей сессии |
| LLM | обновляет `Phases_index.md` | Добавляет/обновляет запись Phase N | `spec: Spec_vN.md`, `plan: Plan_vN.md`, `status: PLANNED` (I-SESSION-PI-6) |
| LLM | `sdd validate-invariants --check I-PHASES-INDEX-1` | Проверяет: `phases_known ⊆ Phases_index.ids` | На failure → STOP → `sdd report-error` |

↓

### DECOMPOSE Phase N

| Кто | Команда | Функция | Примечание |
|-----|---------|---------|------------|
| — | precondition-check | Проверяет: `Plan_vN.md` существует + секции `## Milestones`, `## Risk Notes` не пустые + `Spec_vN.md` в `.sdd/specs/` | На failure → MissingContext → STOP → `sdd report-error` |
| LLM | `sdd record-session --type DECOMPOSE --phase N` | Записывает `SessionDeclared` в EventLog | Первое действие (I-SESSION-DECLARED-1) |
| LLM | `sdd show-plan --phase N` | Читает план | Запрещён прямой read `.sdd/plans/` (SDD-12) |
| LLM | пишет `.sdd/tasks/TaskSet_vN.md` | Разбивает план на задачи | Каждая задача: `Inputs`, `Outputs`, `Invariants Covered` (TG-1..3) |
| LLM AUTO | `sdd activate-phase N --executed-by llm` | Активирует фазу; emits `PhaseInitialized(actor="human", executed_by="llm", plan_hash=…)` | `actor="human"` — человек инициировал сессию; `executed_by="llm"` — в payload для аудита (I-SESSION-ACTOR-1). На `StaleStateError` → recovery.md → RP-STALE |
| LLM AUTO | `sdd show-state` | Подтверждает количество задач | Должно совпасть с TaskSet |

↓

### IMPLEMENT T-NNN (повторяется для каждой задачи)

| Кто | Команда | Функция | Примечание |
|-----|---------|---------|------------|
| LLM | `sdd record-session --type IMPLEMENT --phase N` | Записывает `SessionDeclared` в EventLog | Первое действие (I-SESSION-DECLARED-1) |
| LLM | `sdd task-guard check --task T-NNN --taskset $(sdd path taskset)` | Проверяет: `task_status == TODO` | Guard должен пройти до любой записи кода |
| LLM | реализует код | Пишет только файлы из `Task.Inputs` и `Task.Outputs` | Любой файл вне этого списка — ScopeViolation (NORM-SCOPE-001..002) |
| LLM AUTO | `sdd complete T-NNN` | Отмечает задачу DONE в TaskSet + EventLog | Единственный легальный путь мутации TaskSet (I-2, I-3) |
| LLM | — | Предлагает следующую TODO-задачу или VALIDATE | Одна задача = одна сессия IMPLEMENT (§R.10) |

↓

### VALIDATE T-NNN (повторяется для каждой задачи)

| Кто | Команда | Функция | Примечание |
|-----|---------|---------|------------|
| LLM | `sdd record-session --type VALIDATE --phase N` | Записывает `SessionDeclared` в EventLog | Первое действие (I-SESSION-DECLARED-1) |
| LLM | запускает тесты, проверяет инварианты | Верифицирует реализацию | Должен загрузить `ref/tech-stack.md` (§HARD-LOAD Rule 3) |
| LLM AUTO | `sdd validate T-NNN --result PASS\|FAIL` | Записывает результат в EventLog | `--result` ОБЯЗАТЕЛЕН — без него `InvalidState` (exit 1). FAIL не останавливает цикл, фиксирует попытку |

↓

### SUMMARIZE Phase N → CHECK_DOD

| Кто | Команда | Функция | Примечание |
|-----|---------|---------|------------|
| LLM | `sdd record-session --type SUMMARIZE --phase N` | Записывает `SessionDeclared` в EventLog | Первое действие (I-SESSION-DECLARED-1) |
| LLM | генерирует `PhaseSummary_vN.md` | Итоговый отчёт по фазе | |
| LLM | `sdd validate --check-dod --phase N` | DoD-чек: все задачи DONE + инварианты PASS + тесты PASS | На success → emits `PhaseCompleted`. LLM не может emit это событие напрямую (NORM-ACTOR-003) — только через check-dod |
| **Human** ⛔ | review: читает Summary + DoD-отчёт | Оценивает бизнес-результат фазы | **HUMAN GATE** — см. подробно ниже ↓ |
| **Human** | объявляет `"PLAN Phase N+1"` в чате | Запускает следующий цикл | Это и есть approval-сигнал для следующей фазы |

> **Почему Human review → "PLAN Phase N+1" — это нередуцируемый шаг**
>
> На первый взгляд: раз все тесты прошли, DoD выполнен — зачем человек? Причин несколько:
>
> 1. **Тесты ≠ бизнес-ценность.** `check-dod` проверяет формальные критерии (задачи DONE, инварианты PASS). Он не знает, решает ли реализация реальную проблему. Только человек, знающий контекст продукта, может оценить это.
>
> 2. **Spec drift за время реализации.** Пока шла фаза N, внешний контекст мог измениться: требования бизнеса, новые ограничения, приоритеты. Спек N+1 писался до реализации N — возможно, он уже устарел. Человек решает: план N+1 ещё актуален или нужен новый DRAFT_SPEC.
>
> 3. **Обучение по итогам фазы.** Реализация всегда открывает что-то неожиданное — технические долги, неточности в спеке, риски, которые не были видны при планировании. Человек переносит эти выводы в следующий план. LLM не может самостоятельно решить, насколько эти выводы меняют приоритеты.
>
> 4. **NORM-GATE-003 — supervision checkpoint.** Завершение фазы — это точка остановки для надзора (SENAR). Система спроектирована так, чтобы человек регулярно «прикасался» к процессу и мог скорректировать курс. Без этой точки LLM может автономно пройти несколько фаз подряд — что противоречит принципу supervised engineering.
>
> 5. **Объявление "PLAN Phase N+1" — это не формальность.** Это сигнал: «я видел результат, я согласен двигаться дальше, я готов к следующей фазе». Аналог merge approval в code review — нажатие кнопки несёт смысл, не только механику.

---

## 2. Таблица ответственности

| Действие | Кто | Команда / файл | Инвариант |
|---|---|---|---|
| Объявить сессию | **LLM** | `sdd record-session --type T --phase N` | I-SESSION-DECLARED-1 |
| Написать спек (черновик) | **LLM** | `.sdd/specs_draft/Spec_vN.md` | NORM-SCOPE-004 |
| Одобрить спек (перенос файла) | **Human** | `mv specs_draft/ → specs/` | NORM-ACTOR-001, NORM-GATE-001 |
| Написать план | **LLM** | `.sdd/plans/Plan_vN.md` | SDD-1..5 |
| Обновить Phases_index.md | **LLM** | прямая запись файла | I-PHASES-INDEX-1, I-SESSION-PI-6 |
| Валидировать Phases_index | **LLM** | `sdd validate-invariants --check I-PHASES-INDEX-1` | I-PHASES-INDEX-1 |
| Написать TaskSet | **LLM** | `.sdd/tasks/TaskSet_vN.md` | SDD-2..4, TG-1..3 |
| Активировать фазу | **LLM** (авто, в DECOMPOSE) | `sdd activate-phase N --executed-by llm` | I-SESSION-AUTO-1, I-SESSION-ACTOR-1 |
| Реализовать код | **LLM** | только файлы из Task.Inputs | NORM-SCOPE-001..002 |
| Отметить задачу DONE | **LLM** | `sdd complete T-NNN` | I-2, I-3 |
| Валидировать задачу | **LLM** | `sdd validate T-NNN --result PASS\|FAIL` | I-HANDLER-PURE-1 |
| Завершить фазу (DoD) | **LLM** | `sdd validate --check-dod --phase N` | NORM-ACTOR-003 |
| Переключить контекст фазы | **Human** | `sdd switch-phase N` | NORM-ACTOR-SWITCH-PHASE |
| Инвалидировать событие | **Human** | `invalidate_event` | I-INVALID-1 |
| Emit SpecApproved | **Human** | — | NORM-ACTOR-001 |
| Emit PlanActivated | **Human** | — | NORM-ACTOR-002 |
| Emit PhaseCompleted | только через check-dod | — | NORM-ACTOR-003 |

---

## 3. Ограничения LLM-агента

### Запрещено

| Запрет | Норма |
|---|---|
| Писать в `.sdd/specs/` | NORM-SCOPE-004 |
| Использовать glob-паттерны (`*`, `**`) | NORM-SCOPE-003 |
| Читать `src/**` без явного Task.Inputs | NORM-SCOPE-002 |
| Читать `tests/**` без явного Task.Inputs | NORM-SCOPE-001 |
| Emit SpecApproved / PlanActivated / PhaseCompleted | NORM-ACTOR-001..003 |
| Читать `.sdd/` напрямую (только через `sdd show-*`) | SDD-11..13 |
| Выполнять несколько задач за одну команду | NORM-ACTOR-004, §R.10 |
| Запускать `activate-phase` с `actor="llm"` | I-SESSION-ACTOR-1 |
| Слепо делать recovery без классификации JSON stderr | SEM-12 |
| Параллельные tool calls в цепочке preconditions | SEM-13 |

### Разрешено (только LLM)

- `TaskImplemented`, `validate_task`, `check_dod`, `sync_state`, `record_decision`, `declare_session`
- Условия: `task_status == TODO`, `phase == ACTIVE`, `one_task_per_command`

---

## 4. Каузальная цепочка событий в EventLog

Ключевое нововведение Phase 29 — полный аудит-трейл:

```
H: "DECOMPOSE Phase 27"
↓
seq=X   SessionDeclared(type=DECOMPOSE, phase_id=27, actor=human)   ← LLM создаёт
seq=X+1 PhaseStarted(phase_id=27, caused_by_meta_seq=X)            ← activate-phase
seq=X+2 PhaseInitialized(phase_id=27,                              ← activate-phase
          actor="human",
          executed_by="llm",
          plan_hash="abc123..",
          caused_by_meta_seq=X)
```

Без `SessionDeclared` была "слепая точка" — непонятно, кто инициировал `PhaseInitialized`.

---

## 5. Слабые места системы

### 5.1 Противоречие в `tool-reference.md` строка 55 <!-- ЗАКРЫТО: BC-30-1 -->

Написано: `activate-phase: HUMAN-ONLY gate — LLM MUST NOT invoke`

Противоречит: `decompose.md` Auto-actions + I-SESSION-AUTO-1, которые требуют от LLM вызывать именно эту команду.

**Нужно исправить** строку 55 на:
> `activate-phase`: HUMAN-ONLY — за исключением DECOMPOSE auto-action с `--executed-by llm` (I-SESSION-AUTO-1)

---

### 5.2 Двойственность preconditions в `decompose.md`

В конце файла (раздел "After TaskSet is Written"):
```
Human reviews TaskSet_vN.md → activates:
sdd activate-phase N --tasks T   ← human-only (if not already activated)
```

Это остаток старой модели (до Phase 29). Auto-action выше уже активирует фазу. Раздел вводит в заблуждение.

**Нужно исправить** на: "Human reviews TaskSet (optional — LLM already activated in auto-action above)"

---

### 5.3 `plan-phase.md` — финальная секция

Строки "After Plan is Written":
```
Human reviews Plan_vN.md → activates phase:
sdd activate-phase N [--tasks T]   ← human-only action
LLM waits.
```

После Phase 29 человек не активирует фазу вручную — это делает LLM в DECOMPOSE. Инструкция говорит человеку сделать лишний шаг (friction point F-1 из Spec_v29).

**Нужно исправить** на: "Human reviews Plan_vN.md → объявляет 'DECOMPOSE Phase N' в чате"

---

### 5.4 Отсутствие explicit recovery path в DECOMPOSE <!-- ЗАКРЫТО: BC-30-4 -->

Когда `sdd activate-phase` завершается с `StaleStateError` (race condition, §7 Spec_v29) — нет прямой ссылки из `decompose.md` auto-actions на конкретный RP в `recovery.md`.

**Нужно добавить** в auto-actions блок:
```
On exit 1 with StaleStateError → load sessions/recovery.md → apply RP-STALE
```

---

### 5.5 `plan_hash` — audit drift после изменения плана

`I-SESSION-PLAN-HASH-1` фиксирует хеш плана в момент активации. Нет нормы, запрещающей изменять `Plan_vN.md` после активации фазы. Если план правится после DECOMPOSE, хеш в `PhaseInitialized.plan_hash` и текущий файл расходятся. EventLog честный, план — нет.

**Предлагаемый инвариант:**

> **I-PLAN-IMMUTABLE-AFTER-ACTIVATE:** `Plan_vN.md` MUST NOT be modified after `activate-phase N` has been executed. Any change to the plan file after phase activation constitutes a protocol violation. If a plan update is required, a new phase (N+1) with a revised spec must be initiated.

**Альтернативный механизм — `phase_plan_versions`:**

Если строгая иммутабельность неприемлема (план может уточняться в процессе), ввести поле `phase_plan_versions` в SDDState:

```
phase_plan_versions: dict[int, list[str]]
  # phase_id → [plan_hash_at_activation, plan_hash_at_t1, ...]
```

- При каждом изменении `Plan_vN.md` после активации LLM должен вызвать `sdd record-plan-revision --phase N`, который эмитит `PlanRevised(phase_id=N, old_hash=..., new_hash=...)` и добавляет новый хеш в `phase_plan_versions[N]`.
- `check-dod` проверяет: если `len(phase_plan_versions[N]) > 1` — добавляет warning в DoD-отчёт ("plan was modified after activation").
- Это честный аудит-трейл без запрета: EventLog отражает реальную историю, drift виден явно.

---

### 5.6 Опережающая ссылка в `SessionDeclared.phase_id` для DRAFT_SPEC

`SessionDeclared` требует `phase_id: int`. Но в сессии DRAFT_SPEC Phase N ещё не существует в EventLog. Событие ссылается на несуществующую фазу. Редьюсер это игнорирует (no state mutation), но формальная целостность EventLog нарушается.

**Принятое решение — инвариант I-SESSION-PHASE-NULL-1:**

> **I-SESSION-PHASE-NULL-1:** `SessionDeclared` события с `session_type = "DRAFT_SPEC"` MUST use `phase_id = 0` as a sentinel value. `phase_id = 0` is reserved exclusively for pre-phase sessions and MUST NOT correspond to any real phase in `phases_known`. Reducer MUST treat `phase_id = 0` in `SessionDeclared` as a no-op (no state mutation). All other session types MUST use a real `phase_id ∈ phases_known`.

Выбор `phase_id=0` (не `None`) обусловлен тем, что поле типизировано как `int` в EventLog schema — `None` потребует изменения схемы (EV-1..2). `0` — минимальный sentinel, не конфликтующий с реальными фазами (нумерация начинается с 1).

---

## 6. Таблица неоднозначностей → однозначные правила

| Ситуация | Текущая неоднозначность | Нужное однозначное правило |
|---|---|---|
| LLM видит `StaleStateError` после `activate-phase` | Нет прямой инструкции в decompose.md | Добавить: "On exit 1 → recovery.md → RP-STALE" |
| Человек правит Plan после DECOMPOSE | Не запрещено явно, но нарушает plan_hash | Добавить I-PLAN-IMMUTABLE-AFTER-ACTIVATE или явный disclaimer |
| `tool-reference.md` строка 55 vs I-SESSION-AUTO-1 | Прямое противоречие | Исправить строку 55 |
| `decompose.md` "After TaskSet is Written" | Человек получает инструкцию активировать уже активированное | Удалить или заменить на "optional review" |
| `plan-phase.md` "After Plan is Written" | Человек получает инструкцию активировать — вместо "объяви DECOMPOSE" | Исправить на "объявить DECOMPOSE Phase N" |
| `SessionDeclared.phase_id` в DRAFT_SPEC | Phase ещё не существует в EventLog | **Закрыто:** I-SESSION-PHASE-NULL-1 — использовать `phase_id=0` как sentinel |

---

## 7. Итог

Система архитектурно стройная — event sourcing честный, роли чёткие, Phase 29 закрыла главный friction point (двойной ручной `activate-phase`). Основные проблемы сейчас — **документационный дрейф**: `tool-reference.md` и нижние секции `decompose.md`/`plan-phase.md` содержат устаревшие инструкции из "до-Phase-29" мира, которые прямо противоречат новым инвариантам. Это не баги кода — баги протокольной документации, создающие неоднозначность для LLM при следующих сессиях.

Приоритет исправлений: 5.1 → 5.2 → 5.3 → 5.4 → 5.6 → 5.5
