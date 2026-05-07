# Spec_v8 — Phase 8: CLI + Kernel Stabilization

Status: Draft
Baseline: Spec_v7_Hardening.md (BC-CORE, BC-INFRA, BC-STATE, BC-GUARDS, BC-COMMANDS,
          BC-QUERY, BC-METRICS, BC-HOOKS)

---

## 0. Goal

Phase 8 completes the transition from the legacy `.sdd/tools/*.py` governance layer to the
`src/sdd/` Python package. Three parallel tracks:

1. **CLI layer** — `src/sdd/cli.py` (Click declarative router) + entry points in
   `pyproject.toml`. After `pip install -e .`, the `sdd` command routes all governance
   operations: `complete`, `validate`, `show-state`, `activate-phase`, `replay`,
   `query-events`, `metrics-report`, `report-error`. No business logic lives in `cli.py` —
   it is a pure adapter (D-5). Each existing `commands/*.py` module gains a `main()` entry
   point callable by the CLI.

2. **Thin adapters** — every `.sdd/tools/*.py` script is replaced by a one-liner delegate
   that calls the `sdd` CLI or imports from `src/sdd/` directly. The `sys.path` injection
   introduced in Phase 7 (D-13 deferral, I-HOOK-PATH-1) is removed. All `.sdd/tools/`
   files are marked `# DEPRECATED — use sdd CLI`. Claude Code `~/.claude/settings.json`
   requires no path changes: the hook still calls `.sdd/tools/log_tool.py`, which now
   delegates to the installed package without any `sys.path` hack.

3. **Metrics + Process hardening** — `metrics_report --trend` and `--anomalies` are
   implemented (Phase 7 §10 deferrals). `project_profile.yaml` gains a
   `build.commands.acceptance` field that enforces `ruff check {outputs} && pytest tests/ -q`
   per task, preventing the lint-deferral and interface-drift issues observed in Phase 7.
   `CLAUDE.md` is updated with a `§0.15 Kernel Contract Freeze` section.

After Phase 8, the three diagnostic questions from the kernel stabilization roadmap (§2) all
answer YES, the `sdd` CLI is the sole external entry point, and the project is ready for
Phase 9 integration work.

---

## 1. Scope

### In-Scope

- **BC-CLI** (new): `src/sdd/cli.py` — Click router; entry points in `pyproject.toml`;
  `commands/show_state.py` (new show-state handler); `main()` added to all existing
  `commands/*.py` that lack it
- **BC-METRICS-EXT**: `--trend` and `--anomalies` in `commands/metrics_report.py` backed by
  new `infra/metrics.py` functions `compute_trend()` and `detect_anomalies()`
- **BC-ADAPT**: all `.sdd/tools/*.py` → thin adapters (Pattern A or B); sys.path removed
- **BC-PROC**: `project_profile.yaml` acceptance criteria (I-ACCEPT-1); `CLAUDE.md` §0.15
  kernel freeze section

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### §2.1 BC-CLI: Package Install + CLI Layer

```
pyproject.toml                      ← add [project.scripts] + [tool.*] config
src/sdd/__init__.py                 ← add __version__ = "0.8.0"
src/sdd/cli.py                      ← Click router — NO business logic (I-CLI-1)
src/sdd/commands/show_state.py      ← show-state handler (NEW)
src/sdd/commands/update_state.py    ← add main()
src/sdd/commands/validate_invariants.py  ← add main()
src/sdd/commands/query_events.py    ← add main()
src/sdd/commands/report_error.py    ← add main()
src/sdd/commands/activate_phase.py  ← add main()
src/sdd/commands/metrics_report.py  ← add main() + --trend/--anomalies flags (§2.2)
```

**pyproject.toml entry points:**

```toml
[project.scripts]
sdd = "sdd.cli:main"
```

After `pip install -e .`, the `sdd` command is available system-wide. Development workflow:

```bash
pip install -e .
sdd --help
sdd complete T-801
sdd validate T-801
sdd show-state
```

**cli.py contract (I-CLI-1):** Pure adapter — Click command registration + one-line dispatch
to the corresponding `commands/*.main()`. No infra, domain, or guards imports. No conditional
logic. No state reads. No event emission.

```python
# Illustrative structure — NOT full implementation
import click, sys

@click.group()
@click.version_option(package_name="sdd")
def cli() -> None:
    """SDD — Spec-Driven Development governance CLI."""

@cli.command("complete")
@click.argument("task_id")
def complete(task_id: str) -> None:
    """Mark task T-NNN as DONE."""
    from sdd.commands.update_state import main
    sys.exit(main(["complete", task_id]))

@cli.command("show-state")
def show_state() -> None:
    """Print current State_index.yaml as a markdown table."""
    from sdd.commands.show_state import main
    sys.exit(main([]))

# ... one @cli.command per governance operation (see §2.1 table)

def main() -> None:
    cli()
```

**Full command table (Phase 8):**

| CLI command | Handler | Notes |
|-------------|---------|-------|
| `sdd complete T-NNN` | `commands/update_state.main(["complete", "T-NNN"])` | |
| `sdd validate T-NNN [--result PASS\|FAIL]` | `commands/update_state.main(["validate", ...])` | |
| `sdd show-state` | `commands/show_state.main([])` | NEW |
| `sdd activate-phase N` | `commands/activate_phase.main(["N"])` | Phase 5 cmd |
| `sdd replay [--phase N]` | `commands/query_events.main(["--replay", ...])` | |
| `sdd query-events [args...]` | `commands/query_events.main([...])` | pass-through |
| `sdd metrics-report [--phase N] [--trend] [--anomalies]` | `commands/metrics_report.main([...])` | |
| `sdd report-error --type T --message M` | `commands/report_error.main([...])` | |

### §2.2 BC-METRICS-EXT: Trend + Anomaly Analysis

```
src/sdd/infra/metrics.py    ← add compute_trend(), detect_anomalies(), AnomalyRecord, TrendRecord
src/sdd/commands/metrics_report.py  ← add --trend / --anomalies flags; call new functions
```

**load_metrics** (all DuckDB I/O isolated here):

```python
def load_metrics(metric_ids: list[str], window: int = 10) -> list[MetricRecord]:
    """Queries DuckDB metrics partition; returns last `window` phases per metric_id, ASC."""
```

**compute_trend** computes inter-phase deltas — truly pure, no I/O:

```python
def compute_trend(records: list[MetricRecord]) -> list[TrendRecord]:
    """
    I-TREND-1: pure function — no I/O, no DuckDB.
    Input: MetricRecord list from load_metrics().
    delta = None for the oldest phase per metric.
    direction: "↑" if delta/value > 0.05; "↓" if < -0.05; "→" otherwise.
    I-TREND-2: if abs(value) < trend_epsilon (default 1e-9, configurable) → direction "→".
    Returns [] if records is empty.
    """
```

**detect_anomalies** flags statistical outliers — truly pure, no I/O:

```python
def detect_anomalies(
    records: list[MetricRecord],
    threshold: float = 2.0,
) -> list[AnomalyRecord]:
    """
    I-ANOM-1: pure function — no I/O, no DuckDB.
    Input: MetricRecord list from load_metrics().
    Returns [] if fewer than 3 data points per metric_id.
    I-ANOM-2: returns [] if stdev == 0.
    zscore = (value - mean) / stdev (statistics.stdev, sample).
    threshold overridable via sdd_config.yaml anomaly_zscore_threshold.
    """
```

`metrics_report --trend` calls `load_metrics` then `compute_trend`; renders as markdown table.
`metrics_report --anomalies` calls `load_metrics` then `detect_anomalies`; appends anomaly section.
Both flags are independent and combinable. `load_metrics` is called once per flag combination.

**--trend table format:**

```
| Phase | Metric              | Value  | Delta   | Dir |
|-------|---------------------|--------|---------|-----|
| 6     | task.lead_time      | 1250ms | —       | →   |
| 7     | task.lead_time      | 980ms  | -270ms  | ↓   |
```

**--anomalies section format:**

```
### Anomalies (threshold: 2.0σ)

| Phase | Metric              | Value  | z-score |
|-------|---------------------|--------|---------|
| 7     | quality.lint_violations | 4 | +2.41 |
```

### §2.3 BC-ADAPT: Thin Adapters

After `pip install -e .`, every `.sdd/tools/*.py` script uses one of two patterns.

**Pattern A — CLI delegation** (for scripts with corresponding `sdd` subcommands):

```python
#!/usr/bin/env python3
# DEPRECATED — use 'sdd <command>' after pip install -e .
import subprocess, sys
code = subprocess.call(["sdd", "<command>"] + sys.argv[1:])
sys.exit(code)
```

**Pattern B — Direct import** (for scripts used as guards, hooks, or without CLI equivalent):

```python
#!/usr/bin/env python3
# DEPRECATED — use sdd.<module> after pip install -e .
try:
    from sdd.<module> import main
except ImportError as e:
    import sys, json
    sys.stderr.write(
        json.dumps({"error": "SDD_IMPORT_FAILED", "message": str(e)}) + "\n"
    )
    sys.exit(2)

if __name__ == "__main__":
    main()
```

| Script | Pattern | Delegates to |
|--------|---------|-------------|
| `update_state.py` | A | `sdd complete` / `sdd validate` |
| `validate_invariants.py` | A | `sdd validate` (full validate mode) |
| `query_events.py` | A | `sdd query-events` |
| `metrics_report.py` | A | `sdd metrics-report` |
| `report_error.py` | A | `sdd report-error` |
| `sync_state.py` | A | `sdd sync-state` (Phase 9 candidate; stays as-is for now) |
| `log_tool.py` | B | `sdd.hooks.log_tool.main` |
| `log_bash.py` | B | `sdd.hooks.log_tool.main` (backward-compat; legacy Bash hook) |
| `phase_guard.py` | B | `sdd.guards.phase` module |
| `task_guard.py` | B | `sdd.guards.task` module |
| `check_scope.py` | B | `sdd.guards.scope` module |
| `norm_guard.py` | B | `sdd.guards.norm` module |
| `build_context.py` | B | `sdd.context.build_context.main` |
| `record_metric.py` | B | `sdd.infra.metrics.record_metric_cli` |
| `senar_audit.py` | B | `sdd.infra.audit.audit_cli` |

**I-ADAPT-1:** After replacing all scripts, `grep -r "sys\.path" .sdd/tools/` must return no
matches. Each file's first non-shebang line must be the `# DEPRECATED` comment.

**I-HOOK-PATH-1 supersession:** Phase 8 removes the `sys.path` injection block from
`.sdd/tools/log_tool.py`. I-HOOK-PATH-1's `parents[2]` clause no longer applies. The hook
still fires via `python3 .sdd/tools/log_tool.py`; it now delegates via Pattern B. No change
to `~/.claude/settings.json` is required.

### §2.4 BC-PROC: Process Hardening

**project_profile.yaml — new acceptance field:**

```yaml
build:
  commands:
    lint:       ruff check src/
    typecheck:  mypy src/sdd/
    test:       pytest tests/ -q
    acceptance: "ruff check {outputs} && pytest tests/ -q"   # NEW
```

`sdd_config.yaml` gains two new fields (Phase 8 defaults):

```yaml
anomaly_zscore_threshold: 2.0    # existing — now formally declared
trend_epsilon: 1.0e-9            # NEW — I-TREND-2 division guard
```

`validate_invariants.py --task T-NNN` now performs an acceptance check as a pre-condition
before the task may be marked DONE:

1. Read task T-NNN `Outputs:` field (list of file paths)
2. Run: `subprocess.run(["ruff", "check", *outputs])` — NO shell expansion, no injection risk
3. Run: `subprocess.run(["pytest", "tests/", "-q"])` — always full suite
4. Both must exit 0; if either fails → emit structured error, STOP — task stays TODO

Note: the `acceptance` field in `project_profile.yaml` is a human-readable template only.
Actual execution uses subprocess list API — `{outputs}` is never passed to a shell.

This closes the Phase 7 regression pattern: auto-fixable lint violations in task outputs
were discovered at T-710 (phase validation) instead of at the task level. With I-ACCEPT-1,
any new violation in task outputs blocks `complete T-NNN` immediately.

**CLAUDE.md — §0.15 Kernel Contract Freeze (new section):**

Phase 8 adds §0.15 to CLAUDE.md documenting the frozen kernel interfaces:

| Module | Frozen surface |
|--------|---------------|
| `core/types.py` | `Command`, `CommandHandler` Protocol |
| `core/events.py` | `DomainEvent` base fields, `EventLevel`, `classify_event_level()` |
| `infra/event_log.py` | `sdd_append()`, `sdd_append_batch()`, `sdd_replay()` signatures |
| `infra/event_store.py` | `EventStore.append()` interface |
| `domain/state/reducer.py` | `reduce()` signature + I-REDUCER-1 filter contract |
| `domain/guards/context.py` | `GuardContext`, `GuardResult`, `GuardOutcome` |

Not frozen (free to evolve): DuckDB implementation, reducer logic, guard pipeline
composition, command handler internals, projections, CLI layer.

§0.10 Tools table updated: all `.sdd/tools/` entries marked `[DEPRECATED — use sdd CLI]`.
§0.12 hook section updated: note that `.sdd/tools/log_tool.py` is now a Pattern B adapter.

### §2.5 Dependencies

```
BC-CLI        → BC-CMD-EXT      cli.py imports commands/*.main()
BC-CMD-EXT    → Phase 5..7 cmd  adds main() wrappers to existing handlers
BC-METRICS-EXT → infra/metrics.py  compute_trend / detect_anomalies new functions
BC-ADAPT      → BC-CLI          Pattern A adapters subprocess-call sdd CLI
BC-ADAPT      → pip install -e . precondition: package must be installed
BC-PROC       → BC-CMD-EXT      validate_invariants.py reads acceptance + runs ruff/pytest
```

---

## 3. Domain Events

No new domain events are introduced in Phase 8.

CLI layer events (`CLICommandStarted`, `CLICommandCompleted`) are deferred to Phase 9 —
insufficient integration coverage to justify them before Phase 9 integration tests exist.

`log_bash.py` Pattern B wrapper reuses existing `ToolUseStarted` / `ToolUseCompleted`
event types (delegated to `log_tool.main()`). No new registration needed.

### C-1 Compliance (Phase 8)

No new `event_type` strings. C-1 invariant holds without change.
`register_l1_event_type` remains available for Phase 9 use.

---

## 4. Types & Interfaces

### 4.0 MetricRecord (`infra/metrics.py`)

```python
@dataclass(frozen=True)
class MetricRecord:
    phase: int
    metric_id: str
    value: float
    # All fields hashable — I-PK-4 compatibility
```

### 4.0b load_metrics (`infra/metrics.py`)

```python
def load_metrics(metric_ids: list[str], window: int = 10) -> list[MetricRecord]:
    """
    All DuckDB I/O is here — NOT in compute_trend or detect_anomalies.
    Queries metrics partition ordered by (metric_id, phase) ASC.
    Returns last `window` phases per metric_id.
    Returns [] for unknown metric_ids.
    """
```

`metrics_report` command flow:
```python
records = load_metrics(metric_ids, window)
trends   = compute_trend(records)
anomalies = detect_anomalies(records, threshold=threshold)
```

### 4.1 TrendRecord (`infra/metrics.py`)

```python
@dataclass(frozen=True)
class TrendRecord:
    phase: int
    metric_id: str
    value: float
    delta: float | None   # None for the first phase in the window
    direction: str        # "↑" | "↓" | "→"
    # All fields hashable — I-PK-4 compatibility
```

### 4.2 AnomalyRecord (`infra/metrics.py`)

```python
@dataclass(frozen=True)
class AnomalyRecord:
    phase: int
    metric_id: str
    value: float
    zscore: float
```

### 4.3 compute_trend (`infra/metrics.py`)

```python
def compute_trend(records: list[MetricRecord]) -> list[TrendRecord]:
    """
    I-TREND-1: truly pure function — no I/O, no DuckDB, no randomness.
    Input: pre-loaded MetricRecord list from load_metrics().
    Returns records ordered by (metric_id, phase) ASC.
    delta=None for the oldest phase in each metric's window.
    direction threshold: if abs(value) < trend_epsilon (sdd_config.yaml, default 1e-9)
      → "→" (I-TREND-2, no division); else abs(delta/value) > 0.05 → ↑/↓; else →.
    Returns [] if records is empty.
    """
```

### 4.4 detect_anomalies (`infra/metrics.py`)

```python
def detect_anomalies(
    records: list[MetricRecord],
    threshold: float = 2.0,
) -> list[AnomalyRecord]:
    """
    I-ANOM-1: truly pure function — no I/O, no DuckDB, no randomness.
    Input: pre-loaded MetricRecord list from load_metrics().
    Returns [] if fewer than 3 data points per metric_id.
    Returns [] if stdev == 0 (all values identical) — I-ANOM-2.
    zscore uses statistics.stdev (sample, ddof=1).
    threshold default overridable via sdd_config.yaml anomaly_zscore_threshold.
    """
```

### 4.5 CLI main (`src/sdd/cli.py`)

```python
def main() -> None:
    """Click entry point — called by 'sdd' command after pip install."""
    cli()
```

`cli` is a `click.Group`. Each subcommand is a `@cli.command` with ≤ 5 lines body.

### 4.6 show_state main (`commands/show_state.py`)

```python
def main(args: list[str] | None = None) -> int:
    """
    Reads State_index.yaml, renders as markdown table to stdout.
    Applies State Guard before reading.
    Returns 0 on success, 1 on MissingState or Inconsistency.
    """
```

---

## 5. Invariants

### New Invariants (Phase 8)

| ID | Statement | Enforced by |
|----|-----------|-------------|
| I-PKG-1 | After `pip install -e .`, `python -c "import sdd; print(sdd.__version__)"` exits 0 and prints a semver string. | `tests/unit/test_package.py` — `test_package_importable`, `test_version_string_is_semver` |
| I-PKG-2 | After `pip install -e .`, `sdd --help` exits 0 and its output contains all 8 subcommand names: `complete`, `validate`, `show-state`, `activate-phase`, `replay`, `query-events`, `metrics-report`, `report-error`. | `tests/unit/test_cli.py` — `test_help_lists_all_commands` |
| I-CLI-1 | `src/sdd/cli.py` MUST NOT directly import from `sdd.infra.*`, `sdd.domain.*`, or `sdd.guards.*`. Imports from `sdd.commands.*`, `click`, and `sys` are allowed. Transitive imports via `commands.*` are permitted. No function in `cli.py` exceeds 6 lines. | `tests/unit/test_cli.py` — `test_cli_is_pure_router` (AST check: no direct infra/domain/guards import nodes in cli.py top-level or function bodies) |
| I-CLI-2 | `sdd <command>` exits 0 on success; exits 1 on validation failure (known, structured error); exits 2 on unexpected exception. | `tests/unit/test_cli.py` — `test_exit_code_success`, `test_exit_code_validation_failure`, `test_exit_code_unexpected_error` |
| I-ADAPT-1 | After `pip install -e .`, `grep -r "sys\.path" .sdd/tools/` returns no matches. Each `.sdd/tools/*.py` file starts with the `# DEPRECATED` comment immediately after the shebang. | `tests/unit/test_adapters.py` — `test_no_syspath_in_adapters` (grep), `test_deprecated_comment_present` |
| I-ADAPT-2 | For `update_state.py`, `query_events.py`, and `metrics_report.py` (Pattern A adapters): `python3 .sdd/tools/X.py --help` and `sdd X --help` produce identical output modulo leading process-path tokens. | `tests/unit/test_adapters.py` — `test_update_state_help_parity`, `test_query_events_help_parity`, `test_metrics_report_help_parity` |
| I-TREND-1 | `compute_trend(records: list[MetricRecord])` is a truly pure function (no I/O, no DuckDB, no randomness). Given ≥ 2 phases of input records: returns a `TrendRecord` per `(metric_id, phase)` pair ordered by phase ASC; the first phase in each metric's window has `delta=None`; all subsequent have `delta = value_N − value_(N-1)`; `direction` is one of `{"↑", "↓", "→"}`. All DuckDB I/O is in `load_metrics()`, not here. | `tests/unit/commands/test_metrics_report_enhanced.py` — `test_trend_two_phases`, `test_trend_first_phase_delta_none`, `test_trend_direction_up_down_flat`, `test_trend_pure_no_io` |
| I-ANOM-1 | `detect_anomalies(records: list[MetricRecord], ...)` is a truly pure function (no I/O, no DuckDB, no randomness). Returns `[]` if fewer than 3 data points per metric_id. For ≥ 3 points: flags any value where `abs(zscore) > threshold` (default 2.0). `zscore = (value − mean) / stdev` using `statistics.mean` / `statistics.stdev`. All DuckDB I/O is in `load_metrics()`, not here. | `tests/unit/commands/test_metrics_report_enhanced.py` — `test_anomaly_empty_below_3_points`, `test_anomaly_detected_above_2sigma`, `test_anomaly_not_detected_within_2sigma`, `test_anomaly_pure_no_io` |
| I-ACCEPT-1 | `project_profile.yaml` defines `build.commands.acceptance: "ruff check {outputs} && pytest tests/ -q"`. `validate_invariants.py --task T-NNN` expands `{outputs}` to the space-joined list of task output paths and runs this command. Both `ruff check` (on task outputs only) and `pytest` must exit 0 before `update_state.py complete T-NNN` is permitted. A failing acceptance check emits a structured error and STOPS execution. | `tests/unit/commands/test_validate_invariants.py` — `test_acceptance_command_runs`, `test_acceptance_blocks_done_on_lint_failure`, `test_acceptance_blocks_done_on_test_failure`, `test_outputs_expansion` |
| I-ADAPT-3 | Pattern B adapters MUST catch `ImportError` and fail with a structured JSON error on stderr and exit code 2. Non-import exceptions (e.g. `SyntaxError`, `RuntimeError`) MUST propagate normally. Stderr format: `{"error": "SDD_IMPORT_FAILED", "message": "<str(e)>"}`. | `tests/unit/test_adapters.py` — `test_pattern_b_structured_error_on_import_failure` |
| I-ADAPT-4 | Pattern A adapters MUST pass through the subprocess exit code unchanged via `sys.exit(code)`. Adapter MUST NOT mask or swallow subprocess exit code. | `tests/unit/test_adapters.py` — `test_pattern_a_exit_code_passthrough` |
| I-CLI-3 | For every `sdd` subcommand, CLI invocation and direct `main(args)` invocation MUST produce the same exit code and the same event types emitted (same sequence of L1 event type strings; metadata fields such as `timestamp`, `pid`, `seq` are excluded from comparison). | `tests/unit/test_cli.py` — `test_cli_vs_main_equivalence_complete`, `test_cli_vs_main_equivalence_show_state` |
| I-TREND-2 | `compute_trend` MUST NOT perform division when `abs(value) < 1e-9`. In that case `direction` MUST be `"→"`. This prevents ZeroDivisionError and avoids false signals when the base metric is near zero. | `tests/unit/commands/test_metrics_report_enhanced.py` — `test_trend_direction_zero_value` |
| I-ANOM-2 | `detect_anomalies` MUST return `[]` when `stdev == 0` (all values in window are identical). This prevents ZeroDivisionError during zscore computation. | `tests/unit/commands/test_metrics_report_enhanced.py` — `test_anomaly_empty_on_zero_stdev` |
| I-HOOK-API-2 | If `sys.argv` contains any positional arguments when the hook adapter is invoked, the hook MUST emit a warning to stderr, then continue processing stdin normally. The hook MUST NOT fail due to positional argv. Silent argv ignore is forbidden. | `tests/unit/test_adapters.py` — `test_hook_warns_on_positional_argv` |
| I-KERNEL-EXT-1 | **[Governance invariant — manual enforcement]** Frozen interfaces (§8 Kernel Contract Freeze table) MAY be extended only with: (a) optional parameters with default values, (b) new backward-compatible return fields. Changes to positional arguments, parameter order, or required parameters constitute a breaking change and require a new spec and human approval. | Human review gate at PR merge — no automated test |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-HOOK-WIRE-1 | `.sdd/tools/log_tool.py` contains no `sdd_append` call (AST-verified); all logic in `src/sdd/hooks/log_tool.py` |
| I-HOOK-PARITY-1 | Both hook entry points produce identical EventLog rows for same stdin fixture |
| I-HOOK-API-1 | Hook ignores positional argv; only stdin JSON is valid protocol (Phase 7 T-711) |
| I-REDUCER-1 | `EventReducer.reduce()` discards non-runtime / non-L1 events before dispatch |
| I-REG-1 | `register_l1_event_type` is the sole registration path for L1 types |
| C-1 | `V1_L1_EVENT_TYPES` in sync with `_EVENT_SCHEMA ∪ _KNOWN_NO_HANDLER` |
| I-EL-9 | All DuckDB writes go through `sdd_append` — no direct `duckdb.connect` outside `infra/db.py` |

**Note on I-HOOK-PATH-1 supersession:** I-ADAPT-1 supersedes I-HOOK-PATH-1 for
`.sdd/tools/log_tool.py`. After Phase 8, the `sys.path` injection block (and thus the
`parents[2]` path resolution) is deleted. I-HOOK-PATH-1 is archived as resolved.

### §PHASE-INV (must ALL be PASS before Phase 8 can be COMPLETE)

```
[I-PKG-1,
 I-PKG-2,
 I-CLI-1,
 I-CLI-2,
 I-CLI-3,
 I-ADAPT-1,
 I-ADAPT-2,
 I-ADAPT-3,
 I-ADAPT-4,
 I-TREND-1,
 I-TREND-2,
 I-ANOM-1,
 I-ANOM-2,
 I-ACCEPT-1,
 I-HOOK-API-2,
 I-KERNEL-EXT-1]
```

---

## 6. Pre/Post Conditions

### pip install -e . (precondition for Phase 8 tasks T-803+)

**Pre:**
- `pyproject.toml` has valid `[build-system]`, `[project]`, `[project.scripts]` sections
- `src/sdd/__init__.py` defines `__version__`

**Post:**
- `sdd` command available on PATH
- `import sdd` succeeds without `sys.path` manipulation
- I-PKG-1 holds

### sdd \<command\> invocation

**Pre:**
- `sdd` installed on PATH (I-PKG-1)
- State_index.yaml exists (State Guard passes) for state-modifying commands

**Post:**
- Exit 0 on success; command-specific output to stdout
- Exit 1 on known validation failure (MissingState, Inconsistency, etc.); error to stderr
- Exit 2 on unexpected exception; stack trace to stderr

### validate_invariants --task T-NNN (with acceptance enforcement)

**Pre:**
- `project_profile.yaml` `build.commands.acceptance` field is present
- Task T-NNN has a non-empty `Outputs:` field in TaskSet_vN.md

**Post:**
- `subprocess.run(["ruff", "check", *outputs])` runs; exit non-0 → ERROR (I-ACCEPT-1 violation) → STOP
- `subprocess.run(["pytest", "tests/", "-q"])` runs; exit non-0 → ERROR (I-ACCEPT-1 violation) → STOP
- Both checks pass → validation proceeds normally
- `update_state.py complete T-NNN` is NOT called if acceptance fails
- Shell is never invoked; output paths are passed as subprocess list arguments (no injection risk)

### load_metrics contract

**Pre:**
- DuckDB metrics partition accessible (read-only)
- `metric_ids` is a non-empty list of metric ID strings

**Post:**
- Returns `list[MetricRecord]` ordered by (metric_id, phase) ASC
- Returns `[]` for unknown metric_ids (no error)
- No writes to DuckDB or any file

### compute_trend (pure function contract)

**Pre:**
- Input is `list[MetricRecord]` (already loaded — no I/O precondition)

**Post:**
- No I/O of any kind; no randomness
- If < 2 phases of input: returns list with all `delta=None`
- If ≥ 2 phases: first phase has `delta=None`; all subsequent have computed delta
- Direction "→" when `delta` is None or when `abs(value) < trend_epsilon` (I-TREND-2)

### detect_anomalies (pure function contract)

**Pre:**
- Input is `list[MetricRecord]` (already loaded — no I/O precondition)

**Post:**
- No I/O of any kind; no randomness
- Returns `[]` if fewer than 3 data points per metric_id
- Returns `[]` if `stdev == 0` (I-ANOM-2)
- For ≥ 3 points with non-zero stdev: returns one `AnomalyRecord` per outlier value

---

## 7. Use Cases

### UC-8-1: Governance via CLI (primary Phase 8 workflow)

**Actor:** LLM implementing a task
**Trigger:** Task T-NNN implementation complete
**Pre:** `pip install -e .` done; `sdd` on PATH; task outputs written; I-ACCEPT-1 in force
**Steps:**
1. `sdd validate T-801` → `validate_invariants.py` runs acceptance: `ruff check {outputs}` + `pytest`
2. Both exit 0 → validation report written
3. `sdd complete T-801` → TaskCompleted + MetricRecorded emitted (I-M-1)
4. State_index.yaml updated via `update_state.py`
**Post:** T-801 status = DONE; EventLog records TaskImplemented; no lint violations possible

### UC-8-2: Thin adapter backward compatibility

**Actor:** Legacy invocation (human or CI calling `.sdd/tools/update_state.py`)
**Trigger:** `python3 .sdd/tools/update_state.py complete T-801`
**Pre:** `pip install -e .` done; `update_state.py` is Pattern A adapter
**Steps:**
1. Script: `subprocess.call(["sdd", "complete", "T-801"])`
2. `sdd complete T-801` executes normally
**Post:** Identical behavior to direct CLI call; I-ADAPT-2 satisfied

### UC-8-3: Hook delegation after pip install (no sys.path)

**Actor:** Claude Code runtime
**Trigger:** `PreToolUse` fires; `python3 .sdd/tools/log_tool.py pre` called via settings.json
**Pre:** `pip install -e .` done; `log_tool.py` is Pattern B adapter
**Steps:**
1. `.sdd/tools/log_tool.py`: `from sdd.hooks.log_tool import main; main()`
2. No `sys.path` manipulation (I-ADAPT-1)
3. `src/sdd/hooks/log_tool.py` reads stdin JSON, emits ToolUseStarted (I-HOOK-WIRE-1)
**Post:** EventLog entry written; identical to Phase 7 behavior

### UC-8-4: Per-task acceptance enforcement (Phase 7 regression prevention)

**Actor:** LLM after implementing T-NNN
**Trigger:** `sdd validate T-NNN`
**Pre:** T-NNN outputs written; I-ACCEPT-1 active
**Steps:**
1. Read T-NNN `Outputs: [src/sdd/cli.py, pyproject.toml]`
2. Run: `ruff check src/sdd/cli.py pyproject.toml` — must exit 0
3. Run: `pytest tests/ -q` — must exit 0
4. Both pass → `sdd complete T-NNN` allowed
5. If ruff finds violations → STOP; fix before DONE
**Post:** No task marked DONE with lint violations or test failures in its outputs (I-ACCEPT-1)

### UC-8-5: Metrics trend report during phase summary

**Actor:** LLM executing Summarize Phase 8
**Trigger:** `sdd metrics-report --phase 8 --trend --anomalies`
**Pre:** ≥ 2 phases of metric data in DuckDB metrics partition
**Steps:**
1. `compute_trend(["task.lead_time", "quality.test_coverage", "quality.lint_violations"])`
2. `detect_anomalies(["task.lead_time", "quality.lint_violations"])`
3. Render trend table + anomaly section → `Metrics_Phase8.md`
**Post:** I-TREND-1 and I-ANOM-1 satisfied; Phase8_Summary.md references Metrics_Phase8.md

### UC-8-6: Kernel contract freeze verification

**Actor:** Phase 9 LLM checking whether a proposed change is allowed
**Trigger:** Considering a change to `infra/event_log.py sdd_replay()` signature
**Pre:** CLAUDE.md §0.15 exists with frozen interface list
**Steps:**
1. Read §0.15 — `infra/event_log.py sdd_replay()` is in the frozen list
2. Proposed change = breaking change to frozen interface → requires new spec + human approval
3. LLM refuses implementation without spec change
**Post:** Kernel stability preserved; no silent interface drift

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-CLI → Phase 5..7 commands | this → | cli.py imports `main()` from each command module |
| BC-METRICS-EXT → infra/metrics.py | this → | `compute_trend` / `detect_anomalies` read DuckDB |
| BC-ADAPT → BC-CLI | .sdd/tools/ → | Pattern A adapters subprocess-call `sdd` CLI |
| BC-PROC → BC-CMD-EXT | validate_invariants → | acceptance field enforcement uses task Outputs |
| BC-PROC → infra/metrics.py | metrics_report → | `--trend`/`--anomalies` call new functions |

### Backward Compatibility

- `.sdd/tools/*.py` Pattern A adapters preserve the same CLI interface via delegation —
  existing callers (CI scripts, Makefile) continue to work
- Pattern B adapters call `main()` of the delegated module — same behavior
- `build.commands.acceptance` is a NEW key in `project_profile.yaml`; existing code that
  does not read this key is unaffected; `validate_config.py --phase 8` gains a check for
  it being present
- `TrendRecord` / `AnomalyRecord` are new types — no existing callers

### Kernel Contract Freeze (§0.15 additions to CLAUDE.md)

Phase 8 freezes the following public interfaces (I-KERNEL-EXT-1: non-breaking extensions —
new optional parameters with default values, or new backward-compatible return fields — are
allowed; changes to positional arguments, parameter order, or required parameters require a
new spec and human approval):

| Module | Frozen surface |
|--------|---------------|
| `core/types.py` | `Command` dataclass fields; `CommandHandler` Protocol |
| `core/events.py` | `DomainEvent` base fields; `EventLevel`; `classify_event_level()` |
| `infra/event_log.py` | `sdd_append()`, `sdd_append_batch()`, `sdd_replay()` signatures |
| `infra/event_store.py` | `EventStore.append()` interface |
| `domain/state/reducer.py` | `reduce()` signature; I-REDUCER-1 filter contract |
| `domain/guards/context.py` | `GuardContext`, `GuardResult`, `GuardOutcome` |

Not frozen (may evolve per phase spec): DuckDB schema internals, reducer handler logic,
guard pipeline composition, command handler implementations, projections, CLI layer.

---

## 9. Verification

| # | Test File | Key Tests | Invariant(s) |
|---|-----------|-----------|--------------|
| 1 | `tests/unit/test_package.py` | `test_package_importable`, `test_version_string_is_semver`, `test_entry_point_registered` | I-PKG-1, I-PKG-2 |
| 2 | `tests/unit/test_cli.py` | `test_help_lists_all_commands` (subprocess `sdd --help`), `test_cli_is_pure_router` (AST: no infra/domain/guards import nodes), `test_exit_code_success`, `test_exit_code_validation_failure`, `test_exit_code_unexpected_error`, `test_complete_routes_to_update_state`, `test_query_events_pass_through_args`, `test_show_state_registered`, `test_cli_vs_main_equivalence_complete`, `test_cli_vs_main_equivalence_show_state` | I-PKG-2, I-CLI-1, I-CLI-2, I-CLI-3 |
| 3 | `tests/unit/test_adapters.py` | `test_no_syspath_in_adapters` (grep all .sdd/tools/*.py), `test_deprecated_comment_present`, `test_log_tool_is_pattern_b`, `test_update_state_is_pattern_a`, `test_update_state_help_parity`, `test_query_events_help_parity`, `test_metrics_report_help_parity`, `test_pattern_b_structured_error_on_import_failure`, `test_pattern_a_exit_code_passthrough`, `test_hook_warns_on_positional_argv` | I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-ADAPT-4, I-HOOK-API-2 |
| 4 | `tests/unit/commands/test_metrics_report_enhanced.py` | `test_trend_two_phases`, `test_trend_first_phase_delta_none`, `test_trend_direction_up_down_flat`, `test_trend_pure_no_io`, `test_trend_direction_zero_value`, `test_anomaly_empty_below_3_points`, `test_anomaly_detected_above_2sigma`, `test_anomaly_not_detected_within_2sigma`, `test_anomaly_pure_no_io`, `test_anomaly_empty_on_zero_stdev` | I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2 |
| 5 | `tests/unit/commands/test_validate_invariants.py` | `test_acceptance_command_runs`, `test_acceptance_blocks_done_on_lint_failure`, `test_acceptance_blocks_done_on_test_failure`, `test_outputs_expansion` (verify `{outputs}` substitution) | I-ACCEPT-1 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| CLI events (`CLICommandStarted`, `CLICommandCompleted`) in EventLog | Phase 9 |
| I-REG-STATIC-1 runtime enforcement (replay-start sentinel) | Phase 9 |
| Projection caching with invalidation | Phase 9 |
| `sdd_replay(level=None, include_expired=True)` full debug path | Phase 9 |
| I-EL-8 `caused_by_meta_seq` enforcement beyond schema presence | Phase 9 |
| Compatibility tests: v2 API against v1 EventLog fixture (I-EL-4) | Phase 9 |
| EventLog migration seeding (import Phase 1..7 events into v2 DB) | Phase 9 |
| Removing `.sdd/tools/*.py` entirely (after Phase 9 integration tests pass) | Phase 10 |
| `sdd norm-check`, `sdd norm-list` CLI subcommands | Phase 9 |
| `sync_state.py` → `sdd sync-state` CLI command (no Phase 8 handler exists) | Phase 9 |
| I-ACCEPT-2: pytest failure attribution by task output scope (warn vs block based on file coverage) | Phase 9 |
| I-REPLAY-1: snapshot-based replay optimization to avoid O(N) full replay at scale | Phase 9 |

---

## Appendix: Task Breakdown (~15 tasks)

| Task | Outputs | Produces Invariants | Requires Invariants |
|------|---------|---------------------|---------------------|
| T-801 | `pyproject.toml` (`[project.scripts]`, `[tool.pytest]`, `[tool.ruff]`, `[tool.mypy]`), `src/sdd/__init__.py` (`__version__ = "0.8.0"`) | I-PKG-1 | I-PK-1 |
| T-802 | `tests/unit/test_package.py` (3 tests: importable, semver, entry point) | — | I-PKG-1 |
| T-803 | `src/sdd/commands/show_state.py` (NEW handler), add `main()` to `update_state.py`, `validate_invariants.py`, `query_events.py`, `report_error.py`, `activate_phase.py` | I-CLI-2 (exit codes via handlers) | I-ST-3 (show_state reads State_index), all Phase 4–7 command invariants |
| T-804 | `src/sdd/cli.py` (Click router, 8 subcommands, no logic, `main()` entry point) | I-CLI-1, I-CLI-3, I-PKG-2 | I-PKG-1, T-803 (all `main()` functions must exist) |
| T-805 | `tests/unit/test_cli.py` (10 tests: help, AST purity, exit codes ×3, routing ×3, CLI=main equivalence ×2) | — | I-CLI-1, I-CLI-2, I-CLI-3, I-PKG-2 |
| T-806 | `src/sdd/infra/metrics.py` (+`MetricRecord`, +`TrendRecord`, +`AnomalyRecord`, +`load_metrics()` with DuckDB I/O, +`compute_trend(records)` pure with epsilon guard, +`detect_anomalies(records)` pure with stdev==0 guard) | I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2 | I-EL-9 (only load_metrics reads DuckDB; compute_trend and detect_anomalies are pure) |
| T-807 | `tests/unit/commands/test_metrics_report_enhanced.py` (10 tests: trend ×5 incl. zero-value, anomaly ×5 incl. zero-stdev) | — | I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2 |
| T-808 | `src/sdd/commands/metrics_report.py` (+`--trend` flag calling `compute_trend()`, +`--anomalies` flag calling `detect_anomalies()`, render to markdown, `main()` updated) | I-TREND-1, I-ANOM-1 (cmd side) | I-TREND-1, I-ANOM-1 (infra side, T-806) |
| T-809 | `.sdd/config/project_profile.yaml` (+`build.commands.acceptance`), `src/sdd/commands/validate_invariants.py` (read acceptance field, expand `{outputs}`, run ruff+pytest, block if fails) | I-ACCEPT-1 | I-PK-4 (pure config read) |
| T-810 | `tests/unit/commands/test_validate_invariants.py` (+4 acceptance tests: runs, lint-block, test-block, expansion) | — | I-ACCEPT-1 |
| T-811 | `.sdd/tools/log_tool.py` (remove sys.path → Pattern B with I-ADAPT-3 guard), `.sdd/tools/update_state.py`, `.sdd/tools/validate_invariants.py`, `.sdd/tools/query_events.py`, `.sdd/tools/metrics_report.py`, `.sdd/tools/report_error.py`, `.sdd/tools/sync_state.py` (Pattern A adapters with I-ADAPT-4 exit passthrough) | I-ADAPT-1, I-ADAPT-3 (Pattern B), I-ADAPT-4 (Pattern A) | I-PKG-1 |
| T-812 | `.sdd/tools/phase_guard.py`, `.sdd/tools/task_guard.py`, `.sdd/tools/check_scope.py`, `.sdd/tools/norm_guard.py`, `.sdd/tools/build_context.py`, `.sdd/tools/record_metric.py`, `.sdd/tools/senar_audit.py`, `.sdd/tools/log_bash.py` (Pattern B adapters with I-ADAPT-3 guard + I-HOOK-API-2 for log_tool/log_bash) | I-ADAPT-1 (Pattern B set), I-HOOK-API-2 | I-PKG-1 |
| T-813 | `tests/unit/test_adapters.py` (10 tests: grep no-syspath, deprecated comment, Pattern A/B structure ×2, help parity ×3, I-ADAPT-3 structured error, I-ADAPT-4 exit passthrough, I-HOOK-API-2 argv warning) | — | I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-ADAPT-4, I-HOOK-API-2 |
| T-814 | `CLAUDE.md` (+`§0.15 Kernel Contract Freeze` table; §0.10 tools table marked `[DEPRECATED]`; §0.12 hook section updated for Pattern B) | (process) | all T-801..T-813 |
| T-815 | `.sdd/reports/ValidationReport_T-815.md` (§PHASE-INV coverage: all 9 invariants PASS) | — | all T-801..T-814 |
