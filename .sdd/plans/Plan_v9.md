# Plan_v9 — Phase 9: Command Envelope Refactor

Status: ACTIVE
Spec: specs_draft/Spec_v9_CommandRegistry.md

---

## Milestones

### M1: Command Envelope Layer

```text
Spec:       §2 BC-CMD-ENV — core/payloads.py
BCs:        BC-CMD-ENV
Invariants: I-CMD-ENV-3, I-CMD-ENV-4, I-CMD-ENV-5
Depends:    — (no prior milestone; new module, no src changes)
Risks:      COMMAND_REGISTRY annotated Final — Python does not enforce Final at
            runtime; mypy must be run to catch mutations. Frozen dataclass fields
            must be verified via AST check (I-CMD-ENV-5), not by trust.
```

Outputs: `src/sdd/core/payloads.py`

Defines all payload dataclasses (frozen), `COMMAND_REGISTRY` (Final), and `build_command()`.
`_unpack_payload()` present but not exported — testing utility only.

---

### M2: Subclass Elimination in commands/

```text
Spec:       §2 BC-CMD-FIX — remove *Command subclasses, fix main() and handlers
BCs:        BC-CMD-FIX
Invariants: I-CMD-ENV-1, I-CMD-ENV-6
Depends:    M1 (build_command must exist before main() can use it)
Risks:      Each commands/*.py is modified independently, but all must be consistent.
            Risk: partial migration — if one file still has a subclass, I-CMD-ENV-1
            fails. Mitigation: AST grep in test_no_command_subclasses catches stragglers.
            Handler unpack pattern: PayloadClass(**command.payload) — handler must
            import its own PayloadClass explicitly; no generic validate_payload call.
```

Affected modules (8): `update_state.py` (4 subclasses), `report_error.py`,
`validate_invariants.py`, `activate_phase.py`, `activate_plan.py`,
`validate_config.py`, `metrics_report.py`, `record_decision.py`.

For each: (1) remove `class *Command(Command)` definition, (2) fix `main()` to use
`build_command("Type", ...)`, (3) fix handler to use `PayloadClass(**command.payload)`.

---

### M3: Tests and Verification

```text
Spec:       §2 BC-CMD-TEST, §9 Verification
BCs:        BC-CMD-TEST
Invariants: I-CMD-ENV-1..6 (full coverage)
Depends:    M1 + M2 (tests verify the completed system)
Risks:      Smoke test (I-CMD-ENV-6) requires a real TaskSet fixture in a tmp dir and
            subprocess call to `sdd complete`. If sdd CLI is not installed (pip install -e .)
            the test will fail at import, not at assertion. Mitigation: fixture must
            include a valid TaskSet with ≥1 TODO task; test must check exit code 0,
            not just absence of exception.
```

Outputs: `tests/unit/core/test_payloads.py`, `tests/unit/test_sdd_complete_smoke.py`

`test_payloads.py` covers I-CMD-ENV-1..5 (registry, factory, frozen, coverage, AST grep).
`test_sdd_complete_smoke.py` covers I-CMD-ENV-6 (subprocess, real fixture, exit 0).
Existing `tests/unit/commands/` suite must pass unchanged (no regressions — I-CMD-1, I-CMD-4).

---

## Risk Notes

- R-1: **Partial migration** — if any `commands/*.py` file retains a `*Command(Command)`
  subclass after M2, I-CMD-ENV-1 fails. AST grep in test_no_command_subclasses is the
  gate. Mitigation: treat M2 tasks as a batch; run the invariant check after each file.

- R-2: **Smoke test fixture isolation** — `test_sdd_complete_smoke` writes to a tmp dir
  and invokes `sdd` via subprocess. Risk: test picks up real project state if isolation
  is incomplete. Mitigation: fixture must create a self-contained minimal TaskSet + State
  in `tmp_path`; CLI must accept `--state` and `--taskset` overrides.

- R-3: **Final not enforced at runtime** — `COMMAND_REGISTRY: Final[...]` is a mypy
  annotation only. A buggy import could mutate the dict at runtime. Mitigation:
  document as known limitation (Type Safety Trade-off, §2); Phase 10 adds I-REG-STATIC-1.

- R-4: **Phase 8 not fully closed** — State_index shows 13/15 tasks done (T-814, T-815
  remain). Phase 9 implementation must not modify files in scope of T-814/T-815 to avoid
  conflicts. `commands/update_state.py` (T-902) is both a Phase 9 target and likely
  involved in T-814/T-815 — confirm task boundaries before implementing T-902.
