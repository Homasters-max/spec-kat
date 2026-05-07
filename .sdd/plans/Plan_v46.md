# Plan_v46 — Phase 46: Remove DuckDB (DESTRUCTIVE)

Status: DRAFT
Spec: specs/Spec_v46_RemoveDuckDB.md

---

## Logical Context

type: none
rationale: "Standard new phase. Completes DuckDB removal initiated in Phase 45 (enforce Postgres). Phase 46 finalises the destructive cleanup: removes all DuckDB code paths, replaces test fixtures, migrates invalidate_event to PG, adds enforcement tests."

---

## Milestones

### M0: Preconditions verified

```text
Spec:       §1 — Preconditions (P-1, P-2, P-3)
BCs:        —
Invariants: I-MIGRATION-1
Depends:    — (gate before all implementation milestones)
Risks:      Skipping P-2/P-3 check when DuckDB file absent — mitigated by N/A rule in spec §1
```

### M1: invalidate_event.py migrated to PG + SessionDeclared dedup

```text
Spec:       §3 BC-46-H, §3 BC-46-J
BCs:        BC-46-H, BC-46-J
Invariants: I-INVALIDATE-PG-1, I-SESSION-DEDUP-1, I-DB-ENTRY-1
Depends:    M0
Risks:      BC-46-H MUST precede BC-46-B; if invalidate_event still uses DuckDB SQL
            when db.py DuckDB branch is removed → command breaks at runtime.
            BC-46-J is low-risk (additive change) — scheduled parallel with BC-46-H.
```

### M2: el_kernel.py — minimal extraction

```text
Spec:       §3 BC-46-A
BCs:        BC-46-A
Invariants: I-EL-KERNEL-WIRED-1
Depends:    M0 (not M1; parallel execution allowed per §9)
Risks:      Pure refactor — PostgresEventLog.append() behaviour must remain identical.
            If extraction introduces regression, revert and debug before proceeding to M3.
```

### M3: DuckDB code removal from db.py, connection.py, paths.py

```text
Spec:       §3 BC-46-B, §3 BC-46-C, §3 BC-46-D
BCs:        BC-46-B, BC-46-C, BC-46-D
Invariants: I-NO-DUCKDB-1, I-DB-1
Depends:    M1 (BC-46-H must be done first), M2 (kernel extracted before removing DuckDB path that may interact)
Risks:      DESTRUCTIVE. After BC-46-B, any non-PG URL to open_sdd_connection() raises ValueError.
            All callers must already use PG URLs (verified via M0 preconditions).
            BC-46-D only adds DeprecationWarning — non-breaking, can run in parallel with B/C.
```

### M4: PG test fixtures + pyproject.toml verification

```text
Spec:       §3 BC-46-E, §3 BC-46-F
BCs:        BC-46-E, BC-46-F
Invariants: I-DB-TEST-1, I-NO-DUCKDB-1
Depends:    M3 (DuckDB already removed from production code before replacing fixtures)
Risks:      CI must have SDD_DATABASE_URL set after Phase 46. FakeEventLog unit tests
            must continue working without PG (skip via _require_sdd_database_url guard).
            pg_test_db fixture uses CREATE SCHEMA per test — isolation overhead acceptable
            for Phase 46; optimisation deferred to Phase 47.
```

### M5: Reducer DEBUG for invalidated events (deferrable)

```text
Spec:       §3 BC-46-I
BCs:        BC-46-I
Invariants: (Phase 47 will upgrade to I-INVALIDATED-LOG-1 at INFO level)
Depends:    M3 (DuckDB removed, replay stack is pure PG)
Risks:      Deferrable per spec. If _get_invalidated_seqs() is not accessible in reducer
            context without significant refactor, move to Phase 47 as BC-47-B.
            Grep for existing WARNING pattern first — may already be N/A.
```

### M6: Enforcement tests + final smoke

```text
Spec:       §3 BC-46-G, §10 Verification
BCs:        BC-46-G
Invariants: I-NO-DUCKDB-1, I-DB-ENTRY-1, I-INVALIDATE-PG-1
Depends:    M3, M4 (all DuckDB code removed before enforcement grep tests written)
Risks:      Allowlist in test_no_duckdb_imports_in_src must cover exactly the
            DeprecationWarning string in paths.py — no wider exceptions.
```

---

## Task Mapping (preview for DECOMPOSE)

| Task | BC | Milestone |
|------|----|-----------|
| T-4601 | BC-46-H | M1 — invalidate_event.py PG migration + --force guard |
| T-4602 | BC-46-J | M1 — SessionDeclared stable command_id dedup |
| T-4603 | BC-46-A | M2 — el_kernel.py minimal extraction |
| T-4604 | BC-46-B + BC-46-C | M3 — db.py + connection.py DuckDB removal |
| T-4605 | BC-46-D | M3 — paths.py event_store_file() DeprecationWarning |
| T-4606 | BC-46-E + BC-46-F | M4 — PG test fixtures + pyproject.toml check |
| T-4607 | BC-46-I | M5 — reducer DEBUG for invalidated events (deferrable) |
| T-4608 | BC-46-G | M6 — enforcement tests I-NO-DUCKDB-1 + I-DB-ENTRY-1 |

---

## Risk Notes

- R-1: **Execution order constraint (BC-46-H before BC-46-B)** — `invalidate_event.py` uses DuckDB SQL (`table events`, `? placeholder`). After BC-46-B removes the DuckDB branch from `open_sdd_connection()`, any residual DuckDB call raises ValueError. T-4601 must be committed and tests green before T-4604 starts.

- R-2: **TestEvent WARNING noise in production DB** — seq 25886–25893 are TestEvent records that cause EventReducer WARNING during replay. This does not block Phase 46 tasks but confirms the value of BC-46-H (invalidate-event --force) as a post-phase cleanup action after M6.

- R-3: **CI must provide SDD_DATABASE_URL** — after Phase 46, all integration tests (non-FakeEventLog) require Postgres. If CI does not set `SDD_DATABASE_URL`, those tests skip via `_require_sdd_database_url` guard. The GitHub Actions `services: postgres:` block from Phase 42 CI config must remain active.

- R-4: **BC-46-I deferral risk** — if `_get_invalidated_seqs()` is not directly accessible in reducer without architectural change, defer the entire BC-46-I to Phase 47 (renamed BC-47-B, promoted to INFO level). Phase 47 spec should include this explicitly.

- R-5: **el_kernel.py extraction is a pure refactor** — if `PostgresEventLog.append()` behaviour regresses after BC-46-A, all downstream tests catch it. Extraction does not touch DuckDB code, so rollback is safe.
