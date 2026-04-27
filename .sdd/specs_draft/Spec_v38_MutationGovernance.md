# Spec_v38 — Phase 38: Mutation Governance Runtime (OSML)

Status: Draft
Baseline: Spec_v37_TemporalNavigation.md
Note: Deferred items (ранее помечены "Phase 22") перенесены в Phase 34+ — Phase 22 не существует в roadmap; следующая после Phase 38 — Phase 31 (GovernanceCommands), затем 32, 33.

---

## 0. Goal

Phase 37 дала агенту **временную навигацию** — он умеет спрашивать "что изменилось и почему".
Но система слепа к одному классу изменений: **мутации за пределами TaskOutputs**.

Когда LLM фиксит баг в соседнем файле "попутно" — это изменение:
- не попадает в EventStore (audit gap)
- не проверяется DoD (validation blindness)
- нарушает границы задачи без фиксации (semantic drift)

Phase 38 вводит **Out-of-Scope Mutation Ledger (OSML)** — третий governance layer:

```
System := ⟨Kernel, ValidationRuntime, SpatialIndex, GraphNavigation, TemporalNavigation,
           MutationGovernanceRuntime⟩

SDD vNext = Tri-Layer Governance:
  Layer 1 — Structure Layer   (Spatial Index + Graph)
  Layer 2 — Execution Layer   (Kernel + Tasks + Temporal)
  Layer 3 — Deviation Layer   (OSML — этот spec)
```

OSML решает задачу управления **отклонениями** — временными нарушениями с explicit lifecycle:

```
Flagged → Pending → Resolved → Cleared
```

Ключевые архитектурные принципы:
- **I-OSML-1**: OSML-state derived exclusively from EventLog — никаких независимых mutable fields
- **I-OSML-3**: `OSMLGuard` MUST NOT block `record-change` — нет circular dependency
- **I-SCOPE-OSML-1**: `scope.py` классифицирует, OSML владеет lifecycle нарушений

---

## 1. Scope

### In-Scope

- **BC-38-0: Domain Events** — `OutOfScopeMutationFlagged` + `OutOfScopeChangeRecorded` (events.py)
- **BC-38-1: SDDState Extension** — `pending_osml_mutations` + reducer logic (reducer.py)
- **BC-38-2: yaml_state serialization** — секция `osml:` в State_index.yaml (yaml_state.py)
- **BC-38-3: flag-mutation command** — Layer 1 Detection (flag_mutation.py)
- **BC-38-4: record-change command** — Layer 2 Resolution (record_change.py)
- **BC-38-5: OSMLGuard** — Layer 3 Enforcement (osml_guard.py)
- **BC-38-6: scope.py evolution** — NORM-SCOPE-005 + `scope_status` field
- **BC-38-7: Registry + CLI** — регистрация, Click-команды, cli.schema.yaml
- **BC-38-8: Norm Catalog** — NORM-AUDIT-001, NORM-SCOPE-005
- **BC-38-9: CLAUDE.md invariants** — I-AUDIT-1, I-AUDIT-2(deferred)
- **BC-38-10: Tests** — unit + integration

### Out of Scope

- **I-AUDIT-2 enforcement** — diff-validation против git (требует git integration, Phase 34+)
- Автоматический перехват write-операций ядром (filesystem hooks) — никогда
- Изменения в `.sdd/specs/**` — иммутабельно (SDD-9)
- Удаление тестов Phase 17-20 — запрещено (CEP-3)

---

## 2. Mutation Lifecycle Model

OSML управляет мутациями через детерминированный lifecycle:

```
State:  ABSENT → [flag-mutation] → PENDING → [record-change] → RESOLVED
                                      |                              |
                                      └──── [PhaseInitialized] ─────┘
                                                    ↓
                                              ABANDONED (if pending)
                                              CLEARED   (if resolved)
```

| State | Meaning | EventLog trigger |
|-------|---------|-----------------|
| ABSENT | мутация не зарегистрирована | — |
| PENDING | мутация зафлажена, ещё не разрешена | `OutOfScopeMutationFlagged` |
| RESOLVED | мутация описана и обоснована | `OutOfScopeChangeRecorded` |
| ABANDONED | мутация была PENDING при смене фазы; аудит-след сохранён | `OutOfScopeMutationAbandoned` (emitted by reducer on PhaseInitialized) |
| CLEARED | все мутации фазы сброшены при старте новой фазы | `PhaseInitialized` |

**Идентичность мутации (mutation_id):**

```python
mutation_id = sha256(f"{task_id}:{file_path}:{phase_id}".encode()).hexdigest()[:16]
```

Добавление `phase_id` устраняет конфликт "два изменения одного файла в разных фазах" и корректно
моделирует "relationship (task, file, phase)" — то, что реально идентифицирует отклонение.

**I-OSML-MUTATION-ID-2:** mutation_id MUST be stable within a phase AND independent of replay
context. phase_id для `flag-mutation` и `record-change` MUST резолвиться одинаково из одного
EventLog состояния.

**I-OSML-MUTATION-ID-3:** `flag-mutation` и `record-change` MUST использовать одну и ту же
функцию `_compute_mutation_id()` из `flag_mutation.py` (shared import). Inline-переопределение
запрещено — любое расхождение → mutation не закроется никогда.

---

## 3. Architecture / BCs

### BC-38-0: Domain Events

**`src/sdd/core/events.py`** — добавить два frozen dataclass.

Добавить строки в `V1_L1_EVENT_TYPES` frozenset **прямой вставкой** (не через `register_l1_event_type`):

```python
"OutOfScopeMutationFlagged",
"OutOfScopeChangeRecorded",
"OutOfScopeMutationAbandoned",
```

**OutOfScopeMutationFlaggedEvent:**

```python
@dataclass(frozen=True)
class OutOfScopeMutationFlaggedEvent(DomainEvent):
    """Layer 1: LLM signals it's about to write outside TaskOutputs.
    event_source='runtime', level='L1' — reducer MUST process this event.
    I-OSML-REPLAY-1: replay-safe; no side-effects beyond state projection.
    """
    EVENT_TYPE: ClassVar[str] = "OutOfScopeMutationFlagged"
    mutation_id: str    # sha256(task_id + ":" + file_path + ":" + phase_id)[:16]
    task_id:     str
    file_path:   str
    phase_id:    int
    timestamp:   str    # ISO8601 UTC
```

**OutOfScopeChangeRecordedEvent:**

```python
@dataclass(frozen=True)
class OutOfScopeChangeRecordedEvent(DomainEvent):
    """Layer 2: LLM records what was changed outside scope and why.
    Resolves a PENDING mutation → RESOLVED state.
    I-OSML-REPLAY-1: replay-safe.
    I-OSML-4: if mutation_id not in pending — soft NormViolation (not block).
    """
    EVENT_TYPE: ClassVar[str] = "OutOfScopeChangeRecorded"
    mutation_id:  str    # must match a previously flagged mutation_id
    task_id:      str
    file_path:    str
    change_type:  str    # from OSML taxonomy (see §4)
    severity:     str    # low | medium | high (default: medium)
    reason:       str    # ≤ 500 chars, non-empty
    phase_id:     int
    timestamp:    str    # ISO8601 UTC
```

**OutOfScopeMutationAbandonedEvent:**

```python
@dataclass(frozen=True)
class OutOfScopeMutationAbandonedEvent(DomainEvent):
    """Emitted by reducer on PhaseInitialized for each PENDING mutation.
    Preserves audit trail — phase transition MUST NOT silently drop mutations.
    I-OSML-6: this event is NOT in _KNOWN_NO_HANDLER — reducer processes it,
    but it does NOT modify pending_osml_mutations (mutations already cleared
    by PhaseInitialized handler). Role: audit record only.
    I-OSML-REPLAY-1: replay-safe.
    """
    EVENT_TYPE: ClassVar[str] = "OutOfScopeMutationAbandoned"
    mutation_id: str
    task_id:     str
    file_path:   str
    phase_id:    int
    reason:      str    # always "PhaseTransition"
    timestamp:   str    # ISO8601 UTC
```

**Критически важно: event_source="runtime"**

Reducer применяет pre-filter: обрабатывает только `event_source="runtime"` + `level="L1"`.
Оба OSML-события ДОЛЖНЫ использовать `event_source="runtime"` — иначе reducer их проигнорирует
и `pending_osml_mutations` никогда не обновится (I-OSML-1 нарушение).

`DecisionRecordedEvent` использует `event_source="meta"` потому что он в `_KNOWN_NO_HANDLER`
(не меняет state). OSML-события меняют state → runtime.

**I-OSML-REPLAY-1:** OSML-события replay-safe — повторный replay дает идентичное состояние.
Идемпотентность: при повторном `OutOfScopeMutationFlagged` с тем же mutation_id — dedup в
reducer (entry уже есть → не добавляем).

### BC-38-1: SDDState Extension + Reducer

**`src/sdd/domain/state/reducer.py`**

**Критическое решение — вариант B с I-OSML-2:**

`pending_osml_mutations` хранится в `SDDState` как проекция EventLog (вариант B — быстрее),
НО инвариант I-OSML-2 требует, что это поле ДОЛЖНО быть воспроизводимо через чистый replay
EventLog без внешнего состояния.

**SDDState** — добавить поля между `plan_status` и `state_hash`:

```python
# После plan_status: str
pending_osml_mutations: tuple[tuple[str, str, str, str], ...] = field(default_factory=tuple)
# элемент: (mutation_id, task_id, file_path, phase_id_str)
# phase_id_str для hashability (tuple[str,str,str,str] полностью hashable)

@property
def pending_osml_count(self) -> int:
    """Derived convenience field. I-OSML-8: soft bound signal."""
    return len(self.pending_osml_mutations)
```

Поле `pending_osml_mutations` НЕ входит в `_HUMAN_FIELDS` → включается в `state_hash` (I-OSML-2 compliant).
`pending_osml_count` — property, не поле, не влияет на `state_hash`.

**REDUCER_VERSION: 1 → 2**

Bump версии обязателен: добавление нового поля в `state_hash` инвалидирует
существующие State_index.yaml файлы. После деплоя требуется `sdd sync-state`.

Обновить `_make_empty_state()`:
```python
pending_osml_mutations=(),
```

**EventReducer._EVENT_SCHEMA** — добавить (НЕ в `_KNOWN_NO_HANDLER`):

```python
"OutOfScopeMutationFlagged":    frozenset({"mutation_id", "task_id", "file_path", "phase_id"}),
"OutOfScopeChangeRecorded":     frozenset({"mutation_id", "task_id", "file_path",
                                            "change_type", "severity", "reason", "phase_id"}),
"OutOfScopeMutationAbandoned":  frozenset({"mutation_id", "task_id", "file_path",
                                            "phase_id", "reason"}),
```

**_fold() логика:**

Добавить mutable accumulator:
```python
pending_mutations: list[tuple[str, str, str, str]] = list(base.pending_osml_mutations)
```

В ветке `PhaseInitialized` — сброс (CLEARED/ABANDONED state):

```python
# I-OSML-6: emit OutOfScopeMutationAbandoned for each PENDING mutation
# before clearing — preserves audit trail, MUST NOT silently drop unresolved mutations
for m in pending_mutations:
    abandoned_events.append(OutOfScopeMutationAbandonedEvent(
        event_type="OutOfScopeMutationAbandoned",
        event_id=str(uuid.uuid4()),
        appended_at=now_ms,
        level="L1",
        event_source="runtime",
        caused_by_meta_seq=None,
        mutation_id=m[0],
        task_id=m[1],
        file_path=m[2],
        phase_id=int(m[3]),
        reason="PhaseTransition",
        timestamp=now_iso,
    ))
pending_mutations = []
```

`abandoned_events` должен быть собран в `_fold()` и возвращён вместе с итоговым состоянием
(или appended в EventStore до PhaseInitialized — архитектурное решение на усмотрение реализации,
главное: события должны попасть в EventLog ДО сброса, чтобы replay был корректным).

Новые ветки dispatch:
```python
elif event_type == "OutOfScopeMutationFlagged":
    entry = (
        event["mutation_id"],
        event["task_id"],
        event["file_path"],
        str(event["phase_id"]),
    )
    if entry not in pending_mutations:           # idempotency: no duplicate
        pending_mutations.append(entry)

elif event_type == "OutOfScopeChangeRecorded":
    mid = event.get("mutation_id")
    # I-OSML-4: soft check — warn if mutation_id not found, but do not raise
    # Warning recorded in audit; reducer proceeds regardless (no deadlock risk)
    if not any(e[0] == mid for e in pending_mutations):
        pass  # WarningEvent emitted by RecordChangeHandler before appending
    pending_mutations = [e for e in pending_mutations if e[0] != mid]

elif event_type == "OutOfScopeMutationAbandoned":
    pass  # audit-only event; pending already cleared by PhaseInitialized branch
```

Финальный `SDDState(...)`:
```python
pending_osml_mutations=tuple(pending_mutations),
```

### BC-38-2: yaml_state Serialization

**`src/sdd/domain/state/yaml_state.py`**

**read_state()** — добавить parsing:
```python
osml = data.get("osml", {})
raw_pending = osml.get("pending_mutations") or []
pending_osml_mutations: tuple[tuple[str, str, str, str], ...] = tuple(
    (str(e["mutation_id"]), str(e["task_id"]),
     str(e["file_path"]), str(e["phase_id"]))
    for e in raw_pending
    if isinstance(e, dict)
        and all(k in e for k in ("mutation_id", "task_id", "file_path", "phase_id"))
)
```

Передать в `SDDState(pending_osml_mutations=pending_osml_mutations, ...)`.

**write_state()** — добавить секцию в YAML dict:
```python
"osml": {
    # I-OSML-7: this is a derived cache, NOT source of truth.
    # Source of truth is EventLog replay. Manual edits MUST be followed by sdd sync-state.
    "pending_mutations": [
        {
            "mutation_id": m[0],
            "task_id":     m[1],
            "file_path":   m[2],
            "phase_id":    int(m[3]),
        }
        for m in state.pending_osml_mutations
    ],
    "pending_count": state.pending_osml_count,  # derived convenience field (I-OSML-8)
},
```

### BC-38-3: flag-mutation Command

**`src/sdd/commands/flag_mutation.py`** (новый файл)

Паттерн: строго следует `record_decision.py`.

```python
def _compute_mutation_id(task_id: str, file_path: str, phase_id: int) -> str:
    """Deterministic, idempotent. Scoped per (task, file, phase).
    sha256(task_id + ':' + file_path + ':' + str(phase_id))[:16]
    """
    raw = f"{task_id}:{file_path}:{phase_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

@dataclass(frozen=True)
class FlagMutationCommand:
    command_id:   str
    command_type: str
    payload:      Mapping[str, Any]
    task_id:      str
    file_path:    str
    phase_id:     int

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

class FlagMutationHandler(CommandHandlerBase):
    """Layer 1: Flag an out-of-scope write BEFORE executing it.
    Pure (I-HANDLER-PURE-1): returns [OutOfScopeMutationFlaggedEvent].
    Idempotent: same (task_id, file_path, phase_id) → same mutation_id.
    """

    @error_event_boundary(source=__name__)
    def handle(self, cmd: FlagMutationCommand) -> list[DomainEvent]:
        if not cmd.task_id.strip():
            raise InvalidState("task_id must not be empty (I-OSML-CMD-1)")
        if not cmd.file_path.strip():
            raise InvalidState("file_path must not be empty (I-OSML-CMD-1)")

        # I-OSML-8: soft bound — warn if too many pending mutations for this task
        task_pending = [
            m for m in cmd.state.pending_osml_mutations
            if m[1] == cmd.task_id
        ]
        if len(task_pending) >= 10:
            # emit WarningEvent, do NOT block
            warnings.append(_make_warning_event(
                f"I-OSML-8: {len(task_pending)} pending mutations for task {cmd.task_id} "
                f"(soft bound is 10). Consider resolving via record-change."
            ))

        mutation_id = _compute_mutation_id(cmd.task_id, cmd.file_path, cmd.phase_id)
        now_ms, now_iso = _utc_now_ms_iso()

        return [OutOfScopeMutationFlaggedEvent(
            event_type="OutOfScopeMutationFlagged",
            event_id=str(uuid.uuid4()),
            appended_at=now_ms,
            level=classify_event_level("OutOfScopeMutationFlagged"),
            event_source="runtime",          # MUST be runtime (not meta) — BC-38-0
            caused_by_meta_seq=None,
            mutation_id=mutation_id,
            task_id=cmd.task_id,
            file_path=cmd.file_path,
            phase_id=cmd.phase_id,
            timestamp=now_iso,
        )]
```

Экспортировать `_compute_mutation_id` — используется в `record_change.py` для deterministic match.

**CommandSpec:**
```python
"flag-mutation": CommandSpec(
    actor="llm",
    action="flag_mutation",
    projection=ProjectionType.STATE_ONLY,
    uses_task_id=False,               # task может быть в любом статусе
    event_schema=(OutOfScopeMutationFlaggedEvent,),
    requires_active_phase=True,
    description="Flag an out-of-scope write before executing it (I-AUDIT-1 Layer 1)",
)
```

### BC-38-4: record-change Command

**`src/sdd/commands/record_change.py`** (новый файл)

```python
_VALID_CHANGE_TYPES: frozenset[str] = frozenset({
    "structural_fix",    # add/remove code structures (classes, functions)
    "behavior_fix",      # fix logic or algorithm
    "config_change",     # configuration files
    "dependency_change", # imports, requirements
    "test_fix",          # test files outside TaskOutputs
    "tooling_change",    # scripts, generators, CI
})

_VALID_SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high"})

class RecordChangeHandler(CommandHandlerBase):
    """Layer 2: Record what was changed outside scope and why.
    Resolves a PENDING mutation (removes from pending_osml_mutations).
    Pure (I-HANDLER-PURE-1).
    I-OSML-3: this command MUST NOT be gated by OSMLGuard.
              OSMLGuard blocks validate/complete/check-dod — NOT record-change.
    I-OSML-4: if mutation_id not found in pending → emit WarningEvent, NOT raise.
              Rationale: blocking would create new deadlock paths; soft violation
              is visible in audit without breaking UX.
    """

    @error_event_boundary(source=__name__)
    def handle(self, cmd: RecordChangeCommand) -> list[DomainEvent]:
        if cmd.change_type not in _VALID_CHANGE_TYPES:
            raise InvalidState(
                f"change_type {cmd.change_type!r} invalid; "
                f"valid: {sorted(_VALID_CHANGE_TYPES)}"
            )
        severity = getattr(cmd, "severity", "medium")
        if severity not in _VALID_SEVERITIES:
            raise InvalidState(
                f"severity {severity!r} invalid; valid: {sorted(_VALID_SEVERITIES)}"
            )
        if not cmd.reason.strip():
            raise InvalidState("reason must not be empty")
        if len(cmd.reason) > 500:
            raise InvalidState(f"reason length {len(cmd.reason)} > 500 chars")

        mutation_id = _compute_mutation_id(cmd.task_id, cmd.file_path, cmd.phase_id)

        # I-OSML-4: soft NormViolation if mutation_id not in pending
        events: list[DomainEvent] = []
        if not any(m[0] == mutation_id for m in cmd.state.pending_osml_mutations):
            events.append(_make_warning_event(
                f"I-OSML-4: record-change for mutation_id={mutation_id} "
                f"({cmd.file_path}) not found in pending_osml_mutations. "
                f"Was flag-mutation called first?"
            ))
        # ...
```

**I-OSML-3 enforcement in registry.py:**

`record-change` НИКОГДА не получает `OSMLGuard` в своём guard pipeline.
`_build_spec_guards()` добавляет OSMLGuard только для `{"validate", "complete", "check-dod"}`.
`record-change` явно исключён из этого множества.

**CommandSpec:**
```python
"record-change": CommandSpec(
    actor="llm",
    action="record_change",
    projection=ProjectionType.STATE_ONLY,
    uses_task_id=False,
    event_schema=(OutOfScopeChangeRecordedEvent,),
    requires_active_phase=True,
    description="Record out-of-scope change and resolve pending mutation (I-AUDIT-1 Layer 2)",
)
```

### BC-38-5: OSMLGuard

**`src/sdd/domain/guards/osml_guard.py`** (новый файл)

```python
"""OSMLGuard — I-AUDIT-1 enforcement.

I-OSML-3: THIS GUARD MUST NOT be applied to record-change command.
Applied to: validate, complete, check-dod.

check_phase=True (check-dod): block if ANY pending mutation in current phase.
check_phase=False (validate/complete): block if pending mutations for THIS task_id.
"""

def make_osml_guard(task_id: str | None, check_phase: bool = False) -> Guard:
    def osml_guard(ctx: GuardContext) -> tuple[GuardResult, list[DomainEvent]]:
        pending = ctx.state.pending_osml_mutations   # tuple of (mid, tid, fpath, pid_str)
        current_phase = str(ctx.state.current_phase)

        if check_phase:
            # check-dod: все мутации текущей фазы
            # I-OSML-4-GUARD: filter by phase_id to avoid cross-phase false positives
            blocking = [m for m in pending if m[3] == current_phase]
        else:
            # validate/complete: только мутации текущей задачи в текущей фазе
            blocking = [
                m for m in pending
                if m[1] == task_id and m[3] == current_phase
            ]

        if not blocking:
            return GuardResult(GuardOutcome.ALLOW, "OSMLGuard", "no pending OSML mutations",
                               None, task_id), []

        files = ", ".join(m[2] for m in blocking)
        human_reason = f"Pending out-of-scope mutations ({len(blocking)}): {files}"[:140]

        deny_result = GuardResult(
            outcome=GuardOutcome.DENY,
            guard_name="OSMLGuard",
            message=(
                f"I-AUDIT-1 violation: {len(blocking)} unresolved out-of-scope mutations. "
                f"Call 'sdd record-change' for each: {files}"
            ),
            norm_id="NORM-AUDIT-001",
            task_id=task_id,
            reason="GUARD_DENY.OSMLGuard.I-AUDIT-1",
            human_reason=human_reason,
            violated_invariant="I-AUDIT-1",
        )
        audit_event = NormViolatedEvent(
            norm_id="NORM-AUDIT-001",
            actor="llm",
            action="pending_osml_unresolved",
            task_id=task_id,
            timestamp=ctx.now,
            # ... standard DomainEvent fields ...
        )
        return deny_result, [audit_event]

    return osml_guard
```

**Integration in `_build_spec_guards()` (registry.py):**

```python
# I-OSML-3: OSMLGuard applied ONLY to these commands (never record-change)
_OSML_GATED_COMMANDS: frozenset[str] = frozenset({"validate", "complete", "check-dod"})

def _build_spec_guards(spec: CommandSpec, task_id: str | None) -> list[Guard]:
    guards: list[Guard] = []
    # ... existing guards (phase, task, dependency, norm) ...
    if spec.name in _OSML_GATED_COMMANDS:
        check_phase = (spec.name == "check-dod")
        guards.append(make_osml_guard(task_id, check_phase=check_phase))
    return guards
```

### BC-38-6: scope.py Evolution (NORM-SCOPE-005)

**I-SCOPE-OSML-1:** `scope.py` ДОЛЖЕН только **классифицировать** scope (IN_SCOPE / OUT_OF_SCOPE_WRITE).
OSML **владеет lifecycle** нарушений: flag → pending → resolved.
Нельзя смешивать: scope.py не знает о OSML-состоянии; OSML не дублирует классификацию.

**`src/sdd/guards/scope.py`** — изменения:

1. Добавить `scope_status: str = "UNKNOWN"` в `ScopeDecision` (scope_policy.py).

2. Добавить `--outputs` флаг в CLI parser:
```
--outputs "src/foo.py,src/bar.py"   # comma-separated TaskOutputs
```

3. Добавить параметр `task_outputs: list[str] | None = None` в `check_scope()`.

4. В `write` branch — добавить NORM-SCOPE-005 проверку после specs-check:
```python
if task_outputs:
    resolved_outs = [
        Path(o).resolve()
        for o in task_outputs
        if o and o not in ("—", "-", "")
    ]
    if resolved_outs and resolved_path not in resolved_outs:
        return ScopeDecision(
            allowed=False,
            norm_id="NORM-SCOPE-005",
            reason=(
                f"Write to '{file_path}' is outside TaskOutputs (NORM-SCOPE-005). "
                f"Call 'sdd flag-mutation' before writing, then 'sdd record-change' after."
            ),
            operation=operation,
            file_path=file_path,
            scope_status="OUT_OF_SCOPE_WRITE",   # semantic signal to LLM
        )
```

5. Добавить `scope_status` в `ScopeDecision.to_dict()`.

6. Успешный write:
```python
return ScopeDecision(..., scope_status="IN_SCOPE")
```

**Graceful degradation:** если `--outputs` не передан (старый вызов без outputs) →
NORM-SCOPE-005 не применяется, backward compat сохранён.

### BC-38-7: Registry + CLI

**`src/sdd/commands/registry.py`**

Добавить lazy loaders:
```python
def _lazy_flag_mutation_handler() -> type[CommandHandlerBase]:
    from sdd.commands.flag_mutation import FlagMutationHandler
    return FlagMutationHandler

def _lazy_record_change_handler() -> type[CommandHandlerBase]:
    from sdd.commands.record_change import RecordChangeHandler
    return RecordChangeHandler
```

**`src/sdd/cli.py`** — добавить Click-команды:

```python
@cli.command("flag-mutation")
@click.option("--file", "file_path", required=True)
@click.option("--task", "task_id", required=True)
@click.option("--phase", type=int, default=None)
def flag_mutation(file_path, task_id, phase):
    """Flag out-of-scope write before executing it (I-AUDIT-1)."""
    # phase auto-detected from EventLog if None
    # constructs FlagMutationCommand → execute_and_project

@cli.command("record-change")
@click.option("--file", "file_path", required=True)
@click.option("--task", "task_id", required=True)
@click.option("--type", "change_type", required=True)
@click.option("--reason", required=True)
@click.option("--phase", type=int, default=None)
def record_change(file_path, task_id, change_type, reason, phase):
    """Record out-of-scope change and resolve pending mutation (I-AUDIT-1)."""
    # phase auto-detected from EventLog if None
    # constructs RecordChangeCommand → execute_and_project
```

**`.sdd/contracts/cli.schema.yaml`** — добавить:
- `flag-mutation`: `--file` (required path), `--task` (required), `--phase` (optional)
- `record-change`: `--file` (required), `--task` (required), `--type` (required, taxonomy), `--reason` (required, max 500), `--phase` (optional)
- `check-scope`: добавить `--outputs` (optional, comma-separated)

### BC-38-8: Norm Catalog

**`.sdd/norms/norm_catalog.yaml`**

Добавить в существующую llm `allowed_actions` секцию:
```yaml
- flag_mutation
- record_change
```

Без этого `NormGuard` (strict=True, default DENY) заблокирует обе команды.

Добавить новые нормы:

```yaml
- norm_id: NORM-SCOPE-005
  description: >
    LLM MUST NOT write to files not declared in TaskOutputs without registering via OSML.
    Scope classification only — lifecycle ownership belongs to OSML (I-SCOPE-OSML-1).
  actor: llm
  applies_to_phases: []
  enforcement: hard
  sdd_invariant_refs: [I-AUDIT-1, I-SCOPE-OSML-1]
  senar_category: ScopeViolation
  exception: >
    File is listed in task Outputs field (scope=IN_SCOPE), OR
    sdd flag-mutation was called before the write.
  non_overridable: true

- norm_id: NORM-AUDIT-001
  description: >
    LLM MUST follow the OSML protocol: flag-mutation BEFORE writing outside TaskOutputs,
    record-change AFTER writing. Resolve all pending mutations before sdd validate.
  actor: llm
  applies_to_phases: []
  allowed_actions:
    - flag_mutation
    - record_change
  enforcement: hard
  sdd_invariant_refs: [I-AUDIT-1, I-OSML-3]
  non_overridable: true
```

Добавить в `non_overridable`: `NORM-SCOPE-005`, `NORM-AUDIT-001`.

### BC-38-9: CLAUDE.md Updates

Добавить в `§INV — Baseline Invariants`:

```
| I-AUDIT-1          | Any write outside TaskOutputs MUST be preceded by sdd flag-mutation
|                    | and followed by sdd record-change before sdd validate/complete       |
| I-AUDIT-2          | (DEFERRED Ph34+) recorded changes MUST correspond to actual git diffs  |
| I-OSML-1           | OSML state MUST be derived exclusively from EventLog replay;
|                    | never persisted as independent mutable field outside SDDState          |
| I-OSML-2           | pending_osml_mutations MUST be fully reproducible via EventLog replay  |
| I-OSML-3           | OSMLGuard MUST NOT block record-change command itself (anti-deadlock)  |
| I-OSML-4           | record-change for unknown mutation_id → WarningEvent, NOT raise/block |
| I-OSML-6           | PhaseInitialized MUST emit OutOfScopeMutationAbandoned for each PENDING
|                    | mutation before clearing — no silent audit loss                        |
| I-OSML-7           | osml.pending_mutations in yaml is derived cache; manual edits need sync-state |
| I-OSML-8           | pending mutations per task SHOULD NOT exceed 10; soft WarningEvent only |
| I-OSML-MUTATION-ID-2| mutation_id MUST be stable within phase, independent of replay context |
| I-OSML-MUTATION-ID-3| flag-mutation and record-change MUST share _compute_mutation_id() import |
| I-SCOPE-OSML-1     | scope.py MUST only classify scope (IN_SCOPE/OUT_OF_SCOPE_WRITE);
|                    | OSML MUST own lifecycle of violations (flag→pending→resolved→cleared)  |
| I-SCOPE-2          | (DEFERRED Ph34+) TaskOutputs SHOULD be loaded from TaskSet, not LLM CLI |
```

Добавить в "LLM MUST NOT":
```
- Write files outside TaskOutputs without calling sdd flag-mutation first (I-AUDIT-1)
- Call sdd validate without resolving all pending OSML mutations (I-AUDIT-1)
- Gate record-change behind OSMLGuard (I-OSML-3)
- Reimplement _compute_mutation_id() inline — use shared import (I-OSML-MUTATION-ID-3)
- Treat State_index.yaml osml section as source of truth (I-OSML-7)
```

### BC-38-10: Tests

```
tests/unit/commands/test_flag_mutation.py
tests/unit/commands/test_record_change.py
tests/unit/guards/test_osml_guard.py
tests/unit/domain/state/test_reducer_osml.py   (additions to existing)
tests/unit/guards/test_scope_osml.py           (additions to existing)
```

---

## 4. OSML Change Type Taxonomy

Разделение: структурные ↔ поведенческие ↔ инфраструктурные изменения.

`severity` — опциональный параметр `--severity` в `record-change` CLI (default: `medium`).
Используется для фильтрации audit и future severity-based guard escalation (Phase 22+).

| change_type | Семантика | Default severity |
|-------------|-----------|-----------------|
| `structural_fix` | добавление/удаление классов, функций, типов | medium |
| `behavior_fix` | исправление логики или алгоритма | high |
| `config_change` | конфигурационные файлы | low |
| `dependency_change` | зависимости (imports, requirements, pyproject) | medium |
| `test_fix` | тестовые файлы вне TaskOutputs | low |
| `tooling_change` | скрипты, генераторы, CI, Makefile | low |

Если `--severity` не передан — используется default из таблицы. CLI может принять явное значение
`low | medium | high` для override.

---

## 5. Domain Events

### New Events (Phase 38)

| Event | Level | Source | Reducer | Description |
|-------|-------|--------|---------|-------------|
| `OutOfScopeMutationFlagged` | L1 | runtime | `_EVENT_SCHEMA` | Mutation lifecycle → PENDING |
| `OutOfScopeChangeRecorded` | L1 | runtime | `_EVENT_SCHEMA` | Mutation lifecycle → RESOLVED |
| `OutOfScopeMutationAbandoned` | L1 | runtime | `_EVENT_SCHEMA` | Audit trail для PENDING при PhaseInitialized (I-OSML-6) |

Все три события — L1 runtime → reducer обязан их обрабатывать.
Все три события — НЕ в `_KNOWN_NO_HANDLER`.

`OutOfScopeMutationAbandoned` — audit-only; в reducer ветка `pass` (pending уже очищен
ветками PhaseInitialized). Включён в `_EVENT_SCHEMA` для C-1 assertion.

**C-1 assertion (I-ST-10)** после Phase 38:

```
_KNOWN_NO_HANDLER ∪ frozenset(_EVENT_SCHEMA.keys()) == V1_L1_EVENT_TYPES
```

Новые типы добавлены в `V1_L1_EVENT_TYPES` (events.py) И в `_EVENT_SCHEMA` (reducer.py) атомарно.

### Backward Compatibility

Исторические события (до Phase 38) не затронуты.
Существующий State_index.yaml обновляется через `sdd sync-state` после деплоя.
`REDUCER_VERSION: 2` сигнализирует об изменении схемы (I-OSML-2).

---

## 6. Invariants

### New Invariants — Mutation Governance Layer

| ID | Statement | Phase | Verification |
|----|-----------|-------|-------------|
| I-AUDIT-1 | Any write outside TaskOutputs MUST be preceded by `sdd flag-mutation` and followed by `sdd record-change` before `sdd validate`/`complete` | 21 | `test_osml_guard.py`, integration smoke |
| I-AUDIT-2 | (DEFERRED) recorded changes MUST correspond to actual git diffs | 34+ | Phase 34+ |
| I-OSML-1 | OSML state MUST be derived exclusively from EventLog; never persisted as independent mutable field | 21 | `test_reducer_osml.py` (verify pure replay) |
| I-OSML-2 | `pending_osml_mutations` MUST be fully reproducible via EventLog replay (I-1 compliant) | 21 | `test_reducer_osml.py` (replay test) |
| I-OSML-3 | `OSMLGuard` MUST NOT block `record-change` command (anti-deadlock) | 21 | `test_osml_guard_record_change_bypass.py` |
| I-OSML-4 | `record-change` SHOULD correspond to an existing PENDING mutation. If mutation_id not found → emit WarningEvent (NOT raise, NOT block). Rationale: blocking creates new deadlock paths. | 21 | `test_record_change.py` (soft warn case) |
| I-OSML-5 | `flag-mutation` and `record-change` MUST refer to the same `file_path` as the actual write. Mechanical enforcement deferred to Phase 34+ (I-AUDIT-2 + git diff). Phase 38: invariant documented, not enforced. | 34+ | Phase 34+ git diff integration |
| I-OSML-6 | Phase transition MUST NOT silently drop unresolved mutations. On `PhaseInitialized`: for each PENDING mutation emit `OutOfScopeMutationAbandoned` BEFORE clearing `pending_osml_mutations`. Do NOT block phase transition. | 21 | `test_reducer_osml.py` (abandoned case) |
| I-OSML-7 | `osml.pending_mutations` in `State_index.yaml` is a derived cache, NOT source of truth. Source of truth is EventLog replay. Manual edits MUST be followed by `sdd sync-state`. | 21 | code review |
| I-OSML-8 | Number of pending mutations per task SHOULD NOT exceed 10. On `flag-mutation`: if count ≥ 10 → emit WarningEvent (NOT block). | 21 | `test_flag_mutation.py` (soft bound case) |
| I-OSML-CMD-1 | `FlagMutationCommand.task_id` and `file_path` MUST be non-empty | 21 | `test_flag_mutation.py` |
| I-OSML-REPLAY-1 | OSML events MUST be replay-safe: identical event sequence → identical `pending_osml_mutations` | 21 | `test_reducer_osml.py` |
| I-OSML-MUTATION-ID-1 | `mutation_id` MUST equal `sha256(f"{task_id}:{file_path}:{phase_id}")[:16]` | 21 | `test_flag_mutation.py`, `test_record_change.py` |
| I-OSML-MUTATION-ID-2 | `mutation_id` MUST be stable within a phase AND independent of replay context. `phase_id` MUST resolve identically from the same EventLog state in both `flag-mutation` and `record-change`. | 21 | `test_flag_mutation.py`, `test_record_change.py` |
| I-OSML-MUTATION-ID-3 | `flag-mutation` and `record-change` MUST use the same `_compute_mutation_id()` from `flag_mutation.py` (shared import). Inline reimplementation запрещена. | 21 | code review, import check in tests |
| I-SCOPE-OSML-1 | `scope.py` MUST only classify scope; OSML owns violation lifecycle | 21 | code review, `test_scope_osml.py` |
| I-SCOPE-2 | TaskOutputs SHOULD be loaded from TaskSet, not provided by LLM. DEFERRED Phase 34+: CLI `--outputs` remains for backward compat; Phase 34+ adds auto-load from TaskSet with LLM override only for debug. | 21 | Phase 34+ |

### Critical Deployment Invariant

| ID | Statement |
|----|-----------|
| I-REDUCER-ATOMIC-21 | `events.py` и `reducer.py` MUST be deployed atomically. C-1 assertion fires at import time if V1_L1_EVENT_TYPES and _EVENT_SCHEMA diverge. |

### Preserved Invariants (Phase 17-20)

I-HANDLER-PURE-1, I-KERNEL-WRITE-1, I-1, I-IDEM-1, I-GIT-TASK-1..I-TEMP-3, I-CAS-1..2, I-NAV-1..3, I-CONTEXT-1, I-SI-1..4 — без изменений.

---

## 7. Pre/Post Conditions

### M0 — Domain Events + Reducer

**Pre:** Phase 37 COMPLETE

**Post:**
- `OutOfScopeMutationFlaggedEvent`, `OutOfScopeChangeRecordedEvent`, `OutOfScopeMutationAbandonedEvent` в `events.py`
- Все три типа в `V1_L1_EVENT_TYPES` и `_EVENT_SCHEMA`
- `SDDState.pending_osml_mutations` добавлено, `pending_osml_count` property добавлено, `REDUCER_VERSION=2`
- `_fold()` обрабатывает все три события; PhaseInitialized emits OutOfScopeMutationAbandoned (I-OSML-6)
- C-1 assertion не ломается
- `test_reducer_osml.py` PASS

### M1 — yaml_state Serialization

**Pre:** M0 COMPLETE

**Post:**
- `read_state()` парсит `osml.pending_mutations`
- `write_state()` сериализует `osml.pending_mutations`
- Backward compat: отсутствие секции `osml:` → `pending_osml_mutations=()`
- State_index.yaml с новой схемой корректно round-trips

### M2 — flag-mutation + record-change Commands

**Pre:** M0 COMPLETE

**Post:**
- `flag_mutation.py`, `record_change.py` созданы
- `_compute_mutation_id()` экспортирован из `flag_mutation.py`; `record_change.py` импортирует его (I-OSML-MUTATION-ID-3)
- I-OSML-4: `record-change` emits WarningEvent (not raises) if mutation_id not in pending
- I-OSML-8: `flag-mutation` emits WarningEvent if task pending count ≥ 10
- Зарегистрированы в `REGISTRY`
- `test_flag_mutation.py`, `test_record_change.py` PASS

### M3 — OSMLGuard

**Pre:** M0, M2 COMPLETE

**Post:**
- `osml_guard.py` создан
- Интегрирован в `_build_spec_guards()` для `{"validate", "complete", "check-dod"}`
- Явно НЕ применяется к `record-change` (I-OSML-3)
- Guard фильтрует по `current_phase` (I-OSML-4-GUARD): мутации других фаз не блокируют
- `test_osml_guard.py` PASS: ALLOW без pending, DENY с pending текущей фазы,
  ALLOW для pending другой фазы, record-change bypasses guard

### M4 — scope.py + CLI

**Pre:** M0..M3 COMPLETE

**Post:**
- `--outputs` флаг добавлен в `sdd check-scope`
- NORM-SCOPE-005 применяется когда outputs переданы
- `scope_status` поле в `ScopeDecision.to_dict()`
- Backward compat: без `--outputs` → не применяется
- CLI-команды зарегистрированы в `cli.py`
- `test_scope_osml.py` PASS

### M5 — Norm Catalog + CLAUDE.md

**Pre:** M0..M4 COMPLETE

**Post:**
- `NORM-AUDIT-001`, `NORM-SCOPE-005` в `norm_catalog.yaml`
- `flag_mutation`, `record_change` в llm `allowed_actions`
- I-AUDIT-1, I-OSML-1..3, I-SCOPE-OSML-1 в `CLAUDE.md §INV`
- NormGuard не блокирует новые команды

### M6 — Integration Smoke

**Pre:** M0..M5 COMPLETE, `sdd sync-state` выполнен

**Post (smoke-тест):**
```bash
sdd flag-mutation --file src/foo.py --task T-001       # exit 0
sdd validate T-001                                      # exit 1, GUARD_DENY.OSMLGuard.I-AUDIT-1
sdd record-change --file src/foo.py --task T-001 \
  --type behavior_fix --reason "Fixed wrong key"        # exit 0
sdd validate T-001                                      # exit 0 (if other guards pass)
sdd check-scope --file src/other.py --op write \
  --outputs "src/foo.py" --task T-001                  # allowed=false, OUT_OF_SCOPE_WRITE
```

---

## 8. Use Cases

### UC-21-1: LLM Fixes Out-of-Scope Bug (Standard Flow)

**Actor:** LLM-агент в IMPLEMENT-сессии
**Trigger:** при реализации T-042 обнаружен баг в `scripts/report.py` (не в TaskOutputs)
**Pre:** Phase 38 ACTIVE, T-042 ACTIVE

**Steps:**
1. `sdd check-scope --file scripts/report.py --op write --outputs "src/sdd/..." --task T-042`
   → `{"allowed": false, "scope_status": "OUT_OF_SCOPE_WRITE", "norm_id": "NORM-SCOPE-005"}`
2. `sdd flag-mutation --file scripts/report.py --task T-042`
   → exit 0, `OutOfScopeMutationFlagged` в EventLog
3. LLM исправляет баг в `scripts/report.py`
4. `sdd record-change --file scripts/report.py --task T-042 --type behavior_fix --reason "Fixed wrong keyword keys"`
   → exit 0, мутация RESOLVED
5. `sdd complete T-042` → guard pipeline: PhaseGuard✓, DependencyGuard✓, NormGuard✓, OSMLGuard✓
   → exit 0

**Post:** аудит-след полный; TaskOutputs не нарушен; governance соблюдён

### UC-21-2: Anti-Deadlock — record-change never blocked by OSMLGuard

**Actor:** LLM-агент
**Trigger:** flag-mutation вызван, но validate запущен до record-change
**Pre:** `pending_osml_mutations` содержит запись для T-042

**Steps:**
1. `sdd validate T-042` → OSMLGuard DENY → exit 1 (expected)
2. `sdd record-change --file scripts/report.py --task T-042 --type behavior_fix --reason "..."` → exit 0
   ✓ OSMLGuard НЕ применяется к record-change (I-OSML-3)
3. `sdd validate T-042` → OSMLGuard ALLOW → продолжает → exit 0

**Post:** нет deadlock; протокол восстанавливаем

### UC-21-3: Phase Reset Clears Mutations

**Actor:** human — запускает `sdd activate-phase N+1`
**Trigger:** PhaseInitialized event эмитируется
**Pre:** Phase 38 COMPLETE с несколькими resolved mutations

**Steps:**
1. Human: `sdd activate-phase 22`
2. `PhaseInitializedEvent` → reducer: `pending_mutations = []`
3. `sdd show-state` → `pending_osml_mutations: []`

**Post:** CLEARED state; новая фаза стартует чисто

### UC-21-4: Scope Classification vs OSML Lifecycle Separation

**Actor:** LLM-агент
**Trigger:** two separate calls to scope.py and flag-mutation

**scope.py role:**
```
sdd check-scope --file X --op write --outputs "..." --task T-NNN
→ returns: { "allowed": false, "scope_status": "OUT_OF_SCOPE_WRITE" }
→ scope.py DONE. It classified. It knows nothing about OSML state.
```

**OSML role:**
```
sdd flag-mutation --file X --task T-NNN
→ creates PENDING mutation in EventLog
sdd record-change --file X ...
→ resolves mutation → RESOLVED
PhaseInitialized later
→ CLEARED
```

**Post:** два независимых слоя; нет double-source-of-truth (I-SCOPE-OSML-1)

---

## 9. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| Spec_v1 EventLog | BC-21 → v1 | EventStore.append, EventReducer |
| Spec_v9 Registry | BC-21 → v9 | CommandSpec, execute_and_project |
| Spec_v3 Guards | BC-21 → v3 | Guard type, GuardContext, GuardResult |
| Spec_v8 CLI | BC-21 → v8 | Click patterns, error handling |
| Spec_v17 VR | BC-21 preserves | CEP-3: no test deletion |
| Spec_v37 Temporal | BC-21 builds on | REDUCER_VERSION bump is additive |

### Architecture Position

```
                     ┌─────────────────────────────────────────┐
                     │  Tri-Layer Governance (Phase 38)         │
                     │                                          │
  Layer 1: Structure │  Spatial Index + Graph + Temporal        │
  Layer 2: Execution │  Kernel + Tasks + EventLog               │
  Layer 3: Deviation │  OSML: flag → pending → resolve → clear  │← BC-21
                     └─────────────────────────────────────────┘
```

### State Projection (Derived vs Human-Managed)

```yaml
# State_index.yaml (Phase 38)
phase:
  current: 21
  status: ACTIVE
tasks:
  completed: 5
  # ... existing fields ...
osml:                        # ← NEW (BC-38-2)
  pending_mutations:
    - mutation_id: "abc12345"
      task_id: "T-2101"
      file_path: "scripts/report.py"
      phase_id: 21
```

`osml.pending_mutations` — derived (rebuilt via EventLog replay). NOT human-managed.
Included in `state_hash` computation (I-OSML-2).

---

## 10. Verification

### Phase 38 Complete iff

```bash
# Regression: предыдущие фазы не сломаны
pytest tests/ -q   # Phase 17-20 по-прежнему PASS

# Reducer tests
pytest tests/unit/domain/state/test_reducer_osml.py -v
# Must pass:
#   - flag event → pending gets entry
#   - flag + record → pending empty
#   - dedup: two identical flag events → one entry
#   - PhaseInitialized with pending → OutOfScopeMutationAbandoned emitted for each (I-OSML-6)
#   - PhaseInitialized → pending cleared AFTER abandoned events
#   - replay: same events → same pending_osml_mutations
#   - EMPTY_STATE.pending_osml_mutations == ()
#   - two states differing in pending → different state_hash
#   - pending_osml_count == len(pending_osml_mutations)

# Handler tests
pytest tests/unit/commands/test_flag_mutation.py \
       tests/unit/commands/test_record_change.py -v
# Must pass:
#   - event_source="runtime", level="L1"
#   - mutation_id deterministic = sha256(task:file:phase)[:16]
#   - same inputs → same mutation_id (flag_mutation vs record_change)
#   - _compute_mutation_id is imported from flag_mutation in record_change (I-OSML-MUTATION-ID-3)
#   - invalid change_type → InvalidState
#   - invalid severity → InvalidState
#   - reason > 500 chars → InvalidState
#   - empty task_id or file_path → InvalidState (I-OSML-CMD-1)
#   - record-change for unknown mutation_id → WarningEvent emitted, NOT raise (I-OSML-4)
#   - flag-mutation when task has ≥10 pending → WarningEvent emitted, NOT block (I-OSML-8)

# Guard tests
pytest tests/unit/guards/test_osml_guard.py -v
# Must pass:
#   - no pending → ALLOW
#   - pending for T-001 current phase, guard for T-001 → DENY
#   - pending for T-002, guard for T-001 → ALLOW
#   - pending for T-001 OTHER phase, guard for T-001 current phase → ALLOW (I-OSML-4-GUARD)
#   - check_phase=True + pending in current phase → DENY
#   - check_phase=True + pending in OTHER phase → ALLOW (phase filter)
#   - DENY emits NormViolatedEvent(norm_id="NORM-AUDIT-001")
#   - violated_invariant == "I-AUDIT-1"
#   - reason == "GUARD_DENY.OSMLGuard.I-AUDIT-1"

# I-OSML-3 test
pytest tests/unit/guards/test_osml_guard_i_osml_3.py -v
# Must pass:
#   - record-change NOT in _OSML_GATED_COMMANDS
#   - flag-mutation NOT in _OSML_GATED_COMMANDS

# Scope tests
pytest tests/unit/guards/test_scope_osml.py -v
# Must pass:
#   - write + file in outputs → scope_status="IN_SCOPE", allowed=True
#   - write + file NOT in outputs → scope_status="OUT_OF_SCOPE_WRITE", allowed=False
#   - write + no outputs → allowed=True (backward compat)
#   - sentinel "—" in outputs ignored

# Integration smoke
sdd sync-state --phase 21                               # exit 0 (post-deploy rebuild)
sdd flag-mutation --file src/foo.py --task T-001        # exit 0
sdd validate T-001                                      # exit 1, GUARD_DENY.OSMLGuard
sdd record-change --file src/foo.py --task T-001 \
  --type behavior_fix --reason "Fixed X"                # exit 0
sdd check-scope --file src/foo.py --op write \
  --outputs "src/bar.py" --task T-001                   # allowed=false, OUT_OF_SCOPE_WRITE
```

### Test Suite

| # | File | Invariants |
|---|------|------------|
| 1 | `test_flag_mutation.py` | I-OSML-CMD-1, I-OSML-MUTATION-ID-1..3, I-OSML-REPLAY-1, I-OSML-8 |
| 2 | `test_record_change.py` | I-OSML-MUTATION-ID-1..3, I-OSML-4, change_type taxonomy, severity |
| 3 | `test_osml_guard.py` | I-AUDIT-1, NORM-AUDIT-001, I-OSML-4-GUARD (phase filter) |
| 4 | `test_osml_guard_i_osml_3.py` | I-OSML-3 (anti-deadlock) |
| 5 | `test_reducer_osml.py` | I-OSML-1, I-OSML-2, I-OSML-6, I-OSML-REPLAY-1 |
| 6 | `test_scope_osml.py` | I-SCOPE-OSML-1, NORM-SCOPE-005 |
| 7 | Integration smoke | I-AUDIT-1 end-to-end |

---

## 11. Out of Scope

| Item | Owner |
|------|-------|
| I-AUDIT-2: diff validation against git | Phase 34+ |
| I-OSML-5 enforcement: file_path vs actual write correspondence | Phase 34+ (git diff) |
| I-SCOPE-2: auto-load TaskOutputs from TaskSet (not CLI) | Phase 34+ |
| Severity-based guard escalation (high severity → block) | Phase 34+ |
| OSML phase summary (total/resolved/unresolved counts) | Phase 34+ |
| Filesystem write hooks (auto-intercept) | никогда |
| Phase 17-20 test deletion | никогда (CEP-3) |
| Distributed/concurrent OSML scenarios | Phase 34+ |

---

## Appendix A: Architecture Summary (Phase 18-21)

```
           ┌──────────────────────┐
           │  Glossary (TERM)     │  ← DDD entrypoint (sdd resolve)
           └──────────┬───────────┘
                      ↓ means edges
           ┌──────────────────────┐
           │  Spatial Index       │  ← структура (Phase 18)
           │  + Graph (edges)     │  ← связи + priority (Phase 36)
           └──────────┬───────────┘
                      ↓
      ┌───────────────┴────────────────┐
      ↓                                ↓
Git (WHAT changed)               EventLog (WHY it changed)
GitContentStore                  TaskImplementedEvent.commit_sha
nav-changed-since                TaskCheckpointEvent.commit_sha
Phase 37                         Phase 37
                                 +
                                 OutOfScopeMutationFlagged   ← Phase 38
                                 OutOfScopeChangeRecorded    ← Phase 38
```

**Full Cognitive Stack (Phase 18-21):**

| Question | Tool | Phase |
|----------|------|-------|
| WHERE (что существует?) | `sdd nav-get` | 18 |
| WHAT (как называется?) | `sdd resolve` | 18 |
| HOW (как связано?) | `sdd nav-neighbors` | 19 |
| WHEN (что изменилось?) | `sdd nav-changed-since` | 20 |
| WHY (почему изменилось?) | `sdd nav-task-commits` | 20 |
| **DID IT DEVIATE?** | **`sdd check-scope` + OSML** | **21** |

## Appendix B: Critical Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| C-1 assert breaks on partial deploy | `events.py` + `reducer.py` в одном атомарном коммите |
| State_index.yaml hash mismatch | REDUCER_VERSION bump + `sdd sync-state` после деплоя |
| NormGuard blocks new commands | `flag_mutation` + `record_change` в catalog `allowed_actions` КРИТИЧНО |
| event_source="meta" silently ignored by reducer | event_source="runtime" обязателен (см. BC-38-0) |
| Deadlock: validate blocked, record-change also blocked | I-OSML-3: record-change не в `_OSML_GATED_COMMANDS` |
| Phantom mutations (wrong task_id) | mutation_id includes phase_id; basic task_id format validation |
| Phase crossover guard false positives | OSMLGuard filters by current_phase (I-OSML-4-GUARD) |
| Silent audit loss on unresolved mutations at phase transition | OutOfScopeMutationAbandoned event (I-OSML-6) |
| record-change closes non-existent mutation silently | Soft NormViolation + WarningEvent (I-OSML-4) |
| mutation_id divergence between flag and record | I-OSML-MUTATION-ID-3: shared _compute_mutation_id() import |
| LLM passes wrong --outputs to check-scope | I-SCOPE-2: TaskSet auto-load deferred to Phase 22 |
