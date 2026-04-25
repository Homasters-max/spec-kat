# Spec_v9 — Phase 9: Command Envelope Refactor

Status: Draft
Baseline: Spec_v8_CLI.md (BC-ADAPT, BC-PROC, §0.15 Kernel Contract Freeze)

---

## 0. Goal

Phase 8 froze `core/types.py:Command` and revealed a systemic bug: every `main()` function
creates `*Command(command_id=..., field1=..., ...)` **without** the required base fields
`command_type` and `payload`, causing `TypeError` at runtime (exit code 2) in `sdd complete`,
`sdd validate`, and all other CLI operations.

The root cause is architectural: concrete `*Command` subclasses duplicate typed fields that
are already represented as `payload: Mapping[str, Any]` in the envelope. Two representations
of the same data diverge — exactly what happened.

Phase 9 eliminates the dual-representation permanently:

1. **Remove all concrete `*Command` subclasses** — `CompleteTaskCommand`, `ValidateTaskCommand`,
   etc. cease to exist.
2. **Add `core/payloads.py`** — one frozen `@dataclass` per command type (runtime validation
   at the boundary), plus `COMMAND_REGISTRY` and `build_command()` factory.
3. **Fix all `main()` functions** — use `build_command("CompleteTask", task_id=..., ...)`.
   `build_command` validates via the dataclass constructor; `KeyError` on unknown type,
   `TypeError` on wrong fields.
4. **Fix all handlers** — unpack via `PayloadClass(**command.payload)`, not typed field access
   on a concrete subclass.

After Phase 9: `sdd complete T-NNN` works. Adding a new command type requires one dataclass
and one registry entry — no subclass, no `main()` sync risk.

---

## 1. Scope

### In-Scope

- **BC-CMD-ENV**: `core/payloads.py` — payload dataclasses, `COMMAND_REGISTRY`,
  `build_command()` factory, `validate_payload()` helper
- **BC-CMD-FIX**: Update all `commands/*.py` that contain `*Command(Command)` subclasses —
  remove subclasses, fix `main()` to use `build_command()`, fix handlers to unpack payload
- **BC-CMD-TEST**: Tests for registry, factory, and end-to-end `sdd complete` smoke test

`core/types.py` is **not modified** — `Command` and `CommandHandler` remain frozen (I-KERNEL-EXT-1).

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-CMD-ENV: Command Envelope Support Layer

New module: `src/sdd/core/payloads.py`

```
src/sdd/core/
  payloads.py    # payload dataclasses + COMMAND_REGISTRY + build_command()
```

#### Payload dataclasses

All payload dataclasses are `@dataclass(frozen=True)`. Fields match exactly what handlers
currently access via typed subclass fields. No optional fields are added (out of scope).

```python
# src/sdd/core/payloads.py

@dataclass(frozen=True)
class CompleteTaskPayload:
    task_id:      str
    phase_id:     int
    taskset_path: str
    state_path:   str

@dataclass(frozen=True)
class ValidateTaskPayload:
    task_id:      str | None
    phase_id:     int
    result:       str | None       # "PASS" | "FAIL" | None
    check_dod:    bool
    taskset_path: str
    state_path:   str

@dataclass(frozen=True)
class SyncStatePayload:
    phase_id:     int
    taskset_path: str
    state_path:   str

@dataclass(frozen=True)
class CheckDoDPayload:
    phase_id:   int
    state_path: str

@dataclass(frozen=True)
class ReportErrorPayload:
    error_type:  str
    message:     str
    source:      str
    recoverable: bool

@dataclass(frozen=True)
class ValidateInvariantsPayload:
    phase_id:      int
    task_id:       str | None
    config_path:   str
    cwd:           str
    env_whitelist: tuple[str, ...]

@dataclass(frozen=True)
class ActivatePhasePayload:
    phase_id: int
    actor:    str

@dataclass(frozen=True)
class ActivatePlanPayload:
    plan_version: int
    actor:        str

@dataclass(frozen=True)
class ValidateConfigPayload:
    phase_id:    int
    config_path: str

@dataclass(frozen=True)
class MetricsReportPayload:
    phase_id:    int
    output_path: str | None

@dataclass(frozen=True)
class RecordDecisionPayload:
    decision_id: str
    title:       str
    summary:     str
    phase_id:    int
```

#### Registry and factory

```python
from typing import Any, Final

COMMAND_REGISTRY: Final[dict[str, type[Any]]] = {
    "CompleteTask":        CompleteTaskPayload,
    "ValidateTask":        ValidateTaskPayload,
    "SyncState":           SyncStatePayload,
    "CheckDoD":            CheckDoDPayload,
    "ReportError":         ReportErrorPayload,
    "ValidateInvariants":  ValidateInvariantsPayload,
    "ActivatePhase":       ActivatePhasePayload,
    "ActivatePlan":        ActivatePlanPayload,
    "ValidateConfig":      ValidateConfigPayload,
    "MetricsReport":       MetricsReportPayload,
    "RecordDecision":      RecordDecisionPayload,
}


def build_command(command_type: str, **kwargs) -> Command:
    """Single entry point for Command creation with runtime payload validation.

    This is the ONLY place where payload validation occurs. Handlers must
    trust the envelope and unpack directly (see handler migration pattern).

    Raises:
        KeyError:   unknown command_type (not in COMMAND_REGISTRY)
        TypeError:  wrong or missing fields for the payload dataclass
    """
    schema = COMMAND_REGISTRY[command_type]     # KeyError → unknown type
    payload_obj = schema(**kwargs)              # TypeError → invalid fields
    return Command(
        command_id=str(uuid.uuid4()),
        command_type=command_type,
        payload=asdict(payload_obj),
    )


# Testing/debug utility only — NOT for use in handler runtime path.
# Handlers must unpack directly: PayloadClass(**command.payload)
def _unpack_payload(command_type: str, raw: Mapping[str, Any]) -> Any:
    schema = COMMAND_REGISTRY[command_type]
    return schema(**raw)
```

#### Type Safety Trade-off (known limitation)

After Phase 9, mypy does **not** statically verify the correspondence between
`command_type: str` and the payload type. `COMMAND_REGISTRY` is annotated
`dict[str, type[Any]]` — the string-key dispatch is invisible to the type checker.

Correctness of the command layer is now guaranteed by:
1. `build_command()` — single runtime validation boundary (dataclass constructor)
2. Handler-side direct unpack: `PayloadClass(**command.payload)`
3. Tests: `test_build_command_missing_field`, `test_build_command_unknown_type`,
   `test_registry_coverage`

This is an explicit, accepted trade-off. Static enforcement of the registry is deferred
to Phase 10+ (I-REG-STATIC-1).

### BC-CMD-FIX: Fix concrete Command subclasses in commands/

For each affected module:

1. **Remove** the `*Command(Command)` subclass definition.
2. **Fix `main()`** — replace `XCommand(command_id=..., ...)` with
   `build_command("X", field=..., ...)`.
3. **Fix handlers** — replace `command.field_name` with
   `p = PayloadClass(**command.payload); p.field_name` (handler uses its own payload type directly — no registry lookup).

Affected modules and their removed subclasses:

| Module | Removed subclass(es) |
|--------|----------------------|
| `commands/update_state.py` | `CompleteTaskCommand`, `ValidateTaskCommand`, `SyncStateCommand`, `CheckDoDCommand` |
| `commands/report_error.py` | `ReportErrorCommand` |
| `commands/validate_invariants.py` | `ValidateInvariantsCommand` |
| `commands/activate_phase.py` | `ActivatePhaseCommand` |
| `commands/activate_plan.py` | `ActivatePlanCommand` |
| `commands/validate_config.py` | `ValidateConfigCommand` |
| `commands/metrics_report.py` | `MetricsReportCommand` |
| `commands/record_decision.py` | `RecordDecisionCommand` |

`QueryEventsCommand` is **not** a `Command` subclass — exempt.  
Internal `_*WithCmd` event dataclasses (e.g. `_TaskImplementedWithCmd`) are **not** `Command`
subclasses — exempt.

### BC-CMD-TEST: Tests

```
tests/unit/core/test_payloads.py        ← registry + factory tests
tests/unit/test_sdd_complete_smoke.py   ← end-to-end: sdd complete against real TaskSet fixture
```

### Dependencies

```
BC-CMD-ENV → core/types.py          (imports Command; no modification)
BC-CMD-FIX → BC-CMD-ENV             (imports build_command, validate_payload)
BC-CMD-TEST → BC-CMD-ENV + BC-CMD-FIX
```

---

## 3. Domain Events

No new domain events. The events emitted by handlers (`TaskImplementedEvent`, etc.) are
unchanged. Phase 9 only changes how `Command` objects are constructed and unpacked.

---

## 4. Types & Interfaces

### Public interface — `core/payloads.py`

```python
# Exported public symbols
COMMAND_REGISTRY: Final[dict[str, type[Any]]]   # read-only; do not mutate at runtime
build_command(command_type: str, **kwargs) -> Command

# Internal / testing only — not exported from __init__.py
_unpack_payload(command_type: str, raw: Mapping[str, Any]) -> Any
```

### Invariant — no direct `Command(...)` construction in `commands/`

After Phase 9, `grep -r "Command(command_id" src/sdd/commands/` returns no matches.
All construction goes through `build_command()`.

---

## 5. Invariants

### New Invariants

| ID | Statement | Verified by |
|----|-----------|-------------|
| I-CMD-ENV-1 | `src/sdd/commands/` contains no `class *Command(Command)` subclass definitions | `test_no_command_subclasses` (AST grep) |
| I-CMD-ENV-2 | Every string key in `COMMAND_REGISTRY` is used by exactly one `build_command()` call in `commands/` | `test_registry_coverage` |
| I-CMD-ENV-3 | `build_command(type, **kwargs)` raises `TypeError` when required payload fields are missing | `test_build_command_missing_field` |
| I-CMD-ENV-4 | `build_command(type, **kwargs)` raises `KeyError` for an unregistered `command_type` | `test_build_command_unknown_type` |
| I-CMD-ENV-5 | All payload dataclasses are `frozen=True` (AST check) | `test_payload_dataclasses_frozen` |
| I-CMD-ENV-6 | `sdd complete T-NNN` exits 0 when task status is TODO in the current active phase | `test_sdd_complete_smoke` (subprocess) |

### Preserved Invariants

| ID | Statement |
|----|-----------|
| I-KERNEL-EXT-1 | `core/types.py` `Command` fields and `CommandHandler` Protocol are unchanged |
| I-CMD-1 | `handle(command)` is idempotent by `command_id` |
| I-CMD-4 | Task status transition TODO → DONE is atomic |

---

## 6. Pre/Post Conditions

### `build_command(command_type, **kwargs)`

**Pre:**
- `command_type` ∈ `COMMAND_REGISTRY`
- `kwargs` matches the field set of `COMMAND_REGISTRY[command_type]`

**Post:**
- Returns `Command(command_id=<uuid4>, command_type=command_type, payload=<asdict of payload>)`
- `payload` is a `MappingProxyType` (frozen via `Command.__post_init__`)

**Failure modes:**
- `KeyError` if `command_type` not registered
- `TypeError` if `kwargs` has missing or unexpected fields

### Handler direct unpack: `PayloadClass(**command.payload)`

This is not a function call — it is the required pattern inside each handler.

**Pre:**
- `command` was constructed by `build_command()` — payload is a valid `dict` matching `PayloadClass` fields
- Handler uses its own statically-known `PayloadClass` (e.g. `CompleteTaskPayload`)

**Post:**
- Returns a frozen `PayloadClass` instance

**Failure modes:**
- `TypeError` if payload keys don't match — indicates command was not constructed via `build_command()`

### `_unpack_payload(command_type, raw)` — testing/debug only

Not exported. Used in tests to verify registry mappings. Must not appear in handler code.

---

## 7. Use Cases

### UC-1: Fix `sdd complete T-814`

**Actor:** LLM (post-T-814 implementation)  
**Trigger:** `python3 .sdd/tools/update_state.py complete T-814`  
**Pre:** Phase 8 ACTIVE, T-814 status TODO, `pip install -e .` done  
**Steps:**
1. `update_state.py` delegates to `sdd complete T-814`
2. `cli.py` routes to `update_state.main(["complete", "T-814"])`
3. `main()` calls `build_command("CompleteTask", task_id="T-814", phase_id=8, ...)`
4. `build_command` validates via `CompleteTaskPayload(task_id="T-814", ...)` — no TypeError
5. `CompleteTaskHandler.handle(command)` — unpacks `CompleteTaskPayload(**command.payload)`, proceeds
6. Exit 0; `TaskImplemented` event emitted

**Post:** T-814 status DONE in TaskSet; State synced; exit 0

### UC-2: Developer adds a new command type

**Actor:** Developer (Phase N)  
**Steps:**
1. Add `NewCommandPayload` dataclass to `core/payloads.py`
2. Register: `COMMAND_REGISTRY["NewCommand"] = NewCommandPayload`
3. In `commands/new_command.py`: `cmd = build_command("NewCommand", field=val, ...)`
4. No subclass, no inheritance, no sync risk

---

## 8. Integration

### Impact on frozen interfaces (§0.15)

| Frozen surface | Changed? |
|----------------|----------|
| `core/types.py` — `Command` fields | **No** |
| `core/types.py` — `CommandHandler` Protocol | **No** |
| `infra/event_log.py` — `sdd_append*`, `sdd_replay` | No |
| `infra/event_store.py` — `EventStore.append()` | No |
| `domain/state/reducer.py` — `reduce()` | No |
| `domain/guards/context.py` — `GuardContext*` | No |

All frozen surfaces are **untouched**. Phase 9 is a non-breaking refactor within the
non-frozen `commands/` layer + new `core/payloads.py` module.

### Handler migration pattern

```python
# Before (Phase 8 — broken):
class CompleteTaskHandler(CommandHandlerBase):
    def handle(self, command: CompleteTaskCommand) -> list[DomainEvent]:
        task_id = command.task_id   # AttributeError if constructed via main()

# After (Phase 9 — correct):
from sdd.core.payloads import CompleteTaskPayload

class CompleteTaskHandler(CommandHandlerBase):
    def handle(self, command: Command) -> list[DomainEvent]:
        p = CompleteTaskPayload(**command.payload)   # handler knows its type; no registry lookup
        task_id = p.task_id
```

**Why direct unpack instead of `validate_payload(command.command_type, ...)`:**
- Handler already knows which payload type it expects — registry lookup via string is redundant
- `command.command_type` is not re-validated here; handler trusts the envelope (build_command is the boundary)
- mypy can track `p: CompleteTaskPayload` with the direct form; it cannot with the registry lookup form
- If the wrong command_type somehow reaches the handler, `PayloadClass(**command.payload)` raises `TypeError` on field mismatch — same protection, explicit type

### `main()` migration pattern

```python
# Before:
CompleteTaskHandler(db).handle(CompleteTaskCommand(
    command_id=str(uuid.uuid4()),
    task_id=parsed.task_id,
    phase_id=phase_id,
    taskset_path=taskset,
    state_path=parsed.state,
))

# After:
from sdd.core.payloads import build_command

CompleteTaskHandler(db).handle(build_command(
    "CompleteTask",
    task_id=parsed.task_id,
    phase_id=phase_id,
    taskset_path=taskset,
    state_path=parsed.state,
))
```

---

## 9. Verification

| # | Test file | Key tests | Invariant(s) |
|---|-----------|-----------|--------------|
| 1 | `tests/unit/core/test_payloads.py` | `test_build_command_returns_command`, `test_build_command_missing_field`, `test_build_command_unknown_type`, `test_payload_dataclasses_frozen`, `test_registry_coverage`, `test_no_command_subclasses` (AST grep `commands/`) | I-CMD-ENV-1..5 |
| 2 | `tests/unit/test_sdd_complete_smoke.py` | `test_sdd_complete_exits_zero` (subprocess with real TaskSet fixture, isolated tmp dir) | I-CMD-ENV-6 |
| 3 | Existing test suite passes unchanged | No regressions in `tests/unit/commands/test_complete_task.py`, `test_activate_phase.py`, etc. | I-CMD-1, I-CMD-4 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| `QueryEventsCommand` migration (not a `Command` subclass — no bug) | — (no action needed) |
| Pydantic validation (full schema validation with type coercion) | Phase 11+ |
| CLI events (`CLICommandStarted`, `CLICommandCompleted`) in EventLog | Phase 10 |
| I-REG-STATIC-1 runtime enforcement | Phase 10 |
| Removing `.sdd/tools/*.py` entirely | Phase 11 |
| `sdd norm-check`, `sdd norm-list` CLI subcommands | Phase 10 |
| `sync_state.py → sdd sync-state` CLI command | Phase 10 |
| I-ACCEPT-2 pytest failure attribution | Phase 10 |
| Compatibility tests: v2 API against v1 EventLog fixture (I-EL-4) | Phase 10 |

---

## 11. Task Decomposition (guidance for Decompose Phase 9)

Suggested task grouping (10 tasks, TG-2 compliant):

| T-ID | Outputs | Invariants |
|------|---------|------------|
| T-901 | `src/sdd/core/payloads.py` | I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5 |
| T-902 | `src/sdd/commands/update_state.py` (remove 4 subclasses, fix main+handlers) | I-CMD-ENV-1, I-CMD-ENV-6 |
| T-903 | `src/sdd/commands/report_error.py` | I-CMD-ENV-1 |
| T-904 | `src/sdd/commands/validate_invariants.py` | I-CMD-ENV-1 |
| T-905 | `src/sdd/commands/activate_phase.py`, `activate_plan.py` | I-CMD-ENV-1 |
| T-906 | `src/sdd/commands/validate_config.py`, `metrics_report.py` | I-CMD-ENV-1 |
| T-907 | `src/sdd/commands/record_decision.py` | I-CMD-ENV-1 |
| T-908 | `tests/unit/core/test_payloads.py` | I-CMD-ENV-1..5 |
| T-909 | `tests/unit/test_sdd_complete_smoke.py` | I-CMD-ENV-6 |
| T-910 | `CLAUDE.md` (remove §0.10 deprecated note; document `build_command` pattern) | governance |
