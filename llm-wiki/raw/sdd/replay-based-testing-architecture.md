# Replay-Based Testing Architecture — Full Plan

**Source:** declarative-wandering-rain.md + grill-me session 2026-05-05  
**Status:** Architecture decisions finalized (13/13)  
**Target:** wiki pages in `pattern/` cluster

---

## Контекст

Текущая страница `pattern/replay-based-testing.md` — тонкий набросок. Нужно развить в полную живую архитектуру «ядра качества». Три ключевых усиления по сравнению с наивным подходом: Default State Merge, Context Slicing, Adversarial Mix. Плюс принципиально новая идея: Trace-Aligned Test Partitioning (TATP) — тесты как данные в Projection.

Все изменения — только в `/root/project/obsidian-vault/llm-wiki/wiki/`.

---

## Принцип

EventLog — SSOT (GL-2). Reducer — чистая функция (GL-1). Следствие: `state = reduce(events)` полностью детерминировано и тестируемо без моков. Вся система качества строится на этом.

---

## Три уровня тестов

```
Tier 1 — Unit Replay (L0 unit)
  Input:  list[Event]  (hand-crafted in test)
  Output: State delta + synthetic_trace
  Tested: Reducer + upcast chain + TraceAssertionChecker
  Sandbox: in-memory only, milliseconds
  Filter:  affected_commands (из TestCatalogProjection)

Tier 2 — Golden Tests (L0+L1 integration)
  Input:  GoldenFixture (.sdd/tests/golden/T-NNN.yaml)
  Output: State partial-match, Trace assertions
  Sandbox: temp PostgreSQL с initial_state()
  Filter:  scope.phase_id (из TestCatalogProjection)

Tier 3 — Regression Suite (production → test + adversarial)
  Input:  ScenarioSpec (успешные задачи) + AdversarialScenario (провальные)
  Output: M9 metric
  Sandbox: полный цикл с SandboxManager
  Trigger: AuditEngine.calculate_M9() внутри Session Orchestrator flow
  Filter:  TestCatalog filter + AdversarialScenario checks
```

---

## Архитектурные решения (grill-me, 2026-05-05)

### AD-1: TestCatalogProjection в ProjectionRegistry

**Решение:** Регистрация через command names (не event types).

TestCatalogProjection регистрируется в ProjectionRegistry с явными `subscribed_commands`:
```python
registry.register(TestCatalogProjection(), {
    "golden-approve",       # → GoldenFixtureApproved
    "complete-task",        # → ScenarioGenerated (условно, только COMPLETE)
    "update-policy",        # → PolicyUpdated
    "activate-phase",       # → PhaseInitialized
})
```

ProjectionRegistry роутит по command names — модель нетронута.

### AD-2: ScenarioGenerated → EventStore

**Решение:** Часть транзакции `complete-task`, условно только при COMPLETE.

`complete-task` handler эмитит `ScenarioGenerated` только если `task.status == COMPLETE`. WriteKernel включает оба события (`TaskCompleted` + `ScenarioGenerated`) в одну PostgreSQL транзакцию. Нет окна где задача DONE, но ScenarioSpec ещё нет.

### AD-3: Граница context_prefix

**Решение:** Статический whitelist event types в `CONTEXT_EVENT_TYPES: frozenset`.

```python
# task_event_slice.py
CONTEXT_EVENT_TYPES: frozenset[str] = frozenset({
    "PhaseInitialized",
    "PhaseContextSwitched",
    "PolicyUpdated",
    "BootstrapCompleted",
    # + любые другие event types от которых зависят Guards
})
```

`TaskEventSliceBuilder.from_store()` фильтрует EventLog: только события из `CONTEXT_EVENT_TYPES` до момента `TaskStarted(task_id)`. Детерминировано, не зависит от других задач фазы. При добавлении нового Guard'а, зависящего от нового event type — разработчик явно добавляет тип в константу.

### AD-4: `context_prefix: auto` резолвится при capture

**Решение:** `sdd golden-capture T-NNN` — fixture self-contained.

```bash
sdd golden-capture T-034   # читает EventLog, пишет .sdd/tests/golden/T-034.yaml
                            # context_prefix сериализован в YAML как конкретные события
sdd golden-approve T-034   # эмитит GoldenFixtureApproved → TestCatalogProjection
```

При запуске тестов EventLog не нужен — fixture полностью самодостаточна. Разработчик сам выбирает какие задачи достойны golden test (не автоматически на каждый complete-task).

### AD-5: AdversarialScenarioMutator

**Решение:** Статическая таблица `error_type → MutationStrategy`. Двухуровневая мутация.

```
Task FAILED
  → ErrorClassifier → error_type
  → MUTATION_TABLE[error_type] → MutationStrategy
  → AdversarialScenarioMutator.mutate()
      Tier 1/2: мутирует task_events (инвертирует payload, меняет порядок)
      Tier 3:   мутирует ScenarioSpec checks (инвертирует условия)
  → AdversarialScenario → Tier 3 Adversarial Suite
```

Пример таблицы:
```python
MUTATION_TABLE: dict[str, MutationStrategy] = {
    "SCOPE_VIOLATION":              MutateScopeInEvents(),
    "GRAPH_CHANGED_AFTER_EXPLAIN":  ReorderEvents(),
    "TIMEOUT":                      InjectDelayEvents(),
    "PERMISSION_DENIED":            EscalatePayload(),
}
```

Детерминированность важнее гибкости — никакой LLM-генерации мутаций.

### AD-6: `sdd test --diff` → changed_commands

**Решение:** CommandSpec changes + `file→command` registry → ProjectionRegistry lookup.

```bash
sdd test --diff HEAD~1
```

Алгоритм:
1. `git diff --name-only HEAD~1` → список изменённых файлов
2. Приоритет B: найти изменения в `CommandSpec` определениях → `changed_commands`
3. Fallback A: `handler_registry.yaml` (`file_path → command_name`) для файлов без CommandSpec
4. `ProjectionRegistry.subscribed_commands` → `changed_commands → changed_projections`
5. `TestCatalog.filter(commands=changed_commands)` → релевантные тесты
6. ReplayEngine запускает только их

```yaml
# handler_registry.yaml
src/sdd/handlers/write.py: write
src/sdd/handlers/resolve.py: resolve
src/sdd/guards/execution_guard.py: [write, resolve, explain]
```

### AD-7: TraceAssertionChecker

**Решение:** Работает на `ReplayResult.synthetic_trace` — синтезируется ReplayEngine из event stream.

```python
@dataclass
class ReplayResult:
    final_state: State
    snapshots: list[StateSnapshot]
    synthetic_trace: list[TraceEntry]   # ← новое поле

class ReplayEngine:
    def replay(self, events: list[Event]) -> ReplayResult:
        state = initial_state()
        snapshots = []
        trace = []
        for e in events:
            state = reduce(state, upcast(e))
            snapshots.append(StateSnapshot(event_id=e.id, state=state))
            trace.append(TraceEntry(kind=e.type, payload=e.payload, event_id=e.id))
        return ReplayResult(
            final_state=state,
            snapshots=snapshots,
            synthetic_trace=trace,
        )
```

Никакого DB доступа. Tier 1 тесты получают trace assertions бесплатно.

### AD-8: TestCatalogEntry.affected_commands — автовывод

**Решение:** Автовывод при `golden-approve` через обратный маппинг REGISTRY + ProjectionRegistry.

```python
# При golden-approve:
event_types = {e.type for e in fixture.task_events}
affected_commands = REGISTRY.inverse_lookup(event_types)    # event_type → command
affected_projections = ProjectionRegistry.projections_for(affected_commands)  # command → projections

entry = TestCatalogEntry(
    test_id=f"G-{fixture.task_id}",
    test_type=TestType.GOLDEN,
    affected_commands=affected_commands,
    affected_projections=affected_projections,
    scope={"phase_id": fixture.phase_id},
)
```

Нулевой ручной труд, не рассинхронизируется с кодом.

### AD-9: Tier 3 — встроен в Session Orchestrator flow

**Решение:** Tier 3 = AuditEngine.calculate_M9() + TestCatalog filter + AdversarialScenario checks.

Tier 3 — не новый процесс. AuditEngine уже считает M9 через ScenarioSpec checks после каждого `SandboxManager.commit()`. TATP добавляет к этому:
- Фильтрацию через TestCatalog (только релевантные ScenarioSpecs)
- AdversarialScenario checks как sub-метрика M9

Новых триггеров не нужно. `sdd test --diff` для developer flow запускает Tier 1 + Tier 2 (read-only).

### AD-10: Формат GoldenFixture — без `__partial__` sentinel

**Решение:** Списки — всегда subset check by default. `strict_lists: true` для точного match.

```yaml
# .sdd/tests/golden/T-034.yaml
task_id: T-034
phase_id: 3
schema_version: 1
strict_lists: false          # default: subset check для list-полей
context_prefix:
  - type: PhaseInitialized
    payload: {phase_id: 3}
  # ... сериализованные события из capture
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

Убраны `__partial__` sentinel и `tasks_done_value` — артефакт дизайна.

### AD-11: Новые CLI команды

**Решение:** `golden-approve` → REGISTRY write; `golden-capture` и `sdd test` → read-only.

| Команда | Тип | Событие | Примечание |
|---------|-----|---------|------------|
| `sdd golden-capture T-NNN` | read-only | — | Пишет YAML файл, I-READ-ONLY-EXCEPTION-1 |
| `sdd golden-approve T-NNN` | write (REGISTRY) | `GoldenFixtureApproved` | Триггер TestCatalogProjection |
| `sdd test --diff HEAD~1` | read-only | — | I-READ-ONLY-EXCEPTION-1 |
| `sdd test --tier 1\|2\|3` | read-only | — | Developer flow |

### AD-12: Default State Merge — только для пустого expected_state

**Решение:** `expected_state: {}` → семантика «нет мутаций от initial_state()».

```python
class SnapshotComparator:
    def compare(self, actual: State, expected: dict) -> CompareResult:
        if not expected:
            # Regression check: ничего не изменилось
            return self._compare_full(actual, initial_state())
        # Partial match: только явно указанные ключи
        return self._compare_partial(actual, expected)
```

Для всех остальных случаев — чистый partial match без merge.

### AD-13: Whitelist owner

**Решение:** `CONTEXT_EVENT_TYPES: frozenset` — единственная константа в `task_event_slice.py`.

Единственное место правды. При добавлении нового Guard'а, зависящего от нового event type — разработчик явно добавляет тип сюда. Нет конфигов, нет магии.

---

## Ключевые компоненты

### ReplayEngine (L0, pure)

```python
@dataclass
class StateSnapshot:
    event_id: str
    state: State

@dataclass
class TraceEntry:
    kind: str       # = event.type
    payload: dict
    event_id: str

@dataclass
class ReplayResult:
    final_state: State
    snapshots: list[StateSnapshot]
    synthetic_trace: list[TraceEntry]

class ReplayEngine:
    def replay(self, events: list[Event]) -> ReplayResult:
        state = initial_state()
        snapshots, trace = [], []
        for e in events:
            state = reduce(state, upcast(e))
            snapshots.append(StateSnapshot(event_id=e.id, state=state))
            trace.append(TraceEntry(kind=e.type, payload=e.payload, event_id=e.id))
        return ReplayResult(final_state=state, snapshots=snapshots, synthetic_trace=trace)
```

### TaskEventSlice + Context Slicing

```python
CONTEXT_EVENT_TYPES: frozenset[str] = frozenset({
    "PhaseInitialized", "PhaseContextSwitched",
    "PolicyUpdated", "BootstrapCompleted",
})

@dataclass
class TaskEventSlice:
    task_id: str
    phase_id: int
    schema_version: int
    context_prefix: list[Event]   # system init + фазовые события ДО TaskStarted
    task_events: list[Event]      # события самой задачи

    @property
    def full_sequence(self) -> list[Event]:
        return self.context_prefix + self.task_events

class TaskEventSliceBuilder:
    def from_store(self, task_id: str) -> TaskEventSlice:
        # context_prefix = события из CONTEXT_EVENT_TYPES до TaskStarted(task_id)
        # task_events = события с TaskStarted по TaskCompleted
        ...

    def from_fixture(self, fixture: GoldenFixture) -> TaskEventSlice:
        # context_prefix уже сериализован в YAML (auto резолвится при capture)
        ...
```

### SnapshotComparator

```python
class SnapshotComparator:
    SENTINEL_ANY = "__any__"

    def compare(self, actual: State, expected: dict) -> CompareResult:
        if not expected:
            return self._compare_full(actual, initial_state())
        return self._compare_partial(actual, expected)

    def _compare_partial(self, actual: State, expected: dict) -> CompareResult:
        # Нормализует timestamps/UUIDs
        # Сравнивает ТОЛЬКО ключи из expected
        # __any__ → любое значение OK
        # list поля → subset check (actual ⊇ expected_list)
        # strict_lists=True → exact match для list
        ...
```

### TestCatalogProjection (L1)

```python
@dataclass
class TestCatalogEntry:
    test_id: str                      # "G-T-034" | "S-abc123"
    test_type: TestType               # GOLDEN | SCENARIO | ADVERSARIAL
    affected_projections: list[str]
    affected_commands: list[str]
    scope: dict                       # {"phase_id": 3}

class TestCatalogProjection:
    subscribed_commands = {
        "golden-approve", "complete-task", "update-policy", "activate-phase"
    }

    def handle(self, event: Event) -> None:
        if event.type == "GoldenFixtureApproved":
            self._index_golden(event)
        elif event.type == "ScenarioGenerated":
            self._index_scenario(event)
        ...

    def filter(
        self,
        commands: list[str] | None = None,
        projections: list[str] | None = None,
        phase_id: int | None = None,
    ) -> list[TestCatalogEntry]: ...
```

### GoldenTestRunner

```python
class GoldenTestRunner:
    def run(self, fixture: GoldenFixture) -> TestResult:
        if fixture.schema_version < CURRENT_SYSTEM_VERSION:
            logger.warning(
                f"[Fixture {fixture.task_id}] schema_version={fixture.schema_version} "
                f"< system={CURRENT_SYSTEM_VERSION}. Upcasters active."
            )
        slice_ = TaskEventSliceBuilder().from_fixture(fixture)
        result = ReplayEngine().replay(slice_.full_sequence)
        state_ok = SnapshotComparator().compare(result.final_state, fixture.expected_state)
        trace_ok = TraceAssertionChecker().check(result.synthetic_trace, fixture.trace_assertions)
        return TestResult(state=state_ok, trace=trace_ok)
```

### AdversarialScenarioMutator

```python
MUTATION_TABLE: dict[str, MutationStrategy] = {
    "SCOPE_VIOLATION":              MutateScopeInEvents(),
    "GRAPH_CHANGED_AFTER_EXPLAIN":  ReorderEvents(),
    "TIMEOUT":                      InjectDelayEvents(),
    "PERMISSION_DENIED":            EscalatePayload(),
    # default: ABORT → InvertCriticalChecks() для Tier 3
}

class AdversarialScenarioMutator:
    def mutate(
        self,
        failed_slice: TaskEventSlice,
        failed_spec: ScenarioSpec,
        error_type: str,
    ) -> AdversarialScenario:
        strategy = MUTATION_TABLE.get(error_type, InvertCriticalChecks())
        mutated_events = strategy.mutate_events(failed_slice.task_events)   # Tier 1/2
        mutated_checks = strategy.mutate_checks(failed_spec.checks)         # Tier 3
        return AdversarialScenario(
            source_task_id=failed_slice.task_id,
            mutated_events=mutated_events,
            adversarial_checks=mutated_checks,
        )
```

---

## TATP — Trace-Aligned Test Partitioning

### Три Bounded Context домена

| Домен | affected_projections | Sandbox | Скорость |
|-------|---------------------|---------|----------|
| L0 Core | `["StateProjection"]` | in-memory | миллисекунды |
| L1 Execution | `["TraceProjection", "GraphSessionProjection"]` | temp PostgreSQL | секунды |
| L2 Governance | `["PolicyProjection"]` | full SandboxManager | минуты |

### EventLog Diff → таргетинг тестов

```bash
sdd test --diff HEAD~1
```

Алгоритм:
1. `git diff --name-only` → изменённые файлы
2. CommandSpec changes → `changed_commands` (приоритет)
3. `handler_registry.yaml` lookup → дополнительные `changed_commands`
4. `ProjectionRegistry.subscribed_commands` → `changed_projections`
5. `TestCatalog.filter(commands=changed_commands)` → N тестов
6. ReplayEngine: N тестов за секунды

```
Было: pytest → 40 мин → непонятный fail из другой фазы
Стало: sdd test --diff HEAD~1 → 4 релевантных теста → 2 сек
```

---

## Инварианты

| ID | Правило |
|----|---------|
| I-REPLAY-1 | `ReplayEngine` MUST NOT access EventStore или runtime-DB. UpcasterRegistry может читать маппинги схем из конфига — разрешено |
| I-REPLAY-2 | `upcast()` MUST применяться к каждому событию перед `reduce()` |
| I-REPLAY-3 | `initial_state()` MUST быть детерминированным (без timestamps, random) |
| I-REPLAY-4 | GoldenFixtures MUST NOT содержать production DB paths |
| I-REPLAY-5 | `SnapshotComparator` MUST нормализовать timestamps/UUIDs перед сравнением |
| I-REPLAY-6 | `SnapshotComparator` сравнивает ТОЛЬКО ключи, явно указанные в `expected_state` (partial match); исключение: `expected_state: {}` → full compare с `initial_state()` |
| I-REPLAY-7 | `TaskEventSlice.full_sequence` MUST содержать `context_prefix` из `CONTEXT_EVENT_TYPES` |
| I-REPLAY-8 | `GoldenTestRunner` MUST log Warning если `fixture.schema_version < CURRENT_SYSTEM_VERSION` |
| I-REPLAY-9 | `TestCatalogProjection` MUST обновляться атомарно с EventLog append (через ProjectionRegistry) |
| I-REPLAY-10 | Adversarial scenarios генерируются только из провальных задач; успешные → только ScenarioGen |
| I-REPLAY-11 | `ReplayResult.synthetic_trace` MUST строиться инкрементально из events во время replay; запрещён доступ к TraceProjection |
| I-REPLAY-12 | `CONTEXT_EVENT_TYPES` — единственная константа в `task_event_slice.py`; изменяется только явным PR |
| I-REPLAY-13 | `TestCatalogEntry.affected_commands` MUST вычисляться автоматически при `golden-approve` через REGISTRY inverse + ProjectionRegistry; ручная декларация запрещена |

---

## Файлы для создания/изменения

### 1. UPDATE `pattern/replay-based-testing.md`
Полная переработка: три уровня, TATP overview, ссылки на все новые паттерны, инварианты I-REPLAY-1..13. Точка входа для кластера.

### 2. CREATE `pattern/replay-engine.md`
`ReplayEngine` — L0, pure. `ReplayResult` + `StateSnapshot` + `TraceEntry` (synthetic_trace). AD-7.
`See Also`: reducer, upcaster-registry, task-event-slice, golden-fixture

### 3. CREATE `pattern/task-event-slice.md`
`TaskEventSlice` + `TaskEventSliceBuilder`. `CONTEXT_EVENT_TYPES` whitelist (AD-3, AD-13). `from_store` vs `from_fixture`. AD-4.
`See Also`: replay-engine, golden-fixture, event-sourcing

### 4. CREATE `pattern/golden-fixture.md`
Формат YAML (AD-10): `context_prefix` (сериализован при capture), `expected_state` (partial), `__any__`, `strict_lists`. Lifecycle: `golden-capture` → ревью → `golden-approve`. AD-4, AD-11.
`See Also`: replay-engine, snapshot-comparator, scenario-gen, task-event-slice

### 5. CREATE `pattern/snapshot-comparator.md`
Partial match только по заявленным ключам. `expected_state: {}` → full compare с `initial_state()` (AD-12). `__any__` sentinel. Subset check для lists, `strict_lists` flag (AD-10). Нормализация.
`See Also`: replay-engine, golden-fixture, replay-based-testing

### 6. CREATE `pattern/test-catalog-projection.md`
`TestCatalogProjection` (L1, в ProjectionRegistry через command names — AD-1). `TestCatalogEntry`, `affected_commands` автовывод (AD-8). Три домена (L0/L1/L2). `sdd test --diff` алгоритм (AD-6). TATP workflow.
`See Also`: projection-registry, replay-based-testing, memory-layer, audit-engine

### 7. CREATE `pattern/adversarial-scenario-mutator.md`
`AdversarialScenarioMutator`. Статическая `MUTATION_TABLE` (AD-5). Двухуровневая мутация: events (Tier 1/2) + checks (Tier 3). Anti-gaming для Tier 3. Lifecycle: `Task FAILED → ErrorClassifier → mutate → AdversarialScenario`.
`See Also`: scenario-gen, audit-engine, error-classifier, replay-based-testing

### 8. UPDATE `pattern/scenario-gen.md`
Добавить: ScenarioGen вызывается только при COMPLETE (AD-2). `ScenarioGenerated` эмитится в транзакции `complete-task`. Контраст с AdversarialScenarioMutator (FAILED path).

### 9. UPDATE `pattern/audit-engine.md`
Добавить: M9 использует TestCatalog filter (AD-9). Adversarial failures как sub-метрика M9. Tier 3 встроен в Session Orchestrator flow — не отдельный процесс.

---

## Проверка результата

- Все новые страницы: корректный frontmatter (`domain: sdd`, `page_type`, `tags`)
- `See Also` образуют связный граф без висячих ссылок
- `pattern/replay-based-testing.md` — точка входа для кластера
- I-REPLAY-1..13 задокументированы на главной странице
- TATP workflow (`sdd test --diff`) описан в `test-catalog-projection.md`
- Adversarial Mix чётко отделён от ScenarioGen (COMPLETE vs FAILED path)
- `strict_lists` flag описан в `golden-fixture.md` и `snapshot-comparator.md`
- `synthetic_trace` описан в `replay-engine.md`
- `CONTEXT_EVENT_TYPES` описан в `task-event-slice.md`
