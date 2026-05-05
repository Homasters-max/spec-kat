---
id: pattern/replay-based-testing
page_type: pattern
domain: sdd
layer: architecture
tags:
- automation
- validation
- pipeline
- ssot
- domain/sdd
version: 3
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/replay-based-testing-architecture.md
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
---
# Replay-Based Testing

Архитектура тестирования SDD-системы, построенная на инварианте: `state = reduce(events)` — детерминировано без моков. Три уровня тестов (Tier 1–3) + TATP (Trace-Aligned Test Partitioning) — тесты как данные в Projection.

## Принцип

EventLog — SSOT. Reducer — чистая функция. Следствие: любой State полностью воспроизводим из EventLog без базы данных, без сети, без моков.

## Три уровня тестов

```text
Tier 1 — Unit Replay (L0 unit)
  Input:  list[Event]  (hand-crafted)
  Output: State delta + synthetic_trace
  Tested: Reducer + upcast chain + TraceAssertionChecker
  Sandbox: in-memory, миллисекунды
  Filter:  affected_commands (из TestCatalogProjection)

Tier 2 — Golden Tests (L0+L1 integration)
  Input:  GoldenFixture (.sdd/tests/golden/T-NNN.yaml)
  Output: State partial-match, Trace assertions
  Sandbox: temp PostgreSQL + initial_state()
  Filter:  scope.phase_id (из TestCatalogProjection)

Tier 3 — Regression Suite
  Input:  ScenarioSpec (успешные задачи) + AdversarialScenario (провальные)
  Output: M9 metric
  Sandbox: полный цикл с SandboxManager
  Trigger: AuditEngine.calculate_M9() внутри Session Orchestrator flow
```

## TATP — Trace-Aligned Test Partitioning

`TestCatalogProjection` хранит индекс тестов, сгруппированных по `affected_commands` и `affected_projections`. `sdd test --diff HEAD~1` запускает только релевантные тесты:

```bash
# Было: pytest → 40 мин → непонятный fail из другой фазы
# Стало: sdd test --diff HEAD~1 → 4 теста → 2 сек
```

Три bounded context домена:

| Домен | affected_projections | Sandbox | Скорость |
|-------|---------------------|---------|----------|
| L0 Core | `["StateProjection"]` | in-memory | миллисекунды |
| L1 Execution | `["TraceProjection", "GraphSessionProjection"]` | temp PostgreSQL | секунды |
| L2 Governance | `["PolicyProjection"]` | full SandboxManager | минуты |

## Ключевые компоненты

| Компонент | Уровень | Роль |
|-----------|---------|------|
| [[replay-engine]] | L0, pure | Replay событий → State + synthetic_trace |
| [[task-event-slice]] | L0 | Изоляция событий задачи + context_prefix |
| [[golden-fixture]] | L1 | YAML-формат golden test (capture → approve) |
| [[snapshot-comparator]] | L0 | Partial-match State assertions |
| [[test-catalog-projection]] | L1 | Индекс тестов, TATP-фильтрация |
| [[adversarial-scenario-mutator]] | L2 | Мутации из FAILED задач для Tier 3 |

## Инварианты

| ID | Правило |
|----|---------|
| I-REPLAY-1 | `ReplayEngine` MUST NOT access EventStore или runtime-DB |
| I-REPLAY-2 | `upcast()` MUST применяться к каждому событию перед `reduce()` |
| I-REPLAY-3 | `initial_state()` MUST быть детерминированным (без timestamps, random) |
| I-REPLAY-4 | GoldenFixtures MUST NOT содержать production DB paths |
| I-REPLAY-5 | `SnapshotComparator` MUST нормализовать timestamps/UUIDs перед сравнением |
| I-REPLAY-6 | `SnapshotComparator` сравнивает ТОЛЬКО ключи из `expected_state`; `{}` → full compare с `initial_state()` |
| I-REPLAY-7 | `TaskEventSlice.full_sequence` MUST содержать `context_prefix` из `CONTEXT_EVENT_TYPES` |
| I-REPLAY-8 | `GoldenTestRunner` MUST log Warning если `fixture.schema_version < CURRENT_SYSTEM_VERSION` |
| I-REPLAY-9 | `TestCatalogProjection` MUST обновляться атомарно с EventLog append (через ProjectionRegistry) |
| I-REPLAY-10 | Adversarial scenarios генерируются только из FAILED задач; COMPLETE → только ScenarioGen |
| I-REPLAY-11 | `ReplayResult.synthetic_trace` строится инкрементально из events; доступ к TraceProjection запрещён |
| I-REPLAY-12 | `CONTEXT_EVENT_TYPES` — единственная константа в `task_event_slice.py`; изменяется только явным PR |
| I-REPLAY-13 | `TestCatalogEntry.affected_commands` вычисляется автоматически при `golden-approve`; ручная декларация запрещена |
| I-REPLAY-14 | `replay(EventLog) == current_state_from_StateProjection()`; проверяется при каждом sdd check-dod |
| I-REPLAY-16 | для каждой deterministic Projection P: `P.rebuild(EventLog) == P.current_state()`; approximate projections — отдельный контракт |

## Deterministic vs Approximate Projections

| Класс | Инвариант | Примеры |
|-------|-----------|---------|
| Deterministic | `P.rebuild(EventLog) == P.current_state()` | State, Trace, Graph, Policy, Idempotency |
| Approximate | `P.rebuild(EventLog) ≈ P.current_state()` (semantic equiv.) | EmbeddingProjection |

Только deterministic projections определяют system correctness.  
Approximate projections имеют отдельный контракт (near-neighbor consistency, не побитовое равенство).

**Reducer контракт:**

```text
I-REDUCER-1: reduce — pure function (no side effects)
I-REDUCER-2: reduce — total function (unknown event type → identity, not raise)
```

## When To Use

- Тестирование Reducer, Guards, Projections — Tier 1 (unit replay)
- Регрессионная защита задач фазы — Tier 2 (golden tests)
- M9 расчёт после SandboxManager.commit() — Tier 3 (автоматически через AuditEngine)
- `sdd test --diff HEAD~1` — developer flow перед коммитом

## Trade-offs

- Тесты зависят от качества event sequences — плохой EventLog → слабые тесты
- Изменение схемы Event требует обновления upcasters + golden fixtures
- Tier 3 встроен в Session Orchestrator flow — не изолированный процесс

## See Also

- [[replay-engine]]
- [[task-event-slice]]
- [[golden-fixture]]
- [[snapshot-comparator]]
- [[test-catalog-projection]]
- [[adversarial-scenario-mutator]]
- [[reducer]]
- [[upcaster-registry]]
- [[event-sourcing]]
- [[audit-engine]]
