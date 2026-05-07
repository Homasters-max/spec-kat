# Plan_v10 — Phase 10: Kernel Hardening

Status: ACTIVE
Spec: specs/Spec_v10_KernelHardening.md

---

## Milestones

### M1: CLI Execution Contract (BC-EXEC)

```text
Spec:       §2 BC-EXEC — CLI Execution Contract (all five paths + adapter ImportError)
BCs:        BC-EXEC
Invariants: I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1,
            I-ERR-CLI-1, I-EXEC-NO-CATCH-1
Depends:    — (first milestone; no phase predecessors required)
Risks:      I-ERR-1 dual-path interaction: CommandRunner MUST re-raise after
            writing ErrorEvent; if it swallows the exception BC-EXEC never fires
            JSON to stderr. Verify error_event_boundary + CommandRunner re-raise
            chain before writing tests (I-EXEC-NO-CATCH-1 / S-EXEC-1).
Tasks:      T-1001 (cli.py: _emit_json_error + 5-path main()),
            T-1002 (tests/unit/test_cli_exec_contract.py: 6 tests)
```

**T-1001** implements the five-path execution contract in `src/sdd/cli.py`:

| Path | Trigger | Exit |
|------|---------|------|
| SUCCESS | returns normally | 0 |
| KNOWN_ERR | `SDDError` raised | 1 (JSON stderr) |
| USAGE_ERR | `click.ClickException` raised | 1 (JSON stderr, no ErrorEvent) |
| UNEXPECTED | `Exception` raised | 2 (JSON stderr) |
| INSTALL_ERR | `ImportError` in adapter | 1 (JSON stderr from adapter) |

`_emit_json_error` is a private helper; JSON schema `{"error_type", "message", "exit_code"}`
is frozen (I-CLI-API-1). `click.ClickException` explicitly maps to exit 1, not 2
(I-USAGE-1); it never produces an ErrorEvent (I-ERR-CLI-1).

**T-1002** covers all six unit tests: success path, SDDError, unexpected Exception,
ClickException exit code, ClickException no-ErrorEvent, JSON schema field names.

---

### M2: Static Enforcement (BC-STATIC)

```text
Spec:       §2 BC-STATIC — Static Enforcement (I-LEGACY-0a/b, I-ENTRY-1)
BCs:        BC-STATIC
Invariants: I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1
Depends:    — (independent of M1; patterns reference execution model already
            declared in Spec but require no runtime output from M1)
Risks:      I-ENTRY-1 hook exclusion: src/sdd/hooks/log_tool.py and log_bash.py
            have legitimate __main__ blocks; the exclude list in project_profile.yaml
            MUST match exactly or the pattern produces spurious violations.
            I-LEGACY-0a regex must not match comment strings — verify pattern
            before committing to avoid false positives on doc strings.
Tasks:      T-1003 (.sdd/config/project_profile.yaml: three forbidden_patterns entries),
            T-1004 (src/sdd/commands/validate_invariants.py: --scope full-src dual-mode)
```

**T-1003** adds three `code_rules.forbidden_patterns` entries to `project_profile.yaml`:
`I-LEGACY-0a` (sys.path mutation toward .sdd/), `I-LEGACY-0b` (subprocess to .sdd/tools/),
`I-ENTRY-1` (__main__ block outside cli.py and hooks/). Severity: hard for all three.

**T-1004** extends `validate_invariants.py` with `--scope full-src` flag: when present,
the file set expands from Task Outputs only to all `src/sdd/**/*.py`. Default mode
(no flag) is behaviorally identical to Phase 9 — no breaking change (additive extension).

---

### M3: Kernel Contract Regression Suite (BC-REGRESS)

```text
Spec:       §2 BC-REGRESS — Kernel Contract Regression
BCs:        BC-REGRESS
Invariants: I-KERNEL-REG, I-KERNEL-SIG-1, I-REG-ENV-1
Depends:    — (targets frozen modules from Phase 8; independent of M1/M2)
Risks:      mypy --strict may surface pre-existing errors in frozen modules —
            if so, report as a Phase 10 pre-condition finding before proceeding.
            FROZEN_SIGNATURES baseline must be captured from the live codebase
            state (inspect.signature), not from memory; stale baselines defeat
            the regression purpose.
Tasks:      T-1005 (tests/regression/test_kernel_contract.py + pyproject.toml mypy dep)
```

**T-1005** produces three checks per each of the six frozen modules
(`core/types.py`, `core/events.py`, `infra/event_log.py`, `infra/event_store.py`,
`domain/state/reducer.py`, `domain/guards/context.py`):

1. `mypy --strict <path>` via subprocess (skip if mypy absent — I-REG-ENV-1)
2. `import sdd.<module>` — no exception at import time
3. `inspect.signature()` comparison against `FROZEN_SIGNATURES` dict (I-KERNEL-SIG-1)

`pyproject.toml` is updated to pin `mypy>=1.8` in `[project.optional-dependencies.dev]`.

---

### M4: Environment Independence & Integration Tests (BC-ENV + BC-INTEG)

```text
Spec:       §2 BC-ENV, BC-INTEG — Environment Independence + Cross-layer Integration
BCs:        BC-ENV, BC-INTEG
Invariants: I-ENV-1, I-ENV-2, I-ENV-BOOT-1, I-EXEC-ISOL-1, I-PURE-1, I-PURE-1a
Depends:    M1 (I-ENV-2 test exercises the adapter ImportError pattern from T-1001;
            CLI smoke tests require the 5-path contract to be in place)
Risks:      I-EXEC-ISOL-1: tests using the project sdd_events.duckdb constitute a
            hard invariant violation — every DB-touching test MUST use tmp_path.
            Level A smoke tests may be sensitive to installed sdd CLI version;
            run after pip install -e . is confirmed in the test environment.
            Purity test dual-patch must cover both module-level and inline imports
            of duckdb (I-PURE-1a) — single patch is insufficient.
Tasks:      T-1006 (tests/integration/test_env_independence.py: 2 tests),
            T-1007a (tests/integration/test_pipeline_smoke.py: 3 CLI smoke tests),
            T-1007b (tests/integration/test_pipeline_deterministic.py: 1 isolated DB test),
            T-1008 (tests/unit/infra/test_metrics_purity.py: 2 purity tests)
```

**T-1006** (BC-ENV): `test_sdd_help_minimal_env` runs `sdd --help` with minimal env
dict (PATH, HOME, VIRTUAL_ENV, LANG, LC_ALL only — no PYTHONPATH, no SDD_*);
`test_adapter_import_error_message` monkeypatches PYTHONPATH to break sdd resolution
and verifies JSON InstallError output from a Pattern B adapter (I-ENV-BOOT-1).

**T-1007a** (BC-INTEG Level A): `test_smoke_show_state` (exit 0, "phase" in stdout),
`test_smoke_report_error_exit_code` (exit 1 + JSON stderr), `test_smoke_unknown_command`
(UsageError JSON with exit_code 1). All via installed `sdd` CLI.

**T-1007b** (BC-INTEG Level B): `test_activate_phase_deterministic` — isolated DuckDB
at `tmp_path`, `CommandRunner.run(ActivatePhaseCommand(phase_id=99))`, two replays
produce identical state (determinism + I-EXEC-ISOL-1).

**T-1008** (BC-PURE): dual-patch on `sdd.infra.metrics.duckdb` and `duckdb.connect`
verifies `compute_trend()` and `detect_anomalies()` make zero I/O calls (I-PURE-1,
I-PURE-1a).

---

### M5: Documentation (BC-DOC)

```text
Spec:       §2 BC-DOC — Documentation Updates
BCs:        BC-DOC
Invariants: — (no machine-checkable invariants; human gate)
Depends:    M1, M2, M3, M4 (documentation must reflect the finalized implementation)
Risks:      T-1010 is explicitly a HUMAN TASK (manual sdd_plan.md edit outside SDD
            automation boundary); LLM marks it DONE only after human confirms the
            edit. §R split MUST preserve all existing strictness — content is
            reorganized, not relaxed.
Tasks:      T-1009 (CLAUDE.md: §R-core + §R-rules split; §0.16 Kernel Hardening Catalog),
            T-1010 (sdd_plan.md Phase Overview table — HUMAN TASK)
```

**T-1009** splits `CLAUDE.md §R` into two subsections without altering any rule:
`§R-core` (5 sdd CLI commands LLM uses every session) and `§R-rules` (scope/guard/
forbidden constraints relocated from §R). Adds `§0.16 Kernel Hardening Catalog` table:
all 18 Phase 10 invariants with verification method (test file + command).

**T-1010** updates `sdd_plan.md` Phase Overview table: Phases 0–9 COMPLETE, Phase 10
Kernel Hardening ACTIVE, Phase 11 Improvements & Integration, Phase 12 Self-hosted
Governance. **This is a human task.** LLM adds T-1010 to TaskSet as a coordination
placeholder; its DONE status requires human confirmation.

---

## Risk Notes

- **R-1: I-ERR-1 / BC-EXEC dual-path ordering** — `error_event_boundary` attaches
  `_sdd_error_events` and re-raises; `CommandRunner` writes to EventLog and re-raises;
  `cli.main()` terminates. Any intermediate catch-without-reraise breaks the chain
  (I-EXEC-NO-CATCH-1). Verify the full exception propagation path before writing
  T-1002 tests, or tests may pass against a broken implementation.

- **R-2: mypy --strict on frozen modules (T-1005)** — If `mypy --strict` reveals
  pre-existing type errors in frozen modules, those errors are a Phase 10 pre-condition
  defect, not a new task. Report via `report_error.py` and escalate to human before
  proceeding with the regression suite.

- **R-3: FROZEN_SIGNATURES baseline staleness** — The `FROZEN_SIGNATURES` dict in
  T-1005 must be populated from the *current* live signatures, not from memory. Capture
  via `inspect.signature()` at write time. A wrong baseline produces a test that always
  passes (or always fails).

- **R-4: I-EXEC-ISOL-1 test contamination** — Any DB-touching test that accidentally
  writes to `sdd_events.duckdb` corrupts the project state. All test authors must use
  `tmp_path` from pytest — failure is a hard invariant violation with no automatic
  recovery.

- **R-5: T-1010 human gate** — `sdd_plan.md` is outside SDD automation boundary. The
  task cannot be marked DONE by the LLM autonomously; it requires explicit human
  confirmation that the Phase Overview table has been updated.
