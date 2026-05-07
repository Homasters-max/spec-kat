# Plan_v23 — Phase 23: Activation Guard

Status: DRAFT
Spec: specs/Spec_v23_ActivationGuard.md

---

## Milestones

### M1: Dependency functions — `taskset_file` and `parse_taskset`

```text
Spec:       §2 — BC-23-1 Dependencies, §8 Integration
BCs:        BC-23-1 (prerequisites)
Invariants: I-PHASE-INIT-3
Depends:    —
Risks:      parse_taskset may not exist or have wrong signature; must align with
            sdd.domain.tasks.parser contract before BC-23-1 can call it safely
```

### M2: Implement `_resolve_tasks_total` (BC-23-1)

```text
Spec:       §2 — BC-23-1, §4 Types & Interfaces, §5 Invariants, §6 Pre/Post
BCs:        BC-23-1
Invariants: I-PHASE-INIT-2, I-PHASE-INIT-3
Depends:    M1
Risks:      Caller (main) must not duplicate validation — single-point contract;
            MissingContext / Inconsistency must map to structured SDDError
```

### M3: Deprecate `--tasks` argument (BC-23-2)

```text
Spec:       §2 — BC-23-2, §7 UC-23-1..3
BCs:        BC-23-2
Invariants: I-PHASE-INIT-2, I-PHASE-INIT-3
Depends:    M2
Risks:      default change None vs 0 is a breaking API change for callers passing
            --tasks 0 explicitly; DeprecationWarning must fire before validation
```

### M4: Test suite — verification matrix §9

```text
Spec:       §9 Verification (tests 1..9)
BCs:        BC-23-1, BC-23-2
Invariants: I-PHASE-INIT-2, I-PHASE-INIT-3, I-TASKSET-IMMUTABLE-1
Depends:    M2, M3
Risks:      tests must use real TaskSet fixture files, not mocks (I-HANDLER-PURE-1
            does not prohibit fixtures but parser must be real)
```

---

## Risk Notes

- R-1: `parse_taskset` signature mismatch — if the existing function expects different
  args than `(str) -> list[Task]`, BC-23-1 algorithm breaks at step 2; verify and align
  in M1 before writing BC-23-1.
- R-2: `--tasks` default change (0 → None) may surface latent bugs in callers that
  relied on `0` being falsy; explicit `--tasks 0` now yields `Inconsistency` rather
  than silent zero-task activation — this is intentional per spec §2.
- R-3: `I-TASKSET-IMMUTABLE-1` is a documentation invariant in Phase 23 (no runtime
  checksum yet); enforcement via checksum deferred to Phase 24+ per §10.
