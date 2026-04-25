# Plan_v14 — Phase 14: Control Plane Migration

Status: DRAFT
Spec: specs/Spec_v14_ControlPlaneMigration.md

---

## Milestones

### M1: BC-14-PATHS — Create `paths.py` (Foundation)

```text
Spec:       §2 Architecture/BCs — BC-14-PATHS; §4 Types & Interfaces (paths.py)
BCs:        BC-14-PATHS (new)
Invariants: I-PATH-2, I-PATH-4, I-PATH-5
Depends:    — (prerequisite for all subsequent milestones)
Risks:      None — new file only; zero impact on existing code until consumers switch
```

Create `src/sdd/infra/paths.py` with all 16 public functions
(`get_sdd_root`, `reset_sdd_root`, `event_store_file`, `state_file`, `audit_log_file`,
`norm_catalog_file`, `config_file`, `phases_index_file`, `specs_dir`, `specs_draft_dir`,
`plans_dir`, `tasks_dir`, `reports_dir`, `templates_dir`, `taskset_file`, `plan_file`).

`get_sdd_root()` reads `SDD_HOME` env var; falls back to `Path(".sdd").resolve()`.
Lazy-cached via `_sdd_root` global. `reset_sdd_root()` clears cache for test isolation only.
`paths.py` imports ONLY `os` and `pathlib` (I-PATH-2). No `mkdir` anywhere (I-PATH-4).
Sentinel pattern: `str | None = None` with `if x is None:` guard — `""` is forbidden.

---

### M2: Infra Layer Migration (`db.py`, `audit.py`, `event_log.py`)

```text
Spec:       §2 BC-1 Infra; §4 Types & Interfaces (event_log.py, audit.py, db.py)
BCs:        BC-1 Infra (existing)
Invariants: I-PATH-1, I-KERNEL-EXT-1
Depends:    M1
Risks:      Backward-compatibility: callers passing explicit str path must continue
            to work — sentinel None pattern is the only safe extension
```

- `infra/db.py`: remove `SDD_EVENTS_DB` constant; `open_sdd_connection(db_path: str | None = None)` — body resolves via `event_store_file()` when `db_path is None`.
- `infra/audit.py`: remove `_AUDIT_LOG_DEFAULT` constant; `log_action(..., audit_log_path: str | None = None)` — body resolves via `audit_log_file()`.
- `infra/event_log.py`: change all six functions (`sdd_append`, `sdd_append_batch`, `sdd_replay`, `exists_command`, `exists_semantic`, `get_error_count`) from `db_path: str = SDD_EVENTS_DB` to `db_path: str | None = None`; body resolves via `event_store_file()`.

---

### M3: Guards Layer Migration (`scope.py`, `task.py`, `phase.py`, `norm.py`)

```text
Spec:       §2 BC-3 Guards; §4 Types — guards/scope.py Path.resolve() comparison
BCs:        BC-3 Guards (existing)
Invariants: I-PATH-1
Depends:    M1, M2
Risks:      scope.py comparison logic change — Path.resolve() may behave differently
            than string prefix for relative vs absolute paths; Python <3.9 fallback required
```

- `guards/scope.py`: replace all `path.startswith(".sdd/...")` string comparisons with `Path(path).resolve().is_relative_to(specs_dir().resolve())` (Python <3.9 fallback: `str(...).startswith(str(...))`). Remove hardcoded `.sdd/` strings.
- `guards/task.py`, `guards/phase.py`, `guards/norm.py`: replace all hardcoded `.sdd/` path literals with corresponding `paths.py` function calls.

---

### M4: Commands Layer Migration (7 command files)

```text
Spec:       §2 BC-4 Commands; §1 Scope — "7 command files — replace SDD_DB_PATH / SDD_STATE_PATH"
BCs:        BC-4 Commands (existing)
Invariants: I-PATH-1
Depends:    M1, M2, M3
Risks:      SDD_DB_PATH / SDD_STATE_PATH env vars used by external callers must be
            removed without fallback shim — users must migrate to SDD_HOME (documented
            in spec §8 CLAUDE.md changes)
```

In these 7 command files — `commands/report_error.py`, `commands/query_events.py`,
`commands/update_state.py`, `commands/validate_invariants.py`, `commands/metrics_report.py`,
`commands/activate_phase.py`, `commands/show_state.py` — replace all hardcoded `.sdd/`
path strings and `SDD_DB_PATH`/`SDD_STATE_PATH` env-var reads with `paths.py` function calls.

---

### M5: Hooks + Context Migration (`log_tool.py`, `build_context.py`)

```text
Spec:       §2 BC-Hooks; §2 BC-5 Context; §6 Pre/Post build_context.py
BCs:        BC-Hooks (existing), BC-5 Context (existing)
Invariants: I-PATH-1, I-CONFIG-PATH-1
Depends:    M1, M2
Risks:      build_context.py config backdoor: if project_profile.yaml contains
            state_path / phases_index_path keys today, closing the backdoor may silently
            change behavior — must confirm no active config uses those keys before landing
```

- `hooks/log_tool.py`: replace `SDD_DB_PATH` env-var read with `str(event_store_file())`.
- `context/build_context.py`: remove any code that reads `state_path` or `phases_index_path` from config; always use `state_file()` and `phases_index_file()` from `paths.py` (I-CONFIG-PATH-1). `build_context.py` MUST NOT call `sdd show-*` shell commands internally.

---

### M6: New CLI Commands — `show-task`, `show-spec`, `show-plan` + CLI wiring

```text
Spec:       §2 BC-8 CLI additions; §4 CLI output schema; §6 Pre/Post show-task/spec/plan;
            §7 UC-14-1, UC-14-3
BCs:        BC-8 CLI (existing)
Invariants: I-CLI-READ-1, I-CLI-READ-2, I-CLI-SCHEMA-1, I-CLI-SCHEMA-2,
            I-CLI-FAILSAFE-1, I-CLI-VERSION-1, I-CLI-SSOT-1, I-CLI-SSOT-2,
            I-SCOPE-CLI-1, I-SCOPE-CLI-2, I-SPEC-RESOLVE-1, I-SPEC-RESOLVE-2
Depends:    M1, M2
Risks:      show-spec AmbiguousSpec guard: must use Phases_index.md as SSOT for
            spec filename — NOT sorted()[0] (I-SPEC-RESOLVE-1/2)
```

New files:
- `src/sdd/commands/show_task.py` — `sdd show-task T-NNN [--phase N]`: auto-detects phase from `State_index.yaml` if `--phase` omitted; reads `taskset_file(phase)`; emits frozen schema (§4).
- `src/sdd/commands/show_spec.py` — `sdd show-spec --phase N`: resolves spec path from `Phases_index.md` `spec` field (I-SPEC-RESOLVE-2); emits file content verbatim; AmbiguousSpec guard if >1 match.
- `src/sdd/commands/show_plan.py` — `sdd show-plan --phase N`: reads `plan_file(N)`; emits file content verbatim.
- `cli.py`: register all three new commands.

All three: deterministic stdout (no timestamps, no ANSI), JSON error on stderr (I-CLI-API-1 schema), exit 0/1 only, no event emission, no state mutation.

---

### M7: Test Infrastructure

```text
Spec:       §1 Scope — Test infrastructure; §7 UC-14-2; §9 Verification rows 1–5, 15
BCs:        BC-14-PATHS (test harness)
Invariants: I-EXEC-ISOL-1, I-KERNEL-EXT-1, I-PATH-1, I-PATH-2, I-PATH-3
Depends:    M1–M6 (tests must compile against final API)
Risks:      test_kernel_contract.py references frozen signatures — must update expected
            defaults for the six event_log.py functions from SDD_EVENTS_DB to None
```

- New `tests/integration/test_sdd_home_isolation.py` with at minimum:
  - `test_sdd_home_redirects_all_paths`: set `SDD_HOME=/tmp/…`, assert all `paths.*_file()` / `paths.*_dir()` results are under that root.
  - `test_no_hardcoded_sdd_paths_in_src`: grep `src/sdd/**/*.py` (excluding `paths.py`) for literal `\.sdd[/\\]` — assert empty.
  - `test_paths_module_no_sdd_imports`: assert `paths.py` only imports `os` and `pathlib`.
- Update `tests/regression/test_kernel_contract.py::test_frozen_modules_signatures`: change expected default for all six `event_log.py` functions from `SDD_EVENTS_DB` string to `None`.

---

### M8: Config Enforcement + CLAUDE.md Governance

```text
Spec:       §8 Integration — project_profile.yaml; §8 CLAUDE.md changes
BCs:        Governance (config + docs)
Invariants: I-PATH-1 (enforcement config), I-CLI-SSOT-1, I-CLI-SSOT-2
Depends:    M1–M7 (docs must describe the final, working system)
Risks:      CLAUDE.md §R.2 change is load-bearing for future LLM sessions — must be
            precise; any ambiguity in the CLI-only read model propagates into wrong
            LLM behavior in Phase 15+
```

- `.sdd/config/project_profile.yaml`: add I-PATH-1 forbidden pattern block (§8 Integration).
- `CLAUDE.md`: update §R.1, §R.2 (CLI-only read model), §0.15 (add `paths.py` frozen row), §0.10 (add `sdd show-task/spec/plan` rows), §K.4 (add SDD-11..SDD-19 if applicable), §K.6 (update Read Order steps 2/4 to show-spec/show-task). Remove all `SDD_DB_PATH`/`SDD_STATE_PATH` mentions.

---

## Risk Notes

- **R-1: State_index inconsistency** — `State_index.yaml` shows Phase 13 ACTIVE while `Phases_index.md` shows Phase 14 ACTIVE. Must be resolved via `sdd sync-state --phase 14` (or manual State_index update by human) before any Implement/Validate commands in this phase.
- **R-2: Phases_index.md incorrect spec path** — Entry for Phase 14 lists `specs_draft/Spec_v14_ControlPlaneMigration.md`; actual location is `specs/Spec_v14_ControlPlaneMigration.md`. Must correct the index before running `sdd show-spec --phase 14`.
- **R-3: SDD_DB_PATH / SDD_STATE_PATH removal** — These env vars are removed without backward-compat shim per spec. Any user shell profiles, CI scripts, or external tooling that sets these must migrate to `SDD_HOME`. Document in CLAUDE.md (M8).
- **R-4: Python <3.9 compatibility** — `Path.is_relative_to()` is Python 3.9+. `scope.py` migration (M3) must include the fallback: `str(resolved_path).startswith(str(base))`.
- **R-5: build_context.py backdoor** — Closing I-CONFIG-PATH-1 may silently change behavior if any active `project_profile.yaml` contains `state_path` or `phases_index_path` keys. Verify before landing M5.
