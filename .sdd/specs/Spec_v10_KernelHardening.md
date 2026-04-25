# Spec_v10 — Phase 10: Kernel Hardening

Status: Draft
Baseline: Spec_v8_CLI.md (BC-CLI, BC-METRICS-EXT, BC-ADAPT, BC-PROC)

---

## 0. Goal

Phase 8 freezes kernel interfaces and declares `I-KERNEL-EXT-1`. Phase 10 **proves** those
declarations hold: it adds machine-checkable regression tests for all six frozen modules,
formalizes the entire CLI execution surface as a first-class Bounded Context (BC-EXEC — all
execution paths: success, known error, unexpected, usage error, install error, test isolation),
and enforces entry-point discipline via static analysis.

The central architectural insight of this phase: execution paths (error/success/env/test) are
not scattered implementation details — they are a first-class specification contract.
BC-EXEC makes every path explicit, testable, and immutable for downstream phases.

After Phase 10 the kernel is *verified*, not just declared. Phase 11 (Improvements &
Integration) may build new features on top with confidence that regressions will be caught
automatically.

---

## 1. Scope

### In-Scope

- **BC-EXEC** (new): CLI Execution Contract — all five execution paths formalized as a
  first-class BC; success path; I-ERR-1 dual-path interaction; test DB isolation
- **BC-STATIC** (new): Static Enforcement — I-LEGACY-0a/b (two distinct patterns), I-ENTRY-1
  with hook exclusion; `validate_invariants.py` dual-mode (`--scope full-src`)
- **BC-REGRESS** (new): Kernel Contract Regression Suite — `mypy --strict` + import smoke for
  six frozen modules; graceful skip if mypy absent
- **BC-ENV** (new): Environment Independence — subprocess test with minimal env dict
- **BC-INTEG** (new): Cross-layer Integration Tests — Level A (CLI smoke) + Level B
  (domain determinism, isolated DB)
- **BC-DOC**: `CLAUDE.md §R` split (§R-core + §R-rules); §0.16 Kernel Hardening Catalog;
  `sdd_plan.md` Phase Overview table update

### Out of Scope

See §10.

---

## 2. Architecture / BCs

### BC-EXEC: CLI Execution Contract

**Motivation:** The original draft (BC-HARNESS) specified only the error paths. Success path,
usage-error path, and test-isolation rules were unspecified — invisible to the LLM and not
machine-verifiable. BC-EXEC makes all five paths a first-class specification.

#### Execution Contract Table

| Path | Trigger | Handler clause | Exit code | Stderr |
|------|---------|---------------|-----------|--------|
| SUCCESS | command returns normally | `sys.exit(result or 0)` | 0 | empty |
| KNOWN_ERR | `SDDError` raised | `except SDDError` | 1 | JSON |
| UNEXPECTED | `Exception` raised (non-SDDError, non-Click) | `except Exception` | 2 | JSON |
| USAGE_ERR | `click.ClickException` raised | `except click.ClickException` | 1 | JSON |
| INSTALL_ERR | `ImportError` in adapter | adapter `except ImportError` | 1 | JSON |

#### Exit Code Semantics (S-EXEC-EXIT-1)

Exit code is **not** a full error classifier:

| Exit code | Meaning |
|-----------|---------|
| 0 | SUCCESS |
| 1 | Any expected failure (KNOWN_ERR or USAGE_ERR) |
| 2 | Truly unexpected failure (UNEXPECTED) |

`KNOWN_ERR` and `USAGE_ERR` are **intentionally indistinguishable** at the exit-code level.
The `error_type` field in the JSON stderr payload is the **sole discriminator** between expected
failure classes. Shell scripts check `[ $? -ne 0 ]` for any failure; structured consumers parse
JSON stderr for classification.

`USAGE_ERR` maps to exit 1 (not 2) because `click.ClickException` is a predictable user-input
error, semantically equivalent to `SDDError`. Exit 2 is reserved for truly unexpected failures.

#### Implementation — `cli.py` `main()` (T-1001)

```python
import sys
import json
import click
from sdd.core.errors import SDDError


def _emit_json_error(error_type: str, message: str, exit_code: int) -> None:
    json.dump({"error_type": error_type, "message": message, "exit_code": exit_code},
              sys.stderr)
    sys.stderr.write("\n")


def main(args: list[str] | None = None) -> None:
    try:
        result = cli(standalone_mode=False, args=args)
        sys.exit(result or 0)                              # SUCCESS path
    except SDDError as e:
        _emit_json_error(type(e).__name__, str(e), 1)
        sys.exit(1)                                        # KNOWN_ERR path
    except click.ClickException as e:
        _emit_json_error("UsageError", e.format_message(), 1)
        sys.exit(1)                                        # USAGE_ERR path
    except Exception as e:                                 # noqa: BLE001
        _emit_json_error("UnexpectedException", str(e), 2)
        sys.exit(2)                                        # UNEXPECTED path
```

`I-CLI-1` (cli.py = pure router) is preserved: `_emit_json_error` is a private infrastructure
helper, not domain logic. The `cli` Click group and command registrations remain untouched.

#### I-ERR-1 Interaction (dual-path, both fire)

`error_event_boundary` (Phase 4, I-ERR-1) intercepts exceptions BEFORE BC-EXEC:

```
command.handle()
  └── error_event_boundary catches exc
      ├── attaches exc._sdd_error_events = [ErrorEvent(...)]
      └── re-raises

CommandRunner catches re-raised exc
  ├── writes ErrorEvent to EventLog via EventStore
  └── re-raises

BC-EXEC main() catches re-raised exc (last resort)
  └── emits JSON to stderr, sys.exit(1|2)
```

BC-EXEC **MUST NOT** suppress the exception before I-ERR-1 fires. `CommandRunner` MUST
re-raise after writing to EventLog. This is a hard constraint: both paths (EventLog write
and JSON stderr) fire for the same exception.

**`click.ClickException` and I-ERR-1 (I-ERR-CLI-1):** `ClickException` never passes through
`error_event_boundary` — it is raised by the Click framework at the routing layer, before any
command handler executes. Therefore it produces **no ErrorEvent**. This is by design:
`ClickException` is a CLI usage error, not a domain error. I-ERR-1 applies exclusively to
`SDDError` and its subclasses (I-ERR-CLI-1).

#### Single Ownership Rule (S-EXEC-1)

Each layer owns **exactly one** responsibility and MUST NOT suppress the exception
(except the terminal `BC-EXEC main()`):

| Layer | Responsibility | Constraint |
|-------|---------------|------------|
| `error_event_boundary` (I-ERR-1) | Attach `exc._sdd_error_events` | MUST re-raise |
| `CommandRunner` | Write ErrorEvent to EventLog (DB persist) | MUST re-raise after write |
| `BC-EXEC main()` | JSON serialization + `sys.exit` | Terminal — absorbs exception |

Violation: if `CommandRunner` catches without re-raise → BC-EXEC never sees the exception →
JSON stderr lost. If `error_event_boundary` suppresses → event never attached → I-ERR-1 fails.
No refactor may introduce a catch-without-reraise in any intermediate layer (I-EXEC-NO-CATCH-1).

#### Test Isolation Rule (I-EXEC-ISOL-1)

No integration or deterministic test may write to or read from the project's production
`sdd_events.duckdb`. All tests requiring a DB MUST use pytest's `tmp_path` fixture to
create an isolated DuckDB at a temporary path. This rule applies to T-1007a, T-1007b, and
all future integration tests.

#### INSTALL_ERR path — adapter pattern (I-ENV-2)

Each `.sdd/tools/*.py` Pattern B adapter MUST guard the import with structured JSON output
(consistent with I-CLI-API-1 — I-ENV-BOOT-1):

```python
try:
    from sdd.commands.X import main
except ImportError:
    import sys, json
    json.dump(
        {"error_type": "InstallError",
         "message": "sdd package not found — run: pip install -e .",
         "exit_code": 1},
        sys.stderr,
    )
    sys.stderr.write("\n")
    sys.exit(1)
```

---

### BC-STATIC: Static Enforcement

Two new `code_rules.forbidden_patterns` entries in `project_profile.yaml` (T-1003):

```yaml
# I-LEGACY-0a — sys.path manipulation toward .sdd/
- pattern: 'sys\.path\s*(\.append|\.insert|\[).*\.sdd'
  applies_to: "src/sdd/**/*.py"
  severity: hard
  message: "I-LEGACY-0a: sys.path manipulation toward .sdd/ is forbidden in src/sdd"

# I-LEGACY-0b — subprocess calls to .sdd/tools/ scripts
- pattern: 'subprocess.*\.sdd[/\\\\]tools'
  applies_to: "src/sdd/**/*.py"
  severity: hard
  message: "I-LEGACY-0b: direct subprocess invocation of .sdd/tools/ is forbidden"

# I-ENTRY-1 — no __main__ blocks except cli.py and hooks
- pattern: 'if __name__ == ["\x27]__main__["\x27]'
  applies_to: "src/sdd/**/*.py"
  exclude:
    - "src/sdd/cli.py"
    - "src/sdd/hooks/log_tool.py"
    - "src/sdd/hooks/log_bash.py"
  severity: hard
  message: "I-ENTRY-1: direct module execution forbidden; use sdd CLI (hooks are exempt)"
```

**I-LEGACY-0 split rationale:** The original pattern `from .sdd.tools` was a Python relative
import syntax that can never appear in `src/sdd/` (`.sdd/tools/` is not a Python package).
The two actual violation patterns are: (a) `sys.path` injection to reach `.sdd/` scripts, and
(b) `subprocess` calls to `.sdd/tools/*.py`. These are distinct risks requiring distinct
grep patterns.

**I-LEGACY-0a pattern note:** The pattern `sys\.path\s*(\.append|\.insert|\[).*\.sdd` targets
mutation calls only. Strings like `"sys.path hack for .sdd docs"` in comments will not match.
If the pattern produces a false positive, the relevant line MUST be reviewed manually before
suppressing — no auto-suppress.

**I-ENTRY-1 hook exclusion rationale:** `src/sdd/hooks/log_tool.py` and `log_bash.py` are
invoked directly by the Claude Code hook system (`~/.claude/settings.json` `PreToolUse` /
`PostToolUse`). Their `if __name__ == "__main__"` blocks are legitimate entry points by
architectural design, not legacy violations.

`validate_invariants.py` is extended (T-1004) with a `--scope full-src` mode that checks
all `src/sdd/**/*.py` for these patterns — not just task outputs:

```bash
python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0a --scope full-src
python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0b --scope full-src
python3 .sdd/tools/validate_invariants.py --check I-ENTRY-1 --scope full-src
```

**Dual-mode contract:**

| Mode | Invocation | File set checked | Output schema |
|------|-----------|-----------------|---------------|
| Default | `validate_invariants.py --check I-XXX` | Task Outputs only (existing contract) | unchanged |
| Full-src | `validate_invariants.py --check I-XXX --scope full-src` | All `src/sdd/**/*.py` | identical format |

The `--scope full-src` flag is additive: existing CI/CD invocations without the flag are
unaffected. No behavioral change to the default mode. No new output fields.

---

### BC-REGRESS: Kernel Contract Regression

Six frozen modules (from Spec_v8 §0.15 — authoritative source):

```
src/sdd/core/types.py            ← Command, CommandHandler Protocol
src/sdd/core/events.py           ← DomainEvent base, EventLevel, classify_event_level()
src/sdd/infra/event_log.py       ← sdd_append(), sdd_append_batch(), sdd_replay()
src/sdd/infra/event_store.py     ← EventStore.append() interface
src/sdd/domain/state/reducer.py  ← reduce() + I-REDUCER-1 filter contract
src/sdd/domain/guards/context.py ← GuardContext, GuardResult, GuardOutcome
```

**Explicitly NOT frozen** (from Spec_v8 §0.15): DuckDB internals, reducer handler logic,
guard pipeline composition (`guards/runner.py`), command handler internals, CLI layer.
`guards/runner.py` is not in the regression suite.

Regression test (T-1005) runs three checks per frozen module:

1. `mypy --strict <module_path>` via subprocess — zero errors = PASS
2. `import sdd.core.types` etc. — no exception at import time = PASS
3. `inspect.signature(<fn>)` comparison against a baseline captured at freeze time — signature
   unchanged = PASS (I-KERNEL-SIG-1)

**Signature inspection (I-KERNEL-SIG-1):** The test file includes a `FROZEN_SIGNATURES` dict
capturing the expected `inspect.Signature` for each public function in the six frozen modules.
If a function is renamed, its args change, or its return annotation changes, the test fails.
This is cheaper than snapshot tests and defeats the "just update the snapshot" failure mode.

**mypy availability:** if the `mypy` binary is not found on `$PATH`, the test calls
`pytest.skip("mypy not installed — add to [project.optional-dependencies.dev]")`.
`pyproject.toml` is updated (T-1005) to pin mypy in `[project.optional-dependencies.dev]`:

```toml
[project.optional-dependencies]
dev = ["mypy>=1.8", "pytest-cov"]
```

No JSON snapshot comparison — snapshot tests create "just update the snapshot" behavior
that defeats the regression purpose.

---

### BC-ENV: Environment Independence

Subprocess test with minimal explicit env dict (T-1006):

```python
import os, subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

def test_sdd_help_minimal_env():
    env = {
        k: os.environ[k]
        for k in ("PATH", "HOME", "VIRTUAL_ENV", "LANG", "LC_ALL")
        if k in os.environ
    }
    # Explicitly absent: PYTHONPATH, SDD_*, any project-specific vars
    result = subprocess.run(
        ["sdd", "--help"], env=env, cwd=PROJECT_ROOT, capture_output=True
    )
    assert result.returncode == 0

def test_adapter_import_error_message(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))  # breaks sdd package resolution
    # Import any Pattern B adapter; expect ImportError caught and structured JSON
    result = subprocess.run(
        ["python3", ".sdd/tools/update_state.py", "--help"],
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stderr)          # I-ENV-BOOT-1: must be valid JSON
    assert payload["error_type"] == "InstallError"
    assert "pip install -e ." in payload["message"]   # I-ENV-2
    assert payload["exit_code"] == 1
```

**I-ENV-1 env dict note:** Only keys present in the host environment are forwarded; absent keys
are silently skipped rather than raising `KeyError`. `VIRTUAL_ENV`, `LANG`, `LC_ALL` are
optional on some systems; their absence must not fail the test setup.

---

### BC-INTEG: Cross-layer Integration Tests

Two levels, kept in separate test files (a flaky CLI test never blocks a domain test):

**Level A — CLI Smoke (T-1007a):** three commands dispatched through the installed `sdd` CLI.

```python
# tests/integration/test_pipeline_smoke.py
def test_smoke_show_state(sdd_cli_runner):
    result = sdd_cli_runner(["show-state"])
    assert result.returncode == 0
    assert "phase" in result.stdout.lower()

def test_smoke_report_error_exit_code(sdd_cli_runner):
    result = sdd_cli_runner(["report-error", "--type", "SmokeTest", "--message", "x"])
    assert result.returncode == 1  # known SDDError path
    assert result.stderr  # JSON present

def test_smoke_unknown_command(sdd_cli_runner):
    result = sdd_cli_runner(["unknown-subcommand"])
    assert result.returncode == 1          # USAGE_ERR path — I-USAGE-1
    payload = json.loads(result.stderr)
    assert payload["error_type"] == "UsageError"
    assert payload["exit_code"] == 1
```

**Level B — Domain Determinism (T-1007b):** Command → EventLog → State, no CLI layer.

```python
# tests/integration/test_pipeline_deterministic.py
def test_activate_phase_deterministic(tmp_path):
    db = tmp_path / "test_events.duckdb"   # ISOLATED — never the project DB
    runner = CommandRunner(db_path=str(db))
    runner.run(ActivatePhaseCommand(phase_id=99, actor="test"))  # phase_id=99 avoids collision
    state1 = reduce(sdd_replay(db_path=str(db)))
    state2 = reduce(sdd_replay(db_path=str(db)))
    assert state1 == state2                # I-EXEC-ISOL-1 + determinism
```

Note: `phase_id=99` is used to avoid any collision with real project phases.
**The `tmp_path` fixture is mandatory** — using the project's `sdd_events.duckdb` constitutes
an I-EXEC-ISOL-1 violation.

---

### BC-DOC: Documentation

`CLAUDE.md §R` is split into two subsections (content preserved, zero strictness lost):

**§R-core** — "What to do" (LLM reads every session, 5 commands):
```
sdd complete T-NNN      → mark task DONE after implementation
sdd validate T-NNN      → run invariant checks after implementation
sdd show-state          → read current phase/task state
sdd query-events        → inspect event log
sdd report-error        → structured error reporting
```

**§R-rules** — "What not to do" (invariants + constraints, relocated not modified):
```
Scope rules, single-task rule, idempotency, forbidden patterns, PhaseGuard, StateGuard
```

Add **§0.16 Kernel Hardening Catalog** — one table listing all Phase 10 invariants with
verification method (test file + command).

`sdd_plan.md` Phase Overview table is updated (T-1010) to reflect current reality:
Phases 0–9 COMPLETE, Phase 10 Kernel Hardening ACTIVE,
Phase 11 Improvements & Integration (was 10), Phase 12 Self-hosted Governance (was 11).

---

## 3. Domain Events

No new domain events in Phase 10. All changes are infrastructure (tests, static analysis,
CLI boundary). The `ErrorEvent` schema is frozen from Phase 4 (D-7).

---

## 4. Types & Interfaces

No new public types. `_emit_json_error` is a private helper in `cli.py` — not exported,
not part of the frozen interface.

JSON error schema (I-CLI-API-1 — process invariant, not snapshot):

```json
{
  "error_type": "string",
  "message":    "string",
  "exit_code":  1 | 2
}
```

Field names `error_type`, `message`, `exit_code` are frozen. Modification requires a new
Spec version and a breaking-change annotation. This is a **process invariant** — the test
`test_cli_json_schema_fields` validates the *current* output shape; "no change between
versions" is enforced by spec review, not the test itself.

---

## 5. Invariants

### New Invariants

| ID | Statement | Verified by |
|----|-----------|-------------|
| I-FAIL-1 | CLI exit 1 (SDDError) and exit 2 (Exception) MUST produce `{"error_type","message","exit_code"}` JSON to stderr | T-1002 |
| I-USAGE-1 | `click.ClickException` MUST produce JSON to stderr with `exit_code: 1` (not 2) | T-1002 |
| I-EXEC-SUCCESS-1 | CLI success path MUST call `sys.exit(result or 0)` — never implicit exit | T-1002 |
| I-CLI-API-1 | JSON error fields `error_type`, `message`, `exit_code` are frozen (process invariant — spec-gated change only) | T-1002, spec review |
| I-ERR-CLI-1 | `click.ClickException` MUST NOT produce ErrorEvent — CLI usage errors are not domain errors; I-ERR-1 applies only to `SDDError` and its subclasses | T-1002, spec review |
| I-EXEC-NO-CATCH-1 | No layer between `CommandRunner` and `BC-EXEC main()` may catch `SDDError` or `Exception` without re-raising; only `cli.main()` may terminate exception flow | S-EXEC-1 (Single Ownership Rule), code review |
| I-ENV-1 | `sdd --help` succeeds from project root with minimal env dict (no PYTHONPATH) | T-1006 |
| I-ENV-2 | Any `.sdd/tools/*.py` adapter ImportError MUST output "run pip install -e ." message to stderr | T-1006 |
| I-ENV-BOOT-1 | Adapter ImportError output MUST be structured JSON matching I-CLI-API-1 schema (`error_type`, `message`, `exit_code`) — no plain-text fallback | T-1006 |
| I-LEGACY-0a | No `sys.path` mutation (`.append`, `.insert`, or subscript assignment) toward `.sdd/` in `src/sdd/**/*.py` | T-1003/T-1004, grep |
| I-LEGACY-0b | No `subprocess` calls to `.sdd/tools/` scripts in `src/sdd/**/*.py` | T-1003/T-1004, grep |
| I-ENTRY-1 | No `if __name__ == "__main__"` in `src/sdd/**/*.py` except `cli.py` and `hooks/*.py` | T-1003/T-1004, grep |
| I-KERNEL-REG | Six frozen modules (Spec_v8 §0.15) pass `mypy --strict` + import-time smoke | T-1005 |
| I-KERNEL-SIG-1 | Public function signatures of frozen modules (Spec_v8 §0.15) MUST NOT change (function name + positional args + return type); append-only compatible extensions only | T-1005 (signature inspection), spec review |
| I-REG-ENV-1 | Regression suite (T-1005) runs against the pinned dev toolchain (`mypy>=1.8` from `[project.optional-dependencies.dev]`); no dependency on system-level mypy state outside the venv | T-1005, pyproject.toml |
| I-PURE-1 | `compute_trend()` and `detect_anomalies()` in `infra/metrics.py` make zero I/O calls | T-1008 |
| I-PURE-1a | No `import duckdb` inside function bodies in `sdd/infra/metrics.py`; duckdb usage MUST be at module level only | T-1008, grep |
| I-EXEC-ISOL-1 | Integration and deterministic tests MUST use `tmp_path`-isolated DuckDB; project `sdd_events.duckdb` is never touched by tests | T-1007b, pytest fixture |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-CLI-1 | `cli.py` is a pure router — no domain/infra imports at module level (Phase 8) |
| I-CLI-2 | SDDError → exit 1; unexpected exception → exit 2 (Phase 8) |
| I-CLI-3 | CLI invocation and direct `main()` invocation produce same exit code + same L1 event types (Phase 8) |
| I-ERR-1 | Any exception in `handle()` emits ErrorEvent before propagating (Phase 4) |
| I-KERNEL-EXT-1 | Frozen interfaces: no breaking changes; new fields append-only (Phase 8) |
| I-EL-9 | All DB writes through `sdd_append` — no direct `duckdb.connect` outside `infra/db.py` (Phase 1) |
| I-TREND-1/2 | `compute_trend` is pure (no I/O, no randomness); same input → same output (Phase 8) |

---

## 6. Pre/Post Conditions

### CLI invocation (any command)

**Pre:**
- `pip install -e .` has been run (virtualenv active)
- `sdd --help` returns exit 0 (I-ENV-1)
- Project root is cwd

**Post (success):**
- exit code 0
- stderr empty
- I-ERR-1 not triggered (no exception)

**Post (on SDDError):**
- exit code 1
- stderr contains valid JSON matching I-CLI-API-1 schema with `exit_code: 1`
- ErrorEvent written to EventLog (I-ERR-1)
- No partial state written (I-CMD-1 idempotency preserved)

**Post (on ClickException):**
- exit code 1
- stderr contains valid JSON matching I-CLI-API-1 schema with `exit_code: 1`
- **No ErrorEvent written** — `ClickException` is not a domain error (I-ERR-CLI-1)
- No partial state written

**Post (on unexpected Exception):**
- exit code 2
- stderr contains valid JSON matching I-CLI-API-1 schema with `exit_code: 2`
- ErrorEvent written to EventLog (I-ERR-1)

---

## 7. Use Cases

### UC-10-1: CLI invoked with unknown subcommand

**Actor:** LLM or human
**Trigger:** `sdd unknown-subcommand`
**Pre:** `sdd` installed
**Steps:**
1. Click dispatch raises `click.UsageError` (subclass of `click.ClickException`)
2. BC-EXEC `except click.ClickException` clause fires
3. `_emit_json_error("UsageError", e.format_message(), 1)` writes JSON to stderr
4. `sys.exit(1)`
**Post:** `{"error_type": "UsageError", "message": "...", "exit_code": 1}` on stderr; exit 1; no ErrorEvent (I-ERR-CLI-1)

### UC-10-2: Adapter invoked without package installed

**Actor:** `.sdd/tools/log_tool.py` hook
**Trigger:** hook fires before `pip install -e .`
**Steps:**
1. `from sdd.commands.log_tool import main` raises `ImportError`
2. Adapter `except ImportError` emits JSON: `{"error_type": "InstallError", "message": "sdd package not found — run: pip install -e .", "exit_code": 1}`
3. `sys.exit(1)`
**Post:** `{"error_type": "InstallError", ...}` on stderr (I-ENV-2, I-ENV-BOOT-1); exit 1

### UC-10-3: Kernel regression check

**Actor:** CI / human
**Trigger:** `pytest tests/regression/test_kernel_contract.py`
**Steps:**
1. Test checks if `mypy` binary is available; if not → `pytest.skip(...)`
2. Test runs `mypy --strict` on each of the six frozen modules via subprocess
3. Test imports each frozen module (smoke)
4. Test compares `inspect.signature()` against `FROZEN_SIGNATURES` baseline
5. All pass → exit 0
**Post:** I-KERNEL-REG PASS, I-KERNEL-SIG-1 PASS

### UC-10-4: CLI command succeeds normally

**Actor:** LLM executing `sdd show-state`
**Trigger:** `sdd show-state`
**Steps:**
1. Click dispatches to `show_state.main([])`
2. Handler reads State_index.yaml, returns 0
3. `cli(standalone_mode=False)` returns `0`
4. `sys.exit(0 or 0)` = `sys.exit(0)`
**Post:** exit 0; stderr empty (I-EXEC-SUCCESS-1)

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-CLI (Phase 8) | this extends | `cli.py` `main()` gains execution contract; I-CLI-1 preserved |
| BC-PROC (Phase 8) | this extends | I-LEGACY-0a/b, I-ENTRY-1 added to `project_profile.yaml` |
| BC-COMMANDS (Phase 4) | referenced | `error_event_boundary` (I-ERR-1) fires before BC-EXEC boundary |
| BC-METRICS-EXT (Phase 8) | referenced | `compute_trend`, `detect_anomalies` targeted by I-PURE-1 |

### No Reducer Extensions

Phase 10 adds no new event handlers. The reducer is not modified.

---

## 9. Verification

| # | Test | File | Invariant(s) |
|---|------|------|--------------|
| 1 | `test_success_path_exit_zero` | `tests/unit/test_cli_exec_contract.py` | I-EXEC-SUCCESS-1 |
| 2 | `test_sdd_error_json_stderr_exit_1` | `tests/unit/test_cli_exec_contract.py` | I-FAIL-1, I-CLI-API-1 |
| 3 | `test_unexpected_exception_json_stderr_exit_2` | `tests/unit/test_cli_exec_contract.py` | I-FAIL-1, I-CLI-API-1 |
| 4 | `test_click_exception_exit_1_not_2` | `tests/unit/test_cli_exec_contract.py` | I-USAGE-1, I-CLI-API-1 |
| 5 | `test_click_exception_no_error_event` | `tests/unit/test_cli_exec_contract.py` | I-ERR-CLI-1 |
| 6 | `test_cli_json_schema_fields` | `tests/unit/test_cli_exec_contract.py` | I-CLI-API-1 |
| 7 | `test_sdd_help_minimal_env` | `tests/integration/test_env_independence.py` | I-ENV-1 |
| 8 | `test_adapter_import_error_message` | `tests/integration/test_env_independence.py` | I-ENV-2, I-ENV-BOOT-1 |
| 9 | `test_frozen_modules_mypy_strict` | `tests/regression/test_kernel_contract.py` | I-KERNEL-REG, I-REG-ENV-1 |
| 10 | `test_frozen_modules_import_smoke` | `tests/regression/test_kernel_contract.py` | I-KERNEL-REG |
| 11 | `test_frozen_modules_signatures` | `tests/regression/test_kernel_contract.py` | I-KERNEL-SIG-1 |
| 12 | `test_smoke_show_state` | `tests/integration/test_pipeline_smoke.py` | I-EXEC-SUCCESS-1 |
| 13 | `test_smoke_report_error_exit_code` | `tests/integration/test_pipeline_smoke.py` | I-FAIL-1 |
| 14 | `test_smoke_unknown_command` | `tests/integration/test_pipeline_smoke.py` | I-USAGE-1 |
| 15 | `test_activate_phase_deterministic` | `tests/integration/test_pipeline_deterministic.py` | I-EXEC-ISOL-1, determinism |
| 16 | `test_compute_trend_no_io` | `tests/unit/infra/test_metrics_purity.py` | I-PURE-1 |
| 17 | `test_detect_anomalies_no_io` | `tests/unit/infra/test_metrics_purity.py` | I-PURE-1 |

**Purity test implementation note (T-1008):**

```python
from unittest.mock import patch, MagicMock
from sdd.infra.metrics import compute_trend, detect_anomalies

def test_compute_trend_no_io():
    # Patch the module-level binding AND the global package to catch inline imports
    with patch('sdd.infra.metrics.duckdb', MagicMock()) as mock_mod, \
         patch('duckdb.connect') as mock_connect:
        result = compute_trend([...])          # call with valid fixture data
        assert mock_mod.connect.call_count == 0
        assert mock_connect.call_count == 0
        assert result is not None

def test_detect_anomalies_no_io():
    with patch('sdd.infra.metrics.duckdb', MagicMock()) as mock_mod, \
         patch('duckdb.connect') as mock_connect:
        result = detect_anomalies([...])
        assert mock_mod.connect.call_count == 0
        assert mock_connect.call_count == 0
        assert result is not None
```

Patching `sdd.infra.metrics.duckdb` intercepts module-level `duckdb` usage.
Patching `duckdb.connect` additionally catches any `import duckdb` inside function bodies
(I-PURE-1a). Both patches must show zero calls for I-PURE-1 to pass.

---

## §PHASE-INV

All of the following MUST be PASS before Phase 10 can be COMPLETE:

```
[I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1,
 I-EXEC-NO-CATCH-1,
 I-ENV-1, I-ENV-2, I-ENV-BOOT-1,
 I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1,
 I-KERNEL-REG, I-KERNEL-SIG-1, I-REG-ENV-1,
 I-PURE-1, I-PURE-1a, I-EXEC-ISOL-1]
```

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| BC-EXEC structural split into BC-EXEC-ERROR + BC-EXEC-ENV sub-BCs | Phase 11+ |
| BC-INTEG isolation model formalization (EventLog indirect coupling between Level A/B) | Phase 11+ |
| Replay migration from v1 events (I-EL-4) | Phase 11 |
| Projection caching | Phase 11 |
| `sdd norm-check` / `sdd norm-list` subcommands | Phase 11 |
| Snapshot-based replay optimization | Phase 11 |
| `.sdd/tools/` full removal (self-hosting) | Phase 12 |
| Any new domain features | Phase 11+ |
| Async / concurrent command execution | Phase 11+ |

---

## Appendix A: Task Overview

| Task | Primary Output | Invariants Produced |
|------|---------------|---------------------|
| T-1001 | `src/sdd/cli.py` (execution contract: all 5 paths + `_emit_json_error`) | I-FAIL-1, I-USAGE-1, I-EXEC-SUCCESS-1, I-CLI-API-1, I-ERR-CLI-1 |
| T-1002 | `tests/unit/test_cli_exec_contract.py` (6 tests, all paths incl. I-ERR-CLI-1) | — |
| T-1003 | `.sdd/config/project_profile.yaml` (I-LEGACY-0a/b, I-ENTRY-1 patterns) | I-LEGACY-0a, I-LEGACY-0b, I-ENTRY-1 |
| T-1004 | `src/sdd/commands/validate_invariants.py` (`--scope full-src` dual-mode) | (enables T-1003 enforcement) |
| T-1005 | `tests/regression/test_kernel_contract.py` + `pyproject.toml` mypy dev dep | I-KERNEL-REG, I-KERNEL-SIG-1, I-REG-ENV-1 |
| T-1006 | `tests/integration/test_env_independence.py` | I-ENV-1, I-ENV-2, I-ENV-BOOT-1 |
| T-1007a | `tests/integration/test_pipeline_smoke.py` (CLI smoke, 3 tests) | I-USAGE-1 (smoke) |
| T-1007b | `tests/integration/test_pipeline_deterministic.py` (isolated DB, 1 test) | I-EXEC-ISOL-1 |
| T-1008 | `tests/unit/infra/test_metrics_purity.py` (dual-patch on duckdb, 2 tests) | I-PURE-1, I-PURE-1a |
| T-1009 | `CLAUDE.md` (§R split: §R-core + §R-rules; §0.16 Kernel Hardening Catalog) | — |
| T-1010 | `sdd_plan.md` (Phase Overview table: Phases 0–9 COMPLETE, Phase 10 ACTIVE, Phase 11 Improvements & Integration (was 10), Phase 12 Self-hosted Governance (was 11)) — **HUMAN TASK** (manual doc update, outside SDD automation boundary) | — |

Total: 11 tasks (T-1001 through T-1010, with T-1007a/b counted separately).

---

## Appendix B: Verification Commands

```bash
# BC-EXEC: all execution paths
pytest tests/unit/test_cli_exec_contract.py -v

# BC-ENV: environment independence
pytest tests/integration/test_env_independence.py -v

# BC-STATIC: forbidden patterns across full src/
python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0a --scope full-src
python3 .sdd/tools/validate_invariants.py --check I-LEGACY-0b --scope full-src
python3 .sdd/tools/validate_invariants.py --check I-ENTRY-1 --scope full-src

# BC-REGRESS: mypy --strict + import smoke + signature check
pytest tests/regression/test_kernel_contract.py -v

# BC-INTEG Level A: CLI smoke
pytest tests/integration/test_pipeline_smoke.py -v

# BC-INTEG Level B: domain determinism (isolated DB)
pytest tests/integration/test_pipeline_deterministic.py -v

# BC-PURE: metrics purity
pytest tests/unit/infra/test_metrics_purity.py -v

# Full suite with coverage
pytest tests/ -q --cov=sdd --cov-report=term-missing
```
