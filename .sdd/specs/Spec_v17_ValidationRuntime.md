# Spec_v17 — Phase 17: Validation Runtime (VR)

Status: Draft
Baseline: Spec_v16_LegacyArchitectureClosure.md

---

## 0. Goal

Phase 16 завершила закрытие legacy-адаптеров, а Phase 15 унифицировала Write Kernel.
Ядро структурно стабильно, но не верифицировано **динамически**: нет property-тестов,
mutation-тестов, runtime enforcement и replay-эволюции.

Phase 17 вводит **Validation Runtime (VR)** — архитектурный компонент, равноправный ядру:

```
System := ⟨Kernel, ValidationRuntime⟩
VR проверяет свойства Kernel
System is VALID iff VR_Report.status == "STABLE"
```

"VALID" — не эфемерное "тесты зелёные", а воспроизводимый артефакт `.sdd/reports/VR_Report_v17.json`
с конкретными значениями kill rate, seed, commit hash и результатами P-1..P-10.

Единственное изменение в производственном коде: введение `ExecutionContext` в
`src/sdd/core/execution_context.py` — слой, принадлежащий ядру, а не тестам.

---

## 1. Scope

### In-Scope

- **BC-VR-0: ExecutionContext** — `src/sdd/core/execution_context.py` — stdlib-only ContextVar, часть ядра
- **BC-VR-1: System Harness** — `tests/harness/` — тонкий адаптер над двумя entry points
- **BC-VR-2: Property Engine** — Hypothesis-based тесты P-1..P-10 + RP в `tests/property/`
- **BC-VR-3: Fuzz Engine** — state-aware + interleaving sequences в `tests/fuzz/`
- **BC-VR-4: Runtime Enforcement** — context-based traps в `tests/integration/`
- **BC-VR-5: Evolution Validator** — backward + forward compat в `tests/integration/`
- **BC-VR-6: Mutation Engine** — mutmut с kill rate ≥ 95% + CRITICAL set 100%
- **BC-VR-7: CI Integration** — Makefile + `VR_Report_v17.json` артефакт
- **BC-VR-8: Failure Semantics** — детерминированность ошибок в `tests/integration/`

### Out of Scope

- Изменения в `src/sdd/**` кроме `core/execution_context.py` + одной строки в `registry.py`
- Изменения в `.sdd/specs/**` (иммутабельно, SDD-9)
- Удаление существующих тестов (CEP-3)
- Production observability (metrics, alerts) — Phase 18
- Distributed concurrency testing — Phase 18
- Fuzzing via external tools (AFL, libfuzzer) — Phase 18

---

## 2. Architecture / BCs

### Kernel Entry Points (неизменны, I-VR-API-1)

VR имеет право обращаться **только** к двум публичным функциям ядра:

```python
# I-VR-API-1: ONLY these two functions
execute_command(spec, cmd, db_path, ...) → list[DomainEvent]   # registry.py
get_current_state(db_path)              → SDDState             # projections.py
```

AST-скан (`tests/unit/test_handler_purity.py`) верифицирует I-VR-API-1.

### BC-VR-0: ExecutionContext (production code — ядро, не VR)

```
src/sdd/core/
  execution_context.py   # ContextVar + kernel_context + assert_in_kernel
```

`ExecutionContext` — часть ядра (stdlib-only: `contextvars`). VR использует его, но не владеет им.
Это устраняет cross-layer dependency: ядро не зависит от тестов.

```python
# src/sdd/core/execution_context.py
from contextvars import ContextVar
from contextlib import contextmanager

_EXECUTION_CTX: ContextVar[str | None] = ContextVar("_EXECUTION_CTX", default=None)

@contextmanager
def kernel_context(name: str):
    token = _EXECUTION_CTX.set(name)
    try:
        yield
    finally:
        _EXECUTION_CTX.reset(token)

def assert_in_kernel(operation: str) -> None:
    ctx = _EXECUTION_CTX.get()
    if ctx != "execute_command":
        raise KernelContextError(
            f"{operation} called outside execute_command (ctx={ctx!r})"
        )
```

`registry.py` оборачивает `execute_command` в `with kernel_context("execute_command")`.
Это единственное изменение в ядре. Любой новый write entry point MUST быть обёрнут
(I-EXEC-CONTEXT-1 — контроль через AST-скан, аналогично I-HANDLER-PURE-1).

### BC-VR-1: System Harness

```
tests/harness/
  __init__.py       # VR package marker
  api.py            # execute_sequence, replay, fork, rollback
  fixtures.py       # db_factory, event_factory, state_builder, make_minimal_event
  generators.py     # Hypothesis strategies
```

`tests/harness/context.py` **удалён** — реэкспортирует из `sdd.core.execution_context`.

### BC-VR-2: Property Engine

```
tests/property/
  __init__.py
  test_determinism.py            # P-1
  test_confluence.py             # P-2
  test_prefix_consistency.py     # P-3
  test_invariant_safety.py       # P-4
  test_no_hidden_state.py        # P-5
  test_event_integrity.py        # P-6
  test_idempotency.py            # P-7
  test_concurrency.py            # P-8
  test_schema_evolution.py       # P-9
  test_performance.py            # P-10 (O(N) slope, не абсолютный порог)
  test_state_transitions.py      # RP-1..RP-N (relational — delta properties)
```

### BC-VR-3: Fuzz Engine

```
tests/fuzz/
  __init__.py
  test_adversarial.py    # G4: concurrent, stale head, duplicate, schema corrupt
  test_interleaving.py   # G5: permutations of independent command sequences
```

### BC-VR-4 / BC-VR-5 / BC-VR-8: Integration Tests

```
tests/integration/
  test_runtime_enforcement.py   # VR-4: context-based traps
  test_evolution.py             # VR-5: backward + forward compat
  test_failure_semantics.py     # VR-8: deterministic failure modes
```

### BC-VR-6: Mutation Engine

```
.mutmut.toml                   # targets (6 модулей) + CRITICAL set
scripts/assert_kill_rate.py    # kill rate ≥ 95% + CRITICAL = 100%
```

### BC-VR-7: CI Integration + VR Report

```
Makefile                              # vr-fast, vr-full, vr-stress, vr-mutation, vr-release
pyproject.toml                        # + hypothesis>=6.100, mutmut
scripts/generate_vr_report.py         # создаёт .sdd/reports/VR_Report_v17.json
.sdd/reports/VR_Report_v17.json       # SSOT "системa VALID"
```

### Dependencies

```text
BC-VR-0 (ExecutionContext) → stdlib (contextvars) only
BC-VR-1 (Harness)         → Kernel.execute_command, Kernel.get_current_state, BC-VR-0
BC-VR-2 (Property Engine) → BC-VR-1
BC-VR-3 (Fuzz)            → BC-VR-1
BC-VR-4 (Enforcement)     → BC-VR-0, Kernel.execute_and_project
BC-VR-5 (Evolution)       → BC-VR-1
BC-VR-6 (Mutation)        → BC-VR-2 + BC-VR-3 (test suite как kill-detector)
BC-VR-7 (CI + Report)     → все BC-VR-*
BC-VR-8 (Failure)         → BC-VR-1
```

---

## 3. Domain Events

VR не эмитирует собственных domain events в производственный EventLog.
`ExecutionContext` использует `ContextVar` — in-memory, без персистентности.
`VR_Report_v17.json` — не event, а артефакт результата фазы (аналог `ValidationReport_T-NNN.md`).

---

## 4. Types & Interfaces

### VR Report (`scripts/generate_vr_report.py` → `.sdd/reports/VR_Report_v17.json`)

```json
{
  "phase": 17,
  "timestamp": "2026-...",
  "commit_hash": "...",
  "seed": 0,
  "vr_full": "PASS",
  "vr_mutation_kill_rate": 0.97,
  "vr_mutation_critical_kill_rate": 1.0,
  "properties": {
    "P1_determinism": "PASS",
    "P2_confluence": "PASS",
    "P3_prefix_consistency": "PASS",
    "P4_invariant_safety": "PASS",
    "P5_no_hidden_state": "PASS",
    "P6_event_integrity": "PASS",
    "P7_idempotency": "PASS",
    "P8_concurrency": "PASS",
    "P9_schema_evolution": "PASS",
    "P10_performance_slope": "PASS"
  },
  "relational_properties": {
    "RP1_task_completed_delta": "PASS",
    "RP2_phase_started_reset": "PASS",
    "RP3_decision_recorded_append": "PASS"
  },
  "failure_semantics": {
    "invalid_command_deterministic": "PASS",
    "stale_state_error_deterministic": "PASS",
    "corrupted_log_deterministic": "PASS"
  },
  "event_log_hash_sample": "...",
  "status": "STABLE"
}
```

**I-VR-REPORT-1:** `System VALID iff VR_Report.status == "STABLE"`

Отчёт обновляется только через `make vr-release`. Ручная правка запрещена.

### ExecutionContext (`src/sdd/core/execution_context.py`)

```python
class KernelContextError(SDDError):
    """Raised when a kernel operation is called outside execute_command."""

_EXECUTION_CTX: ContextVar[str | None] = ContextVar("_EXECUTION_CTX", default=None)

@contextmanager
def kernel_context(name: str) -> Iterator[None]: ...

def assert_in_kernel(operation: str) -> None: ...

def current_execution_context() -> str | None:
    """Read-only accessor for VR traps."""
    return _EXECUTION_CTX.get()
```

### Harness API (`tests/harness/api.py`)

```python
def execute_sequence(
    cmds: list[tuple[CommandSpec, Any]],
    db_path: str,
) -> tuple[list[DomainEvent], SDDState]:
    """I-VR-HARNESS-1: использует только execute_command."""

def replay(
    events: list[DomainEvent],
    db_path: str,
) -> SDDState:
    """I-VR-HARNESS-2: использует только get_current_state."""

def fork(
    events: list[DomainEvent],
    extra_cmds: list[tuple[CommandSpec, Any]],
    db_path: str,
) -> list[DomainEvent]:
    """replay(events) then execute_sequence(extra_cmds)."""

def rollback(
    events: list[DomainEvent],
    t: int,
) -> list[DomainEvent]:
    """Return events[:t]."""
```

### Hypothesis Generators (`tests/harness/generators.py`)

```python
# I-VR-NO-LOGIC-1: генераторы создают INPUTS — не содержат domain logic

@st.composite
def valid_command_sequence(draw, max_cmds: int = 10): ...

@st.composite
def edge_payload(draw, command_spec: CommandSpec): ...

@st.composite
def adversarial_sequence(draw): ...

@st.composite
def independent_command_pair(draw) -> tuple[Any, Any]:
    """Два независимых команды для G5 interleaving."""
    ...
```

---

## 5. Invariants

### New Invariants — VR Layer

| ID | Statement | Phase | Verification |
|----|-----------|-------|-------------|
| I-VR-REPORT-1 | `System VALID iff VR_Report.status == "STABLE"` | 17 | `scripts/generate_vr_report.py` |
| I-EXEC-CONTEXT-1 | Любая write-операция MUST выполняться внутри `kernel_context`; новые entry points MUST быть обёрнуты | 17 | AST-скан (аналог I-HANDLER-PURE-1) |
| I-VR-API-1 | `tests/harness/` использует ТОЛЬКО `execute_command` и `get_current_state` | 17 | AST-скан в `test_handler_purity.py` |
| I-VR-HARNESS-1 | `execute_sequence` MUST use only `execute_command` | 17 | `tests/unit/commands/test_harness.py` |
| I-VR-HARNESS-2 | `replay` MUST use only `get_current_state` | 17 | `tests/unit/commands/test_harness.py` |
| I-VR-HARNESS-3 | event_log is append-only (no mutation of existing events) | 17 | `tests/unit/commands/test_harness.py` |
| I-VR-HARNESS-4 | Каждый вызов VR использует `tmp_path`-изолированный DuckDB | 17 | fixture `db_factory` |
| I-VR-NO-LOGIC-1 | `generators.py` создаёт только INPUTS — не содержит domain logic | 17 | code review |
| I-STATE-DETERMINISTIC-1 | `SDDState` не содержит wall-clock, UUID, random ordering; `state_hash` детерминирован | 17 | P-1 |
| I-STATE-TRANSITION-1 | Каждый `DomainEvent` имеет детерминированный и проверяемый эффект на `SDDState`; конкретный delta проверен тестом RP-N | 17 | `test_state_transitions.py` |
| I-CONFLUENCE-STRONG-1 | Для независимых команд порядок выполнения не влияет на финальный `state_hash` | 17 | `test_interleaving.py` (G5) |
| I-PERF-SCALING-1 | `replay` time scales linearly with event count: `t(2N) / t(N) < 2.5` при N ≥ 1000 | 17 | `test_performance.py` (slope ratio) |
| I-VR-MUT-1 | Kill rate ≥ 95% по всему corpus; CRITICAL mutations kill rate = 100% | 17 | `make vr-mutation` + `assert_kill_rate.py` |
| I-MUT-CRITICAL-1 | Все мутанты в CRITICAL set (reducer core, event dispatch, guard pipeline, optimistic lock) MUST be killed | 17 | `assert_kill_rate.py --critical` |
| I-EVENT-UPCAST-1 | Исторические (v1) события upcast-ируются без потери данных и без crash | 17 | `test_evolution.py::test_event_schema_upcast_correctness` |
| I-EVOLUTION-FORWARD-1 | Система устойчива к появлению неизвестных будущих событий: `replay([v1_events + synthetic_v2])` не падает | 17 | `test_evolution.py::test_forward_unknown_event_safe` |
| I-FAIL-DETERMINISTIC-1 | Любая ошибка системы детерминирована и воспроизводима: одинаковый input → одинаковый error type + message | 17 | `test_failure_semantics.py` |
| **I-VR-STABLE-1** | Determinism: `replay(log, db1) == replay(log, db2)` (bit-exact via `state_hash`) | 17 | P-1 |
| **I-VR-STABLE-2** | Event Integrity: event log append-only, ordered, causally consistent | 17 | P-6 |
| **I-VR-STABLE-3** | Idempotency: `execute(cmd) × N → same state as × 1` | 17 | P-7 |
| **I-VR-STABLE-4** | Lock Safety: concurrent writes — exactly one succeeds, one `StaleStateError` | 17 | P-8 |
| **I-VR-STABLE-5** | Kernel Integrity: `EventStore.append` вызывается ТОЛЬКО из `execute_command` | 17 | VR-4 context-trap |
| **I-VR-STABLE-6** | State Purity: `SDDState = f(event_log)` — no YAML, no wall-clock, no UUIDs | 17 | P-5 |
| **I-VR-STABLE-7** | Invariant Safety: no invariant violation survives commit | 17 | P-4 |
| **I-VR-STABLE-8** | Evolution Safety: v1 upcast correct; unknown events skipped; future events safe | 17 | P-9, VR-5 |
| **I-VR-STABLE-9** | Performance: replay scales O(N) — slope ratio < 2.5 | 17 | P-10 (I-PERF-SCALING-1) |
| **I-VR-STABLE-10** | VR Coverage: `make vr-full` PASS + kill rate ≥ 95% + CRITICAL = 100% | 17 | `make vr-release` |

### Preserved Invariants (Phase 15)

| ID | Statement |
|----|-----------|
| I-HANDLER-PURE-1 | `handle()` returns events only — no EventStore, no file I/O |
| I-KERNEL-WRITE-1 | `EventStore.append` exclusively inside `execute_command` |
| I-KERNEL-PROJECT-1 | `rebuild_state` exclusively inside `project_all` |
| I-STATE-ACCESS-LAYER-1 | `get_current_state()` only from guards and projections |
| I-OPTLOCK-ATOMIC-1 | `EventStore.append` — max_seq check + INSERT in single DuckDB transaction |
| I-IDEM-1 | Same payload → same `command_id` → duplicate INSERT silently skipped |
| I-EXEC-ISOL-1 | Tests MUST use `tmp_path`-isolated DuckDB |

---

## 6. Pre/Post Conditions

### M0 — ExecutionContext (новый, первый)

**Pre:**
- Phase 16 COMPLETE
- `src/sdd/core/errors.py` содержит `SDDError` (база для `KernelContextError`)

**Post:**
- `src/sdd/core/execution_context.py` создан (stdlib-only, zero intra-sdd imports кроме `errors.py`)
- `src/sdd/commands/registry.py`: `execute_command` обёрнут в `with kernel_context("execute_command")`
- AST-скан (I-EXEC-CONTEXT-1) добавлен в `test_handler_purity.py`
- I-EXEC-CONTEXT-1 PASS

### M1 — Harness API

**Pre:**
- M0 COMPLETE

**Post:**
- `tests/harness/{api,fixtures,generators}.py` существуют
- `execute_sequence`, `replay`, `fork`, `rollback` работают
- I-VR-API-1, I-VR-HARNESS-1..4 PASS

### M2/M3 — Property Engine P-1..P-10 + RP

**Pre:**
- M1 COMPLETE
- `hypothesis>=6.100` добавлен в `pyproject.toml`

**Post:**
- `tests/property/` (11 файлов) существует
- `pytest tests/property/ --hypothesis-seed=0 -q` зелёный
- P-1..P-10 + RP-1..RP-N PASS
- P-10 проверяет **slope ratio**, не абсолютный порог: `t(2N) / t(N) < 2.5`

### M4 — Fuzz Engine (G4 + G5)

**Pre:**
- M1 COMPLETE, M2/M3 COMPLETE

**Post:**
- `tests/fuzz/test_adversarial.py` — G4 sequences PASS
- `tests/fuzz/test_interleaving.py` — G5: permutations of independent commands → I-CONFLUENCE-STRONG-1 PASS

### M5 — Runtime Enforcement

**Pre:**
- M0 COMPLETE (`execution_context.py` уже в production; `kernel_context` активен)

**Post:**
- `tests/integration/test_runtime_enforcement.py` (4 теста) зелёный
- I-VR-STABLE-5, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1, I-STATE-ACCESS-LAYER-1, I-HANDLER-PURE-1 динамически верифицированы

### M6 — Evolution Validator (backward + forward)

**Pre:**
- M1 COMPLETE
- `compatibility/fixtures/v1_events.json` создан

**Post:**
- `tests/integration/test_evolution.py` (6 тестов) зелёный
- I-EVENT-UPCAST-1 PASS
- I-EVOLUTION-FORWARD-1 PASS (forward simulation с synthetic V2 event)

### M7 — Failure Semantics

**Pre:**
- M1 COMPLETE

**Post:**
- `tests/integration/test_failure_semantics.py` (3 теста) зелёный
- I-FAIL-DETERMINISTIC-1 PASS: invalid command, stale state, corrupted log — детерминированные ошибки

### M8 — Mutation Engine

**Pre:**
- M2/M3/M4 COMPLETE
- `mutmut` добавлен в `pyproject.toml`

**Post:**
- `.mutmut.toml` с 6 target-модулями и явным CRITICAL set
- `scripts/assert_kill_rate.py --min 0.95 --critical-min 1.0` PASS
- I-VR-MUT-1, I-MUT-CRITICAL-1 PASS

### M9 — CI Integration + VR Report

**Pre:**
- M0..M8 COMPLETE

**Post:**
- `Makefile` содержит все targets
- `scripts/generate_vr_report.py` создаёт `.sdd/reports/VR_Report_v17.json`
- `VR_Report.status == "STABLE"`
- I-VR-REPORT-1 PASS

---

## 7. Use Cases

### UC-17-1: Property Test Run

**Actor:** Developer  
**Trigger:** `make vr-full`  
**Pre:** Phase 17 ACTIVE, `hypothesis` установлен  
**Steps:**
1. Hypothesis генерирует через `valid_command_sequence`, `edge_payload`, `adversarial_sequence`, `independent_command_pair`
2. Для P-1..P-10 + RP: `execute_sequence` → проверить свойство
3. Для RP-1: `TaskCompleted(id=X)` → `tasks_completed +1`, `X ∈ tasks_done_ids` — не просто "≤ total"
4. Для P-10: замер `t(N)` и `t(2N)` → `ratio < 2.5` (slope, не порог)
5. При нарушении: shrink → pytest FAIL с минимальным контрпримером  
**Post:** P-1..P-10 + RP PASS или найден воспроизводимый контрпример

### UC-17-2: Runtime Enforcement Trap

**Actor:** Pytest  
**Trigger:** `pytest tests/integration/test_runtime_enforcement.py -v`  
**Pre:** M0 COMPLETE  
**Steps:**
1. `monkeypatch` заменяет `EventStore.append` на `trap_append`
2. `execute_and_project(...)` → `kernel_context("execute_command")` активен → `assert_in_kernel` PASS
3. Прямой вызов `EventStore.append` вне контекста → `KernelContextError` → тест PASS  
**Post:** I-KERNEL-WRITE-1 верифицирован динамически

### UC-17-3: Interleaving Confluence Check

**Actor:** Pytest  
**Trigger:** `pytest tests/fuzz/test_interleaving.py -v`  
**Pre:** M4 COMPLETE  
**Steps:**
1. `independent_command_pair` генерирует `(cmd_a, cmd_b)` — независимые команды
2. Выполнить `[cmd_a, cmd_b]` → `state1`
3. Выполнить `[cmd_b, cmd_a]` → `state2`
4. `assert state1.state_hash == state2.state_hash`  
**Post:** I-CONFLUENCE-STRONG-1 PASS

### UC-17-4: Forward Evolution Simulation

**Actor:** Pytest  
**Trigger:** `pytest tests/integration/test_evolution.py::test_forward_unknown_event_safe -v`  
**Pre:** M6 COMPLETE  
**Steps:**
1. Загрузить `v1_events.json`
2. Вставить `{"event_type": "FutureV2Event", "level": "L1", ...}` в середину лога
3. `replay(v1_events + [synthetic_v2], tmp_db)` — НЕ должен падать
4. `state.schema_version == 1`, `state.phase_current >= 1`  
**Post:** I-EVOLUTION-FORWARD-1 PASS

### UC-17-5: Failure Determinism Verification

**Actor:** Pytest  
**Trigger:** `pytest tests/integration/test_failure_semantics.py -v`  
**Pre:** M7 COMPLETE  
**Steps:**
1. Выполнить invalid command дважды → оба раза одинаковый `error_type` и `message`
2. Спровоцировать `StaleStateError` дважды → воспроизводимо
3. Передать corrupted log → `replay` поднимает конкретный `SDDError` (не generic Exception)  
**Post:** I-FAIL-DETERMINISTIC-1 PASS

### UC-17-6: VR Report Generation

**Actor:** `make vr-release` (CI gate)  
**Trigger:** После `vr-full` + `vr-mutation` + `vr-stress`  
**Steps:**
1. `python scripts/generate_vr_report.py` собирает результаты
2. Записывает `.sdd/reports/VR_Report_v17.json` с `status: "STABLE"` или `"UNSTABLE"`
3. При `UNSTABLE` — `make vr-release` завершается exit 1  
**Post:** I-VR-REPORT-1 PASS — `VR_Report.status == "STABLE"`

### UC-17-7: Mutation Kill Verification

**Actor:** CI / nightly  
**Trigger:** `make vr-mutation`  
**Pre:** M8 COMPLETE  
**Steps:**
1. `mutmut run` — мутанты по 6 модулям
2. `pytest tests/ -x -q` на каждый мутант
3. `assert_kill_rate.py --min 0.95` → проверяет общий kill rate
4. `assert_kill_rate.py --critical-min 1.0` → проверяет CRITICAL set (100%)
5. При выживших CRITICAL мутантах — явный вывод с именем мутанта и модулем  
**Post:** I-VR-MUT-1 + I-MUT-CRITICAL-1 PASS

---

## 8. Integration

### Связь с Phase 15 инвариантами

| Phase 15 static check | Phase 17 dynamic verification |
|----------------------|-------------------------------|
| `make check-handler-purity` (grep) | VR-4 context-trap + I-EXEC-CONTEXT-1 AST |
| `test_handler_purity.py` (AST) | P-4 Invariant Safety + RP State Transitions |
| I-OPTLOCK-ATOMIC-1 (unit) | P-8 Concurrency + I-VR-STABLE-4 |
| I-IDEM-1 (unit) | P-7 Idempotency (Hypothesis) |
| I-FAIL-* (unit, static) | I-FAIL-DETERMINISTIC-1 (dynamic, reproducible) |

### Reducer не расширяется (I-KERNEL-EXT-1)

`SDDState` frozen dataclass. `state_hash` должен покрывать все поля,
влияющие на корректность — не включать `phase_status` (human-only поле, не детерминировано
через события) и wall-clock.

### pyproject.toml

```toml
[project.optional-dependencies]
dev = [
    "hypothesis>=6.100",
    "mutmut",
]
```

### Makefile

```makefile
vr-fast:
	pytest tests/unit/ tests/integration/ -q

vr-full:
	pytest tests/ -q
	pytest tests/property/ -q --hypothesis-seed=0
	pytest tests/integration/test_runtime_enforcement.py tests/integration/test_evolution.py \
	       tests/integration/test_failure_semantics.py -v

vr-stress:
	pytest tests/property/ -q --hypothesis-seed=random -x $(HYPOTHESIS_FLAGS)
	pytest tests/fuzz/ -q

vr-mutation:
	mutmut run
	mutmut results
	python scripts/assert_kill_rate.py --min 0.95 --critical-min 1.0

vr-release:
	make vr-full
	make vr-mutation
	make vr-stress
	python scripts/generate_vr_report.py

check: lint typecheck test check-handler-purity
ci: check vr-full
```

---

## 9. Verification

### Phase 17 Complete iff

```bash
make vr-release   # VR_Report.status == "STABLE"
pytest tests/ -q  # 446+ тестов без регрессий
```

### Test Suite

| # | Test / File | Invariant(s) Covered |
|---|-------------|----------------------|
| 1 | `tests/unit/commands/test_harness.py` | I-VR-HARNESS-1..4 |
| 2 | `tests/unit/test_handler_purity.py` (extended) | I-VR-API-1, I-EXEC-CONTEXT-1 |
| 3 | `tests/property/test_determinism.py` | I-VR-STABLE-1, I-STATE-DETERMINISTIC-1 |
| 4 | `tests/property/test_confluence.py` | I-VR-STABLE-1, I-VR-STABLE-6 |
| 5 | `tests/property/test_prefix_consistency.py` | I-VR-STABLE-7 |
| 6 | `tests/property/test_invariant_safety.py` | I-VR-STABLE-7 |
| 7 | `tests/property/test_no_hidden_state.py` | I-VR-STABLE-6 |
| 8 | `tests/property/test_event_integrity.py` | I-VR-STABLE-2 |
| 9 | `tests/property/test_idempotency.py` | I-VR-STABLE-3, I-IDEM-1 |
| 10 | `tests/property/test_concurrency.py` | I-VR-STABLE-4, I-OPTLOCK-ATOMIC-1 |
| 11 | `tests/property/test_schema_evolution.py` | I-VR-STABLE-8, I-EVENT-UPCAST-1 |
| 12 | `tests/property/test_performance.py` | I-VR-STABLE-9, I-PERF-SCALING-1 |
| 13 | `tests/property/test_state_transitions.py` | I-STATE-TRANSITION-1, RP-1..RP-N |
| 14 | `tests/fuzz/test_adversarial.py` | I-VR-STABLE-4, I-VR-STABLE-7 |
| 15 | `tests/fuzz/test_interleaving.py` | I-CONFLUENCE-STRONG-1 |
| 16 | `tests/integration/test_runtime_enforcement.py` | I-VR-STABLE-5, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1, I-STATE-ACCESS-LAYER-1, I-HANDLER-PURE-1 |
| 17 | `tests/integration/test_evolution.py` | I-VR-STABLE-8, I-EVENT-UPCAST-1, I-EVOLUTION-FORWARD-1 |
| 18 | `tests/integration/test_failure_semantics.py` | I-FAIL-DETERMINISTIC-1 |
| 19 | `scripts/assert_kill_rate.py` + `make vr-mutation` | I-VR-MUT-1, I-MUT-CRITICAL-1, I-VR-STABLE-10 |
| 20 | `scripts/generate_vr_report.py` + `VR_Report_v17.json` | I-VR-REPORT-1 |

### Proof by Destruction (обязательный spot-check)

```bash
# 1. Закомментировать PhaseGuard в registry.py
#    make vr-full → P-4 (invariant_safety) должен упасть → откатить

# 2. Убрать optimistic lock check в EventStore.append
#    make vr-full → P-8 (concurrency) должен упасть → откатить

# 3. Сломать reducer: TaskImplemented не инкрементирует tasks_completed
#    make vr-full → P-2 (confluence) + P-6 (event integrity) + RP-1 должны упасть → откатить

# 4. Убрать kernel_context wrap из execute_command
#    make vr-full → test_runtime_enforcement.py должен упасть → откатить

# 5. Выжившие CRITICAL мутанты (mutmut) → assert_kill_rate.py exit 1 → откатить
```

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Production observability (metrics, alerts) | Phase 18 |
| Distributed concurrency testing (multi-node) | Phase 18 |
| Fuzzing via external tools (AFL, libfuzzer) | Phase 18 |
| Performance profiling / flamegraphs | Phase 18 |
| Изменения в `.sdd/specs/**` | иммутабельно (SDD-9) |
| Удаление существующих тестов | запрещено (CEP-3) |
| Изменения в `src/sdd/**` кроме `core/execution_context.py` + `registry.py` | I-KERNEL-EXT-1 |

---

## Appendix A: Mutation Target Configuration

```toml
# .mutmut.toml
[mutmut]
paths_to_mutate = [
    "src/sdd/domain/state/reducer.py",       # M1, M2, M3
    "src/sdd/domain/guards/pipeline.py",      # M1
    "src/sdd/infra/event_store.py",           # M4, M5
    "src/sdd/commands/registry.py",           # M4, M5
    "src/sdd/infra/projections.py",           # M1, M2
    "src/sdd/core/events.py",                 # M6
]
tests_dir = "tests/"
runner = "python -m pytest tests/ -x -q"
```

CRITICAL set (I-MUT-CRITICAL-1 — kill rate = 100%):

| ID | Target | Killed by |
|----|--------|-----------|
| M1 | Remove guard from pipeline | P-4, RP |
| M2 | Skip invariant check in reducer | P-1 |
| M3 | Alter reducer event_type dispatch | P-2, RP-1 |
| M4 | Bypass optimistic lock check | P-8 |
| M5 | Break idempotency check | P-7 |
| M6 | Event schema corruption | P-6 |

---

## Appendix B: Relational Properties (VR-3b)

`test_state_transitions.py` проверяет delta, не range:

```python
# RP-1: TaskCompleted delta
events_before = replay(log[:t], db1)
events_after  = replay(log[:t+1], db2)
if log[t].event_type == "TaskImplemented":
    assert events_after.tasks_completed == events_before.tasks_completed + 1
    assert log[t].payload["task_id"] in events_after.tasks_done_ids

# RP-2: PhaseStarted reset
if log[t].event_type == "PhaseStarted":
    assert events_after.tasks_completed == 0
    assert events_after.tasks_done_ids == ()
    assert events_after.phase_current == log[t].payload["phase_id"]

# RP-3: DecisionRecorded — нет side-effect на tasks
if log[t].event_type == "DecisionRecorded":
    assert events_after.tasks_completed == events_before.tasks_completed
    assert events_after.phase_current == events_before.phase_current
```

`I-STATE-TRANSITION-1` = каждый `V1_L1_EVENT_TYPE` имеет RP-N тест.

---

## Appendix C: Definition of Stable (Kernel Stability Contract)

```
System is STABLE iff VR_Report.status == "STABLE", что означает:

  1. Determinism        replay(log, db1) == replay(log, db2)            [I-VR-STABLE-1]
  2. Event Integrity    log append-only, ordered, causally consistent   [I-VR-STABLE-2]
  3. Idempotency        execute(cmd) × N → same state as × 1            [I-VR-STABLE-3]
  4. Lock Safety        concurrent: one success, one StaleStateError     [I-VR-STABLE-4]
  5. Kernel Integrity   EventStore.append ONLY from execute_command      [I-VR-STABLE-5]
  6. State Purity       SDDState = f(event_log); no YAML/wall-clock      [I-VR-STABLE-6]
  7. Invariant Safety   no invariant violation survives commit           [I-VR-STABLE-7]
  8. Evolution Safety   v1 upcast; unknown events skipped; future safe   [I-VR-STABLE-8]
  9. Performance        replay O(N): t(2N)/t(N) < 2.5                   [I-VR-STABLE-9]
  10. VR Coverage       vr-full PASS, kill ≥ 95%, CRITICAL = 100%       [I-VR-STABLE-10]
```
