---
source: CLAUDE.md §0.13 + .sdd/config/project_profile.yaml
last_synced: 2026-04-24
update_trigger: when project_profile.yaml stack/build/testing blocks change
---

# Ref: Tech Stack & Build Commands
<!-- Loaded by §HARD-LOAD Rule 3 before VALIDATE or CHECK_DOD -->

## Stack

Read from `.sdd/config/project_profile.yaml` block `stack`:
- Language versions
- Linter / formatter / typecheck tools

To get current values:
```bash
cat .sdd/config/project_profile.yaml
```

## Build Commands

From `project_profile.yaml` block `build.commands`:

These are the commands run by `sdd validate-invariants`:
- `lint`: linting command
- `test`: test command (with coverage)
- `typecheck`: type checking command
- `acceptance`: triggers acceptance check (ruff on outputs + reuses `test` result via I-ACCEPT-REUSE-1)

### Test Tier Contract

| Command | Scope | Flags | Use in session |
|---|---|---|---|
| `test_fast` | `tests/unit/` | `-x -m "not pg"` | IMPLEMENT loop (fail-fast, <15s) |
| `test` | `tests/unit/ tests/integration/` | `-m "not pg" --cov --cov-fail-under=80` | VALIDATE T-NNN |
| `test_full` | `tests/` | `-m "not pg" --cov --cov-fail-under=80` | CHECK_DOD |
| `test_pg` | `tests/` | `-m pg` | Explicit PostgreSQL environments only |

**I-TASK-MODE-1 compliance**: all keys prefixed `test` are auto-excluded in task mode.
`acceptance` is always skipped in the build loop (handled separately by `_run_acceptance_check`).

**Coverage invariant**: `--cov-fail-under=80` in `test` and `test_full` makes coverage a
hard gate — CI fails if coverage drops below 80%. The `testing.coverage_threshold: 80` field
in `project_profile.yaml` is the documentation source; enforcement is via the `--cov-fail-under` flag.

**PostgreSQL exclusion**: `-m "not pg"` in all default commands prevents connection errors in
environments without live PostgreSQL. Tests requiring PG are explicitly opt-in via `test_pg`.

## Coverage Threshold

From `project_profile.yaml` block `testing.coverage_threshold`:
- `validate_invariants.py` exits 1 if coverage drops below this value

## Forbidden Patterns

From `project_profile.yaml` block `code_rules.forbidden_patterns`:
- `hard`: grep-based patterns that cause immediate FAIL
- `soft`: advisory warnings

## Config Loader

All config access goes through `sdd_config_loader.py` (SEM-9).
Direct YAML reads of `.sdd/config/` are FORBIDDEN from `src/sdd/` code.

## Config Override Hierarchy

```
base defaults (SDD built-in) ← project_profile.yaml ← phases/phase_N.yaml
```

Phase-level overrides: `.sdd/config/phases/phase_N.yaml`

## Validation

Before VALIDATE or CHECK_DOD:
```bash
sdd validate-config --phase N
```
Validates `project_profile.yaml` + `phase_N.yaml` against schema.

## Invariant (I-CONFIG-PATH-1)

Config MUST NOT override core SDD paths (state, tasks, specs, plans, db) — SDD-19.
