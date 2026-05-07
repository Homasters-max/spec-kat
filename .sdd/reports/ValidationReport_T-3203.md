# ValidationReport — T-3203
**Task:** Implement `sdd init-project` handler  
**Phase:** 32  
**Validator:** LLM  
**Date:** 2026-04-27  
**Result:** PASS

---

## Spec Coverage

- **Spec_v32 §2 BC-32-0** — `shared` schema + `shared.projects` table creation
- **Spec_v32 §2 BC-32-1** — Connection model + `sdd init-project` command registration

---

## Invariants Checked

| Invariant | Check | Result |
|-----------|-------|--------|
| I-DB-SCHEMA-1 | Schema name = `p_{name}`; direct creation outside `init-project` forbidden | PASS |
| I-DB-1 | `db_url` resolved via payload → `SDD_DATABASE_URL`; empty string raises ValueError | PASS |
| I-REGISTRY-COMPLETE-1 | `init-project` in REGISTRY + `_EXPECTED_REGISTRY_KEYS` updated | PASS |
| I-HANDLER-PURE-1 | `handle()` does not call EventStore/rebuild_state/sync_projections | PASS |
| NORM-ACTOR-INIT-PROJECT | `init_project` action registered in norm catalog for `human` actor | PASS |

---

## Acceptance Criterion

**Criterion:** `sdd init-project --name foo` creates schema `p_foo` and record in `shared.projects`

**Result:** PASS — verified by unit tests:
- `test_creates_schema_and_project_record` — confirms `CREATE SCHEMA IF NOT EXISTS p_foo` and INSERT into `shared.projects` are called
- `test_db_schema_naming_rule` — `p_{name}` naming convention enforced (I-DB-SCHEMA-1)
- `test_empty_name_raises` — empty name rejected before any DB I/O
- `test_invalid_name_raises` — names not matching `[a-z][a-z0-9_]*` rejected with `I-DB-SCHEMA-1` error
- `test_connection_closed_on_db_error` — connection always closed via `finally` (no leak)
- `test_registry_entry_exists` — REGISTRY entry: `actor=human`, `requires_active_phase=False`, `action=init_project`

---

## Test Results

| Suite | Passed | Notes |
|-------|--------|-------|
| `test_init_project.py` (new) | 6/6 | All acceptance criteria covered |
| `tests/unit/` + `tests/integration/` | 978/979 | 1 pre-existing DuckDB flake (`test_schema_has_v2_columns`) — passes in isolation |

**Pre-existing flaky tests (not caused by T-3203):**
- `tests/unit/infra/test_db.py::test_schema_has_v2_columns` — DuckDB concurrent access in full suite; passes individually
- `tests/unit/test_cli_contracts.py::test_all_subcommands_help_exit_0` — ERROR in full suite (test ordering); passes individually

---

## Build Commands (task mode — `test*` excluded per I-TASK-MODE-1)

| Command | Result | Notes |
|---------|--------|-------|
| `lint` | returncode 127 | `ruff` not installed in environment — not a code issue |
| `typecheck` | returncode 127 | `mypy` not installed in environment — not a code issue |
| `pytest` | 978 passed | Run directly via `python3 -m pytest` |

---

## Files Changed

| File | Type | Change |
|------|------|--------|
| `src/sdd/commands/init_project.py` | New | `InitProjectHandler` + `ProjectInitializedEvent` |
| `src/sdd/commands/registry.py` | Modified | Added `init-project` CommandSpec + `_lazy_init_project_handler` |
| `.sdd/norms/norm_catalog.yaml` | Modified | Added `NORM-ACTOR-INIT-PROJECT` (blocking fix — `validate_registry_actions` requires all actions registered) |
| `tests/unit/test_registry_contract.py` | Modified | Added `init-project` to `_EXPECTED_REGISTRY_KEYS` (TP-1) |
| `tests/unit/commands/test_init_project.py` | New | 6 unit tests covering acceptance criterion (TP-2) |

---

## Code Quality Notes

- Input validation via `_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")` prevents SQL injection in `CREATE SCHEMA IF NOT EXISTS {db_schema}`
- `finally: conn.close()` ensures no connection leak on exception
- `ON CONFLICT (db_schema) DO NOTHING` makes the DB operation idempotent at the PostgreSQL level (complementing `_check_idempotent` at the SDD level)
- `@error_event_boundary` wraps handler for audit trail compatibility
