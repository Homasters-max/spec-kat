# sdd_v2: Architecture Deepening — 6 Structural Decisions

_Status: DRAFT — для DRAFT_SPEC сессии_
_Date: 2026-05-05_
_Domain: sdd_
_Source: architectural review of wiki/idea/* + wiki/pattern/* (29 pages)_

---

## Контекст

Этот документ фиксирует шесть архитектурных решений для sdd_v2, выявленных при анализе wiki-страниц домена. Каждое решение устраняет конкретное противоречие между философией Event Sourcing и текущим описанием компонентов: скрытые зависимости, хранимое состояние там где должно быть вычислимое, несоответствие уровней L0/L1/L2.

Принятые решения организованы по принципу: **проблема → неправильный путь (если был предложен) → правильное решение → контракт**.

---

## Decision 1: TraceStore → TraceProjection

### Проблема

TraceStore описан как два интерфейса (TraceWriter + TraceReader) над одним `execution_log.jsonl`. Оба потребителя — ExecutionGuard (fingerprint check) и ScopeGuard (scope verification) — выполняют полный скан файла. ProjectionRegistry уже атомарно обновляет PostgreSQL-проекции на каждый EventLog append. TraceStore стоит рядом с этой инфраструктурой, но хранится в файле.

**Deletion test:** уберём TraceStore → ExecutionGuard и ScopeGuard теряют историю шагов. Значит TraceStore зарабатывает своё место. Проблема в реализации, не в назначении.

### Решение

TraceStore становится `TraceProjection` — полноправным членом ProjectionRegistry.

**Ключевое уточнение:** TraceProjection — это **частичная проекция**. Не все события из EventLog нужны для Trace. Например, `PolicyUpdated`, `PhaseCompleted`, `SessionDeclared` не нужны ExecutionGuard или ScopeGuard. ProjectionRegistry фильтрует события по флагу:

```
CommandSpec.affects_trace: bool
```

Флаг задаётся при регистрации команды в CommandRegistry. Только события от команд с `affects_trace = true` подаются в TraceProjection. Команды, которые затрагивают Trace: `resolve`, `explain`, `write` (любой Edit/Write tool call). Команды, которые не затрагивают: `activate-phase`, `bootstrap-policy`, `record-session`, `switch-phase`.

**TraceWriter** регистрируется как listener на CommandBus — hook на file_write, graph_call, explain. Write path не меняется для вызывающего кода.

**TraceReader** возвращает typed queries по `task_id`, без сырого скана:

```
TraceReader.get_fingerprint(task_id) -> GraphFingerprint
TraceReader.get_writes(task_id) -> list[FileWrite]
TraceReader.get_steps(task_id) -> list[TraceEntry]
```

### Контракт

- TraceProjection обновляется атомарно в той же транзакции что EventLog append (через ProjectionRegistry).
- `execution_log.jsonl` удаляется как runtime-артефакт.
- replay-based-testing работает для TraceProjection автоматически — тот же механизм что у других проекций.
- ScopeGuard и ExecutionGuard получают O(1) query вместо O(N) scan.

---

## Decision 2: Commit/Discard Gate — порядок операций

### Проблема

В `sdd-meta-harness` объявлен порядок: `SandboxManager commit/discard → AuditEngine → ScenarioGen`. ScenarioGen генерирует M9 (execution_correctness), AuditEngine использует M9 при расчёте AgentScore, SandboxManager принимает решение commit/discard — но в момент принятия решения M9 ещё не известен. Это логическое противоречие.

### Почему ScenarioGen.check_critical() — неправильный путь

Перенос gate-логики в ScenarioGen нарушает **I-HARNESS-BOUNDARY-1**: L2 компоненты генерируют данные, но не управляют state-мутациями в L1. ScenarioGen — L2, он производит ScenarioSpec. Решение "коммитить или нет" принадлежит L1.

### Правильное решение

**Двухфазный финал TaskRun:**

**Фаза A: Freeze + Score**

1. Агент завершил шаг → `SandboxManager.freeze()` — snapshot файловой системы, дальнейшие writes невозможны.
2. `AuditEngine.score(task_id, scenario_spec)` вычисляет M1-M9 **до коммита**, используя замороженный snapshot. `scenario_spec` подаётся как **входной параметр**, не запрашивается у ScenarioGen внутри. Это сохраняет L1/L2 boundary: AuditEngine не знает откуда пришла спека.
3. Из score извлекается `critical_passed: bool` (M9 > 0 и все critical checks прошли).

**Фаза B: Commit Gate (L1)**

4. `if critical_passed → SandboxManager.commit()` — изменения входят в основной репозиторий.
5. `else → SandboxManager.discard()` — snapshot удаляется.

**Фаза C: ScenarioGen (L2, после commit)**

6. `ScenarioGen.generate_full_spec(task_id)` — полная ScenarioSpec записывается как `ScenarioGenerated` event в EventLog. Это асинхронная L2-операция, она не блокирует commit.

**Откуда ScenarioSpec в AuditEngine?**

ScenarioSpec для текущего TaskRun создаётся при `start-task` как часть TaskDefinition (минимальная спека с critical checks). При запуске AuditEngine эта спека уже есть в State. ScenarioGen на L2 расширяет и финализирует её после завершения, формируя regression suite — это не blocking операция.

### Контракт

- `SandboxManager.freeze()` → `AuditEngine.score()` → `commit/discard` — строгий линейный порядок.
- AuditEngine принимает `scenario_spec: ScenarioSpec` как параметр, не зависит от ScenarioGen напрямую.
- Commit gate живёт в L1 (SandboxManager + AuditEngine). L2 получает данные после коммита.
- `critical_passed == false` → `ScenarioGenerated` event с `outcome: DISCARDED` всё равно эмитится (аудит).

---

## Decision 3: GraphSessionState → L0 Projection

### Проблема

`graph-session-state` описан как in-memory структура в L1: `has_graph`, `has_explain`, `graph_fingerprint`, `writes_count`. `agent-handle` говорит "crashes recover via EventLog replay" — но механизм восстановления нигде не специфицирован как интерфейс. ExecutionGuard держит GraphSessionState в памяти и теряет его при краше агента.

Это нарушение базового принципа Event Sourcing: **State = reduce(EventLog)**. GraphSessionState — это исключение, которое хранится а не вычисляется.

### Решение

GraphSessionState становится **L0 Projection**, обновляемой инкрементально Reducer'ом при добавлении событий:

| Событие | Эффект на GraphSessionState |
|---|---|
| `GraphResolved` | `has_graph = true`, `graph_fingerprint = event.fingerprint` |
| `ExplainExecuted` | `has_explain = true`, `fingerprint_locked = event.fingerprint` |
| `WriteExecuted` | `writes_count += 1`, `has_graph = false`, `has_explain = false` (reset — агент готов к следующему циклу) |
| `TaskCompleted` | финальный snapshot фиксируется **без сброса флагов**: `writes_count > 0 & has_explain == true` является признаком протокольного завершения задачи |

**Важный нюанс сброса при WriteExecuted:** сброс `has_graph/has_explain` в `false` означает что для следующей записи агент обязан заново пройти `resolve → explain`. Это намеренный инвариант протокола. При `TaskCompleted` Reducer сохраняет состояние проекции как есть — если последним событием был `WriteExecuted`, финальный snapshot покажет `has_graph = false, has_explain = false, writes_count = N`. Это корректно: задача завершена, цикл закрыт, флаги отражают состояние **после** последнего write, не состояние "была ли задача выполнена правильно". Для аудита протокольности используется `writes_count > 0` в сочетании с отсутствием `GuardViolation` событий в TraceProjection — не финальное значение флагов.

**Метод восстановления** становится явным и тривиальным:

```
GraphSessionState.current(task_id: TaskId, reader: ProjectionReader) -> GraphSessionState
```

Это просто SELECT из GraphSessionProjection (уже в ProjectionRegistry из `sdd-component-inventory`).

**ExecutionGuard становится полностью stateless**: при каждом вызове он читает ProjectionReader, не держит state в памяти.

### Контракт

- `GraphSessionState` убирается из L1 in-memory структур.
- `GraphSessionProjection` добавляется в ProjectionRegistry.
- ExecutionGuard: `guard(command, context, reader: ProjectionReader) -> GuardResult`.
- Replay тест: воспроизвести `[GraphResolved, ExplainExecuted, WriteExecuted]` → assert projection state.
- Краш агента: при рестарте ExecutionGuard читает ProjectionReader — состояние восстановлено автоматически.

---

## Decision 4: AuditEngine — MetricSource Seam

### Проблема

M1-M9 вычисляются из разнородных источников:
- M1 (protocol compliance) — TraceStore
- M2 (scope adherence) — ScopeGuard лог
- M3 (tests passed) — sandbox вывод
- M4-M8 — TraceStore, различные срезы
- M9 (execution correctness) — ScenarioSpec critical checks

AuditEngine знает о каждом источнике напрямую. Добавление M10 требует менять AuditEngine и регистрировать новый источник. Нет явного контракта "что именно нужно от каждого источника".

**Deletion test:** удали AuditEngine — AgentScore исчезает. Это **глубокий модуль**, его интерфейс мелкий. Проблема в том, что имплементация слишком широко знает о других компонентах.

### Решение

**MetricCollector** интерфейс:

```
protocol MetricCollector:
    metric_id: MetricId       # M1..M9, расширяемо
    weight: float             # сумма весов всех collectors = 1.0
    collect(task_id: TaskId, context: ScoreContext) -> float  # возвращает 0.0..1.0
```

**ScoreContext** — read-only view на всё что нужно для scoring:

```
ScoreContext:
    trace: TraceReader
    sandbox_output: SandboxOutput
    scenario_spec: ScenarioSpec
    policy: PolicyProjection
```

**AuditEngine** становится простым агрегатором:

```
AuditEngine:
    collectors: list[MetricCollector]  # зарегистрированы при инициализации

    score(task_id, context) -> AgentScore:
        samples = [c.collect(task_id, context) for c in collectors]
        critical_passed = all(
            s > 0 for c, s in zip(collectors, samples) if c.metric_id == M9
        )
        total = sum(c.weight * s for c, s in zip(collectors, samples))
        return AgentScore(total=total, samples=samples, critical_passed=critical_passed)
```

**Locality Collectors по Bounded Context:**

| Collector | Живёт рядом с |
|---|---|
| `ProtocolComplianceCollector` (M1) | `execution-guard` |
| `ScopeAdherenceCollector` (M2) | `scope-guard` |
| `TestPassCollector` (M3) | `sandbox-manager` |
| `FocusCollector` (M4) | `trace-store` (TraceProjection) |
| `TimeCollector` (M5) | `session-orchestrator` |
| `GuardViolationCollector` (M6) | `error-classifier` |
| `CompletionCollector` (M7) | `task state projection` |
| `StepCorrectnessCollector` (M8) | `trace-store` (TraceProjection) |
| `ExecutionCorrectnessCollector` (M9) | `audit-engine` / harness boundary |

Каждый Collector регистрируется в AuditEngine при сборке (dependency injection, не автодискавери).

**Валидация весов при инициализации:**

```
AuditEngine.__init__(collectors):
    total_weight = sum(c.weight for c in collectors)
    if abs(total_weight - 1.0) > 1e-9:
        raise SystemInitializationError(
            f"MetricCollector weights must sum to 1.0, got {total_weight}"
        )
    self.collectors = collectors
```

Это hard failure при старте системы, не runtime warning. Некорректный набор коллекторов делает AgentScore бессмысленным — система не должна стартовать с невалидной конфигурацией аудита.

### Контракт

- AuditEngine не импортирует ничего из ScopeGuard, ExecutionGuard или TraceStore напрямую.
- `AuditEngine.__init__` выполняет `assert sum(weights) == 1.0`, иначе `SystemInitializationError` — жёсткая проверка на старте.
- Добавление метрики = новый класс + регистрация + корректировка весов; несогласованные веса → система не стартует.
- Тест AuditEngine: mock collectors возвращающие фиксированные значения → assert score.
- Тест валидации: передать collectors с суммой весов 1.15 → assert SystemInitializationError.
- Тест каждого Collector: replay events в TraceProjection → assert collect() возвращает ожидаемое.

---

## Decision 5: PolicyKernel Bootstrap — YAML как артефакт деплоя

### Проблема

PolicyKernel хранит правила как `PolicyUpdated` events в EventLog (не файлы). Но `policy-kernel` говорит "Bootstrap from norm_catalog.yaml → EventLog". Механизм этого перехода нигде не описан. Это нарушение: если EventLog — SSOT, то начальное состояние тоже должно быть в EventLog с аудитом.

Дополнительная проблема: "курица и яйцо" при первом деплое — PolicyProjection пуста, guard'ы не знают правил, система не может стартовать.

### Решение

**`sdd bootstrap-policy --from norm_catalog.yaml`** — явная L1 команда, выполняется один раз при деплое.

**Ключевое уточнение:** команда эмитит не специальный `PolicySeeded` тип, а поток стандартных **`PolicyUpdated`** событий — по одному на каждую норму из YAML. ProjectionRegistry строит PolicyProjection из этих событий без специального кода для "сидирования":

```
bootstrap-policy handler:
    for norm in parse_yaml(path):
        emit PolicyUpdated(
            norm_id=norm.id,
            rule=norm.rule,
            actor="human",
            source="bootstrap",
            yaml_hash=hash(norm_catalog.yaml)
        )
```

**Idempotency guard:** повторный `bootstrap-policy` проверяет EventLog на наличие `PolicyUpdated` с `source="bootstrap"` и тем же `yaml_hash`. Если найдено — NOOP с предупреждением. Если YAML изменился — требует `--force` флаг с явным подтверждением.

**norm_catalog.yaml после bootstrap:**

- Становится **артефактом сборки/деплоя**, не рантайм-источником.
- PolicyKernel в рантайме читает только PolicyProjection (EventLog-based).
- YAML используется только для: `bootstrap-policy`, документации, code review.
- Изменение нормы в рантайме = новый `PolicyUpdated` event через `sdd update-policy`, не правка файла.

### Контракт

- Первый старт системы: `sdd bootstrap-policy --from .sdd/norms/norm_catalog.yaml`.
- PolicyProjection строится из EventLog как любая другая проекция (replay-based-testing работает).
- `bootstrap-policy` — human-only команда (actor validation guard).
- Тест: replay `[PolicyUpdated × N]` → assert PolicyProjection содержит все нормы.

---

## Decision 6: GraphQueryEngine — Структурный Fingerprint

### Проблема

GraphQueryEngine кэширует результаты по:

```
fingerprint = hash(code_hash + spec_hash + event_offset)
```

`event_offset` — номер последнего события в EventLog. При write-heavy workflow (много мелких команд в TaskRun) `event_offset` растёт на каждый append, инвалидируя кэш после каждой команды. Большинство этих событий (`TraceEntry`, `SessionDeclared`, `ErrorClassified`) не меняют граф — граф строится из Code, Specs, и структурных событий.

### Решение

Заменить `event_offset` на **`graph_structural_offset`** — offset последнего **графо-структурного** события.

Флаг на CommandSpec в CommandRegistry:

```
CommandSpec:
    ...
    graph_structural: bool  # default: false
```

**Команды с `graph_structural = true`** (полный список):

| Команда | Почему граф меняется |
|---|---|
| `activate-phase` | новая фаза = новые узлы в графе |
| `complete T-NNN` | задача завершена = edge status меняется |
| `define-invariant` | новый инвариант = новый узел |
| `update-policy` | политика влияет на доступность узлов |
| `bootstrap-policy` | начальное состояние политики |

**Команды с `graph_structural = false`** (кэш не инвалидируется):

| Команда | Почему граф не меняется |
|---|---|
| `resolve` | read-only query |
| `explain` | read-only, фиксирует fingerprint |
| `write` (file edit) | меняет code_hash, не event-граф |
| `record-session` | мета-данные сессии |
| `switch-phase` | навигация, не мутация |

**Новый fingerprint:**

```
graph_structural_offset = max(
    event.offset
    for event in EventLog
    if REGISTRY[event.command_name].graph_structural == true
)

fingerprint = hash(code_hash + spec_hash + graph_structural_offset)
```

**Уточнение про `code_hash`:** `code_hash` меняется при каждом `write` (Edit/Write tool call агента). Это правильно — изменение кода должно инвалидировать кэш. Только `event_offset` заменяется на `graph_structural_offset`.

### Контракт

- `CommandSpec.graph_structural: bool` регистрируется в CommandRegistry (не в отдельном whitelist).
- GraphQueryEngine читает флаги из CommandRegistry, не хардкодит имена команд.
- Locality: решение "какие команды меняют граф" живёт рядом с определением команд.
- В рамках одного TaskRun (цикл resolve → explain → write × N) граф не перестраивается между шагами.
- **Инвалидация по `code_hash` при `write` — обязательна и ожидаема.** Изменение кода может добавить или удалить узлы графа (новые функции, удалённые классы). Три `write` подряд (микро-правки) = три пересборки графа. Это корректное поведение: граф строится из актуального кода, и каждый write потенциально меняет его структуру. Оптимизация этого случая (batch writes) — вне scope данного решения.
- Тест: после N `resolve` вызовов без промежуточных `write` → assert cache hits = N-1 (первый всегда miss).
- Тест инвалидации: `resolve` → cache built → `write` (code_hash изменился) → `resolve` → assert cache miss (rebuild).

---

## Сводная таблица решений

| # | Компонент | Тип изменения | Ключевой инвариант |
|---|---|---|---|
| 1 | TraceStore → TraceProjection | JSONL → PostgreSQL projection | `CommandSpec.affects_trace` фильтрует events |
| 2 | Commit Gate ordering | freeze → score → commit/discard | AuditEngine получает ScenarioSpec как параметр |
| 3 | GraphSessionState → L0 Projection | in-memory → EventLog-derived | `GraphSessionProjection` в ProjectionRegistry |
| 4 | AuditEngine MetricSource seam | direct deps → MetricCollector registry | Collectors по Bounded Context |
| 5 | PolicyKernel bootstrap | implicit → `bootstrap-policy` command | `PolicyUpdated` events, YAML = deploy artifact |
| 6 | GraphQueryEngine cache | event_offset → graph_structural_offset | `CommandSpec.graph_structural` в CommandRegistry |

## Связанные компоненты

Изменения формируют единый кластер вокруг трёх принципов:

1. **State = reduce(EventLog)** — решения #1, #3, #5 устраняют компоненты-исключения из этого принципа.
2. **L0/L1/L2 boundary** — решение #2 убирает L2→L1 управляющую зависимость.
3. **CommandRegistry как SSOT** — решения #1, #6 добавляют `affects_trace` и `graph_structural` флаги, делая Registry единым местом описания поведения команд.

## Следующий шаг

Эти решения изменяют контракты L0 компонентов (ProjectionRegistry, CommandSpec, Reducer). Рекомендуется: **DRAFT_SPEC сессия** для формализации расширений CommandSpec и новых типов событий (`WriteExecuted`, `GraphResolved`, `ExplainExecuted`).
