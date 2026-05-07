# Spec_v22 — Phase 22: ValidationRuntime Refinement (VRR)

Status: Draft
Baseline: Spec_v17_ValidationRuntime.md

---

## 0. Goal

Phase 17 (ValidationRuntime) ввела полный pipeline валидации: subprocess execution loop, acceptance check, DuckDB event recording, idempotency guard. Однако финализация выявила четыре системных дефекта в слое исполнения, которые не были формально специфицированы и остались как неконтролируемые инварианты.

**Дефект 1: Недетерминированный timeout-sentinel.** Subprocess-loop записывал `returncode = -1` при SIGKILL-timeout. Значение `-1` — «магическое число» без семантики. Конвенция GNU `timeout(1)` использует `124` — это общепринятое значение в контексте validation pipelines. Важно: POSIX не резервирует `124` и любой процесс теоретически может его вернуть; семантика «timeout» применяется только внутри ValidationRuntime при интерпретации `TestRunCompleted.returncode`.

**Дефект 2: Непрозрачный DuckDB lock error.** `open_sdd_connection()` при исчерпании retry-timeout пробрасывал `duckdb.IOException` — тот же тип, что и при ошибках файловой системы, сети, прав доступа. Caller не может отличить transient lock contention от структурной IO-проблемы без парсинга строки исключения. Нужен `DuckDBLockTimeoutError(RuntimeError)`.

**Дефект 3: Дублирование subprocess в acceptance.** `_run_acceptance_check` запускала `["pytest", "tests/", "-q"]` независимо от build loop, который уже прогнал `test: pytest tests/ -q`. Это удваивало время validation и нарушало I-CMD-6: build loop — единственный источник истины о test results. Acceptance должна потреблять результат, а не воспроизводить его.

**Дефект 4: Отсутствие формальных уровней тестирования.** `project_profile.yaml` содержал единственную `test` команду, запускающую весь тест-сьют (включая property/fuzz). Это создавало ложный DoD: быстрая валидация в pipeline и глубокая проверка корректности — разные контракты и должны быть явно разделены.

Phase 22 закрывает все четыре дефекта через новые инварианты и BC-контракты.

---

## 1. Scope

### In-Scope

- **BC-22-0**: `TIMEOUT_RETURN_CODE` — константа в `src/sdd/commands/validate_invariants.py`
- **BC-22-1**: `DuckDBLockTimeoutError` — новый exception-тип в `src/sdd/infra/db.py`
- **BC-22-2**: `_run_acceptance_check` fail-fast semantics — параметр `test_returncode`, удаление fallback subprocess
- **BC-22-3**: Test-level separation — `test` и `test_full` в `.sdd/config/project_profile.yaml`

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-22-0: TIMEOUT_RETURN_CODE

```
src/sdd/commands/validate_invariants.py
  TIMEOUT_RETURN_CODE = 124   # follows GNU timeout(1) convention
```

Правило: любой subprocess timeout в build loop → `returncode = TIMEOUT_RETURN_CODE`. Значение `-1` запрещено (I-TIMEOUT-1). Значение `124` семантически интерпретируется как timeout в пределах ValidationRuntime; конфликт с реальным exit-кодом процесса возможен теоретически и считается приемлемым — `TIMEOUT_RETURN_CODE` применяется только в контексте `TimeoutExpired` exception.

### BC-22-1: DuckDBLockTimeoutError

```
src/sdd/infra/db.py
  class DuckDBLockTimeoutError(RuntimeError):
      """Raised when open_sdd_connection cannot acquire DuckDB file lock within timeout_secs."""
```

Контракт `open_sdd_connection()`:
- `db_path == ":memory:"` → немедленный connect, без retry (in-memory не имеет file lock)
- `duckdb.IOException` с маркером `"Could not set lock"` → retry до deadline (классификация best-effort, string-based; нестабильна между версиями DuckDB)
- При достижении deadline → `raise DuckDBLockTimeoutError(f"DuckDB lock timeout after {timeout_secs}s on '{db_path}': {last_exc}")`
- `duckdb.IOException` без lock-маркера → `raise` немедленно (не retried)

### BC-22-2: _run_acceptance_check fail-fast

```
src/sdd/commands/validate_invariants.py
  def _run_acceptance_check(
      outputs: list[str],
      cwd: str,
      env: dict[str, str],
      timeout: int,
      test_returncode: int | None = None,
  ) -> int:
```

Контракт:
1. `test_returncode is None` → emit `{"error": "ACCEPTANCE_FAILED", "reason": "NO_TEST_RESULT"}` → `return 1` (детерминированный fail, не crash; сохраняет I-ERROR-1)
2. Если py-outputs присутствуют: ruff check через `subprocess.run(["ruff", "check", *py_outputs], ...)`
3. `pytest_rc = test_returncode` (reused; subprocess не запускается)
4. Если `test_returncode != 0` → emit error JSON → return 1

Caller (`main()`) извлекает `test_returncode` из `TestRunCompleted` событий build loop. Если `test` отсутствует в build.commands — `test_returncode` будет `None`, acceptance вернёт 1 (не crash).

### BC-22-3: Test-level separation

```
.sdd/config/project_profile.yaml
  build:
    commands:
      test:       pytest tests/unit/ tests/integration/ -q
      test_full:  pytest tests/ -q
```

- `test` — fast validation: unit + integration тесты. Покрывает все детерминированные корректностные инварианты (I-TEST-1).
- `test_full` — deep validation: весь тест-сьют включая property + fuzz. Обязателен перед PhaseComplete (I-TEST-2).
- `acceptance` шаблон обновляется на: `"ruff check {outputs} && pytest tests/unit/ tests/integration/ -q"`.

### Dependencies

```text
BC-22-0 → BC-17 ValidateInvariantsHandler : timeout sentinel используется в subprocess loop
BC-22-1 → BC-8  EventStore/infra           : DuckDBLockTimeoutError raised в open_sdd_connection
BC-22-2 → BC-17 ValidateInvariantsHandler : acceptance reuses TestRunCompleted events
BC-22-3 → BC-17 project_profile.yaml      : команды test/test_full определяют DoD уровни
```

---

## 3. Domain Events

Новых event-типов нет. `TestRunCompleted.returncode` при timeout принимает значение `124` вместо `-1` — семантическое уточнение существующего события в рамках BC-17.

### Event Catalog (no change)

| Event | Emitter | Description |
|-------|---------|-------------|
| `TestRunCompleted` | `ValidateInvariantsHandler` | Результат каждой build команды; returncode=124 при timeout |
| `MetricRecorded` | `ValidateInvariantsHandler` | Метрика качества; value=124.0 при timeout |

---

## 4. Types & Interfaces

```python
# src/sdd/infra/db.py
class DuckDBLockTimeoutError(RuntimeError):
    """Raised when open_sdd_connection cannot acquire DuckDB file lock within timeout_secs."""


# src/sdd/commands/validate_invariants.py
TIMEOUT_RETURN_CODE: int = 124
# GNU timeout(1) convention; semantically interpreted as timeout within ValidationRuntime only.
# Theoretical collision with user exit code 124 is acceptable: value is set only on TimeoutExpired.


def _run_acceptance_check(
    outputs: list[str],
    cwd: str,
    env: dict[str, str],
    timeout: int,
    test_returncode: int | None = None,
) -> int:
    """Run ruff+acceptance check per I-ACCEPT-1.

    Reuses test_returncode from build loop (I-ACCEPT-REUSE-1).
    If test_returncode is None: emits ACCEPTANCE_FAILED/NO_TEST_RESULT, returns 1 (deterministic fail).
    Returns 0 on pass, 1 on fail.
    """
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-TIMEOUT-1 | Subprocess timeout in build loop MUST set returncode = TIMEOUT_RETURN_CODE (124); значение `-1` запрещено | 22 |
| I-CMD-7 | All subprocesses in build loop MUST be started with `start_new_session=True`; это гарантирует killpg на весь process group при timeout | 22 |
| I-LOCK-1 | `open_sdd_connection()` при lock retry exhaustion MUST raise `DuckDBLockTimeoutError`; классификация best-effort (string-based); non-lock IOException пробрасывается немедленно | 22 |
| I-LOCK-2 | `open_sdd_connection()` с `db_path == ":memory:"` MUST skip retry и connect немедленно | 22 |
| I-ACCEPT-REUSE-1 | `_run_acceptance_check` MUST receive `test_returncode` from build loop; fallback subprocess запуск pytest из acceptance запрещён; `None` → deterministic fail (return 1, not raise) | 22 |
| I-TEST-1 | `build.commands.test` MUST cover all deterministic correctness invariants (unit + integration); property/fuzz опциональны | 22 |
| I-TEST-2 | **[Process-level, not enforced by ValidationRuntime]** PhaseComplete requires successful `build.commands.test_full` execution; enforcement — ответственность человека при review | 22 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-CMD-6 | Individual subprocess failure MUST NOT abort the build loop; all commands execute |
| I-CMD-1 | Duplicate command_id → idempotent return [] (no subprocess execution) |
| I-ERROR-1 | Write Kernel MUST emit ErrorEvent before raising at every failure stage |
| I-ACCEPT-1 | Acceptance check enforced per-task when acceptance field present in build.commands |
| I-2 | All write commands execute via REGISTRY[name] → execute_and_project |
| I-3 | All side-effects occur in Write Kernel only |

---

## 6. Pre/Post Conditions

### _run_acceptance_check

**Pre:**
- `outputs` может быть пустым (ruff пропускается)
- `env` — filtered dict (whitelist-only, per I-CMD-13)
- `test_returncode` может быть `None` (если `test` отсутствует в build.commands)

**Post:**
- `test_returncode is None` → emit `ACCEPTANCE_FAILED/NO_TEST_RESULT` → return 1
- Returns `0` iff ruff passes (or skipped) AND `test_returncode == 0`
- Returns `1` iff ruff fails OR `test_returncode != 0`
- No subprocess pytest is ever launched from this function

### open_sdd_connection (refined)

**Pre:**
- `db_path` — filesystem path или `:memory:`
- `timeout_secs > 0`

**Post:**
- `db_path == ":memory:"` → connect немедленно, без retry
- Returns open `DuckDBPyConnection` with schema ensured
- OR raises `DuckDBLockTimeoutError` если lock не получен за `timeout_secs` (best-effort classification)
- OR raises `duckdb.IOException` для non-lock IO ошибок (немедленно, без retry)

### main() acceptance flow

**Pre:**
- `parsed.task` задан и `acceptance` в build.commands
- `events` может содержать `TestRunCompleted` с `name == "test"`; может не содержать

**Post:**
- `test_rc_from_loop` = returncode последнего `TestRunCompleted` с `name == "test"` (или `None`)
- Если несколько `TestRunCompleted.name == "test"` — последнее (по порядку в events) wins
- `_run_acceptance_check(..., test_returncode=test_rc_from_loop)` вызван
- При `test_rc_from_loop is None` → acceptance возвращает 1 (детерминированный fail)

---

## 7. Use Cases

### UC-22-1: validate-invariants с timeout subprocess

**Actor:** LLM (sdd validate-invariants CLI)
**Trigger:** `sdd validate-invariants --phase N --task T-NNN --timeout 120`
**Pre:** build.commands содержит `test`, `timeout_secs = 120`
**Steps:**
1. Handler строит env dict из whitelist
2. Для каждой build команды: запуск через `subprocess.Popen(..., start_new_session=True)`
3. `proc.communicate(timeout=timeout)` — если TimeoutExpired:
   a. `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` — убиваем process group
   b. `proc.communicate(timeout=5)` — drain pipes (с диагностикой при вторичном timeout)
   c. `returncode = TIMEOUT_RETURN_CODE` (124)
   d. continue loop (I-CMD-6)
4. Emit `TestRunCompleted(returncode=124)` + `MetricRecorded(value=124.0)`
5. main() appends events to EventStore
6. main() извлекает `test_rc_from_loop` из TestRunCompleted.name=="test"
7. `_run_acceptance_check(..., test_returncode=test_rc_from_loop)` — reuses result

**Post:** события записаны, acceptance завершён без второго pytest subprocess

### UC-22-2: DuckDB lock contention recovery

**Actor:** open_sdd_connection caller (EventStore, get_error_count)
**Trigger:** другой процесс удерживает DuckDB file lock
**Pre:** `timeout_secs=10.0`, lock занят
**Steps:**
1. `duckdb.connect(db_path)` → `duckdb.IOException` с `"Could not set lock"`
2. Retry loop: sleep(0.25), повтор до deadline
3. При deadline: `raise DuckDBLockTimeoutError(f"DuckDB lock timeout after 10.0s...")`

**Post:** caller получает типизированную ошибку, может обработать lock-timeout отдельно от структурных IO-ошибок

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-17 ValidateInvariantsHandler | this refines | Timeout sentinel, acceptance reuse |
| BC-8 EventStore / infra/db | this refines | DuckDBLockTimeoutError type |
| BC-1 project_profile | this extends | test_full command level |

### Reducer Extensions

Нет. Phase 22 не вводит новых event handlers в reducer.

---

## 9. Verification

| # | Test Name | Invariant(s) |
|---|-----------|--------------|
| 1 | `test_subprocess_timeout_records_124_and_continues` | I-TIMEOUT-1, I-CMD-6 |
| 2 | `test_subprocess_uses_start_new_session` | I-CMD-7 |
| 3 | `test_open_sdd_connection_raises_lock_timeout_error` | I-LOCK-1 |
| 4 | `test_open_sdd_connection_raises_io_error_immediately` | I-LOCK-1 (non-lock IO) |
| 5 | `test_open_sdd_connection_memory_no_retry` | I-LOCK-2 |
| 6 | `test_acceptance_skips_pytest_when_test_passed` | I-ACCEPT-REUSE-1, I-ACCEPT-1 |
| 7 | `test_acceptance_returns_failure_from_test_returncode` | I-ACCEPT-REUSE-1 |
| 8 | `test_acceptance_returns_1_when_no_test_result` | I-ACCEPT-REUSE-1 (no crash) |
| 9 | `test_acceptance_uses_last_test_event_when_multiple` | I-ACCEPT-REUSE-1 (last wins) |
| 10 | `test_validate_inv_idempotent` (updated: mock Popen, not run) | I-CMD-1 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| CI/CD pipeline integration | Phase N+? |
| DuckDB schema migration | Phase 22+ (additive-only) |
| Property/fuzz test authoring | Already done in Phase 17 |
| pytest markers (@slow, @fuzz) | Optional — Phase 23+ |
| `test_full` enforcement gate in sdd CLI | Phase 23+ (requires check-dod extension) |
