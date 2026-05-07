# Spec_v0_Compatibility — Phase 0: Compatibility Contract

Status: Draft
Baseline: sdd_v1 reference implementation (sdd_event_log.py, sdd_db.py, update_state.py)

---

## 0. Goal

Define the formal compatibility contract between sdd_v1 (current governance framework,
`.sdd/tools/` standalone scripts) and sdd_v2 (rebuilt Python package `src/sdd/`).
Any v2 implementation that satisfies this spec is a valid drop-in replacement.

This spec is written BEFORE Phase 1 and never changes. It is the arbiter of compatibility
disputes across all subsequent phases.

---

## 1. Event Schema Contract

### 1.1 Database Schema (DuckDB `events` table)

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| `seq` | BIGINT PK | yes | globally monotonic AUTOINCREMENT |
| `partition_key` | VARCHAR | yes | `"sdd"` for governance, `"metrics"` for metrics |
| `event_id` | VARCHAR UNIQUE | yes | SHA-256 deterministic, collision-resistant |
| `event_type` | VARCHAR | yes | see §1.2 |
| `payload` | VARCHAR | yes | JSON-serialized dict, sort_keys=True |
| `schema_version` | INTEGER | yes | 1 for all v1 events |
| `appended_at` | BIGINT | yes | Unix milliseconds |
| `level` | VARCHAR | no | `"L1"` \| `"L2"` \| `"L3"` \| NULL (NULL → treated as L2) |
| `expired` | BOOLEAN | no | FALSE = active, TRUE = archived (L3 TTL) |

v2 MUST add these additional columns (new in v2, absent in v1 events):

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| `event_source` | VARCHAR | yes (v2) | `"meta"` \| `"runtime"` |
| `caused_by_meta_seq` | BIGINT | no | seq of meta event that triggered this runtime event; NULL = no meta context |

**v1 compatibility coercion rule:** when loading v1 events (no `event_source` column),
treat all as `event_source = "runtime"`. This is the only lossy coercion allowed.

### 1.2 L1 Event Catalog (Replay-critical)

These event types constitute the domain truth. v2 MUST preserve their `event_type` string and
required payload field names exactly (I-EL-6).

#### TaskImplemented

Emitted by: `update_state.py complete T-NNN`

```python
payload = {
    "task_id":   str,          # e.g. "T-601" — required
    "phase_id":  str,          # e.g. "6"    — required (string, not int)
    "actor":     str,          # "llm" | "human" — required
    "timestamp": str,          # ISO8601 UTC e.g. "2026-04-10T23:00:00Z" — required
}
```

#### TaskValidated

Emitted by: `update_state.py validate T-NNN --result PASS|FAIL`

```python
payload = {
    "task_id":   str,   # required
    "phase_id":  str,   # required (string)
    "result":    str,   # "PASS" | "FAIL" — required
    "timestamp": str,   # ISO8601 UTC — required
}
```

#### PhaseCompleted

Emitted by: `update_state.py validate T-NNN --check-dod` (when DoD passes)

```python
payload = {
    "phase_id":  str,   # required (string)
    "timestamp": str,   # ISO8601 UTC — required
}
```

#### TestRunCompleted

Emitted by: `update_state.py validate T-NNN --run-tests`

```python
payload = {
    "task_id":    str,   # required
    "result":     str,   # "PASS" | "FAIL" — required
    "returncode": int,   # pytest exit code — required
    "summary":    str,   # first 500 chars of stdout+stderr — required
}
```

#### SDDEventRejected

Emitted by: `phase_guard.py check` (on rejection)

```python
payload = {
    "guard":   str,            # guard name e.g. "PhaseGuard" — required
    "reason":  str,            # human-readable — required
    "command": str,            # rejected command string — required
    "task_id": str | None,     # task context, may be None — required (nullable)
}
```

#### DecisionRecorded

Emitted by: `record_decision.py`

```python
payload = {
    "decision":  str,          # short decision statement — required
    "rationale": str,          # why this decision — required
    "entities":  list[str],    # affected artifacts — required (may be empty list)
    "timestamp": str,          # ISO8601 UTC — required
    # optional fields (may be absent):
    "phase_id":  str,          # if phase context known
    "task_id":   str,          # if task context known
}
```

#### StateDerivationCompleted

Emitted by: `sync_state.py`

```python
payload = {
    "phase":     int | str,    # phase number — required
    "completed": int,          # tasks completed count — required
    "total":     int,          # tasks total count — required
    "timestamp": str,          # ISO8601 UTC — required
}
```

### 1.3 L2 Event Catalog (Telemetry — schema NOT contractual)

L2 events (MetricRecorded, ToolUseStarted, ToolUseCompleted, BashCommandStarted,
BashCommandCompleted) are observability artifacts. Their payload schema may evolve
between v1 and v2 without violating this spec. Consumers MUST NOT rely on L2 payload
field names for correctness.

### 1.4 L3 Event Catalog (Debug — schema NOT contractual)

L3 events (ToolUseStarted, ToolUseCompleted when classified as debug-level) are
ephemeral. Schema not contractual. Must be archived (expired=true) after TTL, never
physically deleted (I-EL-7).

### 1.5 event_id Generation

v1 algorithm (MUST be preserved in v2 for idempotency):

```python
def make_event_id(event_type: str, canonical_payload: str, timestamp_ms: int) -> str:
    raw = f"{event_type}{canonical_payload}{timestamp_ms}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

where `canonical_payload = json.dumps(payload, sort_keys=True)`.

Note: `update_state.py` uses a slightly different algorithm
(`f"{event_type}|{json.dumps(payload, sort_keys=True)}|{ts_iso}"`). v2 MUST support
reading events written by either algorithm — use `ON CONFLICT DO NOTHING` on write.

---

## 2. event_source Contract (I-EL-1)

```
event_source ∈ {"meta", "runtime"}
```

- `"meta"` — governance events emitted by `.sdd/tools/` scripts (sdd_v2: `src/sdd/hooks/`)
- `"runtime"` — application domain events emitted by `src/sdd/` package itself
- v1 events (no `event_source` column) → coerced to `"runtime"` when loaded

**Reducer rule (I-EL-3):** the domain state reducer processes ONLY `event_source="runtime"`.
Meta events MUST be filtered before entering the reducer. This prevents governance
overhead from corrupting application state.

**sdd_replay default (I-EL-10):** `sdd_replay()` with no arguments returns
`level=L1, source="runtime"` events only. This is the canonical replay path.

---

## 3. Invariant Equivalence

v2 MUST satisfy all I-SDD-1..19 invariants from `SDD_Spec_v1.md` plus the following
EventLog and Command invariants:

| ID | Statement | Enforced by |
|----|-----------|-------------|
| I-PK-1 | `open_sdd_connection` idempotent: N calls → same schema | `infra/db.py` |
| I-PK-2 | `sdd_append` idempotent: duplicate `event_id` → `ON CONFLICT DO NOTHING` | `infra/event_log.py` |
| I-PK-3 | `sdd_replay` returns events ordered strictly by `seq ASC` | `infra/event_log.py` |
| I-PK-4 | `classify_event_level` is a pure total function (no side effects, no IO) | `core/events.py` |
| I-PK-5 | `atomic_write` uses tmp file + `os.replace` (no partial writes) | `infra/` |
| I-EL-1 | `event_source ∈ {"meta","runtime"}` enforced at write time | `infra/event_log.py` |
| I-EL-2 | `sdd_replay(level="L1", source="runtime")` returns ONLY L1 runtime events | `infra/event_log.py` |
| I-EL-3 | meta events do NOT cause state changes (reducer filters them) | `domain/state/reducer.py` |
| I-EL-4 | `v2.sdd_replay(v1_events, source="runtime", level="L1")` → same State as v1 | `tests/compatibility/` |
| I-EL-5 | `seq` globally monotonic across meta + runtime (single AUTOINCREMENT) | `infra/db.py` |
| I-EL-6 | L1 `event_type` names and required field names identical between v1 and v2 | `tests/compatibility/test_v1_schema.py` |
| I-EL-7 | L3 events archived (`expired=true`), never physically deleted | `infra/event_log.py` |
| I-EL-8 | runtime events have `caused_by_meta_seq: Optional[int]` in schema | `infra/db.py` |
| I-EL-9 | all DB writes go through `sdd_append` — no `duckdb.connect` outside `infra/db.py` | `code_rules` + `validate_invariants.py` |
| I-EL-10 | `sdd_replay()` default params = `level="L1", source="runtime"` | `infra/event_log.py` |
| I-EL-11 | `TaskCompleted + MetricRecorded` written via `sdd_append_batch` (single txn) | `infra/event_log.py` |
| I-CMD-1 | `handle(command)` idempotent by `command_id` — re-processing returns `[]` | `commands/` |
| I-M-1 | every `TaskCompleted` event → ≥1 `MetricRecorded` in same batch | `infra/metrics.py` |

---

## 4. Replay Compatibility

### I-EL-4: State-level Replay Compatibility

Given a fixture of v1 L1 events (from `tests/compatibility/fixtures/v1_events.json`):

```python
v1_events = load_fixture("v1_events.json")  # list[dict], event_source="runtime" coerced

# v2 replay
state_v2 = sdd_replay(events=v1_events, level="L1", source="runtime")

# v1 replay (reference)
state_v1 = v1_replay(v1_events)

assert state_v2 == state_v1
```

This test lives in `tests/compatibility/test_v1_replay.py` (Phase 7).

### I-EL-6: Event-level Schema Compatibility

For every L1 `event_type` in §1.2, v2 events of that type MUST have all required
fields present with the same names and compatible types. Test:

```python
# tests/compatibility/test_v1_schema.py
for event in load_fixture("v1_events.json"):
    schema = V1_L1_SCHEMA[event["event_type"]]
    for field in schema["required_fields"]:
        assert field in event["payload"], f"{field} missing in {event['event_type']}"
```

### Coercion rules (one-way, v1→v2 only)

| v1 field state | v2 interpretation |
|----------------|-------------------|
| no `event_source` column | `event_source = "runtime"` |
| `level = NULL` | treated as `"L2"` |
| no `expired` column | treated as `expired = FALSE` |
| no `caused_by_meta_seq` | treated as `NULL` |

No v2→v1 coercion is required. v2 is a superset.

---

## 5. CLI Contract

The following CLI entry points MUST be preserved in v2 with identical exit codes and
JSON stdout contract:

### 5.1 update_state.py (→ `sdd.commands.update_state`)

```bash
update_state.py check    T-NNN
    # exit 0: {"ok": true, "task_id": str, "status": str, "phase": int}
    # exit 1: {"ok": false, "error": str}

update_state.py complete T-NNN [--actor llm|human]
    # exit 0: {"ok": true, "task_id": str, "phase": int, "event": {...}, "derived": {...}}
    # exit 1: {"ok": false, "error": str}
    # side effects: TaskImplemented emitted, MetricRecorded emitted (I-M-1)

update_state.py validate T-NNN --result PASS|FAIL [--check-dod]
    # exit 0: {"ok": true, "task_id": str, "result": str, "check_dod": {...}|null}
    # exit 1: {"ok": false, "error": str}
    # side effects: TaskValidated emitted; PhaseCompleted emitted if --check-dod + DoD passes

update_state.py validate T-NNN --run-tests [--check-dod]
    # same as above; also runs pytest and emits TestRunCompleted
```

### 5.2 validate_invariants.py (→ `sdd.commands.validate_invariants`)

```bash
validate_invariants.py --phase N [--task T-NNN]
    # exit 0: {"ok": true, "phase": N, "results": [...]}
    # exit 1: {"ok": false, ...}
    # runs build.commands from project_profile.yaml; emits MetricRecorded events
```

### 5.3 query_events.py (→ `sdd.commands.query_events`)

```bash
query_events.py --phase N [--step T-NNN] [--event TYPE] [--include-bash] [--json] [--save]
    # exit 0: formatted output or JSON list of event records
```

### 5.4 report_error.py (→ `sdd.commands.report_error`)

```bash
report_error.py --type <ErrorType> --message "<msg>" [--task T-NNN]
    # exit 0: {"ok": true, "event_id": str}
    # exit 1: {"ok": false, "error": str}
    # side effects: ErrorEvent emitted (L1), SENARIncident written
```

### 5.5 record_metric.py (→ `sdd.commands.record_metric`)  *(v2 new, not in v1)*

```bash
record_metric.py --metric <id> --value <v> [--task T-NNN] [--phase N]
    # exit 0: {"ok": true}
    # side effects: MetricRecorded emitted to partition_key="metrics"
```

---

## 6. Out of Scope

The following are explicitly NOT governed by this compatibility spec:

| Item | Reason |
|------|--------|
| `.sdd/tools/` internal CLI flag names | Not a public API; Phase 8 thin adapters preserve CLI contract |
| L2/L3 event payload schemas | Telemetry/debug — allowed to evolve |
| `audit_log.jsonl` format | SENAR internal; v2 may replace with DB-backed audit |
| `State_index.yaml` YAML structure | Internal representation; not a replay artifact |
| `TaskSet_vN.md` markdown format | Internal; parser is part of governance layer |
| `metrics_report.py` output format | Report generation; schema may evolve |
| Phase/plan status transitions | Governed by §0.5 of CLAUDE.md; not a replay concern |
| `build_context.py` context format | Phase 2 artifact; not in Phase 0 scope |

---

## §PHASE-INV

Phase 0 has no implementation tasks. Its completion criterion is human approval of
this spec (moves `Draft → .sdd/specs/Spec_v0_Compatibility.md`).

Invariants that MUST hold across all subsequent phases:
- I-EL-4, I-EL-6: tested in `tests/compatibility/` (Phase 7 validation)
- All §3 invariants: produced incrementally by Phases 1–7

---

## Appendix A: v1 L1 Event Type Enumeration

```python
V1_L1_EVENT_TYPES = frozenset({
    "TaskImplemented",
    "TaskValidated",
    "PhaseCompleted",
    "TestRunCompleted",
    "StateDerivationCompleted",
    "ExecutionWrapperAccepted",
    "ExecutionWrapperRejected",
    "SDDEventRejected",
    "DecisionRecorded",
    "SpecApproved",
    "PlanActivated",
    "PhaseInitialized",
    "TaskFailed",
    "TaskRetryScheduled",
})
```

v2 MUST classify all of the above as L1.

## Appendix B: v1 Compatibility Fixture

`tests/compatibility/fixtures/v1_events.json` — extracted during bootstrap (Step 0.6)
from `sdd_v1/.sdd/state/sdd_events.duckdb`, L1 events only, `event_source="runtime"`
coercion applied. Used by `tests/compatibility/test_v1_schema.py` (T-120).
