# Spec_v33 — Phase 33: CommandSpec Guard Factory

Status: Draft
Baseline: Spec_v29_StreamlinedWorkflow.md · registry.py (BC-15-REGISTRY, Spec_v15)

---

## 0. Goal

Устранить coupling между Write Kernel (`execute_command`) и логикой сборки guard-пайплайна. Сейчас kernel содержит условную логику на флагах `spec` (`requires_active_phase`, `apply_task_guard`, `spec.name == "switch-phase"`). После этой фазы kernel делает одно: `guards = spec.build_guards(cmd)` — слепо. Знание о том, какие guards нужны конкретной команде, живёт в `CommandSpec` или в файле команды.

---

## 1. Scope

### In-Scope

- BC-33: CommandSpec Guard Factory — метод `CommandSpec.build_guards(cmd)` + поле `guard_factory`
- BC-33-REGISTRY: `execute_command` теряет условную логику guard-сборки; вызывает `spec.build_guards(cmd)`
- BC-33-SWITCH: `switch_phase.py` объявляет собственный `guard_factory`; `if spec.name == "switch-phase"` удаляется из registry.py

### Out of Scope

- Изменение контракта `Guard = Callable[[GuardContext], tuple[GuardResult, list[DomainEvent]]]` (без изменений)
- Изменение `GuardContext`, `run_guard_pipeline`, domain/guards/* (без изменений)
- Изменение остальных handlers или CommandSpec-полей, кроме добавления `guard_factory`
- Перемещение `_extract_task_id` из registry.py (остаётся private helper до появления второго вызывающего)

---

## 2. Architecture / BCs

### BC-33: CommandSpec Guard Factory

```
src/sdd/commands/
  registry.py       # CommandSpec.build_guards() + guard_factory field
                    # _default_build_guards() заменяет _build_spec_guards()
                    # execute_command: guards = spec.build_guards(cmd)
  switch_phase.py   # _switch_phase_guards(cmd) → list[Guard]
                    # CommandSpec(switch-phase, guard_factory=_switch_phase_guards)
```

### Структура `CommandSpec` после изменения

```python
@dataclass(frozen=True)
class CommandSpec:
    # ... все существующие поля без изменений ...
    guard_factory: Callable[[Any], list[Guard]] | None = None

    def build_guards(self, cmd: Any) -> list[Guard]:
        if self.guard_factory is not None:
            return self.guard_factory(cmd)
        return _default_build_guards(self, cmd)
```

`guard_factory: None` → поведение не отличается от текущего для 8 из 9 команд в REGISTRY.
`guard_factory: Callable` → явный сигнал нестандартной guard-стратегии при чтении `CommandSpec`.

### Dependencies

```text
BC-33 → BC-15-REGISTRY : execute_command protocol (unchanged structure, changed call site)
BC-33 → Spec_v5 domain/guards/ : Guard type contract (unchanged)
```

---

## 3. Domain Events

Новых событий не вводится. Все существующие события guard-пайплайна (`NormViolatedEvent`, `SDDEventRejectedEvent`, `ErrorOccurred`) остаются без изменений.

---

## 4. Types & Interfaces

### Guard type (без изменений, Spec_v5)

```python
Guard = Callable[[GuardContext], tuple[GuardResult, list[DomainEvent]]]
```

### Новое поле и метод CommandSpec

```python
@dataclass(frozen=True)
class CommandSpec:
    # existing fields (unchanged):
    name:                  str
    handler_class:         type[CommandHandlerBase]
    actor:                 Literal["llm", "human", "any"]
    action:                str
    projection:            ProjectionType
    uses_task_id:          bool
    event_schema:          tuple[type[DomainEvent], ...]
    preconditions:         tuple[str, ...]
    postconditions:        tuple[str, ...]
    requires_active_phase: bool = True
    apply_task_guard:      bool = True
    description:           str = ""
    idempotent:            bool = True
    # new field:
    guard_factory: Callable[[Any], list[Guard]] | None = None

    def build_guards(self, cmd: Any) -> list[Guard]:
        """Return guard list for this command.

        Delegates to guard_factory(cmd) if set; otherwise uses default strategy
        derived from spec flags (I-CMD-GUARD-FACTORY-2).
        """
        if self.guard_factory is not None:
            return self.guard_factory(cmd)
        return _default_build_guards(self, cmd)
```

### Замена `_build_spec_guards` → `_default_build_guards`

```python
def _default_build_guards(spec: CommandSpec, cmd: Any) -> list[Guard]:
    """Standard guard assembly from spec flags. Private to registry.py (I-CMD-GUARD-FACTORY-3)."""
    task_id = _extract_task_id(cmd)
    guards: list[Guard] = []
    if spec.requires_active_phase:
        guards.append(make_phase_guard(spec.name, task_id))
    if task_id is not None and spec.uses_task_id:
        if spec.apply_task_guard:
            guards.append(make_task_guard(task_id))
        guards.append(partial(DependencyGuard.check, task_id=task_id))
    guards.append(make_norm_guard(spec.actor, spec.action, task_id))
    return guards
```

### `execute_command` — удаляемый блок

Удаляется (строки 377–394 текущего registry.py):
```python
# УДАЛИТЬ: _build_spec_guards и вызов в execute_command
def _build_spec_guards(spec, task_id, cmd=None): ...
guards = _build_spec_guards(spec, task_id, cmd=cmd)
```

Заменяется на (строка в execute_command после вычисления task_id):
```python
guards = spec.build_guards(cmd)
```

### `switch_phase.py` — новый guard factory

```python
def _switch_phase_guards(cmd: Any) -> list[Guard]:
    """Custom guard factory for switch-phase (I-CMD-GUARD-FACTORY-1)."""
    from sdd.domain.guards.phase_guard import make_phase_guard
    from sdd.domain.guards.norm_guard import make_norm_guard
    from sdd.commands.switch_phase import make_switch_phase_guard
    phase_id = getattr(cmd, "phase_id", 0)
    return [
        make_phase_guard("switch-phase", None),
        make_switch_phase_guard(phase_id),
        make_norm_guard("human", "switch_phase", None),
    ]

CommandSpec(
    name="switch-phase",
    ...
    guard_factory=_switch_phase_guards,  # явный сигнал нестандартной стратегии
)
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-CMD-GUARD-FACTORY-1 | `execute_command` MUST obtain the guard list exclusively via `spec.build_guards(cmd)`. Kernel MUST NOT contain conditional branching on `spec.requires_active_phase`, `spec.apply_task_guard`, or `spec.name` for guard assembly. | 33 |
| I-CMD-GUARD-FACTORY-2 | `CommandSpec.build_guards(cmd)` MUST delegate to `self.guard_factory(cmd)` when `guard_factory is not None`; MUST delegate to `_default_build_guards(self, cmd)` otherwise. No other delegation paths. | 33 |
| I-CMD-GUARD-FACTORY-3 | `_default_build_guards` is the sole function in `registry.py` permitted to read `spec.requires_active_phase` and `spec.apply_task_guard` for guard assembly. All other code MUST use `spec.build_guards(cmd)`. | 33 |
| I-CMD-GUARD-FACTORY-4 | Any `CommandSpec` with `guard_factory is not None` MUST assemble ALL guards it needs (including norm guard and phase guard if applicable) inside that factory. The factory's return value is the complete guard list — `_default_build_guards` is NOT additionally called. | 33 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-SPEC-EXEC-1 | CLI contains only: REGISTRY lookup + execute_and_project; no direct kernel calls outside registry.py |
| I-HANDLER-PURE-1 | `handle()` methods return events only — no EventStore, no rebuild_state, no sync_projections |
| I-CMD-IDEM-1 | Navigation commands MUST NOT be idempotent; `CommandSpec.idempotent=False` → uuid4() command_id |

---

## 6. Pre/Post Conditions

### `CommandSpec.build_guards(cmd)`

**Pre:**
- `cmd` is a valid command object (has `payload` dict or `task_id` attribute, depending on spec)
- `self.guard_factory` is either `None` or a `Callable[[Any], list[Guard]]`

**Post:**
- Returns `list[Guard]` where each element satisfies `Guard = Callable[[GuardContext], tuple[GuardResult, list[DomainEvent]]]`
- If `guard_factory is not None`: result equals `guard_factory(cmd)` — `_default_build_guards` NOT called
- If `guard_factory is None`: result equals `_default_build_guards(self, cmd)`

### `execute_command` (guard assembly step)

**Pre (unchanged):**
- GuardContext fully built (step 1 complete)
- `spec.build_guards` exists and satisfies I-CMD-GUARD-FACTORY-2

**Post:**
- `guards` is a `list[Guard]` obtained exclusively from `spec.build_guards(cmd)`
- No kernel-level inspection of `spec.requires_active_phase` or `spec.apply_task_guard` occurs during guard assembly

---

## 7. Use Cases

### UC-33-1: Добавление новой команды с нестандартным guard

**Actor:** разработчик SDD CLI
**Trigger:** новая команда требует guards, параметризованных нестандартным полем payload
**Pre:** `CommandSpec` определён в соответствующем `commands/mycommand.py`
**Steps:**
1. Определить `_my_command_guards(cmd: Any) -> list[Guard]` в `mycommand.py`; извлечь нужные поля из `cmd` внутри фабрики
2. Передать `guard_factory=_my_command_guards` в `CommandSpec`
3. Зарегистрировать в `REGISTRY`
**Post:** `execute_command` вызывает `spec.build_guards(cmd)` → `_my_command_guards(cmd)` без изменений в registry.py

### UC-33-2: Добавление новой команды со стандартным guard

**Actor:** разработчик SDD CLI
**Trigger:** новая команда использует стандартный набор guards (phase + task + norm)
**Pre:** нужные флаги (`requires_active_phase`, `uses_task_id`, `apply_task_guard`) определены
**Steps:**
1. Определить `CommandSpec` без `guard_factory` (defaults to `None`)
2. Зарегистрировать в `REGISTRY`
**Post:** `execute_command` вызывает `spec.build_guards(cmd)` → `_default_build_guards(spec, cmd)` — без изменений в `_default_build_guards`

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-15-REGISTRY | this extends | `CommandSpec` и `execute_command` расширяются; контракт не ломается |
| Spec_v5 domain/guards/ | this → Spec_v5 | `Guard` type contract; `run_guard_pipeline` вызывается с результатом `spec.build_guards(cmd)` |

### Изменения в execute_command (Spec_v15 §2 BC-15-REGISTRY шаг 2)

Шаг 2 до:
```python
# Step 2: guard pipeline
guards = _build_spec_guards(spec, task_id, cmd=cmd)
guard_result, audit_events = _run_domain_pipeline(ctx, guards, stop_on_deny=True)
```

Шаг 2 после:
```python
# Step 2: guard pipeline — spec owns guard assembly (I-CMD-GUARD-FACTORY-1)
guards = spec.build_guards(cmd)
guard_result, audit_events = _run_domain_pipeline(ctx, guards, stop_on_deny=True)
```

Все остальные шаги (0, 1, 3, 4, 5) — без изменений.

### Nota Bene: task_id в execute_command

`task_id = _extract_task_id(cmd)` остаётся в `execute_command` — он нужен для сборки `GuardContext.task` (не для guard-сборки). Это не нарушает I-CMD-GUARD-FACTORY-1: kernel читает `task_id` для контекста, а не для выбора guards.

---

## 9. Verification

| # | Test Name | Invariant(s) |
|---|-----------|--------------|
| 1 | `test_execute_command_calls_build_guards` | I-CMD-GUARD-FACTORY-1 — mock spec.build_guards; assert called once with cmd |
| 2 | `test_build_guards_default_delegates_to_default_factory` | I-CMD-GUARD-FACTORY-2 — spec with guard_factory=None → _default_build_guards called |
| 3 | `test_build_guards_custom_delegates_to_guard_factory` | I-CMD-GUARD-FACTORY-2 — spec with guard_factory=mock_factory → factory called, not _default_build_guards |
| 4 | `test_custom_guard_factory_receives_full_guard_list` | I-CMD-GUARD-FACTORY-4 — switch-phase factory returns [phase_guard, switch_guard, norm_guard] |
| 5 | `test_default_factory_reads_spec_flags` | I-CMD-GUARD-FACTORY-3 — requires_active_phase=False → no phase guard; apply_task_guard=False → no task guard |
| 6 | `test_registry_no_conditional_on_spec_name` | I-CMD-GUARD-FACTORY-1 — grep/AST: assert `if spec.name` absent from execute_command body |
| 7 | `test_switch_phase_guard_factory_extracts_phase_id` | I-CMD-GUARD-FACTORY-4 — cmd.phase_id extracted inside factory; correct guard parameterized |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| Перемещение `_extract_task_id` в domain/guards/ | Phase N+1 (при появлении второго вызывающего) |
| Унификация `_KernelErrorEvent` с `core/events.py` | Отдельная фаза (другой кандидат из architecture review) |
| Рефакторинг `validate_invariants.py` (нечистый handler) | Отдельная фаза |
| Добавление actor guard для NORM-ACTOR-001..003 | Отдельная фаза |
