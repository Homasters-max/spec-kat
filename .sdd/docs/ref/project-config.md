---
source: CLAUDE.md §0.13 + I-CONFIG-PATH-1
last_synced: 2026-04-24
update_trigger: when project_profile.yaml schema changes or new config blocks added
---

# Ref: Project Configuration
<!-- Loaded for validate-config sessions or config debugging -->

## Config Files

```
.sdd/config/project_profile.yaml   ← stack, code rules, scope, domain, custom norms
.sdd/config/sdd_config.yaml        ← modes, gates, budgets
.sdd/config/phases/phase_N.yaml    ← phase-level overrides
```

## Override Hierarchy (lowest → highest priority)

```
base defaults (SDD built-in) ← project_profile.yaml ← phases/phase_N.yaml
```

## Key Blocks in project_profile.yaml

| Block | Read by | Configures |
|-------|---------|-----------|
| `stack` | `build_context.py` | Languages, versions, linter/formatter/typecheck |
| `build.commands` | `validate_invariants.py` | lint, test, typecheck, build commands |
| `testing.coverage_threshold` | `validate_invariants.py` | exit 1 if coverage below threshold |
| `code_rules.forbidden_patterns` | `validate_invariants.py` | grep on task outputs (hard/soft) |
| `scope.forbidden_dirs` | `check_scope.py` | Extends base deny-list |
| `domain.glossary` | `build_context.py` | Layer 0 of agent context |
| `norms.custom` | `norm_guard.py` | Project norms on top of base norms |

## Config Loader Rule

`sdd_config_loader.py` — sole entry point for reading configs (SEM-9).
FORBIDDEN: direct YAML reads of `.sdd/config/` from `src/sdd/` code.

## Validate Config Command

```bash
sdd validate-config --phase N
```

Runs BEFORE every Validate T-NNN command (§R.7).
Validates `project_profile.yaml` + `phase_N.yaml` against schema.

Read-only command — no REGISTRY entry (I-READ-ONLY-EXCEPTION-1).

## Adding a New Config Block (protocol)

1. Add YAML block to `project_profile.yaml`
2. Add reading logic to `sdd_config_loader.py`
3. Use value in target script
4. Add check to `validate_config.py`

## Invariant I-CONFIG-PATH-1 (SDD-19)

Config MUST NOT override core SDD paths:
- `state` → `.sdd/runtime/State_index.yaml`
- `tasks` → `.sdd/tasks/TaskSet_vN.md`
- `specs` → `.sdd/specs/`
- `plans` → `.sdd/plans/`
- `db` → `SDD_DATABASE_URL` (PostgreSQL connection URL; enforced by I-NO-DUCKDB-1)

## I-CONTEXT-1..4 (build_context.py scoping)

These invariants govern `build_context.py` which is NOT used in Claude Code flow.
Provided for completeness:

- I-CONTEXT-1: Context always built via `build_context.py` (SEM-9)
- I-CONTEXT-2: Output budget-bounded: COMPACT=2000 / STANDARD=6000 / VERBOSE=12000 tokens
- I-CONTEXT-3: Layers 0-2 universal; Layer 3 (task row) coder only; Layer 8 (task input files) coder+VERBOSE only
- I-CONTEXT-4: `context_hash` covers agent_type + task_id + depth + sha256 of loaded files
