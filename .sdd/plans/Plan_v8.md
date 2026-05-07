# Plan_v8 — Phase 8: CLI + Kernel Stabilization

Status: ACTIVE
Spec: specs/Spec_v8_CLI.md

---

## Milestones

### M1: Package Bootstrap

```text
Spec:       §2.1 BC-CLI — pyproject.toml + __version__
BCs:        BC-CLI
Invariants: I-PKG-1
Depends:    — (Phase 7 COMPLETE)
Risks:      If pyproject.toml is malformed, pip install -e . fails and blocks M2+.
            Validate with `pip install -e . --dry-run` before committing.
```

Tasks:
- T-801: `pyproject.toml` (`[project.scripts]`, `[tool.pytest]`, `[tool.ruff]`,
  `[tool.mypy]`); `src/sdd/__init__.py` (`__version__ = "0.8.0"`)
- T-802: `tests/unit/test_package.py` (3 tests: importable, semver, entry point)

### M2: Command Extensions + CLI Router

```text
Spec:       §2.1 BC-CLI — show_state handler + main() wrappers + Click router
BCs:        BC-CLI, BC-CMD-EXT
Invariants: I-CLI-1, I-CLI-2, I-CLI-3, I-PKG-2
Depends:    M1 (pip install -e . must succeed; I-PKG-1 must hold)
Risks:      main() wrappers must preserve existing argv semantics. show_state
            applies State Guard — test against missing State_index.yaml.
            cli.py purity (I-CLI-1) enforced by AST check — no infra/domain imports.
```

Tasks:
- T-803: `src/sdd/commands/show_state.py` (NEW handler with State Guard); add `main()` to
  `update_state.py`, `validate_invariants.py`, `query_events.py`, `report_error.py`,
  `activate_phase.py`
- T-804: `src/sdd/cli.py` (Click router, 8 subcommands, `main()` entry point — no business
  logic, I-CLI-1)
- T-805: `tests/unit/test_cli.py` (10 tests: help, AST purity, exit codes ×3, routing ×3,
  CLI=main equivalence ×2)

### M3: Metrics Extension

```text
Spec:       §2.2 BC-METRICS-EXT — compute_trend / detect_anomalies
BCs:        BC-METRICS-EXT
Invariants: I-TREND-1, I-TREND-2, I-ANOM-1, I-ANOM-2
Depends:    M1 (package importable)
Risks:      Pure-function invariants (I-TREND-1, I-ANOM-1) verified by test_pure_no_io
            mocks. I-TREND-2 zero-value guard must prevent ZeroDivisionError.
            I-ANOM-2 zero-stdev guard must prevent ZeroDivisionError.
            DuckDB I/O must be fully isolated in load_metrics() — not in pure functions.
```

Tasks:
- T-806: `src/sdd/infra/metrics.py` — add `MetricRecord`, `TrendRecord`, `AnomalyRecord`,
  `load_metrics()`, `compute_trend()` (pure + epsilon guard), `detect_anomalies()` (pure +
  stdev==0 guard)
- T-807: `tests/unit/commands/test_metrics_report_enhanced.py` (10 tests: trend ×5 incl.
  zero-value, anomaly ×5 incl. zero-stdev)
- T-808: `src/sdd/commands/metrics_report.py` — add `--trend` flag (calls `compute_trend()`),
  `--anomalies` flag (calls `detect_anomalies()`), render to markdown table, update `main()`

### M4: Process Hardening

```text
Spec:       §2.4 BC-PROC — acceptance enforcement + sdd_config.yaml fields
BCs:        BC-PROC
Invariants: I-ACCEPT-1
Depends:    M2 (validate_invariants.py main() exists), M1 (package importable)
Risks:      Subprocess list API (no shell) is mandatory — prevents injection (§6 note).
            {outputs} expansion must match TaskSet Outputs field exactly.
            Acceptance check must BLOCK complete T-NNN, not just warn.
            validate_config.py --phase 8 must verify acceptance field presence.
```

Tasks:
- T-809: `.sdd/config/project_profile.yaml` (add `build.commands.acceptance`);
  `.sdd/config/sdd_config.yaml` (add `anomaly_zscore_threshold`, `trend_epsilon`);
  `src/sdd/commands/validate_invariants.py` (read acceptance field, expand `{outputs}`,
  subprocess ruff + pytest, block on non-zero exit)
- T-810: `tests/unit/commands/test_validate_invariants.py` (4 acceptance tests: runs,
  lint-block, test-block, outputs expansion)

### M5: Thin Adapters

```text
Spec:       §2.3 BC-ADAPT — Pattern A (CLI delegation) and Pattern B (direct import)
BCs:        BC-ADAPT
Invariants: I-ADAPT-1, I-ADAPT-2, I-ADAPT-3, I-ADAPT-4, I-HOOK-API-2
Depends:    M1 (pip install -e . done; sdd CLI available), M2 (all subcommands registered)
Risks:      Pattern A must pass through subprocess exit codes unchanged (I-ADAPT-4).
            Pattern B must catch ImportError only — non-import exceptions propagate (I-ADAPT-3).
            log_tool.py / log_bash.py: I-HOOK-API-2 requires positional argv warning (not fail).
            I-ADAPT-1: after replacement, grep -r "sys\.path" .sdd/tools/ must return empty.
            I-HOOK-PATH-1 superseded — sys.path injection block removed from log_tool.py.
```

Tasks:
- T-811: Pattern A adapters — `.sdd/tools/log_tool.py` (remove sys.path → Pattern B),
  `.sdd/tools/update_state.py`, `.sdd/tools/validate_invariants.py`,
  `.sdd/tools/query_events.py`, `.sdd/tools/metrics_report.py`,
  `.sdd/tools/report_error.py`, `.sdd/tools/sync_state.py`
- T-812: Pattern B adapters — `.sdd/tools/phase_guard.py`, `.sdd/tools/task_guard.py`,
  `.sdd/tools/check_scope.py`, `.sdd/tools/norm_guard.py`, `.sdd/tools/build_context.py`,
  `.sdd/tools/record_metric.py`, `.sdd/tools/senar_audit.py`, `.sdd/tools/log_bash.py`
- T-813: `tests/unit/test_adapters.py` (10 tests: grep no-syspath, deprecated comment,
  Pattern A/B structure, help parity ×3, structured error on import failure, exit passthrough,
  argv warning)

### M6: Documentation + Phase Validation

```text
Spec:       §2.4 BC-PROC (CLAUDE.md §0.15); §5 §PHASE-INV
BCs:        BC-PROC (documentation)
Invariants: I-KERNEL-EXT-1 (governance — human review gate)
Depends:    M1..M5 (all tasks done, all invariants PASS)
Risks:      §0.10 tools table entries must be marked [DEPRECATED — use sdd CLI].
            §0.12 hook section must note log_tool.py is now a Pattern B adapter.
            T-815 ValidationReport must confirm all 16 §PHASE-INV invariants PASS.
```

Tasks:
- T-814: `CLAUDE.md` — add `§0.15 Kernel Contract Freeze` table; mark §0.10 tools table
  entries `[DEPRECATED — use sdd CLI]`; update §0.12 hook section for Pattern B
- T-815: `.sdd/reports/ValidationReport_T-815.md` — §PHASE-INV coverage: all 16 invariants
  (I-PKG-1, I-PKG-2, I-CLI-1..3, I-ADAPT-1..4, I-TREND-1..2, I-ANOM-1..2, I-ACCEPT-1,
  I-HOOK-API-2, I-KERNEL-EXT-1) PASS

---

## Risk Notes

- R-1: **pip install -e . as a dependency gate.** M3, M4, M5 all require the `sdd` package
  to be installed. If M1 produces a broken `pyproject.toml`, all downstream milestones are
  blocked. Mitigation: T-801 must run `pip install -e .` as part of its validation and confirm
  `import sdd; sdd.__version__` works before marking DONE.

- R-2: **sys.path removal (I-ADAPT-1).** Removing the `sys.path` injection from
  `log_tool.py` (I-HOOK-PATH-1 supersession) means the hook immediately depends on the
  package being installed. If the hook fires before `pip install -e .` is run in a fresh
  environment, it will fail with ImportError. Mitigation: I-ADAPT-3 Pattern B error format
  gives a clear structured error; README should document `pip install -e .` as setup step.

- R-3: **Acceptance enforcement blocks task completion (I-ACCEPT-1).** The new acceptance
  gate in `validate_invariants.py` means any lint violation in task outputs blocks DONE.
  Tasks T-809+ must themselves pass `ruff check` on their outputs. Order: implement → lint
  → validate → complete. Do not mark DONE first.

- R-4: **I-CLI-1 AST purity check.** The `test_cli_is_pure_router` test uses AST inspection
  to verify no direct `sdd.infra.*`, `sdd.domain.*`, or `sdd.guards.*` imports in `cli.py`.
  Lazy imports inside function bodies (via `from sdd.commands.X import main`) are allowed.
  Mitigation: import all command handlers lazily inside the `@cli.command` function bodies.

- R-5: **Phases_index.md stale state.** Phase 7 is still shown as ACTIVE in Phases_index.md
  despite State_index.yaml showing phase.status = COMPLETE. This is a cleanup task for the
  human before marking Phase 8 ACTIVE. No automation should depend on Phases_index.md for
  Phase 7 completion status — the SSOT is State_index.yaml.
