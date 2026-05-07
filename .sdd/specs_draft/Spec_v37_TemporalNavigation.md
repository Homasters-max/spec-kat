# Spec_v37 — Phase 37: Temporal Navigation (TN)

Status: Draft
Baseline: Spec_v36_GraphNavigation.md (Phase 36 с unified $SDD_DATABASE_URL + p_sdd схема)
Note: После Phase 32 (PostgresMigration) следует Phase 33 (GraphNavigation upgrade). Phase 37 выполняется после Phase 36, но до или после Phase 31/32 — по усмотрению. Для post-Phase-32 версии Temporal Navigation будет отдельный спек (Phase 34+).

---

## 0. Goal

Phase 36 дала агенту граф связей — он умеет перемещаться по структуре системы.
Но граф статичен: агент не знает **что изменилось** и **почему это изменилось**.

Phase 37 вводит **Temporal Navigation** — объединение пространства (граф) и времени (git + EventLog):

```
System := ⟨Kernel, ValidationRuntime, SpatialIndex, GraphNavigation, TemporalNavigation⟩
TN отвечает на вопрос: "что изменилось с момента X и почему?"
```

Ключевое архитектурное решение (не менялось с исходного плана):

```
Git     = truth of WHAT changed   (структурная истина)
EventLog = truth of WHY it changed (семантическая истина)
```

Эти два источника НЕ смешиваются как истина для одного факта.

Улучшения по итогам анализа:

1. **TaskCheckpoint event** — реалистичная модель "несколько коммитов на задачу".
   `I-GIT-TASK-1` не ломается: `TaskImplemented.commit_sha` = final boundary.
   `TaskCheckpoint.commit_sha` = intermediate (для debug).

2. **ContentAddressableStore abstraction** — git wrapped в интерфейс.
   Сейчас = git. Потом можно заменить без изменения агентского API.

3. **NORM-NAV-001** — enforcement инварианта I-CONTEXT-1 как machine-readable норма.

---

## 1. Scope

### In-Scope

- **BC-37-0: TaskCheckpoint event** — новый domain event (events.py)
- **BC-37-1: ContentAddressableStore + git_bridge** — абстракция над git (git_bridge.py)
- **BC-37-2: changed_since** — детерминированный temporal query (changed_since.py)
- **BC-37-3: update_state changes** — `sdd complete` создаёт git commit; I-HANDLER-PURE-1 сохранён
- **BC-37-4: validate_invariants extension** — проверка I-TEMP-1
- **BC-37-5: CLI commands** — `sdd nav-changed-since`, `sdd nav-task-commits`
- **BC-37-6: NORM-NAV-001** — в `.sdd/norms/norm_catalog.yaml`
- **BC-37-7: Tests** — unit + integration

### Out of Scope

- ML-анализ git history — никогда
- `blame`-анализ на уровне строк — никогда
- Удаление существующих тестов Phase 17-19 — запрещено (CEP-3)

---

## 2. TaskCheckpoint — Реалистичная Модель

### Проблема с "1 task = 1 commit"

Исходный план подразумевает: `sdd complete T-NNN` → ровно 1 коммит.
На практике задача требует нескольких коммитов (fix, refactor, WIP).

Если жёстко требовать 1 коммит на задачу — нарушается I-GIT-TASK-1 в большинстве реальных workflow.

### Решение: TaskCheckpoint

```
TaskImplemented:
  commit_sha: <final commit>     ← boundary для nav-changed-since

TaskCheckpoint:
  commit_sha: <intermediate>    ← для debug, bisect
```

`sdd complete T-NNN` всегда создаёт финальный коммит и эмитирует `TaskImplementedEvent`
с `commit_sha = HEAD` после коммита.

`sdd checkpoint T-NNN` (новая команда) создаёт промежуточный коммит и эмитирует
`TaskCheckpointEvent` (не меняет статус задачи).

**nav-changed-since** использует `TaskImplemented.commit_sha` (финальная граница).
**debug** может использовать `TaskCheckpoint.commit_sha` для bisect.

I-GIT-TASK-1 остаётся валидным: каждый `TaskImplemented` MUST иметь `commit_sha`.
I-GIT-TASK-1 проверяется `validate-invariants --check I-TEMP-1`.

---

## 3. ContentAddressableStore — Абстракция над Git

### Зачем абстракция

Сейчас git — единственный CAS. В будущем: cloud storage, другой VCS.
Абстракция позволяет заменить без изменения `changed_since.py` и CLI-команд.

```python
class ContentAddressableStore(Protocol):
    def get_hash(self, path: str) -> str | None:
        """Current content hash for path. None if untracked/not exists."""

    def get_changed_files(self, since_sha: str) -> list[str]:
        """Files changed since commit sha. Raises CommitUnresolvableError if sha invalid."""

    def get_current_sha(self) -> str | None:
        """Current HEAD SHA. None if no commits."""
```

`GitContentStore` — реализация через subprocess (не shell=True):

```python
class GitContentStore:
    def get_hash(self, path: str) -> str | None:
        # git ls-files -s <path> → blob SHA (O(1))
        # fallback: git hash-object <path>

    def get_changed_files(self, since_sha: str) -> list[str]:
        # git diff --name-only <since_sha> HEAD
        # Raises CommitUnresolvableError if SHA не найден

    def get_current_sha(self) -> str | None:
        # git rev-parse HEAD
```

---

## 4. Architecture / BCs

### BC-37-0: TaskCheckpoint Event

**`src/sdd/core/events.py`** — добавить:

```python
@dataclass(frozen=True)
class TaskCheckpointEvent(DomainEvent):
    """Intermediate commit during task implementation. Does not change task status."""
    task_id:    str
    commit_sha: str        # intermediate SHA; MUST be non-null (checkpoint = commit exists)
    message:    str        # checkpoint description (~40 chars)
    phase_id:   int

    @classmethod
    def event_type(cls) -> str:
        return "TaskCheckpoint"
```

**Reducer** — `TaskCheckpointEvent` не меняет `SDDState.tasks_completed` и не добавляет
в `tasks_done_ids`. Reducer записывает в `state.last_checkpoint_sha` (новое поле):

```python
# В SDDState:
last_checkpoint_sha: str | None = None  # последний TaskCheckpoint.commit_sha

# В reducer:
case TaskCheckpointEvent():
    return replace(state, last_checkpoint_sha=event.commit_sha)
```

**I-HANDLER-PURE-1 сохранён:** `TaskCheckpointHandler.handle()` получает `commit_sha`
как аргумент из CLI-слоя. Subprocess-вызов только в `checkpoint.main()`.

### BC-37-1: ContentAddressableStore + git_bridge

```
src/sdd/spatial/temporal/
  __init__.py
  git_bridge.py        # GitContentStore + git_add_all_and_commit()
```

```python
# src/sdd/spatial/temporal/git_bridge.py

class CommitUnresolvableError(SDDError):
    """Raised when commit SHA cannot be resolved in repository."""

class GitContentStore:
    def __init__(self, cwd: str): ...
    def get_hash(self, path: str) -> str | None: ...
    def get_changed_files(self, since_sha: str) -> list[str]: ...
    def get_current_sha(self) -> str | None: ...


def git_add_all_and_commit(task_id: str, cwd: str) -> str | None:
    """
    1. subprocess.run(["git", "add", "-A"], ...)      # НЕ shell=True
    2. subprocess.run(["git", "commit", "-m", task_id], ...)
    3. subprocess.run(["git", "rev-parse", "HEAD"], ...) → sha
    Returns sha on success, None on clean tree (nothing to commit) or error.
    Graceful degradation: не падает при ошибках git.
    """


def git_add_checkpoint_commit(task_id: str, message: str, cwd: str) -> str | None:
    """
    Аналог git_add_all_and_commit, но для промежуточных коммитов.
    Commit message: f"[checkpoint] {task_id}: {message}"
    Returns sha on success, None if clean tree or error.
    """
```

### BC-37-2: changed_since

```
src/sdd/spatial/temporal/
  changed_since.py     # changed_since() → детерминированный JSON
```

```python
def changed_since(
    commit_sha: str,
    store: ContentAddressableStore,
    index: SpatialIndex,
    mode: str = "POINTER",
    kind_filter: str | None = None,
) -> dict:
    """
    I-TEMP-2: identical node set for same sha and same index mtime.
    I-TEMP-3: MUST include "deterministic": true; on unresolvable sha →
              {"status": "error", "reason": "COMMIT_SHA_UNRESOLVABLE"}
    """
    # 1. store.get_changed_files(commit_sha) → list[str] (paths)
    # 2. map paths → node_ids из SpatialIndex (I-SI-3: только индекс, no open())
    # 3. фильтр по kind_filter
    # 4. вернуть sorted список (детерминизм)
```

### BC-37-3: update_state.py Changes

**Критическое изменение — сохраняет I-HANDLER-PURE-1:**

```python
# В src/sdd/commands/update_state.py
# ПЕРЕД execute_and_project():

def main(args: list[str]) -> int:
    # ... parse args ...

    # CLI-слой делает subprocess (НЕ handler)
    commit_sha = git_add_all_and_commit(task_id=task_id, cwd=project_root)

    # commit_sha передаётся в command payload
    cmd = CompleteTaskCommand(
        task_id=task_id,
        phase_id=phase_id,
        commit_sha=commit_sha,      # I-GIT-TASK-1: None = graceful degradation
    )
    # execute_and_project(spec, cmd, db_path) → handler получает commit_sha
```

**`CompleteTaskCommand`** расширяется:
```python
@dataclass(frozen=True)
class CompleteTaskCommand:
    task_id:    str
    phase_id:   int
    commit_sha: str | None = None   # I-GIT-TASK-1; None = graceful degradation
```

**`CompleteTaskHandler.handle()`** — не делает subprocess. Получает `commit_sha` из `cmd`.
I-HANDLER-PURE-1 не нарушается.

**Новая команда `sdd checkpoint T-NNN --message "..."` (checkpoint.py):**
```python
def main(args: list[str]) -> int:
    commit_sha = git_add_checkpoint_commit(task_id, message, cwd=project_root)
    if commit_sha is None:
        print(json.dumps({"status": "skipped", "reason": "clean tree"}))
        return 0
    cmd = CheckpointTaskCommand(task_id=task_id, commit_sha=commit_sha, message=message, ...)
    # execute_and_project → TaskCheckpointHandler → TaskCheckpointEvent
```

### BC-37-4: validate_invariants Extension

**`src/sdd/commands/validate_invariants.py`** — добавить `_check_i_temp_1()`:

```python
def _check_i_temp_1(db_path: str, phase_id: int) -> InvariantCheckResult:
    """
    Query EventLog: TaskImplemented events в phase_id
    FAIL если payload.commit_sha is null или отсутствует
    Backward compat: фильтровать только фазы ≥ 20 (activation фазы TN)
    """
```

Вызов: `sdd validate-invariants --check I-TEMP-1 --phase N`

### BC-37-5: CLI Commands

```
src/sdd/spatial/commands/
  nav_changed_since.py   # sdd nav-changed-since <sha> [--mode POINTER|SUMMARY] [--kind KIND]
  nav_task_commits.py    # sdd nav-task-commits [--phase N] [--task T-NNN]

src/sdd/commands/
  checkpoint.py          # sdd checkpoint T-NNN --message "..."
```

**nav-changed-since output:**
```json
// sdd nav-changed-since abc1234  (exit 0)
{
  "deterministic": true,
  "commit_sha": "abc1234...",
  "head_sha": "fed987...",
  "changed_nodes": [
    {"node_id": "FILE:src/sdd/cli.py", "kind": "FILE", "path": "src/sdd/cli.py"}
  ],
  "unchanged_count": 124
}

// unresolvable SHA  (exit 1)
{"status": "error", "reason": "COMMIT_SHA_UNRESOLVABLE", "commit_sha": "badsha"}
```

**nav-task-commits output:**
```json
// sdd nav-task-commits --phase 20  (exit 0)
[
  {"task_id": "T-2001", "commit_sha": "abc123...", "timestamp": "2026-...",
   "nodes_changed": [{"node_id": "FILE:src/sdd/spatial/temporal/__init__.py"}],
   "checkpoints": [
     {"commit_sha": "def456...", "message": "add git_bridge skeleton"}
   ]},
  {"task_id": "T-2002", "commit_sha": null,
   "warning": "I-GIT-TASK-1: commit_sha missing"}
]
```

**checkpoint output:**
```json
// sdd checkpoint T-2001 --message "add git_bridge skeleton"  (exit 0)
{"status": "ok", "task_id": "T-2001", "commit_sha": "def456...", "message": "add git_bridge skeleton"}

// clean tree (exit 0, не ошибка)
{"status": "skipped", "reason": "clean tree"}
```

### BC-37-6: NORM-NAV-001

**`.sdd/norms/norm_catalog.yaml`** — добавить:

```yaml
- norm_id: NORM-NAV-001
  description: >
    LLM MUST NOT access filesystem directly if equivalent info exists in Spatial Index.
    Agent MUST call sdd nav-get (exit 0 = index hit) before opening any file.
  actor: llm
  sdd_invariant_refs: [I-CONTEXT-1, I-NAV-2]
  enforcement: hard
  check_mechanism: >
    sdd nav-get <node_id> exit 0 → file content available via --mode FULL.
    Direct filesystem access after index hit = NORM-NAV-001 violation.
  phase_introduced: 20
```

### BC-37-7: Tests

```
tests/unit/spatial/temporal/
  test_git_bridge.py           # mock subprocess; SHA success/None; clean tree graceful
  test_changed_since.py        # I-TEMP-2 детерминизм; I-TEMP-3 envelope; CommitUnresolvableError

tests/unit/commands/
  test_nav_changed_since.py    # exit 1 на unresolvable sha; deterministic:true в exit 0
  test_nav_task_commits.py     # null commit_sha warning; checkpoints в output
  test_checkpoint.py           # TaskCheckpointEvent эмитируется; clean tree → skipped

tests/integration/
  test_i_temp_1.py             # validate-invariants --check I-TEMP-1 PASS/FAIL
  test_temporal_full.py        # sdd complete → commit exists → nav-changed-since
```

---

## 5. Domain Events

### New Events (Phase 37)

**TaskCheckpointEvent** — добавляется в `src/sdd/core/events.py`:

```python
@dataclass(frozen=True)
class TaskCheckpointEvent(DomainEvent):
    task_id:    str
    commit_sha: str        # MUST be non-null (checkpoint без коммита бессмысленен)
    message:    str
    phase_id:   int
    level:      str = "L1"
    event_type: str = "TaskCheckpoint"
```

### CompleteTaskCommand Extension

`CompleteTaskCommand.commit_sha: str | None` — добавляется поле.
Это изменение Command, не Event — обратно совместимо.

### Backward Compatibility

Исторические `TaskImplemented` события (до Phase 37) имеют `commit_sha = null`.
I-TEMP-1 применяется только к событиям фаз ≥ 20 (`phase_id >= 20`).
`_check_i_temp_1()` фильтрует по `phase_id` — backward compat гарантирован.

---

## 6. Invariants

### New Invariants — Temporal Navigation Layer

| ID | Statement | Phase | Verification |
|----|-----------|-------|-------------|
| I-GIT-TASK-1 | Every `TaskImplemented` event (phase ≥ 20) MUST have non-null `commit_sha` | 20 | `validate-invariants --check I-TEMP-1`, `test_i_temp_1.py` |
| I-GIT-CHECKPOINT-1 | Every `TaskCheckpoint` event MUST have non-null `commit_sha` | 20 | `test_checkpoint.py` |
| I-TEMP-2 | `changed_since(sha_A)` → identical node set for same sha_A and same index mtime | 20 | `test_changed_since.py` |
| I-TEMP-3 | Every temporal query response MUST include `"deterministic": true`; unresolvable sha → `{"status": "error", "reason": "COMMIT_SHA_UNRESOLVABLE"}` | 20 | `test_changed_since.py`, `test_nav_changed_since.py` |
| I-CAS-1 | `GitContentStore` MUST use subprocess list args (not `shell=True`) for injection prevention | 20 | `test_git_bridge.py` (check call args) |
| I-CAS-2 | `git_add_all_and_commit` MUST return None on clean tree (not raise); graceful degradation | 20 | `test_git_bridge.py` |

### Updated Invariants

| ID | Update | Phase |
|----|--------|-------|
| I-HANDLER-PURE-1 | **Confirmed extended:** `CompleteTaskHandler.handle()` и `CheckpointTaskHandler.handle()` — subprocess запрещён; `commit_sha` передаётся из CLI-слоя | 20 |

### Preserved Invariants (Phase 17-19)

I-NAV-1..3, I-CONTEXT-1, I-SI-1..4, I-DDD-0..2, I-GRAPH-1..3, I-GRAPH-PRIORITY-1 — без изменений.

---

## 7. Pre/Post Conditions

### M0 — TaskCheckpoint Event + Reducer

**Pre:** Phase 36 COMPLETE

**Post:**
- `TaskCheckpointEvent` добавлен в `events.py`
- Reducer обрабатывает `TaskCheckpointEvent` → `last_checkpoint_sha`
- `SDDState.last_checkpoint_sha: str | None` добавлено
- Существующие тесты Phase 17 (P-1..P-10) по-прежнему проходят (backward compat)

### M1 — ContentAddressableStore + git_bridge

**Pre:** M0 COMPLETE

**Post:**
- `src/sdd/spatial/temporal/{__init__,git_bridge}.py` созданы
- `GitContentStore` реализует Protocol (duck typing)
- `git_add_all_and_commit()` и `git_add_checkpoint_commit()` работают
- I-CAS-1 (shell=False), I-CAS-2 (clean tree → None) верифицированы
- `tests/unit/spatial/temporal/test_git_bridge.py` PASS (все subprocess в mock)

### M2 — changed_since

**Pre:** M1 COMPLETE, Phase 18 M4 COMPLETE (Navigator + SpatialIndex)

**Post:**
- `changed_since.py` создан
- I-TEMP-2: два вызова с одним sha → байт-идентичный вывод
- I-TEMP-3: `deterministic: true` присутствует; CommitUnresolvableError → error envelope
- `tests/unit/spatial/temporal/test_changed_since.py` PASS

### M3 — update_state Changes + checkpoint Command

**Pre:** M1 COMPLETE

**Post:**
- `CompleteTaskCommand.commit_sha` добавлено (Optional)
- `update_state.main()`: git commit перед `execute_and_project()`
- `checkpoint.py` создан
- I-HANDLER-PURE-1 сохранён: handler не делает subprocess
- `tests/unit/commands/test_checkpoint.py` PASS

### M4 — validate_invariants Extension

**Pre:** M0, M3 COMPLETE

**Post:**
- `_check_i_temp_1()` добавлен в `validate_invariants.py`
- Фильтрация по `phase_id >= 20` (backward compat)
- `tests/integration/test_i_temp_1.py` PASS/FAIL сценарии

### M5 — CLI Commands

**Pre:** M2, M3 COMPLETE

**Post:**
- `nav_changed_since.py`, `nav_task_commits.py` созданы
- `cli.py` зарегистрированы: `nav-changed-since`, `nav-task-commits`, `checkpoint`
- Unit-тесты PASS

### M6 — NORM-NAV-001

**Pre:** Phase 37 ACTIVE

**Post:**
- `NORM-NAV-001` добавлен в `norm_catalog.yaml`
- `sdd check-scope` (если существует norm-check) распознаёт NORM-NAV-001

### M7 — Integration

**Pre:** M0..M6 COMPLETE

**Post:**
- `sdd complete T-NNN` → `TaskImplementedEvent.commit_sha` не null
- `sdd validate-invariants --check I-TEMP-1 --phase 20` exit 0 (PASS)
- `sdd nav-changed-since <sha>` exit 0; `"deterministic": true`
- `sdd nav-task-commits --phase 20` — нет null `commit_sha`
- Два вызова `nav-changed-since <sha>` с тем же индексом → байт-идентичный вывод (I-TEMP-2)
- Все тесты Phase 17, 18, 19 по-прежнему проходят
- `tests/integration/test_temporal_full.py` PASS

---

## 8. Use Cases

### UC-20-1: Agent Checks What Changed Since Task T-2001

**Actor:** LLM-агент в VALIDATE-сессии
**Trigger:** нужно понять что изменилось за время выполнения T-2001
**Pre:** Phase 37 ACTIVE, T-2001 COMPLETE (TaskImplemented с commit_sha)
**Steps:**
1. `sdd nav-task-commits --task T-2001` → `{"commit_sha": "abc123", "nodes_changed": [...]}`
2. `sdd nav-changed-since abc123` → список изменённых узлов (POINTER)
3. Для нужных узлов: `sdd nav-get FILE:src/... --mode SIGNATURE`
**Post:** агент знает точно, какие файлы изменила задача; I-CONTEXT-1 соблюдён

### UC-20-2: Complete with Auto-Commit

**Actor:** LLM-агент
**Trigger:** `sdd complete T-2003`
**Pre:** Phase 37 ACTIVE, есть незакоммиченные изменения
**Steps:**
1. `update_state.main()` вызывает `git_add_all_and_commit("T-2003", cwd)`
2. Получает `commit_sha = "fed321..."`
3. `execute_and_project()` с `CompleteTaskCommand(commit_sha="fed321...")`
4. `TaskImplementedEvent` записывается с `commit_sha != null`
5. I-GIT-TASK-1 выполнен
**Post:** каждая завершённая задача Phase 37+ имеет git boundary

### UC-20-3: Checkpoint During Long Task

**Actor:** LLM-агент
**Trigger:** `sdd checkpoint T-2004 --message "add git_bridge skeleton"`
**Pre:** Phase 37 ACTIVE, T-2004 ACTIVE, есть изменения
**Steps:**
1. `checkpoint.main()` → `git_add_checkpoint_commit(...)` → `commit_sha = "def456"`
2. `TaskCheckpointEvent(task_id="T-2004", commit_sha="def456", ...)` эмитируется
3. Задача остаётся ACTIVE (статус не меняется)
4. Позже: `sdd nav-task-commits --task T-2004` показывает checkpoint в истории
**Post:** промежуточные коммиты трассируемы; `nav-changed-since` использует только final SHA

### UC-20-4: Clean Tree Graceful

**Actor:** LLM-агент
**Trigger:** `sdd complete T-2005` когда все изменения уже закоммичены
**Pre:** `git status` чистый
**Steps:**
1. `git_add_all_and_commit()` → `None` (clean tree)
2. `CompleteTaskCommand(commit_sha=None)` — graceful degradation
3. `TaskImplementedEvent(commit_sha=None)` записывается
4. `validate-invariants --check I-TEMP-1` выдаёт WARN (не FAIL) — backward compat
**Post:** система не падает при чистом дереве; I-GIT-TASK-1 — hard enforcement только при явном нарушении

### UC-20-5: Determinism Verification

**Actor:** Developer / CI
**Trigger:** `sdd nav-changed-since <sha>` дважды
**Pre:** Phase 37 ACTIVE, индекс не изменился
**Steps:**
1. Первый вызов → JSON output
2. Второй вызов → байт-идентичный JSON output
3. I-TEMP-2 PASS
**Post:** temporal queries воспроизводимы; агент может кешировать результаты

---

## 9. Verification

### Phase 37 Complete iff

```bash
# Все предыдущие тесты
pytest tests/ -q  # Phase 17, 18, 19 по-прежнему PASS

# Phase 37 unit
pytest tests/unit/spatial/temporal/ tests/unit/commands/test_nav_changed*.py \
       tests/unit/commands/test_checkpoint.py -q

# I-TEMP-1: commit_sha в TaskImplemented (Phase 37 задачи)
sdd validate-invariants --check I-TEMP-1 --phase 20    # exit 0 PASS

# I-TEMP-2: детерминизм
SHA=$(sdd nav-task-commits --phase 20 | python3 -c "
import sys, json; data = json.load(sys.stdin)
print(data[0]['commit_sha'])
")
OUT1=$(sdd nav-changed-since "$SHA")
OUT2=$(sdd nav-changed-since "$SHA")
[ "$OUT1" = "$OUT2" ] && echo "I-TEMP-2 PASS" || echo "I-TEMP-2 FAIL"

# I-TEMP-3: deterministic envelope
sdd nav-changed-since deadbeef  # exit 1, COMMIT_SHA_UNRESOLVABLE

# Integration
pytest tests/integration/test_i_temp_1.py tests/integration/test_temporal_full.py -q
```

### Test Suite

| # | File | Invariants |
|---|------|------------|
| 1 | `tests/unit/spatial/temporal/test_git_bridge.py` | I-CAS-1, I-CAS-2 |
| 2 | `tests/unit/spatial/temporal/test_changed_since.py` | I-TEMP-2, I-TEMP-3 |
| 3 | `tests/unit/commands/test_nav_changed_since.py` | I-TEMP-3 exit 1 |
| 4 | `tests/unit/commands/test_nav_task_commits.py` | null warning, checkpoints |
| 5 | `tests/unit/commands/test_checkpoint.py` | TaskCheckpointEvent; clean tree skipped |
| 6 | `tests/integration/test_i_temp_1.py` | I-GIT-TASK-1 PASS/FAIL scenarios |
| 7 | `tests/integration/test_temporal_full.py` | полный workflow: complete→commit→changed-since |

### Stabilization Criteria

1. `sdd complete T-NNN` → `TaskImplementedEvent` payload содержит `commit_sha` (не null)
2. `sdd validate-invariants --check I-TEMP-1 --phase 20` exit 0 PASS
3. `sdd nav-changed-since <sha>` exit 0; `"deterministic": true` в ответе
4. `sdd nav-task-commits --phase 20` — нет null `commit_sha` для Phase 37 задач
5. Два вызова `nav-changed-since <sha>` с тем же индексом → байт-идентичный вывод
6. `sdd nav-changed-since deadbeef` exit 1, `COMMIT_SHA_UNRESOLVABLE`
7. `sdd checkpoint T-NNN --message "..."` → `TaskCheckpointEvent` в EventLog
8. `sdd nav-task-commits` показывает checkpoint в `checkpoints: [...]`
9. Все тесты Phase 17, 18, 19 по-прежнему проходят (CEP-3)

---

## 10. Out of Scope

| Item | Owner |
|------|-------|
| ML-анализ git history | никогда |
| `git blame` на уровне строк | никогда |
| Distributed concurrency testing | Phase 17 (из Scope Phase 17 Out of Scope) |
| Production observability (alerts) | внешняя инфраструктура |
| Fuzzing via AFL/libfuzzer | внешняя инфраструктура |
| Изменения в `.sdd/specs/**` | иммутабельно (SDD-9) |

---

## Appendix A: Architecture Summary (Phase 18-20)

```
           ┌──────────────────┐
           │  Glossary (TERM) │  ← DDD entrypoint (sdd resolve)
           └────────┬─────────┘
                    ↓ means edges
           ┌──────────────────┐
           │  Spatial Index   │  ← структура (Phase 18)
           │  + Graph (edges) │  ← связи + priority (Phase 36)
           └────────┬─────────┘
                    ↓
       ┌────────────┴────────────┐
       ↓                         ↓
 Git (WHAT changed)        EventLog (WHY it changed)
 GitContentStore           TaskImplementedEvent.commit_sha
 nav-changed-since         TaskCheckpointEvent.commit_sha
                           (Phase 37)
```

**Cognitive stack агента (полный):**

| Question | Tool | Phase |
|----------|------|-------|
| WHERE (что существует?) | `sdd nav-get` | 18 |
| WHAT (как называется?) | `sdd resolve` + TERM | 18 |
| HOW (как связано?) | `sdd nav-neighbors` + priority | 19 |
| WHEN (что изменилось?) | `sdd nav-changed-since` | 20 |
| WHY (почему изменилось?) | `sdd nav-task-commits` + EventLog | 20 |

## Appendix B: Navigation Protocol (полный, Phase 18-20)

```
STEP 1  Resolve concept      sdd resolve <query>          → TERM или SUMMARY
STEP 2  Expand neighbors     sdd nav-neighbors <id>       → sorted by priority
STEP 3  Select targets       decide which nodes need detail
STEP 4  Load SIGNATURE       sdd nav-get <id> --mode SIGNATURE
STEP 5  FULL (if coding)     sdd nav-get <id> --mode FULL  (max 1 per step)
STEP 6  Temporal (if needed) sdd nav-changed-since <sha>  → что изменилось
```

Инварианты I-NAV-1..3 (Phase 18) управляют шагами 1-5.
Инварианты I-TEMP-2..3 (Phase 37) управляют шагом 6.
