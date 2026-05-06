---
id: pattern/golden-fixture
page_type: pattern
domain: sdd
layer: architecture
tags:
- validation
- automation
- pipeline
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/replay-based-testing-architecture.md
---
# GoldenFixture

Self-contained YAML-файл для Tier 2 golden test. Содержит сериализованный `context_prefix` (резолвится при capture), `task_events`, `expected_state` (partial match), `trace_assertions`. Lifecycle: `sdd golden-capture` → ревью → `sdd golden-approve`.

## How It Works

```yaml
# .sdd/tests/golden/T-034.yaml
task_id: T-034
phase_id: 3
schema_version: 1
strict_lists: false          # default: subset check для list-полей
context_prefix:
  - type: PhaseInitialized
    payload: {phase_id: 3}
  # context_prefix сериализован при capture — EventLog не нужен при запуске теста
events:
  - type: TaskStarted
    version: 1
    payload: {task_id: T-034, phase_id: 3}
  - type: TaskCompleted
    version: 1
    payload: {task_id: T-034}
expected_state:
  phase_status: COMPLETE       # partial match: только этот ключ
  tasks_done: [T-034]          # subset check (strict_lists: false)
  phases_known: __any__        # любое значение OK
trace_assertions:
  - kind: TaskStarted
    payload_contains: {task_id: T-034}
  - kind: TaskCompleted
    count_min: 1
```

**Lifecycle:**

```bash
sdd golden-capture T-034   # читает EventLog, пишет .sdd/tests/golden/T-034.yaml
                            # context_prefix сериализован как конкретные события
# → разработчик ревьюит файл
sdd golden-approve T-034   # эмитит GoldenFixtureApproved → TestCatalogProjection
```

**Семантика expected_state:**

| Конфигурация | Поведение |
|-------------|---------|
| `expected_state: {key: val}` | Partial match — только заявленные ключи |
| `expected_state: {}` | Full compare с `initial_state()` — ничего не изменилось |
| `__any__` как значение | Любое значение OK |
| `strict_lists: false` (default) | list-поля: subset check (`actual ⊇ expected`) |
| `strict_lists: true` | list-поля: exact match |

Убраны `__partial__` sentinel и `tasks_done_value` — артефакты старого дизайна (AD-10).

## When To Use

Разработчик сам выбирает какие задачи достойны golden test — не автоматически на каждый `complete-task`. После `golden-approve` fixture входит в [[test-catalog-projection]] и запускается при `sdd test --diff` если `affected_commands` совпадают.

## Trade-offs

- `schema_version` может отстать от системы — `GoldenTestRunner` логирует Warning и активирует upcasters (I-REPLAY-8)
- context_prefix жёстко зафиксирован при capture — изменения в системных событиях требуют повторного capture

## Open Questions

- [ ] (P1) Q122: Есть ли golden master tests для системы end-to-end? (full scenario → expected final EventLog state snapshot)
- [ ] (P1) Q125: Есть ли тест: replay(EventLog) N раз → bit-identical State? Запускается ли в CI как regression gate?

## Decisions

- [x] (P1) Q97: Replay with snapshots — golden-fixture используется для тестовых снапшотов → [[replay-engine]]

## See Also

- [[replay-engine]]
- [[snapshot-comparator]]
- [[task-event-slice]]
- [[test-catalog-projection]]
- [[scenario-gen]]
- [[replay-based-testing]]
