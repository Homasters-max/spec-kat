# Plan_v1 — Phase 1: Foundation

Status: ACTIVE
Spec: specs/Spec_v1_Foundation.md

---

## Milestones

### M1: Package scaffold + core types

```text
Spec:       §2 BC-CORE, §4.1 SDDError, §4.2 CommandHandler, §4.3 EventLevel+classify_event_level
BCs:        BC-CORE
Invariants: I-PK-1, I-PK-4, I-CMD-1a
Depends:    — (first milestone)
Tasks:      T-101 (pyproject), T-102 (errors), T-103 (events), T-104 (types), T-115, T-117
Risks:      Mypy/ruff config errors in pyproject.toml may block all subsequent linting
```

### M2: Database + schema

```text
Spec:       §4.4, §4.5, §4.6 (DB layer), §6 pre/post conditions
BCs:        BC-INFRA (db.py)
Invariants: I-PK-1, I-EL-1, I-EL-5a, I-EL-5b, I-EL-8
Depends:    M1
Tasks:      T-105 (db.py), T-106 (test_db.py), T-116 (SDD_SEQ_CHECKPOINT)
Risks:      DuckDB sequence restart logic (SDD_SEQ_CHECKPOINT) must be set correctly
            or I-EL-5b (seq total order) breaks across reconnections
```

### M3: Event log — sdd_append, sdd_replay, meta_context

```text
Spec:       §4.4–§4.7, §5 invariants I-PK-2/3/4, I-EL-*
BCs:        BC-INFRA (event_log.py)
Invariants: I-PK-2, I-PK-3, I-PK-4, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12
Depends:    M2
Tasks:      T-107 (event_log.py), T-108 (test_event_log.py)
Risks:      I-EL-9 check requires grep on src/sdd/; must exclude infra/db.py correctly.
            I-EL-7 archive logic must not DELETE — test must verify no DELETE in SQL.
            I-EL-8a: meta_context() must propagate via ContextVar, not threading.local.
            sdd_append_batch atomicity: DuckDB transactions must rollback cleanly on failure.
```

### M4: Audit + config loader + shared fixtures

```text
Spec:       §4.8, §2 BC-INFRA (audit.py, config_loader.py)
BCs:        BC-INFRA (audit.py, config_loader.py)
Invariants: I-PK-5, I-PK-4 (config pure)
Depends:    M2
Tasks:      T-109 (audit.py), T-110 (test_audit.py), T-111 (config_loader.py),
            T-112 (test_config_loader.py), T-113 (conftest.py)
Risks:      atomic_write must work cross-filesystem (tmp on same mount as target)
```

### M5: Metrics + batch enforcement (I-M-1)

```text
Spec:       §4.8 record_metric, §5 I-M-1, I-EL-11
BCs:        BC-INFRA (metrics.py)
Invariants: I-M-1, I-EL-11
Depends:    M3
Tasks:      T-118 (metrics.py), T-119 (test_metrics.py)
Risks:      I-M-1 requires TaskCompleted + MetricRecorded in same sdd_append_batch call.
            Record_metric must not be callable without a paired TaskCompleted in batch mode.
```

### M6: Package re-exports + compatibility test

```text
Spec:       §2 public API, §9 Verification
BCs:        BC-CORE (core/__init__.py), BC-INFRA (infra/__init__.py)
Invariants: I-EL-6 (partial)
Depends:    M1–M5
Tasks:      T-114 (infra/__init__), T-115 (core/__init__), T-120 (test_v1_schema.py)
Risks:      Circular imports if __init__.py pulls in too much
```

### M7: Validation + phase summary

```text
Spec:       §5 §PHASE-INV
Invariants: all Phase 1 invariants
Depends:    M1–M6
Tasks:      T-121 (ValidationReport), T-122 (Phase1_Summary + Metrics)
Risks:      none — documentation tasks
```

---

## Risk Notes

- R-1: DuckDB AUTOINCREMENT + SDD_SEQ_CHECKPOINT cross-connection restart. Mitigation: T-116 sets checkpoint=1 and test_db.py verifies I-EL-5b (strictly increasing seq) across 3 reconnections.
- R-2: I-EL-9 grep enforcement. The forbidden_patterns check must correctly exclude `infra/db.py` from the grep scope. Mitigation: T-108 includes a subprocess grep test.
- R-3: `meta_context()` propagation. Must use `contextvars.ContextVar` (not `threading.local`) to satisfy I-EL-8a — causal link must survive async/generator boundaries if introduced later.
- R-4: `sdd_append_batch` atomicity on DuckDB. DuckDB supports transactions but sequence gaps on rollback are acceptable. Mitigation: test injects failure after first event to verify second is not written.
- R-5: mypy strict mode rejects frozen dataclasses with mutable `dict` field. Fixed in Spec §3: `ErrorEvent.context: tuple[tuple[str, Any], ...]`; `Command.payload: Mapping[str, Any]`.
