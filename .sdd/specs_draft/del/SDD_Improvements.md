# SDD Process Improvements

Status: DRAFT — proposals only, never auto-applied (§ROLES)
Last updated: 2026-04-25

---

## IMP-001 — Two-Mode validate-invariants (task vs system)

**Discovered in:** Phase 25 (T-2510 validation), 2026-04-25
**Implemented in:** Phase 25 (T-2511, T-2512)

### Problem

`sdd validate-invariants --phase N --task T-NNN` runs all build commands unconditionally:

```
validate-invariants
 ├─ spec-level checks   (CLAUDE.md, invariant presence)
 ├─ static checks       (lint, typecheck)
 └─ runtime checks      (pytest tests/ — full suite)   ← всегда, даже для doc tasks
```

Это нарушает два принципа:

| Принцип | Нарушение |
|---------|-----------|
| I-RRL-2: determinism | результат зависит от состояния DuckDB lock — недетерминирован |
| SEM-5: fail fast | D-state hang вместо clean skip |

**Важно:** проблема не в том, что pytest запускается для doc tasks (хотя это тоже плохо).
Проблема в том, что `validate-invariants` смешивает два семантически разных уровня:

- **Task validation** — проверяет: "задача выполнена корректно?" (scope = Task Outputs)
- **System validation** — проверяет: "система всё ещё консистентна?" (scope = полный suite)

Если сделать pytest conditional по Task Outputs (как предлагалось изначально):
system consistency перестаёт проверяться при doc/config задачах → рegressions могут
проскользнуть незамеченными. Это хуже, чем текущий баг.

### Solution: two explicit modes

Не conditional layers — два явных режима с разной семантикой:

```
MODE task (default, --task T-NNN без --system):
  ├─ spec-level: invariant presence in CLAUDE.md
  ├─ static: lint + typecheck (если src/** в outputs)
  └─ runtime: SKIP  ← нет pytest

MODE system (--system --phase N):
  ├─ spec-level: all invariants
  ├─ static: lint + typecheck (всегда)
  └─ runtime: pytest tests/ (всегда)  ← system gate
```

Разделение ответственности:
- `validate-invariants --task T-NNN` → **task gate** (быстро, детерминировано, нет DB)
- `validate-invariants --system --phase N` → **system gate** (полный suite, человек запускает явно)

### Implementation (Phase 25, T-2511)

Изменения в `src/sdd/commands/validate_invariants.py`:

**1. `ValidateInvariantsCommand` — добавить поле:**
```python
validation_mode: str = "task"  # "task" | "system"
```

**2. `ValidateInvariantsHandler.handle()` — фильтровать `test` в task mode:**
```python
if command.validation_mode == "task":
    build_commands = {k: v for k, v in build_commands.items() if k != "test"}
```

**3. `main()` — добавить флаг:**
```python
parser.add_argument("--system", action="store_true", default=False)
# ...
validation_mode = "system" if parsed.system else "task"
```

**4. Acceptance check в `main()` — skip в task mode:**
```python
if parsed.task and not parsed.system:
    # task mode: acceptance check runs ruff only, не проверяет test_returncode
```

### Properties

- **CLI-2 compliant** — `--system` добавляется как optional flag, non-breaking
- **I-HANDLER-PURE-1** — `handle()` остаётся pure, решение принимается по `command.validation_mode`
- **Детерминизм** — task mode никогда не касается DuckDB → нет D-state
- **System gate сохранён** — `--system` запускает полный suite; regression protection не теряется

### ValidationReport impact

Task mode skip MUST be recorded (I-RRL-3):
```
runtime_validation: SKIPPED
reason: task mode (--system not set)
applicable_layers: [spec, static]
```

---

## IMP-003 — validate-invariants task mode: filter ALL pytest commands, not just "test"

**Discovered in:** Phase 25 post-mortem, 2026-04-25
**Root cause:** T-2511 filter `k != "test"` too narrow
Implemented in: Phase 26 (T-2601, T-2602)
Invariant introduced: I-TASK-MODE-1

### Problem

```python
# current (T-2511):
build_commands = {k: v for k, v in build_commands.items() if k != "test"}
```

Config has both `test` AND `test_full`:
```yaml
test:      pytest tests/unit/ tests/integration/ -q   ← filtered ✓
test_full: pytest tests/ -q                           ← NOT filtered ✗ BUG
```

`test_full` still runs in task mode → D-state risk unchanged for full-suite.

### Fix (Phase 26)

```python
# option A — filter by key prefix:
if command.validation_mode == "task":
    build_commands = {k: v for k, v in build_commands.items()
                      if not k.startswith("test")}

# option B — filter by command content (more robust):
if command.validation_mode == "task":
    build_commands = {k: v for k, v in build_commands.items()
                      if "pytest" not in v}
```

Option B is safer: catches any future key name that runs pytest.

### Also: mypy slow in task mode

`typecheck: mypy src/sdd/` runs in task mode even for doc tasks (e.g. T-2510).
Consider skipping `typecheck` if no `src/**` in Task Outputs.

---

## IMP-004 — switch-phase: navigation command не должна быть идемпотентной

**Discovered in:** Phase 24 close + context switch to phase 18, 2026-04-25
**Status:** OPEN — spec draft готов

**Полный анализ и план реализации:** `.sdd/specs_draft/Spec_CommandIdempotency.md`

**Суть дефекта (D-7):** `compute_command_id` использует payload-хэш → два `switch-phase`
с одинаковыми параметрами дают одинаковый `command_id` → второе событие выбрасывается
через `I-IDEM-SCHEMA-1`. Navigation команда ошибочно идемпотентна.

**Исправление:** `CommandSpec.idempotent: bool = True`; для `switch-phase` — `False`;
`execute_command` передаёт `command_id=None` для `idempotent=False` команд.

**Новый инвариант:** `I-CMD-IDEM-1` — Navigation commands MUST NOT be idempotent.

---

## IMP-002 — pytest-timeout как hard requirement перед runtime-тестами

**Discovered in:** Phase 25, D-state hang during validate-invariants
**Status:** закрыт Spec_v25 BC-DB-6 (`pytest-timeout>=4.0`, `--timeout=30`)

Зафиксировано для reference: любая фаза, модифицирующая DB access patterns, MUST
иметь `--timeout` в `pyproject.toml` до запуска полного test suite. Без timeout
D-state = pytest висит бесконечно без диагностики.

---
