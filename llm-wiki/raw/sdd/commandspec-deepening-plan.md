# CommandSpec Deepening Plan
**Date:** 2026-05-05  
**Source:** 57 wiki-файлов с `domain: sdd` в `/obsidian-vault/llm-wiki/wiki/`  
**Method:** improve-codebase-architecture (deepening analysis)  
**Status:** DECISIONS MADE — готово к DRAFT_SPEC сессии

---

## Контекст

Анализ выявил шесть кандидатов на deepening. Ниже — финальные решения по каждому: принят/отклонён/модифицирован, с обоснованием.

---

## Решение A1: CommandSpec — финальный состав (Кандидат 1, ПРИНЯТ с изменениями)

### Проблема

В wiki зафиксированы три независимых boolean-флага на CommandSpec:
- `affects_trace: bool` (из `trace-projection.md`, `trace-store.md`)
- `graph_structural: bool` (из `graph-structural-offset.md`)
- `idempotent: bool` (из `command-bus.md`, `idempotency-middleware.md`)

Каждый флаг требует ручной синхронизации с отдельным инфраструктурным компонентом. Разработчик, добавляя команду, должен знать внутреннее поведение трёх несвязанных модулей. **Это мелкий интерфейс с широким когнитивным контрактом.**

Тест на удаление: убери флаги — логика маршрутизации расползётся по call-сайтам TraceProjection, GraphQueryEngine, IdempotencyMiddleware.

### Решение

```python
@dataclass(frozen=True)
class CommandSpec:
    command_name:  str
    command_type:  Type[Command]
    trace_scope:   TraceScope      # TASK_SCOPED | NONE
    graph_impact:  GraphImpact     # STRUCTURAL | NONE
    dedup:         IdempotencyMode # EXACT | NONE
```

### Решение по `trace_scope: INHERIT` (открытый вопрос → закрыт)

**INHERIT отклонён.** В SDD нет иерархии команд — CommandBus диспатчит независимые команды, у них нет parent-контекста для наследования. INHERIT — несуществующий концепт в этой модели. 

**Финальный enum:** `TraceScope = TASK_SCOPED | NONE`
- `TASK_SCOPED` — шаг записывается в trace текущего task (resolve, explain, write)
- `NONE` — команда не затрагивает trace (activate-phase, complete, record-session)

**Routing:** TraceProjection подписывается только на команды с `trace_scope == TASK_SCOPED`. Фильтр переезжает из ручного флага `affects_trace=true` в типизированный запрос к CommandRegistry.

### Решение по `graph_impact: CODE_HASH` (открытый вопрос → закрыт)

**CODE_HASH отклонён.** Причина: `code_hash` — это производная от состояния файловой системы, не от EventLog. Из `graph-structural-offset.md`:

```
cache_fingerprint = hash(code_hash + max_structural_event_offset)
```

Два канала инвалидации **независимы по природе**:
- `max_structural_event_offset` — вычисляется из EventLog по командам с `graph_impact == STRUCTURAL`
- `code_hash` — вычисляется из FS при каждом cache miss, **независимо от командного флага**

Привязка `CODE_HASH` к CommandSpec создала бы ложную зависимость: команда `write` меняет `code_hash` как побочный эффект записи в FS — это всегда верно, это не routing decision. GraphQueryEngine должен **всегда** пересчитывать `code_hash` при cache miss, вне зависимости от команды.

**Финальный enum:** `GraphImpact = STRUCTURAL | NONE`
- `STRUCTURAL` — команда порождает событие, меняющее структуру графа (activate-phase, complete, define-invariant, update-policy, bootstrap-policy)
- `NONE` — команда не меняет граф через EventLog (resolve, explain, record-session, switch-phase, write)

`code_hash`-инвалидация остаётся отдельным механизмом GraphQueryEngine, не флагом.

### God Object Guard (правило пользователя)

**Правило:** В CommandSpec попадают ТОЛЬКО enum-ы, используемые инфраструктурным слоем (L0/L1) для маршрутизации (Routing, Caching, Tracing).

Компонент-специфичная логика в CommandSpec **запрещена**. Пример нарушения: `context_boundary: bool` для ReplayEngine — это нарушение, потому что используется только TaskEventSlice (см. A4 ниже).

---

## Решение A2: Middleware Pipeline (Кандидат 2, МОДИФИЦИРОВАН)

### Проблема

Слоты middleware — "convention, not types". Порядок `ErrorClassifier → Logging → Idempotency → L0Guard → L1ExecutionGuard → L1ScopeGuard → WriteKernel` задан в фабрике `create_command_bus()` без типовой защиты.

### Решение

**Фабрика сохраняется.** Добавляется startup invariant test:

```python
def test_pipeline_order_invariant():
    pipeline = build_test_pipeline()
    slots = pipeline.slot_sequence()
    assert slots.index(L0GuardSlot) < slots.index(L1ExecutionGuardSlot)
    assert slots.index(IdempotencySlot) < slots.index(L0GuardSlot)
    assert slots[-1] == WriteKernelSlot
    assert not any(is_l1_dependency(s) for s in slots[:slots.index(IdempotencySlot)])
```

**Почему не PipelineSlot.Enum + dynamic registry:** Middleware pipeline собирается один раз при старте приложения. Это инициализационный код, не runtime-логика. Создавать динамический реестр ради кода, вызываемого единожды — over-engineering без leverage. Тест — это seam: нарушение порядка детектируется в CI, не в production.

---

## Решение A3: MutationRegistry (Кандидат 3, ПРИНЯТ с уточнением)

### Проблема

`AdversarialScenarioMutator` содержит статический `MUTATION_TABLE: dict[str, MutationStrategy]` с теми же `error_code` строками, что и `ErrorRegistry`. Два независимых словаря с одинаковыми ключами — нет ни compile-time, ни test-time проверки согласованности.

### Решение

**Не `ErrorMeta.mutation_strategy`.** Причина: mutation — тестовый концепт, `ErrorMeta` — доменный. Смешение testing concerns в error domain нарушает разделение слоёв L0/L1.

**Вместо этого — `MutationRegistry`** как отдельный объект в testing-модуле:

```python
# testing/mutation_registry.py
MutationRegistry: dict[str, MutationStrategy] = {
    ErrorCode.SCOPE_VIOLATION:           InjectScopeViolation(),
    ErrorCode.GRAPH_CHANGED_AFTER_EXPLAIN: InjectGraphFingerprint(),
    ErrorCode.TIMEOUT:                   InjectSlowExecution(),
    ErrorCode.PERMISSION_DENIED:         InjectPermissionDenial(),
}
DEFAULT_MUTATION = InvertCriticalChecks()
```

**Invariant test:**
```python
def test_mutation_registry_covers_all_error_codes():
    known_codes = set(ErrorRegistry.keys()) - {ErrorCode.UNKNOWN}
    assert known_codes.issubset(MutationRegistry.keys()), \
        f"Missing mutation strategies: {known_codes - MutationRegistry.keys()}"
```

**Locality:** testing concern остаётся в testing-модуле. **Leverage:** добавить error code = один файл (`error-registry`), тест укажет на нужность записи в `MutationRegistry`. **Тест:** выше — тривиален, поскольку данные структурно связаны через одну проверку.

---

## Решение A4: CONTEXT_EVENT_TYPES (Кандидат 4, ОТКЛОНЁН)

### Проблема

`TaskEventSlice.CONTEXT_EVENT_TYPES` — frozen set строк, требующий ручного обновления при добавлении Guard-зависимых event types. I-REPLAY-12 документирует это как известный риск.

### Почему отклонён `context_boundary: bool` в CommandSpec

**Command → Event это 1:many с неоднородными типами.** Пример из `graph-session-state.md`: команда `write` может породить `WriteExecuted` (НЕ context-событие) и `GraphResolved` (context-событие). Флаг на CommandSpec не позволяет различить события от одной команды. Это нарушает I-REPLAY-1 (State = reduce(EventLog)) и I-REPLAY-3.

**Intent (Command) ≠ Fact (Event).** Контекст replay — это набор фактов, предшествующих задаче. Команда — это намерение. Привязка context-принадлежности к намерению создаёт ложную абстракцию.

### Решение

Сохранить `CONTEXT_EVENT_TYPES` как явный whitelist в `TaskEventSlice`. Добавить safeguard:

```python
def test_context_event_types_covers_all_guard_dependencies():
    """I-REPLAY-12: Guards must not silently miss context events."""
    guard_event_reads = introspect_guard_event_types(ExecutionGuard, ScopeGuard)
    missing = guard_event_reads - TaskEventSlice.CONTEXT_EVENT_TYPES
    assert not missing, (
        f"Guards depend on event types not in CONTEXT_EVENT_TYPES: {missing}. "
        f"Update TaskEventSlice.CONTEXT_EVENT_TYPES (I-REPLAY-12)."
    )
```

**Явность лучше автоматизации** — контекст replay тонкая материя (подтверждено пользователем). Safeguard переводит silent incorrectness в hard CI failure.

---

## Решение A5: MetricCollector weights (Кандидат 5, ПРИНЯТ)

### Проблема

Каждый `MetricCollector` хранит `weight: float`. Сумма 9 весов = 1.0 ± 1e-9. Добавить M10 = изменить вес M10 И скорректировать ≥1 существующих collector. Интерфейс регистрации требует знания всех остальных.

### Решение

```python
class MetricCollector(Protocol):
    metric_id: str
    priority: int    # заменяет weight: float
    def collect(self, task_id: str, context: ScoreContext) -> float: ...
```

`AuditEngine` нормализует:
```python
total = sum(c.priority for c in collectors)
weight_i = collector.priority / total  # гарантировано sum == 1.0 математически
```

**Начальные приоритеты** (derived from current weights × 100):
```
M1=20, M2=20, M3=20, M4=10, M5=10, M6=10, M7=5, M8=5, M9=10
```

Семантика сохраняется. `sum == 1.0` больше не нужно проверять — это математическая гарантия, не invariant test.

**Leverage:** добавить M10 с `priority=15` — только один файл. AuditEngine автоматически пересчитывает все веса. **Locality:** логика взвешивания концентрируется в AuditEngine, не размазана по 9 коллекторам.

---

## Решение A6: Deprecated wiki links (Кандидат 6, ПРИНЯТ)

`meta-optimization.md` ссылается на `[[classified-recovery]]` — deprecated idea, поглощённую `error-registry` + `error-event` + `error-classifier`.

**Fix:**
1. В `classified-recovery.md`: добавить `superseded_by: [error-registry, error-event, error-classifier]` в frontmatter, добавить блок `## Deprecation Notice` в начало файла
2. В `meta-optimization.md`: заменить `[[classified-recovery]]` на `[[error-classifier]]` в разделе Dependencies

Это навигационный fix — устраняет dead-end для AI-агентов, читающих граф зависимостей.

---

## Итоговая таблица решений

| Кандидат | Решение | Ключевое обоснование |
|---|---|---|
| C1: CommandSpec flags | **ПРИНЯТ (модифицирован)** | bool → типизированные enum; INHERIT и CODE_HASH отклонены |
| C2: Middleware slots | **МОДИФИЦИРОВАН** | Фабрика + invariant test; dynamic registry — over-engineering |
| C3: MUTATION_TABLE | **ПРИНЯТ (уточнён)** | MutationRegistry в testing-модуле, не в ErrorMeta |
| C4: context_boundary | **ОТКЛОНЁН** | Command→Event 1:many; CONTEXT_EVENT_TYPES остаётся явным; добавить test |
| C5: MetricCollector | **ПРИНЯТ** | priority: int + нормализация; математическая гарантия вместо invariant |
| C6: deprecated links | **ПРИНЯТ** | Навигационный fix; dead-end устранён |

---

## Затронутые паттерны wiki

| Паттерн | Изменение |
|---|---|
| `command-bus.md` | ссылки на новые enum типы CommandSpec |
| `middleware-pipeline.md` | factory + startup invariant test |
| `idempotency-middleware.md` | `idempotent: bool` → `dedup: IdempotencyMode` |
| `trace-projection.md` | `affects_trace: bool` → `trace_scope == TASK_SCOPED` |
| `graph-structural-offset.md` | `graph_structural: bool` → `graph_impact: GraphImpact` |
| `adversarial-scenario-mutator.md` | MUTATION_TABLE → MutationRegistry (отдельный модуль) |
| `task-event-slice.md` | CONTEXT_EVENT_TYPES остаётся; добавить safeguard test |
| `metric-collector.md` | `weight: float` → `priority: int` |
| `audit-engine.md` | нормализация весов из priorities |
| `meta-optimization.md` | fix: `[[classified-recovery]]` → `[[error-classifier]]` |
| `idea/classified-recovery.md` | добавить `superseded_by` + Deprecation Notice |

---

## Следующий шаг

Решения A1–A3 и A5 — значимые архитектурные изменения, затрагивающие L0/L1 инфраструктуру.  
**Рекомендация:** `DRAFT_SPEC` сессия для формализации CommandSpec v2 (новые enum types + routing contracts).

Решения A4 и A6 — малые изменения внутри текущей фазы.  
**Рекомендация:** `IMPLEMENT` сессия для текущей фазы.
