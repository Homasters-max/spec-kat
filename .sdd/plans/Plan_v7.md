# Plan_v7 — Phase 7: Hardening

Status: ACTIVE
Spec: specs/Spec_v7_Hardening.md

---

## Milestones

### M1: BC-STATE Hardening — Reducer Pre-Filter

```text
Spec:       §2.1 — BC-STATE Extension (I-REDUCER-1); §4.6 — reducer pre-filter interface
BCs:        BC-STATE
Invariants: I-REDUCER-1, I-REDUCER-WARN
Depends:    — (self-contained; reads EventRecord.event_source/.level already present from Phase 6)
Risks:      _pre_filter() must be inserted BEFORE dispatch in reduce(), not after — wrong
            insertion point means meta events still reach the handler table; test T-702
            catches this via test_only_runtime_l1_dispatched
Tasks:      T-701 (impl: reducer.py), T-702 (tests: test_reducer_hardening.py)
```

### M2: BC-INFRA Hardening — batch_id Column

```text
Spec:       §2.2 — BC-INFRA Extension (I-EL-12); §4.1 EventRecord update;
            §4.2 sdd_append_batch update; §4.3 QueryFilters update
BCs:        BC-INFRA
Invariants: I-EL-12 (write side: T-703; query side: T-704)
Depends:    — (independent; sdd_append signature unchanged; new column is nullable DEFAULT NULL)
Risks:      R-1 — ALTER TABLE must be idempotent if Phase 7 was partially applied previously;
                   mitigated by IF NOT EXISTS clause.
            R-2 — adding batch_id field to frozen EventRecord dataclass breaks positional
                   unpackers; Spec §8 states no such callers exist after Phase 6; grep for
                   positional unpacking before implementing T-703.
            R-3 — batch_id=None + is_batched=False always returns empty (not an error); parity
                   with SQL NULL semantics must be documented in QueryFilters docstring.
Tasks:      T-703 (impl: db.py + event_log.py),
            T-704 (impl: event_query.py QueryFilters + WHERE clauses),
            T-705 (tests: test_batch_id.py)
```

### M3: BC-CORE Hardening — Event Registry + C-1 Mode Split

```text
Spec:       §2.3 — BC-CORE Extension (I-REG-1 + I-C1-MODE-1); §4.4 register_l1_event_type;
            §4.5 _check_c1_consistency
BCs:        BC-CORE
Invariants: I-REG-1, I-REG-STATIC-1, I-C1-MODE-1
Depends:    — (independent; modifies core/events.py only; existing event types preserved)
Risks:      R-4 — default SDD_C1_MODE="warn" silences the C-1 check at import time; all
                   existing and new tests MUST set SDD_C1_MODE=strict (via conftest.py fixture
                   or pytest.ini); missing this causes C-1 violations to go undetected in CI.
            R-5 — bare import-time assert is removed; the replacement call to
                   _check_c1_consistency() must appear at the same module-level position so
                   import-time enforcement still fires in strict mode.
Tasks:      T-706 (impl: events.py — register_l1_event_type, _check_c1_consistency, SDD_C1_MODE),
            T-707 (tests: test_event_registry.py — 9 tests)
```

### M4: BC-HOOKS Hardening — Delegation Contract

```text
Spec:       §2.4 — BC-HOOKS Hardening (I-HOOK-WIRE-1 + I-HOOK-PARITY-1);
            §4.x hook interfaces; UC-7-4, UC-7-5
BCs:        BC-HOOKS
Invariants: I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1
Depends:    M2 (infra/event_log.py sdd_append unchanged, but EventRecord gains batch_id —
               parity test compares EventLog rows, must see consistent schema),
            M3 (core/events.py — ToolUseStartedEvent / ToolUseCompletedEvent / HookErrorEvent
               must be stable before canonical hook implementation is finalised)
Risks:      R-6 — parity test (T-709) invokes both entry points as subprocesses; the
                   subprocess for src/sdd/hooks/log_tool.py must resolve the sdd package.
                   The test must set PYTHONPATH=<project_root>/src or rely on the sys.path
                   injection in .sdd/tools/log_tool.py delegation path. Confirm subprocess
                   import succeeds before asserting row equality.
            R-7 — I-HOOKS-ISO: hooks must NOT be imported by commands/domain/infra. T-708
                   rewrites hooks/log_tool.py; verify that no non-hook module gains an import
                   of sdd.hooks after the rewrite.
            R-8 — .resolve() vs Path(__file__).parent chain: if .sdd/tools/log_tool.py is
                   accessed via a symlink, parents[2] produces the wrong root without .resolve().
                   I-HOOK-PATH-1 mandates .resolve(); test_tools_hook_path_resolution verifies
                   the resolved path contains sdd/__init__.py.
Tasks:      T-708 (impl: src/sdd/hooks/log_tool.py — stdin JSON protocol, canonical
                   _extract_inputs/_extract_output, HookErrorEvent handling),
            T-709 (impl: .sdd/tools/log_tool.py thin wrapper;
                   tests: test_log_tool_parity.py — 7 tests)
```

### M5: Phase Validation

```text
Spec:       §5 — §PHASE-INV (all 9 invariants must be PASS)
BCs:        all
Invariants: I-REDUCER-1, I-REDUCER-WARN, I-EL-12, I-REG-1, I-REG-STATIC-1,
            I-C1-MODE-1, I-HOOK-WIRE-1, I-HOOK-PATH-1, I-HOOK-PARITY-1
Depends:    M1, M2, M3, M4 (all tasks T-701..T-709 DONE)
Risks:      R-9 — validation runs the full test suite; hook parity tests spawn subprocesses
                   that write to DuckDB; test isolation (tmp_path / in-memory DB) must be
                   confirmed for T-705 and T-709 so parallel test runs do not share DB state.
Tasks:      T-710 (validation report: ValidationReport_T-710.md covering §PHASE-INV ×9)
```

---

## Risk Notes

- R-1: `ALTER TABLE events ADD COLUMN IF NOT EXISTS batch_id TEXT` is idempotent — safe for re-runs and existing DBs. No migration seeding needed; NULL is valid for pre-Phase-7 rows.
- R-2: No positional EventRecord unpacking exists post-Phase 6 (frozen dataclass, named-field convention I-PK-4). Grep `infra/db.py` and all callers before T-703 to confirm.
- R-3: `batch_id="x"` + `is_batched=False` is logically empty but not an error. SQL semantics are authoritative; document in QueryFilters docstring.
- R-4: `SDD_C1_MODE` must default to `"strict"` in all test environments. Add `os.environ["SDD_C1_MODE"] = "strict"` to `conftest.py` or `pytest.ini [env]` before T-707 test suite runs.
- R-5: `_check_c1_consistency()` call must be at module top-level in `core/events.py` — same position as the bare `assert` it replaces — so strict-mode enforcement fires on import.
- R-6: Parity subprocess test must ensure `src/` is on PYTHONPATH. Use `env={…, "PYTHONPATH": str(src_path)}` in `subprocess.run()`.
- R-7: After T-708, run `grep -r "from sdd.hooks" src/sdd/{commands,domain,infra}` to confirm I-HOOKS-ISO is preserved.
- R-8: `.resolve()` in `.sdd/tools/log_tool.py` is mandatory for symlink safety (I-HOOK-PATH-1). The test verifies the resolved path ends with `src/sdd/__init__.py`.
- R-9: Tests that write to DuckDB must use a `tmp_path`-based DB path or DuckDB in-memory mode. Confirm `conftest.py` provides an isolated `db_path` fixture for infra and hook tests.
