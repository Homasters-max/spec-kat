# Spec_v34 — Phase 34: EventLog Deep Module

Status: Draft
Baseline: Spec_v15_KernelUnification.md, Spec_v28_WriteKernelGuard.md

---

## 0. Goal

Объединить два тонких взаимозависимых модуля — `infra/event_store.py` и `infra/event_log.py` — в единый глубокий модуль `infra/event_log.py` с классом `EventLog`. Текущая архитектура создаёт мелкий шов: `EventStore` делегирует к `sdd_append_batch` / `sdd_replay`, дублирует INSERT-логику в `_append_locked`, а вызывающий код импортирует запросные функции (`exists_command`, `exists_semantic`, `get_error_count`) напрямую из `event_log.py`, минуя класс. После слияния вся логика персистентности событий — запись, чтение, блокировка, идемпотентность, инвалидация, запросы — сосредоточена за одним интерфейсом `EventLog(db_path)`.

---

## 1. Scope

### In-Scope

- BC-34: EventLog Deep Module — слияние `event_store.py` → `event_log.py`, класс `EventLog`
- BC-34a: перенос `canonical_json()` в `core/`
- BC-34b: обновление всех импортов `EventStore` / `EventStoreError` на `EventLog` / `EventLogError`
- BC-34c: обновление kernel-contracts.md — замена замороженных поверхностей

### Out of Scope

См. §10.

---

## 2. Architecture / BCs

### BC-34: EventLog Deep Module

```
src/sdd/infra/
  event_log.py     # единственный модуль персистентности событий
                   # класс EventLog + legacy module-level функции
src/sdd/core/
  json_utils.py    # canonical_json() — перенесён из event_log.py
```

**Удаляется:**
```
src/sdd/infra/event_store.py   # весь файл
```

### Dependencies

```text
BC-34 → core/events.py         : DomainEvent, classify_event_level
BC-34 → core/errors.py         : SDDError, StaleStateError, KernelContextError
BC-34 → core/execution_context : assert_in_kernel, current_execution_context
BC-34 → infra/db.py            : open_sdd_connection
BC-34 → infra/paths.py         : event_store_file
BC-34a → core/json_utils.py    : canonical_json (новый модуль)
```

---

## 3. Domain Events

Новых доменных событий нет. Фаза является инфраструктурным рефактором без изменения EventLog-схемы.

### Event Catalog

| Event | Emitter | Description |
|-------|---------|-------------|
| _(нет новых)_ | — | — |

---

## 4. Types & Interfaces

### `EventLogError` (заменяет `EventStoreError`)

```python
class EventLogError(SDDError):
    """Raised when EventLog.append() cannot write to the EventLog."""
```

### `EventInput` (без изменений)

```python
@dataclass(frozen=True)
class EventInput:
    event_type: str
    payload: Mapping[str, Any]
    event_source: str = "runtime"
    level: str | None = None
    caused_by_meta_seq: int | None = None
```

### `EventLog` — Public Interface

```python
class EventLog:
    def __init__(self, db_path: str) -> None: ...

    def append(
        self,
        events: list[DomainEvent],
        source: str,
        command_id: str | None = None,
        expected_head: int | None = None,
        allow_outside_kernel: Literal["bootstrap", "test"] | None = None,
    ) -> None:
        """Atomically append events.

        Единый путь: если command_id или expected_head заданы — вся логика
        идёт через одну транзакцию (проверка MAX(seq) + дедупликация по
        command_id/event_index + INSERT). Без них — простой batch INSERT.

        Raises EventLogError on DB failure.
        Raises StaleStateError when expected_head != MAX(seq).
        Raises KernelContextError outside execute_command for production DB.
        Raises ValueError for unrecognized allow_outside_kernel value.
        """

    def replay(
        self,
        after_seq: int | None = None,
        level: str = "L1",
        source: str = "runtime",
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        """Return events ordered by seq ASC, excluding invalidated seqs."""

    def max_seq(self) -> int | None:
        """Return MAX(seq) from the EventLog, or None if empty."""

    def exists_command(self, command_id: str) -> bool:
        """Return True if any non-expired event with payload.command_id exists."""

    def exists_semantic(
        self,
        command_type: str,
        task_id: str | None,
        phase_id: int | None,
        payload_hash: str,
    ) -> bool:
        """Return True if matching (command_type, task_id, phase_id, payload_hash) exists."""

    def get_error_count(self, command_id: str) -> int:
        """Return count of ErrorEvent records for command_id."""
```

### Module-level (сохраняются в `event_log.py`)

```python
# legacy: raw event write — используется hooks/log_tool.py, metrics.py, тестами
def sdd_append(event_type, payload, db_path, level, event_source, caused_by_meta_seq) -> None: ...

# внутренний batch-путь, публичен для тест-инфраструктуры
def sdd_append_batch(events: list[EventInput], db_path: str) -> None: ...

@contextmanager
def meta_context(meta_seq: int) -> Generator[None, None, None]: ...

def archive_expired_l3(cutoff_ms: int, db_path: str) -> int: ...
```

### `core/json_utils.py` (новый модуль)

```python
def canonical_json(data: dict[str, Any]) -> str:
    """Stable JSON: sorted keys, no whitespace, ISO8601 UTC, no sci notation."""
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-EL-UNIFIED-1 | `infra/event_store.py` MUST NOT exist in the codebase. `EventLog` is the sole class for event persistence. | 34 |
| I-EL-UNIFIED-2 | `EventLog.append()` is the single write method. A separate `_append_locked()` method MUST NOT exist; locked and unlocked paths MUST share the same transaction-capable implementation. | 34 |
| I-EL-LEGACY-1 | `sdd_append()` MUST remain as a module-level function in `event_log.py`, marked with `# legacy: raw event write` comment. Its signature MUST NOT change. | 34 |
| I-EL-DEEP-1 | `exists_command`, `exists_semantic`, `get_error_count` MUST be instance methods of `EventLog`. Module-level versions of these functions MUST NOT exist after Phase 34. | 34 |
| I-EL-CANON-1 | `canonical_json()` MUST reside in `core/json_utils.py`. It MUST NOT exist in `infra/event_log.py` after Phase 34. | 34 |
| I-KERNEL-WRITE-1 (updated) | `EventLog.append` exclusively inside `execute_command` in `registry.py`. (Replaces prior form referencing `EventStore.append`.) | 34 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-DB-1 | `open_sdd_connection(db_path)` — `db_path` MUST be explicit non-empty str |
| I-DB-2 | CLI is the single point that resolves `event_store_file()` for default DB path |
| I-OPTLOCK-1 | `execute_command` verifies `EventLog.max_seq() == head_seq` before append |
| I-OPTLOCK-ATOMIC-1 | MAX(seq) check and INSERTs run inside a single DuckDB transaction |
| I-IDEM-SCHEMA-1 | Per-event uniqueness via `(command_id, event_index)` check within transaction |
| I-IDEM-LOG-1 | INFO log when all events were duplicates (`rows_inserted == 0`) |
| I-INVALID-CACHE-1 | Invalidation cache reset on every `append()` call |
| I-ES-1 | Single atomic write path — callers MUST NOT fall back to direct file mutation |
| I-ERROR-1 | Write Kernel MUST emit ErrorEvent before raising at every failure stage |

---

## 6. Pre/Post Conditions

### EventLog.append()

**Pre:**
- `db_path` — непустая строка (I-DB-1)
- `events` — непустой список `DomainEvent`
- Если `allow_outside_kernel is None` и `db_path` == production path: вызов внутри `execute_command` (I-KERNEL-WRITE-1)
- Если `allow_outside_kernel` задан: значение одно из `{"bootstrap", "test"}`
- Если `expected_head` задан: `MAX(seq) == expected_head` в момент начала транзакции (I-OPTLOCK-1)

**Post:**
- Все события записаны в одну DuckDB-транзакцию
- `_invalidated_cache` сброшен в `None`
- При `command_id`: дубликаты `(command_id, event_index)` пропущены; `rows_inserted == 0` → INFO лог (I-IDEM-LOG-1)

### EventLog.replay()

**Pre:**
- `db_path` — непустая строка

**Post:**
- Возвращает `list[dict]`, упорядоченный по `seq ASC`
- Инвалидированные `seq` отфильтрованы (кэш `_get_invalidated_seqs()`)
- Тип `payload` — `dict` (JSON распарсен)

---

## 7. Use Cases

### UC-34-1: Write Kernel — штатная запись событий

**Actor:** `execute_command()` в `registry.py`  
**Trigger:** handler возвращает список `DomainEvent`  
**Pre:** выполняется внутри `execute_command`; `head_seq` получен через `EventLog.max_seq()`  
**Steps:**
1. `EventLog.append(events, source, command_id=..., expected_head=head_seq)`
2. Если `MAX(seq) != head_seq` → `StaleStateError` → rollback → повтор или ERROR
3. INSERT всех событий в одну транзакцию с дедупликацией по `command_id/event_index`
**Post:** события записаны; `project_all()` получает актуальный лог через `EventLog.replay()`

### UC-34-2: Replay для reducer

**Actor:** `rebuild_state()` в `registry.py`  
**Trigger:** `project_all()` после COMMIT  
**Pre:** EventLog непуст  
**Steps:**
1. `EventLog.replay(level="L1", source="runtime")`
2. Инвалидированные seqs отфильтрованы автоматически
3. Результат передаётся в `reduce(events)` → `SDDState`
**Post:** `State_index.yaml` обновлён актуальным состоянием

### UC-34-3: Проверка идемпотентности перед выполнением

**Actor:** `execute_command()` / командные хэндлеры  
**Trigger:** входящая команда с `command_id`  
**Pre:** `db_path` передан в `EventLog`  
**Steps:**
1. `EventLog.exists_command(command_id)` → bool  
   или `EventLog.exists_semantic(...)` → bool
2. True → команда уже выполнена → ранний return без повторной записи
**Post:** EventLog не изменён; вызывающий получает сигнал об идемпотентности

### UC-34-4: Legacy-запись мета-событий (hooks/metrics)

**Actor:** `hooks/log_tool.py`, `infra/metrics.py`  
**Trigger:** запись мета-события без `DomainEvent`-объекта  
**Pre:** `db_path` известен вызывающему  
**Steps:**
1. `sdd_append(event_type, payload, db_path=db_path, level=..., event_source="meta")`
2. `sdd_append` остаётся module-level legacy-функцией  
**Post:** событие записано; вызывающий не конструирует `DomainEvent`

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-INFRA (db.py) | EventLog → | `open_sdd_connection` |
| BC-INFRA (paths.py) | EventLog → | `event_store_file()` для kernel-guard |
| BC-1 (core/events.py) | EventLog → | `DomainEvent`, `classify_event_level` |
| BC-1 (core/errors.py) | EventLog → | `SDDError`, `StaleStateError`, `KernelContextError` |
| BC-15 (registry.py) | registry → EventLog | `EventLog.append`, `EventLog.replay`, `EventLog.max_seq`, idempotency checks |

### Kernel-Contracts Update (I-KERNEL-EXT-1)

После Phase 34 таблица замороженных поверхностей в `kernel-contracts.md` обновляется:

| Было | Стало |
|------|-------|
| `infra/event_store.py` \| `EventStore.append()` | _(удалено)_ |
| `infra/event_log.py` \| `sdd_append()`, `sdd_append_batch()`, `sdd_replay()` | `infra/event_log.py` \| `EventLog.append()`, `EventLog.replay()`, `EventLog.max_seq()`, `sdd_append()` (legacy), `sdd_append_batch()` |

### Callers — Mandatory Import Updates

Файлы, требующие обновления импортов (`EventStore` → `EventLog`, `EventStoreError` → `EventLogError`):

**src/:**
- `commands/reconcile_bootstrap.py`
- `commands/validate_invariants.py`
- `commands/report_error.py`
- `commands/update_state.py`
- `commands/registry.py`

**tests/:**
- `harness/fixtures.py`
- `integration/test_runtime_enforcement.py`
- `integration/test_incident_backfill.py`
- `integration/test_failure_semantics.py`
- `property/test_concurrency.py`
- `property/test_schema_evolution.py`
- `property/test_performance.py`
- `unit/commands/test_command_idempotency.py`
- `unit/commands/test_validate_acceptance.py`
- `unit/infra/test_event_store.py` (переименовать в `test_event_log_class.py`)
- `unit/infra/test_write_kernel_guard.py`
- `unit/infra/test_event_invalidation.py`
- `fuzz/test_adversarial.py`

**Специальный случай:**
- `tests/regression/test_kernel_contract.py:35` — хардкодит путь `"src/sdd/infra/event_store.py"`; обновить на проверку отсутствия файла (I-EL-UNIFIED-1).

### `canonical_json` — callers

Файлы, импортирующие `canonical_json` из `event_log`, должны обновить импорт на `from sdd.core.json_utils import canonical_json`.

---

## 9. Verification

| # | Test Name | Invariant(s) |
|---|-----------|--------------|
| 1 | `test_event_log_append_simple` | I-EL-UNIFIED-2, I-ES-1 |
| 2 | `test_event_log_append_locked_optimistic` | I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1 |
| 3 | `test_event_log_append_idempotent` | I-IDEM-SCHEMA-1, I-IDEM-LOG-1 |
| 4 | `test_event_log_replay_filters_invalidated` | I-INVALID-CACHE-1 |
| 5 | `test_event_log_exists_command` | I-EL-DEEP-1 |
| 6 | `test_event_log_exists_semantic` | I-EL-DEEP-1 |
| 7 | `test_event_log_get_error_count` | I-EL-DEEP-1 |
| 8 | `test_event_store_module_deleted` | I-EL-UNIFIED-1 |
| 9 | `test_canonical_json_in_core` | I-EL-CANON-1 |
| 10 | `test_sdd_append_legacy_preserved` | I-EL-LEGACY-1 |
| 11 | `test_kernel_write_guard_via_event_log` | I-KERNEL-WRITE-1 (updated) |
| 12 | `test_write_kernel_full_chain_event_log` | I-2, I-3, I-HANDLER-PURE-1 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Миграция вызовов `sdd_append()` → `EventLog.append()` (замена legacy API) | Phase 35+ |
| Типизированный возврат `replay()` → `list[EventRecord]` | Phase 35+ |
| Удаление `sdd_append_batch()` как публичной функции | Phase 35+ |
| Изменение схемы DuckDB (`events` таблица) | Отдельный spec (EV-1: additive-only) |
| Reducer возвращает типизированные объекты вместо dict | Отдельный spec |
