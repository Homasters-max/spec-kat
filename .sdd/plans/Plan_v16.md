# Plan_v16 — Phase 16: Legacy Architecture Closure

Status: DRAFT
Spec: specs_draft/Spec_v16_LegacyArchitectureClosure.md

---

## Milestones

### M1: Fix cli.py I-PATH-1 violations

```text
Spec:       §2 BC-1 Infra; §8 Integration
BCs:        BC-1
Invariants: I-PATH-1
Depends:    — (no prior milestone; independent)
Risks:      import order matters — add paths.py imports before removing hardcoded strings;
            if config_file() / event_store_file() / state_file() signatures changed in
            infra/paths.py this will surface here first
```

Gate: `grep -n '\.sdd/' src/sdd/cli.py` → 0 lines; `pytest tests/ -q` → green

---

### M2: Rewrite deprecated-dependent tests

```text
Spec:       §2 BC-TEST
BCs:        BC-TEST
Invariants: I-DEPRECATED-RM-2, I-SHIM-CONTRACT-1
Depends:    M1
Risks:      test_cli_contracts.py must cover all behavioural contracts of 15 deleted shims
            or I-SHIM-CONTRACT-1 cannot be PASS; write before deleting, not after;
            test_log_tool_parity.py AST checks on deprecated file must be removed before
            BC-SHIM-RM or import will fail
```

Gate: `grep -rn "_deprecated_tools" tests/` → 0; `pytest tests/ -q` → green

---

### M3: Verify behavioural coverage of 3 logic modules

```text
Spec:       §2 BC-LOGIC-VERIFY
BCs:        BC-LOGIC-VERIFY
Invariants: I-LOGIC-COVER-1, I-LOGIC-COVER-2, I-LOGIC-COVER-3
Depends:    M1
Risks:      if coverage gaps found, new tests must be added to src/sdd before deletion
            proceeds; atomic_write monkeypatch test requires Path.rename mock — confirm
            pytest monkeypatch fixture available; sdd_latest_seq() may not have a
            src/sdd equivalent — check before marking M3 complete
```

Gate: `pytest tests/unit/domain/test_taskset_parser.py tests/unit/domain/test_state_yaml.py tests/unit/domain/test_norm_catalog.py -v` → all pass; `grep -rn "sdd_latest_seq\|latest_seq" tests/` → ≥ 1 match

---

### M4: Dependency audit grep gate

```text
Spec:       §2 BC-DEP-AUDIT; §11 M4
BCs:        BC-DEP-AUDIT
Invariants: I-DEP-AUDIT-1
Depends:    M2, M3
Risks:      false negatives if grep uses BRE alternation without -E (fixed in spec);
            false positives from test data strings if grep too broad (spec uses
            import/subprocess context filter); compute_spec_hash must also reach 0
```

Gate:
```bash
grep -rEn "sdd_db|sdd_event_log" src/ tests/ --include="*.py" \
    --exclude-dir=_deprecated_tools | grep -v "__pycache__"  # → 0
grep -rn "compute_spec_hash" src/ tests/                     # → 0
grep -rEn "(import|subprocess).*\.(report_error|sync_state)\.py" \
    src/ tests/ --include="*.py" --exclude-dir=_deprecated_tools  # → 0
```

---

### M5: Delete 15 shim files

```text
Spec:       §2 BC-SHIM-RM; §1 In-Scope
BCs:        BC-SHIM-RM
Invariants: I-DEPRECATED-RM-1 (partial), I-DEPRECATED-RM-2
Depends:    M2, M3, M4
Risks:      deletion is irreversible — confirm gate conditions before proceeding;
            Pattern B import shims (9 files): build_context.py, check_scope.py,
            norm_guard.py, phase_guard.py, task_guard.py, log_tool.py, log_bash.py,
            record_metric.py, senar_audit.py;
            Pattern A subprocess shims (6 files): query_events.py, metrics_report.py,
            report_error.py, sync_state.py, update_state.py, validate_invariants.py
```

Gate: `pytest tests/ -q` → green after deletion; file count in _deprecated_tools drops by 15

---

### M5b: Delete 5 uncategorised files (BC-CLEANUP-RM)

```text
Spec:       §1 In-Scope BC-CLEANUP-RM; §11 M5b
BCs:        BC-CLEANUP-RM
Invariants: I-DEPRECATED-RM-1 (partial)
Depends:    M3, M5
Risks:      show_state.py not mentioned anywhere in src/sdd — verify no callers before
            deleting; init_state.py (deprecated) deletion OK per Decision 3 but
            src/sdd/domain/state/init_state.py must be retained; taskset_parser.py /
            norm_catalog.py / state_yaml.py require M3 logic-cover gate to be PASS first
```

Files: `show_state.py`, `init_state.py` (deprecated), `norm_catalog.py`, `state_yaml.py`, `taskset_parser.py`

Gate: `pytest tests/ -q` → green; file count in _deprecated_tools at 7 (legacy infra only)

---

### M6: Resolve and implement critical legacy decisions

```text
Spec:       §2 BC-LEGACY-RESOLVE; Decisions 1, 2, 3
BCs:        BC-LEGACY-RESOLVE
Invariants: I-1 (event-sourcing); I-SDDRUN-DEAD-1 (Phase 15, not here)
Depends:    M5, M5b
Risks:      Decision 1 Layer B (CommandRunner) MUST NOT be removed here — deferred to
            Phase 15 Step 4; only _deprecated_tools/sdd_run.py is deleted in M7;
            Decision 2 (derive_state): if sdd sync-state --dry-run does not print diff,
            alias must be added before deletion — verify before marking done;
            Decision 3 (init_state): src/sdd/domain/state/init_state.py gets deprecation
            warning added, NOT deleted; only _deprecated_tools/init_state.py deleted
```

Gate: `sdd sync-state --dry-run` produces diff output; `pytest tests/ -q` → green after each decision

---

### M7: Delete 7 legacy infra files

```text
Spec:       §2 BC-LEGACY-RM; §11 M7
BCs:        BC-LEGACY-RM
Invariants: I-DEPRECATED-RM-1 (partial)
Depends:    M6
Risks:      sdd_db.py and sdd_event_log.py are the most heavily used legacy files;
            dep-audit (M4) must still hold — re-run grep before deletion as a
            sanity check; guard_runner.py superseded by domain/guards/pipeline.py —
            confirm via grep before deleting
```

Files: `sdd_db.py`, `sdd_event_log.py`, `derive_state.py`, `guard_runner.py`,
       `sdd_run.py` (deprecated adapter, Layer A only), `record_decision.py`,
       `migrate_jsonl_to_duckdb.py`

Gate: `pytest tests/ -q` → green; `ls .sdd/_deprecated_tools/*.py | wc -l` → 0

---

### M8: Delete _deprecated_tools/ directory

```text
Spec:       §2 BC-DIR-RM; §11 M8
BCs:        BC-DIR-RM
Invariants: I-DEPRECATED-RM-1
Depends:    M7
Risks:      verify directory is truly empty before rmdir; any hidden files (.gitkeep etc.)
            will block wc -l → 0 gate — use ls -la not ls
```

Gate: `test ! -d .sdd/_deprecated_tools && echo PASS`

---

### M9: CLAUDE.md and norm_catalog.yaml cleanup

```text
Spec:       §2 BC-DOCS; §9 checks #15, #16
BCs:        BC-DOCS
Invariants: SDD-11 (no stale tool references)
Depends:    M8
Risks:      4 CLAUDE.md lines must be patched exactly — use spec §2 BC-DOCS table;
            norm_catalog.yaml scope_exempt entries for _deprecated_tools/ silently
            mislead if left; activate_plan.py must be documented as internal-only in
            CLAUDE.md §0.10 to satisfy I-CLI-REG-1
```

Gate: `grep -c '\.sdd/tools' CLAUDE.md` → 0; `grep -c '_deprecated_tools' .sdd/norms/norm_catalog.yaml` → 0

---

### M10: CLI registration audit

```text
Spec:       §2 BC-CLI-REG; §9 check #11; §5 I-CLI-REG-1
BCs:        BC-CLI-REG
Invariants: I-CLI-REG-1
Depends:    M9
Risks:      activate_plan.py must be in CLAUDE.md §0.10 internal-only list BEFORE this
            check runs (done in M9); sdd validate-invariants --check I-CLI-REG-1 must
            exist — if not yet implemented, perform manual audit with documented result
```

Gate: `sdd validate-invariants --check I-CLI-REG-1 --scope full-src` → PASS

---

## Risk Notes

- R-1: **Premature deletion.** Each milestone has a hard gate condition. Never proceed to
  the next milestone without the gate passing. Deletion is irreversible.
- R-2: **M4 grep false negatives.** Without `-E` flag, `|` in BRE patterns matches literal
  pipe — command always returns 0. Use `grep -rEn` as specified in spec (fixed in draft).
- R-3: **CommandRunner scope leak.** CommandRunner class in `src/sdd/commands/sdd_run.py`
  must NOT be deleted in Phase 16. It is the active Write Kernel until Phase 15 Step 4.
  Only `_deprecated_tools/sdd_run.py` (the adapter) is deleted in M7.
- R-4: **M8 gate on 27 files.** _deprecated_tools/ originally contains 27 files. Plan
  accounts for all: 15 shims (M5) + 5 uncategorised (M5b) + 7 legacy (M7) = 27. If count
  differs, audit before M8.
- R-5: **sdd_latest_seq() coverage.** If no equivalent exists in `sdd.infra.db`, M3 is
  not complete. Adding the function and test is in scope for M3.
- R-6: **sdd show-spec --phase 16 broken.** During this phase, sdd show-spec fails for
  Phase 16 (path resolution issue in show_spec.py). Spec content must be read from
  `.sdd/specs_draft/Spec_v16_LegacyArchitectureClosure.md` directly until fixed.
